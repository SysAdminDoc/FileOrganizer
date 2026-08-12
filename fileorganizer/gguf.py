"""Bounded GGUF metadata inspection and explicit Ollama model registration."""
from __future__ import annotations

import json
import os
import re
import shutil
import struct
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from fileorganizer.config import _APP_DATA_DIR


_REGISTRY_FILE = os.path.join(_APP_DATA_DIR, "gguf_models.json")
_MAX_METADATA_KEYS = 4096
_MAX_STRING_BYTES = 1_048_576
_MAX_ARRAY_ITEMS = 4096
_MAX_CONTEXT = 131_072
_DEFAULT_CONTEXT = 4096


class GgufError(ValueError):
    """Raised when a GGUF file is invalid or cannot be safely inspected."""


class GgufUnavailable(RuntimeError):
    """Raised when an explicit Ollama registration cannot be completed."""


_FILE_TYPE_NAMES = {
    0: "F32", 1: "F16", 2: "Q4_0", 3: "Q4_1", 6: "Q5_0", 7: "Q5_1",
    8: "Q8_0", 9: "Q8_1", 10: "Q2_K", 11: "Q3_K_S", 12: "Q3_K_M",
    13: "Q3_K_L", 14: "Q4_K_S", 15: "Q4_K_M", 16: "Q5_K_S",
    17: "Q5_K_M", 18: "Q6_K", 19: "TQ1_0", 20: "TQ2_0", 21: "IQ2_XXS",
    22: "IQ2_XS", 23: "IQ3_XXS", 24: "IQ1_S", 25: "IQ4_NL", 26: "IQ3_S",
    27: "IQ3_M", 28: "IQ2_S", 29: "IQ2_M", 30: "IQ4_XS", 31: "IQ1_M",
}
_VALUE_TYPES = {
    0: ("<B", 1),   # UINT8
    1: ("<b", 1),   # INT8
    2: ("<H", 2),   # UINT16
    3: ("<h", 2),   # INT16
    4: ("<I", 4),   # UINT32
    5: ("<i", 4),   # INT32
    6: ("<f", 4),   # FLOAT32
    7: ("<?", 1),   # BOOL
    10: ("<Q", 8),  # UINT64
    11: ("<q", 8),  # INT64
    12: ("<d", 8),  # FLOAT64
}


class _Reader:
    def __init__(self, handle):
        self.handle = handle

    def read(self, size: int) -> bytes:
        payload = self.handle.read(size)
        if len(payload) != size:
            raise GgufError("GGUF metadata is truncated")
        return payload

    def unpack(self, fmt: str):
        return struct.unpack(fmt, self.read(struct.calcsize(fmt)))[0]

    def string(self) -> str:
        length = self.unpack("<Q")
        if length > _MAX_STRING_BYTES:
            raise GgufError("GGUF string exceeds the metadata safety limit")
        return self.read(int(length)).decode("utf-8", errors="replace")


def _read_value(reader: _Reader, value_type: int):
    if value_type == 8:  # STRING
        return reader.string()
    if value_type == 9:  # ARRAY
        item_type = reader.unpack("<I")
        count = reader.unpack("<Q")
        if count > _MAX_ARRAY_ITEMS:
            raise GgufError("GGUF metadata array exceeds the safety limit")
        return [_read_value(reader, item_type) for _ in range(int(count))]
    spec = _VALUE_TYPES.get(value_type)
    if spec is None:
        raise GgufError(f"unsupported GGUF metadata type: {value_type}")
    fmt, _size = spec
    return reader.unpack(fmt)


