from __future__ import annotations

import shutil
import sqlite3
import struct
from pathlib import Path

import asset_db
import pytest
from fileorganizer.folder_cache import FolderCache
from fileorganizer.usn_index import (
    FILE_ATTRIBUTE_DIRECTORY,
    USN_REASON_FILE_CREATE,
    USN_REASON_FILE_DELETE,
    USN_REASON_RENAME_NEW_NAME,
    USN_REASON_RENAME_OLD_NAME,
    JournalCursor,
    NativeUsnReader,
    UsnChange,
    UsnIncrementalIndex,
    UsnUnavailableError,
    VolumeInfo,
    resume_usn_changes,
)


class FakeUsnBackend:
    def __init__(self, *, next_usn: int = 100):
        self.volume = VolumeInfo(True, "C:\\", "volume-1", "NTFS")
        self.cursor = JournalCursor("journal-1", 0, next_usn, 0)
        self.changes: list[UsnChange] = []
        self.read_starts: list[int] = []

    def probe(self, _root_path: str) -> VolumeInfo:
        return self.volume

    def query(self, _volume: VolumeInfo) -> JournalCursor:
        return self.cursor

    def read_changes(
        self,
        _volume: VolumeInfo,
        start_usn: int,
        _journal_id: str,
        stop_usn: int,
    ) -> tuple[list[UsnChange], int]:
        self.read_starts.append(start_usn)
        return list(self.changes), stop_usn


class UnsupportedBackend(FakeUsnBackend):
    def probe(self, _root_path: str) -> VolumeInfo:
        return VolumeInfo(False, filesystem="exFAT", reason="unsupported filesystem exFAT")


def _catalog(root: Path) -> tuple[Path, Path, Path]:
    category = root / "Category"
    asset = category / "Asset"
    asset.mkdir(parents=True)
    file_path = asset / "project.aep"
    file_path.write_bytes(b"version-one")
    return category, asset, file_path


def _change(
    path: Path,
    *,
    usn: int,
    reason: int,
    name: str | None = None,
    is_directory: bool = False,
    file_reference: str | None = None,
    parent_reference: str | None = None,
) -> UsnChange:
    return UsnChange(
        file_reference=file_reference or str(path.stat().st_ino),
        parent_reference=parent_reference or str(path.parent.stat().st_ino),
        usn=usn,
        reason=reason,
        name=name or path.name,
        is_directory=is_directory,
    )


def _v2_record(name: str, *, reason: int = USN_REASON_FILE_CREATE) -> bytes:
    encoded = name.encode("utf-16le")
    record_length = 60 + len(encoded)
    record = bytearray(record_length)
    struct.pack_into("<IHH", record, 0, record_length, 2, 0)
    struct.pack_into("<Q", record, 8, 123)
    struct.pack_into("<Q", record, 16, 456)
    struct.pack_into("<q", record, 24, 789)
    struct.pack_into("<I", record, 40, reason)
    struct.pack_into("<I", record, 52, FILE_ATTRIBUTE_DIRECTORY)
    struct.pack_into("<HH", record, 56, len(encoded), 60)
    record[60:] = encoded
    return bytes(record)


def _catalog_rows(db_path: Path) -> tuple[list[tuple], list[tuple]]:
    con = sqlite3.connect(db_path)
    assets = con.execute(
        "SELECT clean_name, category, file_count, total_bytes, folder_fingerprint "
        "FROM assets ORDER BY category, clean_name"
    ).fetchall()
    files = con.execute(
        "SELECT filename, relative_path, size_bytes, sha256, is_project_file "
        "FROM asset_files ORDER BY relative_path"
    ).fetchall()
    con.close()
    return assets, files


def test_native_v2_parser_preserves_cursor_identity_and_name():
    next_usn, changes = NativeUsnReader.parse_records(
        struct.pack("<q", 999) + _v2_record("New Folder")
    )

    assert next_usn == 999
    assert changes == [
        UsnChange(
            file_reference="123",
            parent_reference="456",
            usn=789,
            reason=USN_REASON_FILE_CREATE,
            name="New Folder",
            is_directory=True,
        )
    ]


def test_native_probe_and_query_reports_a_safe_runtime_path(tmp_path: Path):
    reader = NativeUsnReader()
    volume = reader.probe(str(tmp_path))
    if not volume.supported:
        assert volume.reason
        return
    try:
        cursor = reader.query(volume)
    except UsnUnavailableError as exc:
        pytest.skip(f"USN journal access unavailable: {exc}")
    assert cursor.journal_id
    assert cursor.next_usn >= cursor.lowest_valid_usn


def test_initial_checkpoint_survives_restart(tmp_path: Path):
    root = tmp_path / "organized"
    _catalog(root)
    db_path = tmp_path / "assets.db"
    backend = FakeUsnBackend()
    tracker = UsnIncrementalIndex(str(db_path), backend)

    plan = tracker.prepare(str(root))
    assert plan.mode == "full_rebuild"
    tracker.complete_full_scan(plan)

    resumed = UsnIncrementalIndex(str(db_path), backend).prepare(str(root))
    assert resumed.mode == "incremental"
    assert resumed.start_usn == 100
    assert resumed.end_usn == 100
    assert resumed.affected_assets == set()
    stats = tracker.stats(str(root))
    assert stats["next_usn"] == 100
    assert stats["tracked_entries"] == 4


