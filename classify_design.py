#!/usr/bin/env python3
r"""
classify_design.py — Batch classifier for G:\Design Unorganized (7102 dirs)

Reads design_unorg_index.json, peeks at file extensions inside each dir,
then sends batches of 60 to DeepSeek for classification into G:\Organized categories.

Usage:
    python classify_design.py --preview       # show batches without calling API
    python classify_design.py --run           # classify all unprocessed batches
    python classify_design.py --run --batch 5 # classify only batch 5
    python classify_design.py --stats         # show progress
    python classify_design.py --show-cats     # print full category taxonomy

Results saved to classification_results/design_batch_NNN.json
"""
import os, sys, json, re, argparse
from pathlib import Path
from datetime import datetime

# ── Config ────────────────────────────────────────────────────────────────────
BATCH_SIZE   = 60
INDEX_FILE   = Path(__file__).parent / 'design_unorg_index.json'
RESULTS_DIR  = Path(__file__).parent / 'classification_results'
RESULTS_DIR.mkdir(exist_ok=True)
BATCH_PREFIX = 'design_batch_'

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
    "Stock Music & Audio",
    "Sound Effects & SFX",
    "Stock Photos - General",

    # ── Video & Film Tools ────────────────────────────────────────────────────
    "Video Editing - General",        # misc video tools/packs not fitting above
    "Cinematic FX & Overlays",        # film burns, grain, lens flares, light leaks
    "VFX & Compositing",

    # ── Web ───────────────────────────────────────────────────────────────────
    "Web Template",                   # HTML/CSS/JS site templates

    # ── Education ────────────────────────────────────────────────────────────
    "Tutorial & Education",           # course materials, tutorial projects

    # ── Catch-all ─────────────────────────────────────────────────────────────
    "_Review",     # confidence < 50 or truly ambiguous
    "_Skip",       # empty/junk/license-only/duplicate fragment (e.g. .part2 archive)
]

CATEGORY_HINT = "\n".join(f"  {c}" for c in CATEGORIES)

# ── Utilities ─────────────────────────────────────────────────────────────────
def load_index() -> list[dict]:
    with open(INDEX_FILE, encoding='utf-8') as f:
        return json.load(f)

def batch_file(n: int) -> Path:
    return RESULTS_DIR / f'{BATCH_PREFIX}{n:03d}.json'

def already_done(n: int) -> bool:
    return batch_file(n).exists()

def peek_inside_zip(zip_path: str) -> str:
    """Return the first .aep filename found inside a zip (without extracting)."""
    try:
        import zipfile
        with zipfile.ZipFile(zip_path, 'r') as zf:
            for name in zf.namelist():
                if name.lower().endswith('.aep'):
                    return Path(name).stem
            # Fallback: return the top-level folder name if it's informative
            tops = set()
            for name in zf.namelist():
                parts = name.split('/')
                if parts[0]:
                    tops.add(parts[0])
            for t in tops:
                if not re.match(r'^\d+[-_]INTRO', t, re.IGNORECASE) and len(t) > 4:
                    return t
    except Exception:
        pass
    return ''


def peek_extensions(folder_path: str, max_files: int = 40) -> tuple[list[str], list[str]]:
    """Return (extensions, sample_filenames) from the top level of the folder.
    For folders with generic/numeric names, the filenames reveal the actual content."""
    exts = set()
    filenames = []
    try:
        entries = list(os.scandir(folder_path))
        for entry in entries:
            if entry.is_file():
                ext = Path(entry.name).suffix.lower()
                if ext:
                    exts.add(ext)
                # Capture archive and media filenames (they reveal content)
                if any(entry.name.lower().endswith(s) for s in
                       ('.rar','.zip','.7z','.part1.rar','.mov','.mp4','.aep','.psd','.ai')):
                    # For a single zip matching the folder name (INTRO-HD.NET pattern),
                    # peek inside for the .aep filename
                    if entry.name.lower().endswith('.zip'):
                        inner_name = peek_inside_zip(entry.path)
                        if inner_name and not re.match(r'^\d+[-_]INTRO', inner_name, re.IGNORECASE):
                            filenames.append(inner_name)
                            continue
                    # Strip common junk suffixes from the stem for readability
                    stem = Path(entry.name).stem
                    stem = re.sub(r'\.part\d+$', '', stem, flags=re.IGNORECASE)
                    # Skip stems that are just the folder name (no extra info)
                    if stem.lower().rstrip() != Path(folder_path).name.lower().rstrip():
                        filenames.append(stem)

        if not exts:
            # go one level deeper if top is empty
            for entry in entries:
                if entry.is_dir():
                    for sub in os.scandir(entry.path):
                        if sub.is_file():
                            ext = Path(sub.name).suffix.lower()
                            if ext:
                                exts.add(ext)
    except (PermissionError, OSError):
        pass
    return sorted(exts)[:12], filenames[:4]  # cap both


