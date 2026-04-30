#!/usr/bin/env python3
r"""audit_organized.py - Two-stage repair of `I:\Organized\<category>\<project>\`:

  Stage 1 - Misclassification audit
    Scan each project directory's contents, infer the actual project type
    from authoritative file extensions (.aep => After Effects, .psd =>
    Photoshop, etc.), and propose moving the project to the correct
    category if it's currently filed under the wrong one.

    Example: After Effects - Other / Anniversary Premium Template /
    contains only .psd files -> belongs under Photoshop - Smart Objects.

  Stage 2 - Filename English-ification
    For each project directory, detect inner files whose basename is
    non-English (CJK chars, Cyrillic, mojibake from cp437/cp936, or a
    romanized foreign stem that shares zero words with the directory
    name). Rename those files to match the directory's clean English
    name, preserving extensions and any trailing variant tokens
    (`BT`, `_v2`, etc.).

    Example: Annual Meeting Opening Countdown Video /
      JinShu Daijishi.aep             -> Annual Meeting Opening Countdown Video.aep
      JinShu Daijishi BT.mp4          -> Annual Meeting Opening Countdown Video BT.mp4
      x???x???x???x???x???.docx       -> Annual Meeting Opening Countdown Video.docx

Usage:
    python audit_organized.py --root "I:\Organized" --scan          # report
    python audit_organized.py --root "I:\Organized" --apply         # both fixes
    python audit_organized.py --root "I:\Organized" --classify-only # stage 1 only
    python audit_organized.py --root "I:\Organized" --rename-only   # stage 2 only
    python audit_organized.py --root "I:\Organized" --apply --category "After Effects - Other"
"""
import argparse
import json
import os
import re
import shutil
import sys
import unicodedata
from collections import Counter
from pathlib import Path

# ============================================================
# Project-type detection by file extension
# ============================================================

# Authoritative extensions: presence of one of these is the strongest
# signal of project type. Order matters: AE/PR/PS take priority over
# generic extensions like .mp4/.jpg which are auxiliary in those
# projects but primary in stock-footage/photo projects.
EXT_TO_TYPE = {
    # After Effects
    ".aep": "ae", ".aepx": "ae", ".aet": "ae",
    # Premiere Pro
    ".prproj": "prpro", ".mogrt": "mogrt",
    # Photoshop
    ".psd": "ps", ".psb": "ps",
    # Photoshop styles/actions/brushes/patterns
    ".asl": "ps_styles", ".atn": "ps_actions", ".abr": "ps_brushes",
    ".pat": "ps_patterns", ".csh": "ps_shapes",
    # Illustrator
    ".ai": "ai", ".eps": "ai_eps",
    # InDesign
    ".indd": "id", ".idml": "id",
    # DaVinci Resolve
    ".drp": "resolve", ".drb": "resolve",
    # Final Cut
    ".fcpx": "fcpx", ".fcpxml": "fcpx",
    # 3D
    ".blend": "blender", ".c4d": "c4d", ".max": "max",
    ".ma": "maya", ".mb": "maya",
    ".obj": "3d_model", ".fbx": "3d_model", ".3ds": "3d_model",
    ".dae": "3d_model", ".stl": "3d_model", ".gltf": "3d_model",
    ".glb": "3d_model", ".usdz": "3d_model",
    # Lightroom
    ".lrtemplate": "lr", ".xmp": "lr",
    # Fonts
    ".ttf": "font", ".otf": "font", ".woff": "font", ".woff2": "font",
    # Audio
    ".wav": "audio", ".mp3": "audio", ".aif": "audio", ".aiff": "audio",
    ".flac": "audio", ".ogg": "audio", ".m4a": "audio",
    # LUTs
    ".cube": "lut", ".3dl": "lut", ".look": "lut",
    # Video (auxiliary - only signals stock if NO project file present)
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video",
    ".mxf": "video", ".webm": "video",
    # Images (auxiliary)
    ".jpg": "image", ".jpeg": "image", ".png": "image",
    ".tif": "image", ".tiff": "image", ".webp": "image",
}

