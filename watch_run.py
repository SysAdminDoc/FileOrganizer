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
import os
import shutil
import sys
import time
import traceback


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _stable_size(path: str, settle: float) -> bool:
    """Wait a moment, re-check size; if it didn't change, the file's done writing."""
    try:
        s1 = os.path.getsize(path)
        time.sleep(settle)
        s2 = os.path.getsize(path)
        return s1 == s2 and s1 > 0
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON watch-mode dispatcher")
    parser.add_argument("--watches", required=True,
                        help='JSON array of {"src":"...","dest":"...","copy":<bool>}')
    parser.add_argument("--interval", type=float, default=2.0,
                        help="Seconds between scans.")
    parser.add_argument("--settle", type=float, default=1.5,
                        help="Seconds to wait for a file to finish writing before acting.")
    parser.add_argument("--heartbeat", type=float, default=10.0)
    args = parser.parse_args()

    try:
        watches_in = json.loads(args.watches)
    except json.JSONDecodeError as exc:
        _emit({"event": "error", "code": "bad_watches",
               "message": f"--watches must be valid JSON: {exc}"})
        return 2

    watches: list[dict] = []
    for w in watches_in:
        src = w.get("src", "")
        dst = w.get("dest", "")
        if not (src and dst and os.path.isdir(src)):
            _emit({"event": "error", "code": "bad_watch",
                   "message": f"Skipping watch with missing/invalid src: {w}"})
            continue
        watches.append({"src": os.path.abspath(src),
                        "dest": os.path.abspath(dst),
                        "copy": bool(w.get("copy", False)),
                        "seen": set()})

    if not watches:
        _emit({"event": "error", "code": "no_watches",
               "message": "No valid watches; exiting."})
        return 3

    # Pre-populate `seen` with current contents so we don't replay old files.
    for w in watches:
        for dirpath, _, filenames in os.walk(w["src"]):
            for f in filenames:
                w["seen"].add(os.path.join(dirpath, f))

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
    _emit({"event": "watching", "watches": len(watches), "interval": args.interval})

    last_heartbeat = time.monotonic()
    checked = 0
    moved = 0

    try:
        while True:
            for w in watches:
                for dirpath, _, filenames in os.walk(w["src"]):
                    for f in filenames:
                        path = os.path.join(dirpath, f)
                        checked += 1
                        if path in w["seen"]:
                            continue
                        # Wait for the file to finish writing.
                        if not _stable_size(path, args.settle):
                            continue
                        try:
                            _emit({"event": "detected", "path": path,
                                   "src": w["src"],
                                   "size": os.path.getsize(path)})
                            cat, target = _plan_one(path, w["dest"])
                            target_unique = _resolve_collision(target)
                            os.makedirs(os.path.dirname(target_unique), exist_ok=True)
                            if w["copy"]:
                                shutil.copy2(path, target_unique)
                                status = "copied"
                            else:
                                shutil.move(path, target_unique)
                                status = "moved"
                            moved += 1
                            w["seen"].add(path)
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
            if now - last_heartbeat >= args.heartbeat:
                last_heartbeat = now
                _emit({"event": "heartbeat", "ts": time.time(),
                       "checked": checked, "moved": moved})

            time.sleep(args.interval)

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
