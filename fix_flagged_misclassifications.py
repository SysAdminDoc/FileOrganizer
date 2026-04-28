#!/usr/bin/env python3
r"""fix_flagged_misclassifications.py — Move four I:\Unorganized thematic
collection folders that the AE pipeline mis-routed.

These are not single-item AE templates; they are THEMATIC collection folders
holding mixed content. The original AE classify pass picked the wrong
canonical category for each. Move them under a more accurate canonical
category, journal each correction.

  Wedding              -> After Effects - Wedding & Romance  (was Christmas & Holiday)
  Summer & Tropical    -> Stock Footage - Nature & Landscape (was Christmas & Holiday)
  TV & Broadcast       -> After Effects - News & Broadcast   (was Plugins & Extensions)
  Text Effects & Styles -> Photoshop - Styles & Layer Effects (was Plugins & Extensions)

Usage:
    python fix_flagged_misclassifications.py --scan
    python fix_flagged_misclassifications.py --apply [--dry-run]
"""
import argparse
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
from organize_run import _lp, robust_move  # noqa: E402

DB = REPO / "organize_moves.db"

# (current_path, target_canonical_category, clean_name)
# At apply time the items had landed on G:\Organized (not I:\ as the original
# session handoff suggested); confirmed by `os.path.exists` probe.
FIXES = [
    (Path(r"I:\Organized\After Effects - Christmas & Holiday\Wedding"),
     "After Effects - Wedding & Romance", "Wedding"),
    (Path(r"G:\Organized\After Effects - Christmas & Holiday\Summer & Tropical"),
     "Stock Footage - Nature & Landscape", "Summer & Tropical"),
    (Path(r"G:\Organized\Plugins & Extensions\TV & Broadcast"),
     "After Effects - News & Broadcast", "TV & Broadcast"),
    (Path(r"G:\Organized\Plugins & Extensions\Text Effects & Styles"),
     "Photoshop - Styles & Layer Effects", "Text Effects & Styles"),
]


def journal_correction(src: str, dst: str, clean: str, category: str) -> None:
    if not DB.exists():
        return
    con = sqlite3.connect(str(DB))
    with con:
        con.execute(
            "INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at,status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (src, dst, Path(src).name, clean, category, 90,
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "done"),
        )
    con.close()


def safe_dest(target_dir: Path, name: str) -> Path:
    base = target_dir / name
    if not base.exists():
        return base
    i = 1
    while True:
        cand = target_dir / f"{name} ({i})"
        if not cand.exists():
            return cand
        i += 1


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.scan or args.apply):
        ap.print_help()
        return

    moved = skipped = errors = 0
    for src, target_cat, clean in FIXES:
        if not src.exists():
            print(f"  [SKIP] {src} — not on disk")
            skipped += 1
            continue
        # Target stays on the same drive as the source (avoids cross-drive copy)
        org_root = Path(os.path.splitdrive(str(src))[0] + r"\Organized")
        target_dir = org_root / target_cat
        dest = safe_dest(target_dir, clean)
        files = sum(1 for _ in src.rglob("*") if _.is_file())
        tag = "[SCAN]" if args.scan else ("[DRY]" if args.dry_run else "[APPLY]")
        print(f"  {tag} {src.parent.name}/{src.name}  ({files} files)")
        print(f"        -> {target_cat}/{dest.name}")
        if args.scan or args.dry_run:
            moved += 1
            continue
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            robust_move(str(src), str(dest))
            journal_correction(str(src), str(dest), clean, target_cat)
            moved += 1
        except Exception as e:
            print(f"        ERROR: {e}")
            errors += 1

    print(f"\nSummary: {moved} moved, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
