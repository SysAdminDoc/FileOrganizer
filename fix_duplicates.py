#!/usr/bin/env python3
r"""
fix_duplicates.py -- Merge collision-named folders in G:\Organized back into originals.

When organize_run.py creates "Name (1)" because "Name" already exists (e.g., from
a prior design_org pipeline run), this tool:
  1. Robocopy-merges the collision into the original (union of all files)
  2. Removes the now-empty collision folder
  3. Updates organize_moves.db to point collision entries to the original path

Usage:
    python fix_duplicates.py --scan              # report all collision pairs
    python fix_duplicates.py --analyze           # show what would change
    python fix_duplicates.py --apply             # merge + clean (logs everything)
    python fix_duplicates.py --apply --dry-run   # show without changing
"""

import os, re, sys, json, sqlite3, shutil, subprocess, argparse
from pathlib import Path
from collections import defaultdict


def _same_drive(a: Path, b: Path) -> bool:
    return os.path.splitdrive(str(a))[0].upper() == os.path.splitdrive(str(b))[0].upper()


def os_rename_merge(src: Path, dst: Path) -> tuple[int, int, list[str]]:
    """Recursive same-drive merge using os.rename (metadata-only).

    Walks src bottom-up. For each entry under src:
      - If the corresponding path under dst is free, os.rename it across.
      - If dst already has the same name, leave src's copy in place (src is
        the duplicate; dst is the canonical version).
    After traversal, removes any now-empty directories under src.

    Returns (moved, conflicts, errors) where:
      moved     = number of files+dirs successfully renamed into dst
      conflicts = number of entries that already existed in dst (kept dst)
      errors    = list of unexpected exceptions
    """
    moved = 0
    conflicts = 0
    errors: list[str] = []
    if not src.exists():
        return 0, 0, []

    # Bottom-up walk so we can rmdir leaves after their files have moved.
    for root, dirs, files in os.walk(str(src), topdown=False):
        rel = os.path.relpath(root, str(src))
        dst_root = str(dst) if rel in ('.', '') else os.path.join(str(dst), rel)
        os.makedirs(dst_root, exist_ok=True)

        for name in files:
            src_p = os.path.join(root, name)
            dst_p = os.path.join(dst_root, name)
            if os.path.exists(dst_p):
                conflicts += 1
                continue
            try:
                os.rename(src_p, dst_p)
                moved += 1
            except OSError as e:
                errors.append(f"{src_p} -> {dst_p}: {e}")

        for name in dirs:
            sub = os.path.join(root, name)
            try:
                if os.path.exists(sub) and not os.listdir(sub):
                    os.rmdir(sub)
            except OSError:
                pass

    return moved, conflicts, errors

REPO      = Path(__file__).parent
DB        = REPO / 'organize_moves.db'
ORGANIZED = Path(r'G:\Organized')
ORGANIZED_OVERFLOW = Path(r'I:\Organized')
LOG_FILE  = REPO / 'fix_duplicates_log.json'
EMPTY_DIR = REPO / '.robocopy-empty'

def all_org_roots() -> list[Path]:
    return [r for r in (ORGANIZED, ORGANIZED_OVERFLOW) if r.exists()]

def log(msg: str) -> None:
    safe = msg.encode('cp1252', errors='replace').decode('cp1252')
    print(safe)

