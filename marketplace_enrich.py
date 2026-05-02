#!/usr/bin/env python3
"""marketplace_enrich.py — Stage 2 of the 4-stage classification lookup pipeline.

Extracts numeric marketplace IDs from folder names (Videohive, MotionElements,
CreativeMarket, DesignBundles, Motion Array, Envato) and fetches the actual item
title, tags, and primary category from the marketplace.  Returns near-100%
accuracy for items with known IDs at zero AI cost.

Lookup stages (see ROADMAP.md):
  1. Community fingerprint DB       — asset_db.py         (exact SHA-256 match)
  2. Marketplace ID + fetch          — this module          (confidence 95)
  3. Name heuristics / corrections  — classify_design.py  (confidence 45-70)
  4. AI classification               — classify_design.py  (confidence 70-95)

Usage:
    python marketplace_enrich.py --scan-index org_index.json
    python marketplace_enrich.py --scan-index design_org_index.json
    python marketplace_enrich.py --scan-folder "G:\\Organized"
    python marketplace_enrich.py --lookup VH-28331308
    python marketplace_enrich.py --lookup 10003729_MotionElements_epic-slideshow
    python marketplace_enrich.py --stats
    python marketplace_enrich.py --export-unmapped    # names that had an ID but no category

API / scraping:
    Videohive:     https://videohive.net/item/x/{id}          (scrape og:title / og:url / breadcrumbs)
    MotionElements: https://api.motionelements.com/v1/elements/{id}   (free JSON API)
    CreativeMarket: https://creativemarket.com/api/2/products/{id}    (may require token)
    Fallback:      DeepSeek AI lookup (reads deepseek_key.txt or DEEPSEEK_API_KEY env var)

Cache:
    marketplace_cache.json — keyed by "{platform}:{item_id}", persistent across runs
"""

import argparse, json, os, re, sys, time
from pathlib import Path
from typing import Optional

# ── Bootstrap deps ────────────────────────────────────────────────────────────
def _bootstrap():
    import subprocess, importlib
    for pkg in ['requests', 'openai']:
        try:
            importlib.import_module(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])
_bootstrap()

import requests
from openai import OpenAI

# ── Config ────────────────────────────────────────────────────────────────────
CACHE_FILE   = Path(__file__).parent / 'marketplace_cache.json'
ORGANIZED    = Path(r'G:\Organized')
CONFIDENCE   = 95   # confidence score assigned to marketplace-ID results

REQUEST_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/124.0.0.0 Safari/537.36'
    ),
    'Accept-Language': 'en-US,en;q=0.9',
}
FETCH_TIMEOUT   = 12   # seconds per HTTP request
FETCH_RETRY     = 2    # retries on 429 / 5xx
RATE_LIMIT_WAIT = 1.5  # seconds between requests (per domain)

