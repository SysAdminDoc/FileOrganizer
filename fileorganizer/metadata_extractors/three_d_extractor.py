"""Content-aware metadata extraction for glTF, Draco, and USD assets.

The extractor deliberately uses only bounded standard-library parsing.  A
valid glTF 2.0 JSON document or GLB JSON chunk is enough to identify a 3D
model without loading geometry into memory.  USDZ inspection enumerates safe
ZIP members and optionally asks an installed Pixar ``usdcat`` binary to
inspect its USD layers; the optional binary is never required for routing.
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Optional

from fileorganizer.safe_archive import UnsafeArchiveEntryError, safe_extract_path

from ._types import MetadataHint


MODEL_CATEGORY = "3D - Models & Objects"
TAXONOMY = "3d_model"
GLTF_EXTENSIONS = frozenset({".gltf", ".glb"})
USD_EXTENSIONS = frozenset({".usd", ".usda", ".usdc"})
USDZ_EXTENSIONS = frozenset({".usdz"})
DRACO_EXTENSIONS = frozenset({".drc"})
SUPPORTED_EXTENSIONS = GLTF_EXTENSIONS | USD_EXTENSIONS | USDZ_EXTENSIONS | DRACO_EXTENSIONS

_MAX_GLTF_JSON_BYTES = 16 * 1024 * 1024
_MAX_GLB_BYTES = 2 * 1024 * 1024 * 1024
_MAX_USDZ_ENTRIES = 4096
_MAX_USDZ_TOTAL_BYTES = 512 * 1024 * 1024
_MAX_USDZ_ENTRY_BYTES = 128 * 1024 * 1024
_MAX_USDZ_COMPRESSION_RATIO = 1000.0
_MAX_USDZ_USDCAT_LAYERS = 8
_MAX_USDCAT_PREVIEW = 4096

_DRACO_EXTENSION = "KHR_draco_mesh_compression"
_LOD_EXTENSION_MARKER = "lod"
_USD_LAYER_SUFFIXES = frozenset({".usd", ".usda", ".usdc"})
_USD_TEXTURE_SUFFIXES = frozenset({
    ".jpg", ".jpeg", ".png", ".tga", ".tif", ".tiff", ".exr", ".hdr",
    ".ktx", ".ktx2", ".bmp", ".webp",
})


def extract(path: Path, detected_ext: str | None = None) -> Optional[MetadataHint]:
    """Extract a bounded 3D metadata hint for *path*.

    ``detected_ext`` is supplied by the content-type router when a file has a
    misleading or missing suffix.  The original suffix remains in the raw
    evidence so downstream review can see the mismatch.
    """
    if not path or not path.exists() or not path.is_file():
        return None
    ext = (detected_ext or path.suffix).lower()
    if ext == ".gltf":
        return _extract_gltf(path, format_name="gltf", original_ext=path.suffix.lower())
    if ext == ".glb":
        return _extract_glb(path, original_ext=path.suffix.lower())
    if ext == ".usdz":
        return _extract_usdz(path, original_ext=path.suffix.lower())
    if ext in USD_EXTENSIONS:
        return _extract_usd_layer(path, ext, original_ext=path.suffix.lower())
    if ext == ".drc":
        return _draco_hint(
            path,
            original_ext=path.suffix.lower(),
            reason="standalone Draco mesh bitstream (.drc)",
        )
    return None


def _extract_gltf(path: Path, *, format_name: str, original_ext: str) -> Optional[MetadataHint]:
    try:
        if path.stat().st_size > _MAX_GLTF_JSON_BYTES:
            return None
        document = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    return _hint_from_gltf_document(
        document,
        format_name=format_name,
        original_ext=original_ext,
    )


def _extract_glb(path: Path, *, original_ext: str) -> Optional[MetadataHint]:
    try:
        file_size = path.stat().st_size
        if file_size < 20 or file_size > _MAX_GLB_BYTES:
            return None
        with path.open("rb") as stream:
            header = stream.read(12)
            if len(header) != 12:
                return None
            magic, version, declared_length = struct.unpack("<4sII", header)
            if magic != b"glTF" or version != 2 or declared_length != file_size:
                return None

            json_bytes: bytes | None = None
            binary_bytes = 0
            consumed = 12
            while consumed < declared_length:
                chunk_header = stream.read(8)
                if len(chunk_header) != 8:
                    return None
                chunk_length, chunk_type = struct.unpack("<II", chunk_header)
                consumed += 8
                if chunk_length > declared_length - consumed:
                    return None
                if chunk_type == 0x4E4F534A:  # JSON
                    if chunk_length > _MAX_GLTF_JSON_BYTES:
                        return None
                    json_bytes = stream.read(chunk_length)
                    if len(json_bytes) != chunk_length:
                        return None
                else:
                    binary_bytes += chunk_length
                    stream.seek(chunk_length, os.SEEK_CUR)
                consumed += chunk_length
    except (OSError, struct.error):
        return None

    if json_bytes is None:
        return None
    try:
        document = json.loads(json_bytes.decode("utf-8-sig"))
    except (UnicodeError, json.JSONDecodeError):
        return None
    hint = _hint_from_gltf_document(
        document,
        format_name="glb",
        original_ext=original_ext,
    )
    if hint is not None:
        hint.raw["binary_chunk_bytes"] = binary_bytes
    return hint


def _hint_from_gltf_document(
    document: Any,
    *,
    format_name: str,
    original_ext: str,
) -> Optional[MetadataHint]:
    if not isinstance(document, dict):
        return None
    asset = document.get("asset")
    if not isinstance(asset, dict) or str(asset.get("version", "")) != "2.0":
        return None

    extensions_used = _string_list(document.get("extensionsUsed"))
    extensions_required = _string_list(document.get("extensionsRequired"))
    extension_names = set(extensions_used) | set(extensions_required)
    extension_names.update(_nested_extension_names(document))

    meshes = _dict_list(document.get("meshes"))
    primitives = sum(
        len(mesh.get("primitives") or [])
        for mesh in meshes
        if isinstance(mesh.get("primitives"), list)
    )
    nodes = _dict_list(document.get("nodes"))
    skins = _dict_list(document.get("skins"))
    animations = _dict_list(document.get("animations"))
    textures = _dict_list(document.get("textures"))
    images = _dict_list(document.get("images"))
    materials = _dict_list(document.get("materials"))
    scenes = _dict_list(document.get("scenes"))
    rigged = bool(skins) or any(node.get("skin") is not None for node in nodes)
    lod_count = _lod_count(document, extension_names)
    texture_count = len(textures)
    has_draco = _DRACO_EXTENSION in extension_names
    rigging = "rigged" if rigged else "unrigged"

    raw: dict[str, Any] = {
        "format": format_name,
        "original_ext": original_ext,
        "asset_version": str(asset.get("version")),
        "generator": _bounded_text(asset.get("generator")),
        "copyright": _bounded_text(asset.get("copyright")),
        "extensions_used": extensions_used[:64],
        "extensions_required": extensions_required[:64],
        "has_draco": has_draco,
        "mesh_count": len(meshes),
        "primitive_count": primitives,
        "node_count": len(nodes),
        "skin_count": len(skins),
        "animation_count": len(animations),
        "material_count": len(materials),
        "texture_count": texture_count,
        "image_count": len(images),
        "scene_count": len(scenes),
        "rigged": rigged,
        "lod_count": lod_count,
        "taxonomy": TAXONOMY,
        "subtaxonomy": {
            "rigging": rigging,
            "lod_count": lod_count,
            "texture_count": texture_count,
        },
    }
    details = [
        f"{format_name.upper()} 2.0",
        rigging,
        f"{len(meshes)} mesh{'es' if len(meshes) != 1 else ''}",
        f"{texture_count} texture{'s' if texture_count != 1 else ''}",
    ]
    if lod_count:
        details.append(f"{lod_count} LOD level{'s' if lod_count != 1 else ''}")
    if has_draco:
        details.append("KHR_draco_mesh_compression")
    return MetadataHint(
        category=MODEL_CATEGORY,
        confidence=96,
        extractor="three_d",
        reason=", ".join(details),
        raw=raw,
    )


def _extract_usdz(path: Path, *, original_ext: str) -> Optional[MetadataHint]:
    try:
        with zipfile.ZipFile(path, "r") as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos or len(infos) > _MAX_USDZ_ENTRIES:
                return None
            layer_infos: list[zipfile.ZipInfo] = []
            layers: list[str] = []
            texture_count = 0
            total_bytes = 0
            for info in infos:
                normalized = _validate_usdz_member(info.filename)
                if normalized is None:
                    return None
                size = int(info.file_size)
                compressed = int(info.compress_size)
                if size < 0 or size > _MAX_USDZ_ENTRY_BYTES:
                    return None
                total_bytes += size
                if total_bytes > _MAX_USDZ_TOTAL_BYTES:
                    return None
                ratio = float("inf") if size and not compressed else (
                    size / compressed if compressed else 1.0
                )
                if ratio > _MAX_USDZ_COMPRESSION_RATIO:
                    return None
                suffix = Path(normalized).suffix.lower()
                if suffix in _USD_LAYER_SUFFIXES:
                    layer_infos.append(info)
                    layers.append(normalized)
                elif suffix in _USD_TEXTURE_SUFFIXES:
                    texture_count += 1
            if not layer_infos:
                return None

            usdcat = _find_usdcat()
            usdcat_results: list[dict[str, Any]] = []
            rigged = False
            if usdcat:
                with tempfile.TemporaryDirectory(prefix="fileorganizer-usdz-") as temp_dir:
                    for info in layer_infos[:_MAX_USDZ_USDCAT_LAYERS]:
                        normalized = _validate_usdz_member(info.filename)
                        if normalized is None:
                            continue
                        extracted = safe_extract_path(temp_dir, normalized)
                        Path(extracted).parent.mkdir(parents=True, exist_ok=True)
                        try:
                            with archive.open(info, "r") as source, open(extracted, "wb") as target:
                                _copy_bounded(source, target, _MAX_USDZ_ENTRY_BYTES)
                        except (OSError, RuntimeError, ValueError):
                            continue
                        result = _run_usdcat(usdcat, extracted)
                        preview = result.get("stdout", "")
                        rigged = rigged or any(
                            marker in preview
                            for marker in ("SkelRoot", "Skeleton", "SkelAnimation", "UsdSkel")
                        )
                        usdcat_results.append({
                            "layer": normalized,
                            "returncode": result["returncode"],
                            "stdout": preview[:_MAX_USDCAT_PREVIEW],
                            "stderr": result.get("stderr", "")[:1024],
                        })

            rigging = "rigged" if rigged else "unrigged"
            raw: dict[str, Any] = {
                "format": "usdz",
                "original_ext": original_ext,
                "layer_count": len(layers),
                "layers": layers[:128],
                "texture_count": texture_count,
                "usdcat": "available" if usdcat else "not_detected",
                "usdcat_results": usdcat_results,
                "taxonomy": TAXONOMY,
                "subtaxonomy": {
                    "rigging": rigging,
                    "lod_count": 0,
                    "texture_count": texture_count,
                },
                "rigged": rigged,
                "lod_count": 0,
            }
            reason = (
                f"USDZ package with {len(layers)} USD layer"
                f"{'s' if len(layers) != 1 else ''} and {texture_count} texture"
                f"{'s' if texture_count != 1 else ''}"
            )
            return MetadataHint(
                category=MODEL_CATEGORY,
                confidence=94,
                extractor="three_d",
                reason=reason,
                raw=raw,
            )
    except (OSError, zipfile.BadZipFile, RuntimeError):
        return None


def _extract_usd_layer(path: Path, ext: str, *, original_ext: str) -> MetadataHint:
    usdcat = _find_usdcat()
    result = _run_usdcat(usdcat, str(path)) if usdcat else None
    preview = (result or {}).get("stdout", "")
    rigged = any(
        marker in preview
        for marker in ("SkelRoot", "Skeleton", "SkelAnimation", "UsdSkel")
    )
    return MetadataHint(
        category=MODEL_CATEGORY,
        confidence=92,
        extractor="three_d",
        reason=f"USD layer ({ext})" + ("; skeleton data detected" if rigged else ""),
        raw={
            "format": ext.lstrip("."),
            "original_ext": original_ext,
            "usdcat": "available" if usdcat else "not_detected",
            "usdcat_result": (result or {}).get("returncode") if result else None,
            "usdcat_preview": preview[:_MAX_USDCAT_PREVIEW],
            "taxonomy": TAXONOMY,
            "subtaxonomy": {
                "rigging": "rigged" if rigged else "unrigged",
                "lod_count": 0,
                "texture_count": 0,
            },
            "rigged": rigged,
            "lod_count": 0,
            "texture_count": 0,
        },
    )


def _draco_hint(path: Path, *, original_ext: str, reason: str) -> MetadataHint:
    return MetadataHint(
        category=MODEL_CATEGORY,
        confidence=92,
        extractor="three_d",
        reason=reason,
        raw={
            "format": "draco",
            "original_ext": original_ext,
            "has_draco": True,
            "taxonomy": TAXONOMY,
            "subtaxonomy": {
                "rigging": "unknown",
                "lod_count": 0,
                "texture_count": 0,
            },
        },
    )


def _readable_usdcat(value: str) -> str | None:
    candidate = value.strip()
    if not candidate:
        return None
    path = Path(candidate)
    if path.is_file():
        return str(path)
    return shutil.which(candidate)


def _find_usdcat() -> str | None:
    return _readable_usdcat(os.environ.get("FILEORGANIZER_USDCAT", "")) or shutil.which("usdcat")


def _run_usdcat(usdcat: str | None, path: str) -> dict[str, Any]:
    if not usdcat:
        return {"returncode": None, "stdout": "", "stderr": ""}
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 10,
        "check": False,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        completed = subprocess.run([usdcat, path], **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return {"returncode": -1, "stdout": "", "stderr": str(exc)}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout or "",
        "stderr": completed.stderr or "",
    }


def _copy_bounded(source, target, limit: int) -> None:
    written = 0
    while True:
        chunk = source.read(1024 * 1024)
        if not chunk:
            return
        written += len(chunk)
        if written > limit:
            raise RuntimeError("USDZ layer exceeds extraction limit")
        target.write(chunk)


def _validate_usdz_member(name: str) -> str | None:
    normalized = str(name or "").replace("\\", "/")
    path = PurePosixPath(normalized)
    if not normalized or path.is_absolute() or not path.parts:
        return None
    if any(part in {"", ".", ".."} for part in path.parts):
        return None
    if len(path.parts[0]) >= 2 and path.parts[0][1] == ":":
        return None
    try:
        # Keep the shared containment guard as the final check as well.
        safe_extract_path(tempfile.gettempdir(), normalized)
    except UnsafeArchiveEntryError:
        return None
    return "/".join(path.parts)


def _nested_extension_names(document: Any) -> set[str]:
    names: set[str] = set()
    pending: list[Any] = [document]
    seen = 0
    while pending and seen < 200_000:
        current = pending.pop()
        seen += 1
        if isinstance(current, dict):
            extensions = current.get("extensions")
            if isinstance(extensions, dict):
                names.update(str(name) for name in extensions if isinstance(name, str))
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    return names


def _lod_count(document: dict[str, Any], extension_names: set[str]) -> int:
    count = 0
    pending: list[Any] = [document]
    seen = 0
    while pending and seen < 200_000:
        current = pending.pop()
        seen += 1
        if isinstance(current, dict):
            extensions = current.get("extensions")
            if isinstance(extensions, dict):
                for name, payload in extensions.items():
                    if _LOD_EXTENSION_MARKER not in str(name).lower():
                        continue
                    if isinstance(payload, dict):
                        ids = payload.get("ids") or payload.get("levels")
                        if isinstance(ids, list):
                            count = max(count, len(ids) + 1)
                        else:
                            count = max(count, 1)
                    else:
                        count = max(count, 1)
            pending.extend(current.values())
        elif isinstance(current, list):
            pending.extend(current)
    if count == 0 and any(_LOD_EXTENSION_MARKER in name.lower() for name in extension_names):
        return 1
    return count


def _dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item)[:256] for item in value if isinstance(item, str)][:128]


def _bounded_text(value: Any, limit: int = 256) -> str:
    return str(value)[:limit] if isinstance(value, str) else ""
