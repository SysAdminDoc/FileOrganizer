#!/usr/bin/env python3
r"""
classify_design.py — Batch classifier for design asset directories.

Reads an index JSON, peeks at file extensions inside each dir,
then sends batches of 60 to DeepSeek for classification into G:\Organized categories.

Usage:
    python classify_design.py --preview                      # show batches
    python classify_design.py --run                          # classify all pending batches
    python classify_design.py --run --parallel               # bounded concurrent requests
    python classify_design.py --run --batch 5                # classify only batch 5
    python classify_design.py --stats                        # show progress
    python classify_design.py --show-cats                    # print full category taxonomy
    python classify_design.py --source design_org --run      # classify G:\Design Organized
    python classify_design.py --source loose_files --run     # classify root loose files

Results saved to classification_results/<prefix>NNN.json
"""
import os, sys, json, re, argparse, tempfile
from pathlib import Path
from datetime import datetime
from typing import Callable

from fileorganizer.adaptive_corrector import (
    AdaptiveCorrector,
    build_adaptive_batch_system_prompt,
)
from fileorganizer.classification_provenance import record_classification

# Stage 0: fingerprint DB lookup (for NEXT-15)
try:
    from asset_db import lookup_folder
except ImportError:
    def lookup_folder(*args, **kwargs):  # type: ignore[no-redef]
        """Graceful fallback if asset_db unavailable."""
        return None

# LLM caching (NEXT-44)
try:
    from llm_cache import lookup_cached, store_cached, cleanup_expired
except ImportError:
    def lookup_cached(*args, **kwargs):  # type: ignore[no-redef]
        """Graceful fallback if llm_cache unavailable."""
        return None
    def store_cached(*args, **kwargs):  # type: ignore[no-redef]
        return False
    def cleanup_expired(*args, **kwargs):  # type: ignore[no-redef]
        return 0

# ── Source configs ────────────────────────────────────────────────────────────
SOURCE_CONFIGS = {
    'design_unorg': {
        'index_file':   'design_unorg_index.json',
        'batch_prefix': 'design_batch_',
        'source_dir':   r'G:\Design Unorganized',
        'has_legacy':   False,
        'file_mode':    False,
    },
    'design_org': {
        'index_file':   'design_org_index.json',
        'batch_prefix': 'design_org_batch_',
        'source_dir':   r'G:\Design Organized',
        'has_legacy':   True,
        'file_mode':    False,
    },
    'loose_files': {
        'index_file':   'loose_files_index.json',
        'batch_prefix': 'loose_batch_',
        'source_dir':   r'G:\Design Unorganized',
        'has_legacy':   False,
        'file_mode':    True,
    },
    'design_elements': {
        'index_file':   'design_elements_index.json',
        'batch_prefix': 'de_batch_',
        'source_dir':   r'G:\Design Organized\Design Elements',
        'has_legacy':   True,   # legacy_category = subfolder name
        'file_mode':    False,  # move whole directories
    },
    'i_organized_legacy': {
        'index_file':   'i_organized_legacy_index.json',
        'batch_prefix': 'i_org_batch_',
        'source_dir':   r'I:\Organized',
        'has_legacy':   True,   # legacy_category = first-level category dir name
        'file_mode':    False,
    },
}

# ── Config (defaults; overridden at parse time) ───────────────────────────────
BATCH_SIZE   = 60
RESULTS_DIR  = Path(__file__).parent / 'classification_results'
RESULTS_DIR.mkdir(exist_ok=True)

# These are set dynamically in main() based on --source; defaults = design_unorg
INDEX_FILE   = Path(__file__).parent / 'design_unorg_index.json'
BATCH_PREFIX = 'design_batch_'
SOURCE_DIR   = SOURCE_CONFIGS['design_unorg']['source_dir']
FILE_MODE    = False

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_BASE    = 'https://api.deepseek.com'
DEEPSEEK_MODEL   = 'deepseek-v4-flash'

# Stage 1 deliberately uses a small, stable vocabulary.  It is an evidence
# gate for the category prompt, not a second copy of the destination taxonomy.
FILE_TYPE_LABELS = (
    'After Effects',
    'Premiere Pro',
    'Photoshop',
    'Illustrator',
    'Procreate',
    'Lightroom',
    'Print / Document',
    'Motion Graphics / Video',
    'Audio / Sound',
    '3D',
    'Fonts / Typography',
    'Web / UI',
    'Plugin / Extension',
    'Stock Media',
    'Tutorial / Education',
    'Multi-tool Bundle',
    'Other',
    'Unknown',
)
FILE_TYPE_SET = frozenset(FILE_TYPE_LABELS)
FILE_TYPE_CACHE_MODEL_SUFFIX = ':file-type-v1'

# ── Full category taxonomy for G:\Organized ───────────────────────────────────
# These match the categories already in G:\Organized plus expansions needed
# for the broader content types in G:\Design Unorganized.
CATEGORIES = [
    # ── After Effects ─────────────────────────────────────────────────────────
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
    "After Effects - Map & Location",
    "After Effects - Mockup & Device",
    "After Effects - Motion Graphics Pack",
    "After Effects - Music & Audio Visualizer",
    "After Effects - News & Broadcast",
    "After Effects - Photo Album & Gallery",
    "After Effects - Plugin & Script",
    "After Effects - Preset Pack",
    "After Effects - Product Promo",
    "After Effects - Real Estate",
    "After Effects - Slideshow",
    "After Effects - Social Media",
    "After Effects - Sport & Action",
    "After Effects - Title & Typography",
    "After Effects - Trailer & Teaser",
    "After Effects - Transition Pack",
    "After Effects - VHS & Retro",
    "After Effects - Wedding & Romance",
    "After Effects - Other",

    # ── Premiere Pro ──────────────────────────────────────────────────────────
    "Premiere Pro - LUTs & Color Grading",
    "Premiere Pro - Motion Graphics (.mogrt)",
    "Premiere Pro - Templates",
    "Premiere Pro - Transitions & FX",
    "Premiere Pro - Title & Typography",
    "Premiere Pro - Social Media",
    "Premiere Pro - Other",

    # ── Photoshop ─────────────────────────────────────────────────────────────
    "Photoshop - Actions & Presets",
    "Photoshop - Brushes",
    "Photoshop - Mockups",
    "Photoshop - Overlays & FX",
    "Photoshop - Patterns & Textures",
    "Photoshop - Smart Objects & Templates",
    "Photoshop - Styles & Layer Effects",
    "Photoshop - Other",

    # ── Illustrator ───────────────────────────────────────────────────────────
    "Illustrator - Brushes & Swatches",
    "Illustrator - Icons & UI Kits",
    "Illustrator - Vectors & Assets",
    "Illustrator - Other",

    # ── Procreate ─────────────────────────────────────────────────────────────
    "Procreate - Brushes & Stamps",
    "Procreate - Templates & Canvases",

    # ── Color Grading ─────────────────────────────────────────────────────────
    "Color Grading & LUTs",           # standalone .cube/.3dl/.look packs
    "Lightroom - Presets & Profiles",

    # ── Motion Graphics / Multi-Tool ─────────────────────────────────────────
    "Motion Graphics - Multi-Tool Pack",  # bundles covering AE + Premiere + etc.

    # ── 3D ────────────────────────────────────────────────────────────────────
    "3D - Materials & Textures",
    "3D - Models & Objects",
    "3D - Scenes & Environments",

    # ── Fonts & Typography ────────────────────────────────────────────────────
    "Fonts & Typography",

    # ── Mockups (non-Photoshop standalone) ───────────────────────────────────
    "Mockups - Apparel",
    "Mockups - Branding & Stationery",
    "Mockups - Devices & Screens",
    "Mockups - Packaging",
    "Mockups - Print & Signage",

    # ── Print & Design Templates ─────────────────────────────────────────────
    "Print - Flyers & Posters",
    "Print - Business Cards & Stationery",
    "Print - Brochures & Books",
    "Print - Invitations & Events",
    "Print - Social Media Graphics",
    "Print - Other",

    # ── Plugins & Extensions ──────────────────────────────────────────────────
    "Plugins & Extensions",           # AE plugins, PS plugins, scripts, .zxp, .jsx

    # ── Stock ─────────────────────────────────────────────────────────────────
    "Stock Footage - Abstract & VFX",
    "Stock Footage - Aerial & Drone",
    "Stock Footage - Green Screen",
    "Stock Footage - General",
    "Stock Footage - Nature & Landscape",
    "Stock Footage - People & Lifestyle",
    "Stock Footage - Timelapse",
    "Stock Music & Audio",
    "Sound Effects & SFX",
    "Stock Photos - Food & Drink",
    "Stock Photos - General",
    "Stock Photos - Nature & Outdoors",

    # ── Video & Film Tools ────────────────────────────────────────────────────
    "Video Editing - General",        # misc video tools/packs not fitting above
    "Cinematic FX & Overlays",        # film burns, grain, lens flares, light leaks
    "VFX & Compositing",

    # ── Web ───────────────────────────────────────────────────────────────────
    "Web Template",                   # HTML/CSS/JS site templates

    # ── UI / Icons ────────────────────────────────────────────────────────────
    "UI Resources & Icon Sets",       # .ico packs, .iconpackage, UI kits, app icon sets

    # ── Software & Utilities ──────────────────────────────────────────────────
    "Software & Utilities",           # non-design software (apps, tools, scripts) that landed here by mistake

    # ── Education ────────────────────────────────────────────────────────────
    "Tutorial & Education",           # course materials, tutorial projects

    # ── Catch-all ─────────────────────────────────────────────────────────────
    "_Review",     # confidence < 50 or truly ambiguous
    "_Skip",       # empty/junk/license-only/duplicate fragment (e.g. .part2 archive)
]

