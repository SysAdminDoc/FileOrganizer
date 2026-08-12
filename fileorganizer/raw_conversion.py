"""Safe, optional conversion and archival helpers for camera RAW files.

The conversion boundary is deliberately copy-only: a source RAW is never
deleted or overwritten.  ExifTool identifies the input when available, while
the extension remains a bounded fallback for offline cameras and test
fixtures.  ImageMagick is the supported DNG-writing backend because ``dcraw``
does not emit a DNG container itself.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from fileorganizer.xmp_sidecar import XmpSidecarResult, write_classification_sidecar


RAW_EXTENSIONS = frozenset({
    ".dng", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srw",
    ".orf", ".rw2", ".raf", ".pef", ".rwl", ".x3f", ".3fr", ".dcr",
    ".kdc", ".mrw", ".raw", ".iiq", ".fff", ".mef", ".mos", ".cap",
})

_FORMAT_ALIASES = {
    "DNG": ".dng",
    "CR2": ".cr2",
    "CR3": ".cr3",
    "CRW": ".crw",
    "NEF": ".nef",
    "NRW": ".nrw",
    "ARW": ".arw",
    "SRW": ".srw",
    "ORF": ".orf",
    "RW2": ".rw2",
    "RAF": ".raf",
    "PEF": ".pef",
    "RWL": ".rwl",
    "X3F": ".x3f",
    "3FR": ".3fr",
    "DCR": ".dcr",
    "KDC": ".kdc",
    "MRW": ".mrw",
    "RAW": ".raw",
    "IIQ": ".iiq",
    "FFF": ".fff",
    "MEF": ".mef",
    "MOS": ".mos",
    "CAP": ".cap",
}


@dataclass(frozen=True)
class RawFormatInfo:
    """Bounded identity evidence for one RAW file."""

    format_name: str
    extension: str
    source: str
    exiftool_file_type: str = ""


@dataclass(frozen=True)
class DngConversionResult:
    """Result of a copy/conversion attempt."""

    status: str
    source: str
    destination: str = ""
    backend: str = ""
    detected_format: str = ""
    detection_source: str = ""
    detail: str = ""
    sidecar: XmpSidecarResult | None = None

    @property
    def ok(self) -> bool:
        return self.status in {"copied", "converted", "already_dng"}


def detect_raw_format(path: str | os.PathLike[str]) -> RawFormatInfo | None:
    """Identify a RAW file with ExifTool, falling back to a known suffix.

    The fallback is intentionally limited to the explicit extension allowlist;
    arbitrary filenames are never sent to an image converter.
    """
    source_path = Path(path)
    if not source_path.is_file():
        return None

    exiftool_type = ""
    try:
        from fileorganizer.exiftool_extractor import extract_metadata

        metadata = extract_metadata(source_path) or {}
    except Exception:
        metadata = {}
    for key in ("FileTypeExtension", "FileType", "DetectedFileType"):
        value = metadata.get(key)
        if value:
            exiftool_type = str(value).strip()[:64]
            extension = _extension_from_type(exiftool_type)
            if extension:
                return RawFormatInfo(
                    format_name=extension.lstrip(".").upper(),
                    extension=extension,
                    source="exiftool",
                    exiftool_file_type=exiftool_type,
                )

    extension = source_path.suffix.casefold()
    if extension in RAW_EXTENSIONS:
        return RawFormatInfo(
            format_name=extension.lstrip(".").upper(),
            extension=extension,
            source="extension_fallback",
            exiftool_file_type=exiftool_type,
        )
    return None


def find_dng_converter() -> str | None:
    """Return an explicitly configured or PATH-resolved ImageMagick binary."""
    override = os.environ.get("FILEORGANIZER_IMAGE_MAGICK", "").strip()
    if override:
        if Path(override).is_file():
            return str(Path(override).resolve())
        resolved = shutil.which(override)
        if resolved:
            return resolved
    for candidate in ("magick.exe", "magick"):
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    if os.name != "nt":
        return shutil.which("convert")
    return None


def convert_to_dng(
    source: str | os.PathLike[str],
    destination: str | os.PathLike[str],
    *,
    runner: Callable[..., Any] = subprocess.run,
) -> DngConversionResult:
    """Copy a DNG or convert another RAW file without mutating the source."""
    source_path = Path(source).resolve()
    destination_path = Path(destination).resolve()
    info = detect_raw_format(source_path)
    if info is None:
        return DngConversionResult("not_raw", str(source_path), detail="Input is not a supported RAW file.")
    if destination_path.suffix.casefold() != ".dng":
        return DngConversionResult(
            "invalid_destination", str(source_path), str(destination_path),
            detected_format=info.format_name, detection_source=info.source,
            detail="DNG conversion destination must use the .dng extension.",
        )
    if source_path == destination_path:
        if info.extension == ".dng":
            return DngConversionResult(
                "already_dng", str(source_path), str(destination_path), "copy",
                info.format_name, info.source, "Source is already a DNG file.",
            )
        return DngConversionResult(
            "invalid_destination", str(source_path), str(destination_path),
            detected_format=info.format_name, detection_source=info.source,
            detail="Source and destination must be different files.",
        )
    if destination_path.exists():
        return DngConversionResult(
            "blocked", str(source_path), str(destination_path),
            detected_format=info.format_name, detection_source=info.source,
            detail="Destination already exists; no file was overwritten.",
        )

    try:
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        if info.extension == ".dng":
            shutil.copy2(source_path, destination_path)
            return DngConversionResult(
                "copied", str(source_path), str(destination_path), "copy",
                info.format_name, info.source, "DNG source copied without transcoding.",
            )

        converter = find_dng_converter()
        if not converter:
            return DngConversionResult(
                "unavailable", str(source_path), str(destination_path),
                detected_format=info.format_name, detection_source=info.source,
                detail="ImageMagick was not found; the RAW source was left in place.",
            )
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 300,
            "check": False,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = runner([converter, str(source_path), str(destination_path)], **kwargs)
        if completed.returncode != 0:
            _remove_partial(destination_path)
            return DngConversionResult(
                "failed", str(source_path), str(destination_path), "imagemagick",
                info.format_name, info.source,
                _command_detail(completed),
            )
        if not destination_path.is_file() or destination_path.stat().st_size <= 0:
            _remove_partial(destination_path)
            return DngConversionResult(
                "failed", str(source_path), str(destination_path), "imagemagick",
                info.format_name, info.source,
                "ImageMagick returned success but produced no DNG output.",
            )
        return DngConversionResult(
            "converted", str(source_path), str(destination_path), "imagemagick",
            info.format_name, info.source, "RAW converted to DNG.",
        )
    except (OSError, subprocess.SubprocessError) as exc:
        _remove_partial(destination_path)
        return DngConversionResult(
            "failed", str(source_path), str(destination_path), "imagemagick",
            info.format_name, info.source, f"DNG conversion failed: {type(exc).__name__}.",
        )


def archive_as_dng(
    source: str | os.PathLike[str],
    archive_root: str | os.PathLike[str],
    *,
    exif: dict[str, str] | None = None,
    runner: Callable[..., Any] = subprocess.run,
) -> DngConversionResult:
    """Convert/copy into ``raw_originals/YYYY/YYYY-MM-DD/Camera``.

    A same-basename XMP companion is attempted after a successful conversion;
    missing ExifTool never turns a successful DNG conversion into a failure.
    """
    source_path = Path(source).resolve()
    exif = exif or {}
    destination = _archive_destination(source_path, archive_root, exif)
    result = convert_to_dng(source_path, destination, runner=runner)
    if not result.ok:
        return result
    sidecar = write_classification_sidecar(
        result.destination,
        category="RAW Camera Originals",
        confidence=100,
        method="dng_conversion",
        detail=(
            f"source_format={result.detected_format}; "
            f"backend={result.backend}; detection={result.detection_source}"
        ),
        metadata=exif,
    )
    return DngConversionResult(
        result.status, result.source, result.destination, result.backend,
        result.detected_format, result.detection_source, result.detail, sidecar,
    )


def _archive_destination(
    source: Path,
    archive_root: str | os.PathLike[str],
    exif: dict[str, str],
) -> Path:
    date = _parse_date(exif.get("date_taken", ""))
    year = date.strftime("%Y") if date else "Unknown-Year"
    day = date.strftime("%Y-%m-%d") if date else "Unknown-Date"
    camera = _safe_segment(exif.get("camera", ""), "Unknown_Camera")
    stem = _safe_segment(source.stem, "image")
    candidate = Path(archive_root).resolve() / "raw_originals" / year / day / camera / f"{stem}.dng"
    return _collision_safe(candidate)


def _collision_safe(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem} ({index}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError("could not find a collision-safe DNG destination")


def _extension_from_type(value: str) -> str | None:
    normalized = re.sub(r"[^A-Za-z0-9]+", "", value).upper()
    return _FORMAT_ALIASES.get(normalized)


def _parse_date(value: str) -> datetime | None:
    text = str(value or "").strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def _safe_segment(value: str, fallback: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]+', "_", str(value or "").strip())
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text[:80] or fallback


def _command_detail(completed: Any) -> str:
    output = str(getattr(completed, "stderr", "") or getattr(completed, "stdout", "") or "")
    output = re.sub(r"[\r\n\t]+", " ", output).strip()
    return output[:512] or "ImageMagick returned a non-zero exit code."


def _remove_partial(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


__all__ = [
    "DngConversionResult",
    "RAW_EXTENSIONS",
    "RawFormatInfo",
    "archive_as_dng",
    "convert_to_dng",
    "detect_raw_format",
    "find_dng_converter",
]
