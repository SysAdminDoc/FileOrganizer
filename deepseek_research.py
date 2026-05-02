#!/usr/bin/env python3
"""deepseek_research.py — Use DeepSeek to research ambiguous product IDs and
classify items in G:\\Organized\\_Review that couldn't be resolved from filename alone.

Run:
    python deepseek_research.py --research-ids   # look up product IDs via DeepSeek
    python deepseek_research.py --resolve-review  # move resolved items out of _Review
    python deepseek_research.py --web-scrape <id> # scrape product page for ID details
"""

import json
import os
import re
import shutil
import sys
from pathlib import Path

# Bootstrap
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

# ── Config ─────────────────────────────────────────────────────────────────────
REVIEW_ROOT   = Path(r'G:\Organized\_Review')
ORGANIZED     = Path(r'G:\Organized')
RESULTS_DIR   = Path('classification_results')

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
    messages = []
    if system:
        messages.append({'role': 'system', 'content': system})
    messages.append({'role': 'user', 'content': prompt})
    resp = client.chat.completions.create(
        model='deepseek-v4-flash',
        messages=messages,
        temperature=0.1,
        max_tokens=3000,
    )
    raw = resp.choices[0].message.content.strip()
    if raw.startswith('```'):
        raw = '\n'.join(raw.split('\n')[1:])
        raw = raw.rsplit('```', 1)[0].strip()
    return raw

# ── Product ID research ─────────────────────────────────────────────────────────
PRODUCT_IDS = [
    # DesignBundles IDs (prefix db_ or designbundles_)
    {'id': 'db_1888916',            'platform': 'designbundles', 'pid': '1888916'},
    {'id': 'db_1889031',            'platform': 'designbundles', 'pid': '1889031'},
    {'id': 'db_1889889',            'platform': 'designbundles', 'pid': '1889889'},
    {'id': 'designbundles_1894534', 'platform': 'designbundles', 'pid': '1894534'},
    {'id': 'designbundles_1894553', 'platform': 'designbundles', 'pid': '1894553'},
    {'id': 'designbundles_1894603', 'platform': 'designbundles', 'pid': '1894603'},
    {'id': 'designbundles_1894615', 'platform': 'designbundles', 'pid': '1894615'},
    {'id': 'designbundles_1894905', 'platform': 'designbundles', 'pid': '1894905'},
    # CreativeMarket IDs (prefix cm_)
    {'id': 'cm_4804020',            'platform': 'creativemarket', 'pid': '4804020'},
    {'id': 'cm_4840406',            'platform': 'creativemarket', 'pid': '4840406'},
    {'id': 'cm_7116381',            'platform': 'creativemarket', 'pid': '7116381'},
    {'id': 'cm_7119925',            'platform': 'creativemarket', 'pid': '7119925'},
]

VALID_CATEGORIES = [
    'Fonts & Typography',
    'Stock Photos - General',
    'Photoshop - Actions & Presets',
    'Photoshop - Patterns & Textures',
    'Photoshop - Overlays & FX',
    'Photoshop - Mockups',
    'Print - Flyers & Posters',
    'Print - Invitations & Events',
    'Print - Business Cards & Stationery',
    'Print - Social Media Graphics',
    'Illustrator - Vectors & Assets',
    'Procreate - Brushes & Stamps',
    'UI Resources & Icon Sets',
    'After Effects - Other',
    'Photoshop - Other',
]


def scrape_product_page(platform: str, pid: str) -> dict:
    """Try to fetch product page title/description via HTTP for ground-truth."""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120',
        'Accept-Language': 'en-US,en;q=0.9',
    }
    try:
        if platform == 'designbundles':
            urls = [
                f'https://designbundles.net/product-{pid}',
                f'https://designbundles.net/search/?q={pid}',
            ]
        else:  # creativemarket
            urls = [
                f'https://creativemarket.com/product-{pid}',
                f'https://creativemarket.com/search?q={pid}',
            ]

        for url in urls:
            try:
                r = requests.get(url, headers=headers, timeout=10, allow_redirects=True)
                if r.status_code == 200 and len(r.text) > 500:
                    # Extract <title>
                    m = re.search(r'<title[^>]*>([^<]+)</title>', r.text, re.IGNORECASE)
                    title = m.group(1).strip() if m else ''
                    # Extract meta description
                    m2 = re.search(r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)', r.text, re.IGNORECASE)
                    desc = m2.group(1).strip() if m2 else ''
                    if title and 'page not found' not in title.lower() and '404' not in title:
                        return {'url': url, 'title': title, 'description': desc[:300]}
            except Exception:
                continue
    except Exception:
        pass
    return {}