# Type-priority ordering: when a project contains multiple types, the
# top-most type in this list wins. AE/PR project files always beat raw
# media because they ARE the deliverable; raw media is just inputs.
TYPE_PRIORITY = [
    "ae", "prpro", "mogrt", "ps", "ai", "id", "resolve", "fcpx",
    "blender", "c4d", "max", "maya", "3d_model",
    "ps_styles", "ps_actions", "ps_brushes", "ps_patterns", "ps_shapes",
    "ai_eps", "lr", "lut", "font",
    "audio", "video", "image",
]

# Primary types: a project is confidently "of this type" when it has at
# least one of these files. Auxiliary types (audio/video/image) only
# count as a primary signal when there's no primary at all AND the
# project has 5+ such files (i.e., it's a real stock pack, not a
# template with a few preview clips).
PRIMARY_TYPES = {
    "ae", "prpro", "mogrt", "ps", "ai", "id", "resolve", "fcpx",
    "blender", "c4d", "max", "maya", "3d_model",
    "ps_styles", "ps_actions", "ps_brushes", "ps_patterns", "ps_shapes",
    "ai_eps", "lr", "lut", "font",
}
AUXILIARY_TYPES = {"audio", "video", "image"}
AUXILIARY_MIN_COUNT = 5  # need this many to count as a stock pack

# Map detected type -> expected category prefix. If the project's
# current parent category doesn't start with one of these prefixes,
# propose a move.
TYPE_TO_CATEGORY_PREFIX = {
    "ae":           "After Effects",
    "prpro":        "Premiere Pro",
    "mogrt":        "Premiere Pro - Motion Graphics",
    "ps":           "Photoshop",
    "ps_styles":    "Photoshop - Styles & Layer Effects",
    "ps_actions":   "Photoshop - Actions & Presets",
    "ps_brushes":   "Photoshop - Brushes",
    "ps_patterns":  "Photoshop - Patterns & Textures",
    "ps_shapes":    "Photoshop",
    "ai":           "Illustrator",
    "ai_eps":       "Illustrator",
    "id":           "Print",
    "resolve":      "Premiere Pro",   # no DaVinci category exists; closest is video editing
    "fcpx":         "Video Editing - General",
    "blender":      "3D - Models & Objects",
    "c4d":          "3D - Models & Objects",
    "max":          "3D - Models & Objects",
    "maya":         "3D - Models & Objects",
    "3d_model":     "3D - Models & Objects",
    "lr":           "Lightroom - Presets & Profiles",
    "lut":          "Color Grading & LUTs",
    "font":         "Fonts & Typography",
    "audio":        "Stock Music & Audio",
    "video":        "Stock Footage - General",
    "image":        "Stock Photos - General",
}

# Default fallback category for each prefix when the existing one isn't
# clearly wrong (e.g., a Photoshop project with .psd should go to
# Photoshop - Other, not the very specific Photoshop - Mockups).
PREFIX_FALLBACK_CATEGORY = {
    "After Effects": "After Effects - Other",
    "Premiere Pro":  "Premiere Pro - Templates",
    "Premiere Pro - Motion Graphics": "Premiere Pro - Motion Graphics (.mogrt)",
    "Photoshop":     "Photoshop - Other",
    "Illustrator":   "Illustrator - Vectors & Assets",
    "Print":         "Print - Other",
}

