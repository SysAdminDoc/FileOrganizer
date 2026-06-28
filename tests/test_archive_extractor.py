from __future__ import annotations

import io
import sys
import tarfile
import types
import zipfile
from pathlib import Path

import pytest

from fileorganizer import archive_extractor as ae


def test_zip_extraction_rejects_traversal_entries(tmp_path: Path):
    archive = tmp_path / "payload.zip"
    dest = tmp_path / "dest"
    outside = tmp_path / "escape.txt"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("safe/project.psd", b"ok")
        zf.writestr("../escape.txt", b"bad")
        zf.writestr("C:/Windows/evil.psd", b"bad")

    extracted = ae.extract_archive(str(archive), str(dest), strip_top_folder=False)

    assert [Path(p).relative_to(dest).as_posix() for p in extracted] == ["safe/project.psd"]
    assert (dest / "safe" / "project.psd").read_bytes() == b"ok"
    assert not outside.exists()
    assert not any(p.name == "evil.psd" for p in dest.rglob("*"))


def test_tar_extraction_rejects_traversal_and_links(tmp_path: Path):
    archive = tmp_path / "payload.tar"
    dest = tmp_path / "dest"
    with tarfile.open(archive, "w") as tf:
        data = b"ok"
        info = tarfile.TarInfo("safe/project.ai")
        info.size = len(data)
        tf.addfile(info, io.BytesIO(data))

        bad = tarfile.TarInfo("../escape.ai")
        bad.size = 3
        tf.addfile(bad, io.BytesIO(b"bad"))

        link = tarfile.TarInfo("safe/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../escape.ai"
        tf.addfile(link)

    extracted = ae.extract_archive(str(archive), str(dest), strip_top_folder=False)

    assert [Path(p).relative_to(dest).as_posix() for p in extracted] == ["safe/project.ai"]
    assert (dest / "safe" / "project.ai").read_bytes() == b"ok"
    assert not (tmp_path / "escape.ai").exists()
    assert not (dest / "safe" / "link").exists()


def test_rar_extraction_uses_safe_member_paths(tmp_path: Path, monkeypatch):
    archive = tmp_path / "payload.rar"
    archive.write_bytes(b"rar")
    dest = tmp_path / "dest"

    class FakeInfo:
        def __init__(self, filename):
            self.filename = filename
            self.file_size = 2

        def is_dir(self):
            return False

    class FakeRarFile:
        def __init__(self, _path):
            self.members = [FakeInfo("safe/font.otf"), FakeInfo("../escape.otf")]

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def infolist(self):
            return self.members

        def open(self, member):
            return io.BytesIO(member.filename.encode("utf-8"))

    fake_rarfile = types.ModuleType("rarfile")
    fake_rarfile.RarFile = FakeRarFile
    monkeypatch.setitem(sys.modules, "rarfile", fake_rarfile)

    extracted = ae.extract_archive(str(archive), str(dest), strip_top_folder=False)

    assert [Path(p).relative_to(dest).as_posix() for p in extracted] == ["safe/font.otf"]
    assert (dest / "safe" / "font.otf").read_bytes() == b"safe/font.otf"
    assert not (tmp_path / "escape.otf").exists()


def test_7z_extraction_validates_before_extracting_each_member(tmp_path: Path, monkeypatch):
    archive = tmp_path / "payload.7z"
    archive.write_bytes(b"7z")
    dest = tmp_path / "dest"
    extracted_targets = []

    class FakeSevenZipFile:
        def __init__(self, _path, _mode):
            self.names = ["safe/project.aep", "../escape.aep"]

        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def getnames(self):
            return self.names

        def extractall(self, _path):
            raise AssertionError("unfiltered extractall must not be called")

        def extract(self, path, targets):
            extracted_targets.extend(targets)
            for target in targets:
                out = Path(path, *target.split("/"))
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(target.encode("utf-8"))

    fake_py7zr = types.ModuleType("py7zr")
    fake_py7zr.SevenZipFile = FakeSevenZipFile
    monkeypatch.setitem(sys.modules, "py7zr", fake_py7zr)

    extracted = ae.extract_archive(str(archive), str(dest), strip_top_folder=False)

    assert extracted_targets == ["safe/project.aep"]
    assert [Path(p).relative_to(dest).as_posix() for p in extracted] == ["safe/project.aep"]
    assert (dest / "safe" / "project.aep").read_bytes() == b"safe/project.aep"
    assert not (tmp_path / "escape.aep").exists()


def test_safe_member_destination_rejects_unsafe_even_when_flattening(tmp_path: Path):
    with pytest.raises(ae.UnsafeArchiveEntryError):
        ae._safe_member_destination(str(tmp_path), "../evil.psd", flatten=True)
