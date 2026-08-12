#!/usr/bin/env python3
"""RAW image metadata extractor and dry-run organizer sidecar."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fileorganizer.raw_conversion import (
    RAW_EXTENSIONS as SUPPORTED_RAW_EXTENSIONS,
    archive_as_dng,
    convert_to_dng,
)
from fileorganizer.sidecar_protocol import SidecarEmitter, emit_named


RAW_EXTENSIONS = set(SUPPORTED_RAW_EXTENSIONS)
PLAN_SCHEMA_VERSION = 1
_PROTOCOL = SidecarEmitter("raw")


def emit(event: str, data: dict[str, Any]) -> None:
    """Emit a structured NDJSON event for the WinUI shell."""
    emit_named(_PROTOCOL, event, data)


def _load_rawpy():
    try:
        import rawpy  # type: ignore
        return rawpy
    except ImportError:
        return None


def _tag_text(tags: dict[str, Any], *names: str) -> str:
    for name in names:
        value = tags.get(name)
        if value is not None:
            text = str(value).strip()
            if text:
                return text
    return ""


def _ratio_to_float(value: Any) -> float | None:
    try:
        if hasattr(value, "values"):
            values = value.values
            if values:
                value = values[0]
        if hasattr(value, "num") and hasattr(value, "den"):
            den = float(value.den)
            return float(value.num) / den if den else None
        text = str(value).split()[0]
        if "/" in text:
            num, den = text.split("/", 1)
            den_f = float(den)
            return float(num) / den_f if den_f else None
        return float(text)
    except Exception:
        return None


def _format_focal(value: Any) -> str:
    number = _ratio_to_float(value)
    if number is None:
        text = str(value).strip()
        return text if text.lower().endswith("mm") else text
    if abs(number - round(number)) < 0.05:
        return f"{int(round(number))}mm"
    return f"{number:.1f}mm"


def _normalize_iso(value: Any) -> str:
    text = str(value).strip()
    if not text:
        return ""
    match = re.search(r"\d+", text)
    return match.group(0) if match else text


def _parse_date(value: str) -> datetime | None:
    text = (value or "").strip()
    if not text:
        return None
    for fmt in (
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _display_date(value: str) -> str:
    dt = _parse_date(value)
    if dt is None:
        return value or "Unknown"
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def _metadata_from_exifread(raw_path: str) -> dict[str, str]:
    try:
        import exifread  # type: ignore
    except ImportError:
        return {}

    try:
        with open(raw_path, "rb") as f:
            tags = exifread.process_file(f, stop_tag="UNDEF", details=False)
    except Exception:
        return {}

    if not tags:
        return {}

    focal_value = tags.get("EXIF FocalLength")
    return {
        "make": _tag_text(tags, "Image Make"),
        "model": _tag_text(tags, "Image Model"),
        "date_taken": _tag_text(tags, "EXIF DateTimeOriginal", "Image DateTime"),
        "iso": _normalize_iso(_tag_text(tags, "EXIF ISOSpeedRatings", "EXIF PhotographicSensitivity")),
        "focal_length": _format_focal(focal_value) if focal_value is not None else "",
    }


def _metadata_from_exiftool(raw_path: str) -> dict[str, str]:
    try:
        from fileorganizer.exiftool_extractor import extract_metadata
    except Exception:
        return {}

    data = extract_metadata(Path(raw_path))
    if not data:
        return {}

    return {
        "make": str(data.get("Make") or "").strip(),
        "model": str(data.get("Model") or "").strip(),
        "raw_format": str(
            data.get("FileTypeExtension") or data.get("FileType") or ""
        ).strip(),
        "date_taken": str(data.get("DateTimeOriginal") or data.get("CreateDate") or data.get("ModifyDate") or "").strip(),
        "iso": _normalize_iso(data.get("ISO") or data.get("PhotographicSensitivity") or ""),
        "focal_length": _format_focal(data.get("FocalLength") or "") if data.get("FocalLength") else "",
    }


def _metadata_from_rawpy(raw_path: str, rawpy_module) -> tuple[dict[str, str], str]:
    try:
        with rawpy_module.imread(raw_path) as raw:
            model = str(getattr(raw, "camera_model", "") or "").strip()
            return ({"model": model} if model else {}), "OK"
    except Exception as e:
        return {}, f"Error: {type(e).__name__}"


def _merge_metadata(*parts: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in parts:
        for key, value in part.items():
            if value and not out.get(key):
                out[key] = value
    return out


def extract_exif(raw_path: str, rawpy_module=None) -> dict[str, str]:
    """Extract real RAW metadata when available, without placeholder values."""
    rawpy_module = rawpy_module or _load_rawpy()
    rawpy_meta, status = ({}, "rawpy unavailable")
    if rawpy_module is not None:
        rawpy_meta, status = _metadata_from_rawpy(raw_path, rawpy_module)

    meta = _merge_metadata(
        _metadata_from_exifread(raw_path),
        _metadata_from_exiftool(raw_path),
        rawpy_meta,
    )

    make = meta.get("make", "")
    model = meta.get("model", "")
    camera = " ".join(part for part in (make, model) if part).strip() or "Unknown"
    return {
        "camera": camera,
        "make": make,
        "model": model,
        "raw_format": meta.get("raw_format", "") or Path(raw_path).suffix.lstrip(".").upper(),
        "date_taken": _display_date(meta.get("date_taken", "")),
        "iso": meta.get("iso", "") or "Unknown",
        "focal_length": meta.get("focal_length", "") or "Unknown",
        "status": status,
    }


def _safe_segment(value: str, fallback: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]+', "_", (value or "").strip())
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text[:80] or fallback


def planned_destination(raw_file: Path, exif: dict[str, str], dest_root: Path) -> Path:
    dt = _parse_date(exif.get("date_taken", ""))
    year = dt.strftime("%Y") if dt else "Unknown-Year"
    day = dt.strftime("%Y-%m-%d") if dt else "Unknown-Date"
    camera = _safe_segment(exif.get("camera", ""), "Unknown_Camera")
    return dest_root / year / day / camera / raw_file.name


def write_plan(plan: dict[str, Any], path: str = "") -> str:
    out = Path(path) if path else Path(plan["root"]) / "raw_organize_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(out)


def _move_file(src: Path, dest: Path) -> str:
    if dest.exists():
        return "blocked: destination exists"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dest)
    except OSError:
        shutil.move(str(src), str(dest))
    return "moved"


def convert_dng_file(
    source: str,
    output: str = "",
    archive_root: str = "",
) -> Any:
    """Convert one RAW file or archive it under the canonical RAW tree."""
    source_path = Path(source)
    if archive_root:
        exif = extract_exif(str(source_path), rawpy_module=None)
        return archive_as_dng(source_path, archive_root, exif=exif)
    destination = Path(output) if output else source_path.with_suffix(".dng")
    return convert_to_dng(source_path, destination)


def _run_conversion(source: str, output: str = "", archive_root: str = "") -> int:
    result = convert_dng_file(source, output, archive_root)
    sidecar = result.sidecar
    emit("file", {
        "filename": Path(source).name,
        "path": str(Path(source)),
        "destination": result.destination,
        "status": result.status,
        "backend": result.backend,
        "raw_format": result.detected_format,
        "detection_source": result.detection_source,
        "detail": result.detail,
        "sidecar_status": sidecar.status if sidecar else "not_requested",
        "sidecar_path": sidecar.sidecar_path if sidecar else "",
    })
    emit("complete", {
        "total": 1,
        "converted": 1 if result.ok else 0,
        "status": result.status,
    })
    return 0 if result.ok else 2


def scan_folder(
    root: str,
    mode: str,
    rawpy_module=None,
    dest_root: str = "",
    plan_out: str = "",
    apply: bool = False,
) -> int:
    """Scan a folder for RAW files and emit NDJSON events."""
    _PROTOCOL.reset()
    root_path = Path(root)
    if not root_path.is_dir():
        emit("error", {"code": "invalid_root", "message": f"Not a folder: {root}"})
        return 2

    destination_root = Path(dest_root) if dest_root else root_path
    scanned = 0
    exif_read = 0
    organized = 0
    plan_items: list[dict[str, Any]] = []

    raw_files = []
    for ext in RAW_EXTENSIONS:
        raw_files.extend(root_path.rglob(f"*{ext}"))
        raw_files.extend(root_path.rglob(f"*{ext.upper()}"))

    for raw_file in sorted(set(raw_files)):
        scanned += 1
        if scanned % 10 == 0:
            emit("progress", {
                "scanned": scanned,
                "exif_read": exif_read,
                "organized": organized,
                "status": f"Scanned {scanned} files...",
            })

        exif = extract_exif(str(raw_file), rawpy_module=rawpy_module)
        exif_read += 1
        dest = planned_destination(raw_file, exif, destination_root)
        item_status = exif.get("status", "OK")

        if mode == "organize":
            if item_status.startswith("Error") or item_status == "rawpy unavailable":
                item_status = f"blocked: {item_status}"
            else:
                item_status = _move_file(raw_file, dest) if apply else "planned"
                organized += 1 if item_status in {"planned", "moved"} else 0
            plan_items.append({
                "source": str(raw_file),
                "destination": str(dest),
                "raw_format": exif.get("raw_format", raw_file.suffix.lstrip(".").upper()),
                "camera": exif.get("camera", "Unknown"),
                "date_taken": exif.get("date_taken", "Unknown"),
                "iso": exif.get("iso", "Unknown"),
                "focal_length": exif.get("focal_length", "Unknown"),
                "status": item_status,
            })

        emit("file", {
            "filename": raw_file.name,
            "path": str(raw_file),
            "camera": exif.get("camera", "Unknown"),
            "date_taken": exif.get("date_taken", "Unknown"),
            "iso": exif.get("iso", "Unknown"),
            "focal_length": exif.get("focal_length", "Unknown"),
            "destination": str(dest) if mode == "organize" else "",
            "raw_format": exif.get("raw_format", raw_file.suffix.lstrip(".").upper()),
            "status": item_status,
        })

    if mode == "organize":
        plan = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "root": str(root_path),
            "dest_root": str(destination_root),
            "dry_run": not apply,
            "item_count": len(plan_items),
            "items": plan_items,
        }
        plan_path = write_plan(plan, plan_out)
        emit("plan", {"path": plan_path, "items": len(plan_items), "dry_run": not apply})

    emit("progress", {
        "scanned": scanned,
        "exif_read": exif_read,
        "organized": organized,
        "status": f"Done. Processed {scanned} RAW files.",
    })
    emit("complete", {"total": scanned, "exif_read": exif_read, "organized": organized})
    return 0


def main(argv: list[str] | None = None, rawpy_module_marker: Any = Ellipsis) -> int:
    _PROTOCOL.reset()
    parser = argparse.ArgumentParser(description="RAW photo metadata extractor")
    parser.add_argument("--root", help="Root folder to scan")
    parser.add_argument("--mode", default="preview", choices=["preview", "organize"],
                        help="Mode: preview (read only) or organize (write a plan)")
    parser.add_argument("--dest-root", help="Destination root for organize plans")
    parser.add_argument("--plan-out", help="Write organize plan to this JSON path")
    parser.add_argument("--apply", action="store_true", help="Apply the generated organize plan")
    parser.add_argument("--convert-dng", metavar="FILE", help="Copy or convert one RAW file to DNG")
    parser.add_argument("--output", help="DNG output path for --convert-dng")
    parser.add_argument("--archive-root", help="Archive converted DNG under raw_originals/")
    args = parser.parse_args(argv)

    if args.convert_dng:
        return _run_conversion(args.convert_dng, args.output or "", args.archive_root or "")
    if not args.root:
        parser.error("--root is required unless --convert-dng is used")

    rawpy_module = _load_rawpy() if rawpy_module_marker is Ellipsis else rawpy_module_marker
    if rawpy_module is None:
        _PROTOCOL.emit_capability_error("raw_validation")
        return 2

    return scan_folder(
        args.root,
        args.mode,
        rawpy_module=rawpy_module,
        dest_root=args.dest_root or "",
        plan_out=args.plan_out or "",
        apply=args.apply,
    )


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        emit("error", {"code": "cancelled", "message": "Cancelled."})
        sys.exit(130)
