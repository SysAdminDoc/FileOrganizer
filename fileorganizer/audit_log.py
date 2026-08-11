"""Local structured audit logging with trace propagation and redaction."""

from __future__ import annotations

import contextvars
import getpass
import json
import logging
import os
import re
import sys
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fileorganizer.config import _APP_DATA_DIR

try:
    from loguru import logger as _loguru_logger
except ImportError:  # pragma: no cover - exercised by the base test environment
    _loguru_logger = None


AUDIT_LOG_DIR = Path(_APP_DATA_DIR) / "logs"
AUDIT_LOG_FILE = AUDIT_LOG_DIR / "audit.jsonl"
MAX_EVENT_BYTES = 64 * 1024
MAX_LOG_BYTES = 10 * 1024 * 1024
MAX_ROTATED_LOGS = 3
MAX_PATH_LENGTH = 4_096
MAX_TEXT_LENGTH = 4_096

_TRACE_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "fileorganizer_audit_trace_id", default=None
)
_SESSION_TRACE_ID = uuid.uuid4().hex
_WRITE_LOCK = threading.RLock()
_SECRET_RE = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|authorization|password|secret)"
    r"\s*[:=]\s*([^\s,;]+)"
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_DETAIL_KEYS = frozenset({
    "status", "run_id", "plan_id", "plan_item_id", "source_mode", "mode",
    "count", "moved", "skipped", "errors", "scan_id", "model", "cache_hit",
})


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def _text(value: object, limit: int = MAX_TEXT_LENGTH) -> str:
    return str(value or "")[:limit]


def _redact(value: object) -> str:
    text = _text(value)
    text = _SECRET_RE.sub(lambda match: f"{match.group(1)}=<redacted>", text)
    return _BEARER_RE.sub("Bearer <redacted>", text)


def _trace_or_session(trace_id: str | None = None) -> str:
    return _text(trace_id or _TRACE_ID.get() or _SESSION_TRACE_ID, 128)


def current_trace_id() -> str:
    """Return the active trace ID, or the process session ID outside a run."""
    return _trace_or_session()


def new_trace_id() -> str:
    """Create and activate a new trace ID for an operation run."""
    trace_id = uuid.uuid4().hex
    _TRACE_ID.set(trace_id)
    return trace_id


@contextmanager
def trace_context(trace_id: str | None = None) -> Iterator[str]:
    """Temporarily propagate one trace ID through nested and async work."""
    active = _text(trace_id or uuid.uuid4().hex, 128)
    token = _TRACE_ID.set(active)
    try:
        yield active
    finally:
        _TRACE_ID.reset(token)


def _confidence(value: object) -> int | None:
    if value is None or type(value) is not int or not 0 <= value <= 100:
        return None
    return value


class _InterceptHandler(logging.Handler):
    """Forward stdlib records into the configured Loguru sinks."""

    def emit(self, record: logging.LogRecord) -> None:
        if _loguru_logger is None:
            return
        try:
            level: str | int = _loguru_logger.level(record.levelname).name
        except ValueError:
            level = record.levelno
        _loguru_logger.bind(
            _fileorganizer_audit=True,
            operation="system",
            trace_id=current_trace_id(),
            exception_text="",
        ).log(level, "{}", record.getMessage())


