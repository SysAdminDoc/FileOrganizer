#!/usr/bin/env python3
r"""resolve_unknown_vh.py — Resolve the 5 "Unknown LP/VH Template" detached
AE subfolders left in G:\Organized\_Review\After Effects - Other\.

Manually inspected each item; classifications below come from the
assistant's own reading of the inner folder structure (no DeepSeek round-trip).

Decisions:

 Unknown LP Video 2          (Chinese AE template, no clear subject)
   → After Effects - Other

 Unknown VH Template         (contains "Planet Blast" + Element 3D Models)
   → After Effects - 3D & Particle, rename to "Planet Blast"

 Unknown VH Template (2)     (duplicate of "Planet Blast")
   → After Effects - 3D & Particle, rename to "Planet Blast (2)"

 Unknown VH Template 2 (1)   (contains VH-9265399/Epic Galaxy Titles)
   → After Effects - Title & Typography, rename to "Epic Galaxy Titles"

 Unknown VH Template 3       (generic ae/CS6.aep + tutorial.mp4 — no subject)
   → After Effects - Other
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
from organize_run import robust_move  # noqa: E402

DB = REPO / "organize_moves.db"
G_ROOT = Path(r"G:\Organized")
REVIEW = G_ROOT / "_Review" / "After Effects - Other"

# (current_path, target_canonical_category, new_name, reason)
DECISIONS = [
    (REVIEW / "Unknown LP Video 2",
     "After Effects - Other", "Unknown Chinese AE Template (LP Video 2)",
     "Garbled-name Chinese AE template — no identifiable subject"),
    (REVIEW / "Unknown VH Template",
     "After Effects - 3D & Particle", "Planet Blast",
     "Inner folder is 'Planet Blast' + Element 3D Models — Videohive 3D pack"),
    (REVIEW / "Unknown VH Template (2)",
     "After Effects - 3D & Particle", "Planet Blast",
     "Duplicate of Planet Blast — let safe_dest add (2) suffix"),
    (REVIEW / "Unknown VH Template 2 (1)",
     "After Effects - Title & Typography", "Epic Galaxy Titles",
     "Inner content is VH-9265399/Epic Galaxy Titles — title pack"),
    (REVIEW / "Unknown VH Template 3",
     "After Effects - Other", "Unknown VH Template 3",
     "Generic VH delivery (ae/CS6.aep + tutorial.mp4) — no subject info"),
]


def journal(src: str, dst: str, category: str, clean: str) -> None:
    if not DB.exists():
        return
    con = sqlite3.connect(str(DB))
    with con:
        con.execute(
            "INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at,status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (src, dst, Path(src).name, clean, category, 80,
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
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not (args.scan or args.apply):
        ap.print_help()
        return

    moved = skipped = errors = 0
    for src, target_cat, new_name, reason in DECISIONS:
        if not src.exists():
            print(f"  [SKIP] {src.name} — already gone")
            skipped += 1
            continue
        target_dir = G_ROOT / target_cat
        dest = safe_dest(target_dir, new_name)
        print(f"  [MOVE] {src.name}")
        print(f"         -> {target_cat}/{dest.name}")
        print(f"         reason: {reason}")
        if args.scan or args.dry_run:
            moved += 1
            continue
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            robust_move(str(src), str(dest))
            journal(str(src), str(dest), target_cat, new_name)
            moved += 1
        except Exception as e:
            print(f"         ERROR: {e}")
            errors += 1

    # Try removing the now-empty review subdir
    if args.apply and not args.dry_run:
        try:
            if REVIEW.exists() and not list(REVIEW.iterdir()):
                REVIEW.rmdir()
                print(f"  Removed empty {REVIEW}")
        except OSError:
            pass

    print(f"\nSummary: {moved} moved, {skipped} skipped, {errors} errors")


if __name__ == "__main__":
    main()