# Detected-type -> set of category prefixes where THAT type is an
# expected, legitimate fit (not a misclassification). PSDs in Mockups
# are correct; PSDs in After Effects are not.
COMPATIBLE_CATEGORY_PREFIXES = {
    "ae":          {"After Effects"},
    "prpro":       {"Premiere Pro"},
    "mogrt":       {"Premiere Pro"},
    "ps":          {"Photoshop", "Mockups", "Print", "Web Template",
                    "UI Resources & Icon Sets",
                    "Print - Other", "Print - Brochures & Books",
                    "Print - Business Cards & Stationery",
                    "Print - Flyers & Posters",
                    "Print - Invitations & Events",
                    "Print - Social Media Graphics",
                    "Cinematic FX & Overlays"},
    "ps_styles":   {"Photoshop"},
    "ps_actions":  {"Photoshop"},
    "ps_brushes":  {"Photoshop"},
    "ps_patterns": {"Photoshop"},
    "ps_shapes":   {"Photoshop"},
    "ai":          {"Illustrator", "Print", "Fonts & Typography",
                    "UI Resources & Icon Sets", "Mockups"},
    "ai_eps":      {"Illustrator", "Print", "Fonts & Typography",
                    "UI Resources & Icon Sets"},
    "id":          {"Print"},
    "resolve":     {"Premiere Pro", "Video Editing - General"},
    "fcpx":        {"Video Editing - General", "Premiere Pro"},
    "blender":     {"3D - Models & Objects", "3D - Scenes & Environments"},
    "c4d":         {"3D - Models & Objects", "3D - Scenes & Environments"},
    "max":         {"3D - Models & Objects", "3D - Scenes & Environments"},
    "maya":        {"3D - Models & Objects", "3D - Scenes & Environments"},
    "3d_model":    {"3D - Models & Objects", "3D - Scenes & Environments",
                    "3D - Materials & Textures"},
    "lr":          {"Lightroom - Presets & Profiles"},
    "lut":         {"Color Grading & LUTs",
                    "Premiere Pro - LUTs & Color Grading"},
    "font":        {"Fonts & Typography"},
    "audio":       {"Stock Music & Audio", "Sound Effects & SFX"},
    "video":       {"Stock Footage", "Cinematic FX & Overlays",
                    "VFX & Compositing"},
    "image":       {"Stock Photos", "Photoshop - Patterns & Textures",
                    "3D - Materials & Textures"},
}


def detect_project_type(project_dir: Path,
                        max_depth: int = 4) -> tuple[str | None, Counter]:
    """Walk project_dir up to max_depth, count files by detected type,
    return (winning_type, full_counter).

    Selection rule:
      1. If any PRIMARY_TYPES file is present, the highest-priority
         primary type wins regardless of auxiliary counts.
      2. Otherwise, if AUXILIARY_TYPES has >= AUXILIARY_MIN_COUNT files,
         the top auxiliary type wins (it's a real stock pack).
      3. Otherwise return None (don't move - signal too weak)."""
    counts: Counter = Counter()
    base_depth = len(project_dir.parts)
    for root, dirs, files in os.walk(project_dir):
        depth = len(Path(root).parts) - base_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        if "__MACOSX" in root or root.endswith(".dSYM"):
            dirs[:] = []
            continue
        for fn in files:
            ext = Path(fn).suffix.lower()
            t = EXT_TO_TYPE.get(ext)
            if t:
                counts[t] += 1
    if not counts:
        return None, counts

    # Primary type wins if present
    for t in TYPE_PRIORITY:
        if t in PRIMARY_TYPES and counts.get(t):
            return t, counts
    # Auxiliary fallback
    for t in TYPE_PRIORITY:
        if t in AUXILIARY_TYPES and counts.get(t, 0) >= AUXILIARY_MIN_COUNT:
            return t, counts
    return None, counts


def folder_name_implies(folder_name: str) -> set[str]:
    """Return the set of type tokens the folder NAME explicitly mentions.
    Used as a veto signal: if the name says "After Effects Template" but
    contents are only .psd, skip auto-move - the project is probably
    incomplete or mislabeled, not misfiled."""
    s = folder_name.lower()
    out = set()
    if re.search(r"\b(after\s*effects?|aep|ae\s+template)\b", s):
        out.add("ae")
    if re.search(r"\b(photoshop|psd)\b", s):
        out.add("ps")
    if re.search(r"\b(premiere|prproj|\.pr\b)", s):
        out.add("prpro")
    if re.search(r"\b(illustrator|\.ai\b|vector)\b", s):
        out.add("ai")
    if re.search(r"\b(indesign|\.indd|brochure|booklet)\b", s):
        out.add("id")
    if re.search(r"\bhtml\b|\bweb\s*template\b", s):
        out.add("web")
    if re.search(r"\b(blender|cinema\s*4d|\.c4d|\.blend|3ds\s*max|maya)\b",
                 s):
        out.add("3d")
    if re.search(r"\b(font|typeface|typo)\w*", s):
        out.add("font")
    return out


