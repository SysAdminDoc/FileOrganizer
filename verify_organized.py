#!/usr/bin/env python3
r"""
verify_organized.py — Post-apply verification for G:\Organized.

Checks the physical library against the DB journal to surface:
  - Categories with suspiciously few or many items
  - Excess (N)-suffix collision files still present
  - Items in DB but missing from disk (failed move / deleted)
  - Items on disk but not in DB (moved by external process)
  - _Review breakdown with remediation suggestions
  - Empty category dirs that should be cleaned up
  - Filename encoding issues (replacement chars in names)

Usage:
    python verify_organized.py                     # full health report
    python verify_organized.py --collisions        # list remaining (N)-suffix items
    python verify_organized.py --missing           # DB items not on disk
    python verify_organized.py --orphans           # on-disk dirs not in DB
    python verify_organized.py --review            # _Review breakdown + suggestions
    python verify_organized.py --summary           # category file counts only
    python verify_organized.py --export report.md  # save report as Markdown
"""

import os, sys, re, json, sqlite3, argparse
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

REPO      = Path(__file__).parent
DB        = REPO / 'organize_moves.db'
ORGANIZED          = Path(r'G:\Organized')
ORGANIZED_OVERFLOW = Path(r'I:\Organized')   # overflow destination when G:\ is low

def all_org_roots() -> list[Path]:
    """Return all organized root directories that exist on disk."""
    return [r for r in (ORGANIZED, ORGANIZED_OVERFLOW) if r.exists()]

# ── Helpers ───────────────────────────────────────────────────────────────────

def safe_print(msg: str) -> None:
    print(msg.encode('cp1252', errors='replace').decode('cp1252'))


def iter_db_moves():
    if not DB.exists():
        return
    con = sqlite3.connect(str(DB))
    for row in con.execute(
        "SELECT src, dest, category, confidence, moved_at FROM moves WHERE undone_at IS NULL"
    ):
        yield {'src': row[0], 'dest': row[1], 'category': row[2],
               'confidence': row[3], 'moved_at': row[4]}
    con.close()


def walk_organized():
    r"""Yield all files recursively under all organized roots with their category dir."""
    for root in all_org_roots():
        for cat_dir in sorted(root.iterdir()):
            if not cat_dir.is_dir():
                continue
            for f in cat_dir.rglob('*'):
                if f.is_file():
                    yield f, cat_dir.name


COLLISION_PAT = re.compile(r'^(.+) \((\d+)\)$')
REPLACEMENT_CHARS = re.compile(r'[\ufffd\u003f]{2,}')  # repeated ? or replacement chars


def category_quick_counts() -> Counter:
    """Fast category summary using os.scandir (1 level deep + count sub-items).
    Aggregates across all organized roots (G:\\ primary + I:\\ overflow if present)."""
    counts: Counter = Counter()
    for root in all_org_roots():
        with os.scandir(str(root)) as top:
            for cat_entry in top:
                if not cat_entry.is_dir():
                    continue
                n = 0
                try:
                    with os.scandir(cat_entry.path) as items:
                        for item in items:
                            if item.is_file():
                                n += 1
                            elif item.is_dir():
                                # Count files one more level deep (sub-folders of template packs)
                                try:
                                    with os.scandir(item.path) as sub:
                                        n += sum(1 for s in sub if s.is_file())
                                except PermissionError:
                                    pass
                except PermissionError:
                    pass
                counts[cat_entry.name] += n  # += so same category across roots accumulates
    return counts


def find_collision_dirs() -> list[Path]:
    """Fast scan for top-level collision directories named 'Name (N)'."""
    collisions: list[Path] = []
    for root in all_org_roots():
        for cat_dir in sorted(root.iterdir()):
            if not cat_dir.is_dir():
                continue
            try:
                for item_dir in sorted(cat_dir.iterdir()):
                    if item_dir.is_dir() and COLLISION_PAT.match(item_dir.name):
                        collisions.append(item_dir)
            except PermissionError:
                continue
    return collisions


def detect_issues(path: Path) -> list[str]:
    """Return list of issue tags for a file path."""
    issues = []
    if REPLACEMENT_CHARS.search(path.name):
        issues.append('encoding-garbage')
    if COLLISION_PAT.match(path.stem):
        issues.append('collision-suffix')
    return issues


# ── Report sections ───────────────────────────────────────────────────────────

