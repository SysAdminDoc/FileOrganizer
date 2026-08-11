"""Deterministic dependency and capability health for every shell workflow."""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as distribution_version
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 1
VALID_STATUSES = frozenset({"available", "unavailable", "not_checked"})


@dataclass(frozen=True)
class Requirement:
    label: str
    module: str = ""
    distribution: str = ""
    binary: str = ""


@dataclass(frozen=True)
class CapabilitySpec:
    workflow: str
    capability: str
    requirements: tuple[Requirement, ...]
    scope: str
    remediation: str
    required: bool = False
    online_required: bool = False


PYTHON = Requirement("Python standard library")


SPECS: tuple[CapabilitySpec, ...] = (
    CapabilitySpec("organize", "persisted_move_plans", (PYTHON,),
                   "Preview, apply, journal, and undo persisted move plans", "No action required.", True),
    CapabilitySpec("smart", "extension_routing", (PYTHON,),
                   "Route every supported extension to a workflow", "No action required.", True),
    CapabilitySpec("smart", "audio_metadata", (Requirement("mutagen", "mutagen", "mutagen"),),
                   "Read audio tags for Smart Sort naming", "Install the pinned requirements file."),
    CapabilitySpec("smart", "video_filename_metadata", (Requirement("GuessIt", "guessit", "guessit"),),
                   "Parse release names for Smart Sort video naming", "Install the pinned requirements file."),
    CapabilitySpec("smart", "book_metadata", (Requirement("EbookLib", "ebooklib", "EbookLib"),),
                   "Read EPUB metadata for Smart Sort naming", "Install the pinned requirements file."),
    CapabilitySpec("smart", "font_metadata", (Requirement("fonttools", "fontTools", "fonttools"),),
                   "Read font name and style tables for Smart Sort", "Install the pinned requirements file."),
    CapabilitySpec("files", "extension_routing", (PYTHON,),
                   "Classify files into deterministic extension buckets", "No action required.", True),
    CapabilitySpec("cleanup", "filesystem_scanners", (PYTHON,),
                   "Find empty, temporary, large, and stale paths", "No action required.", True),
    CapabilitySpec("cleanup", "archive_validation", (PYTHON,),
                   "Validate ZIP and TAR structure when requested", "No action required."),
    CapabilitySpec("duplicates", "exact_duplicates", (PYTHON,),
                   "Progressive size, prefix, and full SHA-256 matching", "No action required.", True),
    CapabilitySpec(
        "duplicates", "similar_images",
        (Requirement("Pillow", "PIL", "Pillow"),
         Requirement("ImageHash", "imagehash", "ImageHash"),
         Requirement("pybktree", "pybktree", "pybktree")),
        "Perceptual image hashes and BK-tree similarity clusters",
        "Install Pillow, ImageHash, and pybktree from the pinned requirements file.",
    ),
    CapabilitySpec(
        "clip_index", "clip_visual_index",
        (Requirement("open_clip_torch", "open_clip", "open_clip_torch"),
         Requirement("PyTorch", "torch", "torch"),
         Requirement("sqlite-vec", "sqlite_vec", "sqlite-vec")),
        "768-dimensional ViT-L-14 image embeddings and local vector search",
        "Install the optional CLIP stack: open_clip_torch, torch, and sqlite-vec.",
    ),
    CapabilitySpec(
        "chroma_index", "cross_modal_search",
        (Requirement("ChromaDB", "chromadb", "chromadb"),
         Requirement("open_clip_torch", "open_clip", "open_clip_torch"),
         Requirement("PyTorch", "torch", "torch")),
        "Persistent local image embeddings with CLIP image/text similarity search",
        "Install the optional cross-modal stack: chromadb, open_clip_torch, and torch.",
    ),
    CapabilitySpec(
        "vlm", "qwen2vl_cli",
        (Requirement("llama.cpp Qwen2-VL CLI", binary="llama-qwen2vl-cli"),),
        "Optional low-confidence image/document classification with OCR evidence",
        "Build or install llama.cpp's Qwen2-VL multimodal CLI and configure its path.",
    ),
    CapabilitySpec("music", "musicbrainz_lookup",
                   (Requirement("musicbrainzngs", "musicbrainzngs", "musicbrainzngs"),),
                   "Look up canonical album and track metadata",
                   "Install the pinned requirements file and verify network access.",
                   required=True, online_required=True),
    CapabilitySpec("music", "audio_tag_write", (Requirement("mutagen", "mutagen", "mutagen"),),
                   "Read and write ID3, Vorbis, FLAC, and MP4 tags",
                   "Install the pinned requirements file."),
    CapabilitySpec(
        "music", "acoustic_fingerprint",
        (Requirement("pyacoustid", "acoustid", "pyacoustid"),
         Requirement("Chromaprint fpcalc", binary="fpcalc")),
        "Fingerprint untagged audio and query AcoustID",
        "Install pyacoustid and Chromaprint/fpcalc, then add an AcoustID key in Settings.",
        online_required=True,
    ),
    CapabilitySpec("video", "release_name_parser", (Requirement("GuessIt", "guessit", "guessit"),),
                   "Parse title, episode, codec, source, and release group",
                   "Install the pinned requirements file.", True),
    CapabilitySpec("books", "ebook_metadata", (Requirement("EbookLib", "ebooklib", "EbookLib"),),
                   "Read EPUB and compatible e-book metadata",
                   "Install the pinned requirements file.", True),
    CapabilitySpec("books", "pdf_metadata", (Requirement("pypdf", "pypdf", "pypdf"),),
                   "Read PDF metadata and scan initial pages for ISBNs",
                   "Install the pinned requirements file."),
    CapabilitySpec("books", "isbn_enrichment", (Requirement("isbnlib", "isbnlib", "isbnlib"),),
                   "Enrich ISBN matches using online metadata providers",
                   "Install isbnlib and verify network access.", online_required=True),
    CapabilitySpec("fonts", "font_metadata", (Requirement("fonttools", "fontTools", "fonttools"),),
                   "Read OpenType name, OS/2, family, and style tables",
                   "Install the pinned requirements file.", True),
    CapabilitySpec("code", "project_detection", (PYTHON,),
                   "Detect project markers and count source-language extensions",
                   "No action required.", True),
    CapabilitySpec(
        "subtitles", "subtitle_download",
        (Requirement("Subliminal", "subliminal", "subliminal"),
         Requirement("babelfish", "babelfish", "babelfish")),
        "Search subtitle providers and save the best language match",
        "Install Subliminal/babelfish and verify provider network access.",
        required=True, online_required=True,
    ),
    CapabilitySpec("subtitles", "embedded_subtitle_detection",
                   (Requirement("enzyme", "enzyme", "enzyme"),),
                   "Detect embedded MKV subtitle tracks before download",
                   "Install the pinned requirements file."),
    CapabilitySpec("photos", "image_metadata", (Requirement("Pillow", "PIL", "Pillow"),),
                   "Read dimensions, EXIF, camera, lens, and GPS metadata",
                   "Install the pinned requirements file."),
    CapabilitySpec("photos", "raw_exif_fallback", (Requirement("exifread", "exifread", "ExifRead"),),
                   "Read EXIF from RAW formats Pillow cannot decode",
                   "Install the pinned requirements file."),
    CapabilitySpec("photos", "heif_metadata", (Requirement("pillow-heif", "pillow_heif", "pillow-heif"),),
                   "Decode HEIC and HEIF image metadata",
                   "Install the pinned requirements file."),
    CapabilitySpec("raw", "raw_validation", (Requirement("rawpy", "rawpy", "rawpy"),),
                   "Open and validate RAW camera files",
                   "Install rawpy in the configured Python environment.", True),
    CapabilitySpec("raw", "raw_exif_fallback", (Requirement("exifread", "exifread", "ExifRead"),),
                   "Supplement RAW metadata without full pixel decoding",
                   "Install the pinned requirements file."),
    CapabilitySpec("comics", "comic_page_validation", (Requirement("Pillow", "PIL", "Pillow"),),
                   "Validate comic pages and inspect the first image",
                   "Install the pinned requirements file.", True),
    CapabilitySpec(
        "comics", "rar_archives",
        (Requirement("rarfile", "rarfile", "rarfile"),
         Requirement("RAR extraction backend", binary="unrar|unar|7z|bsdtar")),
        "Inspect CBR/RAR comic archives",
        "Install rarfile plus unrar, unar, 7-Zip, or bsdtar and put the binary on PATH.",
    ),
    CapabilitySpec("comics", "seven_zip_archives", (Requirement("py7zr", "py7zr", "py7zr"),),
                   "Inspect CB7/7-Zip comic archives", "Install the pinned requirements file."),
    CapabilitySpec("watch", "polling_watch", (PYTHON,),
                   "Detect stable new files with bounded persisted polling state",
                   "No action required.", True),
    CapabilitySpec("toolbox", "local_cli_tools", (PYTHON,),
                   "Run local audit, validation, database, and undo utilities",
                   "No action required.", True),
    CapabilitySpec("metadata", "image_metadata", (Requirement("Pillow", "PIL", "Pillow"),),
                   "Generic image dimensions and EXIF", "Install the pinned requirements file."),
    CapabilitySpec("metadata", "audio_metadata", (Requirement("mutagen", "mutagen", "mutagen"),),
                   "Generic audio tags", "Install the pinned requirements file."),
    CapabilitySpec("metadata", "video_metadata", (Requirement("ffprobe", binary="ffprobe"),),
                   "Generic video stream and container metadata", "Install FFmpeg and put ffprobe on PATH."),
    CapabilitySpec(
        "metadata", "xmp_sidecar_write",
        (Requirement("PyExifTool", "exiftool", "PyExifTool"),
         Requirement("ExifTool >=12.15", binary="exiftool")),
        "Write IPTC 2025.1 AI provenance and standard XMP fields to sidecars",
        "Install PyExifTool==0.5.6 and ExifTool 12.15 or newer on PATH.",
    ),
    CapabilitySpec("metadata", "pdf_metadata", (Requirement("pypdf", "pypdf", "pypdf"),),
                   "Generic PDF metadata", "Install the pinned requirements file."),
    CapabilitySpec("metadata", "docx_metadata", (Requirement("python-docx", "docx", "python-docx"),),
                   "Generic Word document metadata", "Install the pinned requirements file."),
    CapabilitySpec("metadata", "xlsx_metadata", (Requirement("openpyxl", "openpyxl", "openpyxl"),),
                   "Generic Excel workbook metadata", "Install the pinned requirements file."),
)


