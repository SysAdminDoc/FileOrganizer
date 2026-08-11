"""Fail-closed Qwen2.5-VL access through the local llama.cpp CLI."""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


MAX_PROMPT_LENGTH = 8_000
MAX_OUTPUT_LENGTH = 64_000
MAX_OCR_LENGTH = 16_000
MAX_DESCRIPTION_LENGTH = 2_000
MAX_IMAGE_BYTES = 32 * 1024 * 1024
DEFAULT_MAX_TOKENS = 1_024
DEFAULT_CONTEXT_SIZE = 16_384


class VlmUnavailable(RuntimeError):
    """Raised when the local multimodal runtime cannot be used."""


class VlmResponseError(ValueError):
    """Raised when a VLM response cannot be trusted as structured output."""


@dataclass(frozen=True)
class VlmClassification:
    category: str
    confidence: int
    description: str
    ocr_text: str
    requires_ocr: bool
    has_text_overlay: bool
    model: str


def find_cli(explicit: str | os.PathLike[str] | None = None) -> str | None:
    """Resolve an explicitly configured or PATH-provided llama.cpp CLI."""
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return str(candidate)
        return shutil.which(str(explicit))
    configured = os.environ.get("FILEORGANIZER_LLAMA_CLI", "").strip()
    if configured:
        resolved = find_cli(configured)
        if resolved:
            return resolved
    for name in ("llama-qwen2vl-cli", "llama-qwen2vl-cli.exe", "llama-mtmd-cli", "llama-cli"):
        resolved = shutil.which(name)
        if resolved:
            return resolved
    return None


def _mime_type(path: str) -> str:
    suffix = Path(path).suffix.casefold()
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
        ".gif": "image/gif", ".bmp": "image/bmp", ".tif": "image/tiff",
        ".tiff": "image/tiff",
    }.get(suffix, "image/png")


def image_data_uri(path: str | os.PathLike[str]) -> str:
    """Read one image as a bounded data URI for Python chat-handler clients."""
    value = Path(path)
    if not value.is_file():
        raise VlmUnavailable(f"image does not exist: {path}")
    try:
        if value.stat().st_size > MAX_IMAGE_BYTES:
            raise VlmUnavailable(f"image exceeds {MAX_IMAGE_BYTES} byte limit: {path}")
        payload = base64.b64encode(value.read_bytes()).decode("ascii")
    except OSError as exc:
        raise VlmUnavailable(f"could not read image: {exc}") from exc
    return f"data:{_mime_type(str(value))};base64,{payload}"


def _bounded_text(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


def _json_object(raw: str) -> dict:
    text = re.sub(r"<think>.*?</think>", "", str(raw or ""), flags=re.DOTALL).strip()
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL).strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if not match:
            raise VlmResponseError("VLM response did not contain a JSON object")
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise VlmResponseError("VLM response contained invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise VlmResponseError("VLM response must be a JSON object")
    return parsed


def parse_classification(
    raw: str,
    *,
    model: str,
    allowed_categories: Sequence[str] = (),
) -> VlmClassification:
    """Validate the bounded JSON contract emitted by Qwen2.5-VL."""
    parsed = _json_object(raw[:MAX_OUTPUT_LENGTH])
    category = _bounded_text(parsed.get("category"), 256)
    if not category or (allowed_categories and category not in allowed_categories):
        raise VlmResponseError("VLM returned an unknown or empty category")
    confidence = parsed.get("confidence")
    if type(confidence) is not int or not 0 <= confidence <= 100:
        raise VlmResponseError("VLM confidence must be an integer from 0 to 100")
    flags = ("requires_ocr", "has_text_overlay")
    for flag in flags:
        if flag in parsed and type(parsed[flag]) is not bool:
            raise VlmResponseError(f"VLM {flag} must be a boolean")
    return VlmClassification(
        category=category,
        confidence=confidence,
        description=_bounded_text(parsed.get("description"), MAX_DESCRIPTION_LENGTH),
        ocr_text=_bounded_text(parsed.get("ocr_text"), MAX_OCR_LENGTH),
        requires_ocr=parsed.get("requires_ocr", False),
        has_text_overlay=parsed.get("has_text_overlay", False),
        model=_bounded_text(model, 256),
    )


def run_cli(
    image_path: str | os.PathLike[str],
    *,
    model_path: str | os.PathLike[str],
    mmproj_path: str | os.PathLike[str],
    prompt: str,
    cli_path: str | os.PathLike[str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    context_size: int = DEFAULT_CONTEXT_SIZE,
    timeout: float = 300.0,
    gpu_layers: int | None = None,
) -> str:
    """Run one hidden, non-interactive llama.cpp multimodal invocation."""
    executable = find_cli(cli_path)
    if executable is None:
        raise VlmUnavailable("llama.cpp multimodal CLI was not found on PATH")
    image = Path(image_path)
    model = Path(model_path)
    mmproj = Path(mmproj_path)
    for label, value in (("image", image), ("model", model), ("mmproj", mmproj)):
        if not value.is_file():
            raise VlmUnavailable(f"{label} does not exist: {value}")
    if not 1 <= int(max_tokens) <= 16_384:
        raise ValueError("max_tokens is outside the supported range")
    if not 512 <= int(context_size) <= 131_072:
        raise ValueError("context_size is outside the supported range")
    if not 0.1 <= float(timeout) <= 3_600:
        raise ValueError("timeout is outside the supported range")
    command = [
        executable,
        "--ctx-size", str(int(context_size)),
        "-n", str(int(max_tokens)),
        "-m", str(model),
        "--mmproj", str(mmproj),
        "--image", str(image),
        "-p", _bounded_text(prompt, MAX_PROMPT_LENGTH),
    ]
    if gpu_layers is not None:
        if not 0 <= int(gpu_layers) <= 999:
            raise ValueError("gpu_layers is outside the supported range")
        command.extend(["--n-gpu-layers", str(int(gpu_layers))])
    kwargs: dict[str, object] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": float(timeout),
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run(command, **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        raise VlmUnavailable(f"llama.cpp invocation failed: {exc}") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "").strip()[-2_000:]
        raise VlmUnavailable(f"llama.cpp exited {completed.returncode}: {detail}")
    return str(completed.stdout or "")


def classify_qwen(
    image_path: str | os.PathLike[str],
    *,
    model_path: str | os.PathLike[str],
    mmproj_path: str | os.PathLike[str],
    model_label: str = "Qwen2.5-VL-7B",
    categories: Sequence[str] = (),
    cli_path: str | os.PathLike[str] | None = None,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    context_size: int = DEFAULT_CONTEXT_SIZE,
    timeout: float = 300.0,
    gpu_layers: int | None = None,
) -> VlmClassification:
    category_text = "\n".join(f"- {item}" for item in categories[:512])
    prompt = (
        "Inspect the supplied image as a local file librarian. Read visible text "
        "when possible and classify the image conservatively. Return JSON only with "
        "these fields: category (string), confidence (integer 0-100), description "
        "(short string), ocr_text (string), requires_ocr (boolean), and "
        "has_text_overlay (boolean). Use confidence below 70 when evidence is weak."
    )
    if category_text:
        prompt += "\nAllowed categories:\n" + category_text
    raw = run_cli(
        image_path,
        model_path=model_path,
        mmproj_path=mmproj_path,
        prompt=prompt,
        cli_path=cli_path,
        max_tokens=max_tokens,
        context_size=context_size,
        timeout=timeout,
        gpu_layers=gpu_layers,
    )
    return parse_classification(
        raw,
        model=model_label,
        allowed_categories=categories,
    )
