"""Tests for fileorganizer.metadata_extractors package.

These tests cover:
  - Package imports cleanly even with no optional deps installed.
  - Each extractor returns None on missing-file / wrong-extension input.
  - PSD aspect-ratio routing emits canonical category names with confidence
    matching the documented threshold.
  - extract_hint(item, source_dir) handles file_mode + folder_mode items and
    refuses to operate when source_dir is empty.
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

# Ensure repo root is importable in case pytest is launched from elsewhere.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

import pytest  # noqa: E402

from fileorganizer.metadata_extractors import (  # noqa: E402
    MetadataHint,
    extract_for_path,
    extract_hint,
    audio_extractor,
    font_extractor,
    psd_extractor,
    video_extractor,
)


# ── Package-level smoke ────────────────────────────────────────────────────


def test_package_imports_cleanly():
    """Importing the package must not raise even when optional deps are missing."""
    import fileorganizer.metadata_extractors as pkg
    assert pkg.MetadataHint is MetadataHint
    assert callable(pkg.extract_hint)
    assert callable(pkg.extract_for_path)


def test_metadata_hint_to_result_shape():
    hint = MetadataHint(
        category="Fonts & Typography",
        confidence=95,
        extractor="font",
        reason="Inter Regular",
    )
    out = hint.to_result("Inter-Regular.ttf")
    assert out["name"] == "Inter-Regular.ttf"
    assert out["category"] == "Fonts & Typography"
    assert out["confidence"] == 95
    assert out["_classifier"] == "metadata_font"
    assert out["clean_name"] == "Inter-Regular.ttf"
    assert "metadata_extractor:font" in out["notes"]
    assert "Inter Regular" in out["notes"]


# ── extract_for_path / extract_hint ────────────────────────────────────────


def test_extract_for_path_rejects_missing_file(tmp_path):
    assert extract_for_path(tmp_path / "nope.psd") is None


def test_extract_for_path_rejects_unknown_extension(tmp_path):
    f = tmp_path / "data.xyz"
    f.write_bytes(b"\x00")
    assert extract_for_path(f) is None


def test_extract_hint_requires_source_dir(tmp_path):
    item = {"name": "anything.psd"}
    assert extract_hint(item, source_dir=None) is None
    assert extract_hint(item, source_dir="") is None


def test_extract_hint_returns_none_on_empty_item():
    assert extract_hint({}, source_dir="C:/anywhere") is None
    assert extract_hint(None, source_dir="C:/anywhere") is None


def test_extract_hint_handles_missing_target(tmp_path):
    item = {"name": "ghost.psd"}
    assert extract_hint(item, source_dir=str(tmp_path)) is None


# ── PSD extractor (no psd-tools required for these aspect tests) ───────────


def test_psd_extractor_returns_none_for_non_psd(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("not a psd")
    assert psd_extractor.extract(f) is None


def test_psd_aspect_helpers():
    """The aspect-classification helpers are pure and worth testing directly."""
    assert psd_extractor._is_vertical_9x16(1080, 1920)
    assert psd_extractor._is_vertical_9x16(720, 1280)
    assert not psd_extractor._is_vertical_9x16(1920, 1080)
    assert not psd_extractor._is_vertical_9x16(0, 100)

    assert psd_extractor._is_square_post(1080, 1080)
    assert psd_extractor._is_square_post(1200, 1200)
    assert not psd_extractor._is_square_post(1080, 1920)

    assert psd_extractor._is_business_card(1050, 600)   # 3.5"x2" @300DPI
    assert not psd_extractor._is_business_card(1080, 1080)

    assert psd_extractor._is_flyer_a4_or_letter(2480, 3508)  # A4 @300DPI
    assert psd_extractor._is_flyer_a4_or_letter(2550, 3300)  # US Letter @300DPI
    assert not psd_extractor._is_flyer_a4_or_letter(3508, 2480)  # landscape


def test_psd_extractor_no_psdtools_returns_none(tmp_path, monkeypatch):
    """When psd-tools isn't installed, extractor must degrade silently."""
    monkeypatch.setattr(psd_extractor, "_HAS_PSD_TOOLS", False)
    f = tmp_path / "fake.psd"
    f.write_bytes(b"8BPS\x00\x01")  # PSD signature, but truncated
    assert psd_extractor.extract(f) is None


