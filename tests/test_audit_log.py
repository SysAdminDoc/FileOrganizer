from __future__ import annotations

import json

from fileorganizer.audit_log import AuditLogger, trace_context


def test_audit_logger_writes_bounded_structured_event(tmp_path):
    path = tmp_path / "logs" / "audit.jsonl"
    logger = AuditLogger(path)
    logger.configure(intercept_standard=False)

    with trace_context("trace-123"):
        logger.event(
            "move",
            "Move completed",
            source_path="C:/Inbox/poster.psd",
            dest_path="D:/Library/Print/poster.psd",
            classification="Print - Flyers & Posters",
            confidence=94,
            exception="api_key=secret-value; file=private.psd",
            status="moved",
            run_id="run-1",
        )

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["trace_id"] == "trace-123"
    assert record["operation"] == "move"
    assert record["source_path"].endswith("poster.psd")
    assert record["confidence"] == 94
    assert record["status"] == "moved"
    assert "secret-value" not in json.dumps(record)
    assert "api_key=<redacted>" in record["exception"]


def test_audit_logger_rotates_oversized_log(tmp_path, monkeypatch):
    import fileorganizer.audit_log as audit_log

    monkeypatch.setattr(audit_log, "MAX_LOG_BYTES", 300)
    path = tmp_path / "audit.jsonl"
    logger = AuditLogger(path)
    logger.configure(intercept_standard=False)
    for index in range(8):
        logger.event("classify", f"classification {index}", count=index)

    assert path.exists()
    assert path.with_name("audit.jsonl.1").exists()
