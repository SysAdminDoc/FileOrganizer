"""FileOrganizer — Marketplace catalog lookup via DeepSeek.

Given a folder/filename, DeepSeek identifies:
  - Clean display name (strip IDs, version tags, marketplace prefixes)
  - Category path  (e.g. "After Effects Templates/Transitions")
  - Marketplace source (Videohive, Envato Elements, Motion Array, etc.)
  - Asset type
  - Confidence

Results are cached in a SQLite DB to avoid repeated API calls.
"""
import os, re, json, sqlite3, hashlib, time, logging
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

from fileorganizer.config import _APP_DATA_DIR

_CATALOG_DB = os.path.join(_APP_DATA_DIR, 'catalog_cache.db')

# ── Database init ──────────────────────────────────────────────────────────────

def _init_catalog_db():
    con = sqlite3.connect(_CATALOG_DB)
    con.execute("""
        CREATE TABLE IF NOT EXISTS catalog_cache (
            key TEXT PRIMARY KEY,
            display_name TEXT,
            category TEXT,
            marketplace TEXT,
            asset_type TEXT,
            confidence INTEGER,
            raw_response TEXT,
            ts INTEGER
        )
    """)
    con.commit()
    con.close()

_init_catalog_db()


def _cache_key(name: str) -> str:
    """Stable cache key from a normalized name."""
    norm = re.sub(r'[\s_\-]+', ' ', name.strip().lower())
    return hashlib.md5(norm.encode()).hexdigest()


def _cache_get(name: str) -> Optional[dict]:
    try:
        con = sqlite3.connect(_CATALOG_DB)
        row = con.execute(
            "SELECT display_name, category, marketplace, asset_type, confidence "
            "FROM catalog_cache WHERE key = ?",
            (_cache_key(name),)
        ).fetchone()
        con.close()
        if row:
            return {
                'display_name': row[0], 'category': row[1],
                'marketplace': row[2], 'asset_type': row[3], 'confidence': row[4],
            }
    except Exception:
        pass
    return None


def _cache_put(name: str, result: dict, raw: str = ''):
    try:
        con = sqlite3.connect(_CATALOG_DB)
        con.execute(
            "INSERT OR REPLACE INTO catalog_cache "
            "(key, display_name, category, marketplace, asset_type, confidence, raw_response, ts) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                _cache_key(name),
                result.get('display_name', ''),
                result.get('category', ''),
                result.get('marketplace', 'Unknown'),
                result.get('asset_type', 'Other'),
                int(result.get('confidence', 0)),
                raw,
                int(time.time()),
            )
        )
        con.commit()
        con.close()
    except Exception as e:
        log.warning("catalog cache write error: %s", e)


# ── Marketplace detection (heuristic pre-filter) ───────────────────────────────

_MARKETPLACE_PREFIXES = {
    'videohive': 'Videohive',
    'envato': 'Envato Elements',
    'motionarray': 'Motion Array',
    'motion-array': 'Motion Array',
    'creativemarket': 'Creative Market',
    'creative-market': 'Creative Market',
    'freepik': 'Freepik',
    'shutterstock': 'Shutterstock',
    'adobestock': 'Adobe Stock',
    'adobe-stock': 'Adobe Stock',
    'filtergrade': 'FilterGrade',
    'storyblocks': 'Storyblocks',
    'pond5': 'Pond5',
    'graphicriver': 'GraphicRiver',
    'audiojungle': 'AudioJungle',
    'elements': 'Envato Elements',
}

_ID_PATTERNS = [
    re.compile(r'\b\d{6,10}\b'),        # bare numeric IDs (Videohive item IDs)
    re.compile(r'[-_]v\d+(\.\d+)?$'),   # version suffix: -v1, _v2.1
    re.compile(r'\s+\d+$'),             # trailing number
]

# Design file extensions mapped to asset type
_EXT_ASSET_TYPE = {
    '.aep':    'AEP',
    '.aepx':   'AEP',
    '.prproj': 'Premiere',
    '.psd':    'PSD',
    '.psb':    'PSD',
    '.ai':     'Illustrator',
    '.indd':   'InDesign',
    '.idml':   'InDesign',
    '.xd':     'XD',
    '.fig':    'Figma',
    '.mogrt':  'Motion Graphics',
    '.wav':    'Audio',
    '.mp3':    'Audio',
    '.aiff':   'Audio',
    '.flac':   'Audio',
    '.ogg':    'Audio',
    '.mid':    'Audio',
    '.midi':   'Audio',
    '.mp4':    'Video',
    '.mov':    'Video',
    '.mxf':    'Video',
    '.r3d':    'Video',
    '.ttf':    'Font',
    '.otf':    'Font',
    '.woff':   'Font',
    '.woff2':  'Font',
    '.lut':    'LUT',
    '.cube':   'LUT',
}


