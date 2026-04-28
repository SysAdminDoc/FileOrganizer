#!/usr/bin/env python3
"""fix_stock_ae_items.py -- Find and correct AE templates misrouted to non-AE categories.

The merge_stock pipeline routes all of G:/Stock/Stock Footage & Photos to
G:/Organized/Stock Footage - General, which captures a handful of Videohive AE
templates that were stored in the stock folder. This script:

  1. Scans one or more non-AE target directories for folders containing AE files
     (.aep, .mogrt, .ffx, .aet, .aex)
  2. Uses keyword rules + DeepSeek to determine the correct AE subcategory
  3. Moves each item to G:/Organized/After Effects - <subcategory>
  4. Journals every correction in organize_moves.db

Usage:
    python fix_stock_ae_items.py --scan              # show candidates only
    python fix_stock_ae_items.py --analyze           # classify candidates
    python fix_stock_ae_items.py --apply --dry-run   # preview moves
    python fix_stock_ae_items.py --apply             # execute corrections
    python fix_stock_ae_items.py --scan-dirs D1 D2   # override search dirs
"""

import os, sys, json, sqlite3, shutil, subprocess, argparse, re
from pathlib import Path
from datetime import datetime, timezone
from collections import Counter
from typing import Optional

# ── Config ────────────────────────────────────────────────────────────────────
ORGANIZED          = Path(r'G:\Organized')
ORGANIZED_OVERFLOW = Path(r'I:\Organized')   # overflow destination when G:\ is low
JOURNAL_FILE  = Path(__file__).parent / 'organize_moves.db'
RESULTS_FILE  = Path(__file__).parent / 'fix_stock_ae_results.json'

def _overflow_scan_dirs() -> list[Path]:
    """Extra scan dirs from I:\\Organized if the overflow root exists."""
    if not ORGANIZED_OVERFLOW.exists():
        return []
    names = ['Stock Footage - General', 'Stock Photos - General',
             'Stock Music & Audio', 'Print - Other', 'Print - Flyers & Posters']
    return [ORGANIZED_OVERFLOW / n for n in names if (ORGANIZED_OVERFLOW / n).exists()]

# Non-AE destination directories to scan for misplaced AE templates
DEFAULT_SCAN_DIRS = [
    ORGANIZED / 'Stock Footage - General',
    ORGANIZED / 'Stock Photos - General',
    ORGANIZED / 'Stock Music & Audio',
    ORGANIZED / 'Print - Other',
    ORGANIZED / 'Print - Flyers & Posters',
] + _overflow_scan_dirs()

AE_EXTENSIONS = {'.aep', '.aet', '.ffx', '.mogrt', '.aex'}

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_URL     = 'https://api.deepseek.com/v1/chat/completions'
DEEPSEEK_MODEL   = 'deepseek-chat'