def report_summary(category_counts: Counter, output: list) -> None:
    roots = all_org_roots()
    root_labels = ' + '.join(str(r) for r in roots)
    output.append('\n## Category Summary\n')
    total_files = sum(category_counts.values())
    output.append(f'Total files in {root_labels}: {total_files:,}\n')
    output.append(f'Total categories: {len(category_counts)}\n\n')
    output.append(f'{"Category":<50} {"Files":>7}\n')
    output.append('-' * 60 + '\n')
    for cat, n in sorted(category_counts.items(), key=lambda x: -x[1]):
        output.append(f'{cat:<50} {n:>7,}\n')


def report_collisions(collision_paths: list[Path], output: list) -> None:
    output.append('\n## Remaining Collision-Suffix Directories\n')
    if not collision_paths:
        output.append('None — all (N) collisions have been resolved. ✓\n')
        return
    by_cat: dict[str, list] = defaultdict(list)
    roots = all_org_roots()
    for f in collision_paths:
        cat = '?'
        for root in roots:
            if f.is_relative_to(root):
                cat = f.parent.relative_to(root).parts[0]
                break
        by_cat[cat].append(f.name)
    output.append(f'{len(collision_paths)} collision directories remaining across {len(by_cat)} categories.\n')
    output.append('Run: python fix_duplicates.py --apply  to resolve.\n\n')
    for cat, names in sorted(by_cat.items(), key=lambda x: -len(x[1])):
        output.append(f'  [{len(names)}] {cat}\n')
        for nm in sorted(names)[:5]:
            output.append(f'    {nm}\n')
        if len(names) > 5:
            output.append(f'    ... and {len(names)-5} more\n')


def report_missing(db_moves: list, disk_paths: set, output: list) -> None:
    output.append('\n## DB Items Missing from Disk\n')
    missing = [m for m in db_moves if m['dest'] not in disk_paths and
               not Path(m['dest']).exists()]
    if not missing:
        output.append('All DB-journaled destinations exist on disk. ✓\n')
        return
    output.append(f'{len(missing)} DB entries whose destination no longer exists:\n\n')
    for m in sorted(missing, key=lambda x: x['category'])[:50]:
        output.append(f'  [{m["category"]}] {Path(m["dest"]).name}\n')
        output.append(f'    dest: {m["dest"]}\n')
    if len(missing) > 50:
        output.append(f'  ... and {len(missing)-50} more\n')


def report_orphans(db_dest_set: set, disk_cat_dirs: dict, output: list) -> None:
    output.append('\n## Category Directories Not in DB\n')
    orphan_cats = [
        cat for cat, paths in disk_cat_dirs.items()
        if cat not in ('_Review',) and not any(p in db_dest_set for p in paths[:10])
    ]
    if not orphan_cats:
        output.append('All category dirs have DB entries. ✓\n')
        return
    output.append(f'{len(orphan_cats)} category dirs with no DB entries (may be pre-existing or externally moved):\n\n')
    for cat in sorted(orphan_cats):
        n = len(disk_cat_dirs[cat])
        output.append(f'  {cat}: {n} files\n')