def detect_asset_type(path: str) -> str:
    ext = Path(path).suffix.lower()
    return _EXT_ASSET_TYPE.get(ext, 'Other')


def detect_marketplace_heuristic(name: str) -> str:
    """Quick local detection of marketplace from name prefix."""
    norm = name.lower().replace('-', '').replace('_', '').replace(' ', '')
    for prefix, marketplace in _MARKETPLACE_PREFIXES.items():
        if norm.startswith(prefix.replace('-', '').replace('_', '')):
            return marketplace
    return ''


def strip_marketplace_noise(name: str) -> str:
    """Remove common marketplace prefixes, IDs, and version tags from a name."""
    result = name
    # Remove marketplace prefix: "videohive-" or "videohive_"
    for prefix in sorted(_MARKETPLACE_PREFIXES.keys(), key=len, reverse=True):
        pat = re.compile(r'^' + re.escape(prefix) + r'[-_\s]?', re.IGNORECASE)
        result = pat.sub('', result)

    # Remove leading numeric IDs
    result = re.sub(r'^\d{6,10}[-_\s]?', '', result)
    # Remove trailing IDs
    result = re.sub(r'[-_\s]\d{6,10}$', '', result)
    # Remove version suffix
    result = re.sub(r'[-_\s]v\d+(\.\d+)?$', '', result, flags=re.IGNORECASE)
    # Normalize separators to spaces
    result = re.sub(r'[-_]+', ' ', result).strip()
    # Title case
    if result and result == result.lower():
        result = result.title()
    return result or name


# ── Category inference map (local first-pass before AI) ───────────────────────

_ASSET_TYPE_CATEGORIES = {
    'AEP': 'After Effects Templates',
    'Premiere': 'Premiere Pro Templates',
    'PSD': 'Photoshop Templates',
    'Illustrator': 'Illustrator Templates',
    'InDesign': 'InDesign Templates',
    'Motion Graphics': 'Motion Graphics Templates',
    'Audio': 'Audio',
    'Video': 'Stock Video',
    'Font': 'Fonts',
    'LUT': 'LUTs & Color Grading',
    'XD': 'UI Kits',
    'Figma': 'UI Kits',
}


def infer_category_from_name(name: str, asset_type: str) -> str:
    """Quick local category suggestion before hitting the AI."""
    base = _ASSET_TYPE_CATEGORIES.get(asset_type, 'Design Assets')
    # Subcategory hints from name
    norm = name.lower()
    if any(x in norm for x in ['transition', 'wipe', 'slide']):
        return f"{base}/Transitions"
    if any(x in norm for x in ['intro', 'opener', 'opening']):
        return f"{base}/Intros & Openers"
    if any(x in norm for x in ['logo', 'reveal', 'sting']):
        return f"{base}/Logo Reveals"
    if any(x in norm for x in ['title', 'text', 'typography', 'typeface']):
        return f"{base}/Titles & Typography"
    if any(x in norm for x in ['lower third', 'lowerthird', 'lower_third']):
        return f"{base}/Lower Thirds"
    if any(x in norm for x in ['wedding', 'bride', 'marriage']):
        return f"{base}/Wedding"
    if any(x in norm for x in ['corporate', 'business', 'company', 'office']):
        return f"{base}/Corporate"
    if any(x in norm for x in ['social', 'instagram', 'facebook', 'tiktok', 'youtube']):
        return f"{base}/Social Media"
    if any(x in norm for x in ['promo', 'promotion', 'advertisement', 'commercial']):
        return f"{base}/Promotional"
    if any(x in norm for x in ['slideshow', 'slide show', 'photo slide']):
        return f"{base}/Slideshows"
    if any(x in norm for x in ['particle', 'smoke', 'fire', 'explosion']):
        return f"{base}/Visual Effects"
    if any(x in norm for x in ['countdown', 'count down', 'timer']):
        return f"{base}/Countdowns"
    if any(x in norm for x in ['overlay', 'frame', 'border']):
        return f"{base}/Overlays & Frames"
    if any(x in norm for x in ['mockup', 'mock-up', 'mock up']):
        return f"{base}/Mockups"
    if any(x in norm for x in ['flyer', 'poster', 'banner']):
        return f"{base}/Print Templates"
    if any(x in norm for x in ['icon', 'icons', 'pictogram']):
        return f"{base}/Icons"
    if any(x in norm for x in ['pattern', 'texture', 'background']):
        return f"{base}/Backgrounds & Textures"
    return base