# ── Taxonomy mapping — marketplace category → our 84-category taxonomy ────────
# Left side: lowercase strings (or fragments) found in marketplace category breadcrumbs
# Right side: exact category name used in G:\Organized\
CATEGORY_MAP: list[tuple[str, str]] = [
    # After Effects
    ('after effects templates / slideshow',        'After Effects - Photo & Image Slideshow'),
    ('after effects templates / logo stings',      'After Effects - Logo Reveal'),
    ('after effects templates / logo reveals',     'After Effects - Logo Reveal'),
    ('after effects templates / openers',          'After Effects - Cinematic Opener'),
    ('after effects templates / corporate',        'After Effects - Corporate & Business'),
    ('after effects templates / product promo',    'After Effects - Product & App Promo'),
    ('after effects templates / titles',           'After Effects - Titles & Text'),
    ('after effects templates / broadcast',        'After Effects - Broadcast & News'),
    ('after effects templates / elements',         'After Effects - Elements & Shapes'),
    ('after effects templates / transitions',      'After Effects - Transitions & Presets'),
    ('after effects templates / infographics',     'After Effects - Infographic & Data'),
    ('after effects templates / wedding',          'After Effects - Wedding & Ceremony'),
    ('after effects templates / social media',     'After Effects - Social Media & Stories'),
    ('after effects templates / sport',            'After Effects - Sport & Action'),
    ('after effects templates / instagram',        'After Effects - Social Media & Stories'),
    ('after effects templates / music',            'After Effects - Music & Audio'),
    ('after effects templates / fashion',          'After Effects - Fashion & Beauty'),
    ('after effects templates / christmas',        'After Effects - Christmas & Holiday'),
    ('after effects templates / holiday',          'After Effects - Christmas & Holiday'),
    ('after effects templates / motion graphics',  'After Effects - Motion Graphics Pack'),
    ('after effects presets',                      'After Effects - Transitions & Presets'),
    ('after effects',                              'After Effects - Other'),
    # Premiere Pro
    ('premiere pro templates',                     'Premiere Pro - Titles & Text'),
    ('premiere pro presets',                       'Premiere Pro - Color Grade & LUTs'),
    # Photoshop
    ('actions',                                    'Photoshop - Actions & Presets'),
    ('add-ons / actions',                          'Photoshop - Actions & Presets'),
    ('brushes',                                    'Photoshop - Brushes & Styles'),
    ('add-ons / brushes',                          'Photoshop - Brushes & Styles'),
    ('mockups',                                    'Mockups - Other'),
    ('add-ons / mockups',                          'Mockups - Other'),
    ('textures',                                   'Photoshop - Patterns & Textures'),
    ('patterns',                                   'Photoshop - Patterns & Textures'),
    ('overlays',                                   'Photoshop - Overlays & FX'),
    # Fonts
    ('fonts',                                      'Fonts & Typography'),
    # LUTs / Color
    ('luts',                                       'Color Grading & LUTs'),
    ('lightroom presets',                          'Lightroom Presets'),
    ('presets',                                    'Lightroom Presets'),
    # Stock
    ('stock footage',                              'Stock Footage - General'),
    ('stock video',                                'Stock Footage - General'),
    ('motion backgrounds',                         'Stock Footage - Abstract & VFX'),
    ('backgrounds',                                'Stock Footage - Abstract & VFX'),
    ('stock music',                                'Stock Music & Audio'),
    ('music',                                      'Stock Music & Audio'),
    ('stock photos',                               'Stock Photos - General'),
    # Print
    ('print templates / flyers',                   'Print - Flyers & Posters'),
    ('print templates / brochures',                'Print - Brochures & Catalogs'),
    ('print templates / business cards',           'Print - Business Cards'),
    ('print templates',                            'Print - Other'),
    # Illustrator
    ('vector',                                     'Illustrator - Vector Graphics'),
    ('infographics',                               'Illustrator - Infographic Templates'),
    # Web
    ('wordpress',                                  'Web Template - WordPress Themes'),
    ('html',                                       'Web Template - HTML & CSS'),
    ('ui',                                         'UI Resources'),
    # Plugins / Scripts
    ('after effects scripts',                      'After Effects - Plugin & Script'),
    ('after effects plugins',                      'After Effects - Plugin & Script'),
    # Procreate
    ('procreate',                                  'Procreate - Brushes & Textures'),
    # MotionElements categories
    ('after effects templates',                    'After Effects - Other'),
    ('premiere pro templates',                     'Premiere Pro - Other'),
    ('final cut',                                  'After Effects - Other'),
    ('animation',                                  'After Effects - Motion Graphics Pack'),
    ('lower thirds',                               'After Effects - Titles & Text'),
]

