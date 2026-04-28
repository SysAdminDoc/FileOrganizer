#!/usr/bin/env python3
r"""resolve_review_manual.py — Hand-curated cleanup of remaining _Review items.

This is a one-shot script that resolves the items left in
G:\Organized\_Review\ by inspecting filenames, archive contents, and
folder structure with the assistant's own judgment (no DeepSeek round-trip).

Decisions made:

 _Review\After Effects - Sport & Action\Girl Foot Project
   → After Effects - Sport & Action  (legitimate sport AE template, was
     in _Review only because original confidence was low)

 _Review\Orphaned Documentation\*  (4 items)
   → DELETE  (pure help/docs detached from parent bundles, per CLAUDE.md
     gotcha "Documentation/Help File folders as bundle components")

 _Review\_Review\LightingEffctBundl1-vfxdownload.net.zip   → Cinematic FX & Overlays
 _Review\_Review\LightleaksVol1-vfxdownload.net.zip        → Cinematic FX & Overlays
 _Review\_Review\Moodboard-Mockup-Kit-2760918.zip          → Mockups - Branding & Stationery

 The remaining 3 zips (18813.zip, PFSPr0P1x1e-..., setup.zip) and the 5
 detached "Unknown VH Template" subfolders stay in _Review — they have no
 reliable signal to classify.

Usage:
   python resolve_review_manual.py --scan
   python resolve_review_manual.py --apply [--dry-run]
"""

import argparse
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
from organize_run import robust_move  # noqa: E402

DB = REPO / "organize_moves.db"
G_ROOT = Path(r"G:\Organized")

REVIEW = G_ROOT / "_Review"

# (current_path, action, target_canonical_category | None, reason)
DECISIONS: list[tuple[Path, str, str | None, str]] = [
    (REVIEW / "After Effects - Sport & Action" / "Girl Foot Project",
     "move", "After Effects - Sport & Action",
     "Sport AE template (girl_foot_project + MotionElements readme)"),

    (REVIEW / "Orphaned Documentation" / "Help File - Avelina Studio",
     "delete", None,
     "Detached help docs (PNG + RTF, no asset content)"),
    (REVIEW / "Orphaned Documentation" / "Main Print",
     "delete", None,
     "Just READ ME.txt — no asset content"),
    (REVIEW / "Orphaned Documentation" / "Read Me (GraphixTree)",
     "delete", None,
     "URL shortcuts + small marketing PNGs from a piracy site"),
    (REVIEW / "Orphaned Documentation" / "readme",
     "delete", None,
     "Just readme.txt — no asset content"),

    (REVIEW / "_Review" / "LightingEffctBundl1-vfxdownload.net.zip",
     "move", "Cinematic FX & Overlays",
     "Lighting Effects Bundle — name + size (1.5 GB) match a film-FX overlay pack"),
    (REVIEW / "_Review" / "LightleaksVol1-vfxdownload.net.zip",
     "move", "Cinematic FX & Overlays",
     "Light Leaks Vol 1 — classic cinematic overlay pack pattern"),
    (REVIEW / "_Review" / "Moodboard-Mockup-Kit-2760918.zip",
     "move", "Mockups - Branding & Stationery",
     "Moodboard Mockup Kit (CreativeMarket ID 2760918) — branding mockup"),
]


def journal(action: str, src: str, dst: str, category: str | None) -> None:
    if not DB.exists():
        return
    con = sqlite3.connect(str(DB))
    with con:
        con.execute(
            "INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at,status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (src, dst or src, Path(src).name, Path(src).stem,
             category or "_Deleted", 90 if action == "move" else 0,
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "done" if action == "move" else "deleted"),
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


def remove_empty_review_dirs() -> None:
    for sub in (REVIEW / "Orphaned Documentation", REVIEW / "_Review"):
        try:
            if sub.exists() and not list(sub.iterdir()):
                sub.rmdir()
                print(f"  Removed empty {sub}")
        except OSError:
            pass


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.scan or args.apply):
        ap.print_help()
        return

    moved = deleted = skipped = errors = 0
    for src, action, target_cat, reason in DECISIONS:
        if not src.exists():
            print(f"  [SKIP] {src.name} — already gone")
            skipped += 1
            continue

        if action == "delete":
            print(f"  [DELETE] {src.name}  — {reason}")
            if args.scan or args.dry_run:
                deleted += 1
                continue
            try:
                if src.is_dir():
                    shutil.rmtree(str(src))
                else:
                    src.unlink()
                journal("delete", str(src), "", None)
                deleted += 1
            except Exception as e:
                print(f"        ERROR: {e}")
                errors += 1
            continue

        # action == "move"
        target_dir = G_ROOT / target_cat
        dest = safe_dest(target_dir, src.name)
        print(f"  [MOVE] {src.name}  -> {target_cat}/{dest.name}")
        print(f"         reason: {reason}")
        if args.scan or args.dry_run:
            moved += 1
            continue
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            robust_move(str(src), str(dest))
            journal("move", str(src), str(dest), target_cat)
            moved += 1
        except Exception as e:
            print(f"         ERROR: {e}")
            errors += 1

    if args.apply and not args.dry_run:
        remove_empty_review_dirs()

    print(f"\nSummary: {moved} moved, {deleted} deleted, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