# Phantom-category guard for any pre-AI stage that emits a category name
# (metadata_extractors, embeddings, marketplace_enrich). Anything not in this
# set is rejected before being written to a batch JSON file.
_CATEGORY_SET = frozenset(CATEGORIES)

# Threshold at which a pre-AI metadata stage skips downstream classification
# entirely. Below this, the hint is informational only and downstream stages run.
_METADATA_HARDROUTE_THRESHOLD = 90

CATEGORY_HINT = "\n".join(f"  {c}" for c in CATEGORIES)


def get_runtime_categories() -> list[str]:
    """Return user-taught categories ahead of the static canonical taxonomy."""
    try:
        from fileorganizer.user_categories import load_user_categories
        user_names = [name for name, _keywords in load_user_categories()]
    except Exception:
        user_names = []
    out: list[str] = []
    seen: set[str] = set()
    for category in [*user_names, *CATEGORIES]:
        key = category.casefold()
        if key in seen:
            continue
        out.append(category)
        seen.add(key)
    return out


def get_runtime_category_set() -> frozenset[str]:
    return frozenset(get_runtime_categories())


def get_runtime_category_hint() -> str:
    return "\n".join(f"  {c}" for c in get_runtime_categories())

# ── Utilities ─────────────────────────────────────────────────────────────────
def load_index() -> list[dict]:
    with open(INDEX_FILE, encoding='utf-8') as f:
        return json.load(f)

def batch_file(n: int) -> Path:
    return RESULTS_DIR / f'{BATCH_PREFIX}{n:03d}.json'


def _atomic_write_json(path: Path, payload) -> None:
    """Write a result file completely before replacing the visible batch file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w',
            encoding='utf-8',
            dir=path.parent,
            prefix=f'.{path.name}.',
            suffix='.tmp',
            delete=False,
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(payload, handle, indent=2, ensure_ascii=False)
            handle.write('\n')
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink()
            except FileNotFoundError:
                pass


def already_done(n: int) -> bool:
    path = batch_file(n)
    if not path.exists():
        return False
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(payload, list) or not payload:
        return False
    return all(
        isinstance(item, dict)
        and not item.get('_retry_required')
        and not item.get('error')
        for item in payload
    )

_JUNK_STEM_RE = re.compile(
    r'(?:INTRO-HD\.NET|AIDOWNLOAD\.NET|aidownload\.net|ShareAE\.com|'
    r'share\.ae|GFXDRUG\.COM|freegfx|graphicux|'
    r'Thumbs|desktop\.ini|__MACOSX|\.DS_Store|\.dropbox|ehthumbs)',
    re.IGNORECASE
)
# Junk top-level zip entries (exact name match, case-insensitive)
_JUNK_ZIP_NAMES = frozenset({
    'thumbs.db', '.ds_store', 'desktop.ini', '__macosx', 'ehthumbs.db',
    '.dropbox', '.gitkeep', 'read this first.pdf', 'read me.pdf',
    'readme.txt', 'readme.md', 'license.txt', 'license.pdf',
})
_DESIGN_EXTS = frozenset([
    '.aep', '.psd', '.ai', '.eps', '.mogrt', '.prproj',
    '.rar', '.zip', '.7z', '.mov', '.mp4', '.lut', '.cube',
    '.otf', '.ttf', '.woff', '.jsxbin', '.jsx', '.aex',
])

def peek_inside_zip(zip_path: str) -> tuple[str, list[str]]:
    """Return (most_informative_name, internal_extensions) from a zip/rar without extracting.
    Name priority: .aep/.prproj/.psd/.ai stem > top-level dir name > empty string.
    Extensions: all unique meaningful extensions found anywhere in the archive."""
    _DESIGN_INNER_EXTS = {
        '.aep', '.prproj', '.psd', '.psb', '.ai', '.eps', '.svg',
        '.otf', '.ttf', '.woff', '.woff2',
        '.lut', '.cube', '.3dl', '.xmp', '.dng', '.lrtemplate',
        '.atn', '.pat', '.abr', '.grd', '.ase',
        '.brushset', '.procreate',
        '.mogrt', '.mlt',
        '.c4d', '.blend', '.fbx', '.obj',
        '.jsxbin', '.jsx',
    }

    def _process_namelist(names: list[str]) -> tuple[str, list[str]]:
        inner_exts: set[str] = set()
        for n in names:
            ext = Path(n).suffix.lower()
            if ext in _DESIGN_INNER_EXTS:
                inner_exts.add(ext)
        # Priority 1: project files with informative stems
        for name in names:
            low = name.lower()
            if any(low.endswith(e) for e in ('.aep', '.prproj', '.psd', '.ai')):
                stem = Path(name).stem
                if len(stem) > 4 and not _JUNK_STEM_RE.search(stem):
                    return stem, sorted(inner_exts)
        # Priority 2: top-level folder names (prefer dirs over loose files)
        top_dirs: set[str] = set()
        top_files: set[str] = set()
        for name in names:
            parts = name.rstrip('/').split('/')
            top = parts[0]
            if not top or top.lower() in _JUNK_ZIP_NAMES:
                continue
            if name.endswith('/') or len(parts) > 1:
                top_dirs.add(top)
            else:
                top_files.add(top)
        candidates = top_dirs or top_files
        best = sorted(candidates, key=len, reverse=True)[:3]
        for t in best:
            if not _JUNK_STEM_RE.search(t) and len(t) > 4:
                return t, sorted(inner_exts)

        # Priority 3: all top-level names are junk — try second-level entries (inner ZIP/folder names)
        # Handles: VH-28331308-INTRO-HD.NET/videohive-OadzdaaH-modern-food-menu-instagram-stories.zip
        _VIDEOHIVE_PREFIX_RE = re.compile(r'^videohive-[A-Za-z0-9]+-', re.IGNORECASE)
        for name in names:
            parts = name.rstrip('/').split('/')
            if len(parts) < 2:
                continue
            inner = parts[1]
            if not inner or inner.lower() in _JUNK_ZIP_NAMES:
                continue
            if _JUNK_STEM_RE.search(inner):
                continue
            # Strip videohive-XXXXXXXX- prefixes from inner zip filenames
            stem = Path(inner).stem
            stem = _VIDEOHIVE_PREFIX_RE.sub('', stem)
            if len(stem) > 4:
                return stem, sorted(inner_exts)

        return '', sorted(inner_exts)

    # Try ZIP first
    try:
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zf:
            return _process_namelist(zf.namelist())
    except Exception:
        pass

    # Try RAR (requires rarfile + unrar CLI)
    try:
        import rarfile
        with rarfile.RarFile(zip_path, 'r') as rf:
            return _process_namelist(rf.namelist())
    except Exception:
        pass

    return '', []


def peek_extensions(folder_path: str, max_files: int = 40) -> tuple[list[str], list[str]]:
    """Return (extensions, sample_filenames) from the folder.
    Surfaces subdirectory names when they're more informative than the parent."""
    exts: set[str] = set()
    filenames: list[str] = []
    folder_stem = Path(folder_path).name.lower().rstrip()

    def is_informative(name: str) -> bool:
        path = Path(name)
        # Only strip suffix if it looks like a real file extension (2-5 alphanum chars).
        # Without this guard, pathlib splits "01. Fade-Grid 1920x1080" into
        # stem="01" and suffix=". Fade-Grid 1920x1080" — falsely short.
        if re.fullmatch(r'\.[a-zA-Z0-9]{2,6}', path.suffix or ''):
            stem = re.sub(r'\.part\d+$', '', path.stem, flags=re.IGNORECASE)
        else:
            stem = str(name)
        if stem.lower().rstrip() == folder_stem:
            return False
        if _JUNK_STEM_RE.search(stem):
            return False
        if len(stem.strip()) <= 4:
            return False
        return True

    try:
        entries = list(os.scandir(folder_path))

        for entry in entries:
            if entry.is_file():
                ext = Path(entry.name).suffix.lower()
                if ext:
                    exts.add(ext)
                if any(entry.name.lower().endswith(s) for s in _DESIGN_EXTS):
                    if entry.name.lower().endswith(('.zip', '.rar', '.7z')):
                        inner, zip_exts = peek_inside_zip(entry.path)
                        exts.update(zip_exts)  # surface internal extensions
                        if inner and is_informative(inner):
                            filenames.append(inner)
                            continue
                    if is_informative(entry.name):
                        filenames.append(Path(entry.name).stem)

            elif entry.is_dir():
                # Surface informative subdirectory names as hints
                if is_informative(entry.name):
                    # Strip junk domain suffix from subdir name for cleaner hint
                    clean = _JUNK_STEM_RE.sub('', entry.name).strip(' .-_')
                    clean = re.sub(r'^\d+[-_]', '', clean).strip(' .-_')
                    if clean and len(clean) > 4:
                        filenames.append(clean)
                # Always descend one level for extensions + L2 subdir names
                try:
                    for sub in os.scandir(entry.path):
                        if sub.is_file():
                            ext = Path(sub.name).suffix.lower()
                            if ext:
                                exts.add(ext)
                            # Surface informative zip/archive names at L2
                            if sub.name.lower().endswith(('.zip', '.rar', '.7z')):
                                inner, zip_exts = peek_inside_zip(sub.path)
                                exts.update(zip_exts)  # surface internal extensions
                                if inner and is_informative(inner):
                                    filenames.append(inner)
                        elif sub.is_dir():
                            # L2 subdir names (e.g., "wonderful-pencils-for-procreate-Aidownload.net"
                            # hidden two levels deep inside a double-nested piracy folder)
                            if is_informative(sub.name) and sub.name.lower() != entry.name.lower():
                                clean = _JUNK_STEM_RE.sub('', sub.name).strip(' .-_')
                                clean = re.sub(r'^\d+[-_]', '', clean).strip(' .-_')
                                if clean and len(clean) > 4:
                                    filenames.append(clean)
                except (PermissionError, OSError):
                    pass

    except (PermissionError, OSError):
        pass

    return sorted(exts)[:12], filenames[:5]


