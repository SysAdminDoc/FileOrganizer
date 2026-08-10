#!/usr/bin/env python3
"""NDJSON sidecar — Watch Mode.

Long-running. Polls a list of folders for new files (via mtime) and,
when a stable file appears, routes it through smart_run's per-file
classifier + planner. Runs until cancelled.

NDJSON events:
    {"event":"start","watches":[{"src":"...","dest":"..."},...]}
    {"event":"watching","watches":N,"interval":<float>}
    {"event":"detected","path":"...","src":"...","size":N}
    {"event":"item","path":"...","src":"...","dest":"...","new_path":"...",
        "category":"...","status":"moved|copied|skipped|error","message":"..."?}
    {"event":"heartbeat","ts":<float>,"checked":N,"moved":N}
    {"event":"error","code":"...","message":"..."}
"""
from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import sys
import time
import traceback
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from fileorganizer.path_safety import validate_move, validate_tree_pair
from fileorganizer.sidecar_protocol import SidecarEmitter


_PROTOCOL = SidecarEmitter("watch")
_MAX_TIMING_SECONDS = 31 * 24 * 60 * 60
_MAX_SEEN_ENTRIES = 1_000_000


class WatchConfigError(ValueError):
    """Raised when watch configuration cannot be started safely."""


@dataclass(frozen=True)
class FileIdentity:
    device: int
    inode: int
    size: int
    modified_ns: int


@dataclass(frozen=True)
class SeenEntry:
    identity: FileIdentity
    remembered_at: float


class BoundedSeenState:
    """Retention-aware LRU for unchanged files in a long-running watch."""

    def __init__(self, max_entries: int = 100_000, retention_seconds: float = 604_800) -> None:
        if max_entries < 1 or max_entries > _MAX_SEEN_ENTRIES:
            raise ValueError(f"max_entries must be between 1 and {_MAX_SEEN_ENTRIES}")
        if not math.isfinite(retention_seconds) or not 0 < retention_seconds <= _MAX_TIMING_SECONDS:
            raise ValueError("retention_seconds must be finite and greater than zero")
        self.max_entries = max_entries
        self.retention_seconds = retention_seconds
        self._entries: OrderedDict[str, SeenEntry] = OrderedDict()
        self.evicted = 0

    @staticmethod
    def _key(path: str) -> str:
        return os.path.normcase(os.path.realpath(os.path.abspath(path)))

    @staticmethod
    def _identity(path: str) -> FileIdentity | None:
        try:
            info = os.stat(path, follow_symlinks=False)
        except OSError:
            return None
        return FileIdentity(
            device=int(getattr(info, "st_dev", 0)),
            inode=int(getattr(info, "st_ino", 0)),
            size=int(info.st_size),
            modified_ns=int(getattr(info, "st_mtime_ns", int(info.st_mtime * 1_000_000_000))),
        )

    def remember(self, path: str, *, now: float | None = None) -> bool:
        identity = self._identity(path)
        if identity is None:
            return False
        key = self._key(path)
        self._entries.pop(key, None)
        self._entries[key] = SeenEntry(
            identity=identity,
            remembered_at=time.monotonic() if now is None else now,
        )
        self.prune(now=now)
        return True

    def is_unchanged(self, path: str, *, now: float | None = None) -> bool:
        current_time = time.monotonic() if now is None else now
        self.prune(now=current_time)
        entry = self._entries.get(self._key(path))
        identity = self._identity(path)
        return entry is not None and identity is not None and entry.identity == identity

    def prune(self, *, now: float | None = None) -> None:
        current_time = time.monotonic() if now is None else now
        expired = [
            key for key, entry in self._entries.items()
            if current_time - entry.remembered_at > self.retention_seconds
        ]
        for key in expired:
            self._entries.pop(key, None)
            self.evicted += 1
        while len(self._entries) > self.max_entries:
            self._entries.popitem(last=False)
            self.evicted += 1

    def __len__(self) -> int:
        return len(self._entries)