def inspect_gguf(path: str | os.PathLike[str]) -> dict:
    """Read model metadata without loading tensor data into memory."""
    model_path = Path(path)
    if not model_path.is_file():
        raise GgufError(f"GGUF model does not exist: {model_path}")
    try:
        file_size = model_path.stat().st_size
    except OSError as exc:
        raise GgufError(f"could not stat GGUF model: {exc}") from exc
    if file_size < 24:
        raise GgufError("GGUF file is too small")

    try:
        with model_path.open("rb") as handle:
            reader = _Reader(handle)
            if reader.read(4) != b"GGUF":
                raise GgufError("file does not have a GGUF header")
            version = reader.unpack("<I")
            if version not in {1, 2, 3}:
                raise GgufError(f"unsupported GGUF version: {version}")
            tensor_count = reader.unpack("<Q")
            metadata_count = reader.unpack("<Q")
            if metadata_count > _MAX_METADATA_KEYS:
                raise GgufError("GGUF metadata key count exceeds the safety limit")
            metadata = {}
            for _ in range(int(metadata_count)):
                key = reader.string()
                if len(key) > 1024:
                    raise GgufError("GGUF metadata key exceeds the safety limit")
                metadata[key] = _read_value(reader, reader.unpack("<I"))
    except OSError as exc:
        raise GgufError(f"could not read GGUF model: {exc}") from exc

    architecture = str(metadata.get("general.architecture", "") or "")
    context_value = None
    if architecture:
        context_value = metadata.get(f"{architecture}.context_length")
    if context_value is None:
        for key, value in metadata.items():
            if key.endswith(".context_length"):
                context_value = value
                break
    try:
        context_length = int(context_value)
    except (TypeError, ValueError):
        context_length = _DEFAULT_CONTEXT
    context_length = max(512, min(_MAX_CONTEXT, context_length))

    chat_template = str(metadata.get("tokenizer.chat_template", "") or "")
    chat_template = chat_template[:16_384]
    file_type_value = metadata.get("general.file_type")
    try:
        file_type_number = int(file_type_value)
    except (TypeError, ValueError):
        file_type_number = -1
    quantization = _FILE_TYPE_NAMES.get(
        file_type_number, str(file_type_value or "unknown")[:64]
    )
    return {
        "path": str(model_path.resolve()),
        "name": model_path.stem,
        "size_bytes": file_size,
        "version": version,
        "tensor_count": int(tensor_count),
        "metadata_count": int(metadata_count),
        "architecture": architecture,
        "context_length": context_length,
        "chat_template": chat_template,
        "quantization": quantization,
        "metadata": metadata,
    }


def _validate_model_name(value: str) -> str:
    name = re.sub(r"[^a-zA-Z0-9._:/-]+", "-", str(value or "").strip()).strip("-./:")
    if not name:
        raise ValueError("Ollama model name cannot be empty")
    return name[:128].lower()


def default_ollama_name(path: str | os.PathLike[str]) -> str:
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", Path(path).stem).strip("-.").lower()
    return _validate_model_name(f"fileorganizer/{stem or 'custom-gguf'}:latest")


def _validate_mmproj(path: str | os.PathLike[str] | None) -> str:
    if not path:
        return ""
    candidate = Path(path)
    if not candidate.is_file() or candidate.suffix.casefold() != ".gguf":
        raise ValueError("multimodal projector must be an existing .gguf file")
    return str(candidate.resolve())


def _read_registry() -> list[dict]:
    try:
        with open(_REGISTRY_FILE, "r", encoding="utf-8") as handle:
            value = json.load(handle)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return []
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict) and item.get("path")]


def load_registered_models() -> list[dict]:
    """Return persisted registrations with bounded, JSON-safe fields."""
    result = []
    for item in _read_registry():
        try:
            context_length = int(item.get("context_length", _DEFAULT_CONTEXT))
        except (TypeError, ValueError):
            context_length = _DEFAULT_CONTEXT
        try:
            ollama_name = _validate_model_name(item.get("ollama_name", "custom-gguf:latest"))
        except ValueError:
            ollama_name = "custom-gguf:latest"
        result.append({
            "path": str(item.get("path", ""))[:1024],
            "ollama_name": ollama_name,
            "name": str(item.get("name", ""))[:256],
            "architecture": str(item.get("architecture", ""))[:128],
            "context_length": max(512, min(_MAX_CONTEXT, context_length)),
            "chat_template": str(item.get("chat_template", ""))[:16_384],
            "quantization": str(item.get("quantization", "unknown"))[:64],
            "mmproj_path": str(item.get("mmproj_path", ""))[:1024],
            "created_at": str(item.get("created_at", ""))[:64],
        })
    return result


