"""
Video metadata extractor — ffprobe (subprocess; no ffmpeg-python dep).

NEXT-11 deep routing rules:
  - 9:16 vertical → "Social Media - Templates" (Stories / Reels / Shorts) [confidence 85]
  - 1:1 square    → "Social Media - Templates" (Instagram square) [confidence 78]
  - ≤ 15s duration → "After Effects - Motion Graphics" (looping clips) [confidence 80]
  - ProRes/DNxHD/XDCAM → "Broadcast / Cinema Stock" [confidence 90]
  - > 5 min duration → "Tutorial Video" [confidence 75]
  - other 16:9 landscape (≥1080p) → "Stock Footage - General" [confidence 70]

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
_CAT_SOCIAL_TEMPLATES = "Social Media - Templates"
_CAT_MOTION_GRAPHICS = "After Effects - Motion Graphics"
_CAT_BROADCAST = "Broadcast / Cinema Stock"
_CAT_TUTORIAL = "Tutorial Video"
_CAT_VIDEO_OTHER = "Video Editing - General"

# Broadcast/cinema codecs (NEXT-11)
_PRO_CODECS = {"prores", "prores_ks", "dnxhd", "dnxhr", "xdcam", "cineform"}


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
    fps = float(video_stream.get("r_frame_rate", "0").split("/")[0] if "/" in str(video_stream.get("r_frame_rate", "0")) else video_stream.get("avg_frame_rate", 0) or 0.0)

    raw = {
        "width": width,
        "height": height,
        "codec": codec,
        "duration_s": duration,
        "fps": fps,
        "ext": path.suffix.lower(),
    }

    if width <= 0 or height <= 0:
        return None

    ratio = width / height

    # NEXT-11: Broadcast/cinema codecs → high confidence (90)
    if codec in _PRO_CODECS:
        return MetadataHint(
            category=_CAT_BROADCAST,
            confidence=90,
            extractor="video",
            reason=f"broadcast codec {codec} ({width}x{height}, {duration:.0f}s)",
            raw=raw,
        )

    # NEXT-11: Very short clips (≤15s) → motion graphics (looping content)
    if 0 < duration <= 15:
        return MetadataHint(
            category=_CAT_MOTION_GRAPHICS,
            confidence=80,
            extractor="video",
            reason=f"short clip ({duration:.1f}s) — likely looping AE motion graphic",
            raw=raw,
        )

    # NEXT-11: Long duration (>5 min) → tutorial video
    if duration > 300:  # 5 min = 300s
        return MetadataHint(
            category=_CAT_TUTORIAL,
            confidence=75,
            extractor="video",
            reason=f"long duration ({duration/60:.1f} min) — likely tutorial/course content",
            raw=raw,
        )

    # Aspect-ratio signals — informational only (below 90, won't skip downstream
    # stages but feeds metadata to embeddings + LLM).
    if 0.55 <= ratio <= 0.58:
        return MetadataHint(
            category=_CAT_SOCIAL_TEMPLATES,
            confidence=85,
            extractor="video",
            reason=f"9:16 vertical ({width}x{height}, {codec}) — likely Reels/Stories/Shorts",
            raw=raw,
        )
    if 0.95 <= ratio <= 1.05:
        return MetadataHint(
            category=_CAT_SOCIAL_TEMPLATES,
            confidence=78,
            extractor="video",
            reason=f"square ({width}x{height}) — likely Instagram/TikTok template",
            raw=raw,
        )
    if 1.7 <= ratio <= 1.8 and width >= 1920:
        return MetadataHint(
            category=_CAT_STOCK,
            confidence=70,
            extractor="video",
            reason=f"16:9 HD ({width}x{height}, {duration:.0f}s)",
            raw=raw,
        )

    return MetadataHint(
        category=_CAT_VIDEO_OTHER,
        confidence=50,
        extractor="video",
        reason=f"{width}x{height} {codec} {duration:.0f}s",
        raw=raw,
    )