def map_category(raw: str, title: str = '', tags: list[str] | None = None) -> Optional[str]:
    """Map a marketplace category string to our taxonomy. Returns None if no match."""
    raw_low = raw.lower()
    for fragment, mapped in CATEGORY_MAP:
        if fragment in raw_low:
            return mapped

    # Fallback: use title keywords
    if title:
        t = title.lower()
        if 'slideshow' in t:           return 'After Effects - Photo & Image Slideshow'
        if 'logo' in t and 'reveal' in t: return 'After Effects - Logo Reveal'
        if 'opener' in t:              return 'After Effects - Cinematic Opener'
        if 'wedding' in t:             return 'After Effects - Wedding & Ceremony'
        if 'christmas' in t or 'holiday' in t: return 'After Effects - Christmas & Holiday'
        if 'sport' in t or 'soccer' in t or 'football' in t: return 'After Effects - Sport & Action'
        if 'instagram' in t or 'social' in t: return 'After Effects - Social Media & Stories'
        if 'broadcast' in t or 'news' in t: return 'After Effects - Broadcast & News'
        if 'mockup' in t:              return 'Mockups - Other'
        if 'font' in t:                return 'Fonts & Typography'
        if 'lut' in t:                 return 'Color Grading & LUTs'
    return None


# ── ID extraction ──────────────────────────────────────────────────────────────
# Each tuple: (compiled_regex, platform, group_index_for_id)
# Patterns ordered from most specific to least specific.
_ID_PATTERNS: list[tuple[re.Pattern, str]] = [
    # MotionElements: 10003729_MotionElements_epic-slideshow
    (re.compile(r'^(\d{7,9})_MotionElements_', re.IGNORECASE), 'motionelements'),
    # Explicit VH- prefix: VH-28331308, VH_6808513
    (re.compile(r'^VH[-_](\d{5,9})', re.IGNORECASE), 'videohive'),
    # Explicit ME- prefix: ME-1234567
    (re.compile(r'^ME[-_](\d{5,9})', re.IGNORECASE), 'motionelements'),
    # CreativeMarket: cm_4804020
    (re.compile(r'^cm[-_](\d{5,9})(?:[^0-9]|$)', re.IGNORECASE), 'creativemarket'),
    # DesignBundles: db_1888916, designbundles_1894534
    (re.compile(r'^(?:db|designbundles)[-_](\d{5,9})', re.IGNORECASE), 'designbundles'),
    # Motion Array: MA-123456, motionarray-123456
    (re.compile(r'^(?:MA|motionarray)[-_](\d{5,8})', re.IGNORECASE), 'motionarray'),
    # Graphic River: GR-123456
    (re.compile(r'^GR[-_](\d{5,9})', re.IGNORECASE), 'graphicriver'),
    # Videohive: 9-digit ID at START (always leading zero for older IDs)
    # e.g., 083555299-happy-hanukkah, 089367555-fast-sildeshow
    (re.compile(r'^(0\d{8})[-_]'), 'videohive'),
    # Videohive: 7-9 digit numeric prefix + hyphen + alpha char
    # e.g., 10003729-something, but NOT "30-satin-curtain" (too short)
    (re.compile(r'^(\d{7,9})-[a-zA-Z]'), 'videohive'),
    # Envato/GraphicRiver: name-ends-with-NNNNN (5-7 digits at end, after alpha)
    # e.g., 30-satin-curtain-backgrounds-29294, abstract-background-137530
    # Exclude pure numeric names and items already matched above
    (re.compile(r'[a-zA-Z]-(\d{5,7})(?:-GFXTRA.*)?(?:\s+\d+)?$', re.IGNORECASE), 'envato'),
]

def extract_id(folder_name: str) -> tuple[str, str] | tuple[None, None]:
    """Return (platform, item_id) extracted from a folder name, or (None, None)."""
    name = folder_name.strip()
    for pat, platform in _ID_PATTERNS:
        m = pat.search(name)
        if m:
            return platform, m.group(1)
    return None, None


# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[str, dict] = {}

def _load_cache():
    global _cache
    if CACHE_FILE.exists():
        try:
            _cache = json.loads(CACHE_FILE.read_text('utf-8'))
        except Exception:
            _cache = {}