class AuditLogger:
    """Thread-safe JSONL audit sink with optional Loguru console integration."""

    def __init__(self, path: str | os.PathLike[str] | None = None) -> None:
        self.path = Path(path) if path is not None else AUDIT_LOG_FILE
        self._configured = False
        self._console = False
        self._loguru_sink_id: int | None = None
        self._loguru_console_id: int | None = None

    def configure(self, *, console: bool = False, intercept_standard: bool = True) -> None:
        """Create the sink and, when installed, route stdlib logging through Loguru."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._console = bool(console)
        if _loguru_logger is not None and self._loguru_sink_id is None:
            self._loguru_sink_id = _loguru_logger.add(
                self._write_loguru,
                level="INFO",
                filter=lambda record: bool(
                    record["extra"].get("_fileorganizer_audit")
                ),
                backtrace=False,
                diagnose=False,
            )
            if console:
                self._loguru_console_id = _loguru_logger.add(
                    sys.stderr,
                    level="INFO",
                    colorize=True,
                    format=(
                        "<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | "
                        "{message}\n"
                    ),
                    filter=lambda record: bool(
                        record["extra"].get("_fileorganizer_audit")
                    ),
                )
            if intercept_standard:
                root = logging.getLogger()
                root.handlers = [_InterceptHandler()]
                root.setLevel(logging.INFO)
        self._configured = True

    def _rotate(self) -> None:
        try:
            if not self.path.is_file() or self.path.stat().st_size < MAX_LOG_BYTES:
                return
            oldest = self.path.with_name(f"{self.path.name}.{MAX_ROTATED_LOGS}")
            if oldest.exists():
                oldest.unlink()
            for index in range(MAX_ROTATED_LOGS - 1, 0, -1):
                source = self.path.with_name(f"{self.path.name}.{index}")
                target = self.path.with_name(f"{self.path.name}.{index + 1}")
                if source.exists():
                    os.replace(source, target)
            os.replace(self.path, self.path.with_name(f"{self.path.name}.1"))
        except OSError:
            pass

    def _write_json(self, event: dict[str, Any]) -> None:
        encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_EVENT_BYTES:
            event["message"] = _text(event.get("message"), 1_024)
            event["exception"] = _redact(event.get("exception"))[:1_024]
            encoded = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        with _WRITE_LOCK:
            self._rotate()
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as stream:
                    stream.write(encoded + "\n")
            except OSError:
                pass

    def _write_loguru(self, message: Any) -> None:
        record = message.record
        extra = record.get("extra", {})
        self._write_json(self._event(
            level=record["level"].name,
            message=record.get("message", ""),
            operation=extra.get("operation", "system"),
            trace_id=extra.get("trace_id"),
            source_path=extra.get("source_path"),
            dest_path=extra.get("dest_path"),
            classification=extra.get("classification"),
            confidence=extra.get("confidence"),
            exception=extra.get("exception_text"),
            details=extra,
            timestamp=record["time"].astimezone(timezone.utc).isoformat(
                timespec="milliseconds"
            ).replace("+00:00", "Z"),
        ))

    def _event(
        self,
        *,
        level: str,
        message: object,
        operation: str,
        trace_id: str | None,
        source_path: object,
        dest_path: object,
        classification: object,
        confidence: object,
        exception: object,
        details: dict[str, object] | None = None,
        timestamp: str | None = None,
    ) -> dict[str, Any]:
        event: dict[str, Any] = {
            "timestamp": timestamp or _now(),
            "trace_id": _trace_or_session(trace_id),
            "level": _text(level, 32).upper(),
            "operation": _text(operation, 64) or "system",
            "user": _text(getpass.getuser(), 128),
            "source_path": _text(source_path, MAX_PATH_LENGTH),
            "dest_path": _text(dest_path, MAX_PATH_LENGTH),
            "classification": _text(classification, 256),
            "confidence": _confidence(confidence),
            "exception": _redact(exception),
            "message": _redact(message),
        }
        if details:
            for key in _DETAIL_KEYS:
                if key in details:
                    value = details[key]
                    event[key] = (
                        _text(value, 256) if isinstance(value, (str, Path)) else value
                    )
        return event

    def event(
        self,
        operation: str,
        message: str,
        *,
        level: str = "INFO",
        trace_id: str | None = None,
        source_path: object = "",
        dest_path: object = "",
        classification: object = "",
        confidence: object = None,
        exception: object = "",
        **details: object,
    ) -> str:
        """Write one bounded event and return its active trace ID."""
        if not self._configured:
            self.configure()
        active_trace = _trace_or_session(trace_id)
        if _loguru_logger is not None and self._loguru_sink_id is not None:
            extra = {
                "_fileorganizer_audit": True,
                "operation": operation,
                "trace_id": active_trace,
                "source_path": source_path,
                "dest_path": dest_path,
                "classification": classification,
                "confidence": confidence,
                "exception_text": exception,
                **{key: value for key, value in details.items() if key in _DETAIL_KEYS},
            }
            _loguru_logger.bind(**extra).log(level.upper(), "{}", message)
        else:
            self._write_json(self._event(
                level=level,
                message=message,
                operation=operation,
                trace_id=active_trace,
                source_path=source_path,
                dest_path=dest_path,
                classification=classification,
                confidence=confidence,
                exception=exception,
                details=details,
            ))
            if self._console:
                print(f"[{level.upper()}] {operation}: {message}", file=sys.stderr)
        return active_trace


_DEFAULT_LOGGER = AuditLogger()


def configure_audit(
    *,
    path: str | os.PathLike[str] | None = None,
    console: bool = False,
    intercept_standard: bool = True,
) -> AuditLogger:
    """Configure and return the process-wide audit logger."""
    global _DEFAULT_LOGGER
    if path is not None and Path(path) != _DEFAULT_LOGGER.path:
        _DEFAULT_LOGGER = AuditLogger(path)
    _DEFAULT_LOGGER.configure(
        console=console,
        intercept_standard=intercept_standard,
    )
    return _DEFAULT_LOGGER


def audit_event(operation: str, message: str, **kwargs: object) -> str:
    """Write an event using the process-wide audit logger."""
    return _DEFAULT_LOGGER.event(operation, message, **kwargs)
