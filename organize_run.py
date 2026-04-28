#!/usr/bin/env python3
"""Agentic organization runner — applies classified items to destination.

Usage:
    python organize_run.py --preview            # dry run all batches
    python organize_run.py --apply              # apply all batches
    python organize_run.py --preview --load F   # dry run single file
    python organize_run.py --validate           # pre-flight: find trailing spaces + long paths
    python organize_run.py --stats              # show batch progress
    python organize_run.py --summary            # category breakdown
    python organize_run.py --retry-errors       # retry only previously errored items
    python organize_run.py --undo-last N        # reverse the last N moves (from journal)
    python organize_run.py --undo-all           # reverse all moves in journal

Known edge cases handled:
    - Trailing spaces in file/folder names (WinError 2) → pre-sanitized before move
    - Deep Unicode paths >260 chars (WinError 3) → robocopy with /256 long-path support
    - Cross-drive moves use robocopy for reliability; os.rename for same-drive
    - shutil.move NEVER deletes source on copy failure (safe), but leaves partial dests
    - Every successful move is journaled to organize_moves.db for full undo support
    - Errors logged to organize_errors.json for retry/audit
"""
import os, sys, json, shutil, re, argparse, subprocess, sqlite3
from pathlib import Path
from collections import defaultdict
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
DEST_PRIMARY     = r'G:\Organized'
MIN_FREE_GB      = 50
REVIEW_SUBDIR    = '_Review'       # low-confidence items land here
MIN_CONFIDENCE   = 50

# ── AE / Unorganized source (Phase 1) ────────────────────────────────────────
AE_BATCH_SIZE    = 60              # items per AE batch (batches 1-18 = 60, batch 19 = 56)
AE_TOTAL         = 1136            # total After Effects items in org_index
INDEX_FILE       = os.path.join(os.path.dirname(__file__), 'org_index.json')

# ── Design source (Phase 2: G:\Design Unorganized) ───────────────────────────
DESIGN_BATCH_SIZE = 60
DESIGN_INDEX_FILE = os.path.join(os.path.dirname(__file__), 'design_unorg_index.json')

LOG_FILE         = os.path.join(os.path.dirname(__file__), 'organize_run.log')
ERRORS_FILE      = os.path.join(os.path.dirname(__file__), 'organize_errors.json')
JOURNAL_FILE     = os.path.join(os.path.dirname(__file__), 'organize_moves.db')
RESULTS_DIR      = os.path.join(os.path.dirname(__file__), 'classification_results')
os.makedirs(RESULTS_DIR, exist_ok=True)

# ── Category name normalization ──────────────────────────────────────────────
# Canonical names (right-hand side).  Any batch that returns a left-hand key
# will be silently rewritten before the destination path is computed.
# This handles cross-batch inconsistencies (AE vs Design classifiers used
# slightly different names for the same category).
CATEGORY_ALIASES = {
    # word-order variant from the AE classifier
    'After Effects - Opener & Intro':   'After Effects - Intro & Opener',
    # old short name — "Title & Typography" is more precise
    'After Effects - Typography':       'After Effects - Title & Typography',
    # flat names returned by older AE batches for categories with subtypes
    'Business & Marketing':             'After Effects - Corporate & Business',
    'Holiday & Seasonal':               'After Effects - Christmas & Holiday',
    'Motion Graphics & VFX':            'After Effects - Motion Graphics Pack',
    'Services & Industries':            'After Effects - Corporate & Business',
    'Sport & Recreation':               'After Effects - Sport & Action',
    'Food & Lifestyle':                 'After Effects - Product Promo',
    'Design Tools & Resources':         'Plugins & Extensions',
    'Audio Resources':                  'Stock Music & Audio',
    'Video Editing - General':          'After Effects - Other',
    # G:\Stock bucket category — maps to general stock footage
    'Stock Footage & Photos':           'Stock Footage - General',
}

def normalize_category(cat: str) -> str:
    """Return the canonical category name, resolving any known alias."""
    return CATEGORY_ALIASES.get(cat, cat)

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg, also_print=True):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    if also_print:
        print(line)
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

