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
    CreativeMarket: https://creativemarket.com/product/{id}            (page metadata)
    Freepik:        https://api.freepik.com/v1/resources/{id}           (FREEPIK_API_KEY)
    Motion Array / FilterGrade / Shutterstock / Adobe Stock             (page metadata)
    Fallback:      DeepSeek AI lookup (reads deepseek_key.txt or DEEPSEEK_API_KEY env var)

Cache:
    marketplace_cache.json — keyed by "{platform}:{item_id}", persistent across runs
"""

import argparse, html as html_lib, json, os, re, sys, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

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
UPDATE_CHECK_INTERVAL = 7 * 24 * 60 * 60
UPDATE_CHECK_MAX_ITEMS = 40

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
    # Expanded provider labels
    ('after effects',                              'After Effects - Other'),
    ('premiere pro',                               'Premiere Pro - Other'),
    ('photoshop',                                  'Photoshop - Other'),
    ('lightroom',                                  'Lightroom Presets'),
    ('illustration',                               'Illustrator - Vector Graphics'),
    ('vector',                                     'Illustrator - Vector Graphics'),
    ('graphic resources',                          'UI Resources'),
    ('video',                                      'Stock Footage - General'),
    ('footage',                                    'Stock Footage - General'),
    ('sound effect',                               'Sound Effects & SFX'),
    ('audio',                                      'Stock Music & Audio'),
    ('filter',                                     'Lightroom Presets'),
    ('preset',                                     'After Effects - Preset Pack'),
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
    # Direct provider URLs are accepted by --lookup and retained as the ID
    # payload so the page fetchers can request the exact slugged page.
    (re.compile(r'https?://(?:www\.)?freepik\.com/(.+?)(?:[?#]|$)', re.IGNORECASE), 'freepik'),
    (re.compile(r'https?://(?:www\.)?motionarray\.com/(.+?)(?:[?#]|$)', re.IGNORECASE), 'motionarray'),
    (re.compile(r'https?://(?:www\.)?filtergrade\.com/(product/.+?)(?:[?#]|$)', re.IGNORECASE), 'filtergrade'),
    (re.compile(r'https?://(?:www\.)?shutterstock\.com/(.+?)(?:[?#]|$)', re.IGNORECASE), 'shutterstock'),
    (re.compile(r'https?://stock\.adobe\.com/(.+?)(?:[?#]|$)', re.IGNORECASE), 'adobe_stock'),
    (re.compile(r'https?://(?:www\.)?creativemarket\.com/(.+?)(?:[?#]|$)', re.IGNORECASE), 'creativemarket'),
    # Explicit provider prefixes used by exported/downloaded folder names.
    (re.compile(r'^(?:freepik|fp)[-_](\d{5,12})(?:\D|$)', re.IGNORECASE), 'freepik'),
    (re.compile(r'^(?:filtergrade|fg)[-_](\d{5,12})(?:\D|$)', re.IGNORECASE), 'filtergrade'),
    (re.compile(r'^(?:shutterstock|ss)[-_](\d{6,12})(?:\D|$)', re.IGNORECASE), 'shutterstock'),
    (re.compile(r'^(?:adobe[-_ ]?stock|stock[-_ ]?adobe|as)[-_](\d{6,12})(?:\D|$)', re.IGNORECASE), 'adobe_stock'),
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
    else:
        _cache = {}

def _save_cache():
    CACHE_FILE.write_text(json.dumps(_cache, ensure_ascii=False, indent=2), 'utf-8')

def _cache_key(platform: str, item_id: str) -> str:
    return f'{platform}:{item_id}'


# ── HTTP helpers ──────────────────────────────────────────────────────────────
_last_request_at: dict[str, float] = {}

def _throttled_get(
    url: str,
    domain: str,
    extra_headers: dict[str, str] | None = None,
) -> Optional[requests.Response]:
    """GET with per-domain rate limiting and retry on 429/5xx."""
    wait = RATE_LIMIT_WAIT - (time.time() - _last_request_at.get(domain, 0))
    if wait > 0:
        time.sleep(wait)
    headers = dict(REQUEST_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    for attempt in range(FETCH_RETRY + 1):
        try:
            resp = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT,
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


def _meta(html: str, key: str) -> list[str]:
    """Extract HTML meta values regardless of property/name attribute order."""
    values = []
    pattern = re.compile(
        rf'<meta[^>]+(?:property|name)=["\']{re.escape(key)}["\'][^>]+content=["\']([^"\']*)["\']'
        rf'|<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:property|name)=["\']{re.escape(key)}["\']',
        re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        value = next((group for group in match.groups() if group is not None), '').strip()
        if value:
            values.append(html_lib.unescape(value))
    return values


def _json_ld_objects(html: str) -> list[dict]:
    """Return product/article JSON-LD objects embedded in a marketplace page."""
    objects = []
    for raw in re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        try:
            payload = json.loads(html_lib.unescape(raw).strip())
        except (TypeError, ValueError):
            continue
        values = payload if isinstance(payload, list) else [payload]
        for value in values:
            if not isinstance(value, dict):
                continue
            graph = value.get('@graph')
            if isinstance(graph, list):
                values.extend(graph)
            else:
                objects.append(value)
    return objects


def _as_tags(value) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in re.split(r'[,;|]', value) if part.strip()]
    if isinstance(value, list):
        tags = []
        for item in value:
            if isinstance(item, dict):
                item = item.get('name') or item.get('label') or ''
            if item:
                tags.append(str(item).strip())
        return [tag for tag in tags if tag]
    return []


def _page_fields(page_html: str) -> tuple[str, str, list[str], str, str]:
    """Extract title, category, tags, and update markers from page metadata."""
    objects = _json_ld_objects(page_html)
    title = _og(page_html, 'title') or ''
    category_raw = ''
    updated_at = ''
    version = ''
    tags = []
    for meta_key in ('keywords', 'article:tag'):
        for value in _meta(page_html, meta_key):
            tags.extend(_as_tags(value))
    for obj in objects:
        title = title or str(obj.get('name') or obj.get('headline') or '').strip()
        category_raw = category_raw or str(
            obj.get('category') or obj.get('genre') or ''
        ).strip()
        updated_at = updated_at or str(
            obj.get('dateModified') or obj.get('datePublished') or ''
        ).strip()
        version = version or str(obj.get('version') or '').strip()
        tags.extend(_as_tags(obj.get('keywords')))
    title = html_lib.unescape(title).strip()
    if not category_raw:
        category_raw = (_meta(page_html, 'article:section') or [''])[0]
    updated_at = updated_at or (
        _meta(page_html, 'article:modified_time')
        or _meta(page_html, 'og:updated_time')
        or ['']
    )[0]
    version = version or (_meta(page_html, 'version') or [''])[0]
    if not tags:
        tags = _as_tags(_meta(page_html, 'description'))
    return title, category_raw, list(dict.fromkeys(tags))[:40], updated_at, version


def _page_result(
    platform: str,
    item_id: str,
    response: requests.Response,
    fallback_url: str,
) -> Optional[dict]:
    title, category_raw, tags, updated_at, version = _page_fields(response.text)
    title = re.sub(r'\s*[-|–]\s*(?:Freepik|Motion Array|FilterGrade|Shutterstock|Adobe Stock).*$', '', title, flags=re.IGNORECASE).strip()
    if not title:
        return None
    category = map_category(category_raw, title, tags)
    result = {
        'platform': platform,
        'item_id': item_id,
        'title': title,
        'category_raw': category_raw,
        'category': category,
        'tags': tags,
        'url': getattr(response, 'url', '') or fallback_url,
        'confidence': CONFIDENCE if category else 70,
        'source': 'marketplace_page',
    }
    if updated_at:
        result['updated_at'] = updated_at
    if version:
        result['version'] = version
    return result


def _api_result(
    platform: str,
    item_id: str,
    data: dict,
    fallback_url: str,
) -> Optional[dict]:
    payload = data.get('data', data) if isinstance(data, dict) else {}
    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        return None
    title = str(payload.get('title') or payload.get('name') or '').strip()
    category_raw = str(
        payload.get('category') or payload.get('type') or payload.get('content_type') or ''
    ).strip()
    if isinstance(payload.get('category'), dict):
        category_raw = str(payload['category'].get('name') or category_raw)
    tags = _as_tags(payload.get('tags') or payload.get('keywords'))
    updated_at = str(
        payload.get('updated_at') or payload.get('date_modified')
        or payload.get('dateModified') or payload.get('published_at') or ''
    ).strip()
    version = str(payload.get('version') or '').strip()
    if not title:
        return None
    category = map_category(category_raw, title, tags)
    result = {
        'platform': platform,
        'item_id': item_id,
        'title': title,
        'category_raw': category_raw,
        'category': category,
        'tags': tags,
        'url': str(payload.get('url') or fallback_url),
        'confidence': CONFIDENCE if category else 70,
        'source': 'marketplace_api',
    }
    if updated_at:
        result['updated_at'] = updated_at
    if version:
        result['version'] = version
    return result


# ── Marketplace fetchers ──────────────────────────────────────────────────────
def _provider_page_url(item_id: str, domain: str, default_path: str) -> str:
    """Build a provider page URL from either a captured URL path or an ID."""
    if item_id.startswith(('http://', 'https://')):
        return item_id
    if '/' in item_id:
        return f'https://{domain}/{item_id.lstrip("/")}'
    return f'https://{domain}/{default_path.format(item_id=quote(item_id, safe="-_."))}'


def fetch_freepik(item_id: str) -> Optional[dict]:
    """Use Freepik's authenticated resource endpoint, then its public page."""
    api_key = os.environ.get('FREEPIK_API_KEY', '').strip()
    if api_key and item_id.isdigit():
        api_url = f'https://api.freepik.com/v1/resources/{item_id}'
        response = _throttled_get(
            api_url,
            'api.freepik.com',
            {'x-freepik-api-key': api_key, 'Accept': 'application/json'},
        )
        if response and response.status_code == 200:
            try:
                result = _api_result('freepik', item_id, response.json(), api_url)
            except (TypeError, ValueError):
                result = None
            if result:
                return result

    if '/' not in item_id:
        return None
    url = _provider_page_url(item_id, 'www.freepik.com', '{item_id}')
    response = _throttled_get(url, 'www.freepik.com')
    if not response or response.status_code != 200:
        return None
    return _page_result('freepik', item_id, response, url)


