#!/usr/bin/env python3
"""reclassify_unorg.py — Post-processing fix for I:\\Unorganized items
   that landed in After Effects categories instead of correct destinations.

The AE apply pipeline treated all 88 I:\\Unorganized category folders as AE templates.
Their actual content is stock photos (JPG/EPS), Photoshop designs (PSD), and design
bundles (ZIP) — not AE templates.  This script:

  1. Reads organize_moves.db to find every move from I:\\Unorganized
  2. Inspects content of each moved folder (file extensions)
  3. Uses DeepSeek + content signals to determine correct category
  4. Proposes and optionally applies moves to correct destinations
  5. Journals corrections back to organize_moves.db

Usage:
    python reclassify_unorg.py --status           # show all unorg moves in journal
    python reclassify_unorg.py --analyze          # DeepSeek analysis of each item
    python reclassify_unorg.py --apply --dry-run  # preview moves
    python reclassify_unorg.py --apply            # execute corrections
"""

import os, sys, json, sqlite3, shutil, subprocess, argparse, re
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
ORGANIZED       = Path(r'G:\Organized')
JOURNAL_FILE    = Path(__file__).parent / 'organize_moves.db'
RESULTS_FILE    = Path(__file__).parent / 'unorg_reclassify_results.json'

# Correct category mapping by dominant file type
# .psd → Photoshop, .ai → Illustrator, .jpg/.eps → Stock Photos, .zip → needs deep inspect
EXTENSION_MAP = {
    '.psd':  'Photoshop - Smart Objects & Templates',
    '.psb':  'Photoshop - Smart Objects & Templates',
    '.ai':   'Illustrator - Vectors & Assets',
    '.eps':  'Stock Photos - General',
    '.svg':  'Illustrator - Vectors & Assets',
    '.jpg':  'Stock Photos - General',
    '.jpeg': 'Stock Photos - General',
    '.png':  'Stock Photos - General',
    '.tif':  'Stock Photos - General',
    '.tiff': 'Stock Photos - General',
    '.indd': 'Print - Brochures & Books',
    '.mp4':  'Stock Footage - General',
    '.mov':  'Stock Footage - General',
    '.aep':  None,  # AE file — these belong in AE categories, don't move
    '.prproj': None,  # Premiere — leave in place
}

# AE extension set — if any found, item is likely a genuine AE template
AE_EXTENSIONS = {'.aep', '.aet', '.ffx', '.mogrt', '.aex'}

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_URL     = 'https://api.deepseek.com/v1/chat/completions'
DEEPSEEK_MODEL   = 'deepseek-chat'