# ── Moves journal (SQLite) ────────────────────────────────────────────────────
_JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS moves (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src         TEXT NOT NULL,
    dest        TEXT NOT NULL,
    disk_name   TEXT NOT NULL,
    clean_name  TEXT,
    category    TEXT,
    confidence  INTEGER,
    moved_at    TEXT NOT NULL,
    undone_at   TEXT
);
CREATE INDEX IF NOT EXISTS idx_moves_moved_at ON moves(moved_at);
CREATE INDEX IF NOT EXISTS idx_moves_undone   ON moves(undone_at);
"""

def _journal_conn() -> sqlite3.Connection:
    con = sqlite3.connect(JOURNAL_FILE)
    con.row_factory = sqlite3.Row
    con.executescript(_JOURNAL_SCHEMA)
    return con

def journal_record(src: str, dest: str, disk_name: str,
                   clean_name: str, category: str, confidence: int):
    """Record a completed move in the SQLite journal."""
    con = _journal_conn()
    con.execute(
        "INSERT INTO moves (src, dest, disk_name, clean_name, category, confidence, moved_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (src, dest, disk_name, clean_name, category, confidence,
         datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'))
    )
    con.commit()
    con.close()

def undo_moves(last_n: int = 0, dry_run: bool = False) -> dict:
    """
    Reverse moves recorded in the journal.
    last_n=0 reverses ALL un-undone moves (newest first).
    Returns {reversed: N, skipped: N, failed: N}.
    """
    if not os.path.exists(JOURNAL_FILE):
        print("No moves journal found — nothing to undo.")
        return {}

    con = _journal_conn()
    if last_n:
        rows = con.execute(
            "SELECT * FROM moves WHERE undone_at IS NULL ORDER BY id DESC LIMIT ?", (last_n,)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM moves WHERE undone_at IS NULL ORDER BY id DESC"
        ).fetchall()

    total = len(rows)
    if not total:
        print("Nothing to undo.")
        con.close()
        return {}

    tag = '[DRY-UNDO]' if dry_run else '[UNDO]'
    print(f"\n{tag} Reversing {total} move(s)...")
    reversed_n = skipped = failed = 0

    for row in rows:
        src  = row['dest']   # where it is NOW
        dest = row['src']    # where it came FROM

        if not os.path.exists(src):
            print(f"  SKIP (gone from dest): {row['disk_name']!r}")
            skipped += 1
            continue
        if os.path.exists(dest):
            print(f"  SKIP (src path occupied): {dest!r}")
            skipped += 1
            continue

        print(f"  {tag} {row['clean_name']!r}  {src!r} -> {dest!r}")
        if not dry_run:
            try:
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                robust_move(src, dest)
                con.execute(
                    "UPDATE moves SET undone_at=? WHERE id=?",
                    (datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ'), row['id'])
                )
                con.commit()
                reversed_n += 1
            except Exception as e:
                print(f"  FAILED undo {row['disk_name']!r}: {e}")
                failed += 1
        else:
            reversed_n += 1

    con.close()
    print(f"\n{'DRY ' if dry_run else ''}Undo complete: {reversed_n} reversed, "
          f"{skipped} skipped, {failed} failed")
    return {'reversed': reversed_n, 'skipped': skipped, 'failed': failed}

# ── Load org_index ────────────────────────────────────────────────────────────
def load_index_for_source(source_mode: str) -> list:
    path = DESIGN_INDEX_FILE if source_mode == 'design' else INDEX_FILE
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_org_index() -> list:
    return load_index_for_source('ae')

# ── Batch file → index offset ─────────────────────────────────────────────────
def batch_offset(filename: str, source_mode: str = 'ae') -> int:
    """
    Map batch filename to its starting offset in the appropriate index.
      AE mode:
        batch_001.json      → 0   (AE items 0-59)
        batch_013.json      → 720 (AE items 720-779)
        unorg_batch_001.json→ AE_TOTAL (Unorganized items start after all AE)
      Design mode:
        design_batch_001.json → 0
        design_batch_013.json → 720
    """
    stem = Path(filename).stem
    if stem.startswith('design_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('unorg_batch_'):
        n = int(stem.split('_')[-1])
        return AE_TOTAL + (n - 1) * 100
    elif stem.startswith('batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * AE_BATCH_SIZE
    return 0

# ── Pre-flight validator ──────────────────────────────────────────────────────
def validate_sources(pairs: list, source_override: str = '') -> dict:
    """
    Scan all source directories for known problem patterns BEFORE attempting
    any moves.  Reports:
      - Directories/files with trailing spaces in their names (→ WinError 2)
      - Paths whose full length exceeds 260 chars (→ WinError 3 on cross-drive)
      - Missing source directories (already moved or never existed)

    Returns {'trailing_spaces': [...], 'long_paths': [...], 'missing': [...]}
    """
    org  = load_org_index()
    trailing_space_items = []
    long_path_items      = []
    missing_items        = []

    for item, org_entry in pairs:
        if not org_entry:
            continue
        src_dir   = source_override or org_entry['folder']
        disk_name = org_entry['name']
        src       = os.path.join(src_dir, disk_name)

        if not os.path.exists(src):
            missing_items.append(src)
            continue

        for dirpath, dirnames, filenames in os.walk(src):
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                if name != name.rstrip():
                    trailing_space_items.append(full)
                if len(full) > 260:
                    long_path_items.append(full)

    return {
        'trailing_spaces': trailing_space_items,
        'long_paths':      long_path_items,
        'missing':         missing_items,
    }

# ── Pre-sanitize: strip trailing spaces from file/folder names in-place ────────
def _win_longpath(p: str) -> str:
    """Return \\\\?\\-prefixed path for extended-length path API on Windows."""
    if p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)

def strip_trailing_spaces(root: str) -> list:
    """
    Rename any file or directory under `root` that has trailing spaces in its name.
    Returns list of (old_path, new_path) renames performed.

    Uses \\\\?\\ extended-length prefix so Windows does NOT strip the trailing
    space when building the source path (the normal API normalises it away, making
    os.rename silently fail — the fix is to bypass normalisation via \\\\?\\).
    """
    renamed = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames + dirnames:
            if name != name.rstrip():
                old = os.path.join(dirpath, name)
                new = os.path.join(dirpath, name.rstrip())
                if not os.path.exists(new):
                    try:
                        # Use extended-length prefix so Windows doesn't normalise
                        # the trailing space away before the rename syscall
                        os.rename(_win_longpath(old), _win_longpath(new))
                        renamed.append((old, new))
                    except Exception as e:
                        # Log silently — robust_move will still attempt robocopy
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

def load_all_with_index(source_mode: str = 'ae') -> list:
    """
    Returns list of (classified_item, index_entry) tuples.
    source_mode='ae'     → batch_NNN.json + unorg_batch_NNN.json → org_index.json
    source_mode='design' → design_batch_NNN.json → design_unorg_index.json
    """
    org = load_index_for_source(source_mode)
    pairs = []

    if source_mode == 'design':
        glob_pattern = 'design_batch_*.json'
    else:
        # AE mode: load batch_NNN.json and unorg_batch_NNN.json; skip design_batch files
        glob_pattern = '*.json'

    for p in sorted(Path(RESULTS_DIR).glob(glob_pattern)):
        stem = p.stem
        # In AE mode, skip design_batch files
        if source_mode == 'ae' and stem.startswith('design_batch_'):
            continue
        # In design mode, only design_batch files
        if source_mode == 'design' and not stem.startswith('design_batch_'):
            continue

        items = load_one(str(p))
        offset = batch_offset(p.name, source_mode)
        for i, item in enumerate(items):
            idx_pos   = offset + i
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
        category = normalize_category(item.get('category', 'After Effects - Other').strip())
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
                # Journal every successful move for undo support
                journal_record(src, dest, disk_name, clean, category, conf)
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
            journal_record(src, dest, e['disk_name'], e.get('clean_name', ''),
                           e.get('category', ''), int(e.get('confidence', 0)))
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

def cmd_validate(pairs: list, source_override: str = ''):
    """Pre-flight scan: find trailing spaces and long paths before attempting moves."""
    print("\nRunning pre-flight validation on source directories...")
    report = validate_sources(pairs, source_override)
    ts = report['trailing_spaces']
    lp = report['long_paths']
    ms = report['missing']
    print(f"\n  Trailing-space names : {len(ts)}")
    for p in ts[:20]:
        print(f"    {p!r}")
    if len(ts) > 20:
        print(f"    ... {len(ts) - 20} more")
    print(f"\n  Long paths (>260)    : {len(lp)}")
    for p in lp[:20]:
        print(f"    {p!r}")
    if len(lp) > 20:
        print(f"    ... {len(lp) - 20} more")
    print(f"\n  Missing sources      : {len(ms)}")
    for p in ms[:10]:
        print(f"    {p!r}")
    would_error = len(ts) + len(lp)
    print(f"\nPre-flight summary: {would_error} items would need remediation before apply")
    if would_error == 0:
        print("All sources look clean — safe to run --apply")
    else:
        print("Run --apply anyway (auto-remediates both issues via robocopy + pre-sanitize)")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview',       action='store_true', help='Dry run (default)')
    ap.add_argument('--apply',         action='store_true', help='Apply moves')
    ap.add_argument('--validate',      action='store_true', help='Pre-flight: scan for WinError 2/3 sources')
    ap.add_argument('--retry-errors',  action='store_true', help='Retry items in organize_errors.json')
    ap.add_argument('--undo-last',     type=int, metavar='N', help='Reverse last N moves from journal')
    ap.add_argument('--undo-all',      action='store_true',   help='Reverse ALL moves from journal')
    ap.add_argument('--load',          type=str,            help='Single JSON file (skips position mapping)')
    ap.add_argument('--source',        type=str, default='ae',
                    choices=['ae', 'design'],
                    help='Source mode: ae (default, I:\\After Effects + I:\\Unorganized) or design (G:\\Design Unorganized)')
    ap.add_argument('--stats',         action='store_true', help='Show batch file counts')
    ap.add_argument('--summary',       action='store_true', help='Category/marketplace breakdown')
    ap.add_argument('--quiet',         action='store_true', help='Suppress per-item output')
    args = ap.parse_args()

    if args.retry_errors:
        retry_errors()
        return

    if args.undo_last:
        undo_moves(last_n=args.undo_last)
        return

    if args.undo_all:
        undo_moves(last_n=0)
        return

    source_mode = args.source   # 'ae' or 'design'

    if args.stats:
        files = sorted(Path(RESULTS_DIR).glob('*.json'))
        total = 0
        print(f"\nClassification results ({RESULTS_DIR}):")
        for fp in files:
            items = load_one(str(fp))
            offset = batch_offset(fp.name, source_mode)
            print(f"  {fp.name:<35} {len(items):>4} items  [index {offset}–{offset+len(items)-1}]")
            total += len(items)
        print(f"\n  Total: {total} items across {len(files)} files")
        if os.path.exists(JOURNAL_FILE):
            con = _journal_conn()
            n_moved  = con.execute("SELECT COUNT(*) FROM moves WHERE undone_at IS NULL").fetchone()[0]
            n_undone = con.execute("SELECT COUNT(*) FROM moves WHERE undone_at IS NOT NULL").fetchone()[0]
            con.close()
            print(f"\n  Moves journal: {n_moved} active moves, {n_undone} undone")
        return

    if args.load:
        org = load_index_for_source(source_mode)
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
        pairs = load_all_with_index(source_mode)
        log(f"Loaded {len(pairs)} items via position-based index mapping (source={source_mode})")

    # Determine the source directory override for design mode
    source_dir_override = ''
    if source_mode == 'design':
        source_dir_override = r'G:\Design Unorganized'

    if args.validate:
        cmd_validate(pairs, source_dir_override)
        return

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
    apply_moves(pairs, source_dir_override, dry_run=dry, verbose=verbose)

if __name__ == '__main__':
    main()
