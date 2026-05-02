"""
Video metadata extractor — ffprobe (subprocess; no ffmpeg-python dep).

Reads container + first video stream attributes and routes by aspect ratio:
  - 9:16 vertical -> "Social Media - Templates" (Stories / Reels / Shorts)
  - 1:1 square    -> "Social Media - Templates" (Instagram square)
  - ProRes / DNxHD codecs -> "Video - Cinema & Broadcast"
  - other landscape -> "Video - Stock Footage" at moderate confidence

ffprobe is the only "external binary" dependency. We probe with a 5s timeout
and degrade gracefully if it isn't on PATH.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ._types import MetadataHint

_FFPROBE = shutil.which("ffprobe")

# NOTE on routing: the canonical taxonomy splits video by application
# (After Effects / Premiere Pro / Stock Footage) rather than by raw aspect.
# A finished .mp4 cannot be authoritatively traced back to its source app
# from container metadata, so we only fire HIGH confidence (>=90) when the
# codec is unmistakably broadcast/cinema. Aspect-ratio hints stay below 90
# (informational only) so downstream stages keep their say.
_CAT_STOCK = "Stock Footage - General"
_CAT_GREEN_SCREEN = "Stock Footage - Green Screen"
_CAT_VIDEO_OTHER = "Video Editing - General"

_PRO_CODECS = {"prores", "prores_ks", "dnxhd", "dnxhr", "cineform"}


def extract(path: Path) -> Optional[MetadataHint]:
    """ffprobe a video file and emit an aspect/codec-driven hint."""
    if _FFPROBE is None:
        return None
    if not path or not path.exists():
        return None
    if path.suffix.lower() not in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf"}:
        return None

    try:
        proc = subprocess.run(
            [
                _FFPROBE, "-v", "error",
                "-print_format", "json",
                "-show_streams", "-show_format",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.TimeoutExpired, OSError):
        return None
    if proc.returncode != 0 or not proc.stdout:
        return None

    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None

    streams = data.get("streams") or []
    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"),
        None,
    )
    if video_stream is None:
        return None

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    codec = str(video_stream.get("codec_name") or "").lower()
    duration = float((data.get("format") or {}).get("duration") or 0.0)

    raw = {
        "width": width,
        "height": height,
        "codec": codec,
        "duration_s": duration,
        "ext": path.suffix.lower(),
    }

    if width <= 0 or height <= 0:
        return None

    ratio = width / height

    # Cinema codecs are the only unambiguous high-confidence signal — ProRes /
    # DNxHD / DNxHR are broadcast/cinema delivery codecs, not consumer-finished
    # output. Route to Stock Footage at confidence 90.
    if codec in _PRO_CODECS:
        return MetadataHint(
            category=_CAT_STOCK,
            confidence=90,
            extractor="video",
            reason=f"pro codec {codec} ({width}x{height})",
            raw=raw,
        )

    # Aspect-ratio signals — informational only (below 90, won't skip downstream
    # stages but feeds metadata to embeddings + LLM).
    if 0.55 <= ratio <= 0.58:
        return MetadataHint(
            category=_CAT_STOCK,
            confidence=72,
            extractor="video",
            reason=f"9:16 vertical ({width}x{height}, {codec}) — likely Reels/Stories",
            raw=raw,
        )
    if 0.95 <= ratio <= 1.05:
        return MetadataHint(
            category=_CAT_STOCK,
            confidence=68,
            extractor="video",
            reason=f"square ({width}x{height})",
            raw=raw,
        )
    if 1.7 <= ratio <= 1.8 and width >= 1920:
        return MetadataHint(
            category=_CAT_STOCK,
            confidence=70,
            extractor="video",
            reason=f"16:9 HD ({width}x{height})",
            raw=raw,
        )

    return MetadataHint(
        category=_CAT_VIDEO_OTHER,
        confidence=50,
        extractor="video",
        reason=f"{width}x{height} {codec}",
        raw=raw,
    )
