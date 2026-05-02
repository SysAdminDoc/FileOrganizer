#!/usr/bin/env python3
r"""
classify_design.py — Batch classifier for design asset directories.

Reads an index JSON, peeks at file extensions inside each dir,
then sends batches of 60 to DeepSeek for classification into G:\Organized categories.

Usage:
    python classify_design.py --preview                      # show batches
    python classify_design.py --run                          # classify all pending batches
    python classify_design.py --run --batch 5                # classify only batch 5
    python classify_design.py --stats                        # show progress
    python classify_design.py --show-cats                    # print full category taxonomy
    python classify_design.py --source design_org --run      # classify G:\Design Organized
    python classify_design.py --source loose_files --run     # classify root loose files

Results saved to classification_results/<prefix>NNN.json
"""
import os, sys, json, re, argparse
from pathlib import Path
from datetime import datetime

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
DEEPSEEK_MODEL   = 'deepseek-chat'

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

# ── Utilities ─────────────────────────────────────────────────────────────────
def load_index() -> list[dict]:
    with open(INDEX_FILE, encoding='utf-8') as f:
        return json.load(f)

def batch_file(n: int) -> Path:
    return RESULTS_DIR / f'{BATCH_PREFIX}{n:03d}.json'

def already_done(n: int) -> bool:
    return batch_file(n).exists()

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

