#!/usr/bin/env python3
"""review_resolver.py — Targeted re-classifier for _Review items in done batch files.

Reads all completed batch JSON files for a given source, finds _Review items, fetches
enriched file hints (via improved peek_extensions/peek_inside_zip), then sends
them to DeepSeek in batches of 30 for re-classification. Updates batch files in place.

Usage:
  python review_resolver.py --preview                       # design_unorg default
  python review_resolver.py --run --source design_org       # design_org batches
  python review_resolver.py --run --source loose_files      # loose files batches
  python review_resolver.py --stats                         # show review counts
  python review_resolver.py --batch N                       # only batch N
"""

import argparse
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

# Bootstrap
def _bootstrap():
    import subprocess, importlib
    for pkg in ['openai']:
        try: importlib.import_module(pkg)
        except ImportError:
            subprocess.check_call([sys.executable, '-m', 'pip', 'install', pkg, '-q'])
_bootstrap()

from openai import OpenAI

# ── Source configs ────────────────────────────────────────────────────────────
SOURCE_CONFIGS = {
    'design_unorg': {
        'index_file':   Path('design_unorg_index.json'),
        'batch_prefix': 'design_batch_',
        'source_root':  Path(r'G:\Design Unorganized'),
        'file_mode':    False,
    },
    'design_org': {
        'index_file':   Path('design_org_index.json'),
        'batch_prefix': 'design_org_batch_',
        'source_root':  Path(r'G:\Design Organized'),
        'file_mode':    False,
    },
    'loose_files': {
        'index_file':   Path('loose_files_index.json'),
        'batch_prefix': 'loose_batch_',
        'source_root':  Path(r'G:\Design Unorganized'),
        'file_mode':    True,
    },
}

# ── Config (populated at runtime from --source) ───────────────────────────────
RESULTS_DIR   = Path('classification_results')
INDEX_FILE    = SOURCE_CONFIGS['design_unorg']['index_file']
DESIGN_ROOT   = SOURCE_CONFIGS['design_unorg']['source_root']
BATCH_PREFIX  = SOURCE_CONFIGS['design_unorg']['batch_prefix']
FILE_MODE     = False     # set True when source is loose_files
BATCH_SIZE    = 30        # items per DeepSeek call
CONF_THRESHOLD = 55       # confidence below this stays _Review
API_BASE      = 'https://api.deepseek.com'
MODEL         = 'deepseek-chat'

# Read API key
def get_api_key():
    key = os.environ.get('DEEPSEEK_API_KEY')
    if not key:
        kf = Path('deepseek_key.txt')
        if kf.exists():
            key = kf.read_text().strip()
    if not key:
        raise RuntimeError('DEEPSEEK_API_KEY not set and deepseek_key.txt not found')
    return key

# ── Category list ──────────────────────────────────────────────────────────────
from classify_design import CATEGORIES, peek_extensions, peek_inside_zip
CATEGORY_HINT = '\n'.join(f'  {c}' for c in CATEGORIES)

# ── Index loading ──────────────────────────────────────────────────────────────
_index_cache: dict[str, dict] | None = None

def load_index() -> dict[str, dict]:
    global _index_cache
    if _index_cache is None:
        items = json.load(open(INDEX_FILE, encoding='utf-8'))
        # Key by name; for loose files, also key by path stem
        _index_cache = {item['name']: item for item in items}
    return _index_cache

# ── Batch helpers ──────────────────────────────────────────────────────────────
def get_done_batches() -> list[int]:
    done = []
    for f in sorted(RESULTS_DIR.glob(f'{BATCH_PREFIX}*.json')):
        n = int(f.stem.replace(BATCH_PREFIX, ''))
        done.append(n)
    return done

def load_batch(n: int) -> list[dict]:
    f = RESULTS_DIR / f'{BATCH_PREFIX}{n:03d}.json'
    raw = json.load(open(f, encoding='utf-8'))
    return raw if isinstance(raw, list) else raw.get('results', raw)

