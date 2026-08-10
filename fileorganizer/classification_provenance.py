"""Durable, privacy-preserving provenance for AI classifications.

The store intentionally keeps hashes instead of prompts, model responses, file
names, or paths.  A caller may supply paths explicitly at export time, but they
are never persisted by this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import tempfile
from collections.abc import Callable, Iterable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fileorganizer.config import _APP_DATA_DIR


SCHEMA_VERSION = 2
EXPORT_SCHEMA_VERSION = 1
DEFAULT_RECORD_LIMIT = 100_000
MAX_JSONL_LINE_BYTES = 64 * 1024
DEFAULT_DB_PATH = Path(_APP_DATA_DIR) / "classification-provenance.sqlite3"
DEFAULT_EXPORT_DIR = Path(_APP_DATA_DIR) / "exports"

_CLASSIFICATION_SCHEMA = {
    "name": "string",
    "category": "string",
    "clean_name": "string",
    "confidence": "integer:0-100",
    "notes": "optional-string",
}
_SECRET_PATTERNS = (
    re.compile(r"\b(?:sk|ghp|github_pat|api)[-_][A-Za-z0-9_-]{8,}\b", re.IGNORECASE),
    re.compile(r"\bBearer\s+[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE),
    re.compile(
        r"(?i)(api[_-]?key|access[_-]?token|authorization|password)"
        r"(\s*[:=]\s*)([^\s,;]+)"
    ),
)
_ABSOLUTE_PATH = re.compile(r"^(?:[A-Za-z]:[\\/]|\\\\|/)")
_EXPORT_FIELDS = (
    "schema_version",
    "record_id",
    "input_fingerprint",
    "provider",
    "model",
    "prompt_hash",
    "schema_hash",
    "taxonomy_hash",
    "response_hash",
    "response_id_hash",
    "confidence",
    "suggested_decision",
    "user_correction",
    "final_decision",
    "classified_at",
    "corrected_at",
    "updated_at",
    "run_id",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _canonical_json(value: object) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
        default=str,
    )


def hash_value(value: object) -> str:
    """Return a full SHA-256 digest for a canonical JSON value."""
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _redact_text(value: object, *, max_length: int = 512) -> str:
    text = str(value or "").strip()[:max_length]
    if _ABSOLUTE_PATH.match(text):
        return "[redacted-path]"
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)(api"):
            text = pattern.sub(r"\1\2[redacted]", text)
        else:
            text = pattern.sub("[redacted-secret]", text)
    return text


def input_fingerprint(value: object) -> str:
    """Fingerprint an input without retaining its raw name or path."""
    if isinstance(value, (str, os.PathLike)):
        path = os.fspath(value)
        try:
            if os.path.isdir(path):
                from fileorganizer.folder_cache import compute_folder_fingerprint

                fingerprint = compute_folder_fingerprint(path)
                if fingerprint:
                    return f"folder-sha256:{fingerprint}"
            elif os.path.isfile(path):
                stat = os.stat(path)
                descriptor = {
                    "kind": "file",
                    "size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "suffix": Path(path).suffix.lower(),
                }
                return f"file-sha256:{hash_value(descriptor)}"
        except OSError:
            pass
        return f"opaque-sha256:{hash_value(path)}"
    return f"input-sha256:{hash_value(value)}"


def _connect(db_path: os.PathLike[str] | str) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=30)
    con.row_factory = sqlite3.Row
    try:
        _ensure_schema(con)
    except Exception:
        con.close()
        raise
    return con


def _ensure_schema(con: sqlite3.Connection) -> None:
    """Create the current schema and migrate older additive schemas."""
    con.execute("BEGIN IMMEDIATE")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS classification_provenance (
            record_id TEXT PRIMARY KEY,
            input_fingerprint TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            schema_hash TEXT NOT NULL DEFAULT '',
            taxonomy_hash TEXT NOT NULL DEFAULT '',
            response_hash TEXT NOT NULL,
            response_id_hash TEXT NOT NULL DEFAULT '',
            confidence INTEGER NOT NULL DEFAULT 0,
            suggested_decision TEXT NOT NULL DEFAULT '',
            user_correction TEXT NOT NULL DEFAULT '',
            final_decision TEXT NOT NULL DEFAULT '',
            classified_at TEXT NOT NULL,
            corrected_at TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            run_id TEXT NOT NULL DEFAULT ''
        )
        """
    )
    existing = {
        str(row[1])
        for row in con.execute(
            "PRAGMA table_info(classification_provenance)"
        ).fetchall()
    }
    migrations = {
        "schema_hash": "TEXT NOT NULL DEFAULT ''",
        "taxonomy_hash": "TEXT NOT NULL DEFAULT ''",
        "response_id_hash": "TEXT NOT NULL DEFAULT ''",
        "user_correction": "TEXT NOT NULL DEFAULT ''",
        "final_decision": "TEXT NOT NULL DEFAULT ''",
        "corrected_at": "TEXT NOT NULL DEFAULT ''",
        "updated_at": "TEXT NOT NULL DEFAULT ''",
        "run_id": "TEXT NOT NULL DEFAULT ''",
    }
    for column, definition in migrations.items():
        if column not in existing:
            con.execute(
                "ALTER TABLE classification_provenance "
                f"ADD COLUMN {column} {definition}"
            )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS classification_provenance_schema (
            schema_name TEXT PRIMARY KEY,
            version INTEGER NOT NULL
        )
        """
    )
    con.execute(
        """
        INSERT INTO classification_provenance_schema(schema_name, version)
        VALUES ('classification_provenance', ?)
        ON CONFLICT(schema_name) DO UPDATE SET version=excluded.version
        WHERE classification_provenance_schema.version < excluded.version
        """,
        (SCHEMA_VERSION,),
    )
    con.execute(
        "UPDATE classification_provenance SET final_decision=suggested_decision "
        "WHERE final_decision=''"
    )
    con.execute(
        "UPDATE classification_provenance SET updated_at=classified_at "
        "WHERE updated_at=''"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_classification_provenance_input "
        "ON classification_provenance(input_fingerprint)"
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_classification_provenance_time "
        "ON classification_provenance(classified_at)"
    )
    con.commit()


def _public_response(response: object) -> object:
    if not isinstance(response, Mapping):
        return response
    return {
        str(key): value
        for key, value in response.items()
        if not str(key).startswith("_")
    }


def record_classification(
    input_value: object,
    *,
    provider: str,
    model: str,
    prompt: object,
    taxonomy: object,
    response: object,
    confidence: int,
    suggested_decision: str,
    final_decision: str = "",
    response_id: str = "",
    run_id: str = "",
    schema: object = _CLASSIFICATION_SCHEMA,
    db_path: os.PathLike[str] | str = DEFAULT_DB_PATH,
    record_limit: int = DEFAULT_RECORD_LIMIT,
) -> dict[str, object]:
    """Persist one classification and return its safe provenance descriptor."""
    fingerprint = input_fingerprint(input_value)
    prompt_digest = hash_value(prompt)
    schema_digest = hash_value(schema)
    taxonomy_digest = hash_value(taxonomy)
    response_digest = hash_value(_public_response(response))
    response_id_digest = hash_value(response_id) if response_id else ""
    provider_name = _redact_text(provider, max_length=100)
    model_name = _redact_text(model, max_length=200)
    suggested = _redact_text(suggested_decision, max_length=300)
    final = _redact_text(final_decision or suggested_decision, max_length=300)
    safe_run_id = _redact_text(run_id, max_length=200)
    bounded_confidence = min(100, max(0, int(confidence)))
    identity = {
        "input_fingerprint": fingerprint,
        "provider": provider_name,
        "model": model_name,
        "prompt_hash": prompt_digest,
        "schema_hash": schema_digest,
        "taxonomy_hash": taxonomy_digest,
        "response_hash": response_digest,
    }
    record_id = f"cls-{hash_value(identity)[:24]}"
    now = _utc_now()

    con = _connect(db_path)
    try:
        con.execute("BEGIN IMMEDIATE")
        con.execute(
            """
            INSERT INTO classification_provenance (
                record_id, input_fingerprint, provider, model, prompt_hash,
                schema_hash, taxonomy_hash, response_hash, response_id_hash,
                confidence, suggested_decision, user_correction,
                final_decision, classified_at, corrected_at, updated_at, run_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, ?, '', ?, ?)
            ON CONFLICT(record_id) DO UPDATE SET
                confidence=excluded.confidence,
                suggested_decision=excluded.suggested_decision,
                final_decision=CASE
                    WHEN classification_provenance.user_correction = ''
                    THEN excluded.final_decision
                    ELSE classification_provenance.final_decision
                END,
                response_id_hash=excluded.response_id_hash,
                updated_at=excluded.updated_at,
                run_id=excluded.run_id
            """,
            (
                record_id,
                fingerprint,
                provider_name,
                model_name,
                prompt_digest,
                schema_digest,
                taxonomy_digest,
                response_digest,
                response_id_digest,
                bounded_confidence,
                suggested,
                final,
                now,
                now,
                safe_run_id,
            ),
        )
        if record_limit > 0:
            con.execute(
                """
                DELETE FROM classification_provenance
                WHERE record_id IN (
                    SELECT record_id FROM classification_provenance
                    ORDER BY classified_at DESC, record_id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (record_limit,),
            )
        con.commit()
    finally:
        con.close()
    return {"record_id": record_id, **identity}


