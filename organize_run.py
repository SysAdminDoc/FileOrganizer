#!/usr/bin/env python3
"""Agentic organization runner — applies classified items to destination.

Usage:
    python organize_run.py --preview            # dry run all batches
    python organize_run.py --apply              # apply all batches
    python organize_run.py --preview --load F   # dry run single file
    python organize_run.py --stats              # show batch progress
    python organize_run.py --summary            # category breakdown
"""
import os, sys, json, shutil, re, argparse
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
    dest_root = get_dest_root()
    moved = skipped = errors = low_conf = 0
    category_counts = defaultdict(int)
    not_found = []

    for item, org_entry in pairs:
        clean    = (item.get('clean_name') or item.get('name', '')).strip()
        category = item.get('category', 'After Effects - Other').strip()
        conf     = int(item.get('confidence', 0))

        if not org_entry:
            not_found.append(item.get('name', '?'))
            skipped += 1
            continue

        src_dir  = source_override or org_entry['folder']
        disk_name = org_entry['name']
        src = os.path.join(src_dir, disk_name)

        if not os.path.exists(src):
            not_found.append(disk_name)
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
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                shutil.move(src, dest)
                moved += 1
            except Exception as e:
                log(f"    ERROR moving {disk_name!r}: {e}")
                errors += 1
        else:
            moved += 1

    tag = 'DRY RUN' if dry_run else 'APPLIED'
    log(f"\n{tag}: {moved} moved, {skipped} skipped (not on disk), "
        f"{errors} errors, {low_conf} low-conf routed to {REVIEW_SUBDIR}/")
    if not_found:
        log(f"\nNot on disk ({len(not_found)} items — first 20):")
        for n in not_found[:20]:
            log(f"  - {n}")
        if len(not_found) > 20:
            log(f"  ... and {len(not_found)-20} more")
    return moved, skipped, errors, category_counts

# ── CLI ───────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview',  action='store_true', help='Dry run (default)')
    ap.add_argument('--apply',    action='store_true', help='Apply moves')
    ap.add_argument('--load',     type=str,            help='Single JSON file (skips position mapping)')
    ap.add_argument('--source',   type=str, default='', help='Override source directory')
    ap.add_argument('--stats',    action='store_true', help='Show batch file counts')
    ap.add_argument('--summary',  action='store_true', help='Category/marketplace breakdown')
    ap.add_argument('--quiet',    action='store_true', help='Suppress per-item output')
    args = ap.parse_args()

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
        # Single-file mode: use name-based lookup (for manual testing)
        from collections import OrderedDict
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

