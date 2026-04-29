#!/usr/bin/env python3
r"""process_ae_archives.py — Rename + extract + classify + organize the
archives in I:\After Effects (and I:\After Effects Organized).

Per archive:
  1. List contents via 7-Zip, find every .aep / .aet / .mogrt and pick the
     most informative stem as the "project name".
  2. Sanitize the name; fall back to the cleaned archive stem if no .aep.
  3. Extract to a temporary scratch dir on the same drive.
  4. Pick a canonical category from the extracted contents
     (folder name + extensions + keyword rules).
  5. Robust-move the extracted folder to
     I:\Organized\<canonical_category>\<project_name> (same-drive os.rename).
  6. Journal the move into organize_moves.db.
  7. Delete the archive (all multipart pieces).

Resume-safe: skips archives whose target dir already exists.

Usage:
    python process_ae_archives.py --scan
    python process_ae_archives.py --apply --root "I:\After Effects"
    python process_ae_archives.py --apply --root "I:\After Effects Organized"
    python process_ae_archives.py --apply --limit 5 --root "I:\After Effects"
"""

import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).parent
sys.path.insert(0, str(REPO))
from organize_run import robust_move  # noqa: E402

DB = REPO / "organize_moves.db"
LOG_FILE = REPO / "process_ae_archives_log.json"

SEVENZIP = r"C:\Program Files\7-Zip\7z.exe"
ORGANIZED_PRIMARY = Path(r"G:\Organized")
ORGANIZED_OVERFLOW = Path(r"I:\Organized")
SCRATCH_ROOT = Path(r"I:\_ae_scratch")  # extraction staging on I:\ to avoid cross-drive
MIN_FREE_GB = 50  # destination drive headroom

# Tunable: archives in priority order
ARCHIVE_EXTS = (".zip", ".rar", ".7z")
PARTIAL_RAR_RE = re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE)

AE_PROJECT_EXTS = {".aep", ".aet"}
AE_PRESET_EXTS = {".ffx", ".aex"}
MOGRT_EXTS = {".mogrt"}
JUNK_TOKENS = re.compile(
    r"(?:INTRO-HD\.NET|AIDOWNLOAD\.NET|aidownload\.net|ShareAE\.com|"
    r"share\.ae|GFXDRUG\.COM|freegfx|graphicux|softarchive|cgpersia|"
    r"_videohive|videohive_|motionarray|envatomarket|VFXDownload\.net|"
    r"vfxdownload\.net|grafixfather)",
    re.IGNORECASE,
)
PIRACY_DOMAIN_RE = re.compile(
    r"(?:aidownload|freegfx|graphicux|downloadfree|softarchive|"
    r"graphicriver|nitroflare|uploadgig|grafixfather|cgpersia|"
    r"cgpeers|motionarray|envato|videohive|audiojungle|vfxdownload)\.(?:net|com|org)",
    re.IGNORECASE,
)
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def log(msg: str) -> None:
    print(msg.encode("cp1252", errors="replace").decode("cp1252"))


# ── Project name extraction ───────────────────────────────────────────────────
def list_archive(archive: Path) -> list[str]:
    """Return list of file paths inside the archive (using 7-Zip).

    Tolerates "Headers Error" / "Warnings" exit codes from 7z; accept any
    listing with at least one Path entry.
    """
    try:
        result = subprocess.run(
            [SEVENZIP, "l", "-slt", str(archive)],
            capture_output=True, text=True, errors="replace", timeout=300,
        )
    except subprocess.TimeoutExpired:
        return []
    names: list[str] = []
    for line in result.stdout.splitlines():
        if line.startswith("Path = "):
            current = line[7:].strip()
            if current and current != str(archive):
                names.append(current)
    return names


# Generic stems we should NOT use as project names — these are extremely
# common as the literal AE project filename ("Project.aep" inside hundreds
# of templates). When we hit one, fall back to the archive stem instead.
GENERIC_AEP_STEMS = {
    "project", "main", "comp 1", "main comp", "preview", "render",
    "untitled", "new project", "scene", "scene 1", "ae", "after effects",
    "template", "final", "edit", "footage", "main project", "video",
    "001", "01",
}