_PIRACY_DOMAIN_RE = re.compile(
    r'(?:aidownload|freegfx|graphicux|downloadfree|softarchive|'
    r'graphicriver|nitroflare|uploadgig|grafixfather|cgpersia|'
    r'cgpeers|motionarray|envato|videohive|audiojungle)\.(?:net|com|org)',
    re.IGNORECASE
)

def looks_generic(name: str) -> bool:
    """Return True if the folder name provides no classification clue on its own.
    When True, the prompt builder will inject filename hints from inside the folder."""
    return bool(
        re.match(r'^[0-9_\-]+$', name) or           # all digits/separators: "0000-3", "1111-22"
        re.match(r'^\d+(?:[-_]\d+)+$', name) or      # digit-separator-digit sequences
        re.match(r'^\d{5,}-INTRO-HD\.NET$', name, re.IGNORECASE) or  # INTRO-HD.NET IDs
        re.match(r'^[A-Za-z]\d+$', name) or           # single-letter labels: A4, A10, B3, a21
        re.match(r'^[A-Za-z]{1,2}$', name) or         # 1-2 pure letters: "A", "AB"
        len(name.strip()) <= 3 or                      # very short: "9", "10", "AB"
        _PIRACY_DOMAIN_RE.search(name)                 # piracy/distribution site domains in name
    )


def _build_file_type_evidence(item: dict) -> list[str]:
    """Collect only raw naming and extension evidence for stage 1."""
    name = item.get('name', '')
    full_path = item.get('path') or os.path.join(item.get('folder', ''), name)
    file_ext = item.get('file_ext')
    is_file = item.get('is_file', False)
    hints = []

    if is_file:
        if file_ext:
            hints.append(f"file type: {file_ext}")
        if file_ext in ('.zip', '.rar', '.7z'):
            try:
                inner, zip_exts = peek_inside_zip(full_path)
                if zip_exts:
                    hints.append(f"files: {', '.join(zip_exts)}")
                if inner and len(inner) > 4:
                    hints.append(f"contains: {inner}")
            except Exception:
                pass
        return hints

    exts = item.get('extensions') or item.get('exts')
    filenames = item.get('filenames')
    if exts is None:
        if full_path and os.path.isdir(full_path):
            exts, filenames = peek_extensions(full_path)
        else:
            exts, filenames = [], []
    if exts:
        hints.append(f"files: {', '.join(exts)}")
    if filenames:
        hints.append(f"contains: {' | '.join(filenames[:3])}")
    return hints