def save_batch(n: int, results: list[dict]):
    f = RESULTS_DIR / f'{BATCH_PREFIX}{n:03d}.json'
    # Preserve original format
    raw = json.load(open(f, encoding='utf-8'))
    if isinstance(raw, list):
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(results, fh, ensure_ascii=False, indent=2)
    else:
        raw['results'] = results
        with open(f, 'w', encoding='utf-8') as fh:
            json.dump(raw, fh, ensure_ascii=False, indent=2)

# ── Prompt builder ─────────────────────────────────────────────────────────────
SYSTEM_PROMPT = f"""You are a design asset classifier. Re-classify items that were previously marked _Review.
Each item has a folder name and optional hints (file extensions, internal filenames, subfolder names).
Use all available hints aggressively — a filename like "Storm Photoshop Action.atn" inside a folder is definitive.

Categories:
{CATEGORY_HINT}

Rules:
1. Return ONLY valid JSON array, no markdown.
2. Each element: {{"folder_name":"...","category":"...","confidence":0-100,"clean_name":"..."}}
3. confidence >= {CONF_THRESHOLD} required to move out of _Review; below that, keep _Review.
4. clean_name = human-readable title (strip VH IDs, domain junk like Aidownload.net, underscores, dashes).
5. If "contains:" hint includes a project/tool file name, use that as the clean_name.

Extension rules:
6. .atn = Photoshop - Actions & Presets
7. .lut, .cube, .3dl = Color Grading & LUTs
8. .aep = After Effects (subcategory from name/hint)
9. .prproj = Premiere Pro - Templates
10. .otf, .ttf, .woff = Fonts & Typography
11. .psd = Photoshop (subcategory from name/hint)
12. .ai, .eps = Illustrator (subcategory from name/hint)
13. .mogrt = Premiere Pro - Templates
14. .brushset, .abr = Photoshop - Brushes (or Procreate if Procreate in name)
15. .xmp, .dng, .lrtemplate, .lrcat = Lightroom - Presets & Profiles (confidence 90+)
16. .pat = Photoshop - Patterns & Textures
17. .ase, .aco = Photoshop - Styles & Layer Effects

Content keyword rules (apply to hints and folder names):
18. "XMP PRESETS", "DNG PRESETS", "Lightroom", "LR presets" → Lightroom - Presets & Profiles
19. "Procreate", "procreate" in hint → Procreate - Brushes & Stamps (if brushes/stamps/pencils); Procreate - Templates if grid/canvas
20. "overlay", "overlays", "film grain", "dust and scratches", "lens flare" → Cinematic FX & Overlays
21. "texture", "textures", "pattern" in hint → Photoshop - Patterns & Textures
22. "action", "actions", "photoshop action" in hint → Photoshop - Actions & Presets
23. "mockup", "mockups" in hint → Photoshop - Mockups
24. "motion graphics" hint → Motion Graphics - Multi-Tool Pack
25. "brush", "brushes", "pencil", "ink" in hint (without Procreate) → Photoshop - Brushes
26. "How To Use Actions" or "How To Install Actions" in hint → Photoshop - Actions & Presets (confidence 85)
27. "How To Use Presets" in hint → Lightroom - Presets & Profiles (confidence 80)
28. "Cover Letter", "resume", "CV template" → Print - Flyers & Posters
29. "slideshow", "photo album" hint → After Effects - Slideshow
30. "intro", "opener" hint → After Effects - Intro & Opener
31. "logo reveal" hint → After Effects - Logo Reveal
32. "broadcast" hint → After Effects - Broadcast Package

Videohive ID rules:
33. Numeric IDs like 4489057, 22323501 may be Videohive item IDs. Use your training data to identify them.
    If you recognize the ID, classify with high confidence. If not, keep _Review.
34. Items with ONLY a numeric ID and no extensions/hints → _Review (confidence 40)

35. .ico, .iconpackage files → UI Resources & Icon Sets
36. Folder has category folders like "books,docs", "audio", "video" with icons → UI Resources & Icon Sets
37. Russian-language folder names mixed with icon-sounding names → UI Resources & Icon Sets
38. Folder name or hint contains "v1.", "v1.0", "v2.0", version numbers typical of apps → Software & Utilities
    (unless it's a design tool like Premiere, Photoshop, AE — those go in their respective categories)
39. "fast_renamer", "file_hunter", "Internet Download Manager", "Declutter", "Express Table" → Software & Utilities (confidence 95)
40. App installer names (e.g. ".exe", "Setup", "Portable", "Multilingual/Multilingua") → Software & Utilities
41. "Extrude", "Evolution", "Coco Color" without clear design context → Software & Utilities or Plugins & Extensions
42. Hints contain "LUT", "LUTs", "LUTs for", "Film Lut", "Cinema LUT" → Color Grading & LUTs (confidence 90)
43. "MASTER BUNDLE" + LUT hints → Color Grading & LUTs (confidence 92)
44. Hint contains "Floral", "Autumn", "Christmas Floral", "Floral Handwriting", "Floral Medley" → likely a Procreate brush pack or font family; if .otf/.ttf/woff hints → Fonts & Typography; otherwise Procreate - Brushes & Stamps (confidence 75)
45. "Main" folder name alone with floral subdir hints → Procreate - Brushes & Stamps (the subdir names are brush set names)
46. Hint contains "vscode", "node_modules", "META-INF", "package.json" without design context → Software & Utilities (confidence 90)
47. "match_v" or similar versioned plugin with VS Code hints → Software & Utilities (confidence 90)
48. Hint contains "ornamet", "ornament" → likely an ornament font or vector → Fonts & Typography or Illustrator - Vectors & Assets
49. Hint is only "fseventsd" (macOS artifact) with no other context → _Review (confidence 30)
50. Name "logging-NNNNN" with hint "_Logging" → Plugins & Extensions (After Effects/Premiere logging plugin, confidence 65)
51. "MWNW" or short alphanumeric names with no hints → _Review (confidence 30)
52. Hint text contains "Photoshop Action" anywhere → Photoshop - Actions & Presets (confidence 92)
53. Hint text contains "typeface" or "The typeface" or "font" → Fonts & Typography (confidence 95)
54. "memleak", "memleak_" — memory leak / profiling tool → Software & Utilities (confidence 85)
55. Hint "Uploaded by INTRO HD Website" → this is an INTROHD.NET item; classify by name if possible, else After Effects - Other
56. "mMovements" → After Effects - Motion Graphics (motion movement pack name pattern, confidence 65)
57. "misc" folder with only image hints and no other context → _Review (genuinely ambiguous)
58. Hints contain "MOGRTs" or "MOGRT" → After Effects - Motion Graphics Pack (confidence 90)
59. Hints contain "Film Mattes" + After Effects context → After Effects - Film Grain & Overlays (confidence 82)
60. "Nostalgia" name + After Effects/Film Mattes hints → After Effects - Film Grain & Overlays (confidence 78)
61. Folder named "Need Sorted" — classify by its hints content: Photoshop Action hints → Photoshop - Actions & Presets; Flyer hints → Photoshop - Templates & Mockups
62. "Parallel v1.1.1" with hints 'fonts', 'icons', 'custom', 'dialog' → UI Resources & Icon Sets (confidence 72)
63. Hint text contains a filename ending in ".ttf", ".otf", ".woff", ".woff2" → Fonts & Typography (confidence 95)
64. "negoziodifoto" in name → Stock Photos - General (confidence 60)
65. Any folder name starting with "photo-slideshow" or "Photo-slideshow" → After Effects - Slideshow (confidence 90)
66. Any folder name starting with "photo-gallery" or "Photo-gallery" → After Effects - Photo Album & Gallery (confidence 90)
67. Any folder name starting with "photo-memories" → After Effects - Slideshow (confidence 88)
68. Any folder name starting with "photo-album" or "photo-pile-collage" → After Effects - Slideshow (confidence 87)
69. Folder name contains "Payhip" or "Payhip –" → classify by content hints; "overlays"/"particles"/"transitions" → After Effects - Overlay & Transition; "SFX"/"overlay pack" → Cinematic FX (confidence 85)
70. Hint contains "BAT OVERLAY" or "BAT SFX" → Cinematic FX (bat/Halloween overlay pack, confidence 82)
71. Hint contains "overlays" + "particles" + "transitions" → After Effects - Overlay & Transition (confidence 85)
72. Folder named "Place Holder" or "PlaceHolder" with hints "PSD Files" or "Preview" → Photoshop - Smart Objects & Templates (confidence 75)
73. Folder named "PNG" or "PNGs" with icon-pack hints (e.g. "IconShock", "Icons_", "Icon Pack", "Pixy.Dust", "Junior") → UI Resources & Icon Sets (confidence 90)
74. Hints containing multiple "Icons_NNNN" or "IconShock" or "RealVista" patterns → UI Resources & Icon Sets (confidence 92)

Items with only numbered JPGs/PNGs inside zip and no other hints → Stock Photos - General (confidence 55)

CONFIRMED ground-truth overrides (verified by inspecting archive contents):
75. Folder name starts with "3P95ESD" → Photoshop - Print & Stationery (confirmed: "Vintage Blue Floral Wedding Invitation Set" PSD files, confidence 97)
76. Folder name starts with "5VAEUJ4" → Photoshop - Print & Stationery (confirmed: ban.psd, menu.psd, rsvp.psd — wedding/event stationery, confidence 97)
77. Folder name starts with "FZ3Y3N9" → Photoshop - Social Media Templates (confirmed: SALE.psd promotional template, confidence 97)
78. Folder name starts with "HFU549S" → Fonts & Typography (confirmed: Districtside graffiti OTF/TTF/WOFF font, confidence 99)
79. Folder name starts with "NGHQJCU" → Fonts & Typography (confirmed: Bambosa modern sans-serif OTF/TTF, confidence 99)
80. Folder name starts with "P-7854reaCP" → Software & Utilities (confirmed: reaConverter Pro 7.854 portable app, confidence 99)
81. Folder name starts with "CreativeMarket-7158301" → Photoshop - Actions & Presets (confirmed: Screenprint-Halftone-Effect-for-Posters.psd, confidence 97)
82. Folder name is "Extrude" → Software & Utilities (confirmed: Extrude.aex = After Effects plugin binary, not a template, confidence 98)
83. Folder name starts with "EzraCohen" → Tutorial & Education (confirmed: EzraCohen.Tv full-site source download with AE templates + tutorials, confidence 90)
84. Folder name starts with "IS_Brilliant" → Software & Utilities (confirmed: ISO file = Windows software installer, confidence 98)
85. Folder name starts with "MDrtsMvfx" → Cinematic FX & Overlays (confirmed: mDirts Dust PNG overlay files, confidence 97)
86. Folder name is "gleri6" → Software & Utilities (confirmed: Glary Utilities 6.20 Portable .exe, confidence 99)
87. Folder name starts with "mCuisine" → Software & Utilities (confirmed: macOS .pkg app installer, confidence 98)
88. Folder name is "Evolution" with .aep hint in Bonus → After Effects - Elements (confirmed: Design Templates 1-10.aep, confidence 95)
89. Folder name is "Dealova" → Photoshop - Print & Stationery (confirmed: Office XML color-scheme bonus files + JPG previews, invitation/stationery design set, confidence 87)
90. Folder contains only sequentially numbered JPEG/JPG files (e.g. "632 (1).jpg", "970 (1).jpg") with no other file types → Stock Photos - General (confidence 72)
91. Folder name is "Documentation" → _Review (confidence 30) — it is a documentation/help folder, not a design asset
92. Folder name contains "Help File" → _Review (confidence 30) — it is a help document, not a creative asset
93. Folder name starts with "Main print" with only README.txt → _Review (confidence 30) — incomplete/corrupted download
94. Folder name is "Reach" with .jsxbin hint → Plugins & Extensions (confirmed: Reach.jsxbin = Adobe ExtendScript binary/plugin, confidence 97)
95. Folder name starts with "graphicriver-37791226" → Photoshop - Actions & Presets (confirmed: Magical Cartoon Art Photoshop Action .atn files, confidence 99)
96. Folder name starts with "SRBSA8N" → Fonts & Typography (confirmed: Querygrand condensed bold sans OTF/TTF/WOFF, confidence 99)
97. Folder name starts with "studio-" + Videohive ID and hint "Virtual Studio" or "Multi Virtual" → After Effects - Backgrounds (virtual studio backdrop template, confidence 90)
98. Folder name starts with "storyboard-" + Videohive ID and hint "Sneaker Logo" → Illustrator - Logos & Branding (logo asset, confidence 85)
99. Folder name "Stratify" or "StyleX" or "Shifter" or "Shortcakes" with version number → Software & Utilities (versioned GUI apps, confidence 90)
100. Folder name is "subway" with no hints → _Review (confidence 30, genuinely ambiguous without hints)
101. Folder name is "subway" and internal .aep found → After Effects - Other (confirmed: Subway AE template with textures + tutorial MP4s, confidence 92)
102. Folder name is "template74" → After Effects - Intro & Opener (confirmed: AEP + C4D + intro.MP4 + Sound.wav, confidence 95)
103. Folder name is "tissue" with hint "tissue-master" and .py files → Plugins & Extensions (confirmed: Tissue Blender addon GitHub repo download, confidence 95)
104. Folder name starts with "ToothPaste" with hints including META-INF → Software & Utilities (confirmed: Java/Android app with META-INF directory structure, confidence 95)"""