def test_psd_extractor_with_mock_psdimage(tmp_path, monkeypatch):
    """Routing through extract() with a fake PSDImage object."""
    monkeypatch.setattr(psd_extractor, "_HAS_PSD_TOOLS", True)

    class FakePSD:
        def __init__(self, w, h):
            self.width = w
            self.height = h

    fake_module = mock.MagicMock()
    fake_module.PSDImage.open.return_value = FakePSD(1080, 1920)
    monkeypatch.setitem(sys.modules, "psd_tools", fake_module)

    f = tmp_path / "story.psd"
    f.write_bytes(b"placeholder")
    hint = psd_extractor.extract(f)
    assert hint is not None
    assert hint.category == "Print - Social Media Graphics"
    assert hint.confidence >= 90
    assert hint.extractor == "psd"


def test_psd_extractor_business_card_routing(tmp_path, monkeypatch):
    monkeypatch.setattr(psd_extractor, "_HAS_PSD_TOOLS", True)

    class FakePSD:
        def __init__(self, w, h):
            self.width = w
            self.height = h

    fake_module = mock.MagicMock()
    fake_module.PSDImage.open.return_value = FakePSD(1050, 600)
    monkeypatch.setitem(sys.modules, "psd_tools", fake_module)

    f = tmp_path / "card.psd"
    f.write_bytes(b"placeholder")
    hint = psd_extractor.extract(f)
    assert hint is not None
    assert hint.category == "Print - Business Cards & Stationery"
    assert hint.confidence >= 90


# ── Font extractor ─────────────────────────────────────────────────────────