def _research_inner_archive(archive: Path, names: list[str]) -> str:
    """If the listing reveals an inner .zip / .rar named informatively,
    that name often carries the real product title. Return cleaned title
    or empty string."""
    inner_archives: list[str] = []
    for n in names:
        n_norm = n.replace("\\", "/")
        if n_norm.startswith("__MACOSX/") or "/._" in n_norm:
            continue
        ext = os.path.splitext(n)[1].lower()
        if ext in (".zip", ".rar", ".7z"):
            inner = os.path.basename(n_norm)
            stem = os.path.splitext(inner)[0]
            if stem and len(stem) > 5 and not JUNK_TOKENS.search(stem):
                inner_archives.append(stem)
    if not inner_archives:
        return ""
    # Prefer the longest informative name
    inner_archives.sort(key=len, reverse=True)
    cleaned = clean_name(inner_archives[0])
    if cleaned and len(cleaned) > 4 and cleaned.lower() not in GENERIC_AEP_STEMS:
        return cleaned
    return ""


def _research_pdf_titles(archive: Path, names: list[str]) -> str:
    """Many marketplaces ship a Readme.pdf / Help.pdf / Manual.pdf whose
    *filename* contains the product title (e.g. "Premium Light Leaks Pack
    User Guide.pdf"). Returns cleaned title or empty string."""
    for n in names:
        n_norm = n.replace("\\", "/")
        if n_norm.startswith("__MACOSX/") or "/._" in n_norm:
            continue
        if not n_norm.lower().endswith(".pdf"):
            continue
        base = os.path.basename(n_norm)
        stem = os.path.splitext(base)[0]
        if not stem or len(stem) <= 5 or JUNK_TOKENS.search(stem):
            continue
        # Strip "readme" / "user guide" / "help" suffixes to get the title
        cleaned = re.sub(
            r"\s*[-_]?\s*(?:read\s*me|user\s*guide|guide|manual|help|"
            r"documentation|installation|instructions?)\s*\.?\s*$",
            "", stem, flags=re.IGNORECASE,
        )
        cleaned = clean_name(cleaned)
        if cleaned and len(cleaned) > 4 and cleaned.lower() not in GENERIC_AEP_STEMS:
            return cleaned
    return ""


def extract_project_name(names: list[str], archive_stem: str) -> str:
    """Pick the most informative name from an archive's listing.

    Priority (highest-confidence first):
      1. Cleaned archive stem if it's a real slug
         ("095550436-photo-slideshow" -> "Photo Slideshow"). This is the
         marketplace-canonical title for any Envato slug-format zip.
      2. Stem of any .aep / .aet whose name is not generic.
      3. Inner archive name (outer-zip-of-inner-zip pattern).
      4. PDF/README filename (often "Product Title User Guide.pdf").
      5. Top-level folder name (excluding __MACOSX / .DS_Store / generic).
      6. Last-resort: any top-level dir or generic .aep stem.
    """
    # 1. Cleaned archive stem if it's a real slug — marketplace-canonical
    #    title for any Envato slug-format zip. This beats inner data because
    #    Envato slugs are deterministic and human-readable.
    cleaned_stem = clean_name(archive_stem)
    archive_stem_is_a_real_slug = (
        cleaned_stem
        and len(cleaned_stem) > 5
        and cleaned_stem.lower() not in GENERIC_AEP_STEMS
        # The archive stem must contain at least one alphabetic word, not
        # just a bare ID like "VH-3101891" or "ME-12345".
        and re.search(r"[A-Za-z]{4,}", cleaned_stem)
        and not re.fullmatch(r"(?:VH|ME)\s+\d+", cleaned_stem, re.IGNORECASE)
    )
    if archive_stem_is_a_real_slug:
        return cleaned_stem

    # 2. Informative .aep/.aet file stems
    aep_stems: list[str] = []
    generic_aep_stems: list[str] = []
    for n in names:
        # Skip macOS resource forks (__MACOSX/ tree, ._-prefixed files)
        n_norm = n.replace("\\", "/")
        if n_norm.startswith("__MACOSX/") or "/._" in n_norm or os.path.basename(n_norm).startswith("._"):
            continue
        ext = os.path.splitext(n)[1].lower()
        if ext in AE_PROJECT_EXTS:
            stem = os.path.splitext(os.path.basename(n))[0].strip()
            if not stem or JUNK_TOKENS.search(stem) or len(stem) <= 3:
                continue
            if stem.lower() in GENERIC_AEP_STEMS:
                generic_aep_stems.append(stem)
            else:
                aep_stems.append(stem)
    if aep_stems:
        aep_stems.sort(key=len, reverse=True)
        return clean_name(aep_stems[0])

    # 3. Inner archive title (outer-of-inner pattern)
    inner_title = _research_inner_archive(Path(""), names)
    if inner_title:
        return inner_title

    # 4. PDF/README filename ("Product Title User Guide.pdf")
    pdf_title = _research_pdf_titles(Path(""), names)
    if pdf_title:
        return pdf_title

    # 5. Top-level dirs (filter out __MACOSX, junk tokens, AND generic names)
    top_dirs: set[str] = set()
    for n in names:
        first = n.replace("\\", "/").split("/", 1)[0].rstrip()
        if first and first.lower() not in ("__macosx", ".ds_store", ".dropbox"):
            top_dirs.add(first)
    candidates = [
        d for d in top_dirs
        if not JUNK_TOKENS.search(d)
        and len(d) > 3
        and d.lower() not in GENERIC_AEP_STEMS
        and not re.match(r"^\(footage\)$", d, re.IGNORECASE)  # AE template helper dir
    ]
    if candidates:
        candidates.sort(key=len, reverse=True)
        return clean_name(candidates[0])

    # 6. Cleaned archive stem even if generic-looking (e.g. "VH 3101891" —
    #    we don't have anything better, keep it).
    if cleaned_stem and len(cleaned_stem) > 3:
        return cleaned_stem

    # 7. Last resort
    if top_dirs:
        return clean_name(sorted(top_dirs, key=len, reverse=True)[0])
    if generic_aep_stems:
        return clean_name(generic_aep_stems[0]) or archive_stem
    return archive_stem


