#!/usr/bin/env python3
r"""fix_overstripped_archives.py — Repair archives whose name was
over-stripped during normalize_archive_names.py to a useless residue
like "V11.zip", "V 2 1.rar", or "V1 5.zip".

These came from filenames like VH-37693478-v11-INTRO-HD.NET.zip where the
version-marker regex stripped the entire prefix, leaving only the version
string. The real product title sits inside the archive — peek via 7-Zip
to recover it.

Heuristic: a current basename is "over-stripped" if it matches:
  - ^V\d+$            (V11)
  - ^V\s*\d+(\s*\d+)*$ (V1 5, V 2 1)
  - ^[A-Za-z]{1,2}\d+$ (a4, b17, c9)

For each, list the archive contents and pick the most informative
top-level directory name (after stripping VH-NNN-vNN-INTRO-HD.NET-style
wrappers).

Also handles archives whose top-level dir is a marketplace-prefix wrapper
even if the current name is otherwise reasonable — re-uses the
process_ae_archives extract_project_name logic.

Usage:
  python fix_overstripped_archives.py --root "I:\After Effects" --scan
  python fix_overstripped_archives.py --root "I:\After Effects" --apply
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
from process_ae_archives import (  # noqa: E402
    list_archive, extract_project_name, clean_name, archive_group,
)

PARTIAL_RAR_RE = re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE)


def part_suffix(archive: Path) -> str:
    m = PARTIAL_RAR_RE.search(archive.name)
    return archive.name[m.start():] if m else ""

ARCHIVE_EXTS = (".zip", ".rar", ".7z")

# Archives are "over-stripped" if their stem looks like a residue:
OVERSTRIPPED_PATTERNS = [
    re.compile(r"^[Vv]\d+$"),                     # V11
    re.compile(r"^[Vv]\s*\d+(?:\s+\d+)*$"),       # V 2 1, V1 5
    re.compile(r"^[A-Za-z]{1,2}\d{1,3}$"),        # a4, b17, c9
    re.compile(r"^\d{1,4}-\d{1,4}$"),             # 0000-2, 1111-22
    re.compile(r"^[A-Za-z]{1,3}$"),                # vk, ab
    re.compile(r"^\d+$"),                          # 551465 (bare numeric)
]


def is_overstripped(stem: str) -> bool:
    for rx in OVERSTRIPPED_PATTERNS:
        if rx.fullmatch(stem):
            return True
    return False


def safe_target(p: Path) -> Path:
    if not p.exists():
        return p
    base = p.stem
    suffix = p.suffix
    pre_part = part_suffix(p)
    if pre_part:
        base = p.name[: -len(pre_part)]
        suffix = pre_part
    i = 1
    while True:
        cand = p.parent / f"{base} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


def derive_better_name(archive: Path) -> str:
    """Use process_ae_archives logic to get the most informative title
    from the archive contents."""
    names = list_archive(archive)
    if not names:
        return ""
    return extract_project_name(names, archive.stem)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not (args.scan or args.apply):
        ap.print_help()
        return

    root = Path(args.root)
    archives = sorted(f for f in root.iterdir()
                       if f.is_file() and f.suffix.lower() in ARCHIVE_EXTS)

    overstripped = []
    for a in archives:
        # Skip multipart non-first parts
        m = re.search(r"\.part(\d+)\.rar$", a.name, re.I)
        if m and int(m.group(1)) != 1:
            continue
        stem = a.stem
        # Strip multipart suffix from stem for the check
        ps = part_suffix(a)
        if ps:
            stem = a.name[: -len(ps)]
        if is_overstripped(stem):
            overstripped.append(a)

    print(f"Found {len(overstripped)} over-stripped archives")

    renames = 0
    for a in overstripped:
        better = derive_better_name(a)
        if not better or better == a.stem:
            print(f"  [SKIP] {a.name} (no better name from contents)")
            continue
        # Numeric-only-rejection: bare ID is not better than the current name.
        if re.fullmatch(r"\d+", better):
            print(f"  [SKIP] {a.name} (better name {better!r} is numeric-only)")
            continue
        # Require the new name to have at least one alphabetic word
        if not re.search(r"[A-Za-z]{3,}", better):
            print(f"  [SKIP] {a.name} (better name {better!r} lacks real word)")
            continue
        # Build target name (preserve multipart suffix if any)
        ps = part_suffix(a)
        if ps:
            target_name = f"{better}{ps}"
        else:
            target_name = f"{better}{a.suffix}"

        target = a.parent / target_name
        if target.exists() and target != a:
            target = safe_target(target)

        tag = "[SCAN]" if args.scan else ("[DRY]" if args.dry_run else "[RENAME]")
        # cp1252-safe console output
        a_safe = a.name.encode("cp1252", errors="replace").decode("cp1252")
        t_safe = target.name.encode("cp1252", errors="replace").decode("cp1252")
        print(f"  {tag} {a_safe}")
        print(f"        -> {t_safe}")

        if args.scan or args.dry_run:
            renames += 1
            continue

        # Rename all multipart parts together
        parts = archive_group(a)
        if not parts:
            continue
        if len(parts) > 1:
            base_target = target.name[: -len(part_suffix(target))]
            for p in parts:
                tgt = p.parent / f"{base_target}{part_suffix(p)}"
                if tgt.exists() and tgt != p:
                    tgt = safe_target(tgt)
                try:
                    os.rename(str(p), str(tgt))
                except OSError as e:
                    print(f"        ERROR: {e}")
        else:
            try:
                os.rename(str(a), str(target))
                renames += 1
            except OSError as e:
                print(f"        ERROR: {e}")

    print(f"\n{renames} renamed")


if __name__ == "__main__":
    main()
