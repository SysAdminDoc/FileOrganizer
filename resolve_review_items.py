#!/usr/bin/env python3
"""
resolve_review_items.py -- Manual curator pass for _Review subfolders.

Moves items that were AI-classified as _Review (low confidence) but have been
manually researched and given a definitive category assignment. Updates the
moves journal (organize_moves.db) to reflect the final destination.

Usage:
    python resolve_review_items.py           # dry run (default)
    python resolve_review_items.py --apply   # execute moves
"""
import argparse, os, shutil, sqlite3, json, re, sys
from datetime import datetime, timezone

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DEST_ROOT   = r'G:\Organized'
JOURNAL     = os.path.join(BASE_DIR, 'organize_moves.db')
LOG_FILE    = os.path.join(BASE_DIR, 'organize_run.log')

# ── Manual resolution map ─────────────────────────────────────────────────────
# Each entry: (current_path, dest_category, clean_name, resolution_note)
RESOLUTIONS = [
    # cm_4804020: "Film Dust Textures" — 20 high-res JPEG overlays (6720×4480px)
    # Source: PDF "This collection of Film Dust Textures contains 20 high-resolution
    # JPEG images... Add that vintage feel... dust & scratch overlay textures"
    (
        r'G:\Organized\_Review\_Review\cm_4804020',
        'Photoshop - Overlays & FX',
        'Film Dust Textures (20 JPG)',
        'Manually identified from embedded PDF: Film Dust Textures pack, 20 hi-res JPEGs',
    ),

    # cm_4840406: "Roller Textures" — 17 JPG roller/paint textures
    # Source: zip contents "Roller Textures No 1.jpg ... No 17.jpg"
    (
        r'G:\Organized\_Review\_Review\cm_4840406',
        'Photoshop - Patterns & Textures',
        'Roller Textures (17 JPG)',
        'Manually identified from zip contents: Roller Textures JPG pack',
    ),

    # cm_7116381: 53 numbered JPGs — generic stock imagery, no other metadata
    (
        r'G:\Organized\_Review\_Review\cm_7116381',
        'Stock Photos - General',
        'CM Stock Pack (53 JPG)',
        'No product metadata; 53 numbered JPGs in main/ — archived as general stock',
    ),

    # cm_7119925: "Light Flare Overlay PNG Photography"
    # Source: RAR filename cm_7119925-Light-Flare-Overlay-PNG-Photography
    (
        r'G:\Organized\_Review\_Review\cm_7119925',
        'Photoshop - Overlays & FX',
        'Light Flare Overlays (PNG)',
        'Identified from RAR filename: Light Flare Overlay PNG for photography',
    ),

    # c4: "Full Video Copilot Collection" — multi-part RAR, AE plugin/resource bundle
    # Source: files named "Full Video Copilot Collection - INTRO-HD.NET.part0N.rar"
    (
        r'G:\Organized\_Review\_Review\c4',
        'After Effects - Plugin & Script',
        'Video Copilot Full Collection',
        'Full Video Copilot Collection multi-part RAR — AE plugins, effects, presets',
    ),

    # Help File - Avelina Studio: orphaned RTFD documentation file
    # Source: G:\Design Unorganized\Help File - Avelina Studio.rtfd
    # No parent package found; isolated documentation.
    (
        r'G:\Organized\_Review\_Review\Help File - Avelina Studio',
        r'_Review\Orphaned Documentation',
        'Help File - Avelina Studio',
        'Orphaned RTF documentation from Avelina Studio product; no parent package found',
    ),

    # Main Print: single READ ME.txt — orphaned doc dir
    (
        r'G:\Organized\_Review\_Review\Main Print',
        r'_Review\Orphaned Documentation',
        'Main Print',
        'Orphaned directory containing only READ ME.txt; no identifiable parent',
    ),

    # Read Me: GraphixTree promotional directory (logo PNGs + promo URLs)
    (
        r'G:\Organized\_Review\_Review\Read Me',
        r'_Review\Orphaned Documentation',
        'Read Me (GraphixTree)',
        'Orphaned GraphixTree promotional directory — logo/URL files, no product content',
    ),

    # readme: single readme.txt — orphaned
    (
        r'G:\Organized\_Review\_Review\readme',
        r'_Review\Orphaned Documentation',
        'readme',
        'Orphaned directory containing only readme.txt; no identifiable parent',
    ),
]