def build_prompt(
    batch_items: list[dict],
    corrector: AdaptiveCorrector | None = None,
) -> str:
    lines = []
    for i, item in enumerate(batch_items, 1):
        name = item['name']
        # Resolve full path: new sources store 'path', legacy stores 'folder'+'name'
        full_path = item.get('path') or os.path.join(item.get('folder', ''), name)
        legacy_cat = item.get('legacy_category')
        file_ext   = item.get('file_ext')
        is_file    = item.get('is_file', False)

        hints = []

        if is_file:
            # Loose file: no directory to scan
            hints.append(f"file type: {file_ext}")
            if file_ext in ('.zip', '.rar', '.7z'):
                try:
                    inner, zip_exts = peek_inside_zip(full_path)
                    if zip_exts:
                        hints.append(f"files: {', '.join(zip_exts)}")
                    if inner and len(inner) > 4:
                        hints.append(f"contains: {inner}")
                except Exception:
                    pass
        else:
            # Directory: use existing peek logic
            exts, filenames = peek_extensions(full_path)
            if exts:
                hints.append(f"files: {', '.join(exts)}")
            use_filenames = (
                filenames and (
                    looks_generic(name) or
                    not exts or
                    any(len(f) > len(name) + 10 for f in filenames)
                )
            )
            if use_filenames:
                hints.append(f"contains: {' | '.join(filenames[:3])}")

        metadata_hint = item.get("_metadata_hint")
        if isinstance(metadata_hint, dict):
            raw = metadata_hint.get("raw") or {}
            try:
                raw_text = json.dumps(raw, sort_keys=True, default=str)
            except (TypeError, ValueError):
                raw_text = str(raw)
            # Keep technical metadata useful to the provider without allowing
            # an unusually large manifest or probe response to dominate a batch.
            raw_text = raw_text[:1200]
            metadata_text = (
                f"metadata: {metadata_hint.get('category', 'unknown')} "
                f"({metadata_hint.get('confidence', 0)}%); "
                f"{metadata_hint.get('reason', '')}; raw={raw_text}"
            )
            hints.append(metadata_text)

        file_type = item.get('_file_type')
        if file_type:
            hints.append(
                f"stage 1 file type: {file_type} "
                f"({int(item.get('_file_type_confidence', 0) or 0)}% confidence)"
            )

        hint_str = f"  [{'; '.join(hints)}]" if hints else ''

        entry_lines = [f"{i}. {name}{hint_str}"]
        if legacy_cat:
            entry_lines.append(f"   Legacy category: {legacy_cat}")
        lines.append('\n'.join(entry_lines))

    items_block = '\n'.join(lines)

    prompt = f"""You are a professional design asset librarian. Classify each folder into EXACTLY one category from the list below.

CATEGORIES:
{get_runtime_category_hint()}

RULES:
1. Use extension hints in [files: ...] to inform classification — they show what file types are inside.
2. .cube/.3dl/.look = "Color Grading & LUTs"
3. .mogrt = "Premiere Pro - Motion Graphics (.mogrt)" unless name clearly says AE
4. .zxp/.jsx/.jsxbin/.aex = "Plugins & Extensions"
5. "tutorial" / "course" / "masterclass" / "class" in name or contains-hint = "Tutorial & Education"
   OR if the "contains:" hint shows a course/class/tutorial RAR name → "Tutorial & Education"
6. Folder with only a .rar/.zip (single archive, no content clue after checking hint) = "_Review"
7. ".part2" / ".part3" fragment archives, empty folders = "_Skip"
8. If name strongly implies After Effects and has .aep files → pick the matching AE subcategory
9. If name implies Photoshop (has .psd) → Photoshop subcategory; Illustrator (.ai/.eps) → Illustrator subcategory
10. "LUT" / "Color Preset" / "Color Grade" in name → "Color Grading & LUTs"
11. "Mockup" / "Mock-Up" / "Mock Up" in name → appropriate Mockups subcategory
12. Font packs (.otf/.ttf/.woff in files) → "Fonts & Typography"
13. Stock footage/video loops → appropriate "Stock Footage -" subcategory
14. Use "_Review" only when genuinely uncertain (confidence < 50%)
15. Do NOT invent category names outside the list above.
16. For folders matching `XXXXXXXXX-INTRO-HD.NET` (numeric ID only, no title):
    - If "contains:" hint reveals an informative name → classify normally using that name
    - If "contains:" hint is still just the numeric ID → "After Effects - Other" (confidence 65)
17. If 'Legacy category:' is present, treat it as a STRONG HINT — the new category should usually
    be in the same domain (e.g. "Posters" → "Print - Flyers & Posters",
    "Backgrounds" → "Photoshop - Patterns & Textures", "Cards" → "Print - Business Cards & Stationery").

ITEMS TO CLASSIFY:
{items_block}

Return ONLY a JSON array with one object per item (same order as input):
[
  {{"name": "exact folder name", "category": "Category Name", "clean_name": "Human readable title", "confidence": 85, "notes": "brief reason"}},
  ...
]
No markdown, no explanation outside the JSON array."""
    if corrector is None:
        return prompt
    return build_adaptive_batch_system_prompt(
        [str(item.get('name', '')) for item in batch_items],
        prompt,
        corrector,
    )


def build_file_type_prompt(batch_items: list[dict]) -> str:
    """Build the context-light stage 1 prompt that identifies asset families."""
    entry_lines = []
    for index, item in enumerate(batch_items, 1):
        evidence = _build_file_type_evidence(item)
        suffix = f"  [{'; '.join(evidence)}]" if evidence else ''
        entry_lines.append(f"{index}. {item.get('name', '')}{suffix}")
    items_block = '\n'.join(entry_lines)
    labels = '\n'.join(f'  {label}' for label in FILE_TYPE_LABELS)
    return f"""You are the file-type analyst in a two-stage design asset classifier.
Identify the broad application or media family for each item from its name and raw file evidence.
This stage must not choose a destination category or infer a subcategory. Do not use a legacy
category, marketplace taxonomy, or any context that is not shown in the item itself.

ALLOWED FILE TYPE LABELS:
{labels}

ITEMS:
{items_block}

Return ONLY a JSON array with one object per item, in the same order:
[
  {{"name": "exact item name", "file_type": "After Effects", "confidence": 85, "notes": "brief evidence"}},
  ...
]
The file_type must exactly match one allowed label. Use Unknown when the evidence is insufficient.
No markdown, no explanation outside the JSON array."""

# ── DeepSeek caller ───────────────────────────────────────────────────────────

class DeepSeekResponseError(RuntimeError):
    """Raised when a model response cannot be safely used as a batch."""

    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


def _validate_deepseek_batch_shape(payload, expected_count: int | None = None) -> list:
    if not isinstance(payload, list):
        raise DeepSeekResponseError(
            'outer_type',
            f"expected a JSON array, got {type(payload).__name__}",
        )
    if expected_count is not None and len(payload) != expected_count:
        raise DeepSeekResponseError(
            'cardinality',
            f"expected {expected_count} result(s), got {len(payload)}",
        )
    return payload


def _deepseek_unresolved(item: dict, index: int, reason: str) -> dict:
    name = str(item.get('name', '') or '').strip() or f'item-{index + 1}'
    return {
        'name': name,
        'category': '_Review',
        'clean_name': name,
        'confidence': 0,
        'notes': f'DeepSeek schema validation failed: {reason}',
        '_source_name': name,
        '_classifier': 'deepseek_schema_guard',
        '_retry_required': True,
        '_schema_error': reason,
    }


def _normalize_deepseek_result(
    raw,
    item: dict,
    index: int,
    category_set,
) -> dict:
    if not isinstance(raw, dict):
        return _deepseek_unresolved(item, index, 'result is not an object')
    if raw.get('_retry_required'):
        return _deepseek_unresolved(item, index, 'cached result is marked for retry')

    for field in ('name', 'category', 'clean_name'):
        value = raw.get(field)
        if not isinstance(value, str) or not value.strip():
            return _deepseek_unresolved(item, index, f'{field} must be a non-empty string')

    confidence = raw.get('confidence')
    if type(confidence) is not int or not 0 <= confidence <= 100:
        return _deepseek_unresolved(
            item,
            index,
            'confidence must be an integer from 0 through 100',
        )
    if raw['category'] not in category_set:
        return _deepseek_unresolved(
            item,
            index,
            f"category {raw['category']!r} is not in the runtime taxonomy",
        )
    if 'notes' in raw and not isinstance(raw['notes'], str):
        return _deepseek_unresolved(item, index, 'notes must be a string when present')
    return dict(raw)


def _attach_deepseek_provenance(
    item: dict,
    result: dict,
    prompt: str,
    model: str,
) -> dict:
    """Persist a hash-only evaluation record and stamp its stable ID."""
    output = dict(result)
    output.pop('_cached_provenance_id', None)
    descriptor = record_classification(
        item.get('path') or {'name': item.get('name', '')},
        provider='deepseek',
        model=model,
        prompt=prompt,
        taxonomy=sorted(get_runtime_category_set()),
        response=output,
        response_id=str(output.pop('_response_id', '') or ''),
        confidence=int(output.get('confidence', 0) or 0),
        suggested_decision=str(output.get('category', '') or ''),
    )
    output['_provenance'] = descriptor
    return output


def call_deepseek_cached(
    prompt: str,
    items: list[dict],
    model: str = DEEPSEEK_MODEL,
    corrector: AdaptiveCorrector | None = None,
) -> list[dict]:
    """
    Cached wrapper around call_deepseek (NEXT-44).
    
    For each item in items, check cache using item's path.
    Only call API for cache misses.
    Returns results in the same order as items.
    """
    from llm_cache import prompt_hash as p_hash
    
    category_set = get_runtime_category_set()
    cached_results = {}
    uncached_indices = []
    
    # Check cache for each item
    for i, item in enumerate(items):
        path = item.get('path', '').strip()
        if path:
            cached = lookup_cached(path, model, prompt)
            if cached:
                normalized = _normalize_deepseek_result(
                    cached, item, i, category_set
                )
                if not normalized.get('_retry_required'):
                    cached_results[i] = normalized
                else:
                    uncached_indices.append(i)
            else:
                uncached_indices.append(i)
        else:
            uncached_indices.append(i)
    
    # Early return if everything is cached
    if not uncached_indices:
        results = [None] * len(items)
        for i, cached in cached_results.items():
            results[i] = _attach_deepseek_provenance(items[i], cached, prompt, model)
        return results
    
    # Build prompt for uncached items only
    uncached_items = [items[i] for i in uncached_indices]
    uncached_prompt = build_prompt(uncached_items, corrector)
    
    # Call API for uncached batch
    try:
        uncached_results = call_deepseek(
            uncached_prompt,
            expected_count=len(uncached_items),
        )
    except Exception:
        raise  # Let caller handle the error

    normalized_results = []
    for i, uncached_idx in enumerate(uncached_indices):
        item = items[uncached_idx]
        normalized = _normalize_deepseek_result(
            uncached_results[i], item, uncached_idx, category_set
        )
        normalized_results.append(normalized)
        if normalized.get('_retry_required'):
            normalized_results[i] = _attach_deepseek_provenance(
                item, normalized, uncached_prompt, model
            )
            continue
        attached = _attach_deepseek_provenance(
            item, normalized, uncached_prompt, model
        )
        path = item.get('path', '').strip()
        if path:
            store_cached(
                path,
                model,
                uncached_prompt,
                normalized,
                attached.get('_provenance'),
            )
        normalized_results[i] = attached
    
    # Merge cached + API results in original order
    results = [None] * len(items)
    for i, cached in cached_results.items():
        results[i] = _attach_deepseek_provenance(items[i], cached, prompt, model)
    for i, uncached_idx in enumerate(uncached_indices):
        results[uncached_idx] = normalized_results[i]
    
    return results