WORKFLOW_ALIASES = {
    "dedup": "duplicates",
    "capabilities": "all",
}


def _module_available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def _package_version(distribution: str) -> str:
    try:
        return distribution_version(distribution)[:128]
    except (PackageNotFoundError, ValueError):
        return "unknown"


def _binary_path(binary: str) -> str | None:
    if binary == "fpcalc":
        override = os.environ.get("FPCALC", "").strip()
        if override and Path(override).is_file():
            return override
    if binary == "llama-qwen2vl-cli":
        override = os.environ.get("FILEORGANIZER_LLAMA_CLI", "").strip()
        if override and Path(override).is_file():
            return override
    for candidate in binary.split("|"):
        path = shutil.which(candidate)
        if path:
            return path
    return None


def _binary_version(path: str) -> str:
    if Path(path).stem.casefold() == "exiftool":
        available, detail = _probe_exiftool_binary(path)
        return detail if available else f"not usable ({detail})"
    return f"detected ({Path(path).name}; version query not run)"


def _probe_exiftool_binary(path: str) -> tuple[bool, str]:
    """Check the minimum ExifTool version without opening a console window."""
    try:
        kwargs: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "timeout": 3,
            "check": False,
        }
        if os.name == "nt":
            kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        completed = subprocess.run([path, "-ver"], **kwargs)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"query failed: {exc}"
    raw = (completed.stdout or completed.stderr or "").strip()
    version_text = raw.splitlines()[0].strip() if raw else "unknown"
    try:
        from fileorganizer.xmp_sidecar import MIN_EXIFTOOL_VERSION, parse_exiftool_version
        parsed = parse_exiftool_version(version_text)
        minimum = MIN_EXIFTOOL_VERSION
        width = max(len(parsed or ()), len(minimum))
        meets_minimum = parsed is not None and (
            tuple(parsed) + (0,) * (width - len(parsed))
            >= tuple(minimum) + (0,) * (width - len(minimum))
        )
    except (ImportError, TypeError, ValueError):
        meets_minimum = False
    if completed.returncode != 0:
        return False, f"{version_text} (version query exited {completed.returncode})"
    return meets_minimum, f"{version_text} (minimum 12.15)"


