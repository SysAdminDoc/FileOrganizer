import hashlib
import json
import os
import sqlite3
import sys
from pathlib import Path

import cleanup_run
import dedup_run
from fileorganizer import review_store
from fileorganizer.review_store import ReviewStore


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_duplicate_action_revalidates_hash_and_rejects_stale_path(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    keeper = root / "keeper.bin"
    duplicate = root / "duplicate.bin"
    keeper.write_bytes(b"same")
    duplicate.write_bytes(b"same")
    original_mtime = duplicate.stat().st_mtime_ns

    store = ReviewStore(tmp_path / "reviews.sqlite3")
    scan_id = store.create_scan("duplicates", str(root), "files")
    digest = _digest(keeper)
    assert store.append_entries(scan_id, [
        {"path": str(keeper), "group_key": digest[:16], "content_sha256": digest,
         "decision": "keep", "is_reference": True},
        {"path": str(duplicate), "group_key": digest[:16], "content_sha256": digest,
         "decision": "delete"},
    ]) == 2
    store.finish_scan(scan_id, "complete", total_size=4)
    assert store.revalidate_scan(scan_id) == {"fresh": 2}

    duplicate.write_bytes(b"evil")
    os.utime(duplicate, ns=(original_mtime, original_mtime))
    called = []
    result = store.apply_selected(scan_id, "delete", lambda entry: called.append(entry["path"]))

    assert called == []
    assert result["applied"] == []
    assert result["stale"][0]["validation_status"] == "stale"
    assert result["stale"][0]["validation_reason"] == "content hash changed"


def test_missing_and_changed_results_are_explicit_and_never_actionable(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    changed = root / "changed.txt"
    missing = root / "missing.txt"
    changed.write_text("before", encoding="utf-8")
    missing.write_text("remove", encoding="utf-8")

    store = ReviewStore(tmp_path / "reviews.sqlite3")
    scan_id = store.create_scan("cleanup", str(root), "temp_files")
    store.append_entries(scan_id, [
        {"path": str(changed), "reason": "temporary", "decision": "quarantine"},
        {"path": str(missing), "reason": "temporary", "decision": "quarantine"},
    ])
    store.finish_scan(scan_id, "complete")
    changed.write_text("after and larger", encoding="utf-8")
    missing.unlink()

    plan = store.action_plan(scan_id, "quarantine")
    assert plan["ready"] == []
    assert {item["validation_status"] for item in plan["stale"]} == {"stale", "missing"}
    assert {item["validation_reason"] for item in plan["stale"]} == {
        "size changed", "path no longer exists",
    }


def test_duplicate_actions_require_a_fresh_unselected_keeper(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    first_path = root / "first.bin"
    second_path = root / "second.bin"
    first_path.write_bytes(b"same")
    second_path.write_bytes(b"same")
    digest = _digest(first_path)
    store = ReviewStore(tmp_path / "reviews.sqlite3")
    scan_id = store.create_scan("duplicates", str(root), "files")
    store.append_entries(scan_id, [
        {"path": str(first_path), "group_key": "group", "content_sha256": digest,
         "decision": "delete", "is_reference": True},
        {"path": str(second_path), "group_key": "group", "content_sha256": digest,
         "decision": "delete"},
    ])
    store.finish_scan(scan_id, "complete")

    plan = store.action_plan(scan_id, "delete")
    assert plan["ready"] == []
    assert len(plan["stale"]) == 2
    assert {entry["validation_reason"] for entry in plan["stale"]} == {
        "duplicate group has no fresh keeper",
    }


def test_export_import_preserves_decisions_and_revalidates(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    candidate = root / "candidate.tmp"
    candidate.write_bytes(b"data")
    first = ReviewStore(tmp_path / "first.sqlite3")
    scan_id = first.create_scan("cleanup", str(root), "temp_files", {"min_age_days": 3})
    first.append_entries(scan_id, [{
        "path": str(candidate), "reason": "temporary", "category": "temp",
        "decision": "review",
    }])
    entry_id = first.get_scan(scan_id)["entries"][0]["id"]
    first.set_decision(scan_id, entry_id, "quarantine")
    first.finish_scan(scan_id, "complete", total_size=4)

    restarted = ReviewStore(tmp_path / "first.sqlite3").get_scan(scan_id)
    assert restarted["entries"][0]["decision"] == "quarantine"

    exported = first.export_scan(scan_id, tmp_path / "review.json")
    payload = json.loads(exported.read_text(encoding="utf-8"))
    assert payload["format"] == review_store.EXPORT_FORMAT
    assert not list(tmp_path.glob(".review.json.*.tmp"))
    candidate.write_bytes(b"changed after export")

    second = ReviewStore(tmp_path / "second.sqlite3")
    imported_id = second.import_scan(exported)
    imported = second.get_scan(imported_id)
    assert imported_id != scan_id
    assert imported["source_scan_id"] == scan_id
    assert imported["options"] == {"min_age_days": 3}
    assert imported["entries"][0]["decision"] == "quarantine"
    assert imported["entries"][0]["validation_status"] == "stale"
    assert imported["entries"][0]["validation_reason"] == "size changed"


def test_store_caps_entries_and_marks_scan_truncated(tmp_path, monkeypatch):
    monkeypatch.setattr(review_store, "MAX_ENTRIES_PER_SCAN", 2)
    root = tmp_path / "root"
    root.mkdir()
    paths = []
    for index in range(3):
        path = root / f"{index}.tmp"
        path.touch()
        paths.append(path)
    store = ReviewStore(tmp_path / "reviews.sqlite3")
    scan_id = store.create_scan("cleanup", str(root), "temp_files")
    added = store.append_entries(scan_id, ({"path": str(path)} for path in paths))
    scan = store.get_scan(scan_id)
    assert added == 2
    assert scan["truncated"] is True
    assert len(scan["entries"]) == 2


def test_schema_one_database_migrates_validation_columns(tmp_path):
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE scans (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, root TEXT NOT NULL,
                mode TEXT NOT NULL, options_json TEXT NOT NULL, status TEXT NOT NULL,
                created_ns INTEGER NOT NULL, updated_ns INTEGER NOT NULL,
                total_count INTEGER NOT NULL DEFAULT 0, total_size INTEGER NOT NULL DEFAULT 0,
                truncated INTEGER NOT NULL DEFAULT 0, source_scan_id TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                ordinal INTEGER NOT NULL, group_key TEXT NOT NULL DEFAULT '', path TEXT NOT NULL,
                path_kind TEXT NOT NULL, size INTEGER NOT NULL, mtime_ns INTEGER NOT NULL,
                content_sha256 TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '',
                category TEXT NOT NULL DEFAULT '', distance INTEGER,
                decision TEXT NOT NULL DEFAULT 'review', is_reference INTEGER NOT NULL DEFAULT 0,
                UNIQUE(scan_id, ordinal)
            );
            CREATE INDEX entries_scan_idx ON entries(scan_id, ordinal);
            CREATE INDEX scans_updated_idx ON scans(updated_ns DESC);
            PRAGMA user_version=1;
            """
        )
    ReviewStore(database)
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == review_store.SCHEMA_VERSION
        columns = {row[1] for row in connection.execute("PRAGMA table_info(entries)")}
    assert {"validation_status", "validation_reason", "validated_ns"} <= columns


def test_cleanup_sidecar_scan_and_resume_marks_missing_result(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    empty = root / "empty.txt"
    empty.touch()
    database = tmp_path / "reviews.sqlite3"
    events = []
    monkeypatch.setattr(cleanup_run, "_emit", events.append)
    monkeypatch.setattr(sys, "argv", [
        "cleanup_run.py", "--scanner", "empty_files", "--root", str(root),
        "--review-db", str(database),
    ])
    assert cleanup_run.main() == 0
    scan_id = next(event["scan_id"] for event in events if event["event"] == "review")
    empty.unlink()

    events.clear()
    monkeypatch.setattr(sys, "argv", [
        "cleanup_run.py", "--resume-scan", scan_id, "--review-db", str(database),
    ])
    assert cleanup_run.main() == 0
    item = next(event for event in events if event["event"] == "item")
    assert item["validation_status"] == "missing"
    assert item["validation_reason"] == "path no longer exists"


def test_duplicate_sidecar_persists_full_hash_and_keeper(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "one.bin").write_bytes(b"duplicate")
    (root / "two.bin").write_bytes(b"duplicate")
    database = tmp_path / "reviews.sqlite3"
    events = []
    monkeypatch.setattr(dedup_run, "_emit", events.append)
    monkeypatch.setattr(sys, "argv", [
        "dedup_run.py", "--root", str(root), "--mode", "files", "--min-size", "1",
        "--review-db", str(database),
    ])
    assert dedup_run.main() == 0
    scan_id = next(event["scan_id"] for event in events if event["event"] == "review")
    scan = ReviewStore(database).get_scan(scan_id, revalidate=True)
    assert len(scan["entries"]) == 2
    assert len(scan["entries"][0]["content_sha256"]) == 64
    assert [entry["decision"] for entry in scan["entries"]] == ["keep", "review"]
    assert [entry["is_reference"] for entry in scan["entries"]] == [True, False]


def test_invalid_scan_root_does_not_initialize_default_review_database(tmp_path, monkeypatch):
    appdata = tmp_path / "appdata"
    missing = tmp_path / "missing"
    monkeypatch.setenv("APPDATA", str(appdata))
    for runner, argv in (
        (cleanup_run, ["cleanup_run.py", "--scanner", "empty_files", "--root", str(missing)]),
        (dedup_run, ["dedup_run.py", "--root", str(missing)]),
    ):
        events = []
        monkeypatch.setattr(runner, "_emit", events.append)
        monkeypatch.setattr(sys, "argv", argv)
        assert runner.main() == 2
        assert events[-1]["code"] == "root_not_found"
    assert not (appdata / "FileOrganizer" / "review-results.sqlite3").exists()