# ─────────────────────────────────────────────────────────────────────────────

def log(msg: str) -> None:
    ts = datetime.now().strftime('%Y/%m/%d %H:%M:%S')
    line = f'[{ts}] {msg}'
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def sanitize(name: str) -> str:
    """Replace filesystem-illegal chars with hyphens."""
    return re.sub(r'[<>:"/\\|?*]', '-', name).strip()


def dest_path(category: str, clean_name: str) -> str:
    """Build full destination path, handling _Review subdir categories."""
    if category.startswith('_Review'):
        # e.g. "_Review\Orphaned Documentation" → G:\Organized\_Review\Orphaned Documentation\<name>
        parts = category.replace('\\', '/').split('/', 1)
        if len(parts) == 2:
            sub = sanitize(parts[1])
            return os.path.join(DEST_ROOT, '_Review', sub, sanitize(clean_name))
        return os.path.join(DEST_ROOT, '_Review', sanitize(clean_name))
    return os.path.join(DEST_ROOT, sanitize(category), sanitize(clean_name))


def unique_dest(path: str) -> str:
    """Append (2), (3)... if dest already exists."""
    if not os.path.exists(path):
        return path
    base = path
    n = 2
    while os.path.exists(f'{base} ({n})'):
        n += 1
    return f'{base} ({n})'


def open_journal() -> sqlite3.Connection:
    conn = sqlite3.connect(JOURNAL)
    conn.execute('''CREATE TABLE IF NOT EXISTS moves (
        id INTEGER PRIMARY KEY,
        src TEXT, dest TEXT, disk_name TEXT, clean_name TEXT,
        category TEXT, confidence INTEGER, moved_at TEXT, undone_at TEXT
    )''')
    conn.commit()
    return conn


def update_journal(conn: sqlite3.Connection, old_dest: str, new_dest: str,
                   clean_name: str, category: str, note: str) -> None:
    """Update the existing DB row to the new destination, or insert if not found."""
    moved_at = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    # Try to find existing row by old dest path
    row = conn.execute(
        'SELECT id FROM moves WHERE dest LIKE ? LIMIT 1',
        ('%' + os.path.basename(old_dest) + '%',)
    ).fetchone()
    if row:
        conn.execute(
            'UPDATE moves SET dest=?, clean_name=?, category=?, moved_at=? WHERE id=?',
            (new_dest, clean_name, category, moved_at, row[0])
        )
    else:
        conn.execute(
            'INSERT INTO moves (src, dest, disk_name, clean_name, category, confidence, moved_at) '
            'VALUES (?,?,?,?,?,?,?)',
            (old_dest, new_dest, os.path.basename(old_dest), clean_name, category, 99, moved_at)
        )
    conn.commit()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true', help='Execute moves (default: dry run)')
    args = ap.parse_args()
    dry = not args.apply

    if dry:
        print('=== DRY RUN — pass --apply to execute ===\n')

    conn = open_journal()
    moved = skipped = errors = 0

    for src, category, clean_name, note in RESOLUTIONS:
        dst = unique_dest(dest_path(category, clean_name))
        src_exists = os.path.isdir(src)

        tag = '[DRY]' if dry else '[MOVE]'
        print(f'{tag} {os.path.basename(src)}')
        print(f'       → {dst}')
        print(f'       note: {note}')
        if not src_exists:
            print(f'       WARNING: source not found — skipping')
            skipped += 1
            continue

        if not dry:
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                os.rename(src, dst)
                update_journal(conn, src, dst, clean_name, category, note)
                log(f'[RESOLVE] {src} → {dst}')
                moved += 1
            except Exception as e:
                log(f'[ERROR] {src}: {e}')
                errors += 1
        print()

    conn.close()

    print(f'\n{"DRY RUN SUMMARY" if dry else "SUMMARY"}:')
    if dry:
        print(f'  {len(RESOLUTIONS)} items would be moved.')
        print(f'  Run with --apply to execute.')
    else:
        print(f'  Moved: {moved}  Skipped: {skipped}  Errors: {errors}')


if __name__ == '__main__':
    main()
