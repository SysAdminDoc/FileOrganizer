from __future__ import annotations

import math
import wave

from PIL import Image

from fileorganizer.waveform import audio_info, render_waveform


def _write_wave(path):
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(8000)
        samples = [
            int(math.sin(index / 8) * 20_000)
            for index in range(8000)
        ]
        writer.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))


def test_audio_info_and_waveform_cache_for_wav(tmp_path):
    audio = tmp_path / "tone.wav"
    cache = tmp_path / "waveforms"
    _write_wave(audio)

    info = audio_info(audio)
    assert info is not None
    assert info.sample_rate == 8000
    assert info.duration == 1.0

    rendered = render_waveform(audio, width=320, height=120, cache_dir=str(cache))
    assert rendered is not None
    assert rendered == render_waveform(audio, width=320, height=120, cache_dir=str(cache))
    assert Image.open(rendered).size == (320, 120)
    assert len(list(cache.glob("*.png"))) == 1


def test_waveform_rejects_non_audio_files(tmp_path):
    not_audio = tmp_path / "notes.txt"
    not_audio.write_text("not audio", encoding="utf-8")

    assert audio_info(not_audio) is None
    assert render_waveform(not_audio, cache_dir=str(tmp_path / "cache")) is None