def find_correct_category(detected_type: str | None, current_category: str,
                          all_categories: list[str],
                          folder_name: str = "",
                          counts: Counter | None = None) -> str | None:
    """If the project's content type contradicts its current parent
    category, return the suggested new category name (which must already
    exist in all_categories). Return None if no move is needed.

    Veto: if the folder NAME implies the same prefix as the current
    category, don't move (the project is likely incomplete).

    Compatibility veto: if ANY file in the project belongs to a type
    compatible with the current category, leave the project alone (it
    is a legitimate mixed-asset bundle, not a misclassification)."""
    if detected_type is None:
        return None
    expected_prefix = TYPE_TO_CATEGORY_PREFIX.get(detected_type)
    if not expected_prefix:
        return None

    cat_prefix = current_category.split(" - ", 1)[0]
    expected_top = expected_prefix.split(" - ", 1)[0]

    if (expected_prefix.startswith("Premiere Pro - Motion Graphics")
            and current_category.startswith("Premiere Pro - Motion Graphics")):
        return None
    if cat_prefix == expected_top:
        return None

    # Compatibility check: any file type in the project that is
    # legitimate for the current category vetoes the move. e.g., Stock
    # Music with both .mp3 (compat) and .psd (cover art): keep it.
    counts = counts or Counter([detected_type])
    for t in counts:
        compat = COMPATIBLE_CATEGORY_PREFIXES.get(t, set())
        if current_category in compat or cat_prefix in compat:
            return None

    # Veto: folder name pins it to current category - skip auto-move.
    name_implies = folder_name_implies(folder_name)
    cat_lower_prefix = cat_prefix.lower()
    name_to_prefix = {
        "ae": "after effects", "ps": "photoshop", "prpro": "premiere pro",
        "ai": "illustrator", "id": "print", "3d": "3d", "font": "fonts",
        "web": "web",
    }
    for tok in name_implies:
        if name_to_prefix.get(tok, "") in cat_lower_prefix:
            return None

    # Auxiliary-only signals (video/image/audio) are weak; skip
    # auto-move and let the user review manually.
    if detected_type in AUXILIARY_TYPES:
        return None

    fallback = PREFIX_FALLBACK_CATEGORY.get(expected_top)
    if fallback and fallback in all_categories:
        return fallback
    candidates = [c for c in all_categories
                  if c.split(" - ", 1)[0] == expected_top]
    return candidates[0] if candidates else None


# ============================================================
# Filename English-ification
# ============================================================

# Unicode block ranges that indicate non-Latin text we should rename.
NON_LATIN_RANGES = [
    (0x0400, 0x04FF),   # Cyrillic
    (0x0500, 0x052F),   # Cyrillic Supplement
    (0x0590, 0x05FF),   # Hebrew
    (0x0600, 0x06FF),   # Arabic
    (0x0900, 0x097F),   # Devanagari
    (0x0E00, 0x0E7F),   # Thai
    (0x3040, 0x309F),   # Hiragana
    (0x30A0, 0x30FF),   # Katakana
    (0x3400, 0x4DBF),   # CJK Ext A
    (0x4E00, 0x9FFF),   # CJK
    (0xAC00, 0xD7AF),   # Hangul
    (0xF900, 0xFAFF),   # CJK Compatibility Ideographs
]


def has_non_ascii(s: str) -> bool:
    return any(ord(c) > 127 for c in s)


def has_non_latin_script(s: str) -> bool:
    for c in s:
        cp = ord(c)
        for lo, hi in NON_LATIN_RANGES:
            if lo <= cp <= hi:
                return True
    return False


# Mojibake from CJK-in-cp437/cp850 looks like sequences of box-drawing
# and extended-ASCII characters. Threshold: 3+ such chars.
MOJIBAKE_RANGES = [
    (0x00B0, 0x00FF),   # Latin-1 Supplement (heavy use suggests mojibake)
    (0x2500, 0x257F),   # Box-drawing
    (0x2580, 0x259F),   # Block elements
]


def looks_like_mojibake(s: str) -> bool:
    count = 0
    for c in s:
        cp = ord(c)
        for lo, hi in MOJIBAKE_RANGES:
            if lo <= cp <= hi:
                count += 1
                break
    return count >= 3


