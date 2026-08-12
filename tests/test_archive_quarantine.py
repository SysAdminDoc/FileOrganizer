"""Archive payload quarantine and safe destination tests."""

from __future__ import annotations

import io
import json
import tarfile
import zipfile
from pathlib import Path
from typing import Any

from fileorganizer import scan_mixin
from fileorganizer.quarantine import quarantine_destination
from fileorganizer.workers import _mark_archive_quarantine


def test_design_zip_with_executable_is_marked_without_extraction(tmp_path: Path):
    archive = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("pack/template.psd", b"design")
        handle.writestr("pack/install.ps1", b"payload")
        handle.writestr("pack/readme.txt", b"readme")

    metadata: dict[str, object] = {}
    assert _mark_archive_quarantine(str(archive), metadata)
    assert metadata["quarantine_files"] == ["pack/install.ps1"]
    assert metadata["quarantine_count"] == 1
    assert metadata["quarantine_source_name"] == "pack"
    json.dumps(metadata)
    assert not (tmp_path / "pack" / "install.ps1").exists()


def test_design_tar_with_executable_is_marked(tmp_path: Path):
    archive = tmp_path / "pack.tar.gz"
    with tarfile.open(archive, "w:gz") as handle:
        for name, payload in (("pack/scene.ai", b"design"), ("pack/setup.exe", b"payload")):
            info = tarfile.TarInfo(name)
            info.size = len(payload)
            handle.addfile(info, io.BytesIO(payload))

    metadata: dict[str, object] = {}
    assert _mark_archive_quarantine(str(archive), metadata)
    assert metadata["quarantine_files"] == ["pack/setup.exe"]
    assert metadata["quarantine_source_name"] == "pack.tar"


def test_non_design_archive_is_not_quarantined(tmp_path: Path):
    archive = tmp_path / "scripts.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.writestr("install.ps1", b"payload")

    metadata: dict[str, object] = {}
    assert not _mark_archive_quarantine(str(archive), metadata)
    assert metadata == {}


def test_quarantine_destination_is_bounded_and_does_not_extract(tmp_path: Path):
    root = tmp_path / "library"
    quarantine_root, destination = quarantine_destination(
        str(root), r"..\evil.zip", r"payload\..\setup.exe"
    )

    assert Path(quarantine_root) == root / "_Quarantine" / "evil"
    assert Path(destination) == root / "_Quarantine" / "evil" / "setup.exe"
    assert not Path(destination).exists()


def test_scan_result_routes_archive_to_quarantine_root(tmp_path: Path, monkeypatch):
    class FakeScan(scan_mixin.ScanMixin):
        pass

    fake: Any = FakeScan.__new__(FakeScan)
    fake.file_items = []
    fake._rename_counters = {}
    fake._pc_src_path = lambda: str(tmp_path / "source")
    fake._pc_template_for = lambda _category: ""
    fake._pc_dst_for = lambda category: str(tmp_path / "library" / category)
    fake._dedup_file_dst = lambda path: path
    fake._add_files_row = lambda *_args: None
    fake._stats_files = lambda: None
    monkeypatch.setattr(scan_mixin, "load_photo_settings", lambda: {"enabled": False})

    scan_mixin.ScanMixin._on_files_result(fake, {
        "name": "pack.zip",
        "full_src": str(tmp_path / "source" / "pack.zip"),
        "category": "Images",
        "confidence": 90,
        "method": "archive_peek",
        "detail": "File: .zip",
        "size": 12,
        "is_folder": False,
        "is_duplicate": False,
        "metadata": {
            "quarantine_files": ["pack/setup.exe"],
            "quarantine_count": 1,
            "quarantine_category": "Images",
        },
    })

    item = fake.file_items[0]
    assert item.category == "_Quarantine"
    assert Path(item.full_dst) == (
        tmp_path / "library" / "Images" / "_Quarantine" / "pack" / "pack.zip"
    )
    assert Path(item.dest_root) == tmp_path / "library" / "Images" / "_Quarantine" / "pack"
