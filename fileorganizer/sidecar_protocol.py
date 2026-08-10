"""Versioned NDJSON protocol shared by FileOrganizer sidecars.

The WinUI shell treats stdout as a machine-readable channel.  This module
keeps every runner on the same bounded envelope while preserving each
workflow's domain-specific fields.
"""

from __future__ import annotations

import json
import math
import re
import sys
import threading
import time
from collections.abc import Mapping, Sequence
from typing import Any, TextIO

from fileorganizer.capabilities import capability_error, capability_matrix


PROTOCOL_VERSION = "1.0"
MAX_RECORD_BYTES = 1_048_576
MAX_STRING_LENGTH = 32_768
MAX_COLLECTION_ITEMS = 4_096
MAX_NESTING_DEPTH = 12

ALLOWED_EVENTS = frozenset({
    "handshake",
    "start",
    "progress",
    "item",
    "group",
    "summary",
    "file",
    "comic",
    "plan",
    "log",
    "complete",
    "error",
    "watching",
    "detected",
    "heartbeat",
    "review",
    "review_exported",
})
TERMINAL_EVENTS = frozenset({"complete", "error"})
_ERROR_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class ProtocolValidationError(ValueError):
    """Raised when an event cannot be represented safely in the protocol."""


def _bounded(value: Any, *, depth: int = 0) -> tuple[Any, bool]:
    """Return a JSON-safe, bounded copy and whether any value was truncated."""
    if depth > MAX_NESTING_DEPTH:
        return "<maximum nesting depth exceeded>", True
    if value is None or isinstance(value, (bool, int)):
        return value, False
    if isinstance(value, float):
        return (value, False) if math.isfinite(value) else (None, True)
    if isinstance(value, str):
        if len(value) <= MAX_STRING_LENGTH:
            return value, False
        return value[:MAX_STRING_LENGTH], True
    if isinstance(value, Mapping):
        out_dict: dict[str, Any] = {}
        truncated = len(value) > MAX_COLLECTION_ITEMS
        for index, (raw_key, raw_value) in enumerate(value.items()):
            if index >= MAX_COLLECTION_ITEMS:
                break
            key = str(raw_key)[:256]
            bounded, child_truncated = _bounded(raw_value, depth=depth + 1)
            out_dict[key] = bounded
            truncated = truncated or child_truncated or len(str(raw_key)) > 256
        return out_dict, truncated
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        truncated = len(value) > MAX_COLLECTION_ITEMS
        out_list: list[Any] = []
        for child in value[:MAX_COLLECTION_ITEMS]:
            bounded, child_truncated = _bounded(child, depth=depth + 1)
            out_list.append(bounded)
            truncated = truncated or child_truncated
        return out_list, truncated
    text = str(value)
    return text[:MAX_STRING_LENGTH], len(text) > MAX_STRING_LENGTH


def _nonnegative_int(value: Any, default: int = 0) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError, OverflowError):
        return default


def _normalise_event(
    event: Mapping[str, Any],
    *,
    expected_total: int | None,
) -> tuple[dict[str, Any], bool]:
    bounded, truncated = _bounded(event)
    if not isinstance(bounded, dict):
        raise ProtocolValidationError("Protocol event must be an object.")

    event_name = bounded.get("event")
    if not isinstance(event_name, str) or not event_name:
        raise ProtocolValidationError("Protocol event requires a nonempty string 'event'.")
    if event_name not in ALLOWED_EVENTS or event_name == "handshake":
        raise ProtocolValidationError(f"Unknown protocol event: {event_name!r}.")

    if event_name == "progress":
        current = _nonnegative_int(
            bounded.get("current", bounded.get("scanned", bounded.get("processed", 0)))
        )
        total_value = bounded.get("total", expected_total)
        total = _nonnegative_int(total_value) if total_value is not None else None
        percent_value = bounded.get("percent")
        try:
            percent = float(percent_value) if percent_value is not None else None
        except (TypeError, ValueError, OverflowError):
            percent = None
        if percent is None or not math.isfinite(percent):
            percent = (current * 100.0 / total) if total else 0.0
        bounded["current"] = current
        bounded["total"] = total
        bounded["percent"] = min(100.0, max(0.0, percent))
        stage = bounded.get("stage", "working")
        bounded["stage"] = str(stage or "working")[:512]

    if event_name in {"item", "file", "comic", "detected"}:
        path = bounded.get("path")
        if not isinstance(path, str) or not path:
            raise ProtocolValidationError(f"{event_name} event requires a nonempty path.")

    if event_name == "review":
        scan_id = bounded.get("scan_id")
        if not isinstance(scan_id, str) or not scan_id:
            raise ProtocolValidationError("review event requires a nonempty scan_id.")

    if event_name == "review_exported":
        scan_id = bounded.get("scan_id")
        path = bounded.get("path")
        if not isinstance(scan_id, str) or not scan_id or not isinstance(path, str) or not path:
            raise ProtocolValidationError(
                "review_exported event requires nonempty scan_id and path fields."
            )

    if event_name == "log":
        bounded["level"] = str(bounded.get("level") or "info")[:32].lower()
        bounded["message"] = str(bounded.get("message") or "")[:MAX_STRING_LENGTH]

    if event_name == "error":
        code = str(bounded.get("code") or "unknown_error").lower()
        if not _ERROR_CODE_RE.fullmatch(code):
            code = "invalid_error_code"
        bounded["code"] = code
        bounded["message"] = str(bounded.get("message") or "Unknown sidecar error.")[
            :MAX_STRING_LENGTH
        ]
        bounded["terminal"] = bool(bounded.get("terminal", True))
        bounded["status"] = "cancelled" if code == "cancelled" else "error"

    if event_name == "complete":
        total = bounded.get("total")
        if total is None:
            for key in ("total_count", "total_files", "scanned"):
                if key in bounded:
                    total = bounded[key]
                    break
        if total is None:
            total = expected_total
        bounded["total"] = _nonnegative_int(total) if total is not None else 0
        bounded["terminal"] = True
        bounded["status"] = "ok"

    return bounded, truncated