def test_wrap_and_volume_identity_changes_force_rebuild(tmp_path: Path):
    root = tmp_path / "organized"
    _catalog(root)
    db_path = tmp_path / "assets.db"
    backend = FakeUsnBackend(next_usn=100)
    tracker = UsnIncrementalIndex(str(db_path), backend)
    tracker.complete_full_scan(tracker.prepare(str(root)))

    backend.cursor = JournalCursor("journal-1", 0, 200, 150)
    wrapped = tracker.prepare(str(root))
    assert wrapped.mode == "full_rebuild"
    assert "wrapped" in wrapped.reason

    backend.cursor = JournalCursor("journal-2", 0, 200, 0)
    replaced = tracker.prepare(str(root))
    assert replaced.mode == "full_rebuild"
    assert "journal identity" in replaced.reason


def test_asset_db_rehashes_same_count_change_and_removes_deleted_asset(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / "organized"
    category, asset, file_path = _catalog(root)
    db_path = tmp_path / "assets.db"
    backend = FakeUsnBackend(next_usn=100)
    monkeypatch.setattr(asset_db, "_load_classification_lookup", lambda: {})
    monkeypatch.setattr(asset_db, "_palette_for_file", lambda _path: (None, None))

    first = asset_db.build_database(
        str(root), str(db_path), use_usn=True, _usn_backend=backend
    )
    assert first["index_mode"] == "full_rebuild"
    assert first["usn_checkpoint_advanced"] is True
    con = sqlite3.connect(db_path)
    original_hash = con.execute("SELECT sha256 FROM asset_files").fetchone()[0]
    con.close()

    file_path.write_bytes(b"version-two")
    backend.cursor = JournalCursor("journal-1", 0, 200, 0)
    backend.changes = [_change(file_path, usn=150, reason=1)]
    fingerprint_calls = []
    real_fingerprint = asset_db.folder_fingerprint

    def track_fingerprint(path):
        fingerprint_calls.append(path)
        return real_fingerprint(path)

    monkeypatch.setattr(asset_db, "folder_fingerprint", track_fingerprint)
    second = asset_db.build_database(
        str(root), str(db_path), use_usn=True, _usn_backend=backend
    )
    assert second["index_mode"] == "incremental"
    assert second["updated"] == 1
    assert second["usn_records"] == 1
    assert second["usn_lag_bytes"] == 100
    assert fingerprint_calls == [str(asset)]
    con = sqlite3.connect(db_path)
    changed_hash = con.execute("SELECT sha256 FROM asset_files").fetchone()[0]
    con.close()
    assert changed_hash != original_hash

    full_db = tmp_path / "full-assets.db"
    asset_db.build_database(str(root), str(full_db))
    assert _catalog_rows(db_path) == _catalog_rows(full_db)

    asset_reference = str(asset.stat().st_ino)
    parent_reference = str(category.stat().st_ino)
    shutil.rmtree(asset)
    backend.cursor = JournalCursor("journal-1", 0, 300, 0)
    backend.changes = [
        _change(
            asset,
            usn=250,
            reason=USN_REASON_FILE_DELETE,
            is_directory=True,
            file_reference=asset_reference,
            parent_reference=parent_reference,
        )
    ]
    third = asset_db.build_database(
        str(root), str(db_path), use_usn=True, _usn_backend=backend
    )
    assert third["removed"] == 1
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM asset_files").fetchone()[0] == 0
    con.close()


def test_asset_rename_reconciles_old_and_new_keys(tmp_path: Path, monkeypatch):
    root = tmp_path / "organized"
    category, asset, _file_path = _catalog(root)
    db_path = tmp_path / "assets.db"
    backend = FakeUsnBackend(next_usn=100)
    monkeypatch.setattr(asset_db, "_load_classification_lookup", lambda: {})
    monkeypatch.setattr(asset_db, "_palette_for_file", lambda _path: (None, None))
    asset_db.build_database(str(root), str(db_path), use_usn=True, _usn_backend=backend)

    asset_reference = str(asset.stat().st_ino)
    parent_reference = str(category.stat().st_ino)
    renamed = category / "Renamed Asset"
    asset.rename(renamed)
    backend.cursor = JournalCursor("journal-1", 0, 200, 0)
    backend.changes = [
        _change(
            renamed,
            usn=150,
            reason=USN_REASON_RENAME_OLD_NAME,
            name="Asset",
            is_directory=True,
            file_reference=asset_reference,
            parent_reference=parent_reference,
        ),
        _change(
            renamed,
            usn=151,
            reason=USN_REASON_RENAME_NEW_NAME,
            name="Renamed Asset",
            is_directory=True,
            file_reference=asset_reference,
            parent_reference=parent_reference,
        ),
    ]

    result = asset_db.build_database(
        str(root), str(db_path), use_usn=True, _usn_backend=backend
    )

    assert result["removed"] == 1
    assert result["added"] == 1
    con = sqlite3.connect(db_path)
    names = [row[0] for row in con.execute("SELECT clean_name FROM assets")]
    con.close()
    assert names == ["Renamed Asset"]


def test_incremental_hash_work_is_bounded_to_changed_assets(tmp_path: Path, monkeypatch):
    root = tmp_path / "organized"
    _category, changed_asset, changed_file = _catalog(root)
    untouched_asset = root / "Category" / "Untouched"
    untouched_asset.mkdir()
    (untouched_asset / "other.psd").write_bytes(b"untouched")
    db_path = tmp_path / "assets.db"
    backend = FakeUsnBackend(next_usn=100)
    monkeypatch.setattr(asset_db, "_load_classification_lookup", lambda: {})
    monkeypatch.setattr(asset_db, "_palette_for_file", lambda _path: (None, None))
    asset_db.build_database(str(root), str(db_path), use_usn=True, _usn_backend=backend)
    changed_file.write_bytes(b"changed")
    backend.cursor = JournalCursor("journal-1", 0, 200, 0)
    backend.changes = [_change(changed_file, usn=150, reason=1)]
    calls = []
    real_fingerprint = asset_db.folder_fingerprint

    def track(path):
        calls.append(path)
        return real_fingerprint(path)

    monkeypatch.setattr(asset_db, "folder_fingerprint", track)

    result = asset_db.build_database(
        str(root), str(db_path), use_usn=True, _usn_backend=backend
    )

    assert result["updated"] == 1
    assert calls == [str(changed_asset)]
    assert str(untouched_asset) not in calls


def test_category_level_delete_rebuilds_and_prunes_tracked_assets(
    tmp_path: Path, monkeypatch
):
    root = tmp_path / "organized"
    category, _asset, _file_path = _catalog(root)
    db_path = tmp_path / "assets.db"
    backend = FakeUsnBackend(next_usn=100)
    monkeypatch.setattr(asset_db, "_load_classification_lookup", lambda: {})
    monkeypatch.setattr(asset_db, "_palette_for_file", lambda _path: (None, None))
    asset_db.build_database(str(root), str(db_path), use_usn=True, _usn_backend=backend)
    category_reference = str(category.stat().st_ino)
    root_reference = str(root.stat().st_ino)
    shutil.rmtree(category)
    backend.cursor = JournalCursor("journal-1", 0, 200, 0)
    backend.changes = [
        _change(
            category,
            usn=150,
            reason=USN_REASON_FILE_DELETE,
            is_directory=True,
            file_reference=category_reference,
            parent_reference=root_reference,
        )
    ]

    result = asset_db.build_database(
        str(root), str(db_path), use_usn=True, _usn_backend=backend
    )

    assert result["index_mode"] == "full_rebuild"
    assert result["removed"] == 1
    con = sqlite3.connect(db_path)
    assert con.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0
    con.close()


def test_changed_asset_invalidates_folder_cache(tmp_path: Path):
    root = tmp_path / "organized"
    _category, asset, file_path = _catalog(root)
    db_path = tmp_path / "assets.db"
    backend = FakeUsnBackend(next_usn=100)
    tracker = UsnIncrementalIndex(str(db_path), backend)
    tracker.complete_full_scan(tracker.prepare(str(root)))
    cache = FolderCache(str(db_path))
    cache.set(str(asset), "fingerprint")

    backend.cursor = JournalCursor("journal-1", 0, 200, 0)
    backend.changes = [_change(file_path, usn=150, reason=1)]
    plan = tracker.prepare(str(root))
    tracker.complete_incremental(plan)

    assert cache.get(str(asset)) is None


def test_unsupported_volume_uses_existing_full_scan(tmp_path: Path, monkeypatch):
    root = tmp_path / "organized"
    _catalog(root)
    db_path = tmp_path / "assets.db"
    monkeypatch.setattr(asset_db, "_load_classification_lookup", lambda: {})
    monkeypatch.setattr(asset_db, "_palette_for_file", lambda _path: (None, None))

    result = asset_db.build_database(
        str(root),
        str(db_path),
        use_usn=True,
        _usn_backend=UnsupportedBackend(),
    )

    assert result["index_mode"] == "full_fallback"
    assert "exFAT" in result["index_reason"]
    assert result["added"] == 1


def test_watch_resume_emits_changes_after_initial_checkpoint(tmp_path: Path):
    root = tmp_path / "watched"
    root.mkdir()
    db_path = tmp_path / "watch.db"
    backend = FakeUsnBackend(next_usn=100)

    first = resume_usn_changes(str(root), str(db_path), backend)
    assert first["mode"] == "full_checkpoint"
    assert first["events"] == []

    file_path = root / "new-file.txt"
    file_path.write_bytes(b"created while stopped")
    backend.cursor = JournalCursor("journal-1", 0, 200, 0)
    backend.changes = [
        _change(file_path, usn=150, reason=USN_REASON_FILE_CREATE)
    ]
    second = resume_usn_changes(str(root), str(db_path), backend)

    assert second["mode"] == "incremental"
    assert second["lag_bytes"] == 100
    assert second["events"] == [
        {"path": str(file_path), "change_type": "created"}
    ]