# ── AE keyword → subcategory rules ────────────────────────────────────────────
# Evaluated in order; first match wins
AE_KEYWORD_RULES: list[tuple[list[str], str]] = [
    (['lower third', 'lower-third'],                           'After Effects - Lower Thirds'),
    (['logo reveal', 'logo sting', 'logo opener'],             'After Effects - Logo Reveal'),
    (['wedding', 'romance', 'love story', 'invitation'],       'After Effects - Wedding & Romance'),
    (['slideshow', 'photo slide', 'photo album'],              'After Effects - Slideshow'),
    (['parallax', 'photo gallery', 'gallery'],                 'After Effects - Photo Album & Gallery'),
    (['lyric', 'lyrics', 'music video'],                       'After Effects - Lyric & Music Video'),
    (['audio visual', 'visualizer', 'equalizer', 'waveform'],  'After Effects - Music & Audio Visualizer'),
    (['news', 'broadcast', 'channel ident'],                   'After Effects - News & Broadcast'),
    (['infographic', 'data viz', 'chart', 'statistic'],        'After Effects - Infographic & Data Viz'),
    (['3d', 'particle', 'particles'],                          'After Effects - 3D & Particle'),
    (['glitch', 'distortion', 'noise', 'vhs', 'retro'],        'After Effects - VHS & Retro'),
    (['christmas', 'holiday', 'new year', 'halloween',
      'thanksgiving', 'easter', 'valentine'],                  'After Effects - Christmas & Holiday'),
    (['sport', 'action', 'soccer', 'football', 'basketball'],  'After Effects - Sport & Action'),
    (['kids', 'cartoon', 'child', 'education'],                'After Effects - Kids & Cartoons'),
    (['real estate', 'realty', 'property', 'mortgage'],        'After Effects - Real Estate'),
    (['map', 'location', 'travel route', 'navigate'],          'After Effects - Map & Location'),
    (['mockup', 'device', 'phone', 'screen'],                  'After Effects - Mockup & Device'),
    (['event', 'party', 'celebration', 'concert', 'festival'], 'After Effects - Event & Party'),
    (['social media', 'instagram', 'facebook', 'twitter',
      'youtube thumbnail', 'tiktok'],                          'After Effects - Social Media'),
    (['product promo', 'product showcase', 'e-commerce',
      'promo', 'advertising', 'ad '],                          'After Effects - Product Promo'),
    (['trailer', 'teaser', 'coming soon'],                     'After Effects - Trailer & Teaser'),
    (['cinematic', 'film', 'movie', 'blockbuster'],            'After Effects - Cinematic & Film'),
    (['corporate', 'business', 'company', 'presentation',
      'professional', 'office'],                               'After Effects - Corporate & Business'),
    (['transition', 'motion pack', 'fx pack'],                 'After Effects - Transition Pack'),
    (['broadcast', 'package', 'promo package'],                'After Effects - Broadcast Package'),
    (['character', 'explainer', 'animation', 'mascot'],        'After Effects - Character & Explainer'),
    (['liquid', 'fluid', 'water', 'ink', 'splash'],            'After Effects - Liquid & Fluid'),
    (['intro', 'opener', 'open', 'ident'],                     'After Effects - Intro & Opener'),
    (['title', 'typography', 'text', 'kinetic', 'headline'],   'After Effects - Title & Typography'),
    (['motion graphic', 'motion pack'],                        'After Effects - Motion Graphics Pack'),
    (['preset', 'presets', 'plugin', 'script'],                'After Effects - Preset Pack'),
]


def keyword_classify(name: str) -> Optional[str]:
    """Return AE subcategory from folder name keywords, or None if no match."""
    name_lower = name.lower()
    for keywords, category in AE_KEYWORD_RULES:
        if any(kw in name_lower for kw in keywords):
            return category
    return None


