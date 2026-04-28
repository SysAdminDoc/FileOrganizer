#!/usr/bin/env python3
"""Agentic organization runner — applies classified items to destination.

Usage:
    python organize_run.py --preview            # dry run all batches
    python organize_run.py --apply              # apply all batches
    python organize_run.py --preview --load F   # dry run single file
    python organize_run.py --stats              # show batch progress
    python organize_run.py --summary            # category breakdown
    python organize_run.py --retry-errors       # retry only previously errored items

Known edge cases handled:
    - Trailing spaces in file/folder names (WinError 2) → pre-sanitized before move
    - Deep Unicode paths >260 chars (WinError 3) → robocopy with /256 long-path support
    - Cross-drive moves use robocopy for reliability; shutil used for same-drive
    - shutil.move NEVER deletes source on copy failure (safe), but leaves partial dests
    - Errors logged to organize_errors.json for retry/audit
"""
import os, sys, json, shutil, re, argparse, subprocess
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DEST_PRIMARY     = r'G:\Organized'
MIN_FREE_GB      = 50
REVIEW_SUBDIR    = '_Review'       # low-confidence items land here
MIN_CONFIDENCE   = 50
AE_BATCH_SIZE    = 60              # items per AE batch (batches 1-18 = 60, batch 19 = 56)
AE_TOTAL         = 1136            # total After Effects items in org_index
INDEX_FILE       = os.path.join(os.path.dirname(__file__), 'org_index.json')
LOG_FILE         = os.path.join(os.path.dirname(__file__), 'organize_run.log')
ERRORS_FILE      = os.path.join(os.path.dirname(__file__), 'organize_errors.json')
RESULTS_DIR      = os.path.join(os.path.dirname(__file__), 'classification_results')
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg, also_print=True):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    if also_print:
        print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

# ── Load org_index ────────────────────────────────────────────────────────────
def load_org_index() -> list:
    if not os.path.exists(INDEX_FILE):
        return []
    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