# ── Community fingerprint DB lookup ───────────────────────────────────────────

def lookup_by_fingerprint(folder_path: str) -> dict | None:
    """
    Query the community asset fingerprint database for an exact or near-exact
    match by file hash.  Returns a result dict with 'source': 'fingerprint_db'
    if found, otherwise None.

    This runs before any AI call — a fingerprint match needs no network round-trip
    and is more reliable than name-based heuristics.

    Requires asset_fingerprints.db to exist (built with asset_db.py --build).
    """
    try:
        import importlib.util, os
        # Locate asset_db.py relative to this package (one level up)
        db_mod_path = os.path.join(os.path.dirname(__file__), '..', 'asset_db.py')
        db_file     = os.path.join(os.path.dirname(__file__), '..', 'asset_fingerprints.db')
        if not os.path.exists(db_file) or not os.path.exists(db_mod_path):
            return None
        spec = importlib.util.spec_from_file_location('asset_db', db_mod_path)
        asset_db = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(asset_db)
        hit = asset_db.lookup_folder(folder_path, db_file)
        if not hit or hit.get('match_type') == 'none':
            return None
        return {
            'display_name': hit['clean_name'],
            'category':     hit['category'],
            'marketplace':  hit['marketplace'] or 'Unknown',
            'asset_type':   'Other',
            'confidence':   hit['confidence'],
            'match_type':   hit['match_type'],
            'source':       'fingerprint_db',
        }
    except Exception as e:
        log.debug("fingerprint DB lookup error: %s", e)
        return None


# ── Single-item lookup ─────────────────────────────────────────────────────────

def lookup_single(name: str, path: str = '', provider=None) -> dict:
    """
    Identify a single design asset by name.
    Returns: {display_name, category, marketplace, asset_type, confidence, source}
    source: 'fingerprint_db' | 'cache' | 'heuristic' | 'ai'
    """
    # Try community fingerprint DB first (folder_path match, strongest signal)
    if path and os.path.isdir(path):
        fp_result = lookup_by_fingerprint(path)
        if fp_result and fp_result['confidence'] >= 75:
            return fp_result

    # Try cache first
    cached = _cache_get(name)
    if cached:
        cached['source'] = 'cache'
        return cached

    asset_type = detect_asset_type(path) if path else 'Other'
    marketplace = detect_marketplace_heuristic(name)
    display_name = strip_marketplace_noise(name)
    category = infer_category_from_name(display_name, asset_type)

    # If no provider, return heuristic result
    if provider is None or not provider.is_available():
        result = {
            'display_name': display_name,
            'category': category,
            'marketplace': marketplace or 'Unknown',
            'asset_type': asset_type,
            'confidence': 45,
            'source': 'heuristic',
        }
        _cache_put(name, result)
        return result

    # Use AI for richer lookup
    from fileorganizer.providers import SYSTEM_CATALOG, parse_json_response, build_catalog_prompt
    prompt = build_catalog_prompt([name])
    raw = provider.classify(prompt, system=SYSTEM_CATALOG, task_type='catalog',
                             max_tokens=512) if hasattr(provider, 'classify') else None

    if raw:
        items = parse_json_response(raw)
        if items and isinstance(items, list) and items:
            ai = items[0]
            result = {
                'display_name': ai.get('display_name', display_name) or display_name,
                'category': ai.get('category', category) or category,
                'marketplace': ai.get('marketplace', marketplace or 'Unknown'),
                'asset_type': ai.get('asset_type', asset_type),
                'confidence': int(ai.get('confidence', 70)),
                'source': 'ai',
            }
            _cache_put(name, result, raw)
            return result

    # AI returned nothing useful — use heuristic
    result = {
        'display_name': display_name,
        'category': category,
        'marketplace': marketplace or 'Unknown',
        'asset_type': asset_type,
        'confidence': 45,
        'source': 'heuristic',
    }
    _cache_put(name, result)
    return result


# ── Batch lookup ───────────────────────────────────────────────────────────────

