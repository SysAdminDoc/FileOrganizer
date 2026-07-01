#!/usr/bin/env python3
"""
Stage 0 content-type pre-routing for design assets.

Google Magika is preferred because it identifies file content from bytes rather
than names. python-magic remains a lightweight fallback when Magika is not
installed. This module is deliberately optional: every public function returns
None/False on missing dependencies or detection errors.
"""
from __future__ import annotations

import importlib.util
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class ContentTypeHint:
    """Normalized content-type result from Magika or python-magic."""

    label: str
    mime_type: str
    description: str = ""
    confidence: float = 0.0
    source: str = ""


_ARCHIVE_MIMES = frozenset({
    "application/zip",
    "application/x-7z-compressed",
    "application/x-rar-compressed",
    "application/vnd.rar",
    "application/gzip",
    "application/x-tar",
    "application/x-bzip2",
    "application/x-xz",
})

_EXTENSIONS_BY_MIME = {
    # Adobe / design project files
    "application/vnd.adobe.photoshop": {".psd", ".psb"},
    "image/vnd.adobe.photoshop": {".psd", ".psb"},
    "image/x-psd": {".psd", ".psb"},
    "application/postscript": {".ai", ".eps", ".ps"},
    # Fonts
    "font/ttf": {".ttf"},
    "font/otf": {".otf"},
    "font/collection": {".ttc"},
    "font/woff": {".woff"},
    "font/woff2": {".woff2"},
    "application/font-woff": {".woff"},
    "application/font-woff2": {".woff2"},
    "application/vnd.ms-fontobject": {".eot"},
    # Audio / video
    "video/mp4": {".mp4", ".m4v"},
    "video/quicktime": {".mov"},
    "video/x-matroska": {".mkv"},
    "video/x-msvideo": {".avi"},
    "video/webm": {".webm"},
    "application/mxf": {".mxf"},
    "audio/mpeg": {".mp3"},
    "audio/wav": {".wav"},
    "audio/x-wav": {".wav"},
    "audio/flac": {".flac"},
    "audio/aac": {".aac"},
    "audio/ogg": {".ogg"},
    "audio/mp4": {".m4a", ".aac"},
    "audio/aiff": {".aiff", ".aif"},
    # General file families useful for mismatch handling.
    "application/pdf": {".pdf"},
    "text/html": {".html", ".htm"},
    "text/css": {".css"},
    "application/javascript": {".js", ".mjs"},
    "application/json": {".json"},
    "image/jpeg": {".jpg", ".jpeg"},
    "image/png": {".png"},
    "image/webp": {".webp"},
    "image/tiff": {".tif", ".tiff"},
    "image/gif": {".gif"},
    "image/svg+xml": {".svg"},
    "image/avif": {".avif"},
    "image/jxl": {".jxl"},
    "application/x-executable": {".exe"},
    "application/x-dosexec": {".exe"},
    "application/x-msdownload": {".exe", ".dll"},
    **{mime: {ext} for mime, ext in [
        ("application/zip", ".zip"),
        ("application/x-7z-compressed", ".7z"),
        ("application/x-rar-compressed", ".rar"),
        ("application/vnd.rar", ".rar"),
        ("application/gzip", ".gz"),
        ("application/x-tar", ".tar"),
        ("application/x-bzip2", ".bz2"),
        ("application/x-xz", ".xz"),
    ]},
}

_EXTENSIONS_BY_LABEL = {
    "aep": {".aep"},
    "after-effects": {".aep"},
    "photoshop": {".psd", ".psb"},
    "psd": {".psd", ".psb"},
    "ttf": {".ttf"},
    "otf": {".otf"},
    "ttc": {".ttc"},
    "woff": {".woff"},
    "woff2": {".woff2"},
    "mp4": {".mp4", ".m4v"},
    "mov": {".mov"},
    "quicktime": {".mov"},
    "mkv": {".mkv"},
    "avi": {".avi"},
    "webm": {".webm"},
    "mxf": {".mxf"},
    "mp3": {".mp3"},
    "wav": {".wav"},
    "flac": {".flac"},
    "aac": {".aac"},
    "ogg": {".ogg"},
    "aiff": {".aiff", ".aif"},
    "zip": {".zip"},
    "7z": {".7z"},
    "rar": {".rar"},
    "pdf": {".pdf"},
    "html": {".html", ".htm"},
    "svg": {".svg"},
    "jpg": {".jpg", ".jpeg"},
    "jpeg": {".jpg", ".jpeg"},
    "png": {".png"},
    "webp": {".webp"},
    "tiff": {".tif", ".tiff"},
    "gif": {".gif"},
    "avif": {".avif"},
    "jxl": {".jxl"},
    "jpegxl": {".jxl"},
    "jpeg-xl": {".jxl"},
    "exe": {".exe"},
    "dll": {".dll"},
}