class SidecarEmitter:
    """Stateful, thread-safe writer for one sidecar process."""

    def __init__(self, sidecar: str, stream: TextIO | None = None) -> None:
        self.sidecar = sidecar
        self.stream = stream
        self._lock = threading.RLock()
        self._sequence = 0
        self._handshake_emitted = False
        self._terminal_emitted = False
        self._expected_total: int | None = None

    def _write(self, record: Mapping[str, Any]) -> None:
        encoded = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > MAX_RECORD_BYTES:
            raise ProtocolValidationError(
                f"Encoded event exceeds {MAX_RECORD_BYTES} bytes."
            )
        stream = self.stream or sys.stdout
        stream.write(encoded + "\n")
        stream.flush()

    def reset(self) -> None:
        """Begin a fresh stream when a reusable in-process runner starts again."""
        with self._lock:
            self._sequence = 0
            self._handshake_emitted = False
            self._terminal_emitted = False
            self._expected_total = None

    def _handshake(self) -> None:
        if self._handshake_emitted:
            return
        self._write({
            "event": "handshake",
            "protocol_version": PROTOCOL_VERSION,
            "sequence": 0,
            "sidecar": self.sidecar,
            "timestamp": time.time(),
            "capabilities": {
                "events": sorted(ALLOWED_EVENTS - {"handshake"}),
                "cancellation": "terminal_error",
                "bounded_records": True,
                "max_record_bytes": MAX_RECORD_BYTES,
                "health_schema_version": 1,
                "capability_matrix": capability_matrix(self.sidecar),
            },
        })
        self._handshake_emitted = True

    def _diagnostic(self, code: str, message: str) -> None:
        if self._terminal_emitted:
            return
        self._sequence += 1
        self._write({
            "event": "log",
            "protocol_version": PROTOCOL_VERSION,
            "sequence": self._sequence,
            "sidecar": self.sidecar,
            "timestamp": time.time(),
            "level": "warning",
            "code": code,
            "message": message[:MAX_STRING_LENGTH],
        })

    def emit(self, event: Mapping[str, Any]) -> None:
        """Validate and write an event; isolate invalid caller records as logs."""
        with self._lock:
            self._handshake()
            if self._terminal_emitted:
                return
            try:
                normalised, truncated = _normalise_event(
                    event,
                    expected_total=self._expected_total,
                )
                if normalised["event"] == "start":
                    for key in ("total", "files_found", "candidates_found"):
                        if key in normalised:
                            self._expected_total = _nonnegative_int(normalised[key])
                            break

                self._sequence += 1
                normalised["protocol_version"] = PROTOCOL_VERSION
                normalised["sequence"] = self._sequence
                normalised["sidecar"] = self.sidecar
                normalised["timestamp"] = time.time()
                if truncated:
                    normalised["protocol_truncated"] = True
                self._write(normalised)

                is_terminal_error = (
                    normalised["event"] == "error"
                    and bool(normalised.get("terminal"))
                )
                if normalised["event"] == "complete" or is_terminal_error:
                    self._terminal_emitted = True
            except ProtocolValidationError as exc:
                self._diagnostic("invalid_event", str(exc))

    def emit_capability_error(
        self,
        capability: str,
        message: str | None = None,
    ) -> None:
        """Emit the shared terminal schema for a missing workflow capability."""
        self.emit(capability_error(self.sidecar, capability, message))


def emit_named(emitter: SidecarEmitter, event: str, data: Mapping[str, Any]) -> None:
    """Compatibility helper for sidecars that use ``emit(name, payload)``."""
    emitter.emit({"event": event, **data})