# Filenames that should NEVER be auto-renamed even when their words
# don't match the parent folder. These are legitimate auxiliary files
# (readmes, marketplace branding, generic media) that we want to leave
# alone. Match against the basename (stem + ext, lowercased).
KEEP_FILENAME_PATTERNS = [
    # Documentation
    re.compile(r"\bread[\s_-]*me\b", re.I),
    re.compile(r"\breadme\b", re.I),
    re.compile(r"\blicens(e|ing)\b", re.I),
    re.compile(r"\bagreement\b", re.I),
    re.compile(r"\bhelp\b", re.I),
    re.compile(r"\bdocumentation\b", re.I),
    re.compile(r"\bguide\b", re.I),
    re.compile(r"\binstructions?\b", re.I),
    re.compile(r"\bgetting[\s_-]+started\b", re.I),
    re.compile(r"\btutorial\b", re.I),
    re.compile(r"\bcredits?\b", re.I),
    re.compile(r"\bchangelog\b", re.I),
    re.compile(r"\bversion[\s_-]+history\b", re.I),
    re.compile(r"\bfont[\s_-]+links?\b", re.I),
    re.compile(r"\bfont[\s_-]+used\b", re.I),
    re.compile(r"\bfonts?[\s_-]+download\b", re.I),
    re.compile(r"\binstall(ation)?\b", re.I),
    re.compile(r"\bhow[\s_-]+to\b", re.I),
    # Marketplaces / brands / promo files
    re.compile(r"\bvideohive\b", re.I),
    re.compile(r"\benvato\b", re.I),
    re.compile(r"\bmotion\s*elements?\b", re.I),
    re.compile(r"\bintro[\s_-]+hd\b", re.I),
    re.compile(r"\brocketstock\b", re.I),
    re.compile(r"\bpremiumbeat\b", re.I),
    re.compile(r"\baudiojungle\b", re.I),
    re.compile(r"\bgraphicriver\b", re.I),
    re.compile(r"\bthemeforest\b", re.I),
    re.compile(r"\bcodecanyon\b", re.I),
    re.compile(r"\bplaceit\b", re.I),
    re.compile(r"\bmotion[\s_-]*array\b", re.I),
    re.compile(r"\buploaded[\s_-]+by\b", re.I),
    re.compile(r"\bget[\s_-]+more\b", re.I),
    # Generic content-pack files
    re.compile(r"^preview", re.I),
    re.compile(r"^demo", re.I),
    re.compile(r"^promo", re.I),
    re.compile(r"^sample", re.I),
    re.compile(r"^trailer", re.I),
    re.compile(r"^logo[._\s]", re.I),
    re.compile(r"^cover[._\s]", re.I),
    re.compile(r"^thumbnail[._\s]", re.I),
    re.compile(r"^thumb[._\s]", re.I),
    re.compile(r"^icon[._\s]", re.I),
    re.compile(r"^screenshot", re.I),
    re.compile(r"^facebook[._\s]", re.I),
    re.compile(r"^twitter[._\s]", re.I),
    re.compile(r"^instagram[._\s]", re.I),
    # Numeric-only filenames
    re.compile(r"^\d+$"),
    re.compile(r"^\d+_\d+$"),
]


def filename_should_keep(name: str) -> bool:
    """True if `name` matches any KEEP pattern - rename should skip it."""
    stem = Path(name).stem
    for rx in KEEP_FILENAME_PATTERNS:
        if rx.search(stem) or rx.search(name):
            return True
    return False


# Tokens we should preserve when grafting a file onto a new base name -
# variant markers, version strings, suffixes that distinguish siblings.
PRESERVE_TOKEN_RX = re.compile(
    r"\b("
    r"v\d+(?:\.\d+)?|"           # v2, v3.1
    r"\d+x\d+|"                  # 1920x1080, 4k
    r"hd|fullhd|4k|2k|"
    r"intro|outro|ending|preview|teaser|"
    r"bt|bts|behind|"            # "BT" in JinShu Daijishi BT.mp4
    r"part\d+|"
    r"final|draft|source|backup|"
    r"footage|preview|demo"
    r")\b",
    re.IGNORECASE,
)