def record_correction(
    *,
    corrected_decision: str,
    record_id: str = "",
    input_value: object | None = None,
    db_path: os.PathLike[str] | str = DEFAULT_DB_PATH,
) -> int:
    """Attach a user correction by provenance ID or stable input fingerprint."""
    if not record_id and input_value is None:
        raise ValueError("record_id or input_value is required")
    correction = _redact_text(corrected_decision, max_length=300)
    if not correction:
        raise ValueError("corrected_decision must not be empty")
    now = _utc_now()
    con = _connect(db_path)
    try:
        if record_id:
            where = "record_id = ?"
            value = record_id
        else:
            where = "input_fingerprint = ?"
            value = input_fingerprint(input_value)
        cur = con.execute(
            "UPDATE classification_provenance SET user_correction=?, "
            f"final_decision=?, corrected_at=?, updated_at=? WHERE {where}",
            (correction, correction, now, now, value),
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def list_records(
    *,
    db_path: os.PathLike[str] | str = DEFAULT_DB_PATH,
    limit: int = DEFAULT_RECORD_LIMIT,
) -> list[dict[str, object]]:
    """Return chronological records using only the redacted export fields."""
    con = _connect(db_path)
    try:
        rows = con.execute(
            "SELECT * FROM classification_provenance "
            "ORDER BY classified_at ASC, record_id ASC LIMIT ?",
            (max(0, min(limit, DEFAULT_RECORD_LIMIT)),),
        ).fetchall()
    finally:
        con.close()
    records: list[dict[str, object]] = []
    for row in rows:
        record = {field: row[field] for field in _EXPORT_FIELDS if field != "schema_version"}
        record["schema_version"] = EXPORT_SCHEMA_VERSION
        records.append(record)
    return records


def default_export_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return DEFAULT_EXPORT_DIR / f"classification-provenance-{stamp}.jsonl"


def export_jsonl(
    output_path: os.PathLike[str] | str,
    *,
    db_path: os.PathLike[str] | str = DEFAULT_DB_PATH,
    include_sensitive_paths: bool = False,
    sensitive_paths: Mapping[str, str] | None = None,
) -> int:
    """Atomically export redacted records; paths require an explicit map and opt-in."""
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    records = list_records(db_path=db_path)
    fd, temp_name = tempfile.mkstemp(prefix=f".{output.name}.", dir=output.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            for record in records:
                if include_sensitive_paths and sensitive_paths:
                    source_path = sensitive_paths.get(str(record["input_fingerprint"]))
                    if source_path:
                        record["source_path"] = source_path
                handle.write(_canonical_json(record))
                handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, output)
    except Exception:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise
    return len(records)


def load_jsonl(path: os.PathLike[str] | str) -> list[dict[str, object]]:
    """Load and validate bounded, redacted provenance fixtures."""
    records: list[dict[str, object]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if len(line.encode("utf-8")) > MAX_JSONL_LINE_BYTES:
                raise ValueError(f"line {line_number} exceeds the JSONL size limit")
            if len(records) >= DEFAULT_RECORD_LIMIT:
                raise ValueError("provenance JSONL exceeds the record limit")
            payload: Any = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"line {line_number} is not a JSON object")
            if payload.get("schema_version") != EXPORT_SCHEMA_VERSION:
                raise ValueError(f"line {line_number} has an unsupported schema")
            for required in (
                "record_id",
                "input_fingerprint",
                "provider",
                "model",
                "prompt_hash",
                "schema_hash",
                "taxonomy_hash",
                "response_hash",
                "confidence",
                "final_decision",
                "classified_at",
            ):
                if required not in payload:
                    raise ValueError(f"line {line_number} is missing {required}")
            if "source_path" in payload:
                raise ValueError("replay input must be a redacted export without source_path")
            records.append({field: payload.get(field, "") for field in _EXPORT_FIELDS})
    return records


def replay_records(
    records: Iterable[Mapping[str, object]],
    evaluator: Callable[[Mapping[str, object]], str],
) -> dict[str, object]:
    """Replay redacted records through a fixture evaluator and score decisions."""
    total = 0
    matched = 0
    disagreements: list[dict[str, str]] = []
    for record in records:
        total += 1
        actual = _redact_text(evaluator(record), max_length=300)
        expected = _redact_text(record.get("final_decision", ""), max_length=300)
        if actual == expected:
            matched += 1
        elif len(disagreements) < 100:
            disagreements.append(
                {
                    "record_id": str(record.get("record_id", "")),
                    "expected": expected,
                    "actual": actual,
                }
            )
    return {
        "total": total,
        "matched": matched,
        "accuracy": (matched / total) if total else 0.0,
        "disagreements": disagreements,
    }


def replay_jsonl(
    provenance_path: os.PathLike[str] | str,
    fixture_path: os.PathLike[str] | str,
) -> dict[str, object]:
    """Replay an export against JSONL fixtures keyed by input fingerprint."""
    fixtures: dict[str, str] = {}
    with open(fixture_path, "r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            if len(fixtures) >= DEFAULT_RECORD_LIMIT:
                raise ValueError("fixture JSONL exceeds the record limit")
            if len(line.encode("utf-8")) > MAX_JSONL_LINE_BYTES:
                raise ValueError(
                    f"fixture line {line_number} exceeds the JSONL size limit"
                )
            payload: Any = json.loads(line)
            if not isinstance(payload, dict):
                raise ValueError(f"fixture line {line_number} is not a JSON object")
            fingerprint = payload.get("input_fingerprint")
            decision = payload.get("decision", payload.get("final_decision"))
            if not isinstance(fingerprint, str) or not isinstance(decision, str):
                raise ValueError(
                    f"fixture line {line_number} needs input_fingerprint and decision"
                )
            fixtures[fingerprint] = decision

    records = load_jsonl(provenance_path)
    missing = 0

    def evaluate(record: Mapping[str, object]) -> str:
        nonlocal missing
        fingerprint = str(record.get("input_fingerprint", ""))
        if fingerprint not in fixtures:
            missing += 1
            return "[missing-fixture]"
        return fixtures[fingerprint]

    result = replay_records(records, evaluate)
    result["fixture_count"] = len(fixtures)
    result["missing_fixtures"] = missing
    return result


def get_stats(
    *, db_path: os.PathLike[str] | str = DEFAULT_DB_PATH
) -> dict[str, object]:
    """Return aggregate record and correction counts without sensitive data."""
    con = _connect(db_path)
    try:
        row = con.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(CASE WHEN user_correction <> '' THEN 1 ELSE 0 END) AS corrected,
                   COUNT(DISTINCT provider || ':' || model) AS models
            FROM classification_provenance
            """
        ).fetchone()
        version_row = con.execute(
            "SELECT version FROM classification_provenance_schema "
            "WHERE schema_name='classification_provenance'"
        ).fetchone()
    finally:
        con.close()
    return {
        "schema_version": int(version_row[0]) if version_row else SCHEMA_VERSION,
        "total": int(row["total"] or 0),
        "corrected": int(row["corrected"] or 0),
        "models": int(row["models"] or 0),
    }
