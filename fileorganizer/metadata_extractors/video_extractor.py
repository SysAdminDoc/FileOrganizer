"""
Video metadata extractor — ffprobe (subprocess; no ffmpeg-python dep).

NEXT-11 deep routing rules:
  - 9:16 vertical -> "After Effects - Social Media" (Stories / Reels / Shorts) [confidence 85]
  - 1:1 square    -> "After Effects - Social Media" (Instagram square) [confidence 78]
  - <= 15s duration -> "After Effects - Motion Graphics Pack" (looping clips) [confidence 80]
  - ProRes/DNxHD/XDCAM -> "Stock Footage - General" [confidence 90]
  - > 5 min duration -> "Tutorial & Education" [confidence 75]
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

from fileorganizer import winrt_metadata
from fileorganizer.video_routing import (
    VideoRoutingMetadata,
    analyze_video_metadata,
    video_to_routing_hints,
)

from ._types import MetadataHint

_FFPROBE = shutil.which("ffprobe")

# NOTE on routing: the canonical taxonomy splits video by application
# (After Effects / Premiere Pro / Stock Footage) rather than by raw aspect.
# A finished .mp4 cannot be authoritatively traced back to its source app
# from container metadata, so we only fire HIGH confidence (>=90) when the
# codec is unmistakably broadcast/cinema. Aspect-ratio hints stay below 90
# (informational only) so downstream stages keep their say.
_CAT_STOCK = "Stock Footage - General"
_CAT_SOCIAL_TEMPLATES = "After Effects - Social Media"
_CAT_MOTION_GRAPHICS = "After Effects - Motion Graphics Pack"
_CAT_BROADCAST = "Stock Footage - General"
_CAT_TUTORIAL = "Tutorial & Education"
_CAT_VIDEO_OTHER = "Video Editing - General"

# Broadcast/cinema codecs (NEXT-11)
_PRO_CODECS = {"prores", "prores_ks", "dnxhd", "dnxhr", "xdcam", "cineform"}


def extract(path: Path, detected_ext: str | None = None) -> Optional[MetadataHint]:
    """ffprobe a video file and emit an aspect/codec-driven hint."""
    if not path or not path.exists():
        return None
    ext = (detected_ext or path.suffix).lower()
    if ext not in {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf"}:
        return None

    try:
        winrt_raw = winrt_metadata.extract(path, detected_ext=detected_ext)
    except Exception:
        winrt_raw = {}
    if winrt_raw and winrt_raw.get("kind") == "video":
        width = int(winrt_raw.get("width") or 0)
        height = int(winrt_raw.get("height") or 0)
        duration = float(winrt_raw.get("duration") or 0.0)
        routing = _analyze_routing(
            path,
            width=width,
            height=height,
            codec=str(winrt_raw.get("codec") or winrt_raw.get("video_codec") or ""),
            duration=duration,
            fps=float(winrt_raw.get("fps") or winrt_raw.get("frame_rate") or 0.0),
            audio_codec=str(winrt_raw.get("audio_codec") or ""),
            bitrate=winrt_raw.get("video_bitrate") or winrt_raw.get("bitrate"),
        )
        return _hint_from_values(
            width=width,
            height=height,
            codec=str(winrt_raw.get("codec") or winrt_raw.get("video_codec") or ""),
            duration=duration,
            fps=float(winrt_raw.get("fps") or winrt_raw.get("frame_rate") or 0.0),
            ext=ext,
            original_ext=path.suffix.lower(),
            source="winrt",
            extra_raw=winrt_raw,
            routing=routing,
        )

    if _FFPROBE is None:
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
    format_data = data.get("format") or {}
    duration = _to_float(format_data.get("duration"), 0.0)
    fps = _parse_frame_rate(
        video_stream.get("r_frame_rate") or video_stream.get("avg_frame_rate")
    )
    audio_stream = next(
        (stream for stream in streams if stream.get("codec_type") == "audio"),
        None,
    )
    audio_codec = str((audio_stream or {}).get("codec_name") or "")
    bitrate = _to_int(format_data.get("bit_rate"))
    if bitrate is None:
        bitrate = _to_int(video_stream.get("bit_rate"))
    routing = _analyze_routing(
        path,
        width=width,
        height=height,
        codec=codec,
        duration=duration,
        fps=fps,
        audio_codec=audio_codec,
        bitrate=bitrate,
    )

    return _hint_from_values(
        width=width,
        height=height,
        codec=codec,
        duration=duration,
        fps=fps,
        ext=ext,
        original_ext=path.suffix.lower(),
        source="ffprobe",
        routing=routing,
    )


def _hint_from_values(
    *,
    width: int,
    height: int,
    codec: str,
    duration: float,
    fps: float,
    ext: str,
    original_ext: str,
    source: str,
    extra_raw: dict | None = None,
    routing: VideoRoutingMetadata | None = None,
) -> Optional[MetadataHint]:
    codec = (codec or "").lower()

    raw = {
        "width": width,
        "height": height,
        "codec": codec,
        "duration_s": duration,
        "fps": fps,
        "ext": ext,
        "original_ext": original_ext,
        "source": source,
    }
    if extra_raw:
        for key, value in extra_raw.items():
            raw.setdefault(key, value)
    if routing is not None:
        raw["routing"] = _routing_payload(routing)
        raw["routing_hints"] = video_to_routing_hints(routing)

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


def _analyze_routing(
    path: Path,
    *,
    width: int,
    height: int,
    codec: str,
    duration: float,
    fps: float,
    audio_codec: str = "",
    bitrate: int | None = None,
) -> VideoRoutingMetadata | None:
    """Run the richer routing pass using already-parsed probe values."""
    resolution = f"{width}x{height}" if width > 0 and height > 0 else None
    codec_info = {
        "video_codec": codec or None,
        "audio_codec": audio_codec or None,
        "resolution": resolution,
        "frame_rate": fps or None,
        "duration": duration or None,
        "bitrate": bitrate,
    }
    try:
        return analyze_video_metadata(str(path), codec_info)
    except Exception:
        return None


def _routing_payload(metadata: VideoRoutingMetadata) -> dict:
    """Keep technical routing context JSON-safe and bounded for the LLM."""
    return {
        "suggested_category": metadata.suggested_category,
        "confidence": round(float(metadata.confidence), 3),
        "codec_family": metadata.codec_family,
        "is_vertical": bool(metadata.is_vertical),
        "is_looping_clip": bool(metadata.is_looping_clip),
        "is_broadcast_codec": bool(metadata.is_broadcast_codec),
        "is_broadcast_fps": bool(metadata.is_broadcast_fps),
        "is_high_performance": bool(metadata.is_high_performance),
        "has_hdr": bool(metadata.has_hdr),
        "has_audio": bool(metadata.has_audio),
    }


def _parse_frame_rate(value) -> float:
    text = str(value or "").strip()
    if not text or text in {"0", "0/0", "N/A"}:
        return 0.0
    try:
        if "/" in text:
            numerator, denominator = (float(part) for part in text.split("/", 1))
            return numerator / denominator if denominator else 0.0
        return float(text)
    except (TypeError, ValueError, ZeroDivisionError):
        return 0.0


def _to_float(value, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _to_int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
