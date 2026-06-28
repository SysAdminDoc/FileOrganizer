import sys
import types
from datetime import datetime, timedelta

from fileorganizer import winrt_metadata as wm


class _FakeProperties:
    async def get_image_properties_async(self):
        return types.SimpleNamespace(
            width=4032,
            height=3024,
            camera_model="EOS R5",
            date_taken=datetime(2026, 6, 27, 12, 30),
            latitude=45.5,
            longitude=-122.6,
            keywords=["event", "portrait"],
        )

    async def get_music_properties_async(self):
        return types.SimpleNamespace(
            title="Impact Hit",
            artist="Library Artist",
            album="SFX Pack",
            genre=["SFX", "Impact"],
            duration=timedelta(seconds=4.5),
            bitrate=320000,
            track_number=3,
            year=2026,
        )

    async def get_video_properties_async(self):
        return types.SimpleNamespace(
            title="Loop",
            duration=timedelta(seconds=12),
            width=1080,
            height=1920,
            bitrate=8000000,
            year=2026,
        )


class _FakeStorageFile:
    @staticmethod
    async def get_file_from_path_async(_path):
        return types.SimpleNamespace(properties=_FakeProperties())


def _install_fake_winrt(monkeypatch):
    winrt_mod = types.ModuleType("winrt")
    windows_mod = types.ModuleType("winrt.windows")
    storage_mod = types.ModuleType("winrt.windows.storage")
    storage_mod.StorageFile = _FakeStorageFile
    monkeypatch.setitem(sys.modules, "winrt", winrt_mod)
    monkeypatch.setitem(sys.modules, "winrt.windows", windows_mod)
    monkeypatch.setitem(sys.modules, "winrt.windows.storage", storage_mod)
    monkeypatch.setattr(wm.sys, "platform", "win32")


def test_non_windows_degrades_to_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(wm.sys, "platform", "linux")
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")
    assert wm.extract(f) == {}


def test_extract_image_properties_from_winrt(tmp_path, monkeypatch):
    _install_fake_winrt(monkeypatch)
    f = tmp_path / "photo.jpg"
    f.write_bytes(b"x")

    meta = wm.extract(f)

    assert meta["kind"] == "image"
    assert meta["width"] == 4032
    assert meta["height"] == 3024
    assert meta["camera_model"] == "EOS R5"
    assert meta["date_taken"].startswith("2026-06-27T12:30:00")
    assert meta["gps_lat"] == 45.5
    assert meta["gps_lon"] == -122.6
    assert meta["keywords"] == "event, portrait"


def test_extract_audio_properties_from_winrt(tmp_path, monkeypatch):
    _install_fake_winrt(monkeypatch)
    f = tmp_path / "hit.mp3"
    f.write_bytes(b"x")

    meta = wm.extract(f)

    assert meta["kind"] == "audio"
    assert meta["title"] == "Impact Hit"
    assert meta["artist"] == "Library Artist"
    assert meta["duration"] == 4.5
    assert meta["bitrate"] == 320
    assert meta["genre"] == "SFX, Impact"


def test_extract_video_properties_from_winrt(tmp_path, monkeypatch):
    _install_fake_winrt(monkeypatch)
    f = tmp_path / "loop.mp4"
    f.write_bytes(b"x")

    meta = wm.extract(f)

    assert meta["kind"] == "video"
    assert meta["width"] == 1080
    assert meta["height"] == 1920
    assert meta["duration"] == 12.0
    assert meta["video_bitrate"] == 8000
