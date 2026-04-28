#!/usr/bin/env python3
r"""research_ae_review.py — Resolve detached AE project subfolders in
G:\Organized\_Review\After Effects - Other\.

These items are typically internal render/comp subfolders that were separated
from their parent template package (e.g. "Chinese AE CC2015 Template" was a
subfolder of a larger AE template bundle).

Strategy per item:
  1. Inspect contents: surface .aep filenames, meaningful folder names
  2. Search G:\Organized for a candidate parent template by name similarity
  3. Use marketplace_enrich for any VH-ID-bearing folder names
  4. Call DeepSeek with all gathered context: suggest either
       - A merge target (existing template dir in G:\Organized)
       - A standalone category assignment
       - "keep-in-review" with a reason

Usage:
    python research_ae_review.py --analyze             # inspect + DeepSeek all 35 items
    python research_ae_review.py --analyze --dry-run   # show analysis only, no API call
    python research_ae_review.py --apply               # execute recommendations in ae_review_results.json
    python research_ae_review.py --apply --dry-run     # preview apply moves
    python research_ae_review.py --status              # show current results file
"""

import os, sys, json, re, shutil, argparse, sqlite3
from pathlib import Path
from datetime import datetime, timezone

# ── Bootstrap ─────────────────────────────────────────────────────────────────
def _bootstrap():
    import subprocess, importlib
    for pkg in ['openai', 'requests']:
        try:
            importlib.import_module(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])
_bootstrap()

from openai import OpenAI
import requests

# ── Config ────────────────────────────────────────────────────────────────────
REVIEW_AE_OTHER = Path(r'G:\Organized\_Review\After Effects - Other')
ORGANIZED       = Path(r'G:\Organized')
RESULTS_FILE    = Path('ae_review_results.json')
JOURNAL_FILE    = 'organize_moves.db'

AE_CATEGORIES = [
    "After Effects - 3D & Particle",
    "After Effects - Broadcast Package",
    "After Effects - Character & Explainer",
    "After Effects - Christmas & Holiday",
    "After Effects - Cinematic & Film",
    "After Effects - Corporate & Business",
    "After Effects - Event & Party",
    "After Effects - Glitch & Distortion",
    "After Effects - Infographic & Data Viz",
    "After Effects - Intro & Opener",
    "After Effects - Kids & Cartoons",
    "After Effects - Liquid & Fluid",
    "After Effects - Logo Reveal",
    "After Effects - Lower Thirds",
    "After Effects - Lyric & Music Video",
    "After Effects - Motion Graphics Pack",
    "After Effects - Other",
    "After Effects - Photo Slideshow",
    "After Effects - Plugin & Script",
    "After Effects - Promo & Advertising",
    "After Effects - Real Estate & Property",
    "After Effects - Social Media",
    "After Effects - Sport & Action",
    "After Effects - Titles & Typography",
    "After Effects - Transitions & Presets",
    "After Effects - Wedding & Romance",
]

# ── DeepSeek helper ───────────────────────────────────────────────────────────
def get_api_key():
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        kf = Path('deepseek_key.txt')
        if kf.exists():
            key = kf.read_text().strip()
    if not key:
        raise RuntimeError('DEEPSEEK_API_KEY not set')
    return key