def looks_generic(name: str) -> bool:
    """Return True if the folder name provides no classification clue."""
    return bool(re.match(r'^[0-9_\-]+$', name) or
                re.match(r'^\d+(?:[-_]\d+)+$', name) or
                re.match(r'^\d{5,}-INTRO-HD\.NET$', name, re.IGNORECASE))

def build_prompt(batch_items: list[dict]) -> str:
    lines = []
    for i, item in enumerate(batch_items, 1):
        name = item['name']
        path = os.path.join(item['folder'], item['name'])
        exts, filenames = peek_extensions(path)
        hints = []
        if exts:
            hints.append(f"files: {', '.join(exts)}")
        if filenames and (looks_generic(name) or not exts):
            hints.append(f"contains: {' | '.join(filenames)}")
        hint_str = f"  [{'; '.join(hints)}]" if hints else ''
        lines.append(f"{i}. {name}{hint_str}")

    items_block = '\n'.join(lines)

    return f"""You are a professional design asset librarian. Classify each folder into EXACTLY one category from the list below.

CATEGORIES:
{CATEGORY_HINT}

RULES:
1. Use extension hints in [files: ...] to inform classification — they show what file types are inside.
2. .cube/.3dl/.look = "Color Grading & LUTs"
3. .mogrt = "Premiere Pro - Motion Graphics (.mogrt)" unless name clearly says AE
4. .zxp/.jsx/.jsxbin/.aex = "Plugins & Extensions"
5. "tutorial" / "course" in name = "Tutorial & Education"
6. Folder with only a .txt, .pdf, or .rar/.zip (single archive, no content clue) = "_Review"
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

def cmd_run(index: list[dict], only_batch: int = 0):
    if not DEEPSEEK_API_KEY:
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

        prompt = build_prompt(batch_items)

        try:
            results = call_deepseek(prompt)
        except Exception as e:
            print(f"  ERROR calling DeepSeek: {e}")
            print("  Saving partial error marker and continuing...")
            batch_file(n).write_text(
                json.dumps([{"error": str(e), "batch": n}], indent=2),
                encoding='utf-8'
            )
            continue

        # Validate count
        if len(results) != len(batch_items):
            print(f"  WARNING: expected {len(batch_items)} results, got {len(results)}")

        # Annotate with source name for audit
        for i, res in enumerate(results):
            if i < len(batch_items):
                res['_source_name'] = batch_items[i]['name']
                res['_batch_index'] = start + i

        batch_file(n).write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')
        print(f"  Saved {batch_file(n).name}")

        # Quick sample
        for res in results[:3]:
            cat = res.get('category', '?')
            nm = res.get('clean_name', res.get('name', '?'))
            conf = res.get('confidence', '?')
            print(f"    [{conf}%] {nm}  →  {cat}")

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
    args = ap.parse_args()

    if not INDEX_FILE.exists():
        print(f"ERROR: {INDEX_FILE} not found. Run build step first.")
        sys.exit(1)

    index = load_index()

    if args.show_cats:
        cmd_show_cats()
    elif args.stats:
        cmd_stats(index)
    elif args.preview:
        cmd_preview(index)
    elif args.run:
        cmd_run(index, only_batch=args.batch)
    else:
        ap.print_help()

if __name__ == '__main__':
    main()