# ── Journal ───────────────────────────────────────────────────────────────────
def journal_correction(src: str, dest: str, clean_name: str,
                       category: str, confidence: int) -> None:
    if not JOURNAL_FILE.exists():
        return
    con = sqlite3.connect(str(JOURNAL_FILE))
    with con:
        con.execute(
            '''INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at)
               VALUES (?,?,?,?,?,?,?)''',
            (src, dest, os.path.basename(src), clean_name, category, confidence,
             datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'))
        )
    con.close()


# ── Content inspection ────────────────────────────────────────────────────────
def has_ae_files(folder: Path) -> bool:
    """Walk folder and return True if any AE template file is found."""
    try:
        for root, dirs, files in os.walk(str(folder)):
            for fn in files:
                if os.path.splitext(fn)[1].lower() in AE_EXTENSIONS:
                    return True
    except (PermissionError, OSError):
        pass
    return False


def ext_profile(folder: Path) -> dict:
    """Return extension counts and dominant extension."""
    counts: Counter = Counter()
    try:
        for root, dirs, files in os.walk(str(folder)):
            for fn in files:
                counts[os.path.splitext(fn)[1].lower()] += 1
    except (PermissionError, OSError):
        pass
    return {
        'counts': dict(counts.most_common(8)),
        'dominant': counts.most_common(1)[0][0] if counts else '',
        'total': sum(counts.values()),
    }


# ── DeepSeek ──────────────────────────────────────────────────────────────────
def deepseek_classify_ae(items: list[dict]) -> list[dict]:
    """Classify ambiguous AE items to the correct AE subcategory."""
    import urllib.request
    if not DEEPSEEK_API_KEY:
        print('[WARN] DEEPSEEK_API_KEY not set; skipping AI classification')
        return [{**i, 'ai_category': None, 'ai_confidence': 60} for i in items]

    ae_subcats = [c for _, c in AE_KEYWORD_RULES]
    ae_subcats.append('After Effects - Other')
    # Deduplicate preserving order
    seen: set = set()
    unique_cats: list = []
    for c in ae_subcats:
        if c not in seen:
            seen.add(c)
            unique_cats.append(c)

    batch_text = '\n'.join(
        f'{j+1}. "{it["folder_name"]}" | {it["ext_summary"]} | found in: {it["source_dir"]}'
        for j, it in enumerate(items)
    )

    prompt = f"""You are classifying Adobe After Effects template folders. These items were found
in non-AE directories and need to be moved to the correct AE subcategory.

Valid AE subcategories:
{chr(10).join(f'- {c}' for c in unique_cats)}

For each item, select the MOST SPECIFIC matching subcategory. Use "After Effects - Other" only
if no other category fits clearly.

Respond with a JSON array:
[{{"index":1,"category":"<subcategory>","confidence":<50-100>,"clean_name":"<display name>","reasoning":"<one sentence>"}}]

Items:
{batch_text}"""

    payload = json.dumps({
        'model': DEEPSEEK_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 2000,
    }).encode()

    req = urllib.request.Request(
        DEEPSEEK_URL, data=payload,
        headers={
            'Authorization': f'Bearer {DEEPSEEK_API_KEY}',
            'Content-Type': 'application/json',
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
        raw = data['choices'][0]['message']['content'].strip()
        raw = re.sub(r'^```(?:json)?\s*', '', raw, flags=re.MULTILINE)
        raw = re.sub(r'\s*```$', '', raw, flags=re.MULTILINE)
        results = json.loads(raw)
        for r in results:
            idx = r.get('index', 0) - 1
            if 0 <= idx < len(items):
                items[idx]['ai_category']   = r.get('category', 'After Effects - Other')
                items[idx]['ai_confidence'] = r.get('confidence', 70)
                items[idx]['ai_clean_name'] = r.get('clean_name', items[idx]['folder_name'])
                items[idx]['ai_reasoning']  = r.get('reasoning', '')
        return items
    except Exception as e:
        print(f'  [ERROR] DeepSeek call failed: {e}')
        return [{**i, 'ai_category': 'After Effects - Other', 'ai_confidence': 50} for i in items]


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
def cmd_scan(scan_dirs: list[Path]) -> None:
    """Walk scan dirs and print all folders containing AE files."""
    print('Scanning for misplaced AE template folders...\n')
    total = 0
    for sdir in scan_dirs:
        if not sdir.exists():
            print(f'  [SKIP] {sdir} — not found')
            continue
        found = []
        for item in sdir.iterdir():
            if item.is_dir() and has_ae_files(item):
                found.append(item.name)
        if found:
            print(f'  {sdir.name}: {len(found)} AE items')
            for nm in found:
                print(f'    - {nm}')
            total += len(found)
        else:
            print(f'  {sdir.name}: 0 AE items')
    print(f'\nTotal AE items misplaced: {total}')
    if total == 0:
        print('Nothing to do.')


def cmd_analyze(scan_dirs: list[Path]) -> None:
    """Classify all misplaced AE items."""
    print('Analyzing misplaced AE template folders...\n')
    results = []
    needs_ai = []

    for sdir in scan_dirs:
        if not sdir.exists():
            continue
        for item in sdir.iterdir():
            if not item.is_dir() or not has_ae_files(item):
                continue

            folder_name = item.name
            profile = ext_profile(item)
            rule_cat = keyword_classify(folder_name)

            if rule_cat:
                results.append({
                    'folder_name':   folder_name,
                    'source_dir':    str(sdir),
                    'current_path':  str(item),
                    'new_category':  rule_cat,
                    'clean_name':    folder_name,
                    'confidence':    85,
                    'method':        'keyword_rule',
                    'ext_summary':   str(profile['counts']),
                })
                print(f'  [RULE] {folder_name}\n         -> {rule_cat}')
            else:
                needs_ai.append({
                    'folder_name': folder_name,
                    'source_dir':  str(sdir),
                    'current_path': str(item),
                    'ext_summary':  str(profile['counts']),
                })

    if needs_ai:
        print(f'\nCalling DeepSeek for {len(needs_ai)} unmatched items...')
        for i in range(0, len(needs_ai), 10):
            batch = deepseek_classify_ae(needs_ai[i:i+10])
            for it in batch:
                cat  = it.get('ai_category', 'After Effects - Other')
                conf = it.get('ai_confidence', 60)
                results.append({
                    'folder_name':  it['folder_name'],
                    'source_dir':   it['source_dir'],
                    'current_path': it['current_path'],
                    'new_category': cat,
                    'clean_name':   it.get('ai_clean_name', it['folder_name']),
                    'confidence':   conf,
                    'method':       'deepseek',
                    'ext_summary':  it['ext_summary'],
                    'ai_reasoning': it.get('ai_reasoning', ''),
                })
                print(f'  [AI]   {it["folder_name"]}\n         -> {cat} ({conf}%)')

    with open(str(RESULTS_FILE), 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)

    print(f'\nSaved {len(results)} results to {RESULTS_FILE.name}')
    if not results:
        print('No AE items found in scanned directories.')
    else:
        cats = Counter(r['new_category'] for r in results)
        for cat, n in cats.most_common():
            print(f'  {n:3d}x  {cat}')


def cmd_apply(dry_run: bool = False) -> None:
    tag = '[DRY]' if dry_run else '[MOVE]'
    if not RESULTS_FILE.exists():
        print('No results file found. Run --analyze first.')
        return

    with open(str(RESULTS_FILE), encoding='utf-8') as f:
        results = json.load(f)

    moved = skipped = errors = 0
    for r in results:
        src       = Path(r['current_path'])
        new_cat   = r.get('new_category', 'After Effects - Other')
        clean_nm  = r.get('clean_name', src.name)
        confidence = r.get('confidence', 70)

        if not src.exists():
            print(f'  [SKIP] {src.name} — not at expected path')
            skipped += 1
            continue

        cat_dir = ORGANIZED / new_cat
        dest    = safe_dest(cat_dir, clean_nm)
        print(f'  {tag} {src.name!r}')
        print(f'       {src.parent.name}/ -> {new_cat}/{clean_nm}')

        if not dry_run:
            try:
                cat_dir.mkdir(parents=True, exist_ok=True)
                # Use organize_run.robust_move for cross-drive + long-path safety
                from organize_run import robust_move, strip_trailing_spaces
                strip_trailing_spaces(str(src))
                robust_move(str(src), str(dest))
                journal_correction(str(src), str(dest), clean_nm, new_cat, confidence)
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
    ap = argparse.ArgumentParser(
        description='Find and correct AE templates misrouted to non-AE categories'
    )
    ap.add_argument('--scan',      action='store_true', help='Find AE items in stock/print dirs')
    ap.add_argument('--analyze',   action='store_true', help='Classify misplaced AE items')
    ap.add_argument('--apply',     action='store_true', help='Apply moves to correct AE categories')
    ap.add_argument('--dry-run',   action='store_true', help='Preview without moving')
    ap.add_argument('--scan-dirs', nargs='+', metavar='DIR',
                    help='Override directories to scan (default: Stock Footage + Stock Photos + ...)')
    args = ap.parse_args()

    scan_dirs = [Path(d) for d in args.scan_dirs] if args.scan_dirs else DEFAULT_SCAN_DIRS

    if args.scan:
        cmd_scan(scan_dirs)
    elif args.analyze:
        cmd_analyze(scan_dirs)
    elif args.apply:
        cmd_apply(dry_run=args.dry_run)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
