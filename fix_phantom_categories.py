#!/usr/bin/env python3
r"""fix_phantom_categories.py — Migrate items out of non-canonical "phantom"
top-level category folders into their canonical destinations.

Background
----------
Earlier AI runs created top-level category folders that don't exist in the
canonical taxonomy (classify_design.CATEGORIES). Two sources caused this:
  1. Bug in fix_stock_ae_items.py — a "promo" keyword rule produced
     "After Effects - Promo & Advertising".
  2. Bug in merge_stock.py AE_ORGANIZED fallback — `f"After Effects - {sub.name}"`
     produced "After Effects - CINEPUNCH.V20", "After Effects - Photo Slideshow".
  3. Phase 4 (I:\Organized legacy library reclassification) was never run, so
     11k+ items still sit in old folder names like "Flyers & Print",
     "Resume & CV", "Logo & Identity", "After Effects - Slideshows".

This script reads the canonical list from classify_design.CATEGORIES, plus
the CATEGORY_ALIASES map from organize_run, and migrates each item from
a phantom folder into the canonical equivalent. Anything not in the alias
map is left in place and reported so a human can decide.

Usage:
    python fix_phantom_categories.py --scan                   # report only
    python fix_phantom_categories.py --apply --dry-run        # preview moves
    python fix_phantom_categories.py --apply                  # do it
    python fix_phantom_categories.py --apply --root I:        # only one root
"""

import argparse
import json
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))

from classify_design import CATEGORIES                # noqa: E402
from organize_run import CATEGORY_ALIASES, _lp        # noqa: E402

CANON = set(CATEGORIES)
ROOTS = [Path(r"G:\Organized"), Path(r"I:\Organized")]
LOG_FILE = REPO / "fix_phantom_categories_log.json"


def is_phantom_dir(name: str) -> bool:
    if name.startswith("_"):
        return False  # _Review, _Skip
    return name not in CANON


def map_phantom(name: str) -> str | None:
    """Return canonical category for a phantom dir, or None if unknown."""
    if name in CATEGORY_ALIASES:
        return CATEGORY_ALIASES[name]
    if name.startswith("Web Template -"):
        return "Web Template"
    return None


