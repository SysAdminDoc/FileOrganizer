"""Non-destructive virtual asset bundles backed by a local SQLite database."""

from __future__ import annotations

import hashlib
import os
import re
import sqlite3
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path

from fileorganizer.cache import hash_file
from fileorganizer.config import _APP_DATA_DIR


DEFAULT_BUNDLE_DB = os.path.join(_APP_DATA_DIR, "asset_bundles.db")
MAX_BUNDLE_NAME = 160
MAX_BUNDLES = 1000
MAX_MEMBERS_PER_BUNDLE = 20_000
_WHITESPACE = re.compile(r"\s+")
_FINGERPRINT_CHUNK = 65536
_MAX_FOLDER_FILES = 20_000


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _connect(db_path: str = DEFAULT_BUNDLE_DB) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS asset_bundles (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL UNIQUE,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS asset_bundle_members (
            bundle_id    INTEGER NOT NULL REFERENCES asset_bundles(id) ON DELETE CASCADE,
            fingerprint  TEXT NOT NULL,
            path_hint    TEXT NOT NULL DEFAULT '',
            asset_name   TEXT NOT NULL DEFAULT '',
            added_at     TEXT NOT NULL,
            PRIMARY KEY (bundle_id, fingerprint)
        );
        CREATE INDEX IF NOT EXISTS idx_asset_bundle_members_fingerprint
            ON asset_bundle_members(fingerprint);
        """
    )


def _clean_name(name: object) -> str:
    cleaned = _WHITESPACE.sub(" ", str(name or "").replace("\x00", " ")).strip()
    return cleaned[:MAX_BUNDLE_NAME]


def asset_fingerprint(path: str | os.PathLike[str]) -> str:
    """Return a stable content/listing fingerprint for one file or asset folder."""
    absolute = os.path.abspath(os.fspath(path))
    if os.path.isdir(absolute):
        digest = hashlib.sha256()
        file_count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(absolute, followlinks=False):
                dirnames[:] = sorted(
                    name for name in dirnames
                    if not os.path.islink(os.path.join(dirpath, name))
                )
                filenames = sorted(
                    name for name in filenames
                    if not os.path.islink(os.path.join(dirpath, name))
                )
                relative_dir = os.path.relpath(dirpath, absolute)
                for filename in filenames:
                    if file_count >= _MAX_FOLDER_FILES:
                        break
                    file_path = os.path.join(dirpath, filename)
                    try:
                        size = os.path.getsize(file_path)
                        with open(file_path, "rb") as handle:
                            prefix = handle.read(_FINGERPRINT_CHUNK)
                            if size > _FINGERPRINT_CHUNK:
                                handle.seek(max(0, size - _FINGERPRINT_CHUNK))
                                suffix = handle.read(_FINGERPRINT_CHUNK)
                            else:
                                suffix = b""
                    except (OSError, PermissionError):
                        continue
                    relative = os.path.normcase(os.path.join(relative_dir, filename))
                    digest.update(relative.encode("utf-8", "surrogatepass"))
                    digest.update(b"\0")
                    digest.update(str(size).encode("ascii"))
                    digest.update(b"\0")
                    digest.update(hashlib.sha256(prefix + suffix).digest())
                    file_count += 1
                if file_count >= _MAX_FOLDER_FILES:
                    break
        except OSError:
            return ""
        digest.update(f"\0files:{file_count}".encode("ascii"))
        return digest.hexdigest() if file_count else hashlib.sha256(b"folder:empty").hexdigest()
    if os.path.isfile(absolute):
        digest = hash_file(absolute)
        return digest or ""
    return ""


def create_bundle(name: str, *, db_path: str = DEFAULT_BUNDLE_DB) -> dict:
    """Create an empty named bundle, rejecting empty or duplicate names."""
    cleaned = _clean_name(name)
    if not cleaned:
        raise ValueError("Bundle name cannot be empty")
    connection = _connect(db_path)
    try:
        _ensure_schema(connection)
        count = connection.execute("SELECT COUNT(*) FROM asset_bundles").fetchone()[0]
        if count >= MAX_BUNDLES:
            raise ValueError("Bundle limit reached")
        now = _now()
        try:
            cursor = connection.execute(
                "INSERT INTO asset_bundles(name, created_at, updated_at) VALUES (?, ?, ?)",
                (cleaned, now, now),
            )
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"Bundle already exists: {cleaned}") from exc
        connection.commit()
        return {"id": int(cursor.lastrowid), "name": cleaned, "member_count": 0}
    finally:
        connection.close()


def list_bundles(*, db_path: str = DEFAULT_BUNDLE_DB) -> list[dict]:
    """List bundles with member counts in stable name order."""
    if not os.path.exists(db_path):
        return []
    connection = _connect(db_path)
    try:
        _ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT b.id, b.name, b.created_at, b.updated_at,
                   COUNT(m.fingerprint) AS member_count
            FROM asset_bundles b
            LEFT JOIN asset_bundle_members m ON m.bundle_id=b.id
            GROUP BY b.id
            ORDER BY b.name COLLATE NOCASE
            """
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def bundle_members(bundle_id: int, *, db_path: str = DEFAULT_BUNDLE_DB) -> list[dict]:
    """Return one bundle's fingerprints and last-known path hints."""
    connection = _connect(db_path)
    try:
        _ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT fingerprint, path_hint, asset_name, added_at
            FROM asset_bundle_members
            WHERE bundle_id=?
            ORDER BY asset_name COLLATE NOCASE, path_hint COLLATE NOCASE
            """,
            (int(bundle_id),),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def add_assets(
    bundle_id: int,
    paths: Iterable[str | os.PathLike[str]],
    *,
    db_path: str = DEFAULT_BUNDLE_DB,
) -> int:
    """Fingerprint existing assets and add them idempotently to a bundle."""
    candidates = []
    for raw_path in paths:
        path = os.path.abspath(os.fspath(raw_path))
        fingerprint = asset_fingerprint(path)
        if fingerprint:
            candidates.append((fingerprint, path, Path(path).name))
    if not candidates:
        return 0
    connection = _connect(db_path)
    try:
        _ensure_schema(connection)
        exists = connection.execute(
            "SELECT 1 FROM asset_bundles WHERE id=?", (int(bundle_id),)
        ).fetchone()
        if not exists:
            raise ValueError("Bundle does not exist")
        current = connection.execute(
            "SELECT COUNT(*) FROM asset_bundle_members WHERE bundle_id=?", (int(bundle_id),)
        ).fetchone()[0]
        remaining = max(0, MAX_MEMBERS_PER_BUNDLE - int(current))
        now = _now()
        added = 0
        for fingerprint, path, asset_name in candidates[:remaining]:
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO asset_bundle_members
                    (bundle_id, fingerprint, path_hint, asset_name, added_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(bundle_id), fingerprint, path, asset_name[:512], now),
            )
            added += int(cursor.rowcount > 0)
        connection.execute(
            "UPDATE asset_bundles SET updated_at=? WHERE id=?", (now, int(bundle_id))
        )
        connection.commit()
        return added
    finally:
        connection.close()


def add_fingerprints(
    bundle_id: int,
    fingerprints: Iterable[str],
    *,
    path_hints: dict[str, str] | None = None,
    db_path: str = DEFAULT_BUNDLE_DB,
) -> int:
    """Add already-computed fingerprints for integrations without file paths."""
    cleaned = [str(value).strip() for value in fingerprints if str(value).strip()]
    if not cleaned:
        return 0
    hints = path_hints or {}
    connection = _connect(db_path)
    try:
        _ensure_schema(connection)
        if not connection.execute(
            "SELECT 1 FROM asset_bundles WHERE id=?", (int(bundle_id),)
        ).fetchone():
            raise ValueError("Bundle does not exist")
        current = connection.execute(
            "SELECT COUNT(*) FROM asset_bundle_members WHERE bundle_id=?", (int(bundle_id),)
        ).fetchone()[0]
        now = _now()
        added = 0
        for fingerprint in cleaned[:max(0, MAX_MEMBERS_PER_BUNDLE - int(current))]:
            path_hint = os.path.abspath(hints.get(fingerprint, "")) if hints.get(fingerprint) else ""
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO asset_bundle_members
                    (bundle_id, fingerprint, path_hint, asset_name, added_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (int(bundle_id), fingerprint[:256], path_hint, Path(path_hint).name[:512], now),
            )
            added += int(cursor.rowcount > 0)
        connection.execute(
            "UPDATE asset_bundles SET updated_at=? WHERE id=?", (now, int(bundle_id))
        )
        connection.commit()
        return added
    finally:
        connection.close()


def remove_members(
    bundle_id: int,
    fingerprints: Iterable[str],
    *,
    db_path: str = DEFAULT_BUNDLE_DB,
) -> int:
    """Remove selected fingerprints without touching the underlying assets."""
    values = [str(value).strip() for value in fingerprints if str(value).strip()]
    if not values:
        return 0
    connection = _connect(db_path)
    try:
        _ensure_schema(connection)
        removed = 0
        for fingerprint in values:
            cursor = connection.execute(
                "DELETE FROM asset_bundle_members WHERE bundle_id=? AND fingerprint=?",
                (int(bundle_id), fingerprint),
            )
            removed += max(0, cursor.rowcount)
        connection.commit()
        return removed
    finally:
        connection.close()


def delete_bundle(bundle_id: int, *, db_path: str = DEFAULT_BUNDLE_DB) -> bool:
    """Delete one virtual bundle and its membership rows only."""
    connection = _connect(db_path)
    try:
        _ensure_schema(connection)
        cursor = connection.execute("DELETE FROM asset_bundles WHERE id=?", (int(bundle_id),))
        connection.commit()
        return bool(cursor.rowcount)
    finally:
        connection.close()


__all__ = [
    "DEFAULT_BUNDLE_DB", "add_assets", "add_fingerprints", "asset_fingerprint",
    "bundle_members", "create_bundle", "delete_bundle", "list_bundles",
    "remove_members",
]