def _probe_requirement(requirement: Requirement) -> tuple[bool, str]:
    if requirement == PYTHON:
        return True, f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if requirement.binary:
        path = _binary_path(requirement.binary)
        if not path:
            return False, "not detected"
        if requirement.binary == "exiftool":
            available, detail = _probe_exiftool_binary(path)
            return available, detail
        return True, _binary_version(path)
    if requirement.module and _module_available(requirement.module):
        return True, _package_version(requirement.distribution or requirement.module)
    return False, "not installed"


def _record(spec: CapabilitySpec) -> dict[str, Any]:
    probes = [_probe_requirement(requirement) for requirement in spec.requirements]
    available = all(result[0] for result in probes)
    if not available:
        status = "unavailable"
        detail = "One or more dependencies were not detected."
    elif spec.online_required:
        status = "not_checked"
        detail = "Local dependencies are present; network service and credentials were not checked."
    else:
        status = "available"
        detail = "All local dependencies were detected."
    versions = "; ".join(
        f"{requirement.label} {probe[1]}" for requirement, probe in zip(spec.requirements, probes)
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "workflow": spec.workflow,
        "capability": spec.capability,
        "dependency": " + ".join(requirement.label for requirement in spec.requirements),
        "detected_version": versions,
        "scope": spec.scope,
        "online_required": spec.online_required,
        "required": spec.required,
        "status": status,
        "detail": detail,
        "remediation": spec.remediation,
    }


def capability_matrix(workflow: str = "all") -> list[dict[str, Any]]:
    """Return sorted, schema-stable capability rows for *workflow*."""
    selected = WORKFLOW_ALIASES.get(workflow, workflow)
    rows = [_record(spec) for spec in SPECS if selected == "all" or spec.workflow == selected]
    return sorted(rows, key=lambda row: (str(row["workflow"]), str(row["capability"])))


def get_capability(workflow: str, capability: str) -> dict[str, Any]:
    for row in capability_matrix(workflow):
        if row["capability"] == capability:
            return row
    raise KeyError(f"Unknown capability {workflow}:{capability}")


def capability_error(
    workflow: str,
    capability: str,
    message: str | None = None,
) -> dict[str, Any]:
    """Build the common terminal error envelope for an unavailable capability."""
    health = dict(get_capability(workflow, capability))
    health["status"] = "unavailable"
    health["detail"] = "The capability failed its runtime dependency check."
    return {
        "event": "error",
        "code": "capability_unavailable",
        "message": message or f"{health['scope']} is unavailable. {health['remediation']}",
        "capability_health": health,
    }