def _emit(obj: dict) -> None:
    _PROTOCOL.emit(obj)


def _stable_size(path: str, settle: float) -> bool:
    """Wait a moment, re-check size; if it didn't change, the file's done writing."""
    try:
        s1 = os.path.getsize(path)
        time.sleep(settle)
        s2 = os.path.getsize(path)
        return s1 == s2 and s1 > 0
    except OSError:
        return False


def _bounded_float(
    value: Any,
    name: str,
    *,
    minimum: float = 0.0,
    maximum: float = _MAX_TIMING_SECONDS,
) -> float:
    if isinstance(value, bool):
        raise WatchConfigError(f"{name} must be a number")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WatchConfigError(f"{name} must be a number") from exc
    if not math.isfinite(number) or number < minimum or number > maximum:
        raise WatchConfigError(
            f"{name} must be finite and between {minimum:g} and {maximum:g}"
        )
    return number


def _bounded_int(value: Any, name: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool):
        raise WatchConfigError(f"{name} must be an integer")
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WatchConfigError(f"{name} must be an integer") from exc
    if str(value).strip() not in {str(number), f"+{number}"}:
        raise WatchConfigError(f"{name} must be an integer")
    if number < minimum or number > maximum:
        raise WatchConfigError(f"{name} must be between {minimum} and {maximum}")
    return number


def load_watches(
    raw: str,
    *,
    default_settle: float,
    seen_limit: int,
    seen_retention: float,
) -> list[dict[str, Any]]:
    try:
        decoded = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise WatchConfigError(f"--watches must be a JSON array: {exc}") from exc
    if not isinstance(decoded, list):
        raise WatchConfigError("--watches must decode to a JSON array")
    if not decoded:
        raise WatchConfigError("--watches must contain at least one watch")

    watches: list[dict[str, Any]] = []
    for index, value in enumerate(decoded):
        if not isinstance(value, dict):
            raise WatchConfigError(f"watch[{index}] must be a JSON object")
        src = value.get("src")
        dest = value.get("dest")
        if not isinstance(src, str) or not src.strip():
            raise WatchConfigError(f"watch[{index}].src must be a nonempty string")
        if not isinstance(dest, str) or not dest.strip():
            raise WatchConfigError(f"watch[{index}].dest must be a nonempty string")
        copy = value.get("copy", False)
        if not isinstance(copy, bool):
            raise WatchConfigError(f"watch[{index}].copy must be true or false")
        settle = _bounded_float(
            value.get("settle", default_settle),
            f"watch[{index}].settle",
        )
        if not os.path.isdir(src):
            raise WatchConfigError(f"watch[{index}].src is not an existing folder: {src}")
        try:
            src_real, dst_real = validate_tree_pair(src, dest)
        except Exception as exc:
            raise WatchConfigError(f"watch[{index}] has unsafe roots: {exc}") from exc
        watches.append({
            "src": src_real,
            "dest": dst_real,
            "copy": copy,
            "settle": settle,
            "seen": BoundedSeenState(seen_limit, seen_retention),
        })
    return watches


