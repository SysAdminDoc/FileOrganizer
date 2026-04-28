#!/usr/bin/env python3
"""merge_stock.py — Merge pre-organized G:\\Stock and G:\\Design Organized into G:\\Organized.

These folders already have correct category names; no AI classification needed.
Uses robocopy /MIR for each subdirectory then removes the empty source.

Usage:
  python merge_stock.py --preview          # dry-run, show what would move
  python merge_stock.py --apply            # move for real
  python merge_stock.py --source stock     # only G:\\Stock (default: all)
  python merge_stock.py --source design    # only G:\\Design Organized
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

DEST_ROOT = Path(r"G:\Organized")

# Map source folder → dest category name (when name needs remapping)
REMAP = {
    "Stock Footage & Photos":  "Stock Footage - General",
    "Flyers":                  "Print - Flyers & Posters",
    "Design Elements":         None,    # needs manual review — skip
    "After Effects Organized": None,    # walk subdirs instead
}

# Remap for subdirs inside "After Effects Organized"
AE_ORGANIZED_REMAP = {
    "Christmas":     "After Effects - Christmas & Holiday",
    "Logo Reveal":   "After Effects - Logo Reveal",
    "CINEPUNCH.V20": "After Effects - Motion Graphics Pack",   # production bundle
}

SOURCES = {
    "stock": Path(r"G:\Stock"),
    "design": Path(r"G:\Design Organized"),
}


def robocopy_move(src: Path, dest: Path, dry_run: bool) -> bool:
    dest.mkdir(parents=True, exist_ok=True)
    cmd = [
        "robocopy", str(src), str(dest),
        "/E",       # copy subdirectories including empty ones
        "/MOVE",    # move (delete after copy)
        "/256",     # disable 260-char limit
        "/NP",      # no progress %
        "/NFL",     # no file list
        "/NDL",     # no dir list
        "/NJH",     # no job header
        "/NJS",     # no job summary
    ]
    if dry_run:
        print(f"  DRY  {src} -> {dest}")
        return True
    result = subprocess.run(cmd, capture_output=True, text=True)
    ok = result.returncode < 8   # robocopy 0-7 = success
    status = "OK" if ok else "FAIL"
    print(f"  [{status}] {src.name} -> {dest}")
    if not ok:
        print(f"        {result.stderr.strip()}")
    else:
        # remove empty source tree after successful move
        try:
            shutil.rmtree(src)
        except Exception as e:
            print(f"        WARNING: could not remove source: {e}")
    return ok


def merge_source(source_root: Path, source_key: str, dry_run: bool):
    if not source_root.exists():
        print(f"SKIP: {source_root} does not exist")
        return

    print(f"\n=== Merging {source_root} ===")
    moved = skipped = errors = 0

    for item in sorted(source_root.iterdir()):
        if not item.is_dir():
            continue
        name = item.name

        if name in REMAP:
            dest_name = REMAP[name]
            if dest_name is None:
                if name == "After Effects Organized":
                    # walk one level deeper
                    print(f"  -> Walking subdirs of {name}")
                    for sub in sorted(item.iterdir()):
                        if sub.is_dir():
                            dest_name = AE_ORGANIZED_REMAP.get(sub.name, f"After Effects - {sub.name}")
                            dest = DEST_ROOT / dest_name
                            if robocopy_move(sub, dest, dry_run):
                                moved += 1
                            else:
                                errors += 1
                else:
                    print(f"  SKIP (manual review): {name}")
                    skipped += 1
                continue
            dest = DEST_ROOT / dest_name
        else:
            dest = DEST_ROOT / name

        if robocopy_move(item, dest, dry_run):
            moved += 1
        else:
            errors += 1

    label = "DRY RUN" if dry_run else "DONE"
    print(f"\n{label}: {moved} moved, {skipped} skipped, {errors} errors")


def main():
    ap = argparse.ArgumentParser(description="Merge pre-organized stock/design dirs into G:\\Organized")
    ap.add_argument("--preview", action="store_true", help="Dry-run (no moves)")
    ap.add_argument("--apply",   action="store_true", help="Actually move files")
    ap.add_argument("--source",  choices=["stock","design","all"], default="all")
    args = ap.parse_args()

    if not args.preview and not args.apply:
        ap.print_help()
        sys.exit(0)

    dry_run = args.preview

    keys = list(SOURCES.keys()) if args.source == "all" else [args.source]
    for key in keys:
        merge_source(SOURCES[key], key, dry_run)


if __name__ == "__main__":
    main()