_EXTRACTOR_EXT_PRIORITY = (
    ".aep",
    ".psd", ".psb",
    ".ttf", ".otf", ".ttc", ".woff", ".woff2",
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf",
    ".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".aiff",
)

_CANONICAL_MIME_ROUTES = {
    "image/jpeg": ("Stock Photos - General", 88),
    "image/png": ("Stock Photos - General", 88),
    "image/webp": ("Stock Photos - General", 88),
    "image/tiff": ("Stock Photos - General", 88),
    "image/svg+xml": ("Illustrator - Vectors & Assets", 88),
    "image/avif": ("Stock Photos - General", 88),
    "image/jxl": ("Stock Photos - General", 88),
    "font/ttf": ("Fonts & Typography", 92),
    "font/otf": ("Fonts & Typography", 92),
    "font/collection": ("Fonts & Typography", 92),
    "font/woff": ("Fonts & Typography", 92),
    "font/woff2": ("Fonts & Typography", 92),
    "audio/mpeg": ("Stock Music & Audio", 85),
    "audio/wav": ("Stock Music & Audio", 85),
    "audio/x-wav": ("Stock Music & Audio", 85),
    "audio/flac": ("Stock Music & Audio", 85),
    "audio/aac": ("Stock Music & Audio", 85),
    "audio/ogg": ("Stock Music & Audio", 85),
    "video/mp4": ("Stock Footage - General", 85),
    "video/quicktime": ("Stock Footage - General", 85),
    "video/x-matroska": ("Stock Footage - General", 85),
    "video/x-msvideo": ("Stock Footage - General", 85),
    "video/webm": ("Stock Footage - General", 85),
    "application/pdf": ("Print - Brochures & Books", 70),
    "text/html": ("Web Template", 80),
    "application/javascript": ("Web Template", 75),
    "application/json": ("Software & Utilities", 65),
    "application/x-executable": ("Software & Utilities", 88),
    "application/x-dosexec": ("Software & Utilities", 88),
    "application/x-msdownload": ("Software & Utilities", 88),
}

_MAGIKA = None
_MAGIKA_IMPORT_ATTEMPTED = False
_MAGIC_LIB = None
_MAGIC_IMPORT_ATTEMPTED = False


def model_cache_dir() -> Path:
    """Return the preferred local Magika model cache directory."""
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "FileOrganizer" / "models" / "magika"
    return Path.home() / ".fileorganizer" / "models" / "magika"


def _get_magika():
    global _MAGIKA, _MAGIKA_IMPORT_ATTEMPTED
    if _MAGIKA_IMPORT_ATTEMPTED:
        return _MAGIKA
    _MAGIKA_IMPORT_ATTEMPTED = True
    if importlib.util.find_spec("magika") is None:
        return None
    try:
        from magika import Magika  # type: ignore

        # Prefer the bundled model. The cache dir function is exposed so callers
        # have one repo-standard location if a future custom model is configured.
        _MAGIKA = Magika()
    except Exception:
        _MAGIKA = None
    return _MAGIKA


def _get_magic():
    global _MAGIC_LIB, _MAGIC_IMPORT_ATTEMPTED
    if _MAGIC_IMPORT_ATTEMPTED:
        return _MAGIC_LIB
    _MAGIC_IMPORT_ATTEMPTED = True
    if importlib.util.find_spec("magic") is None:
        return None
    try:
        import magic  # type: ignore

        _MAGIC_LIB = magic
    except Exception:
        _MAGIC_LIB = None
    return _MAGIC_LIB


