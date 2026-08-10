from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from fileorganizer import classification_provenance as provenance


def _record(db_path: Path, source: Path | str = "C:\\Private\\Asset") -> dict[str, object]:
    return provenance.record_classification(
        source,
        provider="deepseek",
        model="deepseek-v4-flash",
        prompt="Classify C:\\Private\\Asset with api_key=sk-supersecret123",
        taxonomy=["Motion Graphics", "_Review"],
        response={
            "category": "Motion Graphics",
            "confidence": 88,
            "notes": "Bearer tokenvalue123456",
        },
        response_id="response-123",
        confidence=88,
        suggested_decision="Motion Graphics",
        db_path=db_path,
    )


def test_records_survive_restart_and_export_only_hashes(tmp_path: Path):
    db_path = tmp_path / "provenance.db"
    descriptor = _record(db_path)

    records = provenance.list_records(db_path=db_path)
    assert records[0]["record_id"] == descriptor["record_id"]
    assert records[0]["final_decision"] == "Motion Graphics"

    output = tmp_path / "export.jsonl"
    assert provenance.export_jsonl(output, db_path=db_path) == 1
    exported = output.read_text(encoding="utf-8")
    payload = json.loads(exported)
    assert payload["input_fingerprint"].startswith("opaque-sha256:")
    assert len(payload["prompt_hash"]) == 64
    assert len(payload["response_hash"]) == 64
    assert "C:\\Private" not in exported
    assert "sk-supersecret123" not in exported
    assert "tokenvalue123456" not in exported
    assert "prompt" not in payload
    assert "response" not in payload
    database_bytes = db_path.read_bytes()
    assert b"C:\\Private" not in database_bytes
    assert b"sk-supersecret123" not in database_bytes


def test_explicit_path_export_requires_both_opt_in_and_mapping(tmp_path: Path):
    db_path = tmp_path / "provenance.db"
    descriptor = _record(db_path)
    fingerprint = str(descriptor["input_fingerprint"])
    path_map = {fingerprint: "C:\\Private\\Asset"}

    redacted = tmp_path / "redacted.jsonl"
    provenance.export_jsonl(
        redacted,
        db_path=db_path,
        include_sensitive_paths=False,
        sensitive_paths=path_map,
    )
    assert "source_path" not in json.loads(redacted.read_text(encoding="utf-8"))

    explicit = tmp_path / "explicit.jsonl"
    provenance.export_jsonl(
        explicit,
        db_path=db_path,
        include_sensitive_paths=True,
        sensitive_paths=path_map,
    )
    assert json.loads(explicit.read_text(encoding="utf-8"))["source_path"] == path_map[fingerprint]


def test_user_correction_updates_final_decision(tmp_path: Path):
    db_path = tmp_path / "provenance.db"
    descriptor = _record(db_path)

    updated = provenance.record_correction(
        record_id=str(descriptor["record_id"]),
        corrected_decision="After Effects - Intro & Opener",
        db_path=db_path,
    )

    assert updated == 1
    record = provenance.list_records(db_path=db_path)[0]
    assert record["user_correction"] == "After Effects - Intro & Opener"
    assert record["final_decision"] == "After Effects - Intro & Opener"
    assert record["corrected_at"]


def test_v1_schema_is_migrated_without_losing_records(tmp_path: Path):
    db_path = tmp_path / "legacy.db"
    con = sqlite3.connect(db_path)
    con.executescript(
        """
        CREATE TABLE classification_provenance (
            record_id TEXT PRIMARY KEY,
            input_fingerprint TEXT NOT NULL,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            prompt_hash TEXT NOT NULL,
            response_hash TEXT NOT NULL,
            confidence INTEGER NOT NULL,
            suggested_decision TEXT NOT NULL,
            classified_at TEXT NOT NULL
        );
        INSERT INTO classification_provenance VALUES (
            'cls-old', 'input-old', 'deepseek', 'old-model', 'prompt-old',
            'response-old', 70, 'Old Category', '2025-01-01T00:00:00+00:00'
        );
        CREATE TABLE classification_provenance_schema (
            schema_name TEXT PRIMARY KEY,
            version INTEGER NOT NULL
        );
        INSERT INTO classification_provenance_schema VALUES (
            'classification_provenance', 1
        );
        """
    )
    con.commit()
    con.close()

    stats = provenance.get_stats(db_path=db_path)
    records = provenance.list_records(db_path=db_path)

    assert stats["schema_version"] == provenance.SCHEMA_VERSION
    assert stats["total"] == 1
    assert records[0]["record_id"] == "cls-old"
    assert records[0]["final_decision"] == "Old Category"


def test_replay_scores_fixture_decisions(tmp_path: Path):
    db_path = tmp_path / "provenance.db"
    _record(db_path)
    exported = tmp_path / "records.jsonl"
    provenance.export_jsonl(exported, db_path=db_path)
    record = json.loads(exported.read_text(encoding="utf-8"))
    fixtures = tmp_path / "fixtures.jsonl"
    fixtures.write_text(
        json.dumps(
            {
                "input_fingerprint": record["input_fingerprint"],
                "decision": "Motion Graphics",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = provenance.replay_jsonl(exported, fixtures)

    assert result["total"] == 1
    assert result["matched"] == 1
    assert result["accuracy"] == 1.0
    assert result["missing_fixtures"] == 0


def test_replay_rejects_sensitive_path_exports(tmp_path: Path):
    path = tmp_path / "records.jsonl"
    payload: dict[str, object] = {
        field: "value" for field in provenance._EXPORT_FIELDS
    }
    payload.update(
        {
            "schema_version": 1,
            "confidence": 50,
            "source_path": "C:\\Private\\Asset",
        }
    )
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")

    with pytest.raises(ValueError, match="redacted export"):
        provenance.load_jsonl(path)


def test_record_limit_prunes_oldest_rows(tmp_path: Path):
    db_path = tmp_path / "provenance.db"
    for index in range(4):
        provenance.record_classification(
            {"index": index},
            provider="fixture",
            model="v1",
            prompt=f"prompt-{index}",
            taxonomy=["A"],
            response={"category": "A", "index": index},
            confidence=90,
            suggested_decision="A",
            db_path=db_path,
            record_limit=2,
        )

    assert provenance.get_stats(db_path=db_path)["total"] == 2