# ── Journal helpers ───────────────────────────────────────────────────────────
def load_unorg_moves() -> list[dict]:
    """Return all journal entries where source was from I:\\Unorganized."""
    if not JOURNAL_FILE.exists():
        return []
    con = sqlite3.connect(str(JOURNAL_FILE))
    con.row_factory = sqlite3.Row
    rows = con.execute(
        "SELECT * FROM moves WHERE src LIKE 'I:\\Unorganized%' AND undone_at IS NULL"
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def journal_correction(old_dest: str, new_dest: str, clean_name: str,
                       category: str, confidence: int) -> None:
    if not JOURNAL_FILE.exists():
        return
    con = sqlite3.connect(str(JOURNAL_FILE))
    with con:
        con.execute(
            '''INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at)
               VALUES (?,?,?,?,?,?,?)''',
            (old_dest, new_dest, os.path.basename(old_dest), clean_name,
             category, confidence,
             datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        )
    con.close()


# ── Content inspection ────────────────────────────────────────────────────────
def inspect_folder(path: Path) -> dict:
    """Return extension profile and AE flag for a moved folder."""
    ext_counts: Counter = Counter()
    total = 0
    has_ae = False
    try:
        for root, dirs, files in os.walk(str(path)):
            for fn in files:
                ext = os.path.splitext(fn)[1].lower()
                ext_counts[ext] += 1
                total += 1
                if ext in AE_EXTENSIONS:
                    has_ae = True
    except Exception:
        pass
    return {
        'path':      str(path),
        'total':     total,
        'ext_counts': dict(ext_counts.most_common(8)),
        'has_ae':    has_ae,
        'dominant':  ext_counts.most_common(1)[0][0] if ext_counts else '',
    }


def simple_classify(info: dict) -> Optional[str]:
    """Rule-based classification from extension profile. Returns None if AE or ambiguous."""
    if info['has_ae']:
        return None  # genuine AE content — keep in AE category
    dominant = info['dominant']
    exts = info['ext_counts']
    # If majority are design/stock extensions
    total = info['total']
    if total == 0:
        return '_empty'
    # Check for Photoshop-heavy
    psd_count = exts.get('.psd', 0) + exts.get('.psb', 0)
    if psd_count / total > 0.6:
        # All PSD-heavy items → Smart Objects & Templates (no "Social Media" Photoshop cat)
        return 'Photoshop - Smart Objects & Templates'
    # Stock photos
    stock_count = sum(exts.get(e, 0) for e in ('.jpg','.jpeg','.eps','.tif','.tiff','.png'))
    if stock_count / total > 0.5:
        return 'Stock Photos - General'
    # Illustrator vectors
    ai_count = exts.get('.ai', 0) + exts.get('.svg', 0)
    if ai_count / total > 0.5:
        return 'Illustrator - Vectors & Assets'
    # Stock video
    video_count = sum(exts.get(e, 0) for e in ('.mp4','.mov','.avi','.mkv','.webm'))
    if video_count / total > 0.5:
        return 'Stock Footage - General'
    # Zip-only
    zip_count = exts.get('.zip', 0) + exts.get('.rar', 0) + exts.get('.7z', 0)
    if zip_count == total:
        return None  # need DeepSeek for archives
    return EXTENSION_MAP.get(dominant)


# ── DeepSeek analysis ─────────────────────────────────────────────────────────
def deepseek_classify_batch(items: list[dict]) -> list[dict]:
    """Send batch of items to DeepSeek for category determination."""
    import urllib.request
    if not DEEPSEEK_API_KEY:
        print('[WARN] DEEPSEEK_API_KEY not set, skipping AI classification')
        return [{**i, 'ai_category': None} for i in items]

    batch_text = '\n'.join(
        f'{j+1}. Folder: "{it["folder_name"]}" | Files: {it["ext_summary"]} | Path: .../{Path(it["current_path"]).parent.name}/'
        for j, it in enumerate(items)
    )

    categories = [
        'Photoshop - Smart Objects & Templates', 'Photoshop - Mockups', 'Photoshop - Overlays & FX',
        'Photoshop - Patterns & Textures', 'Photoshop - Other',
        'Illustrator - Vectors & Assets', 'Illustrator - Icons & UI Kits',
        'Print - Flyers & Posters', 'Print - Brochures & Books', 'Print - Business Cards & Stationery',
        'Print - Social Media Graphics', 'Print - Other',
        'Stock Photos - General', 'Stock Photos - Food & Drink', 'Stock Photos - Nature & Outdoors',
        'Stock Footage - General', 'Stock Music & Audio',
        'Fonts & Typography', 'UI Resources & Icon Sets', 'Mockups - Branding & Stationery',
        'After Effects - Other',
    ]

    prompt = f"""You are classifying design asset folders. Each folder has been moved into an INCORRECT "After Effects" category. 
Based on the folder name and file content, determine the CORRECT category.

Valid categories: {', '.join(categories)}

Respond with a JSON array, one object per item:
[{{"index":1,"category":"<category>","confidence":<50-100>,"clean_name":"<display name>","reasoning":"<one sentence>"}}]

Items to classify:
{batch_text}"""

    payload = json.dumps({
        'model': DEEPSEEK_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 2000,
    }).encode()

    req = urllib.request.Request(
        DEEPSEEK_URL,
        data=payload,
        headers={
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json',
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        raw = data['choices'][0]['message']['content'].strip()
        # strip markdown code fences
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        results = json.loads(raw)
        # Merge back
        for r in results:
            idx = r.get('index', 0) - 1
            if 0 <= idx < len(items):
                items[idx]['ai_category']  = r.get('category')
                items[idx]['ai_confidence'] = r.get('confidence', 70)
                items[idx]['ai_clean_name'] = r.get('clean_name', items[idx]['folder_name'])
                items[idx]['ai_reasoning']  = r.get('reasoning', '')
        return items
    except Exception as e:
        print(f'  [ERROR] DeepSeek call failed: {e}')
        return [{**i, 'ai_category': None} for i in items]


# ── Safe destination ──────────────────────────────────────────────────────────
def safe_dest(base_dir: Path, clean_name: str) -> Path:
    dest = base_dir / clean_name
    if not dest.exists():
        return dest
    suffix = 1
    while True:
        candidate = base_dir / f'{clean_name} ({suffix})'
        if not candidate.exists():
            return candidate
        suffix += 1


# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_status() -> None:
    moves = load_unorg_moves()
    if not moves:
        print('No I:\\Unorganized moves found in journal.')
        print('Run AE apply first, or journal may not exist.')
        return
    print(f'Found {len(moves)} I:\\Unorganized moves in journal:')
    by_cat = {}
    for m in moves:
        dest = m.get('dest', '')
        cat = Path(dest).parent.parent.name if dest else '?'
        by_cat.setdefault(cat, []).append(m)
    for cat, items in sorted(by_cat.items()):
        print(f'\n  [{cat}] ({len(items)} items)')
        for m in items[:5]:
            print(f'    {Path(m["dest"]).name}')
        if len(items) > 5:
            print(f'    ... +{len(items)-5} more')


def cmd_analyze() -> None:
    moves = load_unorg_moves()
    if not moves:
        print('No journal entries found. Run AE apply first.')
        return

    print(f'Analyzing {len(moves)} I:\\Unorganized moves...')
    results = []
    needs_ai = []

    for m in moves:
        dest = Path(m.get('dest', ''))
        if not dest.exists():
            print(f'  [SKIP] {dest.name} — destination not found')
            results.append({'name': dest.name, 'action': 'skip', 'reason': 'dest not found'})
            continue

        info = inspect_folder(dest)
        folder_name = dest.name
        simple_cat = simple_classify(info)

        if simple_cat is None and info['has_ae']:
            # Genuine AE content — stay where it is
            results.append({
                'name': folder_name, 'action': 'keep',
                'current_path': str(dest),
                'reason': 'has AE files — correctly in AE category',
                'ext_summary': str(info['ext_counts']),
            })
            print(f'  [KEEP-AE] {folder_name} — has AE files, correctly placed')
        elif simple_cat == '_empty':
            results.append({'name': folder_name, 'action': 'keep', 'reason': 'empty folder'})
            print(f'  [EMPTY]  {folder_name}')
        elif simple_cat:
            results.append({
                'name': folder_name, 'action': 'move',
                'current_path': str(dest),
                'new_category': simple_cat,
                'clean_name': folder_name,
                'confidence': 85,
                'ext_summary': str(info['ext_counts']),
                'method': 'rule',
            })
            print(f'  [RULE]   {folder_name} -> {simple_cat}')
        else:
            # Needs AI
            needs_ai.append({
                'folder_name': folder_name,
                'current_path': str(dest),
                'ext_summary': str(info['ext_counts']),
                'total_files': info['total'],
            })

    # Process items needing AI in batches of 10
    if needs_ai:
        print(f'\nCalling DeepSeek for {len(needs_ai)} ambiguous items...')
        for i in range(0, len(needs_ai), 10):
            batch = needs_ai[i:i+10]
            batch = deepseek_classify_batch(batch)
            for item in batch:
                cat = item.get('ai_category') or 'After Effects - Other'
                conf = item.get('ai_confidence', 60)
                results.append({
                    'name': item['folder_name'],
                    'action': 'move',
                    'current_path': item['current_path'],
                    'new_category': cat,
                    'clean_name': item.get('ai_clean_name', item['folder_name']),
                    'confidence': conf,
                    'ext_summary': item['ext_summary'],
                    'method': 'ai',
                    'ai_reasoning': item.get('ai_reasoning', ''),
                })
                print(f'  [AI]     {item["folder_name"]} -> {cat} ({conf}%)')

    # Save results
    with open(str(RESULTS_FILE), 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
    print(f'\nSaved {len(results)} results to {RESULTS_FILE.name}')

    keep = sum(1 for r in results if r.get('action') == 'keep')
    move = sum(1 for r in results if r.get('action') == 'move')
    skip = sum(1 for r in results if r.get('action') == 'skip')
    print(f'Summary: {move} to move, {keep} keep-in-place (AE/empty), {skip} skipped')


def cmd_apply(dry_run: bool = False) -> None:
    tag = '[DRY]' if dry_run else '[MOVE]'
    if not RESULTS_FILE.exists():
        print('No results file found. Run --analyze first.')
        return

    results = json.load(open(str(RESULTS_FILE)))
    moved = 0
    skipped = 0
    errors = 0

    for r in results:
        if r.get('action') != 'move':
            continue
        src = Path(r['current_path'])
        new_cat = r.get('new_category', '')
        clean_name = r.get('clean_name', src.name)
        confidence = r.get('confidence', 70)

        if not src.exists():
            print(f'  [SKIP] {src.name} — not found at {src}')
            skipped += 1
            continue

        cat_dir = ORGANIZED / new_cat
        dest = safe_dest(cat_dir, clean_name)
        print(f'  {tag} {src.name!r} -> {new_cat}/{clean_name}')

        if not dry_run:
            try:
                cat_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dest))
                journal_correction(str(src), str(dest), clean_name, new_cat, confidence)
                moved += 1
            except Exception as e:
                print(f'    [ERROR] {e}')
                errors += 1
        else:
            moved += 1

    suffix = ' (DRY RUN)' if dry_run else ''
    print(f'\nDone{suffix}: {moved} moved, {skipped} skipped, {errors} errors')


# ── Entry point ───────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description='Reclassify I:\\Unorganized items from AE to correct categories')
    ap.add_argument('--status',   action='store_true', help='Show journal entries for unorg moves')
    ap.add_argument('--analyze',  action='store_true', help='Inspect content + DeepSeek classify')
    ap.add_argument('--apply',    action='store_true', help='Apply corrections')
    ap.add_argument('--dry-run',  action='store_true', help='Preview apply without moving')
    args = ap.parse_args()

    if args.status:
        cmd_status()
    elif args.analyze:
        cmd_analyze()
    elif args.apply:
        cmd_apply(dry_run=args.dry_run)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
