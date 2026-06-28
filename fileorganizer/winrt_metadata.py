"""Windows Runtime FileProperties metadata bridge.

The module is optional and Windows-only. It returns an empty dict when PyWinRT
is unavailable so callers can keep using Pillow, mutagen, or ffprobe fallbacks.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any


IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp", ".heic", ".heif"}
AUDIO_EXTS = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".aac", ".aiff", ".wma"}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf", ".wmv"}


def _kind_for_ext(ext: str) -> str:
    ext = ext.lower()
    if ext in IMAGE_EXTS:
        return "image"
    if ext in AUDIO_EXTS:
        return "audio"
    if ext in VIDEO_EXTS:
        return "video"
    return ""


def available() -> tuple[bool, str]:
    if sys.platform != "win32":
        return False, "WinRT metadata is Windows-only."
    try:
        _storage_file_class()
        return True, ""
    except Exception as exc:
        return False, str(exc)


def extract(path: str | os.PathLike[str], detected_ext: str | None = None) -> dict[str, Any]:
    """Extract FileProperties metadata for image/audio/video files."""
    file_path = Path(path)
    if not file_path.exists() or not file_path.is_file():
        return {}
    kind = _kind_for_ext(detected_ext or file_path.suffix)
    if not kind:
        return {}
    ok, _reason = available()
    if not ok:
        return {}
    try:
        return _run_async(_extract_async(file_path, kind))
    except Exception:
        return {}


async def _extract_async(path: Path, kind: str) -> dict[str, Any]:
    StorageFile = _storage_file_class()
    storage_file = await _maybe_await(StorageFile.get_file_from_path_async(str(path.resolve())))
    properties = getattr(storage_file, "properties", None)
    if properties is None:
        return {}
    if kind == "image":
        image = await _maybe_await(properties.get_image_properties_async())
        return _image_props(image)
    if kind == "audio":
        music = await _maybe_await(properties.get_music_properties_async())
        return _audio_props(music)
    if kind == "video":
        video = await _maybe_await(properties.get_video_properties_async())
        return _video_props(video)
    return {}


def _storage_file_class():
    from winrt.windows.storage import StorageFile  # type: ignore
    return StorageFile


async def _maybe_await(value):
    if inspect.isawaitable(value):
        return await value
    return value


def _run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    result: dict[str, Any] = {}
    error: list[BaseException] = []

    def runner():
        try:
            result["value"] = asyncio.run(coro)
        except BaseException as exc:
            error.append(exc)

    thread = threading.Thread(target=runner, name="FileOrganizerWinRTMetadata", daemon=True)
    thread.start()
    thread.join()
    if error:
        raise error[0]
    return result.get("value", {})


def _get(obj: Any, *names: str) -> Any:
    for name in names:
        try:
            value = getattr(obj, name)
        except Exception:
            continue
        if value is not None:
            return value
    return None


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        parts = [str(v).strip() for v in value if str(v).strip()]
        return ", ".join(parts)
    return str(value).strip()


def _int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _duration_seconds(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, timedelta):
        return round(value.total_seconds(), 1)
    if hasattr(value, "total_seconds"):
        try:
            return round(float(value.total_seconds()), 1)
        except Exception:
            return None
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    # Windows TimeSpan is 100 ns ticks. Avoid treating normal second values as ticks.
    if numeric > 10_000_000:
        numeric = numeric / 10_000_000.0
    return round(numeric, 1)


def _date_iso(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        if value.year <= 1601:
            return ""
        return value.isoformat()
    text = str(value).strip()
    if text.startswith("1601-01-01"):
        return ""
    return text


def _put(out: dict[str, Any], key: str, value: Any) -> None:
    if value is None or value == "" or value == []:
        return
    out[key] = value


def _image_props(props: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "image", "source": "winrt"}
    _put(out, "width", _int(_get(props, "width")))
    _put(out, "height", _int(_get(props, "height")))
    _put(out, "date_taken", _date_iso(_get(props, "date_taken")))
    _put(out, "camera_model", _text(_get(props, "camera_model")))
    _put(out, "title", _text(_get(props, "title")))
    _put(out, "orientation", _text(_get(props, "orientation")))
    _put(out, "gps_lat", _float(_get(props, "latitude")))
    _put(out, "gps_lon", _float(_get(props, "longitude")))
    _put(out, "keywords", _text(_get(props, "keywords")))
    _put(out, "people_names", _text(_get(props, "people_names")))
    return out


def _audio_props(props: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "audio", "source": "winrt"}
    _put(out, "title", _text(_get(props, "title")))
    _put(out, "artist", _text(_get(props, "artist")))
    _put(out, "album", _text(_get(props, "album")))
    _put(out, "genre", _text(_get(props, "genre")))
    _put(out, "track", _int(_get(props, "track_number", "track")))
    _put(out, "year", _int(_get(props, "year")))
    _put(out, "duration", _duration_seconds(_get(props, "duration")))
    bitrate = _int(_get(props, "bitrate"))
    if bitrate is not None:
        _put(out, "bitrate", int(bitrate / 1000) if bitrate > 10000 else bitrate)
    return out


def _video_props(props: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"kind": "video", "source": "winrt"}
    _put(out, "title", _text(_get(props, "title")))
    _put(out, "duration", _duration_seconds(_get(props, "duration")))
    _put(out, "width", _int(_get(props, "width", "frame_width")))
    _put(out, "height", _int(_get(props, "height", "frame_height")))
    bitrate = _int(_get(props, "bitrate"))
    if bitrate is not None:
        _put(out, "video_bitrate", int(bitrate / 1000) if bitrate > 10000 else bitrate)
    _put(out, "year", _int(_get(props, "year")))
    _put(out, "orientation", _text(_get(props, "orientation")))
    _put(out, "keywords", _text(_get(props, "keywords")))
    return out