def fetch_motionarray(item_id: str) -> Optional[dict]:
    """Scrape a Motion Array product page when a slug or direct URL is known."""
    url = _provider_page_url(item_id, 'motionarray.com', 'browse/{item_id}')
    response = _throttled_get(url, 'motionarray.com')
    if not response or response.status_code != 200:
        return None
    return _page_result('motionarray', item_id, response, url)


def fetch_filtergrade(item_id: str) -> Optional[dict]:
    """Scrape a FilterGrade product page; no public API key is required."""
    url = _provider_page_url(item_id, 'filtergrade.com', 'product/{item_id}')
    response = _throttled_get(url, 'filtergrade.com')
    if not response or response.status_code != 200:
        return None
    return _page_result('filtergrade', item_id, response, url)


def fetch_shutterstock(item_id: str) -> Optional[dict]:
    """Scrape a Shutterstock asset page; the optional API is not required."""
    url = _provider_page_url(item_id, 'www.shutterstock.com', 'image-photo/{item_id}')
    response = _throttled_get(url, 'www.shutterstock.com')
    if not response or response.status_code != 200:
        return None
    return _page_result('shutterstock', item_id, response, url)


def fetch_adobe_stock(item_id: str) -> Optional[dict]:
    """Scrape a public Adobe Stock asset page without attempting licensing."""
    url = _provider_page_url(item_id, 'stock.adobe.com', 'images/{item_id}')
    response = _throttled_get(url, 'stock.adobe.com')
    if not response or response.status_code != 200:
        return None
    return _page_result('adobe_stock', item_id, response, url)


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
    url = _provider_page_url(item_id, 'creativemarket.com', 'product/{item_id}')
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
    'freepik':       fetch_freepik,
    'motionarray':   fetch_motionarray,
    'filtergrade':   fetch_filtergrade,
    'shutterstock':  fetch_shutterstock,
    'adobe_stock':   fetch_adobe_stock,
    'envato':        fetch_envato,
    'graphicriver':  fetch_envato,   # same endpoint
    'designbundles': None,           # no public API; DeepSeek only
}


