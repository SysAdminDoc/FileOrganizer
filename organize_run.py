#!/usr/bin/env python3
"""Agentic organization runner — applies classified items to destination.

Usage:
    python organize_run.py --preview            # dry run all batches
    python organize_run.py --apply              # apply all batches
    python organize_run.py --preview --load F   # dry run single file
    python organize_run.py --preview --plan-out plan.json
    python organize_run.py --apply-plan plan.json
    python organize_run.py --report RUN_ID --output report.md
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
    - Every planned/applied move is journaled to organize_moves.db for full undo support
    - Errors logged to organize_errors.json for retry/audit
"""
import os, sys, json, shutil, re, argparse, subprocess, sqlite3
from pathlib import Path
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

# ── Config ────────────────────────────────────────────────────────────────────
DEST_PRIMARY     = r'G:\Organized'
DEST_OVERFLOW    = r'I:\Organized'   # used automatically when G:\ free < MIN_FREE_GB
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
ERRORS_FILE      = os.path.join(os.path.dirname(__file__), 'organize_errors.json')  # legacy path
JOURNAL_FILE     = os.path.join(os.path.dirname(__file__), 'organize_moves.db')
RESULTS_DIR      = os.path.join(os.path.dirname(__file__), 'classification_results')
PLANS_DIR        = os.path.join(os.path.dirname(__file__), 'organize_plans')
REPORTS_DIR      = os.path.join(os.path.dirname(__file__), 'organize_reports')
PLAN_SCHEMA_VERSION = 1
os.makedirs(RESULTS_DIR, exist_ok=True)

def errors_file(source_mode: str) -> str:
    """Return source-specific errors file path so concurrent apply runs don't clobber each other."""
    return os.path.join(os.path.dirname(__file__), f'organize_errors_{source_mode}.json')

# ── Category name normalization ──────────────────────────────────────────────
# Canonical names (right-hand side).  Any batch that returns a left-hand key
# will be silently rewritten before the destination path is computed.
# This handles cross-batch inconsistencies (AE vs Design classifiers used
# slightly different names for the same category).
CATEGORY_ALIASES = {
    # word-order variant from the AE classifier
    'After Effects - Opener & Intro':   'After Effects - Intro & Opener',
    # old short names — "Title & Typography" is the canonical form
    'After Effects - Typography':       'After Effects - Title & Typography',
    'After Effects - Titles & Typography': 'After Effects - Title & Typography',
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
    # Photoshop aliases (from older reclassify batches)
    'Photoshop - Templates & Mockups':  'Photoshop - Smart Objects & Templates',
    'Photoshop - Social Media':         'Photoshop - Smart Objects & Templates',
    'Print - Templates & Layouts':      'Print - Other',
}

def normalize_category(cat: str) -> str:
    """Return the canonical category name, resolving any known alias."""
    return CATEGORY_ALIASES.get(cat, cat)

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg, also_print=True):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    if also_print:
        # Encode to cp1252 safely (replace unmappable chars) for Windows consoles
        print(line.encode('cp1252', errors='replace').decode('cp1252'))
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
    undone_at   TEXT,
    plan_id     TEXT,
    plan_item_id TEXT,
    run_id      TEXT,
    status      TEXT DEFAULT 'done',
    error       TEXT,
    planned_at  TEXT,
    updated_at  TEXT,
    partial_dest_exists INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_moves_moved_at ON moves(moved_at);
