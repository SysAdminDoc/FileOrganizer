#!/usr/bin/env python3
"""NDJSON sidecar wrapper around fileorganizer.cleanup scanners.

Emits one JSON-per-line on stdout. Event shapes:

    {"event":"start","scanner":"<name>","root":"<path>"}
    {"event":"progress","scanned":<int>,"found":<int>,"stage":"<msg>"}
    {"event":"item","path":"<str>","size":<int>,"reason":"<str>","category":"<str>","modified":<float>}
    {"event":"complete","total_count":<int>,"total_size":<int>}
    {"event":"error","code":"<short_tag>","message":"<str>"}

Designed to be driven by FileOrganizer.UI's PythonRunner.RunScriptNdjsonAsync.
Scanners: empty_folders, empty_files, temp_files, broken_files, big_files,
old_downloads.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON cleanup-scanner runner")
    parser.add_argument("--scanner", required=True, choices=[
        "empty_folders", "empty_files", "temp_files",
        "broken_files", "big_files", "old_downloads",
    ])
    parser.add_argument("--root", required=True, help="Folder to scan")
    parser.add_argument("--depth", type=int, default=99)
    parser.add_argument("--include-logs", action="store_true",
                        help="temp_files: also flag .log files")
    parser.add_argument("--min-age-days", type=int, default=0,
                        help="temp_files: only flag files older than N days")
    parser.add_argument("--check-archives", action="store_true",
                        help="broken_files: also validate ZIP/TAR integrity")
    parser.add_argument("--min-size-mb", type=float, default=100.0,
                        help="big_files: minimum size in MB")
    parser.add_argument("--limit", type=int, default=500,
                        help="big_files: cap on result count")
    parser.add_argument("--days-old", type=int, default=90,
                        help="old_downloads: not-accessed-in-N-days threshold")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root directory does not exist: {args.root}"})
        return 2

    # Make fileorganizer importable when invoked from the repo root.
    repo_root = os.path.dirname(os.path.abspath(__file__))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)

    try:
        from fileorganizer import cleanup
    except Exception as exc:
        _emit({"event": "error", "code": "import_failed",
               "message": f"Could not import fileorganizer.cleanup: {exc}"})
        return 3

    _emit({"event": "start", "scanner": args.scanner, "root": args.root})

    state = {"scanned": 0, "found": 0, "total_size": 0, "last_progress": 0.0}

    def progress_cb(msg: str) -> None:
        state["scanned"] += 1
        now = time.monotonic()
        # Throttle progress events to ~10/sec to avoid drowning the UI.
        if now - state["last_progress"] >= 0.1:
            state["last_progress"] = now
            _emit({"event": "progress",
                   "scanned": state["scanned"],
                   "found": state["found"],
                   "stage": msg[:200]})

    def item_cb(item) -> None:
        state["found"] += 1
        state["total_size"] += getattr(item, "size", 0) or 0
        _emit({"event": "item",
               "path": item.path,
               "size": int(item.size or 0),
               "reason": item.reason,
               "category": item.category,
               "modified": float(item.modified or 0.0)})

    try:
        scanner_name = args.scanner
        if scanner_name == "empty_folders":
            cleanup.scan_empty_folders(args.root,
                                       progress_cb=progress_cb,
                                       item_cb=item_cb)
        elif scanner_name == "empty_files":
            cleanup.scan_empty_files(args.root, depth=args.depth,
                                     progress_cb=progress_cb,
                                     item_cb=item_cb)
        elif scanner_name == "temp_files":
            cleanup.scan_temp_files(args.root, depth=args.depth,
                                    include_logs=args.include_logs,
                                    min_age_days=args.min_age_days,
                                    progress_cb=progress_cb,
                                    item_cb=item_cb)
        elif scanner_name == "broken_files":
            cleanup.scan_broken_files(args.root, depth=args.depth,
                                      check_archives=args.check_archives,
                                      progress_cb=progress_cb,
                                      item_cb=item_cb)
        elif scanner_name == "big_files":
            # scan_big_files sorts + truncates internally and returns the final
            # list. Stream items as the scanner discovers them via item_cb, but
            # the final emission below is the authoritative ordered slice.
            results = cleanup.scan_big_files(args.root,
                                             min_size_mb=args.min_size_mb,
                                             depth=args.depth,
                                             limit=args.limit,
                                             progress_cb=progress_cb,
                                             item_cb=None)
            # Re-emit the truncated, size-sorted final list so the UI shows
            # only the top-N largest in order.
            state["found"] = 0
            state["total_size"] = 0
            for it in results:
                item_cb(it)
        elif scanner_name == "old_downloads":
            cleanup.scan_old_downloads(args.root, days_old=args.days_old,
                                       progress_cb=progress_cb,
                                       item_cb=item_cb)
        else:
            _emit({"event": "error", "code": "unknown_scanner",
                   "message": f"Unknown scanner: {scanner_name}"})
            return 4

        _emit({"event": "complete",
               "total_count": state["found"],
               "total_size": state["total_size"]})
        return 0

    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled",
               "message": "Cancelled by user."})
        return 130
    except Exception as exc:
        _emit({"event": "error", "code": "scanner_crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