def robocopy_merge(src: Path, dst: Path, dry_run: bool) -> tuple[int, str]:
    """Move all subdirs and files from src into dst. Returns (rc, stderr)."""
    if dry_run:
        return 0, ""
    dst.mkdir(parents=True, exist_ok=True)
    cmd = [
        "robocopy", _lp(str(src)), _lp(str(dst)),
        "/E", "/MOVE", "/256",
        "/COPY:DAT", "/R:1", "/W:1",
        "/NP", "/NS", "/NC", "/NFL", "/NDL", "/NJH", "/NJS",
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
    return res.returncode, (res.stderr or res.stdout or "").strip()


def remove_empty_tree(path: Path) -> None:
    """robocopy /MOVE empties src but doesn't always rmdir; clean up here."""
    if not path.exists():
        return
    try:
        shutil.rmtree(str(path))
    except Exception:
        # Sometimes Windows leaves the dir locked momentarily; not fatal.
        pass


def collect_phantoms(roots: list[Path]) -> dict[Path, list[Path]]:
    """Return {root: [phantom_dir_paths]} for each given root."""
    out: dict[Path, list[Path]] = {}
    for root in roots:
        if not root.exists():
            continue
        out[root] = sorted(
            d for d in root.iterdir()
            if d.is_dir() and is_phantom_dir(d.name)
        )
    return out


def cmd_scan(roots: list[Path]) -> None:
    phantoms = collect_phantoms(roots)
    total_dirs = total_items = unmapped = 0
    by_root_summary: dict[str, dict[str, int]] = defaultdict(lambda: {"mapped": 0, "unmapped": 0, "items": 0})

    for root, dirs in phantoms.items():
        print(f"\n=== {root} ({len(dirs)} phantom dirs) ===")
        for d in dirs:
            try:
                child_count = sum(1 for _ in d.iterdir())
            except Exception:
                child_count = -1
            target = map_phantom(d.name)
            tag = f"-> {target}" if target else "[NO MAPPING — needs human review]"
            if not target:
                unmapped += 1
                by_root_summary[str(root)]["unmapped"] += 1
            else:
                by_root_summary[str(root)]["mapped"] += 1
            by_root_summary[str(root)]["items"] += max(0, child_count)
            total_dirs += 1
            total_items += max(0, child_count)
            print(f"  {d.name:<55} {child_count:>5} items  {tag}")

    print("\n=== Summary ===")
    for root, s in by_root_summary.items():
        print(f"  {root}: {s['mapped']} mapped, {s['unmapped']} unmapped, {s['items']:,} items")
    print(f"Total phantom dirs: {total_dirs} | items: {total_items:,} | unmapped: {unmapped}")


def cmd_apply(roots: list[Path], dry_run: bool) -> None:
    phantoms = collect_phantoms(roots)
    tag = "[DRY]" if dry_run else "[APPLY]"
    log_entries: list[dict] = []
    moved = removed = skipped = errors = 0

    for root, dirs in phantoms.items():
        for d in dirs:
            target_cat = map_phantom(d.name)
            if not target_cat:
                print(f"  {tag} SKIP (no mapping): {root.drive} {d.name}")
                skipped += 1
                log_entries.append({"action": "skip-no-mapping", "path": str(d)})
                continue

            # Empty phantom dir → just remove it
            try:
                contents = list(d.iterdir())
            except Exception as e:
                print(f"  {tag} ERROR list {d}: {e}")
                errors += 1
                continue

            if not contents:
                print(f"  {tag} REMOVE (empty): {root.drive} {d.name}")
                if not dry_run:
                    remove_empty_tree(d)
                removed += 1
                log_entries.append({"action": "remove-empty", "path": str(d)})
                continue

            target_dir = root / target_cat
            print(f"  {tag} MERGE  {root.drive} {d.name!r} ({len(contents)} items) -> {target_cat}")
            rc, err = robocopy_merge(d, target_dir, dry_run)
            if rc >= 8:
                print(f"    ROBOCOPY ERROR rc={rc}: {err[:200]}")
                errors += 1
                log_entries.append({
                    "action": "merge-failed", "src": str(d), "dst": str(target_dir),
                    "rc": rc, "err": err[:500],
                })
                continue

            if not dry_run:
                remove_empty_tree(d)
            moved += 1
            log_entries.append({
                "action": "merge", "src": str(d), "dst": str(target_dir),
                "items": len(contents), "rc": rc,
            })

    print("\n=== Summary ===")
    print(f"  Merged folders:   {moved}")
    print(f"  Removed (empty):  {removed}")
    print(f"  Skipped (no map): {skipped}")
    print(f"  Errors:           {errors}")
    if not dry_run:
        LOG_FILE.write_text(json.dumps(log_entries, indent=2), encoding="utf-8")
        print(f"  Log:              {LOG_FILE.name}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Migrate items out of phantom category folders")
    ap.add_argument("--scan", action="store_true", help="Report phantom dirs without moving")
    ap.add_argument("--apply", action="store_true", help="Migrate items into canonical dirs")
    ap.add_argument("--dry-run", action="store_true", help="With --apply: preview only")
    ap.add_argument("--root", choices=["G:", "I:", "all"], default="all",
                    help="Limit to a single drive root")
    args = ap.parse_args()

    if args.root == "G:":
        roots = [ROOTS[0]]
    elif args.root == "I:":
        roots = [ROOTS[1]]
    else:
        roots = ROOTS

    if args.scan:
        cmd_scan(roots)
    elif args.apply:
        cmd_apply(roots, dry_run=args.dry_run)
    else:
        ap.print_help()


if __name__ == "__main__":
    main()