def lookup_batch(items: list, provider=None, batch_size: int = 20,
                 progress_cb=None) -> list:
    """
    Batch catalog lookup for a list of (name, path) tuples or FileItem-like objects.
    Returns list of result dicts in same order as input.

    progress_cb(done, total): optional progress callback
    """
    from fileorganizer.providers import SYSTEM_CATALOG, parse_json_response, build_catalog_prompt

    results = []
    total = len(items)

    # Normalize input to (name, path) tuples
    pairs = []
    for item in items:
        if isinstance(item, tuple):
            pairs.append(item)
        else:
            name = getattr(item, 'folder_name', None) or getattr(item, 'name', str(item))
            path = getattr(item, 'full_source_path', None) or getattr(item, 'full_src', '')
            pairs.append((name, path))

    # Check fingerprint DB first (strongest signal, no API cost),
    # then cache, collect still-uncached for AI
    uncached_idx = []
    pre_results = {}
    for i, (name, path) in enumerate(pairs):
        # Fingerprint DB — hits are high-confidence, skip AI for them
        if path and os.path.isdir(path):
            fp_result = lookup_by_fingerprint(path)
            if fp_result and fp_result['confidence'] >= 75:
                pre_results[i] = fp_result
                continue
        cached = _cache_get(name)
        if cached:
            cached['source'] = 'cache'
            pre_results[i] = cached
        else:
            uncached_idx.append(i)

    if progress_cb:
        progress_cb(len(pre_results), total)

    # Batch process uncached items via AI
    if uncached_idx and provider and provider.is_available():
        for chunk_start in range(0, len(uncached_idx), batch_size):
            chunk = uncached_idx[chunk_start:chunk_start + batch_size]
            names = [pairs[i][0] for i in chunk]
            prompt = build_catalog_prompt(names)

            raw = None
            if hasattr(provider, 'classify'):
                # ProviderRouter
                raw = provider.classify(prompt, system=SYSTEM_CATALOG,
                                        task_type='catalog', max_tokens=4096)
            elif hasattr(provider, 'classify_batch'):
                raw = provider.classify_batch(names, system=SYSTEM_CATALOG, max_tokens=4096)

            ai_items = parse_json_response(raw) if raw else None

            for j, idx in enumerate(chunk):
                name, path = pairs[idx]
                ai = (ai_items[j] if ai_items and j < len(ai_items) else None)
                asset_type = detect_asset_type(path) if path else 'Other'
                marketplace = detect_marketplace_heuristic(name)
                display_name = strip_marketplace_noise(name)
                category = infer_category_from_name(display_name, asset_type)

                if ai:
                    result = {
                        'display_name': ai.get('display_name', display_name) or display_name,
                        'category': ai.get('category', category) or category,
                        'marketplace': ai.get('marketplace', marketplace or 'Unknown'),
                        'asset_type': ai.get('asset_type', asset_type),
                        'confidence': int(ai.get('confidence', 70)),
                        'source': 'ai',
                    }
                else:
                    result = {
                        'display_name': display_name,
                        'category': category,
                        'marketplace': marketplace or 'Unknown',
                        'asset_type': asset_type,
                        'confidence': 45,
                        'source': 'heuristic',
                    }
                _cache_put(name, result, raw or '')
                pre_results[idx] = result

            if progress_cb:
                progress_cb(len(pre_results), total)

    # Fill in any remaining uncached items with heuristic
    for i, (name, path) in enumerate(pairs):
        if i not in pre_results:
            asset_type = detect_asset_type(path) if path else 'Other'
            marketplace = detect_marketplace_heuristic(name)
            display_name = strip_marketplace_noise(name)
            category = infer_category_from_name(display_name, asset_type)
            result = {
                'display_name': display_name,
                'category': category,
                'marketplace': marketplace or 'Unknown',
                'asset_type': asset_type,
                'confidence': 30,
                'source': 'heuristic',
            }
            _cache_put(name, result)
            pre_results[i] = result

    return [pre_results[i] for i in range(total)]


# ── Cache management ───────────────────────────────────────────────────────────

def catalog_cache_count() -> int:
    try:
        con = sqlite3.connect(_CATALOG_DB)
        n = con.execute("SELECT COUNT(*) FROM catalog_cache").fetchone()[0]
        con.close()
        return n
    except Exception:
        return 0


def catalog_cache_clear():
    try:
        con = sqlite3.connect(_CATALOG_DB)
        con.execute("DELETE FROM catalog_cache")
        con.commit()
        con.close()
    except Exception:
        pass
