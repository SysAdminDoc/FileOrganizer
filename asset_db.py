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
import os, sys, json, sqlite3, hashlib, argparse, re, time
from pathlib import Path
from collections import defaultdict
from datetime import datetime, timezone

# N-12 provenance helper. Imported defensively so a fresh checkout that
# hasn't installed in-tree dependencies can still load this module.
try:
    from fileorganizer.provenance import parse_source_domain as _parse_provenance
except Exception:
    def _parse_provenance(_name: str):  # type: ignore[no-redef]
        return None

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

# Image extensions used when scanning for preview thumbnails
_PREVIEW_EXTS = frozenset({'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'})
# Priority-ordered patterns that identify a "preview" image within a template folder
_PREVIEW_PATTERNS = re.compile(
    r'(preview|thumbnail|thumb|promo|poster|cover|banner|main|hero|featured)',
    re.IGNORECASE
)

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
    preview_image      TEXT,
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
    _migrate_assets_provenance(con)
    now = _now()
    con.execute("INSERT OR IGNORE INTO db_meta VALUES ('version',    ?)", (str(DB_VERSION),))
    con.execute("INSERT OR IGNORE INTO db_meta VALUES ('created_at', ?)", (now,))
    con.commit()
    return con


def _migrate_assets_provenance(con: sqlite3.Connection) -> None:
    """Idempotent ALTER TABLE for N-12 provenance columns.

    SQLite has no ``ALTER TABLE IF NOT COLUMN``, so we read PRAGMA table_info
    and only add columns that aren't there yet. Safe to call on any DB:
      - Fresh DB (created by _SCHEMA above): both columns missing → both added
      - Existing DB pre-N-12: both columns missing → both added, existing rows
        get NULL/0 (back-fill happens lazily on next index pass)
      - Existing DB post-N-12: both columns present → no-op
    """
    have = {row[1] for row in con.execute("PRAGMA table_info(assets)").fetchall()}
    if "source_domain" not in have:
        con.execute("ALTER TABLE assets ADD COLUMN source_domain TEXT")
    if "first_seen_ts" not in have:
        con.execute("ALTER TABLE assets ADD COLUMN first_seen_ts INTEGER")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_assets_source ON assets(source_domain)"
    )
    _migrate_files_broken(con)