def call_deepseek_parallel_cached(
    items: list[dict],
    *,
    concurrency: int = 4,
    request_batch_size: int = 12,
    model: str = DEEPSEEK_MODEL,
    corrector: AdaptiveCorrector | None = None,
) -> list[dict]:
    """Classify cached DeepSeek request chunks concurrently and in input order."""
    from fileorganizer.parallel_classifier import classify_batches_parallel

    def classify_batch(batch: list[dict]) -> list[dict]:
        return call_deepseek_cached(
            build_prompt(batch, corrector), batch, model, corrector
        )

    return classify_batches_parallel(
        items,
        classify_batch,
        concurrency=concurrency,
        batch_size=request_batch_size,
    )


def call_deepseek(
    prompt: str,
    expected_count: int | None = None,
) -> list:
    try:
        from openai import OpenAI
    except ImportError:
        print("openai package not installed. Run: pip install openai")
        sys.exit(1)

    client = OpenAI(api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_BASE)
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
        max_tokens=8000,
    )
    choices = getattr(resp, 'choices', None)
    if not choices:
        raise DeepSeekResponseError('empty_response', 'DeepSeek returned no choices')
    content = getattr(getattr(choices[0], 'message', None), 'content', None)
    if not isinstance(content, str) or not content.strip():
        raise DeepSeekResponseError('empty_response', 'DeepSeek returned no message content')
    raw = content.strip()

    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as e:
        # Attempt to extract JSON array
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            try:
                payload = json.loads(m.group())
            except json.JSONDecodeError as nested:
                raise DeepSeekResponseError(
                    'invalid_json',
                    f"could not parse extracted DeepSeek array: {nested}",
                ) from nested
        else:
            raise DeepSeekResponseError(
                'invalid_json',
                f"could not parse DeepSeek response: {e}; raw={raw[:800]!r}",
            ) from e
    validated = _validate_deepseek_batch_shape(payload, expected_count)
    response_id = str(getattr(resp, 'id', '') or '')
    if response_id:
        for item in validated:
            if isinstance(item, dict):
                item['_response_id'] = response_id
    return validated


def _file_type_unresolved(item: dict, index: int, reason: str) -> dict:
    name = str(item.get('name', '') or '').strip() or f'item-{index + 1}'
    return {
        'name': name,
        'file_type': 'Unknown',
        'confidence': 0,
        'notes': f'file-type schema validation failed: {reason}',
        '_retry_required': True,
        '_schema_error': reason,
    }


def _normalize_file_type_result(raw, item: dict, index: int) -> dict:
    """Validate one context-light stage 1 result before using it as a hint."""
    if not isinstance(raw, dict):
        return _file_type_unresolved(item, index, 'result is not an object')
    if raw.get('_retry_required'):
        return _file_type_unresolved(item, index, 'cached result is marked for retry')

    name = raw.get('name')
    if not isinstance(name, str) or not name.strip():
        return _file_type_unresolved(item, index, 'name must be a non-empty string')
    file_type = raw.get('file_type')
    if not isinstance(file_type, str) or file_type not in FILE_TYPE_SET:
        return _file_type_unresolved(
            item, index, f'file_type {file_type!r} is not in the stage 1 vocabulary'
        )
    confidence = raw.get('confidence')
    if type(confidence) is not int or not 0 <= confidence <= 100:
        return _file_type_unresolved(
            item, index, 'confidence must be an integer from 0 through 100'
        )
    if 'notes' in raw and not isinstance(raw['notes'], str):
        return _file_type_unresolved(item, index, 'notes must be a string when present')
    return dict(raw)


def call_deepseek_file_type(
    prompt: str,
    items: list[dict],
) -> list[dict]:
    """Run and validate one stage 1 file-type request."""
    raw_results = call_deepseek(prompt, expected_count=len(items))
    return [
        _normalize_file_type_result(raw, item, index)
        for index, (raw, item) in enumerate(zip(raw_results, items))
    ]


def call_deepseek_file_type_cached(
    prompt: str,
    items: list[dict],
    model: str = DEEPSEEK_MODEL,
) -> list[dict]:
    """Cache stage 1 independently from destination-category responses."""
    cache_model = f'{model}{FILE_TYPE_CACHE_MODEL_SUFFIX}'
    cached_results = {}
    uncached_indices = []

    for index, item in enumerate(items):
        path = str(item.get('path', '') or '').strip()
        if not path:
            uncached_indices.append(index)
            continue
        cached = lookup_cached(path, cache_model, prompt)
        if cached is None:
            uncached_indices.append(index)
            continue
        normalized = _normalize_file_type_result(cached, item, index)
        if normalized.get('_retry_required'):
            uncached_indices.append(index)
        else:
            cached_results[index] = normalized

    if not uncached_indices:
        return [cached_results[index] for index in range(len(items))]

    uncached_items = [items[index] for index in uncached_indices]
    uncached_prompt = build_file_type_prompt(uncached_items)
    raw_results = call_deepseek_file_type(uncached_prompt, uncached_items)
    fresh_results = {}
    for local_index, source_index in enumerate(uncached_indices):
        result = raw_results[local_index]
        fresh_results[source_index] = result
        path = str(items[source_index].get('path', '') or '').strip()
        if path and not result.get('_retry_required'):
            # Cache under the original request prompt so a later full-batch run
            # can hit the same entry instead of depending on subset ordering.
            store_cached(path, cache_model, prompt, result)

    return [
        cached_results.get(index, fresh_results[index])
        for index in range(len(items))
    ]


def _attach_file_type_context(
    items: list[dict],
    type_results: list[dict],
) -> list[dict]:
    """Copy stage 1 results into bounded stage 2 prompt context."""
    enriched = []
    for index, item in enumerate(items):
        enriched_item = dict(item)
        result = type_results[index] if index < len(type_results) else {}
        if not result.get('_retry_required') and result.get('file_type') in FILE_TYPE_SET:
            enriched_item['_file_type'] = result['file_type']
            enriched_item['_file_type_confidence'] = int(result.get('confidence', 0) or 0)
            enriched_item['_file_type_notes'] = str(result.get('notes', '') or '')[:240]
        else:
            enriched_item['_file_type'] = 'Unknown'
            enriched_item['_file_type_confidence'] = 0
            enriched_item['_file_type_notes'] = ''
        enriched.append(enriched_item)
    return enriched

# ── Commands ──────────────────────────────────────────────────────────────────
def cmd_stats(index: list[dict]):
    total = len(index)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    done = sum(1 for n in range(1, num_batches + 1) if already_done(n))
    print(f"Total items  : {total}")
    print(f"Batches total: {num_batches}")
    print(f"Batches done : {done}")
    print(f"Batches left : {num_batches - done}")
    print(f"Items left   : {max(0, total - done * BATCH_SIZE)}")

    if done:
        # Count classified items breakdown
        cat_counts = {}
        for n in range(1, num_batches + 1):
            bf = batch_file(n)
            if bf.exists():
                items = json.loads(bf.read_text(encoding='utf-8'))
                for item in items:
                    c = item.get('category', 'Unknown')
                    cat_counts[c] = cat_counts.get(c, 0) + 1
        print("\nCategory breakdown (done batches):")
        for cat, cnt in sorted(cat_counts.items(), key=lambda x: -x[1]):
            print(f"  {cnt:4d}  {cat}")