# ── Batch file → org_index offset ────────────────────────────────────────────
def batch_offset(filename: str) -> int:
    """
    Map batch filename to its starting offset in org_index.
      batch_001.json      → 0   (AE items 0-59)
      batch_013.json      → 720 (AE items 720-779)
      unorg_batch_001.json→ AE_TOTAL (Unorganized items start after all AE)
    """
    stem = Path(filename).stem        # e.g. 'batch_013' or 'unorg_batch_001'
    if stem.startswith('unorg_batch_'):
        n = int(stem.split('_')[-1])  # 1-based
        return AE_TOTAL + (n - 1) * 100  # unorg batches can be up to 100 items
    elif stem.startswith('batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * AE_BATCH_SIZE
    return 0

# ── Pre-sanitize: strip trailing spaces from file/folder names in-place ────────
def strip_trailing_spaces(root: str) -> list:
    """
    Rename any file or directory under `root` that has trailing spaces in its name.
    Returns list of (old_path, new_path) renames performed.
    Windows silently strips trailing spaces when CREATING items via the API, but
    existing items (e.g., copied from other systems/drives) can retain them and
    cause WinError 2 during shutil operations.
    """
    renamed = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames + dirnames:
            if name != name.rstrip():
                old = os.path.join(dirpath, name)
                new = os.path.join(dirpath, name.rstrip())
                if not os.path.exists(new):
                    try:
                        os.rename(old, new)
                        renamed.append((old, new))
                    except Exception:
                        pass
    return renamed

def is_cross_drive(src: str, dst: str) -> bool:
    return os.path.splitdrive(src)[0].upper() != os.path.splitdrive(dst)[0].upper()

# ── Robocopy-based move (reliable for cross-drive, Unicode, long paths) ────────
def robust_move(src: str, dst: str) -> None:
    """
    Move `src` directory to `dst`.
    - Same drive: os.rename (atomic).
    - Cross-drive: robocopy /MOVE /256 (long-path aware), then remove emptied src.
    Raises RuntimeError if robocopy exit code >= 8 (actual failure).
    Robocopy exit codes: 0=nothing to do, 1=files copied, 2=extra files,
    3=mismatched, 4=mismatched+copied, 5-7=combinations — all < 8 = success.
    """
    if not is_cross_drive(src, dst):
        os.rename(src, dst)
        return

    os.makedirs(dst, exist_ok=True)
    result = subprocess.run([
        'robocopy', src, dst,
        '/MOVE',   # move (delete source files after copy)
        '/E',      # include empty subdirs
        '/256',    # disable 260-char path limit (long path support)
        '/R:3',    # retry 3×
        '/W:1',    # wait 1 s between retries
        '/NP',     # no progress %
        '/NFL',    # no file list
        '/NDL',    # no dir list
        '/NJH',    # no job header
        '/NJS',    # no job summary
    ], capture_output=True, text=True)

    if result.returncode >= 8:
        raise RuntimeError(
            f"robocopy exit {result.returncode}: {result.stderr.strip() or result.stdout.strip()}"
        )

    # Remove now-empty source dir (robocopy /MOVE empties it but doesn't rmdir)
    try:
        shutil.rmtree(src)
    except Exception:
        pass

# ── Load classification JSONs with position-based org_index alignment ─────────
def load_one(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get('results', [])

def load_all_with_index() -> list:
    """
    Returns list of (classified_item, org_entry) tuples.
    Matches each classified item to its real disk entry by position in org_index.
    """
    org = load_org_index()
    pairs = []
    for p in sorted(Path(RESULTS_DIR).glob('*.json')):
        items = load_one(str(p))
        offset = batch_offset(p.name)
        for i, item in enumerate(items):
            idx_pos = offset + i
            org_entry = org[idx_pos] if idx_pos < len(org) else None
            pairs.append((item, org_entry))
    return pairs

# ── Destination helpers ───────────────────────────────────────────────────────
def get_dest_root() -> str:
    try:
        free = shutil.disk_usage(DEST_PRIMARY[:3]).free
        if free > MIN_FREE_GB * 1_073_741_824:
            return DEST_PRIMARY
    except Exception:
        pass
    return DEST_PRIMARY

def sanitize(s: str, maxlen: int = 120) -> str:
    return re.sub(r'[<>:"/\\|?*]', '-', s).strip()[:maxlen]

def safe_dest_path(dest_root: str, category: str, clean_name: str) -> str:
    dest = os.path.join(dest_root, sanitize(category), sanitize(clean_name))
    if os.path.exists(dest):
        base, i = dest, 1
        while os.path.exists(dest):
            dest = f"{base} ({i})"
            i += 1
    return dest

# ── Core move logic ───────────────────────────────────────────────────────────
def apply_moves(pairs: list, source_override: str,
                dry_run: bool = True, verbose: bool = True):
    dest_root  = get_dest_root()
    moved = skipped = errors = low_conf = 0
    category_counts = defaultdict(int)
    not_found  = []
    error_log  = []   # written to ERRORS_FILE on completion

    for item, org_entry in pairs:
        clean    = (item.get('clean_name') or item.get('name', '')).strip()
        category = item.get('category', 'After Effects - Other').strip()
        conf     = int(item.get('confidence', 0))

        if not org_entry:
            not_found.append(item.get('name', '?'))
            skipped += 1
            continue

        src_dir   = source_override or org_entry['folder']
        disk_name = org_entry['name']
        src       = os.path.join(src_dir, disk_name)

        if not os.path.exists(src):
            # Skip already-moved items silently (idempotent re-runs)
            skipped += 1
            continue

        # Low confidence → Review subfolder
        if conf < MIN_CONFIDENCE:
            eff_category = os.path.join(REVIEW_SUBDIR, category)
            low_conf += 1
        else:
            eff_category = category

        dest = safe_dest_path(dest_root, eff_category, clean)
        category_counts[category] += 1

        if verbose:
            tag  = '[DRY]' if dry_run else '[MOVE]'
            flag = f'  *** LOW CONF={conf}' if conf < MIN_CONFIDENCE else ''
            log(f"  {tag} {disk_name!r}")
            log(f"    -> {dest}  [{conf}]{flag}", also_print=verbose)

        if not dry_run:
            try:
                # Pre-sanitize: strip trailing spaces from any names inside src
                renamed = strip_trailing_spaces(src)
                if renamed:
                    log(f"    Pre-sanitized {len(renamed)} name(s) with trailing spaces in {disk_name!r}")

                os.makedirs(os.path.dirname(dest), exist_ok=True)
                robust_move(src, dest)
                moved += 1
            except Exception as e:
                err_msg = str(e)
                log(f"    ERROR moving {disk_name!r}: {err_msg}")
                errors += 1
                error_log.append({
                    'disk_name': disk_name,
                    'src': src,
                    'dest': dest,
                    'category': category,
                    'clean_name': clean,
                    'confidence': conf,
                    'error': err_msg,
                    'partial_dest_exists': os.path.exists(dest),
                })
        else:
            moved += 1

    tag = 'DRY RUN' if dry_run else 'APPLIED'
    log(f"\n{tag}: {moved} moved, {skipped} skipped (not on disk), "
        f"{errors} errors, {low_conf} low-conf routed to {REVIEW_SUBDIR}/")
    if not_found:
        log(f"\nNot in index ({len(not_found)} items):")
        for n in not_found[:10]:
            log(f"  - {n}")

    if not dry_run and error_log:
        with open(ERRORS_FILE, 'w', encoding='utf-8') as f:
            json.dump(error_log, f, indent=2, ensure_ascii=False)
        log(f"\nErrors written to {ERRORS_FILE} — run --retry-errors to attempt fixes")

    return moved, skipped, errors, category_counts

# ── CLI ───────────────────────────────────────────────────────────────────────
def retry_errors():
    """Re-attempt items from organize_errors.json using the robust move pipeline."""
    if not os.path.exists(ERRORS_FILE):
        print(f"No errors file found at {ERRORS_FILE}")
        return
    with open(ERRORS_FILE, 'r', encoding='utf-8') as f:
        errors = json.load(f)
    log(f"Retrying {len(errors)} errored items...")
    retried = fixed = still_failed = 0
    remaining = []
    for e in errors:
        src  = e['src']
        dest = e['dest']
        if not os.path.exists(src):
            log(f"  SKIP (src gone): {e['disk_name']!r}")
            retried += 1
            fixed   += 1
            continue
        # Clean any partial destination first
        if e.get('partial_dest_exists') and os.path.exists(dest):
            log(f"  Cleaning partial dest: {dest!r}")
            shutil.rmtree(dest, ignore_errors=True)
        try:
            renamed = strip_trailing_spaces(src)
            if renamed:
                log(f"  Pre-sanitized {len(renamed)} trailing-space names in {e['disk_name']!r}")
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            robust_move(src, dest)
            log(f"  FIXED: {e['disk_name']!r}")
            fixed += 1
        except Exception as ex:
            log(f"  STILL FAILED: {e['disk_name']!r}: {ex}")
            still_failed += 1
            remaining.append({**e, 'error': str(ex), 'partial_dest_exists': os.path.exists(dest)})
        retried += 1
    log(f"\nRetry complete: {fixed} fixed, {still_failed} still failing")
    if remaining:
        with open(ERRORS_FILE, 'w', encoding='utf-8') as f:
            json.dump(remaining, f, indent=2, ensure_ascii=False)
        log(f"Remaining errors saved to {ERRORS_FILE}")
    else:
        os.remove(ERRORS_FILE)
        log("All errors resolved — errors file removed")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview',       action='store_true', help='Dry run (default)')
    ap.add_argument('--apply',         action='store_true', help='Apply moves')
    ap.add_argument('--retry-errors',  action='store_true', help='Retry items in organize_errors.json')
    ap.add_argument('--load',          type=str,            help='Single JSON file (skips position mapping)')
    ap.add_argument('--source',        type=str, default='', help='Override source directory')
    ap.add_argument('--stats',         action='store_true', help='Show batch file counts')
    ap.add_argument('--summary',       action='store_true', help='Category/marketplace breakdown')
    ap.add_argument('--quiet',         action='store_true', help='Suppress per-item output')
    args = ap.parse_args()

    if args.retry_errors:
        retry_errors()
        return

    if args.stats:
        files = sorted(Path(RESULTS_DIR).glob('*.json'))
        total = 0
        print(f"\nClassification results ({RESULTS_DIR}):")
        for fp in files:
            items = load_one(str(fp))
            offset = batch_offset(fp.name)
            print(f"  {fp.name:<35} {len(items):>4} items  [org_index {offset}–{offset+len(items)-1}]")
            total += len(items)
        print(f"\n  Total: {total} items across {len(files)} files")
        return

    if args.load:
        # Single-file mode: name-based lookup (for manual testing)
        org = load_org_index()
        name_map = {e['name']: e for e in org}
        items = load_one(args.load)
        log(f"Loaded {len(items)} items from {args.load}")
        pairs = []
        for item in items:
            n = item.get('name', '')
            entry = name_map.get(n) or next(
                (e for e in org if e['name'].startswith(n) or n.startswith(e['name'])), None)
            pairs.append((item, entry))
    else:
        pairs = load_all_with_index()
        log(f"Loaded {len(pairs)} items via position-based index mapping")

    if args.summary:
        cats    = defaultdict(int)
        markets = defaultdict(int)
        low     = sum(1 for item, _ in pairs if int(item.get('confidence', 0)) < MIN_CONFIDENCE)
        for item, _ in pairs:
            cats[item.get('category', 'Unknown')] += 1
            markets[item.get('marketplace', 'Unknown')] += 1
        print(f"\n=== CATEGORY BREAKDOWN ({len(pairs)} items, {low} low-conf) ===")
        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"  {cnt:>4}  {cat}")
        print(f"\n=== MARKETPLACE BREAKDOWN ===")
        for mkt, cnt in sorted(markets.items(), key=lambda x: -x[1]):
            print(f"  {cnt:>4}  {mkt}")
        return

    dry     = not args.apply
    verbose = not args.quiet
    apply_moves(pairs, args.source, dry_run=dry, verbose=verbose)

if __name__ == '__main__':
    main()