def _migrate_files_broken(con: sqlite3.Connection) -> None:
    """Idempotent ALTER TABLE for N-14 broken-file flag on asset_files."""
    have = {row[1] for row in con.execute("PRAGMA table_info(asset_files)").fetchall()}
    if "broken" not in have:
        con.execute("ALTER TABLE asset_files ADD COLUMN broken INTEGER NOT NULL DEFAULT 0")
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_broken ON asset_files(broken)"
    )


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def find_preview_image(folder_path: str) -> str | None:
    """
    Locate the best preview/thumbnail image inside a template folder.
    Scoring: named-preview images > images in root dir > largest image anywhere.
    Returns relative path from folder_path, or None.
    """
    root    = Path(folder_path)
    scored  = []

    for fpath in root.rglob('*'):
        if not fpath.is_file():
            continue
        if fpath.suffix.lower() not in _PREVIEW_EXTS:
            continue
        try:
            size = fpath.stat().st_size
        except OSError:
            continue

        rel   = fpath.relative_to(root).as_posix()
        depth = len(fpath.relative_to(root).parts) - 1   # 0 = root dir

        # Prefer: preview-named > root-level > large file
        name_score = 100 if _PREVIEW_PATTERNS.search(fpath.stem) else 0
        depth_pen  = depth * 20   # penalize depth
        size_bonus = min(50, size // 10_000)  # up to +50 for larger files

        score = name_score - depth_pen + size_bonus
        scored.append((score, rel))

    if not scored:
        return None
    scored.sort(key=lambda x: -x[0])
    return scored[0][1]


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

        # Find best preview image
        preview_rel = find_preview_image(asset_path)

        # N-12 provenance: parse the source domain from the disk folder name
        # (clean_name strips marketplace prefixes; disk_name preserves them).
        source_domain = _parse_provenance(disk_name or clean_name)
        first_seen_ts_now = int(time.time())

        if existing:
            # Update existing record. NEVER overwrite first_seen_ts (immutable
            # per N-12 spec) — only back-fill when the column was previously NULL.
            con.execute("""
                UPDATE assets SET
                    file_count=?, total_bytes=?, skipped_bytes=?, folder_fingerprint=?,
                    marketplace=?, confidence=?, disk_name=?, preview_image=?, updated_at=?,
                    source_domain=COALESCE(source_domain, ?),
                    first_seen_ts=COALESCE(first_seen_ts, ?)
                WHERE id=?
            """, (disk_file_count, total_bytes, skipped_bytes, fp,
                  marketplace, conf, disk_name, preview_rel, now,
                  source_domain, first_seen_ts_now, existing['id']))
            asset_id = existing['id']
            # Remove old file rows and re-insert
            con.execute("DELETE FROM asset_files WHERE asset_id=?", (asset_id,))
            updated += 1
        else:
            cur = con.execute("""
                INSERT INTO assets
                    (clean_name, category, marketplace, confidence, disk_name,
                     file_count, total_bytes, skipped_bytes, folder_fingerprint,
                     preview_image, added_at, updated_at,
                     source_domain, first_seen_ts)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (clean_name, category, marketplace, conf, disk_name,
                  disk_file_count, total_bytes, skipped_bytes, fp,
                  preview_rel, now, now,
                  source_domain, first_seen_ts_now))
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
        'match_type':    match_type,
        'confidence':    confidence,
        'clean_name':    row['clean_name'],
        'category':      row['category'],
        'marketplace':   row['marketplace'] or '',
        'disk_name':     row['disk_name'] or '',
        'preview_image': row['preview_image'] or '',
        'score':         round(score, 3),
        'matched_files': matched,
        'total_files':   total,
        'asset_id':      row['id'],
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
            'preview_image':      asset['preview_image'] or '',
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


# ── Community import ────────────────────────────────────────────────────────────

def import_community_json(json_data: dict, db_path: str = DB_FILE) -> tuple:
    """
    Merge a community-exported asset_fingerprints.json into the local DB.

    Existing assets (matched by folder_fingerprint) are left untouched so
    local renames/corrections take priority over community data.

    Returns (new_assets, skipped_duplicates).
    """
    con = init_db(db_path)
    now = _now()
    new_assets = 0
    skipped    = 0

    try:
        for asset in json_data.get('assets', []):
            fp = asset.get('folder_fingerprint') or ''
            if not fp:
                skipped += 1
                continue

            # INSERT OR IGNORE respects the UNIQUE constraint on folder_fingerprint
            cur = con.execute(
                """
                INSERT OR IGNORE INTO assets
                    (clean_name, category, marketplace, confidence, disk_name,
                     file_count, total_bytes, folder_fingerprint,
                     preview_image, added_at, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    asset.get('clean_name', ''),
                    asset.get('category', ''),
                    asset.get('marketplace', ''),
                    asset.get('confidence', 0),
                    asset.get('disk_name', ''),
                    asset.get('file_count', 0),
                    asset.get('total_bytes', 0),
                    fp,
                    asset.get('preview_image', ''),
                    asset.get('added_at', now),
                    now,
                )
            )
            if cur.lastrowid and cur.rowcount:
                asset_id = cur.lastrowid
                new_assets += 1
                for f in asset.get('files', []):
                    con.execute(
                        """
                        INSERT OR IGNORE INTO asset_files
                            (asset_id, filename, relative_path, size_bytes,
                             sha256, is_project_file, added_at)
                        VALUES (?,?,?,?,?,?,?)
                        """,
                        (
                            asset_id,
                            os.path.basename(f.get('p', '')),
                            f.get('p', ''),
                            f.get('s', 0),
                            f.get('h', ''),
                            int(bool(f.get('k', 0))),
                            now,
                        )
                    )
            else:
                skipped += 1

        con.execute(
            "INSERT OR REPLACE INTO db_meta VALUES ('last_community_import', ?)", (now,)
        )
        con.commit()
    finally:
        con.close()

    return new_assets, skipped




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


# ── Provenance back-fill (iter-2 follow-up to N-12) ─────────────────────────────

def cmd_backfill_provenance(db_path: str = DB_FILE, dry_run: bool = False) -> dict:
    """Populate source_domain + first_seen_ts on rows that pre-date N-12.

    Walks every assets row where source_domain IS NULL OR first_seen_ts IS NULL,
    derives source_domain from disk_name (or clean_name as fallback), and sets
    first_seen_ts to the row's added_at unix timestamp (falling back to the
    current time if added_at is unparseable).

    Re-runs are idempotent: rows whose columns are already populated are
    skipped by the WHERE clause.

    Dry-run honors immutability: opens the DB without invoking ``init_db()``
    so its eager schema migrations don't commit on inspection-only calls.
    If the legacy DB is missing the N-12 columns, dry-run reports the
    pending migration and exits without touching the file.

    Returns a summary dict::
        {
            'rows_scanned': int,        # NULL columns considered
            'rows_updated': int,        # rows actually mutated (0 in dry_run)
            'domains': {dom: count},    # per-domain back-fill counts
            'no_match': int,            # rows where parse_source_domain returned None
            'dry_run': bool,
            'migration_pending': bool,  # only meaningful in dry_run
        }
    """
    if not os.path.exists(db_path):
        print(f"No database at {db_path}")
        return {
            'rows_scanned': 0, 'rows_updated': 0,
            'domains': {}, 'no_match': 0, 'dry_run': dry_run,
            'migration_pending': False,
        }

    if dry_run:
        # Inspect-only: never call init_db (it would commit a schema mutation).
        peek = sqlite3.connect(db_path)
        peek.row_factory = sqlite3.Row
        try:
            cols = {r[1] for r in peek.execute("PRAGMA table_info(assets)").fetchall()}
        except sqlite3.DatabaseError as exc:
            peek.close()
            print(f"ERROR reading {db_path}: {exc}")
            return {
                'rows_scanned': 0, 'rows_updated': 0,
                'domains': {}, 'no_match': 0, 'dry_run': True,
                'migration_pending': False,
            }
        if 'source_domain' not in cols or 'first_seen_ts' not in cols:
            peek.close()
            print(
                f"\n--dry-run: legacy schema detected (missing N-12 columns).\n"
                f"  Run without --dry-run to apply both the schema migration\n"
                f"  AND the row back-fill in a single committed pass."
            )
            return {
                'rows_scanned': 0, 'rows_updated': 0,
                'domains': {}, 'no_match': 0, 'dry_run': True,
                'migration_pending': True,
            }
        con = peek
    else:
        con = init_db(db_path)              # ensure migrations have run
        con.row_factory = sqlite3.Row

    rows = con.execute(
        "SELECT id, clean_name, disk_name, added_at, source_domain, first_seen_ts "
        "FROM assets "
        "WHERE source_domain IS NULL OR first_seen_ts IS NULL"
    ).fetchall()

    domains: dict[str, int] = {}
    updated = 0
    no_match = 0

    for row in rows:
        # Only fill what's missing — never overwrite a non-NULL column.
        new_domain = row['source_domain']
        new_ts = row['first_seen_ts']

        if new_domain is None:
            name = row['disk_name'] or row['clean_name'] or ''
            new_domain = _parse_provenance(name)
            if new_domain is None:
                no_match += 1
            else:
                domains[new_domain] = domains.get(new_domain, 0) + 1

        if new_ts is None:
            ts = _parse_added_at(row['added_at'])
            new_ts = ts if ts is not None else int(time.time())

        if dry_run:
            updated += 1
            continue

        con.execute(
            "UPDATE assets SET "
            "  source_domain = COALESCE(source_domain, ?), "
            "  first_seen_ts = COALESCE(first_seen_ts, ?) "
            "WHERE id = ?",
            (new_domain, new_ts, row['id']),
        )
        updated += 1

    if not dry_run:
        con.commit()

    summary = {
        'rows_scanned': len(rows),
        'rows_updated': updated,
        'domains': domains,
        'no_match': no_match,
        'dry_run': dry_run,
        'migration_pending': False,
    }

    label = 'WOULD update' if dry_run else 'updated'
    print(f"\nBack-fill complete: {label} {updated}/{len(rows)} rows "
          f"({no_match} unmatched).")
    if domains:
        width = max(len(d) for d in domains)
        for dom, n in sorted(domains.items(), key=lambda kv: (-kv[1], kv[0])):
            print(f"  {dom.ljust(width)}  {n:6d}")
    con.close()
    return summary


def _parse_added_at(value) -> int | None:
    """Parse the 'added_at' column (ISO-8601 ish) into a unix epoch seconds.

    Falls back to None when the value is missing or unparseable, which lets
    cmd_backfill_provenance use the current time instead.
    """
    if not value:
        return None
    text = str(value)
    # Try the formats _now() emits first, then a couple of common variants.
    candidates = (
        '%Y-%m-%dT%H:%M:%SZ',
        '%Y-%m-%dT%H:%M:%S',
        '%Y-%m-%d %H:%M:%S',
        '%Y-%m-%d',
    )
    for fmt in candidates:
        try:
            dt = datetime.strptime(text, fmt).replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except (ValueError, TypeError):
            continue
    return None


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
    ap.add_argument('--backfill-provenance', action='store_true',
                    help='Populate source_domain + first_seen_ts on rows that '
                         'pre-date N-12 (idempotent; only fills NULL columns).')
    ap.add_argument('--dry-run', action='store_true',
                    help='With --backfill-provenance: preview without committing.')
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

    if args.backfill_provenance:
        cmd_backfill_provenance(args.db, dry_run=args.dry_run)

    if not any([args.stats, args.build is not None, args.export is not None,
                args.lookup, args.verify is not None,
                args.backfill_provenance]):
        ap.print_help()


if __name__ == '__main__':
    main()