def cmd_preview(index: list[dict]):
    total = len(index)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE
    for n in range(1, num_batches + 1):
        start = (n - 1) * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch_items = index[start:end]
        done = already_done(n)
        print(f"Batch {n:03d}  items {start+1}-{end}  {'[DONE]' if done else '[PENDING]'}")
        if not done:
            for item in batch_items[:3]:
                print(f"  {item['name']}")
            if len(batch_items) > 3:
                print(f"  ... +{len(batch_items)-3} more")

def cmd_show_cats():
    print("Full category taxonomy:")
    for c in get_runtime_categories():
        print(f"  {c}")

def _try_metadata_classify(batch_items: list[dict]) -> dict[int, dict]:
    """Stage 1: zero-AI metadata-driven classification.

    Reads file content (PSD canvas, font name table, audio duration, MOGRT
    manifests, and video aspect/codec/routing) via the
    fileorganizer.metadata_extractors package. Only
    items resolved at confidence >= _METADATA_HARDROUTE_THRESHOLD (90) skip
    downstream stages. Lower-confidence hints are retained as bounded context
    for the prompt so marketplace + embeddings + AI can use their signals.

    Categories are validated against the runtime category set — a phantom hint is
    rejected before it can land in the batch JSON.
    """
    try:
        from fileorganizer.metadata_extractors import extract_hint
    except Exception:
        return {}

    if not SOURCE_DIR:
        return {}

    category_set = get_runtime_category_set()
    out: dict[int, dict] = {}
    for idx, item in enumerate(batch_items):
        try:
            hint = extract_hint(item, source_dir=SOURCE_DIR)
        except Exception:
            hint = None
        if hint is None:
            continue
        item["_metadata_hint"] = {
            "category": hint.category,
            "confidence": int(hint.confidence),
            "extractor": hint.extractor,
            "reason": hint.reason,
            "raw": dict(hint.raw or {}),
        }
        if hint.confidence < _METADATA_HARDROUTE_THRESHOLD:
            continue
        if hint.category not in category_set:
            # Phantom guard: do not let an extractor write a non-canonical
            # category, even at high confidence.
            continue
        out[idx] = hint.to_result(item.get('name', ''))
    return out


_VISION_IMAGE_EXTS = frozenset({
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp',
})
_VISION_EXTS = _VISION_IMAGE_EXTS | {'.pdf'}


def _is_visual_candidate(item: dict) -> bool:
    """Return whether an item can provide an image/PDF preview to a vision model."""
    if item.get('is_file'):
        return str(item.get('file_ext') or Path(item.get('name', '')).suffix).lower() in _VISION_EXTS
    extensions = item.get('extensions') or item.get('exts')
    if extensions is None:
        path = item.get('path') or os.path.join(item.get('folder', ''), item.get('name', ''))
        if path and os.path.isdir(path):
            extensions, _ = peek_extensions(path)
    return any(str(ext).lower() in _VISION_EXTS for ext in (extensions or []))


def _try_vision_classify(batch_items: list[dict]) -> dict[int, dict]:
    """Use an installed local multimodal model for ambiguous visual assets."""
    try:
        from fileorganizer.ollama import _find_visual_preview, ollama_classify_visual
    except Exception:
        return {}

    categories = get_runtime_categories()
    out: dict[int, dict] = {}
    for idx, item in enumerate(batch_items):
        if not _is_visual_candidate(item):
            continue
        path = item.get('path') or os.path.join(item.get('folder', ''), item.get('name', ''))
        if not path:
            continue
        try:
            result = ollama_classify_visual(
                item.get('name', ''),
                path,
                category_list=categories,
            )
        except Exception:
            result = None
        if not result:
            model_path = os.environ.get('FILEORGANIZER_QWEN_MODEL', '').strip()
            mmproj_path = os.environ.get('FILEORGANIZER_QWEN_MMPROJ', '').strip()
            if model_path and mmproj_path:
                try:
                    from fileorganizer.vlm import classify_qwen

                    preview = _find_visual_preview(path)
                    if preview is not None:
                        qwen = classify_qwen(
                            preview,
                            model_path=model_path,
                            mmproj_path=mmproj_path,
                            model_label=os.environ.get(
                                'FILEORGANIZER_QWEN_MODEL_LABEL',
                                'Qwen2.5-VL-7B',
                            ),
                            categories=categories,
                        )
                        result = {
                            'name': item.get('name', ''),
                            'category': qwen.category,
                            'clean_name': item.get('name', ''),
                            'confidence': qwen.confidence,
                            'notes': f'vlm:{qwen.model}',
                            '_source_name': item.get('name', ''),
                            '_classifier': 'vlm',
                            'metadata': {
                                'model': qwen.model,
                                'ocr_text': qwen.ocr_text,
                                'description': qwen.description,
                                'requires_ocr': qwen.requires_ocr,
                                'has_text_overlay': qwen.has_text_overlay,
                                'confidence_source': 'llama_cpp_qwen2vl',
                            },
                        }
                except Exception:
                    result = None
        if not result:
            continue
        if result.get('category') not in categories:
            continue
        if type(result.get('confidence')) is not int or result['confidence'] < 70:
            continue
        out[idx] = result
    return out


def _try_marketplace_enrich(batch_items: list[dict]) -> dict[int, dict]:
    """Pre-classify items that have a known marketplace ID.

    Returns {position_in_batch: enriched_result_dict} for items that were
    resolved with confidence >= 95.  Items not in the returned dict still need
    AI classification.
    """
    try:
        from marketplace_enrich import enrich as _enrich
    except ImportError:
        return {}

    pre: dict[int, dict] = {}
    for idx, item in enumerate(batch_items):
        name = item.get('name', '')
        result = _enrich(name)
        if result and result.get('category') and result.get('confidence', 0) >= 95:
            pre[idx] = {
                'name':             name,
                'category':         result['category'],
                'clean_name':       result.get('title', name),
                'confidence':       result['confidence'],
                'notes':            (f'marketplace_enrich: {result["platform"]}:{result["item_id"]}'),
                '_source_name':     name,
                '_marketplace_id':  f'{result["platform"]}:{result["item_id"]}',
            }
    return pre


def _try_embeddings_classify(batch_items: list[dict],
                             skip_indices: set[int]) -> dict[int, dict]:
    """Pre-classify items via local embeddings against CATEGORIES anchors.

    Returns {position_in_batch: result_dict} for items where the top-1 anchor
    cleared MIN_TOP1 AND the margin over runner-up cleared MIN_MARGIN.  Items
    not in the returned dict either fell below the threshold or had no
    embedding backend installed (silent fallback to AI).

    `skip_indices` is the set of positions already resolved by an earlier stage
    (e.g. marketplace_enrich) so we don't re-do work.
    """
    try:
        from fileorganizer.embeddings_classifier import EmbeddingsClassifier
    except Exception:
        return {}

    clf = EmbeddingsClassifier.instance()
    if not clf.available:
        return {}

    runtime_categories = get_runtime_categories()
    out: dict[int, dict] = {}
    for idx, item in enumerate(batch_items):
        if idx in skip_indices:
            continue
        name = item.get('name', '') or ''
        if not name:
            continue
        result = clf.classify(
            name, runtime_categories,
            ext_set=item.get('extensions') or item.get('exts'),
            marketplace=item.get('marketplace'),
        )
        if result:
            out[idx] = {
                'name':         name,
                'category':     result['category'],
                'clean_name':   result.get('cleaned_name', name),
                'confidence':   result['confidence'],
                'notes':        f"embeddings_classifier (top1={result['top1']}, margin={result['margin']})",
                '_source_name': name,
                '_classifier':  'embeddings',
            }
    return out