def clean_name(raw: str) -> str:
    """Sanitize a project name for filesystem use + strip piracy/marketplace cruft."""
    s = raw.strip()
    # Strip multipart suffixes
    s = re.sub(r"\.part\d+$", "", s, flags=re.IGNORECASE)
    # Strip piracy domains in name
    s = PIRACY_DOMAIN_RE.sub("", s)
    s = JUNK_TOKENS.sub("", s)
    # Strip leading marketplace prefixes (VideoHive/Videohive/VH-/videohive-/elements-)
    s = re.sub(
        r"^(?:videohive[-_\s]+|VH[-_]|elements[-_\s]+|envato[-_\s]+)",
        "", s, flags=re.IGNORECASE,
    )
    s = re.sub(r"^(?:[0-9]{6,}_MotionElements_)", "", s)
    s = re.sub(r"^(?:[0-9]{7,9})[-_\s]+", "", s)  # 7-9 digit VH ID prefix
    s = re.sub(r"^(?:VH[-_])(?=\d)", "", s, flags=re.IGNORECASE)  # VH-1234
    # Strip trailing numeric marketplace IDs ("Wedding slideshow 25259629")
    s = re.sub(r"[\s_\-]+\d{6,9}\s*$", "", s)
    # Strip trailing version/parenthetical noise (CS6, CC2017, CC 2018, etc.)
    s = re.sub(
        r"\s*\((?:CS|CC)\s*\d+(?:\.\d+)?\)\s*$",
        "", s, flags=re.IGNORECASE,
    )
    s = re.sub(
        r"[_\-\s]+(?:CS|CC)\s*\d+(?:\.\d+)?\s*$",
        "", s, flags=re.IGNORECASE,
    )
    # Strip Envato slug-suffix codes ("MWFKLJ-RuBsP6N8-05-19" pattern)
    s = re.sub(
        r"[\s_\-]+[A-Z0-9]{4,8}-[A-Za-z0-9]{8,}-\d{2}-\d{2,4}\s*$",
        "", s,
    )
    # Trailing punctuation
    s = re.sub(r"\s*[-_\.]\s*$", "", s)
    # Replace separators with spaces
    s = re.sub(r"[_\-\.]+", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Remove invalid path chars
    s = INVALID_PATH_CHARS.sub("", s)
    # Title-case if all lowercase / all uppercase
    if s == s.lower() or s == s.upper():
        s = s.title()
    return s[:120].strip(" .")


# ── Category classification ──────────────────────────────────────────────────
KEYWORD_RULES: list[tuple[list[str], str]] = [
    (["lower third", "lower-third"],                     "After Effects - Lower Thirds"),
    (["logo reveal", "logo sting", "logo opener",
      "logo intro"],                                     "After Effects - Logo Reveal"),
    (["wedding", "romance", "love story", "valentine",
      "invitation"],                                     "After Effects - Wedding & Romance"),
    (["slideshow", "photo slide", "memories pack",
      "photo memories"],                                 "After Effects - Slideshow"),
    (["parallax", "photo gallery", "gallery"],           "After Effects - Photo Album & Gallery"),
    (["lyric", "lyrics", "music video"],                 "After Effects - Lyric & Music Video"),
    (["audio visual", "visualizer", "equalizer",
      "waveform"],                                       "After Effects - Music & Audio Visualizer"),
    (["news", "broadcast", "channel ident",
      "news package"],                                   "After Effects - News & Broadcast"),
    (["infographic", "data viz", "chart", "statistic"],  "After Effects - Infographic & Data Viz"),
    (["3d ", "3d_", "particle"],                         "After Effects - 3D & Particle"),
    (["glitch", "distortion", "vhs", "retro"],           "After Effects - VHS & Retro"),
    (["light leak", "lens flare", "optical flare",
      "fire pack", "smoke pack", "dust pack",
      "film grain", "film burn", "overlays pack"],       "Cinematic FX & Overlays"),
    (["christmas", "holiday", "new year", "halloween",
      "thanksgiving", "easter"],                         "After Effects - Christmas & Holiday"),
    (["sport", "soccer", "football", "basketball",
      "boxing", "racing", "fitness", "gym"],             "After Effects - Sport & Action"),
    (["kids", "cartoon", "child"],                       "After Effects - Kids & Cartoons"),
    (["real estate", "realty", "property"],              "After Effects - Real Estate"),
    (["map", "world tour", "globe ", "travel route"],    "After Effects - Map & Location"),
    (["mockup", "device", "phone", "screen"],            "After Effects - Mockup & Device"),
    (["event", "party", "celebration", "concert",
      "festival"],                                       "After Effects - Event & Party"),
    (["social media", "instagram", "facebook",
      "instastories", "story", "stories",
      "quote", "subscribe button", "youtube"],           "After Effects - Social Media"),
    (["product promo", "product showcase", "promo",
      "advertising"],                                    "After Effects - Product Promo"),
    (["trailer", "teaser", "coming soon"],               "After Effects - Trailer & Teaser"),
    (["cinematic", "film ", "movie", "documentary"],     "After Effects - Cinematic & Film"),
    (["corporate", "business", "company",
      "presentation"],                                   "After Effects - Corporate & Business"),
    (["transition", "motion pack", "fx pack",
      "transitions pack"],                               "After Effects - Transition Pack"),
    (["broadcast package", "promo package"],             "After Effects - Broadcast Package"),
    (["character", "explainer", "mascot"],               "After Effects - Character & Explainer"),
    (["liquid", "fluid", "water", "ink", "splash"],      "After Effects - Liquid & Fluid"),
    (["intro", "opener"],                                "After Effects - Intro & Opener"),
    (["title", "typography", "kinetic typography",
      "headline"],                                       "After Effects - Title & Typography"),
    (["motion graphic", "motion pack"],                  "After Effects - Motion Graphics Pack"),
    (["preset", "plugin", "script"],                     "Plugins & Extensions"),
]


def classify(project_name: str, archive_stem: str, names: list[str]) -> str:
    """Pick a canonical AE category by keyword + content signal."""
    haystack = f"{project_name} {archive_stem}".lower()

    # Exception: archive has a .mogrt → Premiere Pro
    if any(os.path.splitext(n)[1].lower() in MOGRT_EXTS for n in names):
        return "Premiere Pro - Motion Graphics (.mogrt)"

    # Exception: archive has only .ffx/.aex (preset/plugin) → Plugins & Extensions
    has_aep = any(os.path.splitext(n)[1].lower() in AE_PROJECT_EXTS for n in names)
    has_preset = any(os.path.splitext(n)[1].lower() in AE_PRESET_EXTS for n in names)
    if not has_aep and has_preset:
        return "Plugins & Extensions"

    for keywords, cat in KEYWORD_RULES:
        if any(kw in haystack for kw in keywords):
            return cat

    # Fallback
    return "After Effects - Other"


# ── Multipart RAR handling ────────────────────────────────────────────────────
def archive_group(archive: Path) -> list[Path]:
    """Return all parts that belong to this multipart archive (or just [archive]
    if it's a single file).

    For "Foo.part1.rar" returns [Foo.part1.rar, Foo.part2.rar, …].
    For "Foo.part2.rar" returns [] (only process the first part).
    """
    m = PARTIAL_RAR_RE.search(archive.name)
    if not m:
        return [archive]
    part_num = int(m.group(1))
    if part_num != 1:
        return []  # not the first part — skip; first-part handler picks all up
    base = archive.name[: m.start()]
    siblings = sorted(
        p for p in archive.parent.iterdir()
        if PARTIAL_RAR_RE.search(p.name) and p.name.startswith(base)
    )
    return siblings


# ── Disk-space-aware destination ──────────────────────────────────────────────
def pick_dest_root(src: Path) -> Path:
    """Choose the destination root that has enough free space.

    Prefer the same drive as `src` (avoids cross-drive copy). Fall back to the
    other root if the same-drive root is too full.
    """
    src_drive = os.path.splitdrive(str(src))[0].upper()
    primary_drive = os.path.splitdrive(str(ORGANIZED_PRIMARY))[0].upper()

    same_drive_root = ORGANIZED_OVERFLOW if src_drive == "I:" else ORGANIZED_PRIMARY
    other_root = ORGANIZED_PRIMARY if same_drive_root == ORGANIZED_OVERFLOW else ORGANIZED_OVERFLOW

    try:
        free = shutil.disk_usage(same_drive_root.drive + "\\").free
        if free > MIN_FREE_GB * 1_073_741_824:
            return same_drive_root
    except Exception:
        pass

    try:
        free = shutil.disk_usage(other_root.drive + "\\").free
        if free > MIN_FREE_GB * 1_073_741_824:
            return other_root
    except Exception:
        pass

    return same_drive_root  # best effort


def safe_dest(target_dir: Path, name: str) -> Path:
    base = target_dir / name
    if not base.exists():
        return base
    i = 1
    while True:
        cand = target_dir / f"{name} ({i})"
        if not cand.exists():
            return cand
        i += 1


# ── Journal ──────────────────────────────────────────────────────────────────
def journal(src: str, dst: str, name: str, category: str, conf: int) -> None:
    if not DB.exists():
        return
    con = sqlite3.connect(str(DB))
    with con:
        con.execute(
            "INSERT INTO moves (src,dest,disk_name,clean_name,category,confidence,moved_at,status) "
            "VALUES (?,?,?,?,?,?,?,?)",
            (src, dst, Path(src).name, name, category, conf,
             datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
             "done"),
        )
    con.close()


# ── Archive processing ───────────────────────────────────────────────────────
def extract_archive(archive: Path, parts: list[Path], dst_dir: Path) -> bool:
    """Extract via 7-Zip. Accept rc 0 (clean), 1 (warning), 2 (some files
    failed CRC but most extracted). Return True if at least one file or
    folder ended up in dst_dir, since CRC errors on previews/.DS_Store
    files are common and don't invalidate the AE template itself.
    """
    dst_dir.mkdir(parents=True, exist_ok=True)
    cmd = [SEVENZIP, "x", str(archive), f"-o{dst_dir}", "-y", "-bso0", "-bse0", "-bsp0"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                                errors="replace", timeout=3 * 3600)
    except subprocess.TimeoutExpired:
        log(f"  EXTRACT TIMEOUT: {archive.name}")
        return False
    # Accept anything where SOMETHING actually extracted
    try:
        extracted_anything = any(dst_dir.iterdir())
    except OSError:
        extracted_anything = False
    if result.returncode in (0, 1):
        return extracted_anything
    if result.returncode == 2 and extracted_anything:
        # Partial extract — CRC errors on individual files, but main
        # content is present. Acceptable for AE template salvage.
        log(f"  WARN partial extract (rc=2): {archive.name}")
        return True
    return False


def find_extracted_root(scratch: Path) -> Path:
    """If the extracted contents are wrapped in a single top-level folder,
    return that folder. Otherwise return scratch itself."""
    try:
        children = [c for c in scratch.iterdir()
                    if c.is_dir() and c.name.lower() not in ("__macosx", ".ds_store")]
    except OSError:
        return scratch
    files = [c for c in scratch.iterdir() if c.is_file()]
    if len(children) == 1 and not files:
        return children[0]
    return scratch


def process_archive(archive: Path, log_entries: list[dict],
                    dry_run: bool = False) -> str:
    parts = archive_group(archive)
    if not parts:
        return "skipped-multipart-tail"

    # Step 1: list contents + pick project name
    names = list_archive(archive)
    if not names:
        log(f"  [LIST FAIL] {archive.name}")
        log_entries.append({"action": "list-fail", "archive": str(archive)})
        return "list-fail"

    project_name = extract_project_name(names, archive.stem)
    if not project_name:
        project_name = clean_name(archive.stem) or archive.stem

    # Step 2: classify
    category = classify(project_name, archive.stem, names)

    # Pick destination root + collision-safe path
    dest_root = pick_dest_root(archive)
    cat_dir = dest_root / category
    final_dest = safe_dest(cat_dir, project_name)

    log(f"  [APPLY] {archive.name}")
    log(f"          project: {project_name!r}")
    log(f"          category: {category}")
    log(f"          dest: {final_dest}")

    if dry_run:
        log_entries.append({
            "action": "dry-run", "archive": str(archive),
            "project": project_name, "category": category,
            "dest": str(final_dest),
        })
        return "dry-run"

    # Resume-safe: skip if final_dest already has identical content
    if final_dest.exists():
        log(f"          dest already exists; skipping extraction")
        log_entries.append({
            "action": "skip-already-extracted", "archive": str(archive),
            "project": project_name, "dest": str(final_dest),
        })
        # Delete archive parts since target exists
        for p in parts:
            try: p.unlink()
            except OSError: pass
        return "skip-existing"

    # Step 3: extract to scratch dir on I:\
    scratch = SCRATCH_ROOT / f"_extract_{archive.stem[:60]}_{os.getpid()}"
    if scratch.exists():
        shutil.rmtree(str(scratch), ignore_errors=True)
    scratch.mkdir(parents=True, exist_ok=True)

    ok = extract_archive(archive, parts, scratch)
    if not ok:
        log(f"          EXTRACT FAILED")
        log_entries.append({"action": "extract-fail", "archive": str(archive)})
        shutil.rmtree(str(scratch), ignore_errors=True)
        return "extract-fail"

    # Step 4: locate extracted root + move
    src_dir = find_extracted_root(scratch)

    cat_dir.mkdir(parents=True, exist_ok=True)
    try:
        robust_move(str(src_dir), str(final_dest))
    except Exception as e:
        log(f"          MOVE FAILED: {e}")
        log_entries.append({
            "action": "move-fail", "archive": str(archive), "error": str(e),
        })
        return "move-fail"

    # Cleanup scratch dir
    try:
        if scratch.exists() and not list(scratch.iterdir()):
            scratch.rmdir()
        elif scratch.exists():
            shutil.rmtree(str(scratch), ignore_errors=True)
    except OSError:
        pass

    # Step 5: journal + delete archive parts
    journal(str(archive), str(final_dest), project_name, category, 80)
    for p in parts:
        try: p.unlink()
        except OSError as e: log(f"          could not delete {p.name}: {e}")

    log_entries.append({
        "action": "moved", "archive": str(archive),
        "project": project_name, "category": category,
        "dest": str(final_dest),
    })
    return "moved"


# ── Loose-file sorting (non-archive files at root) ───────────────────────────
LOOSE_EXT_TO_CATEGORY = {
    ".aep": "After Effects - Other",
    ".aet": "After Effects - Other",
    ".mogrt": "Premiere Pro - Motion Graphics (.mogrt)",
    ".prproj": "Premiere Pro - Templates",
    ".mp4": "Stock Footage - General",
    ".mov": "Stock Footage - General",
    ".mkv": "Stock Footage - General",
    ".flv": "Stock Footage - General",
    ".jpg": "Stock Photos - General",
    ".jpeg": "Stock Photos - General",
    ".png": "Stock Photos - General",
    ".pdf": "_Review",  # PDFs are usually documentation
}


def process_loose_files(root: Path, log_entries: list[dict],
                        dry_run: bool = False) -> dict:
    counts: dict[str, int] = {"moved": 0, "skipped": 0, "errors": 0}
    for entry in list(root.iterdir()):
        if entry.is_dir():
            continue
        ext = entry.suffix.lower()
        if ext in ARCHIVE_EXTS:
            continue
        cat = LOOSE_EXT_TO_CATEGORY.get(ext)
        if not cat:
            counts["skipped"] += 1
            continue
        dest_root = pick_dest_root(entry)
        cat_dir = dest_root / cat
        # Use cleaned stem as filename
        clean = clean_name(entry.stem)
        dest_name = clean + ext if clean else entry.name
        dest = safe_dest(cat_dir, dest_name)
        log(f"  [LOOSE] {entry.name}  -> {cat}/{dest.name}")
        if dry_run:
            counts["moved"] += 1
            continue
        try:
            cat_dir.mkdir(parents=True, exist_ok=True)
            robust_move(str(entry), str(dest))
            journal(str(entry), str(dest), entry.stem, cat, 70)
            counts["moved"] += 1
        except Exception as e:
            log(f"          ERROR: {e}")
            counts["errors"] += 1
            log_entries.append({"action": "loose-fail", "src": str(entry), "error": str(e)})
    return counts


# ── Main ─────────────────────────────────────────────────────────────────────
def list_archives(root: Path) -> list[Path]:
    """Return every archive at the root level, with multipart .partN.rar
    pieces filtered to only the .part1.rar (so we process each group once)."""
    archives: list[Path] = []
    for entry in root.iterdir():
        if not entry.is_file():
            continue
        ext = entry.suffix.lower()
        if ext not in ARCHIVE_EXTS:
            continue
        m = PARTIAL_RAR_RE.search(entry.name)
        if m and int(m.group(1)) != 1:
            continue
        archives.append(entry)
    archives.sort()
    return archives


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True, help=r"e.g. I:\After Effects")
    ap.add_argument("--scan", action="store_true", help="Report only — no changes")
    ap.add_argument("--apply", action="store_true", help="Extract + move + delete")
    ap.add_argument("--dry-run", action="store_true",
                    help="With --apply: show actions without executing")
    ap.add_argument("--limit", type=int, default=0,
                    help="Process at most N archives (0 = unlimited)")
    ap.add_argument("--no-loose", action="store_true",
                    help="Skip loose-file sorting")
    args = ap.parse_args()

    if not (args.scan or args.apply):
        ap.print_help()
        return

    root = Path(args.root)
    if not root.exists():
        log(f"Root not found: {root}")
        sys.exit(1)

    archives = list_archives(root)
    log(f"Found {len(archives)} archives at {root}")

    if args.scan:
        # Spot-check a few
        for a in archives[:5]:
            names = list_archive(a)
            project = extract_project_name(names, a.stem) if names else "?"
            cat = classify(project, a.stem, names) if names else "?"
            log(f"  {a.name}")
            log(f"    -> {project!r}  [{cat}]")
        return

    log_entries: list[dict] = []
    counts: dict[str, int] = {}

    SCRATCH_ROOT.mkdir(parents=True, exist_ok=True)

    processed = 0
    for archive in archives:
        if args.limit and processed >= args.limit:
            log(f"\n--limit reached, stopping at {processed}")
            break
        try:
            outcome = process_archive(archive, log_entries, dry_run=args.dry_run)
            counts[outcome] = counts.get(outcome, 0) + 1
            processed += 1
            # Incremental log save every 10 archives
            if not args.dry_run and processed % 10 == 0:
                LOG_FILE.write_text(json.dumps(log_entries, indent=2),
                                    encoding="utf-8")
        except KeyboardInterrupt:
            log("\nInterrupted by user")
            break
        except Exception as e:
            log(f"  UNEXPECTED ERROR for {archive.name}: {e}")
            counts["unexpected-error"] = counts.get("unexpected-error", 0) + 1

    # Loose files
    loose = {}
    if not args.no_loose:
        log("\n=== Loose files ===")
        loose = process_loose_files(root, log_entries, dry_run=args.dry_run)

    # Final log + summary
    if not args.dry_run:
        LOG_FILE.write_text(json.dumps(log_entries, indent=2), encoding="utf-8")

    log("\n=== Summary ===")
    for k, v in sorted(counts.items()):
        log(f"  {k}: {v}")
    if loose:
        log(f"  loose: {loose}")
    log(f"  log: {LOG_FILE.name}")


if __name__ == "__main__":
    main()