def deepseek(prompt: str, system: str = '') -> str:
    client = OpenAI(api_key=get_api_key(), base_url='https://api.deepseek.com')
    msgs = []
    if system:
        msgs.append({'role': 'system', 'content': system})
    msgs.append({'role': 'user', 'content': prompt})
    resp = client.chat.completions.create(
        model='deepseek-chat', messages=msgs,
        temperature=0.1, max_tokens=4000,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith('```'):
        raw = '\n'.join(raw.split('\n')[1:])
        raw = raw.rsplit('```', 1)[0].strip()
    return raw

# ── Item inspection ───────────────────────────────────────────────────────────
_JUNK_NAMES = {'desktop.ini', 'thumbs.db', '.ds_store', 'license.txt',
               'readme.txt', 'help.txt', '__macosx'}

def inspect_item(item_path: Path) -> dict:
    """Return a dict of extracted signals from the item directory."""
    aep_files  = []
    sub_dirs   = []
    file_exts  = set()
    text_hints = []

    try:
        for root, dirs, files in os.walk(str(item_path)):
            depth = len(Path(root).relative_to(item_path).parts)
            if depth > 3:
                continue
            for f in files:
                fl = f.lower()
                ext = Path(f).suffix.lower()
                if ext:
                    file_exts.add(ext)
                if fl.endswith('.aep'):
                    stem = Path(f).stem
                    if stem.lower() not in _JUNK_NAMES and len(stem) > 3:
                        aep_files.append(stem)
                if fl.endswith('.txt') and depth <= 1:
                    try:
                        txt = (Path(root) / f).read_text(encoding='utf-8', errors='ignore')[:400]
                        if len(txt.strip()) > 10:
                            text_hints.append(txt.strip()[:200])
                    except Exception:
                        pass
            for d in dirs:
                if d.lower() in _JUNK_NAMES:
                    continue
                if depth == 0:
                    sub_dirs.append(d)
    except Exception:
        pass

    return {
        'name':       item_path.name,
        'path':       str(item_path),
        'aep_files':  aep_files[:8],
        'sub_dirs':   sub_dirs[:10],
        'file_exts':  sorted(file_exts),
        'text_hints': text_hints[:2],
    }

# ── Parent template search ────────────────────────────────────────────────────
_STOP_WORDS = {'ae', 'after', 'effects', 'template', 'project', 'videohive',
               'vh', 'version', 'render', 'comp', 'comps', 'final', 'main',
               'chinese', 'file', 'files', 'unknown', 'master', 'scaled',
               'down', 'composition', 'all', '1st', '2nd', '3rd'}

def _search_tokens(name: str) -> list[str]:
    words = re.findall(r'[a-zA-Z]{3,}', name.lower())
    return [w for w in words if w not in _STOP_WORDS]

def find_parent_candidates(item_name: str, max_candidates: int = 5) -> list[str]:
    """Search G:\\\\Organized AE categories for templates whose names overlap with item_name."""
    tokens = _search_tokens(item_name)
    if not tokens:
        return []

    candidates = []
    ae_cats = [d for d in ORGANIZED.iterdir()
               if d.is_dir() and d.name.startswith('After Effects')]
    for cat_dir in ae_cats:
        try:
            for tpl in cat_dir.iterdir():
                if not tpl.is_dir():
                    continue
                tpl_tokens = _search_tokens(tpl.name)
                overlap = len(set(tokens) & set(tpl_tokens))
                if overlap >= 2 or (len(tokens) >= 1 and overlap >= 1 and len(tokens) <= 2):
                    candidates.append((overlap, str(tpl)))
        except Exception:
            pass

    # Sort by overlap descending, return top N
    candidates.sort(key=lambda x: -x[0])
    return [p for _, p in candidates[:max_candidates]]

# ── DeepSeek batch analysis ───────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a design asset librarian expert. You will analyze detached After Effects
project subfolders and determine the best destination for each one.

For each item respond with a JSON object (no markdown, no explanation):
{
  "name": "<folder name>",
  "action": "merge" | "categorize" | "keep-in-review",
  "target": "<full path of target parent dir (if merge), or AE category name (if categorize), or reason (if keep-in-review)>",
  "confidence": <50-100>,
  "clean_name": "<suggested display name for the item>",
  "notes": "<brief reasoning>"
}

For merge: target must be an existing full path from the candidates list.
For categorize: target must be one of the valid AE category names provided.
For keep-in-review: explain why (e.g. "insufficient context").

Respond with a JSON array of objects, one per item."""

def build_batch_prompt(items_info: list[dict]) -> str:
    cats_str = '\n'.join(f'  - {c}' for c in AE_CATEGORIES)
    lines = [
        f'Valid AE categories:\n{cats_str}\n',
        'Analyze these detached AE subfolders:\n',
    ]
    for info in items_info:
        line_parts = [f'  name: "{info["name"]}"']
        if info['aep_files']:
            line_parts.append(f'  .aep files: {info["aep_files"]}')
        if info['sub_dirs']:
            line_parts.append(f'  subdirs: {info["sub_dirs"]}')
        if info['file_exts']:
            line_parts.append(f'  extensions: {info["file_exts"]}')
        if info.get('parent_candidates'):
            line_parts.append(f'  parent candidates (path): {info["parent_candidates"][:3]}')
        if info['text_hints']:
            hint = info['text_hints'][0][:100]
            line_parts.append(f'  text hint: "{hint}"')
        lines.append('\n'.join(line_parts))
        lines.append('')
    return '\n'.join(lines)

# ── Journal write ─────────────────────────────────────────────────────────────
def journal_write(src: str, dest: str, clean_name: str, category: str, confidence: int):
    if not os.path.exists(JOURNAL_FILE):
        return
    try:
        con = sqlite3.connect(JOURNAL_FILE)
        con.execute('''CREATE TABLE IF NOT EXISTS moves
            (id INTEGER PRIMARY KEY, src TEXT, dest TEXT, disk_name TEXT,
             clean_name TEXT, category TEXT, confidence INTEGER,
             moved_at TEXT, undone_at TEXT)''')
        con.execute('''INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at)
                       VALUES (?,?,?,?,?,?,?)''',
                    (src, dest, os.path.basename(src), clean_name, category, confidence,
                     datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')))
        con.commit()
        con.close()
    except Exception:
        pass

# ── Safe destination path ─────────────────────────────────────────────────────
def safe_dest(base_dir: Path, clean_name: str) -> Path:
    """Return a non-colliding destination path."""
    dest = base_dir / clean_name
    if not dest.exists():
        return dest
    suffix = 1
    while True:
        candidate = base_dir / f'{clean_name} ({suffix})'
        if not candidate.exists():
            return candidate
        suffix += 1

# ── Analyze command ───────────────────────────────────────────────────────────
def cmd_analyze(dry_run: bool = False):
    if not REVIEW_AE_OTHER.exists():
        print(f'ERROR: {REVIEW_AE_OTHER} does not exist')
        sys.exit(1)

    items = sorted(p for p in REVIEW_AE_OTHER.iterdir() if p.is_dir())
    print(f'Found {len(items)} items in {REVIEW_AE_OTHER}')

    # Load existing results to avoid re-processing already analyzed items
    existing: dict = {}
    if RESULTS_FILE.exists():
        try:
            for r in json.loads(RESULTS_FILE.read_text(encoding='utf-8')):
                existing[r['name']] = r
        except Exception:
            pass

    all_results = list(existing.values())
    to_process  = [it for it in items if it.name not in existing]
    print(f'Already analyzed: {len(existing)}, to process: {len(to_process)}')

    if not to_process:
        print('Nothing new to analyze.')
        _print_status(all_results)
        return

    # Inspect all items to process
    print('\nInspecting items...')
    infos = []
    for item in to_process:
        info = inspect_item(item)
        info['parent_candidates'] = find_parent_candidates(item.name)
        short_cands = [str(Path(p).relative_to(ORGANIZED)) for p in info['parent_candidates']]
        print(f'  [{item.name}]  aep={info["aep_files"][:2]}  '
              f'cands={short_cands[:2] or "none"}')
        infos.append(info)

    if dry_run:
        print('\n[DRY RUN] Would call DeepSeek for batch analysis. Skipping API call.')
        return

    # Batch analysis: process up to 10 items per DeepSeek call
    BATCH = 10
    for batch_start in range(0, len(infos), BATCH):
        batch = infos[batch_start:batch_start + BATCH]
        print(f'\nCalling DeepSeek for items {batch_start+1}-{batch_start+len(batch)}...')
        prompt = build_batch_prompt(batch)
        try:
            raw = deepseek(prompt, system=SYSTEM_PROMPT)
            batch_results = json.loads(raw)
            if not isinstance(batch_results, list):
                batch_results = [batch_results]
        except json.JSONDecodeError as e:
            print(f'  WARNING: JSON parse failed ({e}). Saving raw for review.')
            for info in batch:
                all_results.append({
                    'name': info['name'], 'action': 'keep-in-review',
                    'target': 'parse-error', 'confidence': 0,
                    'clean_name': info['name'], 'notes': str(raw[:200]),
                    'src_path': info['path'],
                })
            continue
        except Exception as e:
            print(f'  ERROR: DeepSeek call failed: {e}')
            continue

        # Merge responses back (match by name)
        name_map = {i['name']: i for i in batch}
        for res in batch_results:
            name = res.get('name', '')
            src_info = name_map.get(name, {})
            res['src_path'] = src_info.get('path', str(REVIEW_AE_OTHER / name))
            all_results.append(res)
            action = res.get('action', '?')
            target = res.get('target', '?')[:60]
            conf   = res.get('confidence', 0)
            print(f'  [{name}]  {action}  ->  {target}  ({conf}%)')

    # Save results
    RESULTS_FILE.write_text(json.dumps(all_results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\nSaved {len(all_results)} results to {RESULTS_FILE}')
    _print_status(all_results)

# ── Apply command ─────────────────────────────────────────────────────────────
def cmd_apply(dry_run: bool = False):
    if not RESULTS_FILE.exists():
        print(f'ERROR: {RESULTS_FILE} not found. Run --analyze first.')
        sys.exit(1)

    results = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
    print(f'Processing {len(results)} recommendations...')
    moved = skipped = kept = errors = 0

    for res in results:
        name       = res.get('name', '?')
        action     = res.get('action', 'keep-in-review')
        target     = res.get('target', '')
        confidence = int(res.get('confidence', 0))
        clean_name = res.get('clean_name', name)
        src_path   = Path(res.get('src_path', str(REVIEW_AE_OTHER / name)))

        if not src_path.exists():
            print(f'  [SKIP] {name}: source gone ({src_path})')
            skipped += 1
            continue

        tag = '[DRY]' if dry_run else '[MOVE]'

        if action == 'keep-in-review':
            print(f'  [KEEP] {name}: {target}')
            kept += 1
            continue

        if action == 'merge':
            parent = Path(target)
            if not parent.exists():
                print(f'  [ERROR] {name}: merge target missing: {parent}')
                errors += 1
                continue
            dest = safe_dest(parent, clean_name)
            print(f'  {tag} MERGE {name!r} -> {str(dest)[-70:]}')
            if not dry_run:
                try:
                    shutil.move(str(src_path), str(dest))
                    journal_write(str(src_path), str(dest), clean_name,
                                  parent.parent.name, confidence)
                    moved += 1
                except Exception as e:
                    print(f'    ERROR: {e}')
                    errors += 1
            else:
                moved += 1

        elif action == 'categorize':
            cat_dir = ORGANIZED / target
            if not cat_dir.is_dir():
                # Check if it's a valid category that just doesn't exist yet
                if any(target == c for c in AE_CATEGORIES):
                    if not dry_run:
                        cat_dir.mkdir(parents=True, exist_ok=True)
                else:
                    print(f'  [ERROR] {name}: invalid category: {target!r}')
                    errors += 1
                    continue
            dest = safe_dest(cat_dir, clean_name)
            print(f'  {tag} MOVE {name!r} -> {target}/{clean_name}')
            if not dry_run:
                try:
                    shutil.move(str(src_path), str(dest))
                    journal_write(str(src_path), str(dest), clean_name, target, confidence)
                    moved += 1
                except Exception as e:
                    print(f'    ERROR: {e}')
                    errors += 1
            else:
                moved += 1
        else:
            print(f'  [UNKNOWN action={action}] {name}')
            kept += 1

    print(f'\nDone: {moved} moved, {skipped} skipped, {kept} kept-in-review, {errors} errors')

# ── Status command ─────────────────────────────────────────────────────────────
def _print_status(results: list):
    from collections import Counter
    actions = Counter(r.get('action', '?') for r in results)
    print(f'\n--- Results summary ({len(results)} total) ---')
    for act, n in actions.most_common():
        print(f'  {act}: {n}')
    # Show categorize/merge targets
    for r in results:
        if r.get('action') != 'keep-in-review':
            tgt = r.get('target', '?')
            tgt_short = tgt[-60:] if len(tgt) > 60 else tgt
            print(f'  [{r["confidence"]:3d}%] {r.get("action","?")} {r.get("name","?")}  -> {tgt_short}')

def cmd_status():
    if not RESULTS_FILE.exists():
        print('No results file yet. Run --analyze first.')
        return
    results = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
    _print_status(results)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(
        description='Resolve detached AE project subfolders in _Review/After Effects - Other')
    ap.add_argument('--analyze',  action='store_true', help='Inspect items and call DeepSeek')
    ap.add_argument('--apply',    action='store_true', help='Execute recommendations')
    ap.add_argument('--status',   action='store_true', help='Show current results file')
    ap.add_argument('--dry-run',  action='store_true', help='Preview mode (no disk changes)')
    ap.add_argument('--reset',    action='store_true', help='Delete ae_review_results.json and start fresh')
    args = ap.parse_args()

    if args.reset:
        if RESULTS_FILE.exists():
            RESULTS_FILE.unlink()
            print('Deleted ae_review_results.json')
        return

    if args.analyze:
        cmd_analyze(dry_run=args.dry_run)
    elif args.apply:
        cmd_apply(dry_run=args.dry_run)
    elif args.status:
        cmd_status()
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