def research_ids():
    """Use DeepSeek + web scraping to identify all product IDs."""
    print('=== Researching product IDs ===\n')

    # First try web scraping for ground truth
    scraped = {}
    for item in PRODUCT_IDS:
        print(f'  Scraping {item["id"]}...', end=' ', flush=True)
        result = scrape_product_page(item['platform'], item['pid'])
        if result:
            scraped[item['id']] = result
            print(f'OK: {result["title"][:60]}')
        else:
            print('no result')

    # Build DeepSeek prompt with scraped data as context
    scraped_context = ''
    if scraped:
        scraped_context = '\n\nWEB-SCRAPED DATA (use as ground truth where available):\n'
        for k, v in scraped.items():
            scraped_context += f'  {k}: title="{v["title"]}" desc="{v["description"][:150]}"\n'

    category_list = '\n'.join(f'  {c}' for c in VALID_CATEGORIES)

    prompt = f"""You are a design asset expert. Research these product IDs from DesignBundles.net and CreativeMarket.com.
Use your training knowledge of these platforms' product catalogs to identify each product.
{scraped_context}

For each ID, determine:
1. Product name
2. Asset type (font family, SVG bundle, PSD template, photo overlay pack, etc.)
3. Best matching category from:
{category_list}

IDs to research:
{chr(10).join(f"  - {item['id']} (platform: {item['platform']}, numeric ID: {item['pid']})" for item in PRODUCT_IDS)}

Also classify these non-ID items from _Review:
  - Misc (contains: .css .js .png files with subfolders 'images') — likely a web UI template
  - Documentation (contains: .pdf .txt) — a help/documentation folder
  - css, images, js (web asset folders) — probably parts of a web UI kit

Return ONLY a JSON array:
[
  {{"id": "db_1888916", "name": "Product Name", "type": "font/PSD/bundle/etc", "category": "Category Name", "confidence": 85, "notes": "source of info"}},
  ...
]"""

    print('\n  Querying DeepSeek for ID research...')
    raw = deepseek(prompt)

    try:
        results = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        results = json.loads(m.group()) if m else []

    print(f'\n=== DeepSeek research results ({len(results)} items) ===')
    confident = []
    uncertain = []

    for r in results:
        conf = r.get('confidence', 0)
        print(f"\n  {r['id']}")
        print(f"    Name:     {r.get('name','?')}")
        print(f"    Type:     {r.get('type','?')}")
        print(f"    Category: {r.get('category','?')}  [{conf}%]")
        print(f"    Notes:    {r.get('notes','')[:80]}")

        if conf >= 70:
            confident.append(r)
        else:
            uncertain.append(r)

    print(f'\n  Confident resolutions (>=70%): {len(confident)}')
    print(f'  Uncertain (<70%):              {len(uncertain)}')

    # Save results
    out = Path('review_research_results.json')
    out.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f'\n  Saved to {out}')

    return results


def apply_research_results(results: list, dry_run: bool = True):
    """Move resolved _Review items to their identified categories."""
    label = '[DRY]' if dry_run else '[MOVE]'
    moved = skipped = 0

    for r in results:
        item_id = r['id']
        category = r.get('category', '')
        conf = r.get('confidence', 0)
        clean_name = r.get('name', item_id)

        if conf < 70 or not category or category not in VALID_CATEGORIES:
            print(f'  SKIP (conf={conf}% or bad cat): {item_id}')
            skipped += 1
            continue

        src = REVIEW_ROOT / item_id
        if not src.exists():
            # Try case-insensitive match
            matches = [d for d in REVIEW_ROOT.iterdir() if d.name.lower() == item_id.lower()]
            if matches:
                src = matches[0]
            else:
                print(f'  SKIP (not on disk): {item_id}')
                skipped += 1
                continue

        # Sanitize clean_name for filesystem
        safe_name = re.sub(r'[<>:"/\\|?*]', '-', clean_name).strip()[:120]
        dest = ORGANIZED / category / safe_name

        # Handle collisions
        if dest.exists():
            i = 1
            while dest.exists():
                dest = ORGANIZED / category / f'{safe_name} ({i})'
                i += 1

        print(f'  {label} {item_id}')
        print(f'       -> {dest}  [{conf}%]')

        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            moved += 1
        else:
            moved += 1

    print(f'\n{label} done: {moved} would move, {skipped} skipped')
    return moved


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--research-ids',   action='store_true', help='Use DeepSeek to look up product IDs')
    ap.add_argument('--resolve-review', action='store_true', help='Apply research results to move items out of _Review')
    ap.add_argument('--dry-run',        action='store_true', help='Dry run (with --resolve-review)')
    args = ap.parse_args()

    if args.research_ids:
        research_ids()
    elif args.resolve_review:
        rfile = Path('review_research_results.json')
        if not rfile.exists():
            print('ERROR: run --research-ids first to generate review_research_results.json')
            sys.exit(1)
        results = json.loads(rfile.read_text(encoding='utf-8'))
        apply_research_results(results, dry_run=args.dry_run)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
