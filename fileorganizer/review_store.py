"""Durable, bounded review results for cleanup and duplicate scans.

The store deliberately contains no file-operation implementation.  Callers
must request an action plan (or use :meth:`apply_selected`) so every selected
path is revalidated immediately before an adapter is invoked.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import time
import uuid
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any


SCHEMA_VERSION = 2
EXPORT_FORMAT = "fileorganizer-review/v1"
MAX_SCANS = 50
MAX_ENTRIES_PER_SCAN = 100_000
MAX_TOTAL_ENTRIES = 250_000
MAX_PATH_CHARS = 4096
MAX_TEXT_CHARS = 2048
MAX_OPTIONS_BYTES = 32 * 1024
MAX_IMPORT_BYTES = 64 * 1024 * 1024
MAX_DATABASE_BYTES = 512 * 1024 * 1024
VALID_KINDS = frozenset({"cleanup", "duplicates"})
VALID_DECISIONS = frozenset({"review", "keep", "delete", "quarantine", "skip"})


def default_review_db() -> Path:
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return Path(base) / "FileOrganizer" / "review-results.sqlite3"


def _now_ns() -> int:
    return time.time_ns()


def _bounded_text(value: object, limit: int = MAX_TEXT_CHARS) -> str:
    return str(value or "")[:limit]


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class ReviewStore:
    """Versioned SQLite store for resumable, explicitly revalidated reviews."""

    def __init__(self, db_path: str | os.PathLike[str] | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else default_review_db()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(str(self.db_path), timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RuntimeError(
                    f"Review store schema {version} is newer than supported schema {SCHEMA_VERSION}."
                )
            if version == 0:
                connection.executescript(
                    """
                    PRAGMA journal_mode=WAL;
                    PRAGMA auto_vacuum=INCREMENTAL;
                    CREATE TABLE scans (
                        id TEXT PRIMARY KEY,
                        kind TEXT NOT NULL,
                        root TEXT NOT NULL,
                        mode TEXT NOT NULL,
                        options_json TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_ns INTEGER NOT NULL,
                        updated_ns INTEGER NOT NULL,
                        total_count INTEGER NOT NULL DEFAULT 0,
                        total_size INTEGER NOT NULL DEFAULT 0,
                        truncated INTEGER NOT NULL DEFAULT 0,
                        source_scan_id TEXT NOT NULL DEFAULT ''
                    );
                    CREATE TABLE entries (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        scan_id TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
                        ordinal INTEGER NOT NULL,
                        group_key TEXT NOT NULL DEFAULT '',
                        path TEXT NOT NULL,
                        path_kind TEXT NOT NULL,
                        size INTEGER NOT NULL,
                        mtime_ns INTEGER NOT NULL,
                        content_sha256 TEXT NOT NULL DEFAULT '',
                        reason TEXT NOT NULL DEFAULT '',
                        category TEXT NOT NULL DEFAULT '',
                        distance INTEGER,
                        decision TEXT NOT NULL DEFAULT 'review',
                        is_reference INTEGER NOT NULL DEFAULT 0,
                        UNIQUE(scan_id, ordinal)
                    );
                    CREATE INDEX entries_scan_idx ON entries(scan_id, ordinal);
                    CREATE INDEX scans_updated_idx ON scans(updated_ns DESC);
                    PRAGMA user_version=1;
                    """
                )
                version = 1
            if version == 1:
                connection.executescript(
                    """
                    ALTER TABLE entries ADD COLUMN validation_status TEXT NOT NULL DEFAULT 'unchecked';
                    ALTER TABLE entries ADD COLUMN validation_reason TEXT NOT NULL DEFAULT '';
                    ALTER TABLE entries ADD COLUMN validated_ns INTEGER NOT NULL DEFAULT 0;
                    PRAGMA user_version=2;
                    """
                )
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            max_pages = max(1, MAX_DATABASE_BYTES // page_size)
            connection.execute(f"PRAGMA max_page_count={max_pages}")

    def create_scan(
        self,
        kind: str,
        root: str,
        mode: str,
        options: Mapping[str, Any] | None = None,
        *,
        scan_id: str | None = None,
        source_scan_id: str = "",
    ) -> str:
        if kind not in VALID_KINDS:
            raise ValueError(f"Unsupported review kind: {kind}")
        if not str(root).strip():
            raise ValueError("Review root cannot be empty.")
        root_path = os.path.abspath(os.path.normpath(root))
        if len(root_path) > MAX_PATH_CHARS:
            raise ValueError("Review root is too long.")
        encoded_options = json.dumps(dict(options or {}), separators=(",", ":"), sort_keys=True)
        if len(encoded_options.encode("utf-8")) > MAX_OPTIONS_BYTES:
            raise ValueError("Review options exceed the storage limit.")
        identifier = scan_id or uuid.uuid4().hex
        if len(identifier) > 128 or not identifier:
            raise ValueError("Invalid review scan ID.")
        now = _now_ns()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO scans
                   (id, kind, root, mode, options_json, status, created_ns, updated_ns, source_scan_id)
                   VALUES (?, ?, ?, ?, ?, 'running', ?, ?, ?)""",
                (identifier, kind, root_path, _bounded_text(mode, 64), encoded_options,
                 now, now, _bounded_text(source_scan_id, 128)),
            )
            self._prune(connection, protected_scan_id=identifier)
        return identifier

    def append_entries(
        self,
        scan_id: str,
        entries: Iterable[Mapping[str, Any]],
        *,
        preserve_snapshot: bool = False,
    ) -> int:
        added = 0
        with self._connect() as connection:
            scan = connection.execute("SELECT root FROM scans WHERE id=?", (scan_id,)).fetchone()
            if scan is None:
                raise KeyError(f"Unknown review scan: {scan_id}")
            ordinal = int(connection.execute(
                "SELECT COALESCE(MAX(ordinal), -1) + 1 FROM entries WHERE scan_id=?", (scan_id,)
            ).fetchone()[0])
            available = MAX_ENTRIES_PER_SCAN - ordinal
            for raw in entries:
                if available <= 0:
                    connection.execute("UPDATE scans SET truncated=1 WHERE id=?", (scan_id,))
                    break
                raw_path = str(raw.get("path", ""))
                if not raw_path.strip():
                    continue
                path = os.path.abspath(os.path.normpath(raw_path))
                if len(path) > MAX_PATH_CHARS:
                    continue
                if preserve_snapshot:
                    path_kind = _bounded_text(raw.get("path_kind", "file"), 16)
                    if path_kind not in {"file", "directory"}:
                        path_kind = "file"
                    size = max(0, int(raw.get("size", 0) or 0))
                    modified = float(raw.get("modified", 0.0) or 0.0)
                    mtime_ns = int(raw.get("mtime_ns", modified * 1_000_000_000))
                else:
                    try:
                        stat = os.stat(path, follow_symlinks=False)
                        path_kind = "directory" if os.path.isdir(path) else "file"
                        size = int(stat.st_size) if path_kind == "file" else 0
                        mtime_ns = int(stat.st_mtime_ns)
                    except OSError:
                        path_kind = _bounded_text(raw.get("path_kind", "file"), 16)
                        if path_kind not in {"file", "directory"}:
                            path_kind = "file"
                        size = max(0, int(raw.get("size", 0) or 0))
                        modified = float(raw.get("modified", 0.0) or 0.0)
                        mtime_ns = int(raw.get("mtime_ns", modified * 1_000_000_000))
                digest = _bounded_text(raw.get("content_sha256"), 64).lower()
                if digest and (len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest)):
                    digest = ""
                decision = _bounded_text(raw.get("decision", "review"), 16)
                if decision not in VALID_DECISIONS:
                    decision = "review"
                connection.execute(
                    """INSERT INTO entries
                       (scan_id, ordinal, group_key, path, path_kind, size, mtime_ns,
                        content_sha256, reason, category, distance, decision, is_reference)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (scan_id, ordinal, _bounded_text(raw.get("group_key"), 256), path,
                     path_kind, size, mtime_ns, digest,
                     _bounded_text(raw.get("reason")), _bounded_text(raw.get("category"), 256),
                     self._distance(raw.get("distance")), decision,
                     int(bool(raw.get("is_reference", False)))),
                )
                ordinal += 1
                available -= 1
                added += 1
            connection.execute(
                "UPDATE scans SET updated_ns=?, total_count=total_count+? WHERE id=?",
                (_now_ns(), added, scan_id),
            )
            if added and ordinal % 512 == 0:
                self._prune(connection, protected_scan_id=scan_id)
        return added

    def finish_scan(self, scan_id: str, status: str, *, total_size: int = 0) -> None:
        if status not in {"complete", "cancelled", "failed", "interrupted"}:
            raise ValueError(f"Invalid terminal scan status: {status}")
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE scans SET status=?, updated_ns=?, total_size=? WHERE id=?",
                (status, _now_ns(), max(0, int(total_size)), scan_id),
            )
            if result.rowcount == 0:
                raise KeyError(f"Unknown review scan: {scan_id}")
            self._prune(connection, protected_scan_id=scan_id)

    def set_decision(self, scan_id: str, entry_id: int, decision: str) -> None:
        if decision not in VALID_DECISIONS:
            raise ValueError(f"Invalid review decision: {decision}")
        with self._connect() as connection:
            result = connection.execute(
                "UPDATE entries SET decision=? WHERE scan_id=? AND id=?",
                (decision, scan_id, int(entry_id)),
            )
            if result.rowcount == 0:
                raise KeyError(f"Unknown review entry: {entry_id}")
            connection.execute("UPDATE scans SET updated_ns=? WHERE id=?", (_now_ns(), scan_id))

    def get_scan(self, scan_id: str, *, revalidate: bool = False) -> dict[str, Any]:
        if revalidate:
            self.revalidate_scan(scan_id)
        with self._connect() as connection:
            scan = connection.execute("SELECT * FROM scans WHERE id=?", (scan_id,)).fetchone()
            if scan is None:
                raise KeyError(f"Unknown review scan: {scan_id}")
            entries = connection.execute(
                "SELECT * FROM entries WHERE scan_id=? ORDER BY ordinal", (scan_id,)
            ).fetchall()
        result = dict(scan)
        result["options"] = json.loads(result.pop("options_json"))
        result["truncated"] = bool(result["truncated"])
        result["entries"] = [self._entry_dict(row) for row in entries]
        return result

    @staticmethod
    def _entry_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["is_reference"] = bool(result["is_reference"])
        return result

    @staticmethod
    def _distance(value: object) -> int | None:
        if value is None:
            return None
        if not isinstance(value, (str, bytes, bytearray, int, float)):
            return None
        try:
            return min(256, max(0, int(value)))
        except (TypeError, ValueError, OverflowError):
            return None

    def list_scans(self, kind: str | None = None) -> list[dict[str, Any]]:
        query = "SELECT * FROM scans"
        params: tuple[str, ...] = ()
        if kind is not None:
            query += " WHERE kind=?"
            params = (kind,)
        query += " ORDER BY updated_ns DESC LIMIT ?"
        with self._connect() as connection:
            rows = connection.execute(query, (*params, MAX_SCANS)).fetchall()
        return [dict(row) for row in rows]

    def revalidate_scan(self, scan_id: str) -> dict[str, int]:
        with self._connect() as connection:
            scan = connection.execute("SELECT root FROM scans WHERE id=?", (scan_id,)).fetchone()
            if scan is None:
                raise KeyError(f"Unknown review scan: {scan_id}")
            rows = connection.execute("SELECT * FROM entries WHERE scan_id=?", (scan_id,)).fetchall()
            counts: dict[str, int] = {}
            validated_ns = _now_ns()
            for row in rows:
                status, reason = self._validate_entry(scan["root"], row)
                counts[status] = counts.get(status, 0) + 1
                connection.execute(
                    """UPDATE entries SET validation_status=?, validation_reason=?, validated_ns=?
                       WHERE id=?""",
                    (status, reason, validated_ns, row["id"]),
                )
            connection.execute("UPDATE scans SET updated_ns=? WHERE id=?", (validated_ns, scan_id))
        return counts

    @staticmethod
    def _validate_entry(root: str, row: sqlite3.Row | Mapping[str, Any]) -> tuple[str, str]:
        path = str(row["path"])
        try:
            resolved_root = os.path.normcase(os.path.realpath(root))
            resolved_path = os.path.normcase(os.path.realpath(path))
            if os.path.commonpath((resolved_root, resolved_path)) != resolved_root:
                return "stale", "outside scan root"
        except (OSError, ValueError):
            return "stale", "outside scan root"
        try:
            stat = os.stat(path, follow_symlinks=False)
        except FileNotFoundError:
            return "missing", "path no longer exists"
        except OSError as exc:
            return "stale", f"path cannot be inspected: {type(exc).__name__}"
        actual_kind = "directory" if os.path.isdir(path) else "file"
        if actual_kind != row["path_kind"]:
            return "stale", "path type changed"
        if actual_kind == "file" and int(stat.st_size) != int(row["size"]):
            return "stale", "size changed"
        if int(stat.st_mtime_ns) != int(row["mtime_ns"]):
            return "stale", "modified time changed"
        expected_hash = str(row["content_sha256"] or "")
        if expected_hash:
            try:
                if _sha256_file(path) != expected_hash:
                    return "stale", "content hash changed"
            except OSError as exc:
                return "stale", f"content cannot be read: {type(exc).__name__}"
        return "fresh", ""

    def action_plan(self, scan_id: str, action: str) -> dict[str, list[dict[str, Any]]]:
        if action not in {"delete", "quarantine"}:
            raise ValueError("Review actions must be delete or quarantine.")
        self.revalidate_scan(scan_id)
        scan = self.get_scan(scan_id)
        selected = [entry for entry in scan["entries"] if entry["decision"] == action]
        ready = [entry for entry in selected if entry["validation_status"] == "fresh"]
        stale = [entry for entry in selected if entry["validation_status"] != "fresh"]
        if scan["kind"] == "duplicates":
            selected_ids = {entry["id"] for entry in selected}
            groups_with_keeper = {
                entry["group_key"]
                for entry in scan["entries"]
                if entry["id"] not in selected_ids and entry["validation_status"] == "fresh"
            }
            guarded_ready: list[dict[str, Any]] = []
            for entry in ready:
                if entry["group_key"] in groups_with_keeper:
                    guarded_ready.append(entry)
                else:
                    entry["validation_status"] = "stale"
                    entry["validation_reason"] = "duplicate group has no fresh keeper"
                    stale.append(entry)
            ready = guarded_ready
        return {
            "ready": ready,
            "stale": stale,
        }

    def apply_selected(
        self,
        scan_id: str,
        action: str,
        adapter: Callable[[dict[str, Any]], Any],
    ) -> dict[str, list[Any]]:
        """Invoke *adapter* only for rows still fresh at their point of use."""
        plan = self.action_plan(scan_id, action)
        applied: list[Any] = []
        stale: list[dict[str, Any]] = list(plan["stale"])
        scan = self.get_scan(scan_id)
        root = scan["root"]
        for entry in plan["ready"]:
            status, reason = self._validate_entry(root, entry)
            if status != "fresh":
                entry["validation_status"] = status
                entry["validation_reason"] = reason
                stale.append(entry)
                continue
            applied.append(adapter(entry))
        return {"applied": applied, "stale": stale}

    def export_scan(self, scan_id: str, destination: str | os.PathLike[str]) -> Path:
        scan = self.get_scan(scan_id, revalidate=True)
        payload = {"format": EXPORT_FORMAT, "schema_version": SCHEMA_VERSION, "scan": scan}
        raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        if len(raw) > MAX_IMPORT_BYTES:
            raise ValueError("Review export exceeds the file size limit.")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary_name = tempfile.mkstemp(prefix=f".{target.name}.", suffix=".tmp", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_name, target)
        except BaseException:
            try:
                os.unlink(temporary_name)
            except OSError:
                pass
            raise
        return target

    def import_scan(self, source: str | os.PathLike[str]) -> str:
        path = Path(source)
        if path.stat().st_size > MAX_IMPORT_BYTES:
            raise ValueError("Review import exceeds the file size limit.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("format") != EXPORT_FORMAT:
            raise ValueError("Unsupported review export format.")
        scan = payload.get("scan")
        if not isinstance(scan, dict) or scan.get("kind") not in VALID_KINDS:
            raise ValueError("Review export has an invalid scan record.")
        entries = scan.get("entries")
        if not isinstance(entries, list) or len(entries) > MAX_ENTRIES_PER_SCAN:
            raise ValueError("Review export has too many entries.")
        new_id = self.create_scan(
            str(scan["kind"]), str(scan.get("root", "")), str(scan.get("mode", "")),
            scan.get("options") if isinstance(scan.get("options"), dict) else {},
            source_scan_id=_bounded_text(scan.get("id"), 128),
        )
        try:
            self.append_entries(new_id, entries, preserve_snapshot=True)
            total_size = max(0, int(scan.get("total_size", 0) or 0))
            self.finish_scan(new_id, "complete", total_size=total_size)
            self.revalidate_scan(new_id)
        except BaseException:
            with self._connect() as connection:
                connection.execute("DELETE FROM scans WHERE id=?", (new_id,))
            raise
        return new_id

    def _prune(
        self,
        connection: sqlite3.Connection,
        *,
        protected_scan_id: str = "",
    ) -> None:
        connection.execute(
            """DELETE FROM scans WHERE id IN (
                   SELECT id FROM scans ORDER BY updated_ns DESC LIMIT -1 OFFSET ?
               )""",
            (MAX_SCANS,),
        )
        total = int(connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
        while total > MAX_TOTAL_ENTRIES:
            oldest = connection.execute(
                """SELECT id FROM scans WHERE id<>?
                   ORDER BY CASE WHEN status='running' THEN 1 ELSE 0 END, updated_ns ASC
                   LIMIT 1""",
                (protected_scan_id,),
            ).fetchone()
            if oldest is None:
                break
            connection.execute("DELETE FROM scans WHERE id=?", (oldest["id"],))
            total = int(connection.execute("SELECT COUNT(*) FROM entries").fetchone()[0])
        connection.execute("PRAGMA incremental_vacuum(128)")
