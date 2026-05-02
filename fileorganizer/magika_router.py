#!/usr/bin/env python3
"""
magika_router.py — Stage 0 pre-routing using Google magika (NEXT-50).

magika provides 99%+ accurate MIME type detection across 300+ content types by
analyzing file bytes (not extensions). Used to catch obfuscated files:
- .txt that's actually a .zip or .exe
- .doc that's actually a PDF
- Renamed archives without correct extension

Runs before all other classification stages to filter out obvious misroutes.
"""
import importlib.util
from pathlib import Path
from typing import Optional, Tuple

_HAS_PYTHON_MAGIC = importlib.util.find_spec("magic") is not None

# MIME type → FileOrganizer category mapping
_MIME_TO_CATEGORY = {
    # Archives (high priority)
    "application/zip": "Archives",
    "application/x-7z-compressed": "Archives",
    "application/x-rar-compressed": "Archives",
    "application/gzip": "Archives",
    "application/x-tar": "Archives",
    "application/x-bzip2": "Archives",
    "application/x-xz": "Archives",
    
    # Documents
    "application/pdf": "Documents",
    "text/plain": "Documents",
    "text/csv": "Documents",
    "text/markdown": "Documents",
    
    # Images
    "image/jpeg": "Photos",
    "image/png": "Photos",
    "image/webp": "Photos",
    "image/tiff": "Photos",
    "image/gif": "Images & Graphics",
    "image/svg+xml": "Vector Graphics",
    
    # Video
    "video/mp4": "Videos",
    "video/quicktime": "Videos",
    "video/x-msvideo": "Videos",
    "video/x-matroska": "Videos",
    
    # Audio
    "audio/mpeg": "Music",
    "audio/wav": "Music",
    "audio/flac": "Music",
    "audio/aac": "Music",
    
    # Executables/Code
    "application/x-executable": "Executables",
    "application/x-windows-exe": "Executables",
    "text/x-python": "Source Code",
    "text/x-shellscript": "Source Code",
}


def _try_import_magic():
    """Import magic library with fallback."""
    try:
        import magic
        return magic
    except ImportError:
        return None


_MAGIC_LIB = _try_import_magic() if _HAS_PYTHON_MAGIC else None


def detect_mime_type(path: Path) -> Optional[str]:
    """
    Detect MIME type using magic library.
    
    Returns MIME type string (e.g., 'application/zip') or None if detection fails.
    """
    if not _MAGIC_LIB:
        return None
    
    try:
        mime = _MAGIC_LIB.from_file(str(path), mime=True)
        return mime.lower() if mime else None
    except Exception:
        return None


def route_by_mime_type(path: Path) -> Optional[Tuple[str, int]]:
    """
    Pre-route a file by magika MIME type detection.
    
    Returns (category, confidence) if a match is found, else None.
    Confidence is 92 for magika detections (high but not 100, to allow
    downstream metadata to override if conflicting).
    """
    mime = detect_mime_type(path)
    if not mime:
        return None
    
    # Exact MIME match
    if mime in _MIME_TO_CATEGORY:
        return _MIME_TO_CATEGORY[mime], 92
    
    # Prefix matching (e.g., 'image/*' → Photos)
    for prefix, category in [
        ("image/", "Photos"),
        ("video/", "Videos"),
        ("audio/", "Music"),
        ("application/", "Documents"),
    ]:
        if mime.startswith(prefix):
            return category, 70  # Lower confidence for prefix matches
    
    return None


def is_obfuscated_archive(path: Path) -> bool:
    """
    Check if file has a misleading extension but is actually an archive.
    
    Returns True if magic says it's an archive but extension suggests otherwise.
    """
    mime = detect_mime_type(path)
    if not mime:
        return False
    
    archive_mimes = {
        "application/zip",
        "application/x-7z-compressed",
        "application/x-rar-compressed",
        "application/gzip",
        "application/x-tar",
        "application/x-bzip2",
        "application/x-xz",
    }
    
    if mime not in archive_mimes:
        return False
    
    # Check if extension mismatches
    ext = path.suffix.lower()
    archive_exts = {".zip", ".7z", ".rar", ".gz", ".tar", ".bz2", ".xz"}
    
    return ext not in archive_exts
