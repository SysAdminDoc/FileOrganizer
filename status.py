#!/usr/bin/env python3
"""status.py -- Pipeline status dashboard for the design asset reorganization.

Prints a summary of all pipeline sources: how many items classified,
how many moved, how many errors, and what processes are currently running.

Usage:
    python status.py           # summary dashboard
    python status.py --errors  # show all error items across sources
    python status.py --review  # show _Review category breakdown
"""

import os, sys, json, sqlite3, subprocess, argparse
from pathlib import Path
from collections import Counter

REPO      = Path(__file__).parent
DB        = REPO / 'organize_moves.db'
RESULTS   = REPO / 'classification_results'
ORGANIZED = Path(r'G:\Organized')

def get_db_counts() -> dict:
    if not DB.exists():
        return {}
    con = sqlite3.connect(str(DB))
    rows = con.execute("""
        SELECT
          CASE
            WHEN src LIKE 'I:\\After Effects%'     THEN 'ae'
            WHEN src LIKE 'I:\\Unorganized%'       THEN 'unorg'
            WHEN src LIKE 'G:\\Design Organized%'  THEN 'design_org'
            WHEN src LIKE 'G:\\Design Unorganized%' THEN 'loose_prev'
            WHEN src LIKE 'G:\\Stock%'             THEN 'stock'
            WHEN src LIKE 'G:\\Organized%'         THEN 'corrections'
            ELSE 'other'
          END as src_type,
          COUNT(*) as n
        FROM moves WHERE undone_at IS NULL
        GROUP BY src_type
    """).fetchall()
    con.close()
    return {r[0]: r[1] for r in rows}


def get_batch_counts() -> dict:
    if not RESULTS.exists():
        return {}
    prefixes = ['batch_', 'unorg_batch_', 'design_batch_', 'design_org_batch_',
                'loose_batch_', 'de_batch_']
    counts = {}
    for pref in prefixes:
        n = len(list(RESULTS.glob(f'{pref}*.json')))
        counts[pref.rstrip('_')] = n
    return counts


def get_running_pids() -> list[dict]:
    """Find Python pipeline processes and robocopy children."""
    running = []
    try:
        out = subprocess.check_output(
            ['wmic', 'process', 'get', 'ProcessId,ParentProcessId,CommandLine', '/format:csv'],
            text=True, stderr=subprocess.DEVNULL
        )
        for line in out.splitlines():
            parts = line.strip().split(',', 3)
            if len(parts) < 4:
                continue
            _, cmd, pid, ppid = parts
            if 'organize_run.py' in cmd or 'classify_design.py' in cmd or 'merge_stock.py' in cmd:
                src_hint = ''
                for flag in ['--source ae', '--source loose', '--source stock', '--source design']:
                    if flag in cmd:
                        src_hint = flag.replace('--source ', '')
                        break
                running.append({'pid': pid, 'type': 'python', 'hint': src_hint or 'unknown',
                                 'cmd': cmd[-80:]})
            elif 'robocopy' in cmd.lower():
                # Extract source dir from robocopy args
                parts2 = cmd.split('"')
                src = parts2[1] if len(parts2) > 1 else '?'
                running.append({'pid': pid, 'type': 'robocopy', 'hint': src[-60:], 'cmd': ''})
    except Exception:
        pass
    return running


def get_error_counts() -> dict:
    counts = {}
    for f in REPO.glob('organize_errors_*.json'):
        src = f.stem.replace('organize_errors_', '')
        try:
            errs = json.loads(f.read_text(encoding='utf-8'))
            counts[src] = len(errs)
        except Exception:
            counts[src] = -1
    return counts


def review_breakdown() -> dict:
    rev_dir = ORGANIZED / '_Review'
    if not rev_dir.exists():
        return {}
    cats = {}
    for d in rev_dir.iterdir():
        if d.is_dir():
            cats[d.name] = sum(1 for _ in d.rglob('*') if _.is_file())
    return cats