def english_words_in(s: str) -> set[str]:
    """Return lowercase {word} for ASCII words >= 3 chars."""
    return {m.group(0).lower()
            for m in re.finditer(r"[A-Za-z]{3,}", s)}


def is_unambiguous_non_english(name: str) -> bool:
    """True if the filename is *clearly* non-English: contains non-Latin
    script characters or cp437/cp936 mojibake. Romanized CJK is handled
    separately via a cohort check, since single-file romanized stems
    can't be reliably distinguished from English words."""
    if filename_should_keep(name):
        return False
    if has_non_latin_script(name):
        return True
    if looks_like_mojibake(name):
        return True
    return False


def looks_romanized_token(tok: str) -> bool:
    """A single-word romanized-CJK signature: TitleCase, 3-12 chars,
    letters only, no English-y suffix. NOT a sufficient signal alone -
    use only as part of a cohort check across multiple files."""
    if not re.fullmatch(r"[A-Z][a-zA-Z]{2,11}", tok):
        return False
    # Common English endings that are very rare in pinyin/romaji
    if re.search(r"(tion|sion|ing|ed|er|ly|ous|ies|ness|ment|ity|"
                 r"able|ible|ful|less|al|ize|ise|ate|ish|ant|ent)$",
                 tok, re.I):
        return False
    return True


def looks_romanized_stem(stem: str) -> bool:
    """The whole stem looks like 1-4 romanized tokens (no English-y
    endings). Returns False for stems that include any plain-English-
    looking token."""
    tokens = [t for t in re.split(r"[\s_-]+", stem) if t]
    if not tokens or len(tokens) > 4:
        return False
    return all(looks_romanized_token(t) for t in tokens)


def find_foreign_cohort(folder_name: str,
                        files: list[Path]) -> set[Path]:
    """Return the set of files in this folder whose names should be
    renamed.

    Two signals trigger inclusion:
      A. Unambiguous non-English (non-Latin script or mojibake).
      B. *Cohort signal*: 2+ files share the same romanized-foreign-
         looking stem AND the folder has a clean English name (3+
         English words). Single-file romanized stems are skipped to
         avoid false positives like "Locations.aep" alone.
    """
    out: set[Path] = set()
    folder_words = english_words_in(folder_name)
    folder_is_english = len(folder_words) >= 3

    # Group by stem (case-insensitive) to find cohorts
    stem_groups: dict[str, list[Path]] = {}
    for f in files:
        stem = f.stem.lower()
        # Strip a trailing ` v2`, ` BT`, ` (1)` etc. so siblings group
        stripped = re.sub(
            r"\s*(?:v\d+(?:\.\d+)?|bt|bts|hd|fullhd|4k|2k|"
            r"part\d+|final|draft|footage|preview|demo|"
            r"\(\d+\))\s*$",
            "", stem, flags=re.I).strip()
        stem_groups.setdefault(stripped or stem, []).append(f)

    for stem_key, members in stem_groups.items():
        # Signal A: any member has unambiguous non-English signal -
        # rename ALL siblings sharing this stripped stem (so the project
        # converges on one English base).
        if any(is_unambiguous_non_english(m.name) for m in members):
            out.update(members)
            continue
        # Signal B: cohort of 2+ romanized siblings, folder is English.
        # Use ORIGINAL-CASE stem from a member (the lowercased key would
        # break the TitleCase test in looks_romanized_token).
        # Skip cohort if any member is a known auxiliary file (readme etc).
        if any(filename_should_keep(m.name) for m in members):
            continue
        if folder_is_english and len(members) >= 2:
            sample_stem = members[0].stem
            sample_stripped = re.sub(
                r"\s*(?:v\d+(?:\.\d+)?|bt|bts|hd|fullhd|4k|2k|"
                r"part\d+|final|draft|footage|preview|demo|"
                r"\(\d+\))\s*$",
                "", sample_stem, flags=re.I).strip()
            if looks_romanized_stem(sample_stripped):
                stem_words = english_words_in(stem_key)
                if not (stem_words & folder_words):
                    out.update(members)
    return out


