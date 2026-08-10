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
import os
import sqlite3
import sys
import time
import traceback

from fileorganizer.sidecar_protocol import SidecarEmitter
from fileorganizer.review_store import ReviewStore


_PROTOCOL = SidecarEmitter("cleanup")


def _emit(obj: dict) -> None:
    _PROTOCOL.emit(obj)


def _emit_saved_review(store: ReviewStore, scan_id: str) -> int:
    try:
        scan = store.get_scan(scan_id)
        if scan["status"] == "running":
            store.finish_scan(scan_id, "interrupted", total_size=int(scan["total_size"]))
        scan = store.get_scan(scan_id, revalidate=True)
    except KeyError as exc:
        _emit({"event": "error", "code": "review_not_found", "message": str(exc)})
        return 2
    if scan["kind"] != "cleanup":
        _emit({"event": "error", "code": "wrong_review_kind",
               "message": "That scan ID does not contain cleanup results."})
        return 2
    _emit({"event": "review", "scan_id": scan_id, "status": scan["status"],
           "root": scan["root"], "mode": scan["mode"],
           "truncated": scan["truncated"]})
    _emit({"event": "start", "scanner": scan["mode"], "root": scan["root"],
           "resumed": True})
    total_size = 0
    validation: dict[str, int] = {}
    for entry in scan["entries"]:
        size = int(entry["size"])
        total_size += size
        status = str(entry["validation_status"])
        validation[status] = validation.get(status, 0) + 1
        _emit({"event": "item", "entry_id": entry["id"], "path": entry["path"],
               "size": size, "reason": entry["reason"], "category": entry["category"],
               "modified": entry["mtime_ns"] / 1_000_000_000,
               "decision": entry["decision"], "validation_status": status,
               "validation_reason": entry["validation_reason"]})
    _emit({"event": "complete", "total_count": len(scan["entries"]),
           "total_size": total_size, "validation": validation, "resumed": True,
           "review_truncated": scan["truncated"]})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON cleanup-scanner runner")
    parser.add_argument("--scanner", choices=[
        "empty_folders", "empty_files", "temp_files",
        "broken_files", "big_files", "old_downloads",
    ])
    parser.add_argument("--root", help="Folder to scan")
    parser.add_argument("--review-db", help=argparse.SUPPRESS)
    parser.add_argument("--resume-scan", metavar="SCAN_ID")
    parser.add_argument("--export-scan", metavar="SCAN_ID")
    parser.add_argument("--import-review", metavar="JSON_FILE")
    parser.add_argument("--output", help="Destination for --export-scan")
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

    if args.export_scan or args.import_review or args.resume_scan:
        try:
            store = ReviewStore(args.review_db)
            if args.export_scan:
                if not args.output:
                    parser.error("--export-scan requires --output")
                exported = store.export_scan(args.export_scan, args.output)
                _emit({"event": "review_exported", "scan_id": args.export_scan,
                       "path": str(exported)})
                _emit({"event": "complete", "total_count": 1, "operation": "review_export"})
                return 0
            if args.import_review:
                imported_id = store.import_scan(args.import_review)
                return _emit_saved_review(store, imported_id)
            if args.resume_scan:
                return _emit_saved_review(store, args.resume_scan)
        except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
            _emit({"event": "error", "code": "review_store_error",
                   "message": f"Could not use saved review: {exc}"})
            return 2

    if not args.scanner or not args.root:
        parser.error("--scanner and --root are required for a new scan")

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root directory does not exist: {args.root}"})
        return 2

    try:
        store = ReviewStore(args.review_db)
    except (OSError, ValueError, RuntimeError, sqlite3.Error) as exc:
        _emit({"event": "error", "code": "review_store_error",
               "message": f"Could not open saved reviews: {exc}"})
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

    options = {
        "depth": args.depth, "include_logs": args.include_logs,
        "min_age_days": args.min_age_days, "check_archives": args.check_archives,
        "min_size_mb": args.min_size_mb, "limit": args.limit, "days_old": args.days_old,
    }
    try:
        scan_id = store.create_scan("cleanup", args.root, args.scanner, options)
    except (OSError, ValueError, sqlite3.Error) as exc:
        _emit({"event": "error", "code": "review_store_error",
               "message": f"Could not create saved review: {exc}"})
        return 2

    _emit({"event": "review", "scan_id": scan_id, "status": "running",
           "root": os.path.abspath(args.root), "mode": args.scanner, "truncated": False})
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
        store.append_entries(scan_id, [{
            "path": item.path,
            "size": int(item.size or 0),
            "reason": item.reason,
            "category": item.category,
            "modified": float(item.modified or 0.0),
        }])
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
                                             progress_cb=progress_cb)
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

        store.finish_scan(scan_id, "complete", total_size=int(state["total_size"]))
        _emit({"event": "complete",
               "total_count": state["found"],
               "total_size": state["total_size"],
               "scan_id": scan_id})
        return 0

    except KeyboardInterrupt:
        store.finish_scan(scan_id, "cancelled", total_size=int(state["total_size"]))
        _emit({"event": "error", "code": "cancelled",
               "message": "Cancelled by user."})
        return 130
    except Exception as exc:
        store.finish_scan(scan_id, "failed", total_size=int(state["total_size"]))
        _emit({"event": "error", "code": "scanner_crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
