"""Tests for fileorganizer.broken_detector — N-14."""
from __future__ import annotations

import io
import sys
import zipfile
from pathlib import Path
from unittest import mock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fileorganizer import broken_detector  # noqa: E402


# ── Dispatcher routing ────────────────────────────────────────────────────


def test_is_broken_unknown_extension_returns_false(tmp_path):
    f = tmp_path / "doc.txt"
    f.write_text("not media")
    broken, reason = broken_detector.is_broken(f)
    assert broken is False
    assert reason == ""


def test_is_broken_dispatches_to_image_check(tmp_path, monkeypatch):
    sentinel = (True, "sentinel image broken")
    monkeypatch.setattr(broken_detector, "check_image", lambda p: sentinel)
    f = tmp_path / "x.jpg"
    f.write_bytes(b"not jpeg")
    assert broken_detector.is_broken(f) == sentinel


def test_is_broken_dispatches_to_video_check(tmp_path, monkeypatch):
    sentinel = (True, "sentinel video broken")
    monkeypatch.setattr(broken_detector, "check_video", lambda p: sentinel)
    f = tmp_path / "x.mp4"
    f.write_bytes(b"not mp4")
    assert broken_detector.is_broken(f) == sentinel


def test_is_broken_dispatches_to_archive_check(tmp_path, monkeypatch):
    sentinel = (True, "sentinel archive broken")
    monkeypatch.setattr(broken_detector, "check_archive", lambda p: sentinel)
    f = tmp_path / "x.zip"
    f.write_bytes(b"PK")
    assert broken_detector.is_broken(f) == sentinel


# ── Image check ──────────────────────────────────────────────────────────


def test_check_image_no_pillow_returns_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_HAS_PILLOW", False)
    f = tmp_path / "img.jpg"
    f.write_bytes(b"\xff\xd8\xff")  # JPEG header — but truncated
    broken, reason = broken_detector.check_image(f)
    assert broken is False
    assert reason == ""