def build_prompt(batch_items: list[dict]) -> str:
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

        hint_str = f"  [{'; '.join(hints)}]" if hints else ''

        entry_lines = [f"{i}. {name}{hint_str}"]
        if legacy_cat:
            entry_lines.append(f"   Legacy category: {legacy_cat}")
        lines.append('\n'.join(entry_lines))

    items_block = '\n'.join(lines)

    return f"""You are a professional design asset librarian. Classify each folder into EXACTLY one category from the list below.

CATEGORIES:
{CATEGORY_HINT}

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

# ── DeepSeek caller ───────────────────────────────────────────────────────────
def call_deepseek(prompt: str) -> list[dict]:
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
    raw = resp.choices[0].message.content.strip()

    # Strip markdown fences if present
    raw = re.sub(r'^```(?:json)?\s*', '', raw)
    raw = re.sub(r'\s*```$', '', raw)

    try:
        return json.loads(raw)
    except json.JSONDecodeError as e:
        # Attempt to extract JSON array
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if m:
            return json.loads(m.group())
        raise RuntimeError(f"Could not parse DeepSeek response: {e}\n\nRaw:\n{raw[:800]}")

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
    for c in CATEGORIES:
        print(f"  {c}")

def _try_metadata_classify(batch_items: list[dict]) -> dict[int, dict]:
    """Stage 1: zero-AI metadata-driven classification.

    Reads file content (PSD canvas, font name table, audio duration, video
    aspect/codec) via the fileorganizer.metadata_extractors package. Only
    items resolved at confidence >= _METADATA_HARDROUTE_THRESHOLD (90) skip
    downstream stages. Lower-confidence hints are dropped silently so
    marketplace + embeddings + AI keep their say.

    Categories are validated against _CATEGORY_SET — a phantom hint is
    rejected before it can land in the batch JSON.
    """
    try:
        from fileorganizer.metadata_extractors import extract_hint
    except Exception:
        return {}

    if not SOURCE_DIR:
        return {}

    out: dict[int, dict] = {}
    for idx, item in enumerate(batch_items):
        try:
            hint = extract_hint(item, source_dir=SOURCE_DIR)
        except Exception:
            hint = None
        if hint is None:
            continue
        if hint.confidence < _METADATA_HARDROUTE_THRESHOLD:
            continue
        if hint.category not in _CATEGORY_SET:
            # Phantom guard: do not let an extractor write a non-canonical
            # category, even at high confidence.
            continue
        out[idx] = hint.to_result(item.get('name', ''))
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

    out: dict[int, dict] = {}
    for idx, item in enumerate(batch_items):
        if idx in skip_indices:
            continue
        name = item.get('name', '') or ''
        if not name:
            continue
        result = clf.classify(
            name, CATEGORIES,
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


def cmd_run(index: list[dict], only_batch: int = 0,
            embeddings_only: bool = False):
    """Classify all unprocessed batches.

    Stages run in order; each stage skips items resolved by an earlier one:
      1. metadata_extractors   — file-content metadata (PSD canvas, font name
                                  table, audio duration, video aspect/codec).
                                  Hardroute at confidence >= 90.
      2. marketplace_enrich    — known marketplace IDs → confidence 95+
      3. embeddings_classifier — local cosine match vs category anchors
                                  (zero AI cost when top1 ≥ 0.65 AND margin ≥ 0.15)
      4. DeepSeek AI           — everything else (skipped when embeddings_only=True)
    """
    if not embeddings_only and not DEEPSEEK_API_KEY:
        print("ERROR: DEEPSEEK_API_KEY not set in environment.")
        sys.exit(1)

    total = len(index)
    num_batches = (total + BATCH_SIZE - 1) // BATCH_SIZE

    batches_to_run = [only_batch] if only_batch else range(1, num_batches + 1)

    for n in batches_to_run:
        if already_done(n) and not only_batch:
            continue  # resume-safe: skip completed batches

        start = (n - 1) * BATCH_SIZE
        end = min(start + BATCH_SIZE, total)
        batch_items = index[start:end]

        ts = datetime.now().strftime('%H:%M:%S')
        print(f"[{ts}] Batch {n:03d}/{num_batches}  items {start+1}-{end}  ({len(batch_items)} items)")

        # Stage 1: metadata extractors (file-content driven, zero AI cost)
        meta_resolved = _try_metadata_classify(batch_items)
        if meta_resolved:
            print(f"  Metadata pre-classified {len(meta_resolved)} item(s) — skipping downstream for those")

        # Stage 2: marketplace ID pre-classification (zero AI cost for known items)
        pre_enriched = _try_marketplace_enrich(batch_items)
        if pre_enriched:
            # Drop any positions already resolved by Stage 1.
            pre_enriched = {k: v for k, v in pre_enriched.items() if k not in meta_resolved}
            if pre_enriched:
                print(f"  Marketplace pre-classified {len(pre_enriched)} item(s) — skipping AI for those")

        # Stage 3: local embeddings classifier
        already_resolved = set(meta_resolved.keys()) | set(pre_enriched.keys())
        embed_resolved = _try_embeddings_classify(batch_items, already_resolved)
        if embed_resolved:
            print(f"  Embeddings pre-classified {len(embed_resolved)} item(s) — skipping AI for those")

        resolved = {**meta_resolved, **pre_enriched, **embed_resolved}

        # Build AI prompt only for items NOT yet resolved
        ai_items  = [(i, it) for i, it in enumerate(batch_items) if i not in resolved]
        ai_results: list[dict] = []
        if ai_items and not embeddings_only:
            ai_only_batch = [it for _, it in ai_items]
            prompt = build_prompt(ai_only_batch)
            try:
                ai_results = call_deepseek(prompt)
            except Exception as e:
                print(f"  ERROR calling DeepSeek: {e}")
                print("  Saving partial error marker and continuing...")
                batch_file(n).write_text(
                    json.dumps([{"error": str(e), "batch": n}], indent=2),
                    encoding='utf-8'
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
            res['_source_name'] = item['name']
            res['_batch_index'] = start + idx
            results.append(res)

        batch_file(n).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
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
    cfg = SOURCE_CONFIGS[args.source]
    global INDEX_FILE, BATCH_PREFIX, SOURCE_DIR, FILE_MODE
    INDEX_FILE   = Path(__file__).parent / cfg['index_file']
    BATCH_PREFIX = cfg['batch_prefix']
    SOURCE_DIR   = cfg['source_dir']
    FILE_MODE    = bool(cfg.get('file_mode', False))

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
        cmd_run(index, only_batch=args.batch, embeddings_only=args.embeddings_only)
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
