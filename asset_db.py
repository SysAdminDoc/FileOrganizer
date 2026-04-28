#!/usr/bin/env python3
"""
asset_db.py — Community asset fingerprint database.

Hashes every file in G:\\Organized and stores SHA-256 fingerprints in a
SQLite database so other FileOrganizer users can instantly identify and
classify their own copies of the same templates.

Matching strategy (strongest → weakest):
    exact     — folder fingerprint matches (same set of files)  → conf 100
    project   — a .aep/.psd/.prproj/etc exact hash match        → conf 90
    overlap75 — ≥75 % of file hashes overlap                    → conf 85
    overlap40 — ≥40 % of file hashes overlap                    → conf 60

Usage:
    python asset_db.py --build [G:\\Organized]      # hash + store (incremental)
    python asset_db.py --lookup PATH               # identify an unknown folder
    python asset_db.py --export [out.json]         # export for community sharing
    python asset_db.py --stats                     # DB overview
    python asset_db.py --verify [G:\\Organized]    # check DB vs disk
"""
import os, sys, json, sqlite3, hashlib, argparse, re
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

# ── Config ─────────────────────────────────────────────────────────────────────
DB_FILE           = os.path.join(os.path.dirname(__file__), 'asset_fingerprints.db')
RESULTS_DIR       = os.path.join(os.path.dirname(__file__), 'classification_results')
INDEX_FILE        = os.path.join(os.path.dirname(__file__), 'org_index.json')
EXPORT_FILE       = os.path.join(os.path.dirname(__file__), 'asset_fingerprints.json')
DEFAULT_ORGANIZED = r'G:\Organized'

AE_BATCH_SIZE = 60
AE_TOTAL      = 1136

# Files larger than this are hashed but not stored in asset_files if they
# have a generic extension — large .mp4 preview renders are not unique.
MAX_HASH_BYTES = 300 * 1024 * 1024   # 300 MB hard limit; larger files are skipped

# These extensions identify the "soul" of a template — a hash match here is
# as strong as finding a fingerprint on a person.
PROJECT_EXTS = frozenset({
    '.aep', '.aepx', '.prproj', '.psd', '.psb', '.ai', '.indd',
    '.idml', '.mogrt', '.aet', '.xd', '.fig', '.ppj', '.sesx',
    '.fla', '.flp', '.sketch',
})

DB_VERSION = 1