def cmd_dashboard() -> None:
    db  = get_db_counts()
    bat = get_batch_counts()
    err = get_error_counts()
    run = get_running_pids()

    total_db = sum(db.values())

    print('=' * 62)
    print('  DESIGN ASSET REORGANIZATION -- PIPELINE STATUS')
    print('=' * 62)

    print('\n  SOURCE PROGRESS')
    print('  ' + '-' * 58)
    rows = [
        ('AE Templates (I:)',       bat.get('batch', 0),         19,    db.get('ae', 0),    1136, err.get('ae', 0)),
        ('AE Unorganized (I:)',     bat.get('unorg_batch', 0),    1,     db.get('unorg', 0), 88,   0),
        ('Design Org (G:)',         bat.get('design_org_batch',0), 44,   db.get('design_org',0), 2643, 0),
        ('Loose Files (G:)',        bat.get('loose_batch', 0),   326,   0,                  19531, err.get('loose_files', 0)),
        ('Merge Stock (G:)',        0,                             0,    db.get('stock', 0), 0,    err.get('stock', 0)),
    ]

    fmt = '  {:<25} {:>5}/{:<5} batches  {:>5}/{:<5} moved  {:>3} err'
    for label, cb, ct, mb, mt, e in rows:
        batch_str  = f'{cb}' if ct else '-'
        batch_tot  = f'{ct}' if ct else '-'
        moved_str  = f'{mb}' if mt else '-'
        moved_tot  = f'{mt}' if mt else '-'
        err_str    = str(e) if e else '-'
        print(f'  {label:<25} {batch_str:>5}/{batch_tot:<5} batches  '
              f'{moved_str:>5}/{moved_tot:<5} moved  {err_str:>3} err')

    print(f'\n  TOTAL MOVES IN DB: {total_db:,}')

    print('\n  CORRECTIONS')
    print(f'  loose_prev moves (prior design_unorg): {db.get("loose_prev", 0):,}')
    print(f'  corrections (fix_stock_ae, etc.):      {db.get("corrections", 0):,}')

    print('\n  RUNNING PROCESSES')
    if not run:
        print('  (none detected)')
    for p in run:
        if p['type'] == 'python':
            print(f'  PID {p["pid"]:>6} python -- {p["hint"]}')
        else:
            print(f'  PID {p["pid"]:>6} robocopy <- {p["hint"]}')

    err_src = {k: v for k, v in err.items() if v > 0}
    if err_src:
        print(f'\n  ERRORS (need --retry-errors): {err_src}')

    print('=' * 62)


def cmd_errors() -> None:
    for f in sorted(REPO.glob('organize_errors_*.json')):
        src = f.stem.replace('organize_errors_', '')
        try:
            errs = json.loads(f.read_text(encoding='utf-8'))
        except Exception:
            continue
        if not errs:
            continue
        print(f'\n  [{src}] {len(errs)} errors:')
        for e in errs:
            nm = e.get('name') or e.get('disk_name', '?')
            msg = str(e.get('error', ''))[:80]
            print(f'    {nm!r}: {msg}')


def cmd_review() -> None:
    cats = review_breakdown()
    if not cats:
        print('_Review is empty or does not exist.')
        return
    total = sum(cats.values())
    print(f'\n  _Review: {total} files in {len(cats)} subcategories\n')
    for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
        bar = '#' * min(n // 2, 40)
        print(f'  {n:5d}  {cat:<45}  {bar}')


def main():
    ap = argparse.ArgumentParser(description='Pipeline status dashboard')
    ap.add_argument('--errors', action='store_true', help='Show all error items')
    ap.add_argument('--review', action='store_true', help='Show _Review breakdown')
    args = ap.parse_args()
    if args.errors:
        cmd_errors()
    elif args.review:
        cmd_review()
    else:
        cmd_dashboard()


if __name__ == '__main__':
    main()
