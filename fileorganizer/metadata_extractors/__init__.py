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
from . import aep_extractor, psd_extractor, font_extractor, audio_extractor, video_extractor

__all__ = [
    "MetadataHint",
    "extract_hint",
    "extract_for_path",
    "aep_extractor",
    "psd_extractor",
    "font_extractor",
    "audio_extractor",
    "video_extractor",
]


# Map dominant file extension -> extractor module exposing .extract(Path).
_EXT_DISPATCH = {
    # After Effects
    ".aep": aep_extractor,
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
    if mod is not None:
        try:
            hint = mod.extract(path)
        except Exception:
            hint = None
        if hint is not None:
            return _attach_content_mismatch(path, hint)
    return _extract_from_content_type(path)


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
      1. If any .aep — return the best-scored project file.
      2. Else if any .ttf/.otf — return the first (font folder).
      3. Else if any .psd/.psb — return the largest (PSD bundle).
      4. Else if any video — return the largest.
      5. Else if any audio — return the largest.
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

    aep = _best_aep_file(folder, files, ext_hint)
    if aep is not None:
        return aep
    font = first_with_ext({".ttf", ".otf", ".ttc", ".woff", ".woff2"})
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
    content_detected = _select_content_detected_file(files)
    if content_detected is not None:
        return content_detected
    return None


def _extract_from_content_type(path: Path) -> Optional[MetadataHint]:
    """Use Magika/python-magic mismatch detection to route extensionless files."""
    try:
        from fileorganizer import magika_router
    except Exception:
        return None

    detected_ext = magika_router.extractor_extension_for_path(path)
    if detected_ext:
        mod = _EXT_DISPATCH.get(detected_ext)
        if mod is not None:
            try:
                hint = mod.extract(path, detected_ext=detected_ext)
            except TypeError:
                hint = mod.extract(path)
            except Exception:
                hint = None
            if hint is not None:
                return _attach_content_mismatch(path, hint)

    routed = magika_router.route_by_mime_type(path)
    mismatch = magika_router.detect_extension_mismatch(path)
    if routed is None or mismatch is None:
        return None
    category, confidence = routed
    raw = dict(mismatch)
    return MetadataHint(
        category=category,
        confidence=confidence,
        extractor="content_type",
        reason=(
            f"{raw.get('detected_mime') or raw.get('detected_label')} bytes do not match "
            f"{raw.get('original_ext') or 'no extension'}"
        ),
        raw=raw,
    )


def _attach_content_mismatch(path: Path, hint: MetadataHint) -> MetadataHint:
    """Add mismatch metadata to a successful extractor hint when applicable."""
    try:
        from fileorganizer import magika_router
        mismatch = magika_router.detect_extension_mismatch(path)
    except Exception:
        mismatch = None
    if not mismatch:
        return hint
    raw = dict(hint.raw)
    raw.update(mismatch)
    reason = hint.reason
    detected = mismatch.get("detected_mime") or mismatch.get("detected_label")
    if detected:
        reason = f"{reason}; content-type {detected} differs from suffix"
    return MetadataHint(
        category=hint.category,
        confidence=hint.confidence,
        extractor=hint.extractor,
        reason=reason,
        raw=raw,
    )


def _select_content_detected_file(files: list[Path]) -> Optional[Path]:
    """Find a top-level file whose bytes expose a supported extractor type."""
    try:
        from fileorganizer import magika_router
    except Exception:
        return None

    candidates: list[tuple[int, int, Path]] = []
    for path in files[:80]:
        try:
            detected_ext = magika_router.extractor_extension_for_path(path)
            if not detected_ext:
                routed = magika_router.route_by_mime_type(path)
                if routed is None or not magika_router.detect_extension_mismatch(path):
                    continue
                priority = 99
            else:
                priority = _content_ext_priority(detected_ext)
            size = path.stat().st_size
        except OSError:
            continue
        except Exception:
            continue
        candidates.append((priority, -size, path))
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (row[0], row[1], row[2].name.lower()))[0][2]


def _content_ext_priority(ext: str) -> int:
    if ext == ".aep":
        return 0
    if ext in {".ttf", ".otf", ".ttc", ".woff", ".woff2"}:
        return 1
    if ext in {".psd", ".psb"}:
        return 2
    if ext in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf"}:
        return 3
    if ext in {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".aiff"}:
        return 4
    return 50


def _best_aep_file(folder: Path, files: list[Path], ext_hint: list[str]) -> Optional[Path]:
    aep_exts = {".aep"}
    candidates = [p for p in files if p.suffix.lower() in aep_exts]
    hint_exts = {str(ext).lower() for ext in ext_hint}
    if not candidates and hint_exts.intersection(aep_exts):
        try:
            for path in folder.rglob("*"):
                if path.is_file() and path.suffix.lower() in aep_exts:
                    candidates.append(path)
                    if len(candidates) >= 500:
                        break
        except OSError:
            return None
    if not candidates:
        return None
    try:
        from fileorganizer.categories import _score_aep
        return max(candidates, key=lambda p: _score_aep(p, folder, folder.name)[0])
    except Exception:
        try:
            return max(candidates, key=lambda p: p.stat().st_size)
        except OSError:
            return candidates[0]