def main(argv: list[str] | None = None) -> int:
    _PROTOCOL.reset()
    parser = argparse.ArgumentParser(description="NDJSON watch-mode dispatcher")
    parser.add_argument("--watches", required=True,
                        help='JSON array of {"src":"...","dest":"...","copy":<bool>}')
    parser.add_argument("--interval", default="2.0",
                        help="Seconds between scans.")
    parser.add_argument("--settle", default="1.5",
                        help="Seconds to wait for a file to finish writing before acting.")
    parser.add_argument("--heartbeat", default="10.0")
    parser.add_argument("--duration", default="0",
                        help="Optional run duration in seconds; zero runs until cancelled.")
    parser.add_argument("--seen-limit", default="100000",
                        help="Maximum remembered file identities per watch.")
    parser.add_argument("--seen-retention", default="604800",
                        help="Seconds to retain unchanged file identities.")
    args = parser.parse_args(argv)

    try:
        interval = _bounded_float(args.interval, "--interval", minimum=0.01, maximum=3600)
        settle = _bounded_float(args.settle, "--settle")
        heartbeat = _bounded_float(args.heartbeat, "--heartbeat", minimum=0.01)
        duration = _bounded_float(args.duration, "--duration")
        seen_limit = _bounded_int(
            args.seen_limit,
            "--seen-limit",
            minimum=1,
            maximum=_MAX_SEEN_ENTRIES,
        )
        seen_retention = _bounded_float(
            args.seen_retention,
            "--seen-retention",
            minimum=0.01,
        )
        watches = load_watches(
            args.watches,
            default_settle=settle,
            seen_limit=seen_limit,
            seen_retention=seen_retention,
        )
    except WatchConfigError as exc:
        _emit({"event": "error", "code": "invalid_watch_config",
               "message": str(exc)})
        return 2

    # Pre-populate `seen` with current contents so we don't replay old files.
    for w in watches:
        for dirpath, _, filenames in os.walk(w["src"]):
            for f in filenames:
                w["seen"].remember(os.path.join(dirpath, f))

    # Bring smart_run's planner into scope to reuse classifier/planner.
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        from smart_run import _plan_one, _resolve_collision
    except ImportError as exc:
        _emit({"event": "error", "code": "missing_dispatcher",
               "message": f"Could not import smart_run: {exc}"})
        return 4

    _emit({"event": "start",
           "watches": [{"src": w["src"], "dest": w["dest"]} for w in watches]})
    _emit({"event": "watching", "watches": len(watches), "interval": interval,
           "seen_limit": seen_limit, "seen_retention": seen_retention})

    last_heartbeat = time.monotonic()
    started_at = last_heartbeat
    checked = 0
    moved = 0

    try:
        while True:
            for w in watches:
                for dirpath, _, filenames in os.walk(w["src"]):
                    for f in filenames:
                        path = os.path.join(dirpath, f)
                        checked += 1
                        if w["seen"].is_unchanged(path):
                            continue
                        # Wait for the file to finish writing.
                        if not _stable_size(path, w["settle"]):
                            continue
                        try:
                            _emit({"event": "detected", "path": path,
                                   "src": w["src"],
                                   "size": os.path.getsize(path)})
                            cat, target = _plan_one(path, w["dest"])
                            target_unique = _resolve_collision(target)
                            validate_move(
                                path,
                                target_unique,
                                source_root=w["src"],
                                dest_root=w["dest"],
                            )
                            os.makedirs(os.path.dirname(target_unique), exist_ok=True)
                            if w["copy"]:
                                shutil.copy2(path, target_unique)
                                status = "copied"
                            else:
                                shutil.move(path, target_unique)
                                status = "moved"
                            moved += 1
                            if w["copy"]:
                                w["seen"].remember(path)
                            _emit({"event": "item", "path": path,
                                   "src": w["src"], "dest": w["dest"],
                                   "new_path": target_unique,
                                   "category": cat, "status": status})
                        except Exception as exc:
                            _emit({"event": "item", "path": path,
                                   "src": w["src"], "dest": w["dest"],
                                   "new_path": "", "category": "other",
                                   "status": "error",
                                   "message": f"{type(exc).__name__}: {exc}"})

            now = time.monotonic()
            if now - last_heartbeat >= heartbeat:
                last_heartbeat = now
                _emit({"event": "heartbeat", "ts": time.time(),
                       "checked": checked, "moved": moved,
                       "seen_entries": sum(len(w["seen"]) for w in watches),
                       "seen_evicted": sum(w["seen"].evicted for w in watches)})

            if duration and now - started_at >= duration:
                _emit({"event": "complete", "total": checked, "moved": moved})
                return 0

            time.sleep(interval)

    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled", "message": "Watch stopped."})
        return 130


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled", "message": "Watch stopped."})
        raise SystemExit(130)
    except Exception as exc:
        _emit({"event": "error", "code": "crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        raise SystemExit(1)
