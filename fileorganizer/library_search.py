"""Local FTS5 index and natural-language search for organized libraries."""
from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from fileorganizer.config import _APP_DATA_DIR


_SEARCH_DB = os.path.join(_APP_DATA_DIR, "library_search.db")
_FTS_TABLE = "library_documents_fts"
_STOP_WORDS = {
    "a", "all", "and", "are", "for", "from", "find", "files", "in",
    "is", "me", "of", "show", "the", "that", "this", "to", "with",
}
_MAX_DESCRIPTION = 4000
_MAX_QUERY_LENGTH = 500


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _clean(value: object, limit: int) -> str:
    text = str(value or "").replace("\x00", " ")
    return re.sub(r"\s+", " ", text).strip()[:limit]


def _root(value: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(value)))


def _connect(db_path: str = _SEARCH_DB) -> sqlite3.Connection:
    connection = sqlite3.connect(db_path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> bool:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS library_documents (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            library_root  TEXT NOT NULL,
            path          TEXT NOT NULL,
            name          TEXT NOT NULL,
            category      TEXT NOT NULL DEFAULT '',
            description   TEXT NOT NULL DEFAULT '',
            kind          TEXT NOT NULL DEFAULT 'file',
            updated_at    TEXT NOT NULL,
            UNIQUE(library_root, path)
        );
        CREATE INDEX IF NOT EXISTS idx_library_documents_root
            ON library_documents(library_root);
        """
    )
    try:
        connection.execute(
            f"""CREATE VIRTUAL TABLE IF NOT EXISTS {_FTS_TABLE} USING fts5(
                name, path, category, description,
                content='library_documents', content_rowid='id',
                tokenize='unicode61 remove_diacritics 2'
            )"""
        )
        return True
    except sqlite3.OperationalError:
        # SQLite builds without FTS5 still get a useful LIKE-backed search.
        return False


def _rebuild_fts(connection: sqlite3.Connection, fts_available: bool) -> None:
    if not fts_available:
        return
    try:
        connection.execute(f"INSERT INTO {_FTS_TABLE}({_FTS_TABLE}) VALUES('rebuild')")
    except sqlite3.OperationalError:
        # A damaged index should not make a move or index refresh fail.  The
        # next refresh can rebuild it again from the canonical table.
        pass


def _entry(
    path: str | os.PathLike[str],
    *,
    library_root: str | os.PathLike[str],
    category: str = "",
    description: str = "",
    kind: str = "file",
) -> dict:
    absolute = os.path.abspath(os.fspath(path))
    return {
        "library_root": _root(library_root),
        "path": absolute,
        "name": _clean(Path(absolute).name, 512),
        "category": _clean(category, 512),
        "description": _clean(description, _MAX_DESCRIPTION),
        "kind": "folder" if kind == "folder" else "file",
        "updated_at": _now(),
    }


def index_entries(entries: list[dict], db_path: str = _SEARCH_DB) -> int:
    """Upsert search records and rebuild the local FTS index once."""
    if not entries:
        return 0
    connection = _connect(db_path)
    try:
        fts_available = _ensure_schema(connection)
        for raw in entries:
            record = _entry(
                raw["path"],
                library_root=raw["library_root"],
                category=raw.get("category", ""),
                description=raw.get("description", ""),
                kind=raw.get("kind", "file"),
            )
            connection.execute(
                """
                INSERT INTO library_documents
                    (library_root, path, name, category, description, kind, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(library_root, path) DO UPDATE SET
                    name=excluded.name,
                    category=excluded.category,
                    description=excluded.description,
                    kind=excluded.kind,
                    updated_at=excluded.updated_at
                """,
                tuple(record[key] for key in (
                    "library_root", "path", "name", "category", "description",
                    "kind", "updated_at",
                )),
            )
        _rebuild_fts(connection, fts_available)
        connection.commit()
        return len(entries)
    finally:
        connection.close()


def index_entry(
    path: str | os.PathLike[str],
    *,
    library_root: str | os.PathLike[str],
    category: str = "",
    description: str = "",
    kind: str = "file",
    db_path: str = _SEARCH_DB,
) -> int:
    """Upsert one moved asset into the search index."""
    return index_entries([{
        "path": path,
        "library_root": library_root,
        "category": category,
        "description": description,
        "kind": kind,
    }], db_path=db_path)


def index_library(
    library_root: str | os.PathLike[str],
    *,
    descriptions: dict[str, str] | None = None,
    db_path: str = _SEARCH_DB,
) -> int:
    """Index folders and files under an organized root.

    ``descriptions`` is optional and keyed by absolute path.  It lets callers
    merge cached AI descriptions without coupling this module to a provider or
    a particular classification database.
    """
    root_path = Path(library_root).resolve()
    if not root_path.is_dir():
        return 0
    normalized_root = _root(root_path)
    provided_descriptions = descriptions or {}
    entries = []
    try:
        for dirpath, dirnames, filenames in os.walk(root_path, followlinks=False):
            dirnames[:] = sorted(
                name for name in dirnames
                if not name.startswith(".")
                and not os.path.islink(os.path.join(dirpath, name))
            )
            filenames = sorted(name for name in filenames if not name.startswith("."))
            current = Path(dirpath)
            if current != root_path:
                relative = current.relative_to(root_path)
                category = relative.parts[0] if relative.parts else ""
                path_text = str(current)
                entries.append({
                    "path": path_text,
                    "library_root": normalized_root,
                    "category": category,
                    "description": provided_descriptions.get(path_text, ""),
                    "kind": "folder",
                })
            for filename in filenames:
                file_path = current / filename
                try:
                    relative = file_path.relative_to(root_path)
                except ValueError:
                    continue
                category = relative.parts[0] if relative.parts else ""
                path_text = str(file_path)
                entries.append({
                    "path": path_text,
                    "library_root": normalized_root,
                    "category": category,
                    "description": provided_descriptions.get(path_text, ""),
                    "kind": "file",
                })
    except OSError:
        pass

    connection = _connect(db_path)
    try:
        fts_available = _ensure_schema(connection)
        existing_descriptions = {
            row["path"]: row["description"]
            for row in connection.execute(
                "SELECT path, description FROM library_documents WHERE library_root=?",
                (normalized_root,),
            ).fetchall()
        }
        for entry in entries:
            path_text = str(entry["path"])
            if path_text not in provided_descriptions:
                entry["description"] = existing_descriptions.get(path_text, "")
        connection.execute(
            "DELETE FROM library_documents WHERE library_root = ?",
            (normalized_root,),
        )
        for raw in entries:
            record = _entry(
                raw["path"],
                library_root=normalized_root,
                category=raw.get("category", ""),
                description=raw.get("description", ""),
                kind=raw.get("kind", "file"),
            )
            connection.execute(
                """
                INSERT INTO library_documents
                    (library_root, path, name, category, description, kind, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                tuple(record[key] for key in (
                    "library_root", "path", "name", "category", "description",
                    "kind", "updated_at",
                )),
            )
        _rebuild_fts(connection, fts_available)
        connection.commit()
    finally:
        connection.close()
    return len(entries)


def _parse_query(query: str) -> tuple[str, dict[str, str]]:
    """Turn a human query into a safe FTS expression and simple filters."""
    raw = _clean(query, _MAX_QUERY_LENGTH)
    filters: dict[str, str] = {}

    def pull_filter(match: re.Match) -> str:
        filters[match.group(1).casefold()] = match.group(2)
        return " "

    remaining = re.sub(
        r"\b(category|type):([^\s]+)", pull_filter, raw, flags=re.IGNORECASE,
    )
    phrases = re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', remaining)
    remaining = re.sub(r'"([^"\\]*(?:\\.[^"\\]*)*)"', " ", remaining)
    tokens = [
        token for token in re.findall(r"[^\W_]+", remaining, flags=re.UNICODE)
        if token.casefold() not in _STOP_WORDS
    ]
    parts = []
    for phrase in phrases:
        cleaned = _clean(phrase, 200).replace('"', ' ')
        if cleaned:
            parts.append('"' + cleaned + '"')
    for token in tokens:
        parts.append('"' + token.replace('"', ' ') + '"*')
    return " AND ".join(parts), filters


def _search_rows(
    connection: sqlite3.Connection,
    expression: str,
    filters: dict[str, str],
    *,
    library_root: str = "",
    fts_available: bool,
    limit: int,
) -> list[sqlite3.Row]:
    params: list[object] = []
    clauses = []
    if library_root:
        clauses.append("d.library_root = ?")
        params.append(_root(library_root))
    if filters.get("category"):
        clauses.append("d.category LIKE ? COLLATE NOCASE")
        params.append(f"%{filters['category']}%")
    if filters.get("type") in {"file", "folder"}:
        clauses.append("d.kind = ?")
        params.append(filters["type"])
    where = " AND ".join(clauses)
    where_sql = f" AND {where}" if where else ""
    if fts_available:
        sql = f"""
            SELECT d.id, d.path, d.name, d.category, d.description, d.kind,
                   bm25({_FTS_TABLE}, 10.0, 1.0, 5.0, 2.0) AS rank
            FROM {_FTS_TABLE} f
            JOIN library_documents d ON d.id = f.rowid
            WHERE {_FTS_TABLE} MATCH ?{where_sql}
            ORDER BY rank ASC, d.path COLLATE NOCASE
            LIMIT ?
        """
        params = [expression, *params, limit]
    else:
        like_terms = [part.replace('"', '').replace('*', '') for part in expression.split(" AND ") if part]
        search_sql = " AND ".join(
            "(d.name LIKE ? OR d.path LIKE ? OR d.category LIKE ? OR d.description LIKE ?)"
            for _ in like_terms
        ) or "1=1"
        like_params = []
        for term in like_terms:
            value = f"%{term}%"
            like_params.extend([value, value, value, value])
        sql = f"""
            SELECT d.id, d.path, d.name, d.category, d.description, d.kind,
                   0.0 AS rank
            FROM library_documents d
            WHERE {search_sql}{where_sql}
            ORDER BY d.path COLLATE NOCASE
            LIMIT ?
        """
        params = [*like_params, *params, limit]
    return connection.execute(sql, params).fetchall()


def search_library(
    query: str,
    *,
    library_root: str | os.PathLike[str] | None = None,
    limit: int = 50,
    db_path: str = _SEARCH_DB,
) -> list[dict]:
    """Search indexed paths, categories, and AI descriptions.

    Queries support ordinary natural-language words plus ``category:...`` and
    ``type:file|folder`` filters.  Results include a citation string suitable
    for a local RAG prompt or direct display in Browse.
    """
    expression, filters = _parse_query(query)
    if not expression:
        return []
    try:
        bounded_limit = max(1, min(200, int(limit)))
    except (TypeError, ValueError):
        bounded_limit = 50
    if not os.path.exists(db_path):
        return []
    connection = _connect(db_path)
    try:
        fts_available = _ensure_schema(connection)
        rows = _search_rows(
            connection, expression, filters,
            library_root=str(library_root or ""),
            fts_available=fts_available,
            limit=bounded_limit,
        )
        # If a natural-language query is too specific for an AND expression,
        # return useful partial matches rather than an empty Browse panel.
        if not rows and " AND " in expression:
            rows = _search_rows(
                connection, expression.replace(" AND ", " OR "), filters,
                library_root=str(library_root or ""),
                fts_available=fts_available,
                limit=bounded_limit,
            )
        results = []
        for rank, row in enumerate(rows, start=1):
            description = row["description"] or ""
            citation = f"[{rank}] {row['path']}"
            if description:
                citation += f" — {description}"
            results.append({
                "rank": rank,
                "path": row["path"],
                "name": row["name"],
                "category": row["category"],
                "description": description,
                "kind": row["kind"],
                "score": round(max(0.0, -float(row["rank"] or 0.0)), 6),
                "citation": citation,
            })
        return results
    finally:
        connection.close()


def remove_entry(
    path: str | os.PathLike[str],
    *,
    library_root: str | os.PathLike[str],
    db_path: str = _SEARCH_DB,
) -> int:
    """Remove one path from the durable index."""
    if not os.path.exists(db_path):
        return 0
    connection = _connect(db_path)
    try:
        fts_available = _ensure_schema(connection)
        cursor = connection.execute(
            "DELETE FROM library_documents WHERE library_root=? AND path=?",
            (_root(library_root), os.path.abspath(os.fspath(path))),
        )
        _rebuild_fts(connection, fts_available)
        connection.commit()
        return cursor.rowcount
    finally:
        connection.close()


__all__ = [
    "index_entries", "index_entry", "index_library", "remove_entry",
    "search_library",
]
