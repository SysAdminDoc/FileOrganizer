"""Durable, local checkpoints for long-running duplicate scans."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import time
from collections.abc import Iterable

from fileorganizer.config import _APP_DATA_DIR

DEFAULT_CHECKPOINT_PATH = os.path.join(_APP_DATA_DIR, "dedup_checkpoints.db")


def checkpoint_key(file_entries: Iterable[tuple]) -> str:
    """Return a stable identity for one file set and its current stat data."""
    normalized = []
    for entry in file_entries:
        path = str(entry[0])
        size = int(entry[1]) if len(entry) > 1 else 0
        mtime_ns = int(entry[2]) if len(entry) > 2 else 0
        normalized.append((os.path.normcase(os.path.abspath(path)), size, mtime_ns))
    payload = json.dumps(sorted(normalized), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class DedupCheckpointStore:
    """SQLite-backed stage hash store, safe to update in small batches."""

    def __init__(self, path: str = DEFAULT_CHECKPOINT_PATH):
        self.path = str(path)
        self._conn: sqlite3.Connection | None = None

    def open(self) -> None:
        if self._conn is not None:
            return
        directory = os.path.dirname(os.path.abspath(self.path))
        os.makedirs(directory, exist_ok=True)
        self._conn = sqlite3.connect(self.path, timeout=5)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute(
            """CREATE TABLE IF NOT EXISTS dedup_checkpoint_hashes (
                run_key TEXT NOT NULL,
                stage TEXT NOT NULL,
                path TEXT NOT NULL,
                value TEXT NOT NULL,
                updated REAL NOT NULL,
                PRIMARY KEY (run_key, stage, path)
            )"""
        )
        self._conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_dedup_checkpoint_updated "
            "ON dedup_checkpoint_hashes(updated)"
        )
        self._conn.commit()

    def get(self, run_key: str, stage: str, path: str) -> str | None:
        if self._conn is None:
            self.open()
        row = self._conn.execute(
            "SELECT value FROM dedup_checkpoint_hashes "
            "WHERE run_key=? AND stage=? AND path=?",
            (run_key, stage, str(path)),
        ).fetchone()
        return str(row[0]) if row else None

    def put_many(self, run_key: str, stage: str, values: dict[str, str]) -> None:
        if not values:
            return
        if self._conn is None:
            self.open()
        now = time.time()
        self._conn.executemany(
            "INSERT OR REPLACE INTO dedup_checkpoint_hashes "
            "(run_key, stage, path, value, updated) VALUES (?, ?, ?, ?, ?)",
            [(run_key, stage, str(path), str(value), now) for path, value in values.items()],
        )
        self._conn.commit()

    def clear(self, run_key: str) -> None:
        if self._conn is None:
            return
        self._conn.execute(
            "DELETE FROM dedup_checkpoint_hashes WHERE run_key=?", (run_key,)
        )
        self._conn.commit()

    def prune(self, max_age_days: int = 30) -> None:
        if self._conn is None:
            return
        cutoff = time.time() - max(1, int(max_age_days)) * 86400
        self._conn.execute(
            "DELETE FROM dedup_checkpoint_hashes WHERE updated < ?", (cutoff,)
        )
        self._conn.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *_exc) -> None:
        self.close()