CREATE INDEX IF NOT EXISTS idx_moves_undone   ON moves(undone_at);
"""

_JOURNAL_MIGRATIONS = {
    'plan_id': "ALTER TABLE moves ADD COLUMN plan_id TEXT",
    'plan_item_id': "ALTER TABLE moves ADD COLUMN plan_item_id TEXT",
    'run_id': "ALTER TABLE moves ADD COLUMN run_id TEXT",
    'status': "ALTER TABLE moves ADD COLUMN status TEXT DEFAULT 'done'",
    'error': "ALTER TABLE moves ADD COLUMN error TEXT",
    'planned_at': "ALTER TABLE moves ADD COLUMN planned_at TEXT",
    'updated_at': "ALTER TABLE moves ADD COLUMN updated_at TEXT",
    'partial_dest_exists': "ALTER TABLE moves ADD COLUMN partial_dest_exists INTEGER DEFAULT 0",
}

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _compact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def _ensure_journal_columns(con: sqlite3.Connection):
    existing = {row[1] for row in con.execute("PRAGMA table_info(moves)").fetchall()}
    for column, sql in _JOURNAL_MIGRATIONS.items():
        if column not in existing:
            con.execute(sql)
    con.execute("UPDATE moves SET status='done' WHERE status IS NULL OR status=''")
    con.execute("CREATE INDEX IF NOT EXISTS idx_moves_status ON moves(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_moves_plan_id ON moves(plan_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_moves_run_id ON moves(run_id)")

def _journal_conn() -> sqlite3.Connection:
    con = sqlite3.connect(JOURNAL_FILE)
    con.row_factory = sqlite3.Row
    con.executescript(_JOURNAL_SCHEMA)
    _ensure_journal_columns(con)
    con.commit()
    return con

def journal_record(src: str, dest: str, disk_name: str,
                   clean_name: str, category: str, confidence: int,
                   status: str = 'done', plan_id: str = '',
                   plan_item_id: str = '', run_id: str = '',
                   error: str = '', partial_dest_exists: bool = False) -> int:
    """Record a planned/completed move in the SQLite journal and return its row id."""
    now = _utc_now()
    con = _journal_conn()
    cur = con.execute(
        "INSERT INTO moves (src, dest, disk_name, clean_name, category, confidence, moved_at, "
        "plan_id, plan_item_id, run_id, status, error, planned_at, updated_at, partial_dest_exists) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (src, dest, disk_name, clean_name, category, confidence, now,
         plan_id, plan_item_id, run_id, status, error, now, now, int(partial_dest_exists))
    )
    con.commit()
    row_id = cur.lastrowid
    con.close()
    return row_id

def journal_update(move_id: int, status: str, error: str = '',
                   partial_dest_exists: bool = False):
    """Update a journal row status after a plan item succeeds or fails."""
    con = _journal_conn()
    con.execute(
        "UPDATE moves SET status=?, error=?, updated_at=?, partial_dest_exists=? WHERE id=?",
        (status, error, _utc_now(), int(partial_dest_exists), move_id)
    )
    con.commit()
    con.close()

def journal_src_exists(src: str) -> bool:
    """Return True if this source path is already recorded as moved (not undone)."""
    if not os.path.exists(JOURNAL_FILE):
        return False
    con = _journal_conn()
    row = con.execute(
        "SELECT 1 FROM moves WHERE src = ? AND undone_at IS NULL "
        "AND COALESCE(status, 'done') IN ('pending', 'done') LIMIT 1", (src,)
    ).fetchone()
    con.close()
    return row is not None

def journal_src_set() -> set:
    """Return a set of all src paths already moved (not undone) — for bulk skip checks."""
    if not os.path.exists(JOURNAL_FILE):
        return set()
    con = _journal_conn()
    rows = con.execute(
        "SELECT src FROM moves WHERE undone_at IS NULL "
        "AND COALESCE(status, 'done') IN ('pending', 'done')"
    ).fetchall()
    con.close()
    return {r[0] for r in rows}

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
            "SELECT * FROM moves WHERE undone_at IS NULL "
            "AND COALESCE(status, 'done')='done' ORDER BY id DESC LIMIT ?", (last_n,)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM moves WHERE undone_at IS NULL "
            "AND COALESCE(status, 'done')='done' ORDER BY id DESC"
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
                    "UPDATE moves SET undone_at=?, status=?, updated_at=? WHERE id=?",
                    (_utc_now(), 'undone', _utc_now(), row['id'])
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
    if source_mode == 'design':
        path = DESIGN_INDEX_FILE
    elif source_mode == 'design_org':
        path = os.path.join(os.path.dirname(__file__), 'design_org_index.json')
    elif source_mode == 'loose_files':
        path = os.path.join(os.path.dirname(__file__), 'loose_files_index.json')
    elif source_mode == 'design_elements':
        path = os.path.join(os.path.dirname(__file__), 'design_elements_index.json')
    else:
        path = INDEX_FILE
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
      Design Org mode:
        design_org_batch_001.json → 0
      Loose files mode:
        loose_batch_001.json → 0
    """
    stem = Path(filename).stem
    if stem.startswith('design_org_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('de_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('loose_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('design_batch_'):
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
def _lp(path: str) -> str:
    """Return a \\\\?\\-prefixed extended-length path for Win32 robocopy calls.
    Normalises forward slashes and strips any existing \\\\?\\ prefix first.
    """
    p = os.path.abspath(path).replace('/', '\\')
    if p.startswith('\\\\?\\'):
        return p
    if p.startswith('\\\\'):          # UNC path
        return '\\\\?\\UNC\\' + p[2:]
    return '\\\\?\\' + p


def robust_move(src: str, dst: str) -> None:
    """
    Move `src` directory to `dst`.
    - Same drive: os.rename (atomic).
    - Cross-drive: robocopy /MOVE /256 (long-path aware), then remove emptied src.
    Both src and dst are passed with \\\\?\\ prefix so robocopy source-scanning
    also honours extended path lengths (not just the destination).
    Raises RuntimeError if robocopy exit code >= 8 (actual failure).
    Robocopy exit codes: 0=nothing to do, 1=files copied, 2=extra files,
    3=mismatched, 4=mismatched+copied, 5-7=combinations — all < 8 = success.
    """
    if not is_cross_drive(src, dst):
        os.rename(src, dst)
        return

    os.makedirs(dst, exist_ok=True)
    result = subprocess.run([
        'robocopy', _lp(src), _lp(dst),
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
    source_mode='ae'              → batch_NNN.json + unorg_batch_NNN.json → org_index.json
    source_mode='design'          → design_batch_NNN.json → design_unorg_index.json
    source_mode='design_org'      → design_org_batch_NNN.json → design_org_index.json
    source_mode='loose_files'     → loose_batch_NNN.json → loose_files_index.json
    source_mode='design_elements' → de_batch_NNN.json → design_elements_index.json
    """
    org = load_index_for_source(source_mode)
    pairs = []

    if source_mode == 'design':
        glob_pattern = 'design_batch_*.json'
    elif source_mode == 'design_org':
        glob_pattern = 'design_org_batch_*.json'
    elif source_mode == 'loose_files':
        glob_pattern = 'loose_batch_*.json'
    elif source_mode == 'design_elements':
        glob_pattern = 'de_batch_*.json'
    else:
        glob_pattern = '*.json'

    for p in sorted(Path(RESULTS_DIR).glob(glob_pattern)):
        stem = p.stem
        # In AE mode, skip design/org/loose/de batch files
        if source_mode == 'ae' and stem.startswith(('design_batch_', 'design_org_batch_', 'loose_batch_', 'de_batch_')):
            continue
        # In design mode, only design_batch files
        if source_mode == 'design' and not stem.startswith('design_batch_'):
            continue
        # In design_org mode, only design_org_batch files
        if source_mode == 'design_org' and not stem.startswith('design_org_batch_'):
            continue
        # In loose_files mode, only loose_batch files
        if source_mode == 'loose_files' and not stem.startswith('loose_batch_'):
            continue
        # In design_elements mode, only de_batch files
        if source_mode == 'design_elements' and not stem.startswith('de_batch_'):
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
    """Return primary destination, or overflow if primary is running low on space."""
    try:
        free_bytes = shutil.disk_usage(DEST_PRIMARY[:3]).free
        if free_bytes > MIN_FREE_GB * 1_073_741_824:
            return DEST_PRIMARY
    except Exception:
        pass
    os.makedirs(DEST_OVERFLOW, exist_ok=True)
    return DEST_OVERFLOW

def sanitize(s: str, maxlen: int = 120) -> str:
    return re.sub(r'[<>:"/\\|?*]', '-', s).strip()[:maxlen]

def _cat_path(dest_root: str, category: str) -> str:
    """
    Build the category sub-path under dest_root, preserving multi-level categories.

    category may be a single name  ('After Effects - Slideshow')
    or a path-joined two-level str ('_Review\\After Effects - Slideshow')
    as produced by os.path.join(REVIEW_SUBDIR, category) in apply_moves.

    Each component is sanitized independently so the backslash separator is
    never eaten by sanitize() — which previously collapsed
    '_Review\\After Effects - Other' → '_Review-After Effects - Other'.
    """
    parts = [p for p in category.replace('\\', '/').split('/') if p]
    return os.path.join(dest_root, *[sanitize(p) for p in parts])

def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))

def _path_taken(path: str, reserved: set | None = None) -> bool:
    return os.path.exists(path) or (reserved is not None and _path_key(path) in reserved)

def safe_dest_path(dest_root: str, category: str, clean_name: str,
                   reserved: set | None = None) -> str:
    dest = os.path.join(_cat_path(dest_root, category), sanitize(clean_name))
    if _path_taken(dest, reserved):
        base, i = dest, 1
        while _path_taken(dest, reserved):
            dest = f"{base} ({i})"
            i += 1
    return dest

def safe_dest_path_file(dest_root: str, category: str, clean_name: str, ext: str,
                        reserved: set | None = None) -> str:
    """Build collision-safe destination path for a flat file (not a directory)."""
    cat_dir = _cat_path(dest_root, category)
    stem    = sanitize(clean_name)
    dest    = os.path.join(cat_dir, f"{stem}{ext}")
    if _path_taken(dest, reserved):
        i = 1
        while _path_taken(dest, reserved):
            dest = os.path.join(cat_dir, f"{stem} ({i}){ext}")
            i += 1
    return dest

# ── Move plans ────────────────────────────────────────────────────────────────
@dataclass
class MovePlanItem:
    id: str
    source_mode: str
    src: str
    dest: str
    disk_name: str
    clean_name: str
    category: str
    effective_category: str
    confidence: int
    is_file_item: bool = False
    file_ext: str = ''
    low_confidence: bool = False
    status: str = 'planned'
    reason: str = ''
    error: str = ''

@dataclass
class MovePlan:
    schema_version: int
    plan_id: str
    created_at: str
    source_mode: str
    dest_root: str
    min_confidence: int
    item_count: int
    category_counts: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    items: list = field(default_factory=list)

def _default_plan_path(plan_id: str) -> str:
    return os.path.join(PLANS_DIR, f"{plan_id}.json")

def _default_report_path(report_id: str) -> str:
    return os.path.join(REPORTS_DIR, f"{report_id}.md")

def _plan_dict(plan: MovePlan | dict) -> dict:
    return asdict(plan) if isinstance(plan, MovePlan) else plan

def write_move_plan(plan: MovePlan | dict, path: str = '') -> str:
    plan_data = _plan_dict(plan)
    out = path or _default_plan_path(plan_data['plan_id'])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(plan_data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return out

def read_move_plan(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if int(data.get('schema_version', 0)) != PLAN_SCHEMA_VERSION:
        raise ValueError(f"Unsupported plan schema: {data.get('schema_version')!r}")
    if not isinstance(data.get('items'), list):
        raise ValueError("Move plan missing items list")
    return data

def build_move_plan(pairs: list, source_override: str = '',
                    source_mode: str = 'ae', plan_id: str = '') -> MovePlan:
    """Convert classified/index pairs into an editable, collision-safe move plan."""
    plan_id = plan_id or f"plan-{_compact_timestamp()}"
    created_at = _utc_now()
    first_dest_root = get_dest_root()
    planned = []
    skipped = []
    category_counts = defaultdict(int)
    reserved_dests = set()
    already_moved = journal_src_set()
    last_dest_root = first_dest_root

    for item, org_entry in pairs:
        dest_root = get_dest_root()
        last_dest_root = dest_root
        raw_name = item.get('name', '?')
        category = normalize_category(item.get('category', 'After Effects - Other').strip())
        try:
            conf = int(item.get('confidence', 0))
        except (TypeError, ValueError):
            conf = 0

        if not org_entry:
            skipped.append({'name': raw_name, 'reason': 'not_in_index'})
            continue

        is_file_item = bool(org_entry.get('is_file'))
        if 'path' in org_entry:
            src = org_entry['path']
            disk_name = os.path.basename(src)
        else:
            src_dir = source_override or org_entry['folder']
            disk_name = org_entry['name']
            src = os.path.join(src_dir, disk_name)

        clean = (item.get('clean_name') or raw_name or '').strip()
        if not clean:
            clean = Path(disk_name).stem or disk_name or 'Unnamed Asset'

        if not os.path.exists(src):
            skipped.append({'name': disk_name, 'src': src, 'reason': 'missing_source'})
            continue
        if src in already_moved:
            skipped.append({'name': disk_name, 'src': src, 'reason': 'already_moved'})
            continue

        low_conf = conf < MIN_CONFIDENCE
        eff_category = os.path.join(REVIEW_SUBDIR, category) if low_conf else category

        if is_file_item:
            file_ext = org_entry.get('file_ext', Path(src).suffix.lower())
            disk_stem = sanitize(Path(disk_name).stem)
            dest_stem = disk_stem if disk_stem else clean
            dest = safe_dest_path_file(dest_root, eff_category, dest_stem, file_ext, reserved_dests)
        else:
            file_ext = ''
            dest = safe_dest_path(dest_root, eff_category, clean, reserved_dests)

        reserved_dests.add(_path_key(dest))
        category_counts[category] += 1
        planned.append(asdict(MovePlanItem(
            id=f"{source_mode}-{len(planned) + 1:06d}",
            source_mode=source_mode,
            src=src,
            dest=dest,
            disk_name=disk_name,
            clean_name=clean,
            category=category,
            effective_category=eff_category,
            confidence=conf,
            is_file_item=is_file_item,
            file_ext=file_ext,
            low_confidence=low_conf,
        )))

    return MovePlan(
        schema_version=PLAN_SCHEMA_VERSION,
        plan_id=plan_id,
        created_at=created_at,
        source_mode=source_mode,
        dest_root=last_dest_root,
        min_confidence=MIN_CONFIDENCE,
        item_count=len(planned),
        category_counts=dict(sorted(category_counts.items())),
        skipped=skipped,
        items=planned,
    )

def _move_plan_item(item: dict):
    src = item['src']
    dest = item['dest']
    if os.path.exists(dest):
        raise FileExistsError(f"Destination already exists: {dest}")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if item.get('is_file_item'):
        try:
            os.rename(src, dest)
        except OSError:
            shutil.move(src, dest)
    else:
        renamed = strip_trailing_spaces(src)
        if renamed:
            log(f"    Pre-sanitized {len(renamed)} name(s) with trailing spaces in {item['disk_name']!r}")
        robust_move(src, dest)

def apply_move_plan(plan: MovePlan | dict, dry_run: bool = False,
                    verbose: bool = True) -> dict:
    """Apply an editable move plan and journal pending/done/failed transitions."""
    plan_data = _plan_dict(plan)
    source_mode = plan_data.get('source_mode', 'ae')
    plan_id = plan_data.get('plan_id') or f"plan-{_compact_timestamp()}"
    run_id = f"{plan_id}-run-{_compact_timestamp()}"
    moved = skipped = errors = 0
    low_conf = sum(1 for item in plan_data.get('items', []) if item.get('low_confidence'))
    category_counts = defaultdict(int)
    error_log = []
    already_moved = journal_src_set()

    for item in plan_data.get('items', []):
        src = item['src']
        dest = item['dest']
        disk_name = item.get('disk_name', os.path.basename(src))
        category = item.get('category', 'Unknown')
        category_counts[category] += 1

        if src in already_moved:
            skipped += 1
            continue

        if verbose:
            tag = '[DRY-PLAN]' if dry_run else '[MOVE]'
            flag = f"  *** LOW CONF={item.get('confidence', 0)}" if item.get('low_confidence') else ''
            log(f"  {tag} {disk_name!r}")
            log(f"    -> {dest}  [{item.get('confidence', 0)}]{flag}", also_print=verbose)

        if dry_run:
            moved += 1
            continue

        move_id = journal_record(
            src, dest, disk_name, item.get('clean_name', ''), category,
            int(item.get('confidence', 0)), status='pending',
            plan_id=plan_id, plan_item_id=item.get('id', ''), run_id=run_id,
        )

        try:
            if not os.path.exists(src):
                raise FileNotFoundError(f"Source missing: {src}")
            _move_plan_item(item)
            journal_update(move_id, 'done')
            already_moved.add(src)
            moved += 1
        except Exception as e:
            err_msg = str(e)
            partial = os.path.exists(dest)
            journal_update(move_id, 'failed', err_msg, partial_dest_exists=partial)
            log(f"    ERROR moving {disk_name!r}: {err_msg}")
            errors += 1
            error_log.append({
                'disk_name': disk_name,
                'src': src,
                'dest': dest,
                'category': category,
                'clean_name': item.get('clean_name', ''),
                'confidence': int(item.get('confidence', 0)),
                'error': err_msg,
                'partial_dest_exists': partial,
                'plan_id': plan_id,
                'plan_item_id': item.get('id', ''),
                'run_id': run_id,
            })

    tag = 'DRY PLAN' if dry_run else 'APPLIED PLAN'
    log(f"\n{tag}: {moved} moved, {skipped} skipped, {errors} errors, "
        f"{low_conf} low-conf routed to {REVIEW_SUBDIR}/")
    if plan_data.get('skipped'):
        by_reason = defaultdict(int)
        for item in plan_data['skipped']:
            by_reason[item.get('reason', 'unknown')] += 1
        reason_text = ', '.join(f"{reason}={count}" for reason, count in sorted(by_reason.items()))
        log(f"Plan skipped {len(plan_data['skipped'])} item(s): {reason_text}")

    if not dry_run and error_log:
        efile = errors_file(source_mode)
        with open(efile, 'w', encoding='utf-8') as f:
            json.dump(error_log, f, indent=2, ensure_ascii=False)
        log(f"\nErrors written to {efile} — run --retry-errors --source {source_mode} to attempt fixes")

    return {
        'plan_id': plan_id,
        'run_id': run_id,
        'moved': moved,
        'skipped': skipped,
        'errors': errors,
        'low_confidence': low_conf,
        'category_counts': dict(category_counts),
    }

def apply_moves(pairs: list, source_override: str,
                dry_run: bool = True, verbose: bool = True,
                source_mode: str = 'ae'):
    """Compatibility wrapper: build a move plan, then dry-run or apply it."""
    plan = build_move_plan(pairs, source_override, source_mode)
    result = apply_move_plan(plan, dry_run=dry_run, verbose=verbose)
    return result['moved'], result['skipped'], result['errors'], result['category_counts']

# ── CLI ───────────────────────────────────────────────────────────────────────
def retry_errors(source_mode: str = 'ae'):
    """Re-attempt items from the source-specific errors file."""
    efile = errors_file(source_mode)
    # Fall back to legacy path if source-specific file doesn't exist yet
    if not os.path.exists(efile) and os.path.exists(ERRORS_FILE):
        efile = ERRORS_FILE
    if not os.path.exists(efile):
        print(f"No errors file found at {efile}")
        return
    with open(efile, 'r', encoding='utf-8') as f:
        errors = json.load(f)
    log(f"Retrying {len(errors)} errored items (source={source_mode})...")
    retried = fixed = still_failed = 0
    remaining = []
    for e in errors:
        src  = e['src']
        # Recompute destination using current dest root so disk-full retries
        # automatically redirect to I:\Organized when G:\ is still low.
        dest_root   = get_dest_root()
        eff_cat     = e.get('category', '')
        clean       = e.get('clean_name', '')
        conf        = int(e.get('confidence', 0))
        if conf < MIN_CONFIDENCE:
            eff_cat = os.path.join(REVIEW_SUBDIR, eff_cat)
        # Prefer recomputed dest; fall back to stored dest if category data missing
        if eff_cat and clean:
            dest = safe_dest_path(dest_root, eff_cat, clean)
        else:
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
        with open(efile, 'w', encoding='utf-8') as f:
            json.dump(remaining, f, indent=2, ensure_ascii=False)
        log(f"Remaining errors saved to {efile}")
    else:
        os.remove(efile)
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

def _md_cell(value) -> str:
    text = str(value if value is not None else '')
    return text.replace('\\', '\\\\').replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')

def _report_name(identifier: str) -> str:
    return sanitize(identifier.replace(os.sep, '-'), 100) or f"report-{_compact_timestamp()}"

def generate_report(identifier: str, output: str = '') -> str:
    """Generate a Markdown report from a run id, plan id, or plan JSON path."""
    generated_at = _utc_now()
    rows = []
    skipped = []
    report_title = identifier

    if os.path.exists(identifier):
        plan = read_move_plan(identifier)
        report_title = plan.get('plan_id', identifier)
        rows = [
            {
                'status': item.get('status', 'planned'),
                'src': item.get('src', ''),
                'dest': item.get('dest', ''),
                'disk_name': item.get('disk_name', ''),
                'clean_name': item.get('clean_name', ''),
                'category': item.get('category', ''),
                'confidence': item.get('confidence', 0),
                'error': item.get('error', ''),
                'partial_dest_exists': 0,
            }
            for item in plan.get('items', [])
        ]
        skipped = plan.get('skipped', [])
    else:
        con = _journal_conn()
        found = con.execute(
            "SELECT * FROM moves WHERE run_id=? OR plan_id=? ORDER BY id",
            (identifier, identifier)
        ).fetchall()
        con.close()
        rows = [dict(row) for row in found]
        if not rows:
            raise RuntimeError(f"No journal entries found for report id: {identifier}")

    status_counts = defaultdict(int)
    category_counts = defaultdict(int)
    low_conf = 0
    for row in rows:
        status_counts[row.get('status') or 'unknown'] += 1
        category_counts[row.get('category') or 'Unknown'] += 1
        try:
            if int(row.get('confidence') or 0) < MIN_CONFIDENCE:
                low_conf += 1
        except (TypeError, ValueError):
            pass

    out = output or _default_report_path(_report_name(report_title))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    lines = [
        '# FileOrganizer Move Report',
        '',
        f'- Report id: `{_md_cell(report_title)}`',
        f'- Generated: `{generated_at}`',
        f'- Items: `{len(rows)}`',
        f'- Low confidence: `{low_conf}`',
        f'- Skipped before planning: `{len(skipped)}`',
        '',
        '## Status Summary',
        '',
        '| Status | Count |',
        '|---|---:|',
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"| {_md_cell(status)} | {count} |")

    lines.extend(['', '## Category Summary', '', '| Category | Count |', '|---|---:|'])
    for category, count in sorted(category_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| {_md_cell(category)} | {count} |")

    failures = [row for row in rows if (row.get('status') == 'failed' or row.get('error'))]
    if failures:
        lines.extend(['', '## Failures', '', '| Item | Error | Partial Dest |', '|---|---|---:|'])
        for row in failures:
            lines.append(
                f"| {_md_cell(row.get('disk_name') or row.get('clean_name'))} "
                f"| {_md_cell(row.get('error'))} "
                f"| {int(bool(row.get('partial_dest_exists')))} |"
            )

    if skipped:
        lines.extend(['', '## Skipped Before Planning', '', '| Item | Reason | Source |', '|---|---|---|'])
        for row in skipped:
            lines.append(
                f"| {_md_cell(row.get('name', ''))} | {_md_cell(row.get('reason', ''))} "
                f"| {_md_cell(row.get('src', ''))} |"
            )

    lines.extend([
        '',
        '## Items',
        '',
        '| Status | Confidence | Category | Source | Destination |',
        '|---|---:|---|---|---|',
    ])
    for row in rows:
        lines.append(
            f"| {_md_cell(row.get('status', 'planned'))} "
            f"| {_md_cell(row.get('confidence', 0))} "
            f"| {_md_cell(row.get('category', ''))} "
            f"| `{_md_cell(row.get('src', ''))}` "
            f"| `{_md_cell(row.get('dest', ''))}` |"
        )

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview',       action='store_true', help='Dry run (default)')
    ap.add_argument('--apply',         action='store_true', help='Apply moves')
    ap.add_argument('--plan-out',      type=str,            help='Write generated move plan to this JSON path')
    ap.add_argument('--apply-plan',    type=str,            help='Apply a previously generated move plan JSON')
    ap.add_argument('--report',        type=str,            help='Generate Markdown report for a run id, plan id, or plan JSON path')
    ap.add_argument('--output',        type=str,            help='Output path for --report')
    ap.add_argument('--validate',      action='store_true', help='Pre-flight: scan for WinError 2/3 sources')
    ap.add_argument('--retry-errors',  action='store_true', help='Retry items in organize_errors.json')
    ap.add_argument('--undo-last',     type=int, metavar='N', help='Reverse last N moves from journal')
    ap.add_argument('--undo-all',      action='store_true',   help='Reverse ALL moves from journal')
    ap.add_argument('--load',          type=str,            help='Single JSON file (skips position mapping)')
    ap.add_argument('--source',        type=str, default='ae',
                    choices=['ae', 'design', 'design_org', 'loose_files', 'design_elements'],
                    help='Source mode: ae (default), design, design_org, loose_files, or design_elements')
    ap.add_argument('--stats',         action='store_true', help='Show batch file counts')
    ap.add_argument('--summary',       action='store_true', help='Category/marketplace breakdown')
    ap.add_argument('--quiet',         action='store_true', help='Suppress per-item output')
    args = ap.parse_args()

    if args.report:
        out = generate_report(args.report, args.output or '')
        print(f"Report written: {out}")
        return

    if args.apply_plan:
        plan = read_move_plan(args.apply_plan)
        result = apply_move_plan(plan, dry_run=(args.preview and not args.apply), verbose=not args.quiet)
        print(f"Plan id: {result['plan_id']}")
        print(f"Run id: {result['run_id']}")
        print(f"Moved={result['moved']} skipped={result['skipped']} errors={result['errors']}")
        return

    if args.retry_errors:
        retry_errors(args.source)
        return

    if args.undo_last:
        undo_moves(last_n=args.undo_last)
        return

    if args.undo_all:
        undo_moves(last_n=0)
        return

    source_mode = args.source

    if args.stats:
        files = sorted(Path(RESULTS_DIR).glob('*.json'))
        total = 0
        print(f"\nClassification results ({RESULTS_DIR}):")
        for fp in files:
            items = load_one(str(fp))
            offset = batch_offset(fp.name, source_mode)
            print(f"  {fp.name:<35} {len(items):>4} items  [index {offset}-{offset+len(items)-1}]")
            total += len(items)
        print(f"\n  Total: {total} items across {len(files)} files")
        if os.path.exists(JOURNAL_FILE):
            con = _journal_conn()
            n_moved  = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NULL AND COALESCE(status, 'done')='done'"
            ).fetchone()[0]
            n_pending = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NULL AND COALESCE(status, 'done')='pending'"
            ).fetchone()[0]
            n_failed = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NULL AND COALESCE(status, 'done')='failed'"
            ).fetchone()[0]
            n_undone = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NOT NULL OR COALESCE(status, 'done')='undone'"
            ).fetchone()[0]
            con.close()
            print(f"\n  Moves journal: {n_moved} done, {n_pending} pending, {n_failed} failed, {n_undone} undone")
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

    # Determine source directory override per mode
    _SOURCE_DIRS = {
        'design':           r'G:\Design Unorganized',
        'design_org':       r'G:\Design Organized',
        'loose_files':      r'G:\Design Unorganized',
        'design_elements':  r'G:\Design Organized\Design Elements',
    }
    source_dir_override = _SOURCE_DIRS.get(source_mode, '')

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
    plan = build_move_plan(pairs, source_dir_override, source_mode)
    plan_path = write_move_plan(plan, args.plan_out or '')
    log(f"Move plan written: {plan_path}")
    result = apply_move_plan(plan, dry_run=dry, verbose=verbose)
    if not dry:
        log(f"Plan id: {result['plan_id']}")
        log(f"Run id: {result['run_id']}")

if __name__ == '__main__':
    main()