def derive_english_name(file_path: Path, folder_name: str,
                        sibling_stems: list[str]) -> str:
    """Rename a non-English file to use folder_name as its base, while
    preserving any meaningful suffix tokens (BT, v2, _01, etc.).
    Returns the new filename (basename only)."""
    ext = file_path.suffix
    stem = file_path.stem

    # Try to identify a unique suffix - the part of this file's stem that
    # distinguishes it from siblings. We do this by finding the longest
    # common prefix among siblings; the part after that prefix is the
    # distinguishing token.
    if len(sibling_stems) > 1:
        common = os.path.commonprefix(sibling_stems)
        if common and len(common) > 2 and stem.startswith(common):
            tail = stem[len(common):].strip(" -_")
            if tail:
                # Keep tail if it's ASCII and short, otherwise drop
                if tail.isascii() and len(tail) <= 24:
                    return f"{folder_name} {tail}{ext}"

    # Look for a preserve-token anywhere in the original stem
    m = PRESERVE_TOKEN_RX.search(stem)
    if m and m.group(0).lower() not in folder_name.lower():
        return f"{folder_name} {m.group(0)}{ext}"

    return f"{folder_name}{ext}"


def safe_target(p: Path) -> Path:
    """Resolve naming collisions by appending (1), (2), ..."""
    if not p.exists():
        return p
    base = p.stem
    suffix = p.suffix
    i = 1
    while True:
        cand = p.parent / f"{base} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


# ============================================================
# Driver
# ============================================================

ARCHIVE_EXTS = {".zip", ".rar", ".7z"}
SKIP_DIR_NAMES = {".DS_Store", "__MACOSX", "Thumbs.db"}


def iter_projects(root: Path, only_category: str | None = None):
    """Yield (project_dir, category_name) for each subdir at depth 2."""
    categories = sorted(d for d in root.iterdir()
                        if d.is_dir() and d.name not in SKIP_DIR_NAMES)
    if only_category:
        categories = [c for c in categories if c.name == only_category]
    for cat in categories:
        try:
            entries = sorted(cat.iterdir())
        except (PermissionError, OSError):
            continue
        for proj in entries:
            if proj.is_dir() and proj.name not in SKIP_DIR_NAMES:
                yield proj, cat.name