def _try_fingerprint_db_lookup(batch_items: list[dict]) -> dict[int, dict]:
    """
    Stage 0: Hash-first DB skip (NEXT-15).
    
    For each item, compute folder fingerprint and query asset_db.
    Returns resolved items at confidence 100 (zero API cost).
    Expected skip rate: 60-70% for common templates already in the DB.
    """
    out = {}
    for idx, item in enumerate(batch_items):
        name = item.get('name', '').strip()
        path = item.get('path', '').strip()
        
        if not path or not os.path.isdir(path):
            continue
        
        # Query fingerprint DB
        match = lookup_folder(path)
        if match and match['match_type'] == 'exact':
            # Exact match: use stored category at confidence 100
            category = match['category']
            clean_name = match['clean_name']
            out[idx] = {
                'name':          name,
                'category':      category,
                'clean_name':    clean_name,
                'confidence':    100,
                'notes':         f"fingerprint_db (skip_rate; {match['score']:.0%} match)",
                '_source_name':  name,
                '_classifier':   'fingerprint_db',
                '_asset_id':     match.get('asset_id'),
            }
    
    return out


def _try_adaptive_corrections(
    batch_items: list[dict],
    corrector: AdaptiveCorrector,
) -> dict[int, dict]:
    """Return exact fingerprint corrections keyed by batch position."""
    resolved = {}
    for index, item in enumerate(batch_items):
        path = str(item.get('path', '') or '')
        match = corrector.apply_correction(path)
        if match is None:
            continue
        category, weight = match
        name = str(item.get('name', '') or Path(path).name)
        resolved[index] = {
            'name': name,
            'category': category,
            'clean_name': name,
            'confidence': 100,
            'notes': f'adaptive correction (weight {weight})',
            '_source_name': name,
            '_classifier': 'adaptive_correction',
        }
    return resolved


def _run_unresolved_stage(
    batch_items: list[dict],
    resolved: dict[int, dict],
    stage: Callable[[list[dict]], dict[int, dict]],
) -> dict[int, dict]:
    """Run a position-keyed classifier only for unresolved batch items."""
    pending = [
        (index, item) for index, item in enumerate(batch_items)
        if index not in resolved
    ]
    if not pending:
        return {}
    local_results = stage([item for _, item in pending])
    return {
        pending[local_index][0]: result
        for local_index, result in local_results.items()
        if 0 <= local_index < len(pending)
    }


def cmd_run(index: list[dict], only_batch: int = 0,
            embeddings_only: bool = False, parallel: bool = False,
            concurrency: int = 4, request_batch_size: int = 12):
    """Classify all unprocessed batches.

    Stages run in order; each stage skips items resolved by an earlier one:
     -1. adaptive correction — exact user-corrected folder fingerprint
      0. fingerprint_db     — exact folder fingerprint match vs community DB
                              (zero AI cost; ~60-70% skip rate for common templates)
     1. metadata_extractors   — file-content metadata (PSD canvas, font name
                                  table, audio duration, video aspect/codec).
                                  Hardroute at confidence >= 90.
      2. vision_classifier     — local multimodal preview for ambiguous images/PDFs
      3. marketplace_enrich    — known marketplace IDs → confidence 95+
      4. embeddings_classifier — local cosine match vs category anchors
                                  (zero AI cost when top1 ≥ 0.65 AND margin ≥ 0.15)
      5. DeepSeek file-type stage — broad application/media family, no taxonomy context
      6. DeepSeek category stage  — constrained subcategory using the type result
                                    (both skipped when embeddings_only=True)
    """
    # Clean up expired cache entries (NEXT-44)
    expired_count = cleanup_expired(max_age_days=30)
    if expired_count > 0:
        print(f"Cleaned {expired_count} expired cache entry(ies)")

    total = len(index)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    batches_to_run = [only_batch] if only_batch else range(1, num_batches + 1)
    corrector = AdaptiveCorrector()

    for n in batches_to_run:
        if already_done(n) and not only_batch:
            continue  # resume-safe: skip completed batches

        start = (n - 1) * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch_items = index[start:end]

        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] Batch {n:03d}/{num_batches}  items {start+1}-{end}  ({len(batch_items)} items)")

        # Stage -1: user correction by exact folder fingerprint (NEXT-7)
        adaptive_resolved = _try_adaptive_corrections(batch_items, corrector)
        if adaptive_resolved:
            print(
                f"  Adaptive corrections matched {len(adaptive_resolved)} item(s) "
                "— skipping all downstream for those"
            )

        # Stage 0: fingerprint DB lookup (hash-first skip, NEXT-15)
        fp_resolved = _run_unresolved_stage(
            batch_items, adaptive_resolved, _try_fingerprint_db_lookup
        )
        if fp_resolved:
            print(f"  Fingerprint DB matched {len(fp_resolved)} item(s) — skipping all downstream for those")

        # Stage 1: metadata extractors (file-content driven, zero AI cost)
        prior = {**adaptive_resolved, **fp_resolved}
        meta_resolved = _run_unresolved_stage(
            batch_items, prior, _try_metadata_classify
        )
        if meta_resolved:
            print(f"  Metadata pre-classified {len(meta_resolved)} item(s) — skipping downstream for those")

        # Stage 2: local multimodal fallback for ambiguous visual assets.
        prior = {**prior, **meta_resolved}
        vision_resolved = {}
        if not embeddings_only:
            vision_resolved = _run_unresolved_stage(
                batch_items, prior, _try_vision_classify
            )
        if vision_resolved:
            print(f"  Vision pre-classified {len(vision_resolved)} item(s) — skipping downstream for those")

        # Stage 3: marketplace ID pre-classification (zero AI cost for known items)
        prior = {**prior, **vision_resolved}
        pre_enriched = _run_unresolved_stage(
            batch_items, prior, _try_marketplace_enrich
        )
        if pre_enriched:
            print(f"  Marketplace pre-classified {len(pre_enriched)} item(s) — skipping AI for those")

        # Stage 4: local embeddings classifier
        prior = {**prior, **pre_enriched}
        embed_resolved = _run_unresolved_stage(
            batch_items,
            prior,
            lambda items: _try_embeddings_classify(items, set()),
        )
        if embed_resolved:
            print(f"  Embeddings pre-classified {len(embed_resolved)} item(s) — skipping AI for those")

        resolved = {
            **fp_resolved,
            **meta_resolved,
            **vision_resolved,
            **pre_enriched,
            **embed_resolved,
            **adaptive_resolved,
        }

        # Build AI prompt only for items NOT yet resolved
        ai_items  = [(i, it) for i, it in enumerate(batch_items) if i not in resolved]
        ai_results: list[dict] = []
        if ai_items and not embeddings_only:
            if not DEEPSEEK_API_KEY:
                print("ERROR: DEEPSEEK_API_KEY not set in environment.")
                sys.exit(1)
            ai_only_batch = [it for _, it in ai_items]
            try:
                # Stage 1 identifies the broad file family before the category
                # prompt sees the destination taxonomy.  A failed type hint is
                # non-fatal: stage 2 can still use the existing evidence rules.
                type_prompt = build_file_type_prompt(ai_only_batch)
                try:
                    type_results = call_deepseek_file_type_cached(
                        type_prompt,
                        ai_only_batch,
                        DEEPSEEK_MODEL,
                    )
                except Exception as type_error:
                    print(
                        f"  File-type stage unavailable ({type(type_error).__name__}); "
                        "continuing with category evidence"
                    )
                    type_results = [
                        _file_type_unresolved(item, index, str(type_error))
                        for index, item in enumerate(ai_only_batch)
                    ]
                ai_only_batch = _attach_file_type_context(ai_only_batch, type_results)
                for (source_index, _), typed_item in zip(ai_items, ai_only_batch):
                    for key in (
                        '_file_type',
                        '_file_type_confidence',
                        '_file_type_notes',
                    ):
                        batch_items[source_index][key] = typed_item[key]
                typed_count = sum(
                    1 for result in type_results
                    if not result.get('_retry_required')
                )
                print(f"  File-type stage: {typed_count}/{len(ai_only_batch)} usable hint(s)")

                # Use cached wrapper (NEXT-44) to eliminate >90% of API calls on re-runs
                if parallel:
                    print(
                        f"  Parallel AI: {len(ai_only_batch)} item(s), "
                        f"concurrency={concurrency}, request_batch={request_batch_size}"
                    )
                    ai_results = call_deepseek_parallel_cached(
                        ai_only_batch,
                        concurrency=concurrency,
                        request_batch_size=request_batch_size,
                        model=DEEPSEEK_MODEL,
                        corrector=corrector,
                    )
                else:
                    ai_results = call_deepseek_cached(
                        build_prompt(ai_only_batch, corrector),
                        ai_only_batch,
                        DEEPSEEK_MODEL,
                        corrector,
                    )
                cache_hits = sum(1 for r in ai_results if r is not None)
                if cache_hits > 0:
                    print(f"  LLM cache hit {cache_hits}/{len(ai_results)} item(s) — skipped API calls")
            except Exception as e:
                print(f"  ERROR calling DeepSeek: {e}")
                print("  Saving partial error marker and continuing...")
                _atomic_write_json(
                    batch_file(n),
                    [{
                        'error': str(e),
                        'batch': n,
                        '_retry_required': True,
                    }],
                )
                continue

            if len(ai_results) != len(ai_items):
                print(f"  WARNING: expected {len(ai_items)} AI results, got {len(ai_results)}")

        # Merge back in original order, maintaining position-based index mapping
        results: list[dict] = []
        ai_cursor = 0
        for idx, item in enumerate(batch_items):
            if idx in resolved:
                res = dict(resolved[idx])
            elif embeddings_only:
                # Benchmark mode: leave the slot blank with a sentinel so
                # we can measure embeddings skip rate without paying for AI.
                res = {
                    'name':       item.get('name', ''),
                    'category':   '_Unresolved',
                    'clean_name': item.get('name', ''),
                    'confidence': 0,
                    'notes':      'embeddings_only: below threshold',
                }
            else:
                res = ai_results[ai_cursor] if ai_cursor < len(ai_results) else {}
                ai_cursor += 1
            file_type = item.get('_file_type')
            if file_type:
                res['_file_type'] = file_type
                res['_file_type_confidence'] = int(
                    item.get('_file_type_confidence', 0) or 0
                )
            res['_source_name'] = item['name']
            res['_batch_index'] = start + idx
            results.append(res)

        _atomic_write_json(batch_file(n), results)
        print(f"  Saved {batch_file(n).name}")

        # Quick sample
        for res in results[:3]:
            cat = res.get('category', '?')
            nm = res.get('clean_name', res.get('name', '?'))
            conf = res.get('confidence', '?')
            src = res.get('_marketplace_id', '')
            tag = res.get('_classifier', '')
            badge = ' [MKT]' if src else (f' [{tag.upper()}]' if tag else '')
            print(f"    [{conf}%] {nm}  ->  {cat}{badge}")

    print("\nAll done.")
    cmd_stats(index)

