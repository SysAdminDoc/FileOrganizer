#!/usr/bin/env python3
r"""fast_merge_g_to_i.py — Faster G:\Organized -> I:\Organized merge.

The supervisor's Phase 3 hits a wall on heavy-overlap categories
(Christmas, Print - Flyers & Posters, etc.) because robocopy with
/XC /XN /XO stats every source AND dest file to make merge decisions.
With 130K+ files in a Christmas dir, that's millions of HDD seeks.

This script avoids the comparison cost by working at the SUBDIRECTORY
level instead of the file level:

  For each subdir under G:\Organized\<cat>:
    - If I:\Organized\<cat>\<subdir> doesn't exist: robocopy /MOVE the whole
      subdir over in one shot (full HDD speed, no comparison overhead).
    - If it exists: leave the source on G:\ for now; fix_duplicates
      handles cross-drive collision-suffix detection in a later phase.

This is dramatically faster for overlap-heavy categories: instead of
millions of file-level decisions, we make a few hundred subdir-level
decisions (just `os.path.exists` calls).

Usage:
    python fast_merge_g_to_i.py --apply
    python fast_merge_g_to_i.py --apply --dry-run
    python fast_merge_g_to_i.py --apply --only-cat "After Effects - Christmas & Holiday"
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent
LOG_FILE = REPO / "fast_merge_log.json"

G_ROOT = Path(r"G:\Organized")
I_ROOT = Path(r"I:\Organized")


def ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def log(msg: str) -> None:
    line = f"[{ts()}] {msg}"
    safe = line.encode("cp1252", errors="replace").decode("cp1252")
    print(safe, flush=True)


def append_log(entry: dict) -> None:
    entries: list[dict] = []
    if LOG_FILE.exists():
        try:
            entries = json.loads(LOG_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            entries = []
    entries.append({"ts": ts(), **entry})
    LOG_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def _lp(p: str) -> str:
    ap = os.path.abspath(p).replace("/", "\\")
    if ap.startswith("\\\\?\\"):
        return ap
    if ap.startswith("\\\\"):
        return "\\\\?\\UNC\\" + ap[2:]
    return "\\\\?\\" + ap


def robocopy_move(src: Path, dst: Path) -> int:
    """Whole-dir robocopy /MOVE /E. Returns rc."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "robocopy", _lp(str(src)), _lp(str(dst)),
        "/MOVE", "/E", "/256", "/COPY:DAT",
        "/R:1", "/W:1",
        "/NP", "/NFL", "/NDL", "/NJH", "/NJS",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                errors="replace", timeout=12 * 3600)
        return result.returncode
    except subprocess.TimeoutExpired:
        return -1


def merge_category(cat_g: Path, cat_i: Path, dry_run: bool = False) -> dict:
    """Merge G:\Organized\<cat> into I:\Organized\<cat> at subdir granularity."""
    counts = {"moved": 0, "kept_on_g_collision": 0,
              "skipped_files": 0, "errors": 0}
    if not cat_g.exists():
        return counts

    cat_i.mkdir(parents=True, exist_ok=True)

    # Snapshot subdirs first (the loop modifies the source side)
    try:
        subdirs = [d for d in cat_g.iterdir() if d.is_dir()]
    except OSError as e:
        log(f"  iterdir fail {cat_g}: {e}")
        counts["errors"] += 1
        return counts

    files = [f for f in cat_g.iterdir() if f.is_file()]

    for sub in subdirs:
        target = cat_i / sub.name
        if target.exists():
            counts["kept_on_g_collision"] += 1
            continue
        log(f"  -> moving {sub.name!r}")
        if dry_run:
            counts["moved"] += 1
            continue
        rc = robocopy_move(sub, target)
        if rc < 0:
            log(f"     TIMEOUT")
            counts["errors"] += 1
            continue
        if rc >= 8:
            log(f"     robocopy rc={rc}")
            counts["errors"] += 1
            continue
        counts["moved"] += 1

    # Move loose files at category root
    for f in files:
        target = cat_i / f.name
        if target.exists():
            counts["skipped_files"] += 1
            continue
        log(f"  -> moving file {f.name!r}")
        if dry_run:
            counts["moved"] += 1
            continue
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Cross-drive: shutil.move = copy + delete
            shutil.move(str(f), str(target))
            counts["moved"] += 1
        except Exception as e:
            log(f"     fail: {e}")
            counts["errors"] += 1

    # Try removing the now-empty G:\<cat> dir (only if NO collisions stayed)
    if counts["kept_on_g_collision"] == 0 and counts["skipped_files"] == 0:
        try:
            if cat_g.exists() and not list(cat_g.iterdir()):
                cat_g.rmdir()
        except OSError:
            pass

    return counts


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-cat", help="Process only this category name")
    ap.add_argument("--start-from-cat",
                    help="Skip categories alphabetically before this one")
    args = ap.parse_args()

    if not args.apply:
        ap.print_help()
        return

    if not G_ROOT.exists():
        log(f"{G_ROOT} not found, nothing to do")
        return

    cats = sorted(c for c in G_ROOT.iterdir() if c.is_dir())
    if args.only_cat:
        cats = [c for c in cats if c.name == args.only_cat]
    elif args.start_from_cat:
        cats = [c for c in cats if c.name >= args.start_from_cat]

    log(f"Processing {len(cats)} categories")
    total_moved = total_collisions = total_skipped = total_errors = 0
    for cat_g in cats:
        cat_i = I_ROOT / cat_g.name
        log(f"=== {cat_g.name} ===")
        counts = merge_category(cat_g, cat_i, dry_run=args.dry_run)
        log(f"  moved={counts['moved']} collisions={counts['kept_on_g_collision']} "
            f"skipped_files={counts['skipped_files']} errors={counts['errors']}")
        total_moved += counts["moved"]
        total_collisions += counts["kept_on_g_collision"]
        total_skipped += counts["skipped_files"]
        total_errors += counts["errors"]
        append_log({
            "category": cat_g.name, **counts,
        })

    # Try removing G:\Organized root if empty
    try:
        if G_ROOT.exists() and not list(G_ROOT.iterdir()):
            G_ROOT.rmdir()
            log(f"{G_ROOT} removed (empty)")
    except OSError:
        pass

    log(f"\nDONE: {total_moved} subdirs moved, {total_collisions} collisions, "
        f"{total_skipped} files skipped, {total_errors} errors")


if __name__ == "__main__":
    main()
