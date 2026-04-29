#!/usr/bin/env python3
r"""fix_short_titles.py — Upgrade cache entries where og:title is short
and slug-derived title is significantly longer/more descriptive.

Discovery: Envato's `<meta property="og:title">` sometimes carries a
short marketing tag (`Stomp`, `Wedding`, `Awards`) while the canonical
URL slug holds the full descriptive title (`ultimate-stomp`,
`wedding-story`, `gold-frames-awards-show`). The first
normalize_archive_names pass preferred og:title and produced these
truncated names. This script:

  1. Walks the marketplace_title_cache.json.
  2. For each entry where slug-derived title (a) has more words than
     og:title and (b) is at least 30% longer, swap to slug-derived.
  3. Walks the target directory and renames any file whose current
     name matches the old (short) title to the new (long) title.

Idempotent: a re-run with no fixable entries is a no-op.

Usage:
  python fix_short_titles.py --root "I:\After Effects" --scan
  python fix_short_titles.py --root "I:\After Effects" --apply
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).parent
CACHE_FILE = REPO / "marketplace_title_cache.json"

ARCHIVE_EXTS = (".zip", ".rar", ".7z")
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def slug_to_title(slug: str) -> str:
    if not slug:
        return ""
    s = slug.replace("-", " ").replace("_", " ")
    return re.sub(r"\s+", " ", s).strip().title()


def sanitize_for_filename(s: str) -> str:
    s = INVALID_PATH_CHARS.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:180].rstrip(" .")


def find_better_title(entry: dict) -> str | None:
    """Return the better title if slug-derived beats og:title, else None."""
    og_title = entry.get("title", "").strip()
    slug = entry.get("slug", "").strip()
    if not slug:
        return None

    slug_title = slug_to_title(slug)
    if not slug_title:
        return None

    og_words = len(og_title.split()) if og_title else 0
    slug_words = len(slug_title.split())

    # Prefer slug if it has strictly more words AND is at least 30% longer
    if slug_words > og_words and len(slug_title) > len(og_title) * 1.3:
        return slug_title
    return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not (args.scan or args.apply):
        ap.print_help()
        return

    cache = json.loads(CACHE_FILE.read_text(encoding="utf-8"))

    # Step 1: identify cache entries that should swap title
    swaps: list[tuple[str, str, str]] = []  # (cache_key, old_title, new_title)
    for k, v in cache.items():
        if not v:
            continue
        better = find_better_title(v)
        if better and better != v["title"]:
            swaps.append((k, v["title"], better))

    print(f"Found {len(swaps)} cache entries that can be upgraded")
    for k, old, new in swaps[:15]:
        print(f"  {k}: {old!r}  ->  {new!r}")
    if len(swaps) > 15:
        print(f"  ... +{len(swaps)-15} more")

    if not args.apply:
        return

    # Step 2: rename files on disk
    root = Path(args.root)
    if not root.exists():
        print(f"Root not found: {root}")
        sys.exit(1)

    archives = {f.name: f for f in root.iterdir()
                if f.is_file() and f.suffix.lower() in ARCHIVE_EXTS}

    renames = 0
    for k, old_title, new_title in swaps:
        # Update cache
        cache[k]["title"] = new_title
        cache[k]["title_source"] = "slug-derived (upgrade pass)"

        # Find files on disk with the old title; both .zip and .rar
        old_safe = sanitize_for_filename(old_title)
        new_safe = sanitize_for_filename(new_title)
        for ext in (".zip", ".rar", ".7z"):
            current_name = f"{old_safe}{ext}"
            target_name = f"{new_safe}{ext}"
            current = root / current_name
            target = root / target_name
            if not current.exists() or current_name == target_name:
                continue
            # Avoid clobbering: add (1) suffix if target exists
            if target.exists():
                i = 1
                while True:
                    cand = root / f"{new_safe} ({i}){ext}"
                    if not cand.exists():
                        target = cand
                        break
                    i += 1
            print(f"  RENAME  {current.name}  ->  {target.name}")
            try:
                os.rename(str(current), str(target))
                renames += 1
            except OSError as e:
                print(f"    ERROR: {e}")

    # Save updated cache
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                          encoding="utf-8")

    print(f"\n{renames} files renamed, {len(swaps)} cache entries upgraded")


if __name__ == "__main__":
    main()