def test_font_extractor_returns_none_for_non_font(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("not a font")
    assert font_extractor.extract(f) is None


def test_font_extractor_no_fonttools_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(font_extractor, "_HAS_FONTTOOLS", False)
    f = tmp_path / "fake.ttf"
    f.write_bytes(b"\x00\x01\x00\x00")
    assert font_extractor.extract(f) is None


# ── Audio extractor ────────────────────────────────────────────────────────


def test_audio_extractor_returns_none_for_non_audio(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("not audio")
    assert audio_extractor.extract(f) is None


def test_audio_extractor_no_mutagen_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_extractor, "_HAS_MUTAGEN", False)
    f = tmp_path / "fake.mp3"
    f.write_bytes(b"\x00")
    assert audio_extractor.extract(f) is None


def test_audio_extractor_short_clip_categorizes_as_sfx_below_threshold(tmp_path, monkeypatch):
    """Audio MVP per N-9 rubric: NEVER hardroutes (confidence < 90).

    Duration alone can't distinguish a 4s music intro stab from a 4s SFX
    one-shot — defer to downstream stages.
    """
    monkeypatch.setattr(audio_extractor, "_HAS_MUTAGEN", True)

    fake_info = mock.MagicMock()
    fake_info.length = 4.5
    fake_info.bitrate = 320000
    fake_audio = mock.MagicMock()
    fake_audio.info = fake_info
    fake_audio.tags = {}
    fake_audio.get = lambda key: None  # type: ignore[attr-defined]

    fake_module = mock.MagicMock()
    fake_module.File.return_value = fake_audio
    monkeypatch.setitem(sys.modules, "mutagen", fake_module)

    f = tmp_path / "boom.wav"
    f.write_bytes(b"placeholder")
    hint = audio_extractor.extract(f)
    assert hint is not None
    assert hint.category == "Sound Effects & SFX"
    assert hint.confidence < 90  # informational only


def test_audio_extractor_long_track_categorizes_as_music_below_threshold(tmp_path, monkeypatch):
    monkeypatch.setattr(audio_extractor, "_HAS_MUTAGEN", True)

    fake_info = mock.MagicMock()
    fake_info.length = 215.0  # 3:35
    fake_info.bitrate = 256000
    fake_audio = mock.MagicMock()
    fake_audio.info = fake_info
    fake_audio.tags = {}
    fake_audio.get = lambda key: None  # type: ignore[attr-defined]

    fake_module = mock.MagicMock()
    fake_module.File.return_value = fake_audio
    monkeypatch.setitem(sys.modules, "mutagen", fake_module)

    f = tmp_path / "track.mp3"
    f.write_bytes(b"placeholder")
    hint = audio_extractor.extract(f)
    assert hint is not None
    assert hint.category == "Stock Music & Audio"
    assert hint.confidence < 90  # informational only — downstream still runs


def test_select_primary_file_picks_webfont(tmp_path):
    """Folder-mode dispatch must pick .woff/.woff2 (audit fix)."""
    from fileorganizer.metadata_extractors import _select_primary_file
    folder = tmp_path / "webfont_pack"
    folder.mkdir()
    (folder / "Inter-Regular.woff2").write_bytes(b"woff2 placeholder")
    (folder / "preview.png").write_bytes(b"preview")
    primary = _select_primary_file(folder, [])
    assert primary is not None
    assert primary.suffix == ".woff2"


def test_select_primary_file_picks_woff(tmp_path):
    from fileorganizer.metadata_extractors import _select_primary_file
    folder = tmp_path / "webfont_pack"
    folder.mkdir()
    (folder / "Inter-Regular.woff").write_bytes(b"woff placeholder")
    primary = _select_primary_file(folder, [])
    assert primary is not None
    assert primary.suffix == ".woff"


# ── Video extractor ────────────────────────────────────────────────────────


def test_video_extractor_returns_none_for_non_video(tmp_path):
    f = tmp_path / "a.txt"
    f.write_text("not a video")
    assert video_extractor.extract(f) is None


def test_video_extractor_no_ffprobe_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(video_extractor, "_FFPROBE", None)
    f = tmp_path / "fake.mp4"
    f.write_bytes(b"\x00")
    assert video_extractor.extract(f) is None


def test_video_extractor_pro_codec_routes_to_stock(tmp_path, monkeypatch):
    monkeypatch.setattr(video_extractor, "_FFPROBE", "ffprobe")

    completed = mock.MagicMock()
    completed.returncode = 0
    completed.stdout = (
        '{"streams":[{"codec_type":"video","codec_name":"prores",'
        '"width":1920,"height":1080}],"format":{"duration":"5.0"}}'
    )

    monkeypatch.setattr(
        video_extractor.subprocess, "run", lambda *a, **k: completed
    )

    f = tmp_path / "broadcast.mov"
    f.write_bytes(b"placeholder")
    hint = video_extractor.extract(f)
    assert hint is not None
    assert hint.category == "Stock Footage - General"
    assert hint.confidence >= 90


def test_video_extractor_vertical_routes_below_threshold(tmp_path, monkeypatch):
    """9:16 vertical .mp4 should produce a hint but stay below the hardroute threshold."""
    monkeypatch.setattr(video_extractor, "_FFPROBE", "ffprobe")

    completed = mock.MagicMock()
    completed.returncode = 0
    completed.stdout = (
        '{"streams":[{"codec_type":"video","codec_name":"h264",'
        '"width":1080,"height":1920}],"format":{"duration":"15.0"}}'
    )

    monkeypatch.setattr(
        video_extractor.subprocess, "run", lambda *a, **k: completed
    )

    f = tmp_path / "reel.mp4"
    f.write_bytes(b"placeholder")
    hint = video_extractor.extract(f)
    assert hint is not None
    assert hint.confidence < 90  # informational only — downstream stages run
