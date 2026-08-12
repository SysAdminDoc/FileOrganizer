"""Bounded audio waveform extraction and PNG caching for Browse previews."""

from __future__ import annotations

import hashlib
import os
import shutil
import struct
import subprocess
import wave
import warnings
from dataclasses import dataclass
from pathlib import Path

from fileorganizer.config import _APP_DATA_DIR


with warnings.catch_warnings():
    warnings.simplefilter("ignore", DeprecationWarning)
    import aifc


AUDIO_EXTENSIONS = frozenset({
    ".mp3", ".wav", ".aiff", ".aif", ".flac", ".ogg", ".oga", ".m4a", ".aac",
    ".opus", ".wma",
})
DEFAULT_WAVEFORM_CACHE = os.path.join(_APP_DATA_DIR, "waveforms")
MAX_RENDER_SECONDS = 10 * 60
MAX_PIXELS = 1600
_FFMPEG_MAX_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class AudioInfo:
    frames: int
    sample_rate: int
    channels: int
    duration: float


def _audio_info_from_reader(reader) -> AudioInfo:
    frames = max(0, int(reader.getnframes()))
    sample_rate = max(1, int(reader.getframerate()))
    return AudioInfo(
        frames=frames,
        sample_rate=sample_rate,
        channels=max(1, int(reader.getnchannels())),
        duration=frames / sample_rate,
    )


def audio_info(path: str | os.PathLike[str]) -> AudioInfo | None:
    """Read lightweight stream metadata without decoding the entire asset."""
    path_text = os.fspath(path)
    extension = Path(path_text).suffix.casefold()
    reader_factory = wave.open if extension == ".wav" else aifc.open if extension in {".aif", ".aiff"} else None
    if reader_factory:
        try:
            with reader_factory(path_text, "rb") as reader:
                return _audio_info_from_reader(reader)
        except (OSError, EOFError, wave.Error, aifc.Error):
            return None
    try:
        import soundfile as sf

        with sf.SoundFile(path_text) as reader:
            frames = max(0, int(len(reader)))
            sample_rate = max(1, int(reader.samplerate))
            return AudioInfo(
                frames=frames,
                sample_rate=sample_rate,
                channels=max(1, int(reader.channels)),
                duration=frames / sample_rate,
            )
    except (ImportError, OSError, RuntimeError, ValueError):
        return None


def _sample_value(raw: bytes, offset: int, sample_width: int) -> float:
    chunk = raw[offset:offset + sample_width]
    if len(chunk) != sample_width:
        return 0.0
    if sample_width == 1:
        return (chunk[0] - 128) / 128.0
    value = int.from_bytes(chunk, "little", signed=True)
    return value / float(1 << (sample_width * 8 - 1))