# ── Main ──────────────────────────────────────────────────────────────────────
def configure_source(source: str) -> None:
    """Apply one validated source configuration to the module pipeline."""
    if source not in SOURCE_CONFIGS:
        raise ValueError(f'Unknown classification source: {source}')
    cfg = SOURCE_CONFIGS[source]
    global INDEX_FILE, BATCH_PREFIX, SOURCE_DIR, FILE_MODE
    INDEX_FILE = Path(__file__).parent / str(cfg['index_file'])
    BATCH_PREFIX = str(cfg['batch_prefix'])
    SOURCE_DIR = str(cfg['source_dir'])
    FILE_MODE = bool(cfg.get('file_mode', False))


def _provider_runtime_settings() -> dict:
    """Load protected provider credentials and bounded parallel defaults."""
    from fileorganizer.providers import load_provider_settings

    settings = load_provider_settings()
    global DEEPSEEK_API_KEY, DEEPSEEK_BASE, DEEPSEEK_MODEL
    DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '') or str(
        settings.get('deepseek_api_key', '') or ''
    )
    DEEPSEEK_BASE = str(settings.get('deepseek_endpoint', DEEPSEEK_BASE))
    DEEPSEEK_MODEL = str(settings.get('deepseek_model', DEEPSEEK_MODEL))
    return settings


def run_source(
    source: str,
    *,
    only_batch: int = 0,
    embeddings_only: bool = False,
    parallel: bool | None = None,
    concurrency: int | None = None,
    request_batch_size: int | None = None,
) -> None:
    """Run one configured source for CLI orchestration such as organize_run."""
    configure_source(source)
    if not INDEX_FILE.exists():
        raise FileNotFoundError(
            f'{INDEX_FILE} not found; run build_source_index.py --source {source} first'
        )
    settings = _provider_runtime_settings()
    use_parallel = (
        settings.get('parallel_enabled') is True if parallel is None else parallel
    )
    worker_count = concurrency or int(settings.get('parallel_concurrency', 4))
    chunk_size = request_batch_size or int(settings.get('parallel_batch_size', 12))
    cmd_run(
        load_index(),
        only_batch=only_batch,
        embeddings_only=embeddings_only,
        parallel=use_parallel,
        concurrency=max(1, min(worker_count, 8)),
        request_batch_size=max(1, min(chunk_size, 60)),
    )


def main():
    ap = argparse.ArgumentParser(description='Design asset batch classifier')
    ap.add_argument('--preview',   action='store_true', help='Show batches without calling API')
    ap.add_argument('--run',       action='store_true', help='Classify all unprocessed batches')
    ap.add_argument('--stats',     action='store_true', help='Show progress stats')
    ap.add_argument('--show-cats', action='store_true', help='Print full category list')
    ap.add_argument('--batch',     type=int, default=0, help='Process only batch N (with --run)')
    ap.add_argument('--source',    type=str, default='design_unorg',
                    choices=list(SOURCE_CONFIGS.keys()),
                    help='Source to classify (default: design_unorg)')
    ap.add_argument('--embeddings-only', action='store_true',
                    help='Run only marketplace + local embeddings stages; skip the '
                         'AI call entirely.  Items below the embedding threshold are '
                          'recorded as _Unresolved at confidence 0.  Useful for '
                          'benchmarking the embeddings skip-rate before paying for AI.')
    ap.add_argument('--parallel', action='store_true', default=None,
                    help='Classify unresolved request chunks concurrently')
    ap.add_argument('--concurrency', type=int, choices=range(1, 9), metavar='N',
                    help='Concurrent API requests for --parallel (1-8)')
    ap.add_argument('--request-batch-size', type=int, choices=range(1, 61), metavar='N',
                    help='Folders in each parallel API request (1-60)')
    # Default export path resolves against this script's directory so the file
    # always lands at repo root regardless of the caller's CWD.
    _default_rules_path = str(Path(__file__).parent / 'organize_rules.yaml')
    ap.add_argument('--export-rules', nargs='?', const=_default_rules_path,
                    metavar='OUTPUT',
                    help='Export the canonical taxonomy + alias map as an '
                         'organize-cli-compatible YAML rules file. Pass an '
                         'output path or use the default (repo-root '
                         'organize_rules.yaml). Pass "-" to write to stdout.')
    ap.add_argument('--export-dest-root', default=r'G:\Organized',
                    help='Destination root for --export-rules move actions '
                         '(default: G:\\Organized).')
    args = ap.parse_args()

    # --export-rules is a one-shot path that doesn't need an index file;
    # handle it before the source-config wiring so a fresh checkout can run.
    if args.export_rules is not None:
        from fileorganizer.yaml_rule_export import export as _export_rules
        cfg = SOURCE_CONFIGS[args.source]
        text = _export_rules(
            output=None if args.export_rules == '-' else args.export_rules,
            dest_root=args.export_dest_root,
            source=cfg['source_dir'],
        )
        if args.export_rules == '-':
            sys.stdout.write(text)
        else:
            print(f"Exported organize-cli rules -> {args.export_rules}")
        return

    # Wire up globals for the selected source
    configure_source(args.source)

    if not INDEX_FILE.exists():
        print(f"ERROR: {INDEX_FILE} not found. Run build_source_index.py --source {args.source} first.")
        sys.exit(1)

    index = load_index()

    if args.show_cats:
        cmd_show_cats()
    elif args.stats:
        cmd_stats(index)
    elif args.preview:
        cmd_preview(index)
    elif args.run:
        settings = _provider_runtime_settings()
        use_parallel = (
            settings.get('parallel_enabled') is True
            if args.parallel is None else args.parallel
        )
        cmd_run(
            index,
            only_batch=args.batch,
            embeddings_only=args.embeddings_only,
            parallel=use_parallel,
            concurrency=args.concurrency or settings['parallel_concurrency'],
            request_batch_size=(
                args.request_batch_size or settings['parallel_batch_size']
            ),
        )
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
