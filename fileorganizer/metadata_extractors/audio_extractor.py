"""
Audio metadata extractor — mutagen 1.47+.

Reads tag fields (title, artist, album, duration, bitrate). Audio is rarely a
straight-shot category in the design-asset taxonomy — most marketplace audio
is "Audio - SFX & Loops" or "Audio - Music Tracks", and the routing depends
on duration + tag patterns rather than format alone. Conservative confidences
in this MVP: short loops (< 30s) route at 88, longer tracks at 80.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

from ._types import MetadataHint

_HAS_MUTAGEN = importlib.util.find_spec("mutagen") is not None

_CAT_SFX = "Sound Effects & SFX"
_CAT_MUSIC = "Stock Music & Audio"


def extract(path: Path) -> Optional[MetadataHint]:
    """Read audio tags + duration; emit a hint based on duration heuristics."""
    if not _HAS_MUTAGEN:
        return None
    if not path or not path.exists():
        return None
    if path.suffix.lower() not in {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".aiff"}:
        return None

    try:
        from mutagen import File as MutagenFile  # type: ignore
        audio = MutagenFile(str(path))
    except Exception:
        return None
    if audio is None:
        return None

    duration = 0.0
    bitrate = 0
    try:
        info = getattr(audio, "info", None)
        if info is not None:
            duration = float(getattr(info, "length", 0.0) or 0.0)
            bitrate = int(getattr(info, "bitrate", 0) or 0)
    except Exception:
        duration = 0.0
        bitrate = 0

    title = _first_tag(audio, ("title", "TIT2", "©nam"))
    artist = _first_tag(audio, ("artist", "TPE1", "©ART"))
    album = _first_tag(audio, ("album", "TALB", "©alb"))

    raw = {
        "duration_s": duration,
        "bitrate": bitrate,
        "title": title,
        "artist": artist,
        "album": album,
        "ext": path.suffix.lower(),
    }

    if duration <= 0:
        # Header parsed but no playable info — informational only.
        return MetadataHint(
            category=_CAT_MUSIC,
            confidence=60,
            extractor="audio",
            reason="parsed without duration",
            raw=raw,
        )

    # MVP per N-9 rubric: audio is informational only — duration alone can't
    # distinguish a 4s music intro stab from a 4s SFX one-shot, so we stay
    # below the 90-conf hardroute threshold and let downstream stages decide.
    if duration < 30:
        return MetadataHint(
            category=_CAT_SFX,
            confidence=85,
            extractor="audio",
            reason=f"short clip ({duration:.1f}s)",
            raw=raw,
        )
    if duration < 180:
        return MetadataHint(
            category=_CAT_MUSIC,
            confidence=75,
            extractor="audio",
            reason=f"mid-length ({duration:.1f}s) — ambiguous",
            raw=raw,
        )
    # Longer than 3 minutes: highly likely a full music track, but hold
    # below the hardroute threshold (still ambiguous: tutorial audio,
    # podcast clip, dialogue track all hit this band).
    return MetadataHint(
        category=_CAT_MUSIC,
        confidence=85,
        extractor="audio",
        reason=f"full track ({duration:.1f}s)",
        raw=raw,
    )


def _first_tag(audio, keys: tuple[str, ...]) -> str:
    """Pull the first non-empty tag value from a list of candidate keys."""
    try:
        tags = getattr(audio, "tags", None) or audio
    except Exception:
        return ""
    for key in keys:
        try:
            val = tags.get(key) if hasattr(tags, "get") else None
            if val is None:
                continue
            if isinstance(val, list) and val:
                val = val[0]
            text = str(val).strip()
            if text:
                return text
        except Exception:
            continue
    return ""