def build_prompt(items: list[dict]) -> str:
    lines = []
    for item in items:
        name = item['folder_name']
        hints = []
        if item.get('exts'):
            hints.append('files: ' + ', '.join(item['exts'][:6]))
        if item.get('content_hints'):
            hints.append('contains: ' + ' | '.join(item['content_hints']))
        hint_str = '  [' + '; '.join(hints) + ']' if hints else ''
        lines.append(f'- {name}{hint_str}')
    return 'Re-classify these _Review items:\n' + '\n'.join(lines)


# ── DeepSeek caller ────────────────────────────────────────────────────────────
def call_deepseek(items: list[dict], dry_run: bool) -> list[dict] | None:
    if dry_run:
        for item in items:
            name = item_name(item)
            print(f'  PREVIEW: {name[:55]}')
            print(f'    hints: {item.get("content_hints", [])}')
        return None

    client = OpenAI(api_key=get_api_key(), base_url=API_BASE)
    prompt = build_prompt(items)
    try:
        resp = client.chat.completions.create(
            model=MODEL,
            messages=[
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': prompt},
            ],
            temperature=0.1,
            max_tokens=3000,
        )
        raw = resp.choices[0].message.content.strip()
        # Strip markdown fences if present
        if raw.startswith('```'):
            raw = '\n'.join(raw.split('\n')[1:])
            raw = raw.rsplit('```', 1)[0].strip()
        return json.loads(raw)
    except Exception as e:
        print(f'  API error: {e}')
        return None