def robocopy_merge(src: Path, dst: Path, dry_run: bool = False) -> tuple[int, list[str]]:
    """
    Copy all files from src into dst using robocopy.
    Returns (exit_code, error_lines).
    Exit codes 0-7 are success (0=no files, 1=files copied, 3=extra+files, etc.)
    """
    if dry_run:
        return 0, []
    cmd = [
        'robocopy',
        str(src), str(dst),
        '/E',          # copy all subdirs including empty
        '/COPY:DAT',   # preserve data/attributes/timestamps (no audit rights needed)
        '/R:1', '/W:1',
        '/NP',         # no progress percentage
        '/NS', '/NC',  # no size/class in output
        '/NFL', '/NDL' # no file/dir lists — just summary
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    errors = [l for l in result.stderr.splitlines() if l.strip()]
    return result.returncode, errors


def robocopy_purge(path: Path, dry_run: bool = False) -> tuple[int, list[str]]:
    """
    Mirror an empty directory into `path` to delete troublesome contents that
    shutil.rmtree may not handle cleanly on Windows (trailing spaces, odd Unicode).
    """
    if dry_run:
        return 0, []
    EMPTY_DIR.mkdir(exist_ok=True)
    cmd = [
        'robocopy',
        str(EMPTY_DIR), str(path),
        '/MIR',
        '/R:1', '/W:1',
        '/NP',
        '/NS', '/NC',
        '/NFL', '/NDL',
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, errors='replace')
    errors = [l for l in result.stderr.splitlines() if l.strip()]
    return result.returncode, errors


def rmtree_safe(path: Path, dry_run: bool = False) -> bool:
    """Remove a directory tree. Returns True on success."""
    if dry_run:
        return True
    if not path.exists():
        return True
    try:
        shutil.rmtree(str(path))
        return True
    except Exception as e:
        log(f'  WARN rmtree {path}: {e}')
        rc, err_lines = robocopy_purge(path, dry_run=dry_run)
        if rc > 7:
            log(f'  ERROR robocopy purge {path} rc={rc}: {err_lines}')
            return False
        try:
            shutil.rmtree(str(path))
            return True
        except FileNotFoundError:
            return True
        except Exception as e2:
            if not path.exists():
                return True
            log(f'  ERROR rmtree after purge {path}: {e2}')
            return False


def find_collisions() -> dict[str, list[dict]]:
    r"""
    Scan all organized roots for folders matching 'Name (N)' pattern.
    Returns a dict: original_path -> list of collision infos sorted by N ascending.
    """
    collisions: dict[str, list[dict]] = defaultdict(list)

    for root in all_org_roots():
        for cat_dir in sorted(root.iterdir()):
            if not cat_dir.is_dir() or cat_dir.name.startswith('_'):
                continue
            for item_dir in sorted(cat_dir.iterdir()):
                if not item_dir.is_dir():
                    continue
                m = re.match(r'^(.+) \((\d+)\)$', item_dir.name)
                if not m:
                    continue
                base = m.group(1)
                n    = int(m.group(2))
                orig = cat_dir / base
                collisions[str(orig)].append({
                    'path':  str(item_dir),
                    'n':     n,
                    'files': sum(1 for _ in item_dir.rglob('*') if _.is_file()),
                })

    # Sort each collision list by N
    for k in collisions:
        collisions[k].sort(key=lambda x: x['n'])

    return dict(collisions)


def get_orig_file_count(orig_path: str) -> int:
    p = Path(orig_path)
    if not p.exists():
        return -1
    return sum(1 for _ in p.rglob('*') if _.is_file())


def cmd_scan() -> None:
    collisions = find_collisions()
    total_coll  = sum(len(v) for v in collisions.values())
    total_files = sum(c['files'] for v in collisions.values() for c in v)

    print(f'Collision pairs:        {len(collisions)}')
    print(f'Total collision dirs:   {total_coll}')
    print(f'Total files in colls:   {total_files:,}')

    # Breakdown by category
    by_cat: dict[str, int] = defaultdict(int)
    for orig_path, colls in collisions.items():
        cat = Path(orig_path).parent.name
        by_cat[cat] += len(colls)

    print('\nBy category (top 15):')
    for cat, n in sorted(by_cat.items(), key=lambda x: -x[1])[:15]:
        print(f'  {n:4d}  {cat}')


def cmd_analyze(limit: int = 20) -> None:
    collisions = find_collisions()
    print(f'Analyzing {len(collisions)} collision pairs...\n')
    shown = 0
    for orig_path, colls in sorted(collisions.items()):
        if shown >= limit:
            print(f'  ... {len(collisions) - shown} more pairs not shown.')
            break
        orig = Path(orig_path)
        orig_files = get_orig_file_count(orig_path)
        status = 'PRESENT' if orig_files >= 0 else 'MISSING'
        print(f'  [{status}] {orig.parent.name}/{orig.name}')
        print(f'    Original: {orig_files} files')
        for c in colls:
            print(f'    Collision ({c["n"]}): {c["files"]} files  -> {Path(c["path"]).name}')
        shown += 1


def cmd_apply(dry_run: bool = False) -> None:
    collisions = find_collisions()
    con = sqlite3.connect(str(DB))

    results = []
    merged = 0
    deleted = 0
    skipped = 0
    db_updates = 0
    errors = 0

    tag = '[DRY]' if dry_run else '[APPLY]'

    for orig_path, colls in sorted(collisions.items()):
        orig = Path(orig_path)
        orig_files = get_orig_file_count(orig_path)

        for coll_info in colls:
            coll      = Path(coll_info['path'])
            coll_n    = coll_info['n']
            coll_files = coll_info['files']

            # Case 1: Original is MISSING — rename collision to original name
            if orig_files < 0:
                log(f'{tag} RENAME  {coll.name} -> {orig.name}  ({coll_files} files)')
                if not dry_run:
                    try:
                        coll.rename(orig)
                        # Update DB entry
                        con.execute(
                            'UPDATE moves SET dest = ? WHERE dest = ?',
                            (str(orig), str(coll))
                        )
                        con.commit()
                        db_updates += 1
                        orig_files = coll_files  # now exists
                        merged += 1
                    except Exception as e:
                        log(f'  ERROR rename: {e}')
                        errors += 1
                results.append({'action': 'rename', 'from': str(coll), 'to': str(orig)})
                continue

            # Case 2: Both exist — merge collision contents into original, then delete collision.
            # Same-drive: per-file os.rename (metadata-only, near-instant).
            # Cross-drive: robocopy /E (must copy file bytes anyway).
            log(f'{tag} MERGE   {coll.name}  ({coll_files} files) -> {orig.name} ({orig_files} files)')

            if dry_run:
                rc, err_lines = 0, []
            elif _same_drive(coll, orig):
                m, c, errs = os_rename_merge(coll, orig)
                if errs:
                    log(f'  rename merge: {len(errs)} errors (first: {errs[0][:200]})')
                    errors += 1
                    results.append({'action': 'merge_failed', 'src': str(coll), 'dst': str(orig),
                                    'errors': errs[:5]})
                    skipped += 1
                    continue
                rc = 0
                err_lines = []
            else:
                rc, err_lines = robocopy_merge(coll, orig, dry_run=dry_run)
                if rc > 7:
                    log(f'  ROBOCOPY ERROR rc={rc}: {err_lines}')
                    errors += 1
                    results.append({'action': 'merge_failed', 'src': str(coll), 'dst': str(orig), 'rc': rc})
                    skipped += 1
                    continue

            # Remove collision
            removed = rmtree_safe(coll, dry_run=dry_run)
            if removed:
                deleted += 1
                if not dry_run:
                    # Update DB: redirect collision's dest to original
                    con.execute(
                        'UPDATE moves SET dest = ? WHERE dest = ?',
                        (str(orig), str(coll))
                    )
                    con.commit()
                    db_updates += 1
                # Recount orig files after merge
                orig_files = get_orig_file_count(orig_path)
                log(f'  -> merged, original now has {orig_files} files')
                merged += 1
            else:
                errors += 1

            results.append({
                'action': 'merge',
                'collision': str(coll),
                'original': str(orig),
                'coll_files': coll_files,
                'orig_files_after': orig_files if not dry_run else '?',
                'rc': rc,
            })

            # Incremental log save every 50 merges so a kill mid-run preserves audit trail
            if not dry_run and len(results) % 50 == 0:
                LOG_FILE.write_text(json.dumps(results, indent=2), encoding='utf-8')

    con.close()

    # Save results (final)
    if not dry_run:
        LOG_FILE.write_text(json.dumps(results, indent=2), encoding='utf-8')
        log(f'\nResults saved to {LOG_FILE.name}')

    print(f'\n{"[DRY RUN] " if dry_run else ""}Summary:')
    print(f'  Merged/renamed:  {merged}')
    print(f'  Deleted colls:   {deleted}')
    print(f'  DB updated:      {db_updates}')
    print(f'  Skipped/errors:  {errors}')


def main():
    ap = argparse.ArgumentParser(description='Merge collision-named duplicate folders')
    ap.add_argument('--scan',    action='store_true', help='Report all collision pairs')
    ap.add_argument('--analyze', action='store_true', help='Show what would be merged')
    ap.add_argument('--apply',   action='store_true', help='Perform merge + cleanup')
    ap.add_argument('--dry-run', action='store_true', help='With --apply: show without changing')
    args = ap.parse_args()

    if args.scan:
        cmd_scan()
    elif args.analyze:
        cmd_analyze()
    elif args.apply:
        cmd_apply(dry_run=args.dry_run)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