def _save_registry(models: list[dict]) -> None:
    os.makedirs(os.path.dirname(_REGISTRY_FILE) or ".", exist_ok=True)
    temp_name = ""
    try:
        fd, temp_name = tempfile.mkstemp(
            prefix="gguf_models.", suffix=".tmp", dir=os.path.dirname(_REGISTRY_FILE) or ".",
        )
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(models, handle, indent=2)
            handle.write("\n")
        os.replace(temp_name, _REGISTRY_FILE)
    except OSError:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise


def register_gguf(
    path: str | os.PathLike[str],
    *,
    ollama_name: str = "",
    mmproj_path: str | os.PathLike[str] | None = None,
) -> dict:
    """Inspect and persist one local GGUF registration."""
    info = inspect_gguf(path)
    model_name = _validate_model_name(ollama_name or default_ollama_name(path))
    projector = _validate_mmproj(mmproj_path)
    record = {
        "path": info["path"],
        "name": info["name"],
        "ollama_name": model_name,
        "architecture": info["architecture"],
        "context_length": info["context_length"],
        "chat_template": info["chat_template"],
        "quantization": info["quantization"],
        "mmproj_path": projector,
        "created_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    models = _read_registry()
    replaced = False
    for index, existing in enumerate(models):
        if os.path.normcase(str(existing.get("path", ""))) == os.path.normcase(record["path"]):
            models[index] = record
            replaced = True
            break
    if not replaced:
        models.append(record)
    _save_registry(models)
    return record


def _find_ollama() -> str | None:
    configured = os.environ.get("FILEORGANIZER_OLLAMA", "").strip()
    if configured and Path(configured).is_file():
        return configured
    found = shutil.which("ollama.exe" if os.name == "nt" else "ollama")
    return found


def _subprocess_kwargs(timeout: float) -> dict:
    kwargs = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": timeout,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return kwargs


def _modelfile(record: dict, directory: str) -> str:
    model_path = Path(record["path"]).resolve().as_posix()
    lines = [f'FROM "{model_path}"']
    context_length = max(512, min(_MAX_CONTEXT, int(record.get("context_length", _DEFAULT_CONTEXT))))
    lines.append(f"PARAMETER num_ctx {context_length}")
    template = str(record.get("chat_template", "") or "")
    if template and '"""' not in template and "\x00" not in template:
        lines.extend(["TEMPLATE \"\"\"", template, "\"\"\""])
    path = Path(directory) / "Modelfile"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def create_ollama_model(
    record: dict,
    *,
    ollama_binary: str | os.PathLike[str] | None = None,
    timeout: float = 1800,
) -> dict:
    """Create the registered GGUF as an Ollama model without shell execution."""
    binary = str(ollama_binary or _find_ollama() or "")
    if not binary:
        raise GgufUnavailable("Ollama executable was not found on PATH")
    model_path = Path(record.get("path", ""))
    if not model_path.is_file():
        raise GgufUnavailable(f"registered GGUF model does not exist: {model_path}")
    model_name = _validate_model_name(record.get("ollama_name", ""))
    with tempfile.TemporaryDirectory(prefix="fileorganizer-gguf-") as directory:
        modelfile = _modelfile(record, directory)
        command = [binary, "create", model_name, "-f", modelfile]
        try:
            completed = subprocess.run(command, **_subprocess_kwargs(timeout))
        except (OSError, subprocess.SubprocessError) as exc:
            raise GgufUnavailable(f"Ollama model creation failed: {exc}") from exc
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()[-2_000:]
            raise GgufUnavailable(
                f"Ollama model creation exited {completed.returncode}: {detail}"
            )
        return {
            "ollama_name": model_name,
            "output": str(completed.stdout or "").strip()[-2_000:],
        }


__all__ = [
    "GgufError", "GgufUnavailable", "create_ollama_model", "default_ollama_name",
    "inspect_gguf", "load_registered_models", "register_gguf",
]
