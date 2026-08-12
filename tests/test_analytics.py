"""Tests for local analytics aggregation."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fileorganizer.analytics import load_analytics_snapshot


def test_analytics_snapshot_aggregates_local_stores(tmp_path: Path):
    journal = tmp_path / "organize_moves.db"
    with sqlite3.connect(journal) as connection:
        connection.executescript(
            """
            CREATE TABLE moves (
                id INTEGER PRIMARY KEY, category TEXT, dst TEXT, status TEXT,
                source_signature TEXT, ts_done TEXT
            );
            """
        )
        connection.executemany(
            """
            INSERT INTO moves(category, dst, status, source_signature, ts_done)
            VALUES (?, ?, 'done', ?, ?)
            """,
            [
                ("Archives", r"C:\Library\Archives\pack.zip", json.dumps({"size": 120}), "2026-08-01"),
                ("Images", r"C:\Library\Images\photo.jpg", json.dumps({"size": 50}), "2026-08-02"),
                ("Images", r"C:\Library\Images\other.jpg", json.dumps({"size": 60}), "2026-08-03"),
            ],
        )

    provenance = tmp_path / "provenance.db"
    with sqlite3.connect(provenance) as connection:
        connection.execute(
            """
            CREATE TABLE classification_provenance (
                record_id TEXT PRIMARY KEY, classified_at TEXT, provider TEXT,
                model TEXT, suggested_decision TEXT, final_decision TEXT,
                user_correction TEXT
            )
            """
        )
        connection.executemany(
            "INSERT INTO classification_provenance VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                ("1", "2026-08-01T10:00:00Z", "local", "model-a", "Images", "Images", ""),
                ("2", "2026-08-01T11:00:00Z", "local", "model-a", "Images", "Documents", "Documents"),
            ],
        )

    review = tmp_path / "review-results.sqlite3"
    with sqlite3.connect(review) as connection:
        connection.executescript(
            """
            CREATE TABLE scans (id TEXT PRIMARY KEY, kind TEXT);
            CREATE TABLE entries (
                path TEXT, scan_id TEXT, is_reference INTEGER, size INTEGER
            );
            INSERT INTO scans VALUES ('scan-1', 'duplicates');
            INSERT INTO entries VALUES ('a.psd', 'scan-1', 1, 100);
            INSERT INTO entries VALUES ('b.psd', 'scan-1', 0, 80);
            INSERT INTO entries VALUES ('c.psd', 'scan-1', 0, 70);
            """
        )

    snapshot = load_analytics_snapshot(
        journal_db=journal,
        provenance_db=provenance,
        review_db=review,
    )

    assert snapshot["organized"]["total"] == 3
    assert snapshot["organized"]["by_category"][0] == {"category": "Images", "count": 2}
    assert snapshot["organized"]["top_file_types"][0] == {"extension": ".jpg", "count": 2}
    assert snapshot["storage_reclaimed_bytes"] == 120
    assert snapshot["model"]["accuracy"] == 0.5
    assert snapshot["model"]["confusion_matrix"][1]["final"] == "Documents"
    assert snapshot["duplicates"] == {
        "total": 3,
        "duplicates": 2,
        "rate": 2 / 3,
        "bytes": 150,
    }


def test_analytics_snapshot_is_empty_without_databases(tmp_path: Path):
    snapshot = load_analytics_snapshot(
        journal_db=tmp_path / "missing-journal.db",
        provenance_db=tmp_path / "missing-provenance.db",
        review_db=tmp_path / "missing-review.db",
    )

    assert snapshot["organized"]["total"] == 0
    assert snapshot["model"]["total"] == 0
    assert snapshot["duplicates"]["rate"] == 0.0