# ── Schema ──────────────────────────────────────────────────────────────────────
_SCHEMA = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS db_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS assets (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    clean_name         TEXT NOT NULL,
    category           TEXT NOT NULL,
    marketplace        TEXT,
    confidence         INTEGER DEFAULT 0,
    disk_name          TEXT,
    file_count         INTEGER DEFAULT 0,
    total_bytes        INTEGER DEFAULT 0,
    skipped_bytes      INTEGER DEFAULT 0,
    folder_fingerprint TEXT UNIQUE,
    added_at           TEXT NOT NULL,
    updated_at         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_files (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_id        INTEGER NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    filename        TEXT NOT NULL,
    relative_path   TEXT NOT NULL,
    size_bytes      INTEGER NOT NULL,
    sha256          TEXT NOT NULL,
    is_project_file INTEGER NOT NULL DEFAULT 0,
    added_at        TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_files_sha256   ON asset_files(sha256);
CREATE INDEX IF NOT EXISTS idx_files_size     ON asset_files(size_bytes);
CREATE INDEX IF NOT EXISTS idx_assets_fp      ON assets(folder_fingerprint);
CREATE INDEX IF NOT EXISTS idx_assets_name    ON assets(clean_name COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_assets_cat     ON assets(category);
CREATE INDEX IF NOT EXISTS idx_files_asset    ON asset_files(asset_id);
CREATE INDEX IF NOT EXISTS idx_files_proj     ON asset_files(is_project_file, sha256);
"""


def init_db(db_path: str = DB_FILE) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    con.executescript(_SCHEMA)
    now = _now()
    con.execute("INSERT OR IGNORE INTO db_meta VALUES ('version',    ?)", (str(DB_VERSION),))
    con.execute("INSERT OR IGNORE INTO db_meta VALUES ('created_at', ?)", (now,))
    con.commit()
    return con


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def hash_file(path: str) -> str | None:
    """Return SHA-256 hex digest of a file, streamed in 1 MB chunks.
    Returns None if the file is too large or unreadable."""
    try:
        size = os.path.getsize(path)
        if size > MAX_HASH_BYTES:
            return None
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(1_048_576), b''):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, PermissionError):
        return None


def folder_fingerprint(folder_path: str) -> tuple[str | None, list[dict]]:
    """
    Walk `folder_path`, hash every file, and compute a folder-level fingerprint.

    Returns (fingerprint_hex, file_list) where:
      fingerprint_hex — SHA-256 of the sorted "(relative_path|sha256)" strings,
                        giving a stable identifier regardless of directory order.
                        None if no files could be hashed.
      file_list       — [{filename, relative_path, size_bytes, sha256|None,
                          is_project_file, skipped}]
    """
    file_list = []
    root = Path(folder_path)
    for fpath in sorted(root.rglob('*')):
        if not fpath.is_file():
            continue
        rel   = fpath.relative_to(root).as_posix()
        size  = fpath.stat().st_size
        ext   = fpath.suffix.lower()
        sha   = hash_file(str(fpath))
        file_list.append({
            'filename':        fpath.name,
            'relative_path':   rel,
            'size_bytes':      size,
            'sha256':          sha,
            'is_project_file': int(ext in PROJECT_EXTS),
            'skipped':         sha is None,
        })

    # Build fingerprint only from hashed files (so skipped large files don't
    # break identity for otherwise identical templates)
    hashable = sorted(
        f"{f['relative_path']}|{f['sha256']}"
        for f in file_list if f['sha256']
    )
    if not hashable:
        return None, file_list

    fp = hashlib.sha256('\n'.join(hashable).encode()).hexdigest()
    return fp, file_list


# ── Classification results lookup ──────────────────────────────────────────────

def _load_classification_lookup() -> dict:
    """
    Load all batch classification results and return a dict keyed by
    (category_normalized, clean_name_normalized) → {marketplace, confidence, disk_name}.
    Used to enrich database entries with the AI-assigned metadata.
    """
    if not os.path.exists(RESULTS_DIR) or not os.path.exists(INDEX_FILE):
        return {}

    with open(INDEX_FILE, 'r', encoding='utf-8') as f:
        org = json.load(f)

    lookup = {}
    for fp in sorted(Path(RESULTS_DIR).glob('*.json')):
        try:
            items = json.load(open(fp, encoding='utf-8'))
            if isinstance(items, dict):
                items = items.get('results', [])
        except Exception:
            continue

        stem = fp.stem
        if stem.startswith('unorg_batch_'):
            n      = int(stem.split('_')[-1])
            offset = AE_TOTAL + (n - 1) * 100
        elif stem.startswith('batch_'):
            n      = int(stem.split('_')[-1])
            offset = (n - 1) * AE_BATCH_SIZE
        else:
            continue

        for i, item in enumerate(items):
            idx = offset + i
            if idx >= len(org):
                continue
            cat    = (item.get('category') or '').strip()
            clean  = (item.get('clean_name') or item.get('name') or '').strip()
            key    = (_norm(cat), _norm(clean))
            lookup[key] = {
                'marketplace': item.get('marketplace', ''),
                'confidence':  int(item.get('confidence', 0)),
                'disk_name':   org[idx]['name'],
            }
    return lookup


def _norm(s: str) -> str:
    return re.sub(r'[\s_\-]+', ' ', s.strip().lower())


# ── Build ───────────────────────────────────────────────────────────────────────

def build_database(organized_root: str = DEFAULT_ORGANIZED,
                   db_path: str = DB_FILE,
                   progress_cb=None) -> dict:
    """
    Walk `organized_root` (structure: category_dir/asset_dir/...files...) and
    hash every file into the asset fingerprint database.  Incremental: already-
    fingerprinted assets are skipped unless their file count has changed.

    progress_cb(done, total, current_asset_name) — optional progress hook.

    Returns {'added': N, 'updated': N, 'skipped': N, 'errors': N, 'total_files': N}.
    """
    con = init_db(db_path)
    lookup = _load_classification_lookup()

    # Discover asset dirs: organized_root/CATEGORY/ASSET_NAME/
    asset_dirs = []
    root = Path(organized_root)
    if not root.exists():
        print(f"ERROR: {organized_root} does not exist")
        return {}

    for cat_dir in sorted(root.iterdir()):
        if not cat_dir.is_dir():
            continue
        category = cat_dir.name
        for asset_dir in sorted(cat_dir.iterdir()):
            if not asset_dir.is_dir():
                continue
            asset_dirs.append((category, asset_dir.name, str(asset_dir)))

    total    = len(asset_dirs)
    added    = updated = skipped = errors = total_files = 0
    now      = _now()

    print(f"Found {total} asset folders in {organized_root}")

    for i, (category, clean_name, asset_path) in enumerate(asset_dirs):
        if progress_cb:
            progress_cb(i, total, clean_name)

        # Check if already in DB with same file count
        disk_file_count = sum(1 for _ in Path(asset_path).rglob('*') if Path(_).is_file())
        existing = con.execute(
            "SELECT id, file_count, folder_fingerprint FROM assets "
            "WHERE clean_name=? AND category=?",
            (clean_name, category)
        ).fetchone()

        if existing and existing['file_count'] == disk_file_count:
            skipped += 1
            continue

        try:
            fp, file_list = folder_fingerprint(asset_path)
        except Exception as e:
            print(f"  ERROR fingerprinting {clean_name!r}: {e}")
            errors += 1
            continue

        total_bytes   = sum(f['size_bytes'] for f in file_list)
        skipped_bytes = sum(f['size_bytes'] for f in file_list if f['skipped'])
        hashed_files  = [f for f in file_list if not f['skipped']]

        # Enrich with classification lookup
        meta = lookup.get((_norm(category), _norm(clean_name)), {})
        marketplace = meta.get('marketplace', '')
        conf        = meta.get('confidence', 0)
        disk_name   = meta.get('disk_name', '')

        if existing:
            # Update existing record
            con.execute("""
                UPDATE assets SET
                    file_count=?, total_bytes=?, skipped_bytes=?, folder_fingerprint=?,
                    marketplace=?, confidence=?, disk_name=?, updated_at=?
                WHERE id=?
            """, (disk_file_count, total_bytes, skipped_bytes, fp,
                  marketplace, conf, disk_name, now, existing['id']))
            asset_id = existing['id']
            # Remove old file rows and re-insert
            con.execute("DELETE FROM asset_files WHERE asset_id=?", (asset_id,))
            updated += 1
        else:
            cur = con.execute("""
                INSERT INTO assets
                    (clean_name, category, marketplace, confidence, disk_name,
                     file_count, total_bytes, skipped_bytes, folder_fingerprint,
                     added_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """, (clean_name, category, marketplace, conf, disk_name,
                  disk_file_count, total_bytes, skipped_bytes, fp, now, now))
            asset_id = cur.lastrowid
            added += 1

        # Insert file rows
        rows = [
            (asset_id, f['filename'], f['relative_path'],
             f['size_bytes'], f['sha256'], f['is_project_file'], now)
            for f in hashed_files
        ]
        con.executemany(
            "INSERT INTO asset_files "
            "(asset_id, filename, relative_path, size_bytes, sha256, is_project_file, added_at) "
            "VALUES (?,?,?,?,?,?,?)",
            rows
        )
        total_files += len(rows)

        if (i + 1) % 50 == 0 or i == total - 1:
            con.commit()
            pct = int((i + 1) / total * 100)
            print(f"  [{pct:3d}%] {i+1}/{total}  added={added} updated={updated} "
                  f"skipped={skipped} errors={errors}")

    con.execute("INSERT OR REPLACE INTO db_meta VALUES ('last_build', ?)", (_now(),))
    con.execute("INSERT OR REPLACE INTO db_meta VALUES ('asset_count', ?)",
                (str(con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]),))
    con.commit()
    con.close()

    result = {'added': added, 'updated': updated, 'skipped': skipped,
              'errors': errors, 'total_files': total_files}
    print(f"\nBuild complete: {added} added, {updated} updated, {skipped} unchanged, "
          f"{errors} errors, {total_files} files hashed")
    return result


# ── Lookup ──────────────────────────────────────────────────────────────────────

def lookup_folder(folder_path: str, db_path: str = DB_FILE) -> dict | None:
    """
    Identify an unknown asset folder against the fingerprint database.

    Returns a match dict or None:
    {
        'match_type':  'exact' | 'project_file' | 'hash_overlap' | 'none',
        'confidence':  0-100,
        'clean_name':  str,
        'category':    str,
        'marketplace': str,
        'disk_name':   str,
        'score':       float,   # fraction of files matched
        'matched_files': int,
        'asset_id':    int,
    }
    """
    if not os.path.exists(db_path):
        return None

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    try:
        fp, file_list = folder_fingerprint(folder_path)
        hashed = [f for f in file_list if not f['skipped']]
        if not hashed:
            return None

        # ── 1. Exact folder fingerprint match ──────────────────────────────────
        if fp:
            row = con.execute(
                "SELECT * FROM assets WHERE folder_fingerprint=?", (fp,)
            ).fetchone()
            if row:
                return _match_result(row, 'exact', 100, len(hashed), len(hashed))

        # ── 2. Project file (.aep/.psd/etc) exact hash match ──────────────────
        proj_hashes = [f['sha256'] for f in hashed if f['is_project_file']]
        if proj_hashes:
            placeholders = ','.join('?' * len(proj_hashes))
            row = con.execute(
                f"SELECT a.* FROM assets a "
                f"JOIN asset_files f ON f.asset_id = a.id "
                f"WHERE f.sha256 IN ({placeholders}) AND f.is_project_file = 1 "
                f"LIMIT 1",
                proj_hashes
            ).fetchone()
            if row:
                return _match_result(row, 'project_file', 90, 1, len(hashed))

        # ── 3. File hash overlap scoring ───────────────────────────────────────
        all_hashes = [f['sha256'] for f in hashed]
        placeholders = ','.join('?' * len(all_hashes))
        rows = con.execute(
            f"SELECT asset_id, COUNT(*) as cnt "
            f"FROM asset_files "
            f"WHERE sha256 IN ({placeholders}) "
            f"GROUP BY asset_id ORDER BY cnt DESC LIMIT 5",
            all_hashes
        ).fetchall()

        if rows:
            best_id, best_cnt = rows[0]['asset_id'], rows[0]['cnt']
            asset_row = con.execute(
                "SELECT * FROM assets WHERE id=?", (best_id,)
            ).fetchone()
            if asset_row:
                known_count = asset_row['file_count']
                score = best_cnt / max(known_count, len(hashed))
                if score >= 0.75:
                    conf = int(min(85, 75 + score * 10))
                    return _match_result(asset_row, 'hash_overlap', conf, best_cnt, len(hashed), score)
                if score >= 0.40:
                    conf = int(40 + score * 50)
                    return _match_result(asset_row, 'hash_overlap_partial', conf, best_cnt, len(hashed), score)

        return {'match_type': 'none', 'confidence': 0}
    finally:
        con.close()


def _match_result(row, match_type: str, confidence: int,
                  matched: int, total: int, score: float = 1.0) -> dict:
    return {
        'match_type':   match_type,
        'confidence':   confidence,
        'clean_name':   row['clean_name'],
        'category':     row['category'],
        'marketplace':  row['marketplace'] or '',
        'disk_name':    row['disk_name'] or '',
        'score':        round(score, 3),
        'matched_files': matched,
        'total_files':  total,
        'asset_id':     row['id'],
    }


# ── Export ──────────────────────────────────────────────────────────────────────

def export_json(db_path: str = DB_FILE, output_path: str = EXPORT_FILE) -> int:
    """
    Export the database to a JSON file for community sharing.
    The export is keyed by folder_fingerprint for fast lookup.
    Returns total asset count exported.
    """
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    meta    = {r['key']: r['value'] for r in con.execute("SELECT * FROM db_meta")}
    assets  = con.execute("SELECT * FROM assets ORDER BY category, clean_name").fetchall()
    total   = len(assets)

    export = {
        'schema_version': DB_VERSION,
        'generated_at':   _now(),
        'asset_count':    total,
        'db_meta':        dict(meta),
        'assets':         [],
    }

    for asset in assets:
        files = con.execute(
            "SELECT relative_path, size_bytes, sha256, is_project_file "
            "FROM asset_files WHERE asset_id=? ORDER BY relative_path",
            (asset['id'],)
        ).fetchall()

        export['assets'].append({
            'id':                 asset['id'],
            'clean_name':         asset['clean_name'],
            'category':           asset['category'],
            'marketplace':        asset['marketplace'] or '',
            'confidence':         asset['confidence'],
            'disk_name':          asset['disk_name'] or '',
            'file_count':         asset['file_count'],
            'total_bytes':        asset['total_bytes'],
            'folder_fingerprint': asset['folder_fingerprint'],
            'added_at':           asset['added_at'],
            'files': [
                {
                    'p': f['relative_path'],   # path within asset
                    's': f['size_bytes'],       # size
                    'h': f['sha256'],           # sha256
                    'k': f['is_project_file'],  # is key/project file
                }
                for f in files
            ],
        })

    con.close()

    os.makedirs(os.path.dirname(output_path) or '.', exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(export, f, indent=2, ensure_ascii=False)

    size_mb = os.path.getsize(output_path) / 1_048_576
    print(f"Exported {total} assets to {output_path}  ({size_mb:.1f} MB)")
    return total


# ── Stats ────────────────────────────────────────────────────────────────────────

def cmd_stats(db_path: str = DB_FILE):
    if not os.path.exists(db_path):
        print(f"No database at {db_path}")
        return

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row

    meta   = {r['key']: r['value'] for r in con.execute("SELECT * FROM db_meta")}
    n_ast  = con.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
    n_fil  = con.execute("SELECT COUNT(*) FROM asset_files").fetchone()[0]
    n_proj = con.execute("SELECT COUNT(*) FROM asset_files WHERE is_project_file=1").fetchone()[0]
    tb     = con.execute("SELECT SUM(total_bytes) FROM assets").fetchone()[0] or 0
    cats   = con.execute("SELECT category, COUNT(*) c FROM assets GROUP BY category ORDER BY c DESC").fetchall()
    mkts   = con.execute("SELECT marketplace, COUNT(*) c FROM assets GROUP BY marketplace ORDER BY c DESC").fetchall()

    print(f"\n=== Asset Fingerprint Database ===")
    print(f"  DB path      : {db_path}")
    print(f"  Version      : {meta.get('version', '?')}")
    print(f"  Created      : {meta.get('created_at', '?')}")
    print(f"  Last build   : {meta.get('last_build', 'never')}")
    print(f"  Assets       : {n_ast:,}")
    print(f"  File records : {n_fil:,}  ({n_proj:,} project files)")
    print(f"  Total size   : {tb / 1_073_741_824:.1f} GB")
    print(f"\n  Top categories:")
    for r in cats[:15]:
        print(f"    {r['c']:>5}  {r['category']}")
    if len(cats) > 15:
        print(f"           ... {len(cats) - 15} more")
    print(f"\n  Marketplace breakdown:")
    for r in mkts[:10]:
        print(f"    {r['c']:>5}  {r['marketplace'] or '(unknown)'}")
    con.close()


# ── Verify ───────────────────────────────────────────────────────────────────────

def cmd_verify(organized_root: str = DEFAULT_ORGANIZED,
               db_path: str = DB_FILE) -> dict:
    """Check that every DB entry still has a matching folder on disk."""
    if not os.path.exists(db_path):
        print(f"No database at {db_path}")
        return {}

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    assets = con.execute("SELECT * FROM assets").fetchall()
    con.close()

    missing = []
    count_mismatch = []
    for asset in assets:
        path = os.path.join(organized_root, asset['category'], asset['clean_name'])
        if not os.path.exists(path):
            missing.append(f"  MISSING  {asset['category']}/{asset['clean_name']}")
        else:
            disk_count = sum(1 for _ in Path(path).rglob('*') if Path(_).is_file())
            if disk_count != asset['file_count']:
                count_mismatch.append(
                    f"  COUNT MISMATCH  {asset['clean_name']!r}  "
                    f"db={asset['file_count']} disk={disk_count}"
                )

    ok = len(assets) - len(missing) - len(count_mismatch)
    print(f"\nVerify: {ok} OK, {len(missing)} missing, {len(count_mismatch)} count mismatches")
    for m in missing[:20]:
        print(m)
    for m in count_mismatch[:20]:
        print(m)
    return {'ok': ok, 'missing': len(missing), 'count_mismatch': len(count_mismatch)}


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(
        description="Asset fingerprint database builder/lookup for FileOrganizer"
    )
    ap.add_argument('--build',   nargs='?', const=DEFAULT_ORGANIZED, metavar='DIR',
                    help='Build/update database from organized directory')
    ap.add_argument('--lookup',  metavar='FOLDER',
                    help='Identify an unknown asset folder')
    ap.add_argument('--export',  nargs='?', const=EXPORT_FILE, metavar='OUTPUT',
                    help='Export database to JSON for community sharing')
    ap.add_argument('--stats',   action='store_true',
                    help='Show database statistics')
    ap.add_argument('--verify',  nargs='?', const=DEFAULT_ORGANIZED, metavar='DIR',
                    help='Verify DB entries match disk')
    ap.add_argument('--db',      default=DB_FILE, metavar='PATH',
                    help=f'Database path (default: {DB_FILE})')
    args = ap.parse_args()

    if args.stats:
        cmd_stats(args.db)

    if args.build is not None:
        build_database(args.build, args.db)

    if args.export is not None:
        export_json(args.db, args.export)

    if args.lookup:
        result = lookup_folder(args.lookup, args.db)
        if result and result['match_type'] != 'none':
            print(f"\nMatch: {result['match_type']}  (confidence {result['confidence']}%)")
            print(f"  Name       : {result['clean_name']}")
            print(f"  Category   : {result['category']}")
            print(f"  Marketplace: {result['marketplace']}")
            print(f"  Files hit  : {result['matched_files']} / {result['total_files']}")
        else:
            print("No match found in database")

    if args.verify is not None:
        cmd_verify(args.verify, args.db)

    if not any([args.stats, args.build is not None, args.export is not None,
                args.lookup, args.verify is not None]):
        ap.print_help()


if __name__ == '__main__':
    main()