# ── Core resolver ──────────────────────────────────────────────────────────────
def item_name(item: dict) -> str:
    """Get the folder name regardless of which key the batch file uses."""
    return item.get('folder_name') or item.get('name') or item.get('_source_name', '')


def enrich_item(item: dict) -> dict:
    """Add file hints to a _Review item by peeking inside its folder or file."""
    from classify_design import peek_inside_zip
    name = item_name(item)
    item = dict(item)
    item['folder_name'] = name
    exts, content_hints = [], []

    if FILE_MODE:
        # Item is a file, not a directory
        file_path = Path(item.get('path', '')) if item.get('path') else DESIGN_ROOT / (name + item.get('file_ext', ''))
        if file_path.exists():
            ext = file_path.suffix.lower()
            exts = [ext]
            # Peek inside archives for more hints
            if ext in ('.zip', '.rar', '.7z'):
                content_hints = peek_inside_zip(str(file_path))
    else:
        path = DESIGN_ROOT / name
        if path.exists():
            exts, content_hints = peek_extensions(str(path))
        # Include legacy_category as a hint if present
        if item.get('legacy_category'):
            content_hints = [f"legacy: {item['legacy_category']}"] + content_hints

    item['exts'] = exts
    item['content_hints'] = content_hints
    return item


def resolve_batch(batch_num: int, dry_run: bool) -> tuple[int, int]:
    """Resolve _Review items in a single batch. Returns (resolved, remaining)."""
    results = load_batch(batch_num)
    review_indices = [
        i for i, v in enumerate(results)
        if isinstance(v, dict) and v.get('category') in ('_Review', 'Review')
    ]
    if not review_indices:
        return 0, 0

    # Enrich with live folder hints
    enriched = [enrich_item(dict(results[i])) for i in review_indices]

    resolved_count = 0
    remaining_count = 0
    all_updates: dict[int, dict] = {}

    # Process in sub-batches of BATCH_SIZE
    for start in range(0, len(enriched), BATCH_SIZE):
        chunk = enriched[start:start + BATCH_SIZE]
        api_results = call_deepseek(chunk, dry_run)
        if api_results is None:
            remaining_count += len(chunk)
            continue

        # Map API results back by position
        for j, api_item in enumerate(api_results):
            if j >= len(chunk):
                break
            orig_idx = review_indices[start + j]
            cat = api_item.get('category', '_Review')
            conf = api_item.get('confidence', 0)

            if cat not in ('_Review', 'Review') and conf >= CONF_THRESHOLD:
                folder_name = item_name(results[orig_idx])
                print(f'  [RESOLVED +{conf}%] {folder_name[:50]} -> {cat}')
                resolved_count += 1
                updated = dict(results[orig_idx])
                updated['category'] = cat
                updated['confidence'] = conf
                updated['clean_name'] = api_item.get('clean_name', updated.get('clean_name', folder_name))
                updated['resolved_by'] = 'review_resolver'
                all_updates[orig_idx] = updated
            else:
                folder_name = item_name(results[orig_idx])
                print(f'  [STILL REVIEW {conf}%] {folder_name[:50]}')
                remaining_count += 1

        if not dry_run and len(chunk) == BATCH_SIZE:
            time.sleep(0.3)  # gentle rate limiting

    # Apply updates to batch file
    if not dry_run and all_updates:
        for idx, updated in all_updates.items():
            results[idx] = updated
        save_batch(batch_num, results)
        print(f'  -> Saved batch {batch_num:03d} ({resolved_count} resolved)')

    return resolved_count, remaining_count