def _save_cache():
    CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), 'utf-8')

def _cache_key(platform: str, item_id: str) -> str:
    return f'{platform}:{item_id}'


# ── HTTP helpers ──────────────────────────────────────────────────────────────
_last_request_at: dict[str, float] = {}

def _throttled_get(url: str, domain: str) -> Optional[requests.Response]:
    """GET with per-domain rate limiting and retry on 429/5xx."""
    wait = RATE_LIMIT_WAIT - (time.time() - _last_request_at.get(domain, 0))
    if wait > 0:
        time.sleep(wait)
    for attempt in range(FETCH_RETRY + 1):
        try:
            resp = requests.get(url, headers=REQUEST_HEADERS, timeout=FETCH_TIMEOUT,
                                allow_redirects=True)
            _last_request_at[domain] = time.time()
            if resp.status_code == 429 or resp.status_code >= 500:
                time.sleep(3 * (attempt + 1))
                continue
            return resp
        except requests.RequestException:
            if attempt < FETCH_RETRY:
                time.sleep(2)
    return None


def _og(html: str, prop: str) -> str:
    """Extract an og: meta tag value from raw HTML."""
    m = re.search(rf'<meta[^>]+property=["\']og:{prop}["\'][^>]+content=["\']([^"\']+)["\']',
                  html, re.IGNORECASE)
    if not m:
        m = re.search(rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:{prop}["\']',
                      html, re.IGNORECASE)
    return m.group(1).strip() if m else ''


# ── Marketplace fetchers ──────────────────────────────────────────────────────
def fetch_videohive(item_id: str) -> Optional[dict]:
    """Scrape videohive.net for item title and category."""
    url = f'https://videohive.net/item/x/{item_id}'
    resp = _throttled_get(url, 'videohive.net')
    if not resp or resp.status_code not in (200,):
        return None

    html = resp.text
    title = _og(html, 'title') or ''
    # Remove marketplace suffix: "Happy Hanukkah - After Effects Templates | Envato..."
    title = re.sub(r'\s*\|.*$', '', title).strip()
    title = re.sub(r'\s*[-–]\s*(?:After Effects Templates?|Premiere Pro.*|Envato.*)$', '',
                   title, flags=re.IGNORECASE).strip()

    # Extract breadcrumb category: look for category links in breadcrumb nav
    # e.g.  /category/after-effects-templates/slideshow
    category_raw = ''
    m = re.search(r'videohive\.net/category/([a-z0-9/_-]+)', html)
    if m:
        category_raw = m.group(1).replace('-', ' ').replace('/', ' / ').title()

    # Fallback: og:url often encodes the canonical category path
    if not category_raw:
        og_url = _og(html, 'url')
        # https://videohive.net/item/happy-hanukkah/083555299
        # category is NOT in the item URL, so try meta description
        desc = _og(html, 'description') or ''
        m2 = re.search(r'(?:in|category)[:\s]+([A-Za-z &/]+)(?:[,.]|$)', desc, re.IGNORECASE)
        if m2:
            category_raw = m2.group(1).strip()

    tags_raw = _og(html, 'article:tag') or ''
    tags = [t.strip() for t in re.split(r'[,;]', tags_raw) if t.strip()]

    if not title:
        return None

    category = map_category(category_raw, title, tags)
    return {
        'platform': 'videohive',
        'item_id':  item_id,
        'title':    title,
        'category_raw': category_raw,
        'category': category,
        'tags':     tags,
        'url':      resp.url,
        'confidence': CONFIDENCE if category else 70,
    }


def fetch_motionelements(item_id: str) -> Optional[dict]:
    """Try MotionElements public API then scrape fallback."""
    api_url = f'https://api.motionelements.com/v1/elements/{item_id}'
    resp = _throttled_get(api_url, 'api.motionelements.com')
    if resp and resp.status_code == 200:
        try:
            data = resp.json()
            title        = data.get('title') or data.get('name') or ''
            category_raw = (data.get('category') or {}).get('name') or ''
            tags         = [t.get('name','') for t in data.get('tags', [])]
            category     = map_category(category_raw, title, tags)
            return {
                'platform': 'motionelements',
                'item_id':  item_id,
                'title':    title,
                'category_raw': category_raw,
                'category': category,
                'tags':     tags,
                'url':      f'https://www.motionelements.com/en/{item_id}/',
                'confidence': CONFIDENCE if category else 70,
            }
        except Exception:
            pass

    # Scrape fallback
    page_url = f'https://www.motionelements.com/en/stock-after-effects/{item_id}/'
    resp2 = _throttled_get(page_url, 'www.motionelements.com')
    if not resp2 or resp2.status_code not in (200,):
        return None
    html  = resp2.text
    title = _og(html, 'title') or ''
    title = re.sub(r'\s*[-|].*$', '', title).strip()

    m = re.search(r'"category"\s*:\s*"([^"]+)"', html)
    category_raw = m.group(1) if m else ''
    category = map_category(category_raw, title)
    if not title:
        return None
    return {
        'platform': 'motionelements',
        'item_id':  item_id,
        'title':    title,
        'category_raw': category_raw,
        'category': category,
        'tags':     [],
        'url':      resp2.url,
        'confidence': CONFIDENCE if category else 70,
    }


def fetch_creativemarket(item_id: str) -> Optional[dict]:
    """Scrape creativemarket.com for item title and category."""
    url = f'https://creativemarket.com/product/{item_id}'
    resp = _throttled_get(url, 'creativemarket.com')
    if not resp or resp.status_code not in (200,):
        return None
    html  = resp.text
    title = _og(html, 'title') or ''
    title = re.sub(r'\s*[-|].*Creative Market.*$', '', title, flags=re.IGNORECASE).strip()
    m = re.search(r'"category_name"\s*:\s*"([^"]+)"', html)
    category_raw = m.group(1) if m else ''
    category = map_category(category_raw, title)
    if not title:
        return None
    return {
        'platform': 'creativemarket',
        'item_id':  item_id,
        'title':    title,
        'category_raw': category_raw,
        'category': category,
        'tags':     [],
        'url':      resp.url,
        'confidence': CONFIDENCE if category else 70,
    }


def fetch_envato(item_id: str) -> Optional[dict]:
    """Generic Envato item lookup (Graphic River / AudioJungle / etc.)."""
    # Try videohive first; if the redirect goes elsewhere, handle gracefully
    result = fetch_videohive(item_id)
    if result:
        result['platform'] = 'envato'
        return result
    # Try GraphicRiver
    url = f'https://graphicriver.net/item/x/{item_id}'
    resp = _throttled_get(url, 'graphicriver.net')
    if not resp or resp.status_code not in (200,):
        return None
    html  = resp.text
    title = _og(html, 'title') or ''
    title = re.sub(r'\s*[-|].*$', '', title).strip()
    m = re.search(r'graphicriver\.net/category/([a-z0-9/_-]+)', html)
    category_raw = m.group(1).replace('-', ' ').replace('/', ' / ').title() if m else ''
    category = map_category(category_raw, title)
    if not title:
        return None
    return {
        'platform': 'envato',
        'item_id':  item_id,
        'title':    title,
        'category_raw': category_raw,
        'category': category,
        'tags':     [],
        'url':      resp.url,
        'confidence': CONFIDENCE if category else 70,
    }


# ── DeepSeek fallback ─────────────────────────────────────────────────────────
def _get_deepseek_key() -> Optional[str]:
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        kf = Path(__file__).parent / 'deepseek_key.txt'
        if kf.exists():
            key = kf.read_text().strip()
    return key or None


def fetch_via_deepseek(platform: str, item_id: str, folder_name: str) -> Optional[dict]:
    """Use DeepSeek as a last-resort lookup when scraping fails or returns no title."""
    key = _get_deepseek_key()
    if not key:
        return None
    client = OpenAI(api_key=key, base_url='https://api.deepseek.com')
    prompt = (
        f'I have a design asset folder named "{folder_name}". '
        f'The marketplace is "{platform}" and the item ID is {item_id}. '
        f'Based on your training knowledge, what is the title of this item, '
        f'and what category does it belong to? '
        f'Reply with ONLY a JSON object with keys: '
        f'"title" (string), "category_raw" (marketplace category as a string), '
        f'"tags" (array of strings). No commentary.'
    )
    try:
        resp = client.chat.completions.create(
            model='deepseek-v4-flash',
            messages=[{'role': 'user', 'content': prompt}],
            temperature=0.05,
            max_tokens=300,
        )
        raw = resp.choices[0].message.content.strip()
        if raw.startswith('```'):
            raw = '\n'.join(raw.split('\n')[1:]).rsplit('```', 1)[0].strip()
        data = json.loads(raw)
        title        = data.get('title', '')
        category_raw = data.get('category_raw', '')
        tags         = data.get('tags', [])
        category = map_category(category_raw, title, tags)
        if not title:
            return None
        return {
            'platform': platform,
            'item_id':  item_id,
            'title':    title,
            'category_raw': category_raw,
            'category': category,
            'tags':     tags,
            'url':      '',
            'confidence': 80 if category else 55,   # lower conf — AI knowledge may be stale
            'source':   'deepseek_fallback',
        }
    except Exception:
        return None


# ── Main enrichment entry point ──────────────────────────────────────────────
_FETCHERS = {
    'videohive':     fetch_videohive,
    'motionelements': fetch_motionelements,
    'creativemarket': fetch_creativemarket,
    'envato':        fetch_envato,
    'graphicriver':  fetch_envato,   # same endpoint
    'designbundles': None,           # no public API; DeepSeek only
    'motionarray':   None,           # no public API; DeepSeek only
}

def enrich(folder_name: str) -> Optional[dict]:
    """Top-level: extract ID → cache check → fetch → cache save → return result.

    Returns a dict with keys: platform, item_id, title, category, tags, url,
    confidence.  Returns None if no ID found or all fetchers fail.
    """
    _load_cache()

    platform, item_id = extract_id(folder_name)
    if not platform:
        return None

    key = _cache_key(platform, item_id)
    if key in _cache:
        return _cache[key]

    result = None
    fetcher = _FETCHERS.get(platform)
    if fetcher:
        result = fetcher(item_id)

    if not result:
        result = fetch_via_deepseek(platform, item_id, folder_name)

    if result:
        _cache[key] = result
        _save_cache()

    return result


def enrich_batch(folder_names: list[str],
                 verbose: bool = False) -> dict[str, dict]:
    """Enrich a list of folder names. Returns {folder_name: result} for hits only."""
    _load_cache()
    results: dict[str, dict] = {}
    for name in folder_names:
        r = enrich(name)
        if r:
            results[name] = r
            if verbose:
                cat = r.get('category') or r.get('category_raw') or '?'
                print(f'  [{r["platform"]:14s}] {item_id_short(r):12s} conf={r["confidence"]:3d}'
                      f' -> {cat[:45]:45s}  {r["title"][:40]}')
    return results


def item_id_short(result: dict) -> str:
    return f'{result["platform"][:3].upper()}-{result["item_id"]}'


# ── CLI helpers ──────────────────────────────────────────────────────────────
def scan_index(index_path: str, verbose: bool = True):
    with open(index_path, 'r', encoding='utf-8') as f:
        items = json.load(f)

    names = [it['name'] for it in items if 'name' in it]
    print(f'Scanning {len(names)} items in {index_path} ...')

    hits = matched = missed = 0
    platform_counts: dict[str, int] = {}
    unmapped: list[dict] = []

    for name in names:
        platform, item_id = extract_id(name)
        if not platform:
            continue
        hits += 1
        platform_counts[platform] = platform_counts.get(platform, 0) + 1
        result = enrich(name)
        if result:
            matched += 1
            if not result.get('category'):
                unmapped.append({'name': name, **result})
        else:
            missed += 1
        if verbose:
            if result:
                cat = result.get('category') or '(no category mapped)'
                print(f'  [{result["platform"]:14s}] {item_id:12s} conf={result["confidence"]:3d}'
                      f' -> {cat[:45]:45s}  {result["title"][:40]}')
            else:
                print(f'  [{platform:14s}] {item_id:12s} FETCH FAILED')

    print(f'\nScan complete: {hits} IDs found, {matched} fetched, {missed} fetch-failed')
    print(f'Platform breakdown: {platform_counts}')
    if unmapped:
        print(f'Unmapped (ID found, no taxonomy match): {len(unmapped)} items')
        for u in unmapped[:20]:
            print(f'  {u["name"][:60]}  raw_cat={u.get("category_raw","?")[:40]}')


def scan_folder(root: str, verbose: bool = True):
    """Walk a folder tree and enrich all directories that have a marketplace ID."""
    root_path = Path(root)
    print(f'Scanning {root_path} ...')
    dirs = [d for d in root_path.iterdir() if d.is_dir()]
    names = [d.name for d in dirs]
    hits = enrich_batch(names, verbose=verbose)
    print(f'\n{len(hits)}/{len(names)} directories enriched from marketplace.')


def enrich_results_glob(pattern: str, min_improvement: int = 10,
                         dry_run: bool = False, verbose: bool = True) -> dict:
    """Post-process existing classification batch JSON files.

    For each result item, if the folder name has a marketplace ID and the
    marketplace lookup returns a category with confidence >= (AI confidence +
    min_improvement), overwrite the AI classification with the marketplace data.

    Args:
        pattern:         glob pattern for batch JSON files
                         (e.g. 'classification_results/loose_batch_*.json')
        min_improvement: minimum confidence gain to trigger an override (default 10)
        dry_run:         if True, report changes without writing files
        verbose:         print per-item changes

    Returns dict with keys: files_checked, items_checked, items_upgraded, items_skipped
    """
    import glob as _glob
    files     = sorted(_glob.glob(pattern))
    stats     = dict(files_checked=0, items_checked=0, items_upgraded=0, items_skipped=0)
    _load_cache()

    for fpath in files:
        stats['files_checked'] += 1
        try:
            with open(fpath, encoding='utf-8') as f:
                results = json.load(f)
        except Exception as e:
            print(f'  SKIP {fpath}: {e}')
            continue

        if not isinstance(results, list):
            continue

        changed = False
        for item in results:
            stats['items_checked'] += 1
            # Use _source_name (original disk name) for ID extraction when available
            raw_name = item.get('_source_name') or item.get('name') or ''
            if not raw_name:
                continue

            mkt = enrich(raw_name)
            if not mkt or not mkt.get('category'):
                stats['items_skipped'] += 1
                continue

            ai_conf   = item.get('confidence', 0)
            mkt_conf  = mkt.get('confidence', CONFIDENCE)
            ai_cat    = item.get('category', '')

            # Only upgrade if marketplace result is meaningfully better
            if mkt_conf >= ai_conf + min_improvement:
                if verbose:
                    print(f'  UPGRADE [{mkt["platform"]:12s}] {raw_name[:50]}')
                    print(f'    AI:  conf={ai_conf:3d} cat={ai_cat[:45]}')
                    print(f'    MKT: conf={mkt_conf:3d} cat={mkt["category"][:45]}  title={mkt["title"][:35]}')
                if not dry_run:
                    item['category']        = mkt['category']
                    item['clean_name']      = mkt['title']
                    item['confidence']      = mkt_conf
                    item['notes']           = (f'marketplace_enrich: {mkt["platform"]} '
                                               f'ID={mkt["item_id"]}; '
                                               f'prev_cat={ai_cat[:30]}; '
                                               f'prev_conf={ai_conf}')
                    item['_marketplace_id'] = f'{mkt["platform"]}:{mkt["item_id"]}'
                    changed = True
                stats['items_upgraded'] += 1
            else:
                stats['items_skipped'] += 1

        if changed and not dry_run:
            with open(fpath, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)

    print(f'\nEnrich-results summary:')
    print(f'  Files checked  : {stats["files_checked"]}')
    print(f'  Items checked  : {stats["items_checked"]}')
    print(f'  Items upgraded : {stats["items_upgraded"]}')
    print(f'  Items skipped  : {stats["items_skipped"]} (no ID or no improvement)')
    if dry_run:
        print('  (DRY RUN — no files written)')
    return stats


def show_stats():
    _load_cache()
    if not _cache:
        print('Cache is empty.')
        return
    by_platform: dict[str, int] = {}
    no_category = 0
    for k, v in _cache.items():
        plat = v.get('platform', k.split(':')[0])
        by_platform[plat] = by_platform.get(plat, 0) + 1
        if not v.get('category'):
            no_category += 1
    print(f'Cache entries: {len(_cache)}')
    for plat, cnt in sorted(by_platform.items(), key=lambda x: -x[1]):
        print(f'  {plat:20s} {cnt:5d}')
    print(f'Entries without taxonomy mapping: {no_category}')


def main():
    ap = argparse.ArgumentParser(description='Marketplace ID enrichment for FileOrganizer')
    ap.add_argument('--scan-index',   metavar='PATH',  help='Scan an index JSON (org_index.json etc.)')
    ap.add_argument('--scan-folder',  metavar='PATH',  help='Walk a folder and enrich directories')
    ap.add_argument('--lookup',       metavar='NAME',  help='Enrich a single folder name')
    ap.add_argument('--stats',        action='store_true', help='Show cache statistics')
    ap.add_argument('--enrich-results', metavar='GLOB',
                    help='Post-process batch JSON files matching GLOB; upgrade AI results with marketplace data')
    ap.add_argument('--min-improvement', type=int, default=10, metavar='N',
                    help='Minimum confidence gain to trigger an upgrade in --enrich-results (default: 10)')
    ap.add_argument('--dry-run', action='store_true',
                    help='With --enrich-results: report changes without writing files')
    ap.add_argument('--quiet', '-q',  action='store_true', help='Suppress per-item output')
    args = ap.parse_args()

    verbose = not args.quiet

    if args.lookup:
        result = enrich(args.lookup)
        if result:
            print(json.dumps(result, indent=2, ensure_ascii=False))
        else:
            platform, item_id = extract_id(args.lookup)
            if platform:
                print(f'ID found: {platform}:{item_id} — but fetch returned nothing.')
            else:
                print(f'No marketplace ID detected in: {args.lookup!r}')

    elif args.scan_index:
        scan_index(args.scan_index, verbose=verbose)

    elif args.scan_folder:
        scan_folder(args.scan_folder, verbose=verbose)

    elif args.stats:
        show_stats()

    elif args.enrich_results:
        enrich_results_glob(
            args.enrich_results,
            min_improvement=args.min_improvement,
            dry_run=args.dry_run,
            verbose=verbose,
        )

    elif args.export_unmapped:
        _load_cache()
        unmapped = [v for v in _cache.values() if not v.get('category')]
        out = Path(__file__).parent / 'unmapped_ids.json'
        out.write_text(json.dumps(unmapped, indent=2, ensure_ascii=False))
        print(f'Wrote {len(unmapped)} unmapped entries to {out}')

    else:
        ap.print_help()


if __name__ == '__main__':
    main()