def safe_print(*args):
    msg = " ".join(str(a) for a in args)
    sys.stdout.write(msg.encode("cp1252", errors="replace")
                     .decode("cp1252") + "\n")
    sys.stdout.flush()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--classify-only", action="store_true",
                    help="Only run misclassification stage")
    ap.add_argument("--rename-only", action="store_true",
                    help="Only run filename English-ification stage")
    ap.add_argument("--category", default=None,
                    help="Only audit this single category")
    ap.add_argument("--report",
                    default=str(Path(__file__).parent / "audit_report.json"),
                    help="Write findings to this JSON path")
    args = ap.parse_args()
    if not (args.scan or args.apply):
        ap.print_help(); return

    root = Path(args.root)
    if not root.is_dir():
        safe_print(f"root not found: {root}"); sys.exit(1)
    apply = args.apply
    do_classify = not args.rename_only
    do_rename = not args.classify_only

    all_categories = sorted(d.name for d in root.iterdir()
                            if d.is_dir() and d.name not in SKIP_DIR_NAMES)

    moves: list[dict] = []
    renames: list[dict] = []
    project_count = 0
    no_project_file = []

    for proj, cat in iter_projects(root, args.category):
        project_count += 1
        if project_count % 250 == 0:
            safe_print(f"  ... scanned {project_count} projects")

        # ---- Stage 1: misclassification
        target_cat = None
        if do_classify:
            detected, counts = detect_project_type(proj)
            target_cat = find_correct_category(detected, cat, all_categories,
                                               proj.name, counts)
            if detected is None:
                no_project_file.append(str(proj))
            if target_cat:
                moves.append({
                    "project": str(proj),
                    "from_category": cat,
                    "to_category": target_cat,
                    "detected_type": detected,
                    "ext_counts": dict(counts.most_common(5)),
                })

        # The destination dir for stage 2 is wherever the project will live
        # after stage 1 (so renames target the post-move dir if applied).
        proj_after_move = (root / target_cat / proj.name) if target_cat else proj

        # ---- Stage 2: foreign filenames
        if do_rename:
            try:
                inner = list(proj.iterdir())
            except (PermissionError, OSError):
                continue
            files = [p for p in inner if p.is_file()
                     and p.suffix.lower() not in ARCHIVE_EXTS]
            cohort = find_foreign_cohort(proj.name, files)
            sibling_stems = [p.stem for p in files]
            for f in cohort:
                new_name = derive_english_name(f, proj.name, sibling_stems)
                if new_name == f.name:
                    continue
                renames.append({
                    "from": str(f),
                    "to_name": new_name,
                    "project": str(proj),
                    "project_after_move": str(proj_after_move),
                })

    # ---- Report
    safe_print(f"\n=== AUDIT REPORT ({project_count} projects scanned) ===")
    safe_print(f"  misclassified projects: {len(moves)}")
    safe_print(f"  foreign filenames:      {len(renames)}")
    safe_print(f"  projects with no project-file detected: {len(no_project_file)}")

    if moves[:10]:
        safe_print("\n  sample misclassifications:")
        for m in moves[:10]:
            safe_print(f"    [{m['detected_type']:>10s}] "
                       f"{Path(m['project']).name}: "
                       f"{m['from_category']!r} -> {m['to_category']!r}")
    if renames[:10]:
        safe_print("\n  sample renames:")
        for r in renames[:10]:
            safe_print(f"    {Path(r['from']).name!r} -> {r['to_name']!r}")

    Path(args.report).write_text(
        json.dumps({"moves": moves, "renames": renames,
                    "no_project_file_count": len(no_project_file)},
                   indent=2, ensure_ascii=False),
        encoding="utf-8")
    safe_print(f"\n  full report: {args.report}")

    if not apply:
        return

    # ---- Apply
    safe_print("\n=== APPLYING ===")
    moves_done = 0
    for m in moves:
        src = Path(m["project"])
        target_cat_dir = root / m["to_category"]
        target_cat_dir.mkdir(parents=True, exist_ok=True)
        dst = target_cat_dir / src.name
        if dst.exists() and dst != src:
            dst = safe_target(dst)
        try:
            # same-drive move via os.rename (metadata-only, fast)
            os.rename(str(src), str(dst))
            moves_done += 1
            m["dst"] = str(dst)
            if moves_done % 50 == 0:
                safe_print(f"  moved {moves_done}/{len(moves)}")
        except OSError as e:
            try:
                shutil.move(str(src), str(dst))
                moves_done += 1
                m["dst"] = str(dst)
            except Exception as e2:
                safe_print(f"  ERR move {src.name}: {e2}")

    renames_done = 0
    for r in renames:
        # Resolve the post-move location of the project
        old_proj = Path(r["project"])
        proj_now = Path(r["project_after_move"])
        if not proj_now.exists():
            # Project dir didn't move (no stage-1 fix); use original
            proj_now = old_proj
        if not proj_now.exists():
            continue
        old_path = proj_now / Path(r["from"]).name
        if not old_path.exists():
            # File path may have moved with the project move
            old_path = Path(r["from"])
            if not old_path.exists():
                continue
        new_path = old_path.parent / r["to_name"]
        if new_path.exists() and new_path != old_path:
            new_path = safe_target(new_path)
        try:
            os.rename(str(old_path), str(new_path))
            renames_done += 1
            r["dst"] = str(new_path)
        except OSError as e:
            safe_print(f"  ERR rename {old_path.name}: {e}")

    safe_print(f"\nmoved   {moves_done}/{len(moves)}")
    safe_print(f"renamed {renames_done}/{len(renames)}")

    Path(args.report).write_text(
        json.dumps({"moves": moves, "renames": renames,
                    "applied": True,
                    "moves_done": moves_done,
                    "renames_done": renames_done,
                    "no_project_file_count": len(no_project_file)},
                   indent=2, ensure_ascii=False),
        encoding="utf-8")


if __name__ == "__main__":
    main()