def _peaks_from_pcm(reader, info: AudioInfo, sample_width: int, buckets: int) -> list[float]:
    bucket_count = max(1, min(MAX_PIXELS, int(buckets)))
    frames_per_bucket = max(1, (info.frames + bucket_count - 1) // bucket_count)
    peaks = []
    frame_size = sample_width * info.channels
    for _bucket_index in range(bucket_count):
        remaining = frames_per_bucket
        peak = 0.0
        while remaining > 0:
            raw = reader.readframes(min(remaining, 8192))
            if not raw:
                break
            frame_count = len(raw) // frame_size
            for frame_index in range(frame_count):
                peak = max(peak, abs(_sample_value(raw, frame_index * frame_size, sample_width)))
            remaining -= frame_count
            if frame_count == 0:
                break
        if remaining == frames_per_bucket and not peak:
            break
        peaks.append(min(1.0, peak))
    return peaks


def _peaks_from_stdlib(path: str, buckets: int) -> tuple[AudioInfo, list[float]] | None:
    extension = Path(path).suffix.casefold()
    reader_factory = wave.open if extension == ".wav" else aifc.open if extension in {".aif", ".aiff"} else None
    if not reader_factory:
        return None
    try:
        with reader_factory(path, "rb") as reader:
            info = _audio_info_from_reader(reader)
            if info.duration > MAX_RENDER_SECONDS:
                info = AudioInfo(
                    frames=int(MAX_RENDER_SECONDS * info.sample_rate),
                    sample_rate=info.sample_rate,
                    channels=info.channels,
                    duration=MAX_RENDER_SECONDS,
                )
            return info, _peaks_from_pcm(reader, info, int(reader.getsampwidth()), buckets)
    except (OSError, EOFError, wave.Error, aifc.Error, ValueError):
        return None


def _peaks_from_soundfile(path: str, buckets: int) -> tuple[AudioInfo, list[float]] | None:
    try:
        import numpy as np
        import soundfile as sf

        with sf.SoundFile(path) as reader:
            info = AudioInfo(
                frames=max(0, int(len(reader))),
                sample_rate=max(1, int(reader.samplerate)),
                channels=max(1, int(reader.channels)),
                duration=max(0, int(len(reader))) / max(1, int(reader.samplerate)),
            )
            frames = min(info.frames, int(MAX_RENDER_SECONDS * info.sample_rate))
            bucket_count = max(1, min(MAX_PIXELS, int(buckets)))
            frames_per_bucket = max(1, (frames + bucket_count - 1) // bucket_count)
            peaks = []
            remaining = frames
            while remaining > 0 and len(peaks) < bucket_count:
                block = reader.read(
                    min(frames_per_bucket, remaining), dtype="float32", always_2d=True
                )
                if len(block) == 0:
                    break
                peaks.append(float(np.max(np.abs(block))))
                remaining -= len(block)
            return info, [min(1.0, max(0.0, peak)) for peak in peaks]
    except (ImportError, OSError, RuntimeError, ValueError):
        return None


def _peaks_from_ffmpeg(path: str, buckets: int) -> tuple[AudioInfo, list[float]] | None:
    ffmpeg = os.environ.get("FILEORGANIZER_FFMPEG") or shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    try:
        result = subprocess.run(
            [
                ffmpeg, "-v", "error", "-i", path,
                "-t", str(MAX_RENDER_SECONDS), "-ac", "1", "-ar", "4000",
                "-f", "f32le", "-",
            ],
            capture_output=True,
            timeout=20,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0 or not result.stdout or len(result.stdout) > _FFMPEG_MAX_BYTES:
        return None
    usable_bytes = len(result.stdout) - (len(result.stdout) % 4)
    values = struct.iter_unpack("<f", result.stdout[:usable_bytes])
    samples = [min(1.0, abs(float(value[0]))) for value in values]
    if not samples:
        return None
    bucket_count = max(1, min(MAX_PIXELS, int(buckets)))
    step = max(1, (len(samples) + bucket_count - 1) // bucket_count)
    peaks = [max(samples[index:index + step]) for index in range(0, len(samples), step)]
    return AudioInfo(
        frames=len(samples), sample_rate=4000, channels=1,
        duration=len(samples) / 4000,
    ), peaks[:bucket_count]


def _cache_path(path: str, width: int, height: int, cache_dir: str) -> str:
    stat_result = os.stat(path)
    identity = f"{os.path.abspath(path)}|{stat_result.st_size}|{stat_result.st_mtime_ns}|{width}|{height}"
    key = hashlib.sha256(identity.encode("utf-8", "surrogatepass")).hexdigest()
    return os.path.join(cache_dir, f"{key}.png")


def render_waveform(
    path: str | os.PathLike[str],
    *,
    width: int = 720,
    height: int = 170,
    cache_dir: str = DEFAULT_WAVEFORM_CACHE,
) -> str | None:
    """Render/cache a bounded waveform PNG and return its path."""
    path_text = os.path.abspath(os.fspath(path))
    if Path(path_text).suffix.casefold() not in AUDIO_EXTENSIONS or not os.path.isfile(path_text):
        return None
    width = max(120, min(MAX_PIXELS, int(width)))
    height = max(60, min(600, int(height)))
    try:
        output = _cache_path(path_text, width, height, cache_dir)
    except OSError:
        return None
    if os.path.isfile(output):
        return output
    try:
        os.makedirs(cache_dir, exist_ok=True)
        decoded = _peaks_from_stdlib(path_text, width - 20)
        if decoded is None:
            decoded = _peaks_from_soundfile(path_text, width - 20)
        if decoded is None:
            decoded = _peaks_from_ffmpeg(path_text, width - 20)
        if decoded is None:
            return None
        info, peaks = decoded
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (width, height), "#0b1220")
        draw = ImageDraw.Draw(image)
        center = height // 2
        draw.line((10, center, width - 10, center), fill="#334155", width=1)
        if peaks:
            x_step = (width - 20) / max(1, len(peaks))
            for index, peak in enumerate(peaks):
                x = int(10 + index * x_step)
                amplitude = max(1, int(peak * (height - 24) / 2))
                draw.line((x, center - amplitude, x, center + amplitude), fill="#38bdf8", width=2)
        draw.text((12, 8), f"{info.duration:.1f}s", fill="#cbd5e1")
        temporary = output + ".tmp"
        image.save(temporary, format="PNG", optimize=True)
        os.replace(temporary, output)
        return output
    except (ImportError, OSError, ValueError, struct.error):
        try:
            if os.path.exists(output + ".tmp"):
                os.remove(output + ".tmp")
        except OSError:
            pass
        return None


__all__ = ["AUDIO_EXTENSIONS", "AudioInfo", "audio_info", "render_waveform"]