def _marker_timestamp(value) -> float | None:
    """Convert a provider date marker or epoch value into UTC seconds."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value or '').strip()
    if not text:
        return None
    if re.fullmatch(r'\d+(?:\.\d+)?', text):
        return float(text)
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _version_tuple(value) -> tuple[int, ...] | None:
    parts = re.findall(r'\d+', str(value or ''))
    return tuple(int(part) for part in parts) if parts else None


def _is_newer_marketplace_result(previous: dict, current: dict) -> bool:
    """Compare only explicit provider version/date markers; never guess from titles."""
    previous_version = _version_tuple(previous.get('version'))
    current_version = _version_tuple(current.get('version'))
    if previous_version and current_version and previous_version != current_version:
        return current_version > previous_version

    previous_date = _marker_timestamp(previous.get('updated_at'))
    current_date = _marker_timestamp(current.get('updated_at'))
    return bool(
        previous_date is not None
        and current_date is not None
        and current_date > previous_date
    )


def _update_record(name: str, previous: dict, current: dict) -> dict:
    return {
        'name': name,
        'platform': current.get('platform') or previous.get('platform', ''),
        'item_id': current.get('item_id') or previous.get('item_id', ''),
        'title': current.get('title') or previous.get('title', ''),
        'category': current.get('category') or previous.get('category') or 'Marketplace',
        'previous_version': previous.get('previous_version') or previous.get('version', ''),
        'current_version': current.get('version') or current.get('current_version', ''),
        'previous_updated_at': previous.get('previous_updated_at') or previous.get('updated_at', ''),
        'current_updated_at': current.get('updated_at') or current.get('current_updated_at', ''),
    }


def check_for_updates(
    folder_names,
    *,
    force: bool = False,
    now: float | None = None,
    max_items: int = UPDATE_CHECK_MAX_ITEMS,
) -> dict:
    """Refresh a bounded set of known marketplace IDs and return update alerts.

    A first lookup establishes a baseline.  Alerts require an explicit provider
    version or modification date that is newer than the cached marker.  Checks
    are throttled per cache entry so a scan does not repeatedly hit marketplace
    pages.
    """
    _load_cache()
    current_time = float(time.time() if now is None else now)
    summary = {'checked': 0, 'skipped': 0, 'updates': []}
    seen = set()
    changed = False

    for name in folder_names or []:
        raw_name = str(name or '').strip()
        platform, item_id = extract_id(raw_name)
        if not platform or not item_id:
            continue
        key = _cache_key(platform, item_id)
        if key in seen:
            continue
        seen.add(key)
        fetcher = _FETCHERS.get(platform)
        if not fetcher or len(seen) > max(1, int(max_items)):
            continue

        previous = _cache.get(key)
        last_checked = _marker_timestamp(
            previous.get('last_update_check_at') if previous else None
        )
        if (
            not force
            and last_checked is not None
            and current_time - last_checked < UPDATE_CHECK_INTERVAL
        ):
            summary['skipped'] += 1
            if previous and previous.get('update_available'):
                summary['updates'].append(_update_record(raw_name, previous, previous))
            continue

        summary['checked'] += 1
        try:
            fresh = fetcher(item_id)
        except Exception:
            fresh = None
        if fresh:
            fresh = dict(fresh)
            fresh['last_update_check_at'] = int(current_time)
            if previous and _is_newer_marketplace_result(previous, fresh):
                fresh['update_available'] = True
                fresh['previous_version'] = previous.get('version', '')
                fresh['previous_updated_at'] = previous.get('updated_at', '')
                summary['updates'].append(_update_record(raw_name, previous, fresh))
            elif previous and previous.get('update_available'):
                # Keep an alert visible until a later UI action acknowledges it.
                fresh['update_available'] = True
                fresh['previous_version'] = previous.get('previous_version', '')
                fresh['previous_updated_at'] = previous.get('previous_updated_at', '')
                summary['updates'].append(_update_record(raw_name, previous, fresh))
            _cache[key] = fresh
            changed = True
        elif previous:
            previous = dict(previous)
            previous['last_update_check_at'] = int(current_time)
            _cache[key] = previous
            changed = True
            if previous.get('update_available'):
                summary['updates'].append(_update_record(raw_name, previous, previous))

    if changed:
        _save_cache()
    return summary

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