def test_check_image_oversize_skipped(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_HAS_PILLOW", True)
    monkeypatch.setattr(broken_detector, "MAX_IMAGE_VERIFY_BYTES", 10)
    f = tmp_path / "huge.jpg"
    f.write_bytes(b"x" * 1024)
    broken, reason = broken_detector.check_image(f)
    assert broken is False
    assert reason == ""


def test_check_image_missing_file(tmp_path):
    broken, reason = broken_detector.check_image(tmp_path / "nope.png")
    assert broken is True
    assert reason == "missing"


def test_check_image_corrupt_via_mocked_pil(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_HAS_PILLOW", True)

    class FakeImage:
        @staticmethod
        def open(p):
            ctx = mock.MagicMock()
            ctx.__enter__ = lambda self: ctx
            ctx.__exit__ = lambda self, *a: False
            ctx.verify = mock.MagicMock(side_effect=OSError("truncated file"))
            return ctx

    fake_pil = mock.MagicMock()
    fake_pil.Image = FakeImage
    fake_pil.UnidentifiedImageError = ValueError
    monkeypatch.setitem(sys.modules, "PIL", fake_pil)
    monkeypatch.setitem(sys.modules, "PIL.Image", FakeImage)

    f = tmp_path / "broken.png"
    f.write_bytes(b"\x89PNG truncated")
    broken, reason = broken_detector.check_image(f)
    assert broken is True
    assert "image verify failed" in reason


# ── Video check ──────────────────────────────────────────────────────────


def test_check_video_no_ffprobe_returns_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_FFPROBE", None)
    f = tmp_path / "x.mp4"
    f.write_bytes(b"\x00")
    broken, reason = broken_detector.check_video(f)
    assert broken is False
    assert reason == ""


def test_check_video_ffprobe_returns_error_json(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_FFPROBE", "ffprobe")
    completed = mock.MagicMock()
    completed.returncode = 0
    completed.stdout = '{"error":{"code":-541478725,"string":"End of file"}}'
    completed.stderr = ""
    monkeypatch.setattr(broken_detector.subprocess, "run", lambda *a, **k: completed)

    f = tmp_path / "broken.mp4"
    f.write_bytes(b"placeholder")
    broken, reason = broken_detector.check_video(f)
    assert broken is True
    assert "End of file" in reason


def test_check_video_ffprobe_nonzero_rc(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_FFPROBE", "ffprobe")
    completed = mock.MagicMock()
    completed.returncode = 1
    completed.stdout = ""
    completed.stderr = "Invalid data found when processing input"
    monkeypatch.setattr(broken_detector.subprocess, "run", lambda *a, **k: completed)

    f = tmp_path / "broken.mp4"
    f.write_bytes(b"placeholder")
    broken, reason = broken_detector.check_video(f)
    assert broken is True
    assert "rc=1" in reason


def test_check_video_ffprobe_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_FFPROBE", "ffprobe")
    completed = mock.MagicMock()
    completed.returncode = 0
    completed.stdout = '{"streams":[],"format":{}}'
    completed.stderr = ""
    monkeypatch.setattr(broken_detector.subprocess, "run", lambda *a, **k: completed)

    f = tmp_path / "ok.mp4"
    f.write_bytes(b"placeholder")
    broken, reason = broken_detector.check_video(f)
    assert broken is False
    assert reason == ""


def test_check_video_rc0_with_stderr_is_broken(tmp_path, monkeypatch):
    """Audit fix: ffprobe sometimes emits warnings to stderr while returning rc=0.
    Rubric requires treating any non-empty stderr as a broken signal."""
    monkeypatch.setattr(broken_detector, "_FFPROBE", "ffprobe")
    completed = mock.MagicMock()
    completed.returncode = 0
    completed.stdout = '{"streams":[],"format":{}}'
    completed.stderr = "[mov,mp4,m4a,3gp,3g2,mj2 @ 0x1] moov atom not found"
    monkeypatch.setattr(broken_detector.subprocess, "run", lambda *a, **k: completed)

    f = tmp_path / "warn.mp4"
    f.write_bytes(b"placeholder")
    broken, reason = broken_detector.check_video(f)
    assert broken is True
    assert "moov atom" in reason


# ── Archive check (real zipfile, no mocks needed) ─────────────────────────


def test_check_archive_healthy_zip(tmp_path):
    f = tmp_path / "good.zip"
    with zipfile.ZipFile(str(f), "w") as z:
        z.writestr("hello.txt", "world")
    broken, reason = broken_detector.check_archive(f)
    assert broken is False
    assert reason == ""


def test_check_archive_corrupt_zip(tmp_path):
    f = tmp_path / "bad.zip"
    f.write_bytes(b"PK\x03\x04 truncated header data")
    broken, reason = broken_detector.check_archive(f)
    assert broken is True
    assert reason  # non-empty diagnostic


def test_check_archive_missing_file(tmp_path):
    broken, reason = broken_detector.check_archive(tmp_path / "nope.zip")
    assert broken is True
    assert reason == "missing"


def test_check_archive_unknown_format_returns_healthy(tmp_path):
    f = tmp_path / "thing.unknown"
    f.write_bytes(b"x")
    broken, reason = broken_detector.check_archive(f)
    assert broken is False
    assert reason == ""


def test_check_archive_rar_no_dep_returns_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_HAS_RARFILE", False)
    f = tmp_path / "x.rar"
    f.write_bytes(b"Rar!\x1a\x07")
    broken, reason = broken_detector.check_archive(f)
    assert broken is False
    assert reason == ""


def test_check_archive_7z_no_dep_returns_healthy(tmp_path, monkeypatch):
    monkeypatch.setattr(broken_detector, "_HAS_PY7ZR", False)
    f = tmp_path / "x.7z"
    f.write_bytes(b"7z\xbc\xaf\x27\x1c")
    broken, reason = broken_detector.check_archive(f)
    assert broken is False
    assert reason == ""


# ── CLI smoke ────────────────────────────────────────────────────────────


def test_cli_scan_finds_broken_zip_and_returns_1(tmp_path, capsys):
    good = tmp_path / "good.zip"
    with zipfile.ZipFile(str(good), "w") as z:
        z.writestr("ok.txt", "x")
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"PK\x03\x04 garbage")
    rc = broken_detector._cli_scan(tmp_path)
    assert rc == 1
    out = capsys.readouterr().out
    assert "BROKEN" in out
    assert "bad.zip" in out
    assert "good.zip" not in out  # only broken lines printed
    assert "broken=1" in out


def test_cli_scan_clean_dir_returns_0(tmp_path, capsys):
    f = tmp_path / "good.zip"
    with zipfile.ZipFile(str(f), "w") as z:
        z.writestr("ok.txt", "y")
    rc = broken_detector._cli_scan(tmp_path)
    assert rc == 0
    out = capsys.readouterr().out
    assert "checked=1" in out
    assert "broken=0" in out


def test_cli_scan_missing_dir_returns_2(tmp_path, capsys):
    rc = broken_detector._cli_scan(tmp_path / "no_such_dir")
    assert rc == 2


# ── asset_db schema migration ────────────────────────────────────────────


def test_asset_db_files_table_has_broken_column(tmp_path):
    import asset_db
    db = tmp_path / "fp.db"
    con = asset_db.init_db(str(db))
    cols = {r[1] for r in con.execute("PRAGMA table_info(asset_files)").fetchall()}
    assert "broken" in cols
    con.close()


def test_asset_db_broken_migration_idempotent(tmp_path):
    import asset_db
    db = tmp_path / "fp.db"
    con1 = asset_db.init_db(str(db)); con1.close()
    con2 = asset_db.init_db(str(db))
    cols = [r[1] for r in con2.execute("PRAGMA table_info(asset_files)").fetchall()]
    assert cols.count("broken") == 1
    con2.close()