def report_review(output: list) -> None:
    output.append('\n## _Review Breakdown\n')
    review_dirs = [root / '_Review' for root in all_org_roots() if (root / '_Review').exists()]
    if not review_dirs:
        output.append('_Review directory does not exist — no items queued for review. ✓\n')
        return
    cats: Counter = Counter()
    for review_dir in review_dirs:
        for d in sorted(review_dir.iterdir()):
            if d.is_dir():
                count = sum(1 for _ in d.rglob('*') if _.is_file())
                cats[d.name] += count
    if not cats:
        output.append('_Review is empty. ✓\n')
        return
    total = sum(cats.values())
    output.append(f'{total} files across {len(cats)} subcategories in _Review.\n\n')
    output.append('Action: re-run classify_design.py with --force-review to attempt re-classification,\n')
    output.append('or manually verify and move to correct categories.\n\n')
    for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
        bar = '#' * min(n // 3, 30)
        output.append(f'  {n:5d}  {cat:<45}  {bar}\n')


def report_encoding_issues(encoding_bad: list[Path], output: list) -> None:
    output.append('\n## Files with Encoding Issues\n')
    if not encoding_bad:
        output.append('No encoding issues detected. ✓\n')
        return
    output.append(f'{len(encoding_bad)} files with replacement/garbage characters in names.\n\n')
    for f in sorted(encoding_bad)[:30]:
        output.append(f'  {f}\n')
    if len(encoding_bad) > 30:
        output.append(f'  ... and {len(encoding_bad)-30} more\n')


def report_empty_categories(category_counts: Counter, output: list) -> None:
    empty = []
    for root in all_org_roots():
        empty += [d.name for d in root.iterdir()
                  if d.is_dir() and d.name not in category_counts]
    output.append('\n## Empty Category Directories\n')
    if not empty:
        output.append('No empty category directories. ✓\n')
        return
    output.append(f'{len(empty)} empty dirs (safe to remove):\n')
    for d in sorted(empty):
        output.append(f'  {d}\n')


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description='Verify G:\\Organized against DB journal')
    ap.add_argument('--collisions', action='store_true', help='Show remaining (N)-suffix collisions')
    ap.add_argument('--missing',    action='store_true', help='DB items not present on disk')
    ap.add_argument('--orphans',    action='store_true', help='On-disk dirs not in DB')
    ap.add_argument('--review',     action='store_true', help='_Review breakdown')
    ap.add_argument('--summary',    action='store_true', help='Category file counts only')
    ap.add_argument('--export',     metavar='FILE', help='Write report to a Markdown file')
    args = ap.parse_args()

    run_all = not any([args.collisions, args.missing, args.orphans, args.review, args.summary])

    # Summary mode uses fast shallow scan — no full rglob needed
    if args.summary and not run_all:
        print('Scanning G:\\Organized (shallow)...')
        category_counts = category_quick_counts()
        output = [f'# FileOrganizer — Category Summary\n',
                  f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n']
        report_summary(category_counts, output)
        report_text = ''.join(output)
        for line in report_text.splitlines():
            safe_print(line)
        if args.export:
            Path(args.export).write_text(report_text, encoding='utf-8')
            print(f'\nReport saved to: {args.export}')
        return

    if args.collisions and not run_all:
        print('Scanning G:\\Organized for collision directories (targeted)...')
        collision_dirs = find_collision_dirs()
        output = [f'# FileOrganizer — Collision Report\n',
                  f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n']
        report_collisions(collision_dirs, output)
        report_text = ''.join(output)
        for line in report_text.splitlines():
            safe_print(line)
        if args.export:
            Path(args.export).write_text(report_text, encoding='utf-8')
            print(f'\nReport saved to: {args.export}')
        return

    if args.review and not run_all:
        print('Scanning G:\\Organized _Review directories (targeted)...')
        output = [f'# FileOrganizer — Review Queue Report\n',
                  f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n']
        report_review(output)
        report_text = ''.join(output)
        for line in report_text.splitlines():
            safe_print(line)
        if args.export:
            Path(args.export).write_text(report_text, encoding='utf-8')
            print(f'\nReport saved to: {args.export}')
        return

    print(f'Scanning G:\\Organized (full — may take several minutes)...')
    category_counts: Counter = Counter()
    collision_files: list[Path] = []
    encoding_bad: list[Path] = []
    disk_paths: set = set()
    disk_cat_dirs: dict = defaultdict(list)

    for f, cat in walk_organized():
        category_counts[cat] += 1
        disk_paths.add(str(f))
        disk_cat_dirs[cat].append(str(f))
        for issue in detect_issues(f):
            if issue == 'collision-suffix':
                collision_files.append(f)
            elif issue == 'encoding-garbage':
                encoding_bad.append(f)

    print(f'Loading DB moves...')
    db_moves = list(iter_db_moves())
    db_dest_set = {m['dest'] for m in db_moves}

    output = [f'# FileOrganizer Verification Report\n',
              f'Generated: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}\n\n']

    if run_all or args.summary:
        report_summary(category_counts, output)
    if run_all or args.collisions:
        report_collisions(collision_files, output)
    if run_all or args.missing:
        report_missing(db_moves, disk_paths, output)
    if run_all or args.orphans:
        report_orphans(db_dest_set, dict(disk_cat_dirs), output)
    if run_all or args.review:
        report_review(output)
    if run_all:
        report_encoding_issues(encoding_bad, output)
        report_empty_categories(category_counts, output)

    report_text = ''.join(output)
    for line in report_text.splitlines():
        safe_print(line)

    if args.export:
        Path(args.export).write_text(report_text, encoding='utf-8')
        print(f'\nReport saved to: {args.export}')


if __name__ == '__main__':
    main()
