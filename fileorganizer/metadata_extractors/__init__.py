"""
fileorganizer.metadata_extractors — Stage-1 pre-AI classification hints.

Each extractor reads file content (not just the name) to produce a
high-confidence category hint. Items resolved here at confidence >= 90 skip
downstream stages (marketplace lookup, embeddings, LLM) entirely.

Entry point: extract_hint(item, source_dir) -> MetadataHint | None.

Returns None when:
- The optional dependency for the matching extractor isn't installed
- The file is unreadable / malformed / empty
- The extractor's confidence falls below the per-type threshold

A returned MetadataHint always has a canonical category name (validated against
the classify_design._CATEGORY_SET allowlist by the caller).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ._types import MetadataHint
from . import psd_extractor, font_extractor, audio_extractor, video_extractor

__all__ = [
    "MetadataHint",
    "extract_hint",
    "extract_for_path",
    "psd_extractor",
    "font_extractor",
    "audio_extractor",
    "video_extractor",
]


# Map dominant file extension -> extractor module exposing .extract(Path).
_EXT_DISPATCH = {
    # PSD / Photoshop
    ".psd": psd_extractor,
    ".psb": psd_extractor,
    # Fonts
    ".ttf": font_extractor,
    ".otf": font_extractor,
    ".ttc": font_extractor,
    ".woff": font_extractor,
    ".woff2": font_extractor,
    # Audio
    ".mp3": audio_extractor,
    ".flac": audio_extractor,
    ".wav": audio_extractor,
    ".ogg": audio_extractor,
    ".m4a": audio_extractor,
    ".aac": audio_extractor,
    ".aiff": audio_extractor,
    # Video
    ".mp4": video_extractor,
    ".mov": video_extractor,
    ".mkv": video_extractor,
    ".avi": video_extractor,
    ".webm": video_extractor,
    ".m4v": video_extractor,
    ".mxf": video_extractor,
    ".prores": video_extractor,
}


def extract_for_path(path: Path) -> Optional[MetadataHint]:
    """Dispatch a single file path to the matching extractor."""
    if not path or not path.exists() or not path.is_file():
        return None
    ext = path.suffix.lower()
    mod = _EXT_DISPATCH.get(ext)
    if mod is None:
        return None
    try:
        return mod.extract(path)
    except Exception:
        # Extractors should swallow their own errors, but defend in depth.
        return None


def extract_hint(item: dict, source_dir: Optional[str] = None) -> Optional[MetadataHint]:
    """Resolve a classification hint for a classify_design batch item.

    item shape (the relevant fields):
      - name: folder or file name (relative to source_dir)
      - file_mode: True if item is a single file, False if a folder
      - extensions: list of extensions found in the folder (peek result)

    For file_mode items: the extractor for the file's extension is called directly.
    For folder items: the dominant file (largest .psd, single .ttf, first video, etc.)
      drives the dispatch.
    """
    if not item:
        return None
    name = item.get("name") or ""
    if not name:
        return None
    # Resolve to a real path.
    base = Path(source_dir) if source_dir else None
    if not base:
        # Caller didn't provide a source_dir; we can't open the file.
        return None
    target = base / name
    if not target.exists():
        return None
    if target.is_file():
        return extract_for_path(target)
    if target.is_dir():
        primary = _select_primary_file(target, item.get("extensions") or [])
        if primary is None:
            return None
        return extract_for_path(primary)
    return None


def _select_primary_file(folder: Path, ext_hint: list[str]) -> Optional[Path]:
    """Pick the dominant file in a folder for metadata-driven classification.

    Priority:
      1. If any .ttf/.otf — return the first (font folder).
      2. Else if any .psd/.psb — return the largest (PSD bundle).
      3. Else if any video — return the largest.
      4. Else if any audio — return the largest.
    """
    try:
        files = [p for p in folder.iterdir() if p.is_file()]
    except OSError:
        return None
    if not files:
        return None

    def first_with_ext(exts):
        for p in sorted(files, key=lambda f: f.name.lower()):
            if p.suffix.lower() in exts:
                return p
        return None

    def largest_with_ext(exts):
        candidates = [p for p in files if p.suffix.lower() in exts]
        if not candidates:
            return None
        try:
            return max(candidates, key=lambda f: f.stat().st_size)
        except OSError:
            return candidates[0]

    font = first_with_ext({".ttf", ".otf", ".ttc"})
    if font is not None:
        return font
    psd = largest_with_ext({".psd", ".psb"})
    if psd is not None:
        return psd
    video = largest_with_ext({".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf"})
    if video is not None:
        return video
    audio = largest_with_ext({".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac"})
    if audio is not None:
        return audio
    return None