# ── Commands ───────────────────────────────────────────────────────────────────
def cmd_stats():
    total_review = 0
    for n in get_done_batches():
        results = load_batch(n)
        rv = sum(1 for v in results if isinstance(v, dict) and v.get('category') in ('_Review', 'Review'))
        if rv:
            print(f'  Batch {n:03d}: {rv} _Review items')
            total_review += rv
    print(f'\nTotal _Review across all done batches: {total_review}')


def cmd_run(dry_run: bool, only_batch: int | None = None):
    batches = [only_batch] if only_batch else get_done_batches()
    total_resolved = total_remaining = 0

    for n in batches:
        results = load_batch(n)
        rv_count = sum(1 for v in results if isinstance(v, dict) and v.get('category') in ('_Review', 'Review'))
        if rv_count == 0:
            continue

        print(f'\n[Batch {n:03d}] {rv_count} _Review items')
        res, rem = resolve_batch(n, dry_run)
        total_resolved += res
        total_remaining += rem

    label = 'DRY RUN' if dry_run else 'DONE'
    print(f'\n{label}: {total_resolved} resolved, {total_remaining} still _Review')


def main():
    ap = argparse.ArgumentParser(description='Targeted _Review re-classifier')
    ap.add_argument('--preview', action='store_true')
    ap.add_argument('--run',     action='store_true')
    ap.add_argument('--stats',   action='store_true')
    ap.add_argument('--batch',   type=int)
    ap.add_argument('--source',  choices=list(SOURCE_CONFIGS.keys()), default='design_unorg',
                    help='Which source batch files to operate on (default: design_unorg)')
    args = ap.parse_args()

    # Apply source config to module globals
    cfg = SOURCE_CONFIGS[args.source]
    global INDEX_FILE, DESIGN_ROOT, BATCH_PREFIX, FILE_MODE
    INDEX_FILE   = cfg['index_file']
    DESIGN_ROOT  = cfg['source_root']
    BATCH_PREFIX = cfg['batch_prefix']
    FILE_MODE    = cfg['file_mode']

    if args.stats:
        cmd_stats()
    elif args.preview:
        cmd_run(dry_run=True, only_batch=args.batch)
    elif args.run:
        cmd_run(dry_run=False, only_batch=args.batch)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