def detect_content_type(path: Path) -> Optional[ContentTypeHint]:
    """Detect content type using Magika, with python-magic as fallback."""
    if not path or not Path(path).is_file():
        return None
    magika = _get_magika()
    if magika is not None:
        try:
            result = magika.identify_path(path)
            if getattr(result, "ok", True):
                output = getattr(result, "output", None)
                if output is not None:
                    mime = str(getattr(output, "mime_type", "") or "").lower()
                    label = str(getattr(output, "ct_label", "") or getattr(output, "label", "") or "").lower()
                    description = str(getattr(output, "description", "") or "")
                    confidence = float(getattr(output, "score", 0.0) or 0.0)
                    if mime or label:
                        return ContentTypeHint(
                            label=label,
                            mime_type=mime,
                            description=description,
                            confidence=confidence,
                            source="magika",
                        )
        except Exception:
            pass

    magic = _get_magic()
    if magic is not None:
        try:
            mime = magic.from_file(str(path), mime=True)
            if mime:
                return ContentTypeHint(
                    label="",
                    mime_type=str(mime).lower(),
                    description="",
                    confidence=1.0,
                    source="python-magic",
                )
        except Exception:
            pass
    return None


def detect_mime_type(path: Path) -> Optional[str]:
    """Compatibility wrapper returning only the MIME type."""
    hint = detect_content_type(path)
    return hint.mime_type if hint else None


def expected_extensions(hint: ContentTypeHint) -> set[str]:
    """Return known extensions for a normalized content-type hint."""
    out: set[str] = set()
    if hint.mime_type:
        out.update(_EXTENSIONS_BY_MIME.get(hint.mime_type, set()))
    if hint.label:
        out.update(_EXTENSIONS_BY_LABEL.get(hint.label, set()))
    if not out:
        if hint.mime_type.startswith("image/"):
            out.update({".jpg", ".jpeg", ".png", ".webp", ".gif", ".tif", ".tiff", ".svg"})
        elif hint.mime_type.startswith("video/"):
            out.update({".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v"})
        elif hint.mime_type.startswith("audio/"):
            out.update({".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac", ".aiff"})
        elif hint.mime_type.startswith("font/"):
            out.update({".ttf", ".otf", ".ttc", ".woff", ".woff2"})
    return out


def detect_extension_mismatch(path: Path) -> Optional[dict[str, object]]:
    """Return mismatch metadata when bytes and suffix disagree."""
    hint = detect_content_type(path)
    if hint is None:
        return None
    expected = expected_extensions(hint)
    if not expected:
        return None
    actual = Path(path).suffix.lower()
    if actual in expected:
        return None
    return {
        "extension_mismatch": True,
        "original_ext": actual,
        "detected_exts": sorted(expected),
        "detected_mime": hint.mime_type,
        "detected_label": hint.label,
        "detected_description": hint.description,
        "detected_confidence": hint.confidence,
        "detector": hint.source,
    }


def extractor_extension_for_path(path: Path) -> Optional[str]:
    """Return a content-detected extension supported by metadata extractors."""
    mismatch = detect_extension_mismatch(path)
    if mismatch is None:
        return None
    detected_exts = set(mismatch.get("detected_exts", []))
    for ext in _EXTRACTOR_EXT_PRIORITY:
        if ext in detected_exts:
            return ext
    return None


def route_by_mime_type(path: Path) -> Optional[tuple[str, int]]:
    """Return a canonical design category for content-only routing."""
    hint = detect_content_type(path)
    if hint is None:
        return None
    if hint.mime_type in _ARCHIVE_MIMES and detect_extension_mismatch(path):
        return "_Review", 92
    if hint.mime_type in _CANONICAL_MIME_ROUTES:
        return _CANONICAL_MIME_ROUTES[hint.mime_type]
    if hint.mime_type.startswith("image/"):
        return "Stock Photos - General", 70
    if hint.mime_type.startswith("video/"):
        return "Stock Footage - General", 70
    if hint.mime_type.startswith("audio/"):
        return "Stock Music & Audio", 70
    if hint.mime_type.startswith("font/"):
        return "Fonts & Typography", 88
    return None


def is_obfuscated_archive(path: Path) -> bool:
    """Return True when a non-archive suffix contains archive bytes."""
    hint = detect_content_type(path)
    if hint is None or hint.mime_type not in _ARCHIVE_MIMES:
        return False
    return detect_extension_mismatch(path) is not None
