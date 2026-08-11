#!/usr/bin/env python3
"""Agentic organization runner — applies classified items to destination.

Usage:
    python organize_run.py --preview            # dry run all batches
    python organize_run.py --apply              # apply all batches
    python organize_run.py --preview --load F   # dry run single file
    python organize_run.py --preview --plan-out plan.json
    python organize_run.py --apply-plan plan.json
    python organize_run.py --report RUN_ID --output report.md
    python organize_run.py --validate           # pre-flight: find trailing spaces + long paths
    python organize_run.py --stats              # show batch progress
    python organize_run.py --summary            # category breakdown
    python organize_run.py --preview --rename   # opt-in canonical batch names
    python organize_run.py --retry-errors       # retry only previously errored items
    python organize_run.py --undo-last N        # reverse the last N moves (from journal)
    python organize_run.py --undo-all           # reverse all moves in journal

Known edge cases handled:
    - Trailing spaces in file/folder names (WinError 2) → pre-sanitized before move
    - Deep Unicode paths >260 chars (WinError 3) → robocopy with /256 long-path support
    - Cross-drive moves use robocopy for reliability; os.rename for same-drive
    - shutil.move NEVER deletes source on copy failure (safe), but leaves partial dests
    - Every planned/applied move is journaled to organize_moves.db for full undo support
    - Errors logged to organize_errors.json for retry/audit
"""
import os, sys, json, shutil, re, argparse, subprocess, sqlite3, hashlib, ntpath
from pathlib import Path
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from types import ModuleType

from fileorganizer.path_safety import (
    PathSafetyError, canonical_path, is_within, validate_move,
)
from fileorganizer.folder_cache import FolderCache, should_skip_folder
from fileorganizer.rule_chains import RuleChainManager
from fileorganizer.batch_rename import CANONICAL_TEMPLATE, render_name

# ── Config ────────────────────────────────────────────────────────────────────
DEST_PRIMARY     = r'G:\Organized'
DEST_OVERFLOW    = r'I:\Organized'   # used automatically when G:\ free < MIN_FREE_GB
MIN_FREE_GB      = 50
_FORCE_OVERFLOW  = False             # set True via --overflow-now CLI flag
REVIEW_SUBDIR    = '_Review'       # low-confidence items land here
# MIN_CONFIDENCE is loaded from user settings (Design Workflow -> Classification Thresholds).
# Default 50 is used when the GUI has never been opened / settings file is absent.
def _load_min_confidence() -> int:
    try:
        import sys as _sys, os as _os
        _pkg = _os.path.join(_os.path.dirname(__file__), 'fileorganizer')
        if _pkg not in _sys.path:
            _sys.path.insert(0, _os.path.dirname(__file__))
        from fileorganizer.config import load_confidence_settings
        return int(load_confidence_settings()['review_below'])
    except Exception:
        return 50
MIN_CONFIDENCE   = _load_min_confidence()

# ── AE / Unorganized source (Phase 1) ────────────────────────────────────────
AE_BATCH_SIZE    = 60              # items per AE batch (batches 1-18 = 60, batch 19 = 56)
AE_TOTAL         = 1136            # total After Effects items in org_index
INDEX_FILE       = os.path.join(os.path.dirname(__file__), 'org_index.json')

# ── Design source (Phase 2: G:\Design Unorganized) ───────────────────────────
DESIGN_BATCH_SIZE = 60
DESIGN_INDEX_FILE = os.path.join(os.path.dirname(__file__), 'design_unorg_index.json')

LOG_FILE         = os.path.join(os.path.dirname(__file__), 'organize_run.log')
ERRORS_FILE      = os.path.join(os.path.dirname(__file__), 'organize_errors.json')  # legacy path
JOURNAL_FILE     = os.path.join(os.path.dirname(__file__), 'organize_moves.db')
RESULTS_DIR      = os.path.join(os.path.dirname(__file__), 'classification_results')
PLANS_DIR        = os.path.join(os.path.dirname(__file__), 'organize_plans')
REPORTS_DIR      = os.path.join(os.path.dirname(__file__), 'organize_reports')
PLAN_SCHEMA_VERSION = 2
os.makedirs(RESULTS_DIR, exist_ok=True)

def errors_file(source_mode: str) -> str:
    """Return source-specific errors file path so concurrent apply runs don't clobber each other."""
    return os.path.join(os.path.dirname(__file__), f'organize_errors_{source_mode}.json')

# ── Category name normalization ──────────────────────────────────────────────
# Canonical names (right-hand side).  Any batch that returns a left-hand key
# will be silently rewritten before the destination path is computed.
# This handles cross-batch inconsistencies (AE vs Design classifiers used
# slightly different names for the same category).
CATEGORY_ALIASES = {
    # word-order variant from the AE classifier
    'After Effects - Opener & Intro':   'After Effects - Intro & Opener',
    # old short names — "Title & Typography" is the canonical form
    'After Effects - Typography':       'After Effects - Title & Typography',
    'After Effects - Titles & Typography': 'After Effects - Title & Typography',
    # flat names returned by older AE batches for categories with subtypes
    'Business & Marketing':             'After Effects - Corporate & Business',
    'Holiday & Seasonal':               'After Effects - Christmas & Holiday',
    'Motion Graphics & VFX':            'After Effects - Motion Graphics Pack',
    'Services & Industries':            'After Effects - Corporate & Business',
    'Sport & Recreation':               'After Effects - Sport & Action',
    'Food & Lifestyle':                 'After Effects - Product Promo',
    'Design Tools & Resources':         'Plugins & Extensions',
    'Audio Resources':                  'Stock Music & Audio',
    'Video Editing - General':          'After Effects - Other',
    # G:\Stock bucket category — maps to general stock footage
    'Stock Footage & Photos':           'Stock Footage - General',
    # Photoshop aliases (from older reclassify batches)
    'Photoshop - Templates & Mockups':  'Photoshop - Smart Objects & Templates',
    'Photoshop - Social Media':         'Photoshop - Smart Objects & Templates',
    'Print - Templates & Layouts':      'Print - Other',
    # ── Phantom categories generated by buggy prior-AI runs (audit 2026-04-28).
    # All of these existed as folders on disk; they're rewritten at apply time
    # so future moves never re-create them.
    'After Effects - Promo & Advertising': 'After Effects - Product Promo',
    'After Effects - Photo Slideshow':     'After Effects - Slideshow',
    'After Effects - CINEPUNCH.V20':       'After Effects - Motion Graphics Pack',
    'After Effects - Slideshows':          'After Effects - Slideshow',
    'After Effects - Logo Reveals':        'After Effects - Logo Reveal',
    'After Effects - Intros & Openers':    'After Effects - Intro & Opener',
    'After Effects - Transitions':         'After Effects - Transition Pack',
    'After Effects - Wedding & Events':    'After Effects - Wedding & Romance',
    'After Effects - Templates':           'After Effects - Other',
    'After Effects - Character Animation': 'After Effects - Character & Explainer',
    'After Effects - Countdown & Timer':   'After Effects - Other',
    'After Effects - Emoji & Stickers':    'After Effects - Other',
    'After Effects - Explainer & Promo':   'After Effects - Character & Explainer',
    'After Effects - HUD & UI':            'After Effects - 3D & Particle',
    'After Effects - Infographics & Data': 'After Effects - Infographic & Data Viz',
    'After Effects - Lyric Video':         'After Effects - Lyric & Music Video',
    'After Effects - Particles & FX':      'After Effects - 3D & Particle',
    'After Effects - Photo & Gallery':     'After Effects - Photo Album & Gallery',
    'After Effects - Presets & Scripts':   'After Effects - Preset Pack',
    'After Effects - Social Media Templates': 'After Effects - Social Media',
    'Photoshop - Print & Stationery':      'Print - Business Cards & Stationery',
    'Photoshop - Social Media Templates':  'Print - Social Media Graphics',
    'Illustrator - Logos & Branding':      'Illustrator - Vectors & Assets',
    'After Effects - Backgrounds':         'After Effects - News & Broadcast',
    'After Effects - Elements':            'After Effects - Motion Graphics Pack',
    'After Effects - Film Grain & Overlays':'Cinematic FX & Overlays',
    'After Effects - Overlay & Transition':'After Effects - Transition Pack',
    'After Effects - Motion Graphics':     'After Effects - Motion Graphics Pack',
    'Cinematic FX':                        'Cinematic FX & Overlays',
    # legacy I:\Organized library top-level folder names (pre-Phase-4)
    'Mockups - Branding':                  'Mockups - Branding & Stationery',
    'Mockups - Devices':                   'Mockups - Devices & Screens',
    'Mockups - Print':                     'Mockups - Print & Signage',
    'Mockups - Signage':                   'Mockups - Print & Signage',
    'InDesign - Magazine & Editorial':     'Print - Brochures & Books',
    'InDesign - Print Templates':          'Print - Other',
    'Audio Visualizer':                    'After Effects - Music & Audio Visualizer',
    'Animated Backgrounds':                'After Effects - Other',
    'Animated Elements':                   'After Effects - Motion Graphics Pack',
    'Animated Icons':                      'UI Resources & Icon Sets',
    'Animated GIFs & Cinemagraphs':        'Stock Footage - General',
    'Light & Lens FX':                     'Cinematic FX & Overlays',
    'Glitch & Distortion FX':              'After Effects - Glitch & Distortion',
    'Fire & Explosion FX':                 'Cinematic FX & Overlays',
    'Cinematic Effects':                   'Cinematic FX & Overlays',
    'Drone & Aerial Video':                'Stock Footage - Aerial & Drone',
    'Kinetic Typography':                  'After Effects - Title & Typography',
    'Countdown & Numbers':                 'After Effects - Other',
    'Call-Outs & Pointers':                'After Effects - Other',
    'Maps & Cartography':                  'After Effects - Map & Location',
    'Brushes & Presets':                   'Photoshop - Brushes',
    'Backgrounds & Textures':              'Photoshop - Patterns & Textures',
    'Frame & Border':                      'Photoshop - Other',
    'Frames & Borders':                    'Photoshop - Other',
    'Branding & Identity Kits':            'Mockups - Branding & Stationery',
    'Logo & Identity':                     'Illustrator - Vectors & Assets',
    'Badges & Emblems':                    'Illustrator - Vectors & Assets',
    'Clipart & Illustrations':             'Illustrator - Vectors & Assets',
    'Icons & Symbols':                     'UI Resources & Icon Sets',
    'Buttons & UI Elements':               'UI Resources & Icon Sets',
    'Mobile App Design':                   'UI Resources & Icon Sets',
    'Font Collections':                    'Fonts & Typography',
    'Fonts - Display & Decorative':        'Fonts & Typography',
    'Fonts - Sans Serif':                  'Fonts & Typography',
    'Fonts - Script & Handwritten':        'Fonts & Typography',
    'Flyers & Print':                      'Print - Flyers & Posters',
    'Posters':                             'Print - Flyers & Posters',
    'Banners':                             'Print - Flyers & Posters',
    'Billboard':                           'Print - Flyers & Posters',
    'Business Cards':                      'Print - Business Cards & Stationery',
    'Letterhead & Stationery':             'Print - Business Cards & Stationery',
    'Brochures & Bi-Fold & Tri-Fold':      'Print - Brochures & Books',
    'Annual Report':                       'Print - Brochures & Books',
    'Book & Literature':                   'Print - Brochures & Books',
    'Menu Design':                         'Print - Brochures & Books',
    'Food & Menu':                         'Print - Brochures & Books',
    'Calendar':                            'Print - Other',
    'Certificate':                         'Print - Other',
    'Resume & CV':                         'Print - Other',
    'Forms & Documents':                   'Print - Other',
    'Gift Voucher & Coupon':               'Print - Other',
    'Invitations & Save the Date':         'Print - Invitations & Events',
    'Anniversary':                         'Print - Invitations & Events',
    'Bachelor & Bachelorette':             'Print - Invitations & Events',
    'Wedding':                             'Print - Invitations & Events',
    'Birthday':                            'Print - Invitations & Events',
    'Graduation & Prom':                   'Print - Invitations & Events',
    'Funeral & Memorial':                  'Print - Invitations & Events',
    'Baby & Newborn':                      'Print - Invitations & Events',
    'Party & Celebration':                 'Print - Invitations & Events',
    'Events & Occasions':                  'Print - Invitations & Events',
    'Holidays & Seasonal':                 'Print - Invitations & Events',
    'Christmas':                           'Print - Invitations & Events',
    'Halloween':                           'Print - Invitations & Events',
    'Easter':                              'Print - Invitations & Events',
    'Black Friday':                        'Print - Flyers & Posters',
    'Cyber Monday':                        'Print - Flyers & Posters',
    'Fathers Day':                         'Print - Invitations & Events',
    'Mothers Day':                         'Print - Invitations & Events',
    'Valentines Day':                      'Print - Invitations & Events',
    'New Year':                            'Print - Invitations & Events',
    'Thanksgiving':                        'Print - Invitations & Events',
    'Chinese & Lunar New Year':            'Print - Invitations & Events',
    'Cinco de Mayo':                       'Print - Invitations & Events',
    'Canada Day':                          'Print - Invitations & Events',
    'Black History Month':                 'Print - Invitations & Events',
    'Carnival & Mardi Gras':               'Print - Invitations & Events',
    'Kentucky Derby':                      'Print - Invitations & Events',
    'Labor Day':                           'Print - Invitations & Events',
    'Cancer Awareness':                    'Print - Invitations & Events',
    'COVID-19':                            'Print - Flyers & Posters',
    'Black Party & Dark Themes':           'Print - Flyers & Posters',
    'Girls Night & Ladies Night':          'Print - Flyers & Posters',
    'Gay & LGBT Pride':                    'Print - Flyers & Posters',
    'Concert & Live Music':                'Print - Flyers & Posters',
    'Festival':                            'Print - Flyers & Posters',
    'Conference & Summit':                 'Print - Flyers & Posters',
    'Awards & Ceremonies':                 'Print - Flyers & Posters',
    'Election & Political':                'Print - Flyers & Posters',
    'Charity & Fundraiser':                'Print - Flyers & Posters',
    'Grand Opening':                       'Print - Flyers & Posters',
    'Garage Sale & Yard Sale':             'Print - Flyers & Posters',
    'Auction':                             'Print - Flyers & Posters',
    'Family':                              'Print - Invitations & Events',
    'Children & Kids':                     'Print - Invitations & Events',
    'Dating & Romance':                    'Print - Invitations & Events',
    'Sports':                              'Print - Flyers & Posters',
    'Boxing & MMA':                        'Print - Flyers & Posters',
    'Bike & Cycling':                      'Print - Flyers & Posters',
    'Golf':                                'Print - Flyers & Posters',
    'Fishing':                             'Print - Flyers & Posters',
    'Diving & Water Sports':               'Print - Flyers & Posters',
    'Dance':                               'Print - Flyers & Posters',
    'Comedy & Standup':                    'Print - Flyers & Posters',
    'Cabaret & Burlesque':                 'Print - Flyers & Posters',
    'Bar & Nightlife':                     'Print - Flyers & Posters',
    'Beer & Alcohol':                      'Print - Flyers & Posters',
    'Cafe & Restaurant':                   'Print - Flyers & Posters',
    'Bakery & Pastry':                     'Print - Flyers & Posters',
    'Cooking & Grill':                     'Print - Flyers & Posters',
    'Beauty, Fashion & Spa':               'Print - Flyers & Posters',
    'Fitness & Gym':                       'Print - Flyers & Posters',
    'Dentist & Dental':                    'Print - Flyers & Posters',
    'Health & Medical':                    'Print - Flyers & Posters',
    'Lawn Care & Landscaping':             'Print - Flyers & Posters',
    'Cleaning Service':                    'Print - Flyers & Posters',
    'Handyman & Home Repair':              'Print - Flyers & Posters',
    'Insurance':                           'Print - Flyers & Posters',
    'Accounting & Finance':                'Print - Flyers & Posters',
    'Call Center & Support':               'Print - Flyers & Posters',
    'Computer & IT Services':              'Print - Flyers & Posters',
    'Cab & Taxi':                          'Print - Flyers & Posters',
    'Car & Auto':                          'Print - Flyers & Posters',
    'Boat & Yacht':                        'Print - Flyers & Posters',
    'Aircraft & Aviation':                 'Print - Flyers & Posters',
    'Architecture & Construction':         'Print - Flyers & Posters',
    'Agriculture & Farming':               'Print - Flyers & Posters',
    'Education & School':                  'Print - Flyers & Posters',
    'Florist & Flowers':                   'Print - Flyers & Posters',
    'Furniture & Interior':                'Print - Flyers & Posters',
    'Clothing & Apparel':                  'Print - Flyers & Posters',
    'Electronics & Technology':            'Print - Flyers & Posters',
    'Alternative Energy':                  'Print - Flyers & Posters',
    'Art & Photography':                   'Print - Flyers & Posters',
    'Astrology & Zodiac':                  'Print - Flyers & Posters',
    'Africa & Afro':                       'Print - Flyers & Posters',
    'Arabian & Middle Eastern':            'Print - Flyers & Posters',
    'Church & Gospel':                     'Print - Flyers & Posters',
    'Dating & Romance':                    'Print - Invitations & Events',
    'Documentary':                         'Print - Flyers & Posters',
    'Cinema & Film':                       'Print - Flyers & Posters',
    'Entertainment':                       'Print - Flyers & Posters',
    'Erotic & Adult':                      'Print - Flyers & Posters',
    'Club & DJ':                           'Print - Flyers & Posters',
    'Circus':                              'Print - Flyers & Posters',
    'City & Urban':                        'Print - Flyers & Posters',
    'Beach & Coastal':                     'Print - Flyers & Posters',
    'Community':                           'Print - Flyers & Posters',
    'Indie & Alternative':                 'Print - Flyers & Posters',
    'Games & Gaming':                      'Print - Flyers & Posters',
    'Travel & Tourism':                    'Print - Flyers & Posters',
    'Business & Corporate':                'Print - Flyers & Posters',
    'Advertising & Marketing':             'Print - Flyers & Posters',
    'Ad & Banner Design':                  'Print - Flyers & Posters',
    'Email & Newsletter':                  'Print - Flyers & Posters',
    'Blog & Content':                      'Print - Flyers & Posters',
    'Covers & Headers':                    'Print - Social Media Graphics',
    'Facebook & Social Covers':            'Print - Social Media Graphics',
    'Instagram & Stories':                 'Print - Social Media Graphics',
    'Infographic':                         'Print - Other',
    'Black & White Photography':           'Stock Photos - General',
    'Macro & Close-Up':                    'Stock Photos - General',
    'Flat Lay & Styled Photography':       'Stock Photos - General',
    'Abstract':                            'Stock Footage - Abstract & VFX',
    '3D':                                  '3D - Models & Objects',
    'Masks':                               'Photoshop - Other',
    'Flat Design':                         'Illustrator - Vectors & Assets',
    'Isometric Design':                    'Illustrator - Vectors & Assets',
    'Minimal & Clean':                     'Print - Flyers & Posters',
    'Elegant & Luxury':                    'Print - Flyers & Posters',
    'Grunge & Distressed':                 'Photoshop - Patterns & Textures',
    'Gold & Metallic':                     'Photoshop - Styles & Layer Effects',
    'Graffiti & Street Art':               'Print - Flyers & Posters',
    'Futuristic & Sci-Fi':                 'Print - Flyers & Posters',
    'Flags & Patriotic':                   'Print - Flyers & Posters',
    'Fire & Fireworks':                    'Cinematic FX & Overlays',
    'Design Inspiration Packs':            'Print - Flyers & Posters',
    # ── round 2 of legacy aliases (auto-discovered by fix_phantom_categories --scan) ──
    'Motion Graphics':                     'After Effects - Motion Graphics Pack',
    'Multipurpose':                        'Print - Other',
    'Music':                               'Stock Music & Audio',
    'Music - Ambient & Chill':             'Stock Music & Audio',
    'Music - Cinematic & Orchestral':      'Stock Music & Audio',
    'Music - Corporate & Upbeat':          'Stock Music & Audio',
    'Music - Electronic & EDM':            'Stock Music & Audio',
    'Music - Loops & Beats':               'Stock Music & Audio',
    'Nature & Weather FX':                 'Cinematic FX & Overlays',
    'Olympic Games':                       'Print - Flyers & Posters',
    'Overlays & Effects':                  'Cinematic FX & Overlays',
    'Packaging & Product':                 'Mockups - Packaging',
    'Parallax & Ken Burns':                'After Effects - Slideshow',
    'Patterns - Seamless':                 'Photoshop - Patterns & Textures',
    'Photography Presets & Actions':       'Photoshop - Actions & Presets',
    'Photoshop - Actions':                 'Photoshop - Actions & Presets',
    'Photoshop - Overlays':                'Photoshop - Overlays & FX',
    'Photoshop - Patterns':                'Photoshop - Patterns & Textures',
    'Photoshop - Retouching & Skin':       'Photoshop - Actions & Presets',
    'Photoshop - Smart Objects & PSDs':    'Photoshop - Smart Objects & Templates',
    'Photoshop - Styles & Effects':        'Photoshop - Styles & Layer Effects',
    'Photoshop - Templates & Composites':  'Photoshop - Smart Objects & Templates',
    'Pinterest':                           'Print - Social Media Graphics',
    'Pizza & Italian':                     'Print - Flyers & Posters',
    'PNG - Transparent Assets':            'Photoshop - Other',
    'Podcast & Voiceover':                 'Stock Music & Audio',
    'Poker & Casino':                      'Print - Flyers & Posters',
    'Polar Plunge':                        'Print - Flyers & Posters',
    'Pool Party':                          'Print - Invitations & Events',
    'Portrait Photography':                'Stock Photos - General',
    'Postcards':                           'Print - Invitations & Events',
    'Premiere Pro - LUTs & Color':         'Premiere Pro - LUTs & Color Grading',
    'Premiere Pro - Titles & Text':        'Premiere Pro - Title & Typography',
    'Presentations & PowerPoint':          'Print - Brochures & Books',
    'Product Photography':                 'Stock Photos - General',
    'Quotes & Motivational':               'Print - Social Media Graphics',
    'Real Estate':                         'Print - Flyers & Posters',
    'Retirement':                          'Print - Invitations & Events',
    'Retro & Vintage':                     'Photoshop - Patterns & Textures',
    'Reveal & Unveil Animations':          'After Effects - Logo Reveal',
    'Ribbon & Banner Animations':          'After Effects - Other',
    'Ribbons & Labels':                    'Photoshop - Other',
    'Rollup Banners & Signage':            'Mockups - Print & Signage',
    'Saint Patricks Day':                  'Print - Invitations & Events',
    'Shapes & Geometric':                  'Illustrator - Vectors & Assets',
    'Shop & Retail':                       'Print - Flyers & Posters',
    'Silhouettes':                         'Illustrator - Vectors & Assets',
    'Social Media':                        'Print - Social Media Graphics',
    'Speed & Action FX':                   'Cinematic FX & Overlays',
    'Stock Photos - People & Portraits':   'Stock Photos - General',
    'Stop Motion':                         'Stock Footage - General',
    'Summer & Tropical':                   'Print - Flyers & Posters',
    'Text Effects & Styles':               'Photoshop - Styles & Layer Effects',
    'Timelapse & Hyperlapse':              'Stock Footage - Timelapse',
    'Twitch & Streaming':                  'Print - Social Media Graphics',
    'UI & UX Design':                      'UI Resources & Icon Sets',
    'Vectors & SVG':                       'Illustrator - Vectors & Assets',
    'Watercolor & Artistic':               'Photoshop - Patterns & Textures',
    'Website Design':                      'Web Template',
    'Womens Day':                          'Print - Invitations & Events',
    'Yoga & Meditation':                   'Print - Flyers & Posters',
    'YouTube & Video Platform':            'Print - Social Media Graphics',
}

# "Web Template - <subcat>" → "Web Template" (only top-level is canonical)
def _web_template_collapse(cat: str) -> str:
    if cat.startswith('Web Template -'):
        return 'Web Template'
    return cat

def normalize_category(cat: str) -> str:
    """Return the canonical category name, resolving any known alias."""
    return CATEGORY_ALIASES.get(cat, _web_template_collapse(cat))

# ── Logging ───────────────────────────────────────────────────────────────────
def log(msg, also_print=True):
    ts = datetime.now().strftime('%H:%M:%S')
    line = f"[{ts}] {msg}"
    if also_print:
        # Encode to cp1252 safely (replace unmappable chars) for Windows consoles
        print(line.encode('cp1252', errors='replace').decode('cp1252'))
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(line + '\n')

# ── Moves journal (SQLite) ────────────────────────────────────────────────────
_JOURNAL_SCHEMA = """
CREATE TABLE IF NOT EXISTS moves (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src         TEXT NOT NULL,
    dest        TEXT NOT NULL,
    disk_name   TEXT NOT NULL,
    clean_name  TEXT,
    category    TEXT,
    confidence  INTEGER,
    moved_at    TEXT NOT NULL,
    undone_at   TEXT,
    plan_id     TEXT,
    plan_item_id TEXT,
    run_id      TEXT,
    status      TEXT DEFAULT 'done',
    error       TEXT,
    planned_at  TEXT,
    updated_at  TEXT,
    partial_dest_exists INTEGER DEFAULT 0,
    duplicate_source_file TEXT,
    duplicate_existing_file TEXT,
    duplicate_sha256 TEXT,
    source_root TEXT,
    dest_root TEXT,
    source_signature TEXT,
    provenance_id TEXT,
    provenance_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_moves_moved_at ON moves(moved_at);
CREATE INDEX IF NOT EXISTS idx_moves_undone   ON moves(undone_at);
"""

_JOURNAL_MIGRATIONS = {
    'plan_id': "ALTER TABLE moves ADD COLUMN plan_id TEXT",
    'plan_item_id': "ALTER TABLE moves ADD COLUMN plan_item_id TEXT",
    'run_id': "ALTER TABLE moves ADD COLUMN run_id TEXT",
    'status': "ALTER TABLE moves ADD COLUMN status TEXT DEFAULT 'done'",
    'error': "ALTER TABLE moves ADD COLUMN error TEXT",
    'planned_at': "ALTER TABLE moves ADD COLUMN planned_at TEXT",
    'updated_at': "ALTER TABLE moves ADD COLUMN updated_at TEXT",
    'partial_dest_exists': "ALTER TABLE moves ADD COLUMN partial_dest_exists INTEGER DEFAULT 0",
    'duplicate_source_file': "ALTER TABLE moves ADD COLUMN duplicate_source_file TEXT",
    'duplicate_existing_file': "ALTER TABLE moves ADD COLUMN duplicate_existing_file TEXT",
    'duplicate_sha256': "ALTER TABLE moves ADD COLUMN duplicate_sha256 TEXT",
    'source_root': "ALTER TABLE moves ADD COLUMN source_root TEXT",
    'dest_root': "ALTER TABLE moves ADD COLUMN dest_root TEXT",
    'source_signature': "ALTER TABLE moves ADD COLUMN source_signature TEXT",
    'provenance_id': "ALTER TABLE moves ADD COLUMN provenance_id TEXT",
    'provenance_json': "ALTER TABLE moves ADD COLUMN provenance_json TEXT",
}

def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')

def _compact_timestamp() -> str:
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def _ensure_journal_columns(con: sqlite3.Connection):
    existing = {row[1] for row in con.execute("PRAGMA table_info(moves)").fetchall()}
    for column, sql in _JOURNAL_MIGRATIONS.items():
        if column not in existing:
            con.execute(sql)
    con.execute("UPDATE moves SET status='done' WHERE status IS NULL OR status=''")
    con.execute("CREATE INDEX IF NOT EXISTS idx_moves_status ON moves(status)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_moves_plan_id ON moves(plan_id)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_moves_run_id ON moves(run_id)")

def _journal_conn() -> sqlite3.Connection:
    con = sqlite3.connect(JOURNAL_FILE)
    con.row_factory = sqlite3.Row
    con.executescript(_JOURNAL_SCHEMA)
    _ensure_journal_columns(con)
    con.commit()
    return con

def journal_record(src: str, dest: str, disk_name: str,
                   clean_name: str, category: str, confidence: int,
                   status: str = 'done', plan_id: str = '',
                   plan_item_id: str = '', run_id: str = '',
                   error: str = '', partial_dest_exists: bool = False,
                   duplicate_source_file: str = '',
                   duplicate_existing_file: str = '',
                   duplicate_sha256: str = '', source_root: str = '',
                   dest_root: str = '', source_signature: dict | None = None,
                   provenance: dict | None = None) -> int:
    """Record a planned/completed move in the SQLite journal and return its row id."""
    now = _utc_now()
    con = _journal_conn()
    cur = con.execute(
        "INSERT INTO moves (src, dest, disk_name, clean_name, category, confidence, moved_at, "
        "plan_id, plan_item_id, run_id, status, error, planned_at, updated_at, partial_dest_exists, "
        "duplicate_source_file, duplicate_existing_file, duplicate_sha256, source_root, dest_root, source_signature, "
        "provenance_id, provenance_json) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (src, dest, disk_name, clean_name, category, confidence, now,
         plan_id, plan_item_id, run_id, status, error, now, now, int(partial_dest_exists),
         duplicate_source_file, duplicate_existing_file, duplicate_sha256,
         source_root, dest_root, json.dumps(source_signature or {}, sort_keys=True),
         str((provenance or {}).get('record_id', '') or ''),
         json.dumps(provenance or {}, sort_keys=True))
    )
    con.commit()
    row_id = cur.lastrowid
    con.close()
    return row_id

def journal_update(move_id: int, status: str, error: str = '',
                   partial_dest_exists: bool = False):
    """Update a journal row status after a plan item succeeds or fails."""
    con = _journal_conn()
    con.execute(
        "UPDATE moves SET status=?, error=?, updated_at=?, partial_dest_exists=? WHERE id=?",
        (status, error, _utc_now(), int(partial_dest_exists), move_id)
    )
    con.commit()
    con.close()

def journal_src_exists(src: str) -> bool:
    """Return True if this source path is already recorded as moved (not undone)."""
    if not os.path.exists(JOURNAL_FILE):
        return False
    con = _journal_conn()
    row = con.execute(
        "SELECT 1 FROM moves WHERE src = ? AND undone_at IS NULL "
        "AND COALESCE(status, 'done') IN ('pending', 'done') LIMIT 1", (src,)
    ).fetchone()
    con.close()
    return row is not None

def journal_src_set() -> set:
    """Return a set of all src paths already moved (not undone) — for bulk skip checks."""
    if not os.path.exists(JOURNAL_FILE):
        return set()
    con = _journal_conn()
    rows = con.execute(
        "SELECT src FROM moves WHERE undone_at IS NULL "
        "AND COALESCE(status, 'done') IN ('pending', 'done')"
    ).fetchall()
    con.close()
    return {r[0] for r in rows}

def undo_moves(last_n: int = 0, dry_run: bool = False) -> dict:
    """
    Reverse moves recorded in the journal.
    last_n=0 reverses ALL un-undone moves (newest first).
    Returns {reversed: N, skipped: N, failed: N}.
    """
    if not os.path.exists(JOURNAL_FILE):
        print("No moves journal found — nothing to undo.")
        return {}

    con = _journal_conn()
    if last_n:
        rows = con.execute(
            "SELECT * FROM moves WHERE undone_at IS NULL "
            "AND COALESCE(status, 'done')='done' ORDER BY id DESC LIMIT ?", (last_n,)
        ).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM moves WHERE undone_at IS NULL "
            "AND COALESCE(status, 'done')='done' ORDER BY id DESC"
        ).fetchall()

    total = len(rows)
    if not total:
        print("Nothing to undo.")
        con.close()
        return {}

    tag = '[DRY-UNDO]' if dry_run else '[UNDO]'
    print(f"\n{tag} Reversing {total} move(s)...")
    reversed_n = skipped = failed = 0

    for row in rows:
        src  = row['dest']   # where it is NOW
        dest = row['src']    # where it came FROM

        if not os.path.exists(src):
            print(f"  SKIP (gone from dest): {row['disk_name']!r}")
            skipped += 1
            continue
        if os.path.exists(dest):
            print(f"  SKIP (src path occupied): {dest!r}")
            skipped += 1
            continue

        source_root = row['dest_root'] or ''
        dest_root = row['source_root'] or ''
        if not source_root or not dest_root:
            print(f"  SKIP (missing persisted path boundaries): {row['disk_name']!r}")
            skipped += 1
            continue
        try:
            validate_move(
                src,
                dest,
                source_root=source_root,
                dest_root=dest_root,
            )
        except PathSafetyError as exc:
            print(f"  SKIP (unsafe undo path): {row['disk_name']!r}: {exc}")
            skipped += 1
            continue

        print(f"  {tag} {row['clean_name']!r}  {src!r} -> {dest!r}")
        if not dry_run:
            try:
                robust_move(src, dest)
                con.execute(
                    "UPDATE moves SET undone_at=?, status=?, updated_at=? WHERE id=?",
                    (_utc_now(), 'undone', _utc_now(), row['id'])
                )
                con.commit()
                reversed_n += 1
            except Exception as e:
                print(f"  FAILED undo {row['disk_name']!r}: {e}")
                failed += 1
        else:
            reversed_n += 1

    con.close()
    print(f"\n{'DRY ' if dry_run else ''}Undo complete: {reversed_n} reversed, "
          f"{skipped} skipped, {failed} failed")
    return {'reversed': reversed_n, 'skipped': skipped, 'failed': failed}

# ── Load org_index ────────────────────────────────────────────────────────────
def load_index_for_source(source_mode: str) -> list:
    if source_mode == 'design':
        path = DESIGN_INDEX_FILE
    elif source_mode == 'design_org':
        path = os.path.join(os.path.dirname(__file__), 'design_org_index.json')
    elif source_mode == 'loose_files':
        path = os.path.join(os.path.dirname(__file__), 'loose_files_index.json')
    elif source_mode == 'design_elements':
        path = os.path.join(os.path.dirname(__file__), 'design_elements_index.json')
    elif source_mode == 'i_organized_legacy':
        path = os.path.join(os.path.dirname(__file__), 'i_organized_legacy_index.json')
    else:
        path = INDEX_FILE
    if not os.path.exists(path):
        return []
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_org_index() -> list:
    return load_index_for_source('ae')

# ── Batch file → index offset ─────────────────────────────────────────────────
def batch_offset(filename: str, source_mode: str = 'ae') -> int:
    """
    Map batch filename to its starting offset in the appropriate index.
      AE mode:
        batch_001.json      → 0   (AE items 0-59)
        batch_013.json      → 720 (AE items 720-779)
        unorg_batch_001.json→ AE_TOTAL (Unorganized items start after all AE)
      Design mode:
        design_batch_001.json → 0
        design_batch_013.json → 720
      Design Org mode:
        design_org_batch_001.json → 0
      Loose files mode:
        loose_batch_001.json → 0
    """
    stem = Path(filename).stem
    if stem.startswith('i_org_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('design_org_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('de_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('loose_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('design_batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * DESIGN_BATCH_SIZE
    elif stem.startswith('unorg_batch_'):
        n = int(stem.split('_')[-1])
        return AE_TOTAL + (n - 1) * 100
    elif stem.startswith('batch_'):
        n = int(stem.split('_')[-1])
        return (n - 1) * AE_BATCH_SIZE
    return 0

# ── Pre-flight validator ──────────────────────────────────────────────────────
def validate_sources(pairs: list, source_override: str = '') -> dict:
    """
    Scan all source directories for known problem patterns BEFORE attempting
    any moves.  Reports:
      - Directories/files with trailing spaces in their names (→ WinError 2)
      - Paths whose full length exceeds 260 chars (→ WinError 3 on cross-drive)
      - Missing source directories (already moved or never existed)

    Returns {'trailing_spaces': [...], 'long_paths': [...], 'missing': [...]}
    """
    org  = load_org_index()
    trailing_space_items = []
    long_path_items      = []
    missing_items        = []

    for item, org_entry in pairs:
        if not org_entry:
            continue
        src_dir   = source_override or org_entry['folder']
        disk_name = org_entry['name']
        src       = os.path.join(src_dir, disk_name)

        if not os.path.exists(src):
            missing_items.append(src)
            continue

        for dirpath, dirnames, filenames in os.walk(src):
            for name in dirnames + filenames:
                full = os.path.join(dirpath, name)
                if name != name.rstrip():
                    trailing_space_items.append(full)
                if len(full) > 260:
                    long_path_items.append(full)

    return {
        'trailing_spaces': trailing_space_items,
        'long_paths':      long_path_items,
        'missing':         missing_items,
    }

# ── Pre-sanitize: strip trailing spaces from file/folder names in-place ────────
def _win_longpath(p: str) -> str:
    """Return \\\\?\\-prefixed path for extended-length path API on Windows."""
    if p.startswith('\\\\?\\'):
        return p
    return '\\\\?\\' + os.path.abspath(p)

def strip_trailing_spaces(root: str) -> list:
    """
    Rename any file or directory under `root` that has trailing spaces in its name.
    Returns list of (old_path, new_path) renames performed.

    Uses \\\\?\\ extended-length prefix so Windows does NOT strip the trailing
    space when building the source path (the normal API normalises it away, making
    os.rename silently fail — the fix is to bypass normalisation via \\\\?\\).
    """
    renamed = []
    for dirpath, dirnames, filenames in os.walk(root, topdown=False):
        for name in filenames + dirnames:
            stripped = name.rstrip()
            if name != stripped and stripped:
                old = os.path.join(dirpath, name)
                new = os.path.join(dirpath, stripped)
                if not os.path.exists(new):
                    try:
                        # Use extended-length prefix so Windows doesn't normalise
                        # the trailing space away before the rename syscall
                        os.rename(_win_longpath(old), _win_longpath(new))
                        renamed.append((old, new))
                    except Exception as e:
                        # Log silently — robust_move will still attempt robocopy
                        pass
    return renamed


def _exact_path_exists(path: str) -> bool:
    candidate = _win_longpath(path) if os.name == 'nt' else path
    return os.path.lexists(candidate)


def _rename_exact_path(source: str, destination: str) -> None:
    if os.name == 'nt':
        os.rename(_win_longpath(source), _win_longpath(destination))
    else:
        os.rename(source, destination)


def _sanitized_component_destination(parent: str, name: str) -> str:
    """Choose a no-overwrite name for a component after right-trimming it."""
    candidate = os.path.join(parent, name)
    if not _exact_path_exists(candidate):
        return candidate
    stem, extension = os.path.splitext(name)
    index = 1
    while True:
        candidate = os.path.join(parent, f'{stem} ({index}){extension}')
        if not _exact_path_exists(candidate):
            return candidate
        index += 1


def sanitize_file_source_path(path: str, source_root: str) -> tuple[str, list[tuple[str, str]]]:
    """Right-trim loose-file path components without overwriting siblings."""
    path_module: ModuleType
    if os.name == 'nt':
        source_value = os.fspath(path).replace('/', '\\')
        root_value = os.fspath(source_root).replace('/', '\\')
        source_abs = (
            source_value if ntpath.isabs(source_value)
            else ntpath.join(os.getcwd(), source_value)
        )
        root_abs = (
            root_value if ntpath.isabs(root_value)
            else ntpath.join(os.getcwd(), root_value)
        )
        path_module = ntpath
        root_prefix = root_abs if root_abs.endswith('\\') else root_abs + '\\'
        if not path_module.normcase(source_abs).startswith(path_module.normcase(root_prefix)):
            raise PathSafetyError('loose-file source escapes its source root')
        relative = source_abs[len(root_prefix):]
    else:
        source_abs = os.path.abspath(path)
        root_abs = os.path.abspath(source_root)
        path_module = os.path
        try:
            common = path_module.commonpath((source_abs, root_abs))
            if common != root_abs or source_abs == root_abs:
                raise PathSafetyError('loose-file source escapes its source root')
        except ValueError as exc:
            raise PathSafetyError('loose-file source is on a different volume') from exc
        relative = path_module.relpath(source_abs, root_abs)
    current = root_abs
    renamed: list[tuple[str, str]] = []
    components = re.split(r'[\\/]', relative)
    if any(component in {'', '.', '..'} for component in components):
        raise PathSafetyError('loose-file source has an unsafe relative component')
    for component in components:
        old_path = path_module.join(current, component)
        stripped = component.rstrip()
        if stripped and stripped != component:
            new_path = _sanitized_component_destination(current, stripped)
            _rename_exact_path(old_path, new_path)
            renamed.append((old_path, new_path))
            current = new_path
        else:
            current = old_path
    return (current if renamed else path), renamed

def is_cross_drive(src: str, dst: str) -> bool:
    return os.path.splitdrive(src)[0].upper() != os.path.splitdrive(dst)[0].upper()

# ── Robocopy-based move (reliable for cross-drive, Unicode, long paths) ────────
def _lp(path: str) -> str:
    """Return a \\\\?\\-prefixed extended-length path for Win32 robocopy calls.
    Normalises forward slashes and strips any existing \\\\?\\ prefix first.
    """
    p = os.path.abspath(path).replace('/', '\\')
    if p.startswith('\\\\?\\'):
        return p
    if p.startswith('\\\\'):          # UNC path
        return '\\\\?\\UNC\\' + p[2:]
    return '\\\\?\\' + p


def _robocopy_mt_arg() -> list:
    """Return ['/MT:n'] when multi-thread enabled, else [].

    Pulled from advanced_settings.json (default 8).  /MT:0 or /MT:1 means
    "disable" — return [] so robocopy uses single-thread mode (which is what
    it does without /MT at all).
    """
    try:
        from fileorganizer.config import load_advanced_settings
        n = int(load_advanced_settings().get('robocopy_mt', 8))
    except Exception:
        n = 8
    if n <= 1:
        return []
    return [f'/MT:{n}']


def robust_move(src: str, dst: str) -> None:
    """
    Move `src` (file or directory) to `dst`.
    - Same drive: os.rename (atomic).
    - Cross-drive directory: robocopy /MOVE /E /256 /MT:8 then remove emptied src.
    - Cross-drive file: robocopy /MOV (single-file mode) on the parent dir.
    Both src and dst are passed with \\\\?\\ prefix so robocopy source-scanning
    also honours extended path lengths (not just the destination).
    Raises RuntimeError if robocopy exit code >= 8 (actual failure).
    Robocopy exit codes: 0=nothing to do, 1=files copied, 2=extra files,
    3=mismatched, 4=mismatched+copied, 5-7=combinations — all < 8 = success.

    /MT:n thread count is loaded from advanced_settings.json (default 8); set
    robocopy_mt=0 or 1 to disable multi-thread on slow USB drives.
    """
    validate_move(src, dst)
    if not is_cross_drive(src, dst):
        os.rename(src, dst)
        return

    mt = _robocopy_mt_arg()

    is_file = os.path.isfile(src)
    if is_file:
        # Robocopy works on parent dirs + a filename pattern. Don't pre-create
        # `dst` as a directory — that's what previously caused
        # "ERROR 123 (0x0000007B) Accessing Source Directory" when a caller
        # mistakenly invoked robust_move on a file.
        src_parent = os.path.dirname(src) or os.path.splitdrive(src)[0] + '\\'
        dst_parent = os.path.dirname(dst) or os.path.splitdrive(dst)[0] + '\\'
        src_name = os.path.basename(src)
        dst_name = os.path.basename(dst)
        os.makedirs(dst_parent, exist_ok=True)
        result = subprocess.run([
            'robocopy', _lp(src_parent), _lp(dst_parent), src_name,
            '/MOV',    # /MOV (single V) moves files but not dir trees
            '/256', '/R:3', '/W:1',
            *mt,
            '/NP', '/NFL', '/NDL', '/NJH', '/NJS',
        ], capture_output=True, text=True)
        if result.returncode >= 8:
            raise RuntimeError(
                f"robocopy file move exit {result.returncode}: "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
        # Robocopy preserves the original filename; rename if dst differs
        intermediate = os.path.join(dst_parent, src_name)
        if intermediate != dst and os.path.exists(intermediate):
            os.rename(intermediate, dst)
        return

    os.makedirs(dst, exist_ok=True)
    result = subprocess.run([
        'robocopy', _lp(src), _lp(dst),
        '/MOVE',   # move (delete source files after copy)
        '/E',      # include empty subdirs
        '/256',    # disable 260-char path limit (long path support)
        '/R:3',    # retry 3×
        '/W:1',    # wait 1 s between retries
        *mt,       # /MT:n multi-thread (default 8) — 4-6× faster on cross-drive
        '/NP',     # no progress %
        '/NFL',    # no file list
        '/NDL',    # no dir list
        '/NJH',    # no job header
        '/NJS',    # no job summary
    ], capture_output=True, text=True)

    if result.returncode >= 8:
        raise RuntimeError(
            f"robocopy exit {result.returncode}: {result.stderr.strip() or result.stdout.strip()}"
        )

    # Remove now-empty source dir (robocopy /MOVE empties it but doesn't rmdir)
    try:
        shutil.rmtree(src)
    except Exception:
        pass

# ── Load classification JSONs with position-based org_index alignment ─────────
def load_one(path: str) -> list:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get('results', [])

def load_all_with_index(source_mode: str = 'ae') -> list:
    """
    Returns list of (classified_item, index_entry) tuples.
    source_mode='ae'              → batch_NNN.json + unorg_batch_NNN.json → org_index.json
    source_mode='design'          → design_batch_NNN.json → design_unorg_index.json
    source_mode='design_org'      → design_org_batch_NNN.json → design_org_index.json
    source_mode='loose_files'     → loose_batch_NNN.json → loose_files_index.json
    source_mode='design_elements' → de_batch_NNN.json → design_elements_index.json
    """
    org = load_index_for_source(source_mode)
    pairs = []

    if source_mode == 'design':
        glob_pattern = 'design_batch_*.json'
    elif source_mode == 'design_org':
        glob_pattern = 'design_org_batch_*.json'
    elif source_mode == 'loose_files':
        glob_pattern = 'loose_batch_*.json'
    elif source_mode == 'design_elements':
        glob_pattern = 'de_batch_*.json'
    elif source_mode == 'i_organized_legacy':
        glob_pattern = 'i_org_batch_*.json'
    else:
        glob_pattern = '*.json'

    for p in sorted(Path(RESULTS_DIR).glob(glob_pattern)):
        stem = p.stem
        # In AE mode, skip design/org/loose/de/i_org batch files
        if source_mode == 'ae' and stem.startswith(('design_batch_', 'design_org_batch_', 'loose_batch_', 'de_batch_', 'i_org_batch_')):
            continue
        # In design mode, only design_batch files
        if source_mode == 'design' and not stem.startswith('design_batch_'):
            continue
        # In design_org mode, only design_org_batch files
        if source_mode == 'design_org' and not stem.startswith('design_org_batch_'):
            continue
        # In loose_files mode, only loose_batch files
        if source_mode == 'loose_files' and not stem.startswith('loose_batch_'):
            continue
        # In design_elements mode, only de_batch files
        if source_mode == 'design_elements' and not stem.startswith('de_batch_'):
            continue
        # In i_organized_legacy mode, only i_org_batch files
        if source_mode == 'i_organized_legacy' and not stem.startswith('i_org_batch_'):
            continue

        items = load_one(str(p))
        offset = batch_offset(p.name, source_mode)
        for i, item in enumerate(items):
            idx_pos   = offset + i
            org_entry = org[idx_pos] if idx_pos < len(org) else None
            pairs.append((item, org_entry))
    return pairs

# ── Destination helpers ───────────────────────────────────────────────────────
def get_dest_root() -> str:
    """Return primary destination, or overflow if primary is running low on space."""
    if _FORCE_OVERFLOW:
        os.makedirs(DEST_OVERFLOW, exist_ok=True)
        return DEST_OVERFLOW
    try:
        free_bytes = shutil.disk_usage(DEST_PRIMARY[:3]).free
        if free_bytes > MIN_FREE_GB * 1_073_741_824:
            return DEST_PRIMARY
    except Exception:
        pass
    os.makedirs(DEST_OVERFLOW, exist_ok=True)
    return DEST_OVERFLOW

def sanitize(s: str, maxlen: int = 120) -> str:
    return re.sub(r'[<>:"/\\|?*]', '-', s).strip()[:maxlen]


def _safe_name_component(value: str, label: str) -> str:
    """Reject rooted/traversal values before display sanitization."""
    if not isinstance(value, str):
        raise PathSafetyError(f"{label} must be a string")
    value = value.strip()
    if not value or value in {'.', '..'}:
        raise PathSafetyError(f"{label} is empty or a dot path")
    if '\x00' in value or '/' in value or '\\' in value:
        raise PathSafetyError(f"{label} contains a path separator")
    if os.path.isabs(value) or ntpath.isabs(value) or ntpath.splitdrive(value)[0]:
        raise PathSafetyError(f"{label} is rooted")
    return value


def _valid_category(category: str) -> bool:
    """Return whether a normalized category is in the runtime allowlist."""
    if not isinstance(category, str) or not category.strip():
        return False
    if '/' in category or '\\' in category or category in {'.', '..'}:
        return False
    try:
        from fileorganizer.categories import get_all_category_names
        allowed = set(get_all_category_names())
    except Exception:
        allowed = set()
    # Historical batch aliases are normalized above and remain valid output
    # names even when the current taxonomy has since renamed the category.
    allowed.update(CATEGORY_ALIASES.values())
    return category in allowed

def _cat_path(dest_root: str, category: str) -> str:
    """
    Build the category sub-path under dest_root, preserving multi-level categories.

    category may be a single name  ('After Effects - Slideshow')
    or a path-joined two-level str ('_Review\\After Effects - Slideshow')
    as produced by os.path.join(REVIEW_SUBDIR, category) in apply_moves.

    Each component is sanitized independently so the backslash separator is
    never eaten by sanitize() — which previously collapsed
    '_Review\\After Effects - Other' → '_Review-After Effects - Other'.
    """
    if not isinstance(category, str):
        raise PathSafetyError("category must be a string")
    parts = [p for p in category.replace('\\', '/').split('/') if p]
    if not parts:
        raise PathSafetyError("category path is empty")
    safe_parts = [sanitize(_safe_name_component(part, 'category')) for part in parts]
    if any(not part or part in {'.', '..'} for part in safe_parts):
        raise PathSafetyError("category contains no usable filename component")
    dest = os.path.join(dest_root, *safe_parts)
    if not is_within(dest, dest_root):
        raise PathSafetyError(f"category destination escapes root: {category!r}")
    return dest

def _path_key(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))

def _path_taken(path: str, reserved: set | None = None) -> bool:
    return os.path.exists(path) or (reserved is not None and _path_key(path) in reserved)

def safe_dest_path(dest_root: str, category: str, clean_name: str,
                   reserved: set | None = None) -> str:
    clean_name = _safe_name_component(clean_name, 'clean_name')
    dest = os.path.join(_cat_path(dest_root, category), sanitize(clean_name))
    if not is_within(dest, dest_root):
        raise PathSafetyError("clean_name destination escapes root")
    if _path_taken(dest, reserved):
        base, i = dest, 1
        while _path_taken(dest, reserved):
            dest = f"{base} ({i})"
            i += 1
    return dest

def safe_dest_path_file(dest_root: str, category: str, clean_name: str, ext: str,
                        reserved: set | None = None) -> str:
    """Build collision-safe destination path for a flat file (not a directory)."""
    cat_dir = _cat_path(dest_root, category)
    stem    = sanitize(_safe_name_component(clean_name, 'clean_name'))
    if not isinstance(ext, str) or '/' in ext or '\\' in ext or not ext.startswith('.'):
        raise PathSafetyError("file extension is unsafe")
    dest    = os.path.join(cat_dir, f"{stem}{ext}")
    if not is_within(dest, dest_root):
        raise PathSafetyError("file destination escapes root")
    if _path_taken(dest, reserved):
        i = 1
        while _path_taken(dest, reserved):
            dest = os.path.join(cat_dir, f"{stem} ({i}){ext}")
            i += 1
    return dest


def _rule_context(
    src: str,
    item: dict,
    org_entry: dict,
    *,
    confidence: int,
    category: str,
    dest_root: str,
) -> dict:
    """Build the bounded, read-only context exposed to user rule chains."""
    metadata = item.get('metadata')
    if not isinstance(metadata, dict):
        metadata = org_entry.get('metadata')
    if not isinstance(metadata, dict):
        metadata = {}
    file_size = org_entry.get('size', item.get('file_size', 0))
    file_count = org_entry.get('file_count', item.get('file_count', 0))
    try:
        file_size = int(file_size or 0)
    except (TypeError, ValueError, OverflowError):
        file_size = 0
    try:
        file_count = int(file_count or 0)
    except (TypeError, ValueError, OverflowError):
        file_count = 0
    if os.path.isfile(src):
        try:
            file_size = os.path.getsize(src)
        except OSError:
            pass
        file_count = 1
    extension = org_entry.get('file_ext') or item.get('extension') or Path(src).suffix
    return {
        'extension': str(extension).lower().lstrip('.'),
        'filename': os.path.basename(src),
        'folder_name': os.path.basename(src),
        'file_size': file_size,
        'file_count': file_count,
        'llm_confidence': confidence,
        'metadata': metadata,
        'category': category,
        'dest_root': dest_root,
    }


def _rule_destination_container(destination: str, dest_root: str) -> str:
    if not isinstance(destination, str) or not destination.strip():
        raise PathSafetyError('rule move destination is empty')
    destination = destination.strip()
    if os.path.isabs(destination) or ntpath.isabs(destination):
        container = os.path.abspath(destination)
    else:
        container = os.path.abspath(os.path.join(dest_root, destination))
    if not is_within(container, dest_root, allow_equal=True):
        raise PathSafetyError(
            'rule move destination escapes the approved destination root')
    return container


def _safe_dest_in_container(
    container: str,
    clean_name: str,
    *,
    file_ext: str = '',
    reserved: set | None = None,
) -> str:
    stem = sanitize(_safe_name_component(clean_name, 'rule rename'))
    if file_ext:
        if '/' in file_ext or '\\' in file_ext or not file_ext.startswith('.'):
            raise PathSafetyError('file extension is unsafe')
        candidate = os.path.join(container, f'{stem}{file_ext}')
        base = os.path.join(container, stem)
        index = 1
        while _path_taken(candidate, reserved):
            candidate = f'{base} ({index}){file_ext}'
            index += 1
    else:
        candidate = os.path.join(container, stem)
        base = candidate
        index = 1
        while _path_taken(candidate, reserved):
            candidate = f'{base} ({index})'
            index += 1
    if not is_within(candidate, container):
        raise PathSafetyError('rule destination name escapes its container')
    return candidate

# ── Move plans ────────────────────────────────────────────────────────────────
@dataclass
class MovePlanItem:
    id: str
    source_mode: str
    src: str
    dest: str
    disk_name: str
    clean_name: str
    category: str
    effective_category: str
    confidence: int
    source_root: str = ''
    source_signature: dict = field(default_factory=dict)
    is_file_item: bool = False
    file_ext: str = ''
    low_confidence: bool = False
    status: str = 'planned'
    reason: str = ''
    error: str = ''
    duplicate_matches: list = field(default_factory=list)
    duplicate_policy: str = ''
    provenance: dict = field(default_factory=dict)
    rule_matches: list = field(default_factory=list)
    rule_deferred_actions: list = field(default_factory=list)

@dataclass
class MovePlan:
    schema_version: int
    plan_id: str
    created_at: str
    source_mode: str
    dest_root: str
    min_confidence: int
    item_count: int
    category_counts: dict = field(default_factory=dict)
    skipped: list = field(default_factory=list)
    items: list = field(default_factory=list)


_PROVENANCE_DESCRIPTOR_FIELDS = (
    'record_id',
    'input_fingerprint',
    'provider',
    'model',
    'prompt_hash',
    'schema_hash',
    'taxonomy_hash',
    'response_hash',
)


def _safe_provenance_descriptor(value) -> dict:
    if not isinstance(value, dict):
        return {}
    return {
        field_name: str(value[field_name])[:512]
        for field_name in _PROVENANCE_DESCRIPTOR_FIELDS
        if isinstance(value.get(field_name), str) and value[field_name]
    }

def _default_plan_path(plan_id: str) -> str:
    return os.path.join(PLANS_DIR, f"{plan_id}.json")

def _default_report_path(report_id: str) -> str:
    return os.path.join(REPORTS_DIR, f"{report_id}.md")

def _plan_dict(plan: MovePlan | dict) -> dict:
    return asdict(plan) if isinstance(plan, MovePlan) else plan

def write_move_plan(plan: MovePlan | dict, path: str = '') -> str:
    plan_data = _plan_dict(plan)
    out = path or _default_plan_path(plan_data['plan_id'])
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(plan_data, f, indent=2, ensure_ascii=False)
        f.write('\n')
    return out

def read_move_plan(path: str) -> dict:
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("Move plan must be a JSON object")
    schema_version = int(data.get('schema_version', 0))
    if schema_version == 1:
        for item in data.get('items', []):
            if isinstance(item, dict):
                item.setdefault('provenance', {})
        data['schema_version'] = PLAN_SCHEMA_VERSION
    elif schema_version != PLAN_SCHEMA_VERSION:
        raise ValueError(f"Unsupported plan schema: {data.get('schema_version')!r}")
    if not isinstance(data.get('items'), list):
        raise ValueError("Move plan missing items list")
    if not isinstance(data.get('dest_root'), str) or not data['dest_root']:
        raise ValueError("Move plan missing destination boundary")
    for index, item in enumerate(data['items']):
        if not isinstance(item, dict):
            raise ValueError(f"Move plan item {index} is not an object")
        if not isinstance(item.get('src'), str) or not isinstance(item.get('dest'), str):
            raise ValueError(f"Move plan item {index} has invalid paths")
        if not isinstance(item.get('source_root'), str) or not item.get('source_root'):
            raise ValueError(f"Move plan item {index} has no source boundary")
    return data

def _file_sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


class RetryCleanupError(RuntimeError):
    """A stale or unowned retry destination could not be removed safely."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _is_reparse_entry(path: str, info=None) -> bool:
    if os.path.islink(path):
        return True
    if info is None:
        info = os.lstat(path)
    return bool(getattr(info, 'st_file_attributes', 0) & 0x0400)


def _partial_destination_signature(path: str, *, max_entries: int = 100_000) -> dict:
    """Capture identity for a partial destination without following reparse points."""
    if not os.path.lexists(path):
        return {}
    info = os.lstat(path)
    if _is_reparse_entry(path, info):
        kind = 'reparse'
    elif os.path.isfile(path):
        kind = 'file'
    elif os.path.isdir(path):
        kind = 'directory'
    else:
        kind = 'other'
    signature = {
        'kind': kind,
        'st_dev': int(getattr(info, 'st_dev', 0)),
        'st_ino': int(getattr(info, 'st_ino', 0)),
        'size': int(info.st_size),
        'mtime_ns': int(getattr(info, 'st_mtime_ns', int(info.st_mtime * 1_000_000_000))),
        'cleanup_safe': kind in {'file', 'directory'},
    }
    if kind != 'directory':
        return signature

    digest = hashlib.sha256()
    entry_count = 0
    for dirpath, dirnames, filenames in os.walk(path, topdown=True, followlinks=False):
        dirnames.sort()
        filenames.sort()
        for name in [*dirnames, *filenames]:
            entry_count += 1
            if entry_count > max_entries:
                signature['cleanup_safe'] = False
                signature['reason'] = 'partial destination exceeds cleanup entry limit'
                return signature
            entry_path = os.path.join(dirpath, name)
            entry_info = os.lstat(entry_path)
            if _is_reparse_entry(entry_path, entry_info):
                signature['cleanup_safe'] = False
                signature['reason'] = 'partial destination contains a reparse point'
                return signature
            relative = os.path.relpath(entry_path, path).replace('\\', '/')
            entry_kind = 'directory' if os.path.isdir(entry_path) else 'file'
            entry_record = (
                f"{relative}\0{entry_kind}\0{entry_info.st_size}\0"
                f"{getattr(entry_info, 'st_mtime_ns', 0)}\0"
                f"{getattr(entry_info, 'st_dev', 0)}\0{getattr(entry_info, 'st_ino', 0)}\n"
            )
            digest.update(entry_record.encode('utf-8', errors='surrogatepass'))
    signature['entry_count'] = entry_count
    signature['tree_digest'] = digest.hexdigest()
    return signature


def _safe_partial_destination_signature(path: str) -> dict:
    try:
        return _partial_destination_signature(path)
    except OSError as exc:
        return {
            'kind': 'unreadable',
            'cleanup_safe': False,
            'reason': f'could not inspect partial destination: {exc}',
        }


def _file_is_source_prefix(source: str, partial: str) -> bool:
    try:
        if os.path.getsize(partial) > os.path.getsize(source):
            return False
        with open(source, 'rb') as source_file, open(partial, 'rb') as partial_file:
            while True:
                partial_chunk = partial_file.read(1024 * 1024)
                if not partial_chunk:
                    return True
                if source_file.read(len(partial_chunk)) != partial_chunk:
                    return False
    except OSError:
        return False


def _partial_destination_matches_source(
    source: str,
    destination: str,
    *,
    max_entries: int = 100_000,
) -> bool:
    if os.path.isfile(source) and os.path.isfile(destination):
        return _file_is_source_prefix(source, destination)
    if not os.path.isdir(source) or not os.path.isdir(destination):
        return False

    checked = 0
    for dirpath, dirnames, filenames in os.walk(
        destination, topdown=True, followlinks=False):
        for name in [*dirnames, *filenames]:
            checked += 1
            if checked > max_entries:
                return False
            partial_path = os.path.join(dirpath, name)
            if _is_reparse_entry(partial_path):
                return False
            relative = os.path.relpath(partial_path, destination)
            source_path = os.path.join(source, relative)
            if os.path.isdir(partial_path):
                if not os.path.isdir(source_path):
                    return False
            elif not os.path.isfile(source_path) or not _file_is_source_prefix(
                source_path, partial_path):
                return False
    return True


def _cleanup_partial_destination(source: str, destination: str, expected: dict) -> None:
    if not isinstance(expected, dict) or not expected.get('cleanup_safe'):
        raise RetryCleanupError(
            'partial_identity_missing',
            'partial destination has no safe recorded identity',
        )
    current = _partial_destination_signature(destination)
    if current != expected:
        raise RetryCleanupError(
            'partial_destination_changed',
            'partial destination changed since the failed move',
        )
    if not _partial_destination_matches_source(source, destination):
        raise RetryCleanupError(
            'partial_destination_unrelated',
            'occupied destination does not match the source partial copy',
        )
    if _partial_destination_signature(destination) != expected:
        raise RetryCleanupError(
            'partial_destination_changed',
            'partial destination changed during retry validation',
        )
    if expected.get('kind') == 'file':
        os.remove(destination)
    elif expected.get('kind') == 'directory':
        shutil.rmtree(destination)
    else:
        raise RetryCleanupError(
            'partial_type_unsafe', 'partial destination type cannot be removed safely')

def _iter_hashable_files(root: str):
    if os.path.isfile(root):
        yield root, os.path.basename(root)
        return
    if not os.path.isdir(root):
        return
    for dirpath, _dirnames, filenames in os.walk(root):
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            yield full, rel

def _hash_files(root: str) -> list[dict]:
    records = []
    for full, rel in _iter_hashable_files(root):
        try:
            records.append({
                'sha256': _file_sha256(full),
                'path': full,
                'relative_path': rel,
            })
        except (OSError, PermissionError):
            continue
    return records

def _destination_hash_index(dest_dir: str) -> dict:
    index = {}
    if not os.path.exists(dest_dir):
        return index
    for rec in _hash_files(dest_dir):
        index.setdefault(rec['sha256'], rec['path'])
    return index

def _planned_dest_file(dest: str, src: str, source_file: str,
                       is_file_item: bool) -> str:
    if is_file_item:
        return dest
    try:
        rel = os.path.relpath(source_file, src)
    except ValueError:
        rel = os.path.basename(source_file)
    return os.path.join(dest, rel)

def _duplicate_matches(source_hashes: list[dict], dest_hashes: dict,
                       limit: int = 10) -> list[dict]:
    matches = []
    for rec in source_hashes:
        existing = dest_hashes.get(rec['sha256'])
        if not existing:
            continue
        if _path_key(existing) == _path_key(rec['path']):
            continue
        matches.append({
            'sha256': rec['sha256'],
            'source_file': rec['path'],
            'existing_file': existing,
        })
        if len(matches) >= limit:
            break
    return matches

def _duplicate_error(match: dict) -> str:
    return (
        "Destination already contains identical file: "
        f"{match.get('source_file', '')} == {match.get('existing_file', '')}"
    )


def _source_signature(path: str) -> dict:
    """Capture enough source identity to detect a tampered persisted plan."""
    info = os.stat(path, follow_symlinks=False)
    return {
        'st_dev': int(getattr(info, 'st_dev', 0)),
        'st_ino': int(getattr(info, 'st_ino', 0)),
        'size': int(info.st_size),
        'mtime_ns': int(getattr(info, 'st_mtime_ns', int(info.st_mtime * 1_000_000_000))),
        'is_file': bool(os.path.isfile(path)),
        'is_dir': bool(os.path.isdir(path)),
    }


def _check_source_signature(item: dict, src: str) -> None:
    expected = item.get('source_signature')
    if not expected:
        raise PathSafetyError(
            f"plan item {item.get('id', '?')!r} has no source identity metadata"
        )
    try:
        actual = _source_signature(src)
    except OSError as exc:
        raise PathSafetyError(f"cannot inspect planned source {src!r}: {exc}") from exc
    for key in ('st_dev', 'st_ino', 'size', 'mtime_ns', 'is_file', 'is_dir'):
        if key in expected and expected[key] != actual[key]:
            raise PathSafetyError(
                f"planned source identity changed for {src!r} ({key})"
            )


def _validate_plan_item(item: dict, plan_data: dict, *, require_source: bool = True) -> None:
    if not isinstance(item, dict):
        raise PathSafetyError("move plan item must be an object")
    src = item.get('src')
    dest = item.get('dest')
    source_root = item.get('source_root')
    dest_root = plan_data.get('dest_root')
    if not isinstance(src, str) or not isinstance(dest, str):
        raise PathSafetyError(f"plan item {item.get('id', '?')!r} has invalid paths")
    if not isinstance(source_root, str) or not source_root:
        raise PathSafetyError(f"plan item {item.get('id', '?')!r} has no source boundary")
    if not isinstance(dest_root, str) or not dest_root:
        raise PathSafetyError("move plan has no destination boundary")
    validate_move(
        src,
        dest,
        source_root=source_root,
        dest_root=dest_root,
        require_source=require_source,
    )
    if require_source and os.path.lexists(src):
        _check_source_signature(item, src)


def _preflight_move_plan(plan_data: dict, already_moved: set[str]) -> None:
    """Validate every mutating item before the first move starts."""
    approved_dest_root = get_dest_root()
    if canonical_path(plan_data.get('dest_root', '')) != canonical_path(approved_dest_root):
        raise PathSafetyError("move plan destination is not the current approved root")
    for item in plan_data.get('items', []):
        src = item.get('src') if isinstance(item, dict) else None
        if src in already_moved:
            continue
        if isinstance(item, dict) and item.get('duplicate_matches') and item.get('duplicate_policy', 'skip') != 'move':
            continue
        _validate_plan_item(item, plan_data, require_source=False)
        if isinstance(item, dict) and os.path.lexists(item.get('src', '')):
            _check_source_signature(item, item['src'])

def build_move_plan(pairs: list, source_override: str = '',
                    source_mode: str = 'ae', plan_id: str = '',
                    rule_manager: RuleChainManager | None = None,
                    folder_cache: FolderCache | None = None, *,
                    rename: bool = False,
                    rename_template: str = CANONICAL_TEMPLATE) -> MovePlan:
    """Convert classified/index pairs into an editable, collision-safe move plan."""
    plan_id = plan_id or f"plan-{_compact_timestamp()}"
    created_at = _utc_now()
    first_dest_root = get_dest_root()
    planned = []
    skipped = []
    category_counts = defaultdict(int)
    reserved_dests = set()
    already_moved = journal_src_set()
    dest_hash_cache = {}
    last_dest_root = first_dest_root

    for item, org_entry in pairs:
        dest_root = get_dest_root()
        last_dest_root = dest_root
        raw_name = item.get('name', '?')
        raw_category = item.get('category', 'After Effects - Other')
        raw_category_text = raw_category.strip() if isinstance(raw_category, str) else ''
        category = normalize_category(raw_category_text) if raw_category_text else ''
        try:
            conf = int(item.get('confidence', 0))
        except (TypeError, ValueError):
            conf = 0

        if not org_entry:
            skipped.append({'name': raw_name, 'reason': 'not_in_index'})
            continue

        is_file_item = bool(org_entry.get('is_file'))
        if 'path' in org_entry:
            src = org_entry['path']
            source_root = (
                org_entry.get('source_root') or source_override or os.path.dirname(src)
            )
        else:
            src_dir = source_override or org_entry['folder']
            src = os.path.join(src_dir, org_entry['name'])
            source_root = src_dir

        disk_name = os.path.basename(src)
        if is_file_item:
            try:
                src, renamed = sanitize_file_source_path(src, source_root)
            except (OSError, PathSafetyError) as exc:
                skipped.append({
                    'name': raw_name,
                    'src': src,
                    'reason': 'source_sanitize_failed',
                    'error': str(exc),
                })
                continue
            if renamed:
                log(f"    Pre-sanitized {len(renamed)} trailing-space component(s) in {raw_name!r}")
            disk_name = os.path.basename(src)

        clean = (item.get('clean_name') or raw_name or '').strip()
        if not clean:
            clean = Path(disk_name).stem or disk_name or 'Unnamed Asset'

        if not os.path.exists(src):
            skipped.append({'name': disk_name, 'src': src, 'reason': 'missing_source'})
            continue
        if src in already_moved:
            skipped.append({'name': disk_name, 'src': src, 'reason': 'already_moved'})
            continue
        if folder_cache is not None and os.path.isdir(src):
            unchanged, cache_detail = should_skip_folder(src, folder_cache)
            if unchanged:
                skipped.append({
                    'name': disk_name,
                    'src': src,
                    'reason': 'unchanged_cached',
                    'detail': cache_detail,
                })
                continue

        valid_category = _valid_category(category)
        rule_decision = None
        if rule_manager is not None and rule_manager.chains:
            rule_decision = rule_manager.plan(_rule_context(
                src,
                item,
                org_entry,
                confidence=conf,
                category=category or raw_category_text,
                dest_root=dest_root,
            ))
            if rule_decision.skip:
                skipped.append({
                    'name': disk_name,
                    'src': src,
                    'reason': 'rule_skip',
                    'rule_matches': list(rule_decision.matched_rules),
                })
                continue
            if rule_decision.rename:
                clean = rule_decision.rename.strip()
                if is_file_item and Path(clean).suffix.lower() == Path(src).suffix.lower():
                    clean = Path(clean).stem
                try:
                    _safe_name_component(clean, 'rule rename')
                except PathSafetyError as exc:
                    skipped.append({
                        'name': disk_name,
                        'src': src,
                        'reason': 'invalid_rule_rename',
                        'error': str(exc),
                        'rule_matches': list(rule_decision.matched_rules),
                    })
                    continue

        if rename:
            try:
                clean = render_name(
                    {
                        **item,
                        'name': disk_name,
                        'category': category,
                        'clean_name': clean,
                        'is_file_item': is_file_item,
                    },
                    index=len(planned) + 1,
                    template=rename_template,
                )
            except (TypeError, ValueError, PathSafetyError) as exc:
                skipped.append({
                    'name': disk_name,
                    'src': src,
                    'reason': 'invalid_rename_template',
                    'error': str(exc),
                })
                continue

        try:
            _safe_name_component(clean, 'clean_name')
        except PathSafetyError:
            skipped.append({
                'name': disk_name,
                'src': src,
                'reason': 'invalid_clean_name',
            })
            continue

        if not valid_category:
            if rule_decision is None or not rule_decision.destination:
                skipped.append({
                    'name': raw_name,
                    'category': raw_category_text,
                    'reason': 'invalid_category',
                })
                continue
            category = 'After Effects - Other'

        low_conf = conf < MIN_CONFIDENCE
        rule_destination = rule_decision.destination if rule_decision is not None else None
        has_rule_destination = bool(rule_destination)
        eff_category = (
            category if has_rule_destination
            else os.path.join(REVIEW_SUBDIR, category) if low_conf else category
        )

        try:
            rule_container = (
                _rule_destination_container(rule_destination or '', dest_root)
                if has_rule_destination
                else ''
            )
            if is_file_item:
                file_ext = Path(src).suffix.lower()
                disk_stem = sanitize(Path(disk_name).stem)
                dest_stem = (
                    clean if rule_decision and rule_decision.rename
                    else disk_stem or clean
                )
                dest = (
                    _safe_dest_in_container(
                        rule_container,
                        dest_stem,
                        file_ext=file_ext,
                        reserved=reserved_dests,
                    )
                    if rule_container else
                    safe_dest_path_file(
                        dest_root, eff_category, dest_stem, file_ext, reserved_dests
                    )
                )
            else:
                file_ext = ''
                dest = (
                    _safe_dest_in_container(
                        rule_container, clean, reserved=reserved_dests
                    )
                    if rule_container else
                    safe_dest_path(dest_root, eff_category, clean, reserved_dests)
                )
        except PathSafetyError as exc:
            skipped.append({
                'name': disk_name,
                'src': src,
                'reason': 'invalid_rule_destination',
                'error': str(exc),
                'rule_matches': (
                    list(rule_decision.matched_rules) if rule_decision else []
                ),
            })
            continue

        try:
            source_signature = _source_signature(src)
        except OSError as exc:
            skipped.append({
                'name': disk_name,
                'src': src,
                'reason': 'source_unreadable',
                'error': str(exc),
            })
            continue

        dest_category_dir = rule_container or _cat_path(dest_root, eff_category)
        dest_key = _path_key(dest_category_dir)
        if dest_key not in dest_hash_cache:
            dest_hash_cache[dest_key] = _destination_hash_index(dest_category_dir)
        source_hashes = _hash_files(src)
        duplicate_hits = _duplicate_matches(source_hashes, dest_hash_cache[dest_key])
        item_status = 'blocked_duplicate' if duplicate_hits else 'planned'
        item_reason = 'destination_duplicate' if duplicate_hits else ''
        duplicate_policy = 'skip' if duplicate_hits else ''
        if not duplicate_hits:
            for rec in source_hashes:
                dest_file = _planned_dest_file(dest, src, rec['path'], is_file_item)
                dest_hash_cache[dest_key].setdefault(rec['sha256'], dest_file)

        reserved_dests.add(_path_key(dest))
        category_counts[category] += 1
        planned.append(asdict(MovePlanItem(
            id=f"{source_mode}-{len(planned) + 1:06d}",
            source_mode=source_mode,
            src=src,
            dest=dest,
            source_root=os.path.abspath(source_root),
            source_signature=source_signature,
            disk_name=disk_name,
            clean_name=clean,
            category=category,
            effective_category=eff_category,
            confidence=conf,
            is_file_item=is_file_item,
            file_ext=file_ext,
            low_confidence=low_conf,
            status=item_status,
            reason=item_reason,
            duplicate_matches=duplicate_hits,
            duplicate_policy=duplicate_policy,
            provenance=_safe_provenance_descriptor(
                item.get('_provenance') or item.get('provenance')
            ),
            rule_matches=(
                list(rule_decision.matched_rules) if rule_decision else []
            ),
            rule_deferred_actions=(
                list(rule_decision.deferred_actions) if rule_decision else []
            ),
        )))

    return MovePlan(
        schema_version=PLAN_SCHEMA_VERSION,
        plan_id=plan_id,
        created_at=created_at,
        source_mode=source_mode,
        dest_root=last_dest_root,
        min_confidence=MIN_CONFIDENCE,
        item_count=len(planned),
        category_counts=dict(sorted(category_counts.items())),
        skipped=skipped,
        items=planned,
    )

def _move_plan_item(item: dict, plan_data: dict | None = None):
    src = item['src']
    dest = item['dest']
    if item.get('is_file_item'):
        src, renamed = sanitize_file_source_path(
            src, item.get('source_root') or os.path.dirname(src))
        if renamed:
            item['src'] = src
            item['disk_name'] = os.path.basename(src)
            item['file_ext'] = Path(src).suffix.lower()
            log(
                f"    Pre-sanitized {len(renamed)} trailing-space component(s) "
                f"in {item['disk_name']!r}"
            )
    if plan_data is not None:
        _validate_plan_item(item, plan_data)
    else:
        validate_move(src, dest)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if item.get('is_file_item'):
        try:
            os.rename(src, dest)
        except OSError:
            shutil.move(src, dest)
    else:
        renamed = strip_trailing_spaces(src)
        if renamed:
            log(f"    Pre-sanitized {len(renamed)} name(s) with trailing spaces in {item['disk_name']!r}")
        robust_move(src, dest)

def apply_move_plan(plan: MovePlan | dict, dry_run: bool = False,
                    verbose: bool = True) -> dict:
    """Apply an editable move plan and journal pending/done/failed transitions."""
    plan_data = _plan_dict(plan)
    source_mode = plan_data.get('source_mode', 'ae')
    plan_id = plan_data.get('plan_id') or f"plan-{_compact_timestamp()}"
    run_id = f"{plan_id}-run-{_compact_timestamp()}"
    moved = skipped = errors = 0
    low_conf = sum(1 for item in plan_data.get('items', []) if item.get('low_confidence'))
    category_counts = defaultdict(int)
    error_log = []
    already_moved = journal_src_set()

    # A persisted plan is untrusted input.  Validate every item, including
    # source identity and both roots, before the first item can mutate disk.
    _preflight_move_plan(plan_data, already_moved)

    for item in plan_data.get('items', []):
        src = item['src']
        dest = item['dest']
        disk_name = item.get('disk_name', os.path.basename(src))
        category = item.get('category', 'Unknown')
        category_counts[category] += 1

        if src in already_moved:
            skipped += 1
            continue

        duplicate_hits = item.get('duplicate_matches') or []
        duplicate_policy = item.get('duplicate_policy') or ('skip' if duplicate_hits else '')
        if duplicate_hits and duplicate_policy != 'move':
            match = duplicate_hits[0]
            err_msg = _duplicate_error(match)
            if verbose:
                tag = '[DRY-DUP-SKIP]' if dry_run else '[DUP-SKIP]'
                log(f"  {tag} {disk_name!r}")
                log(f"    {err_msg}", also_print=verbose)
            if not dry_run:
                journal_record(
                    src, dest, disk_name, item.get('clean_name', ''), category,
                    int(item.get('confidence', 0)), status='skipped_duplicate',
                    plan_id=plan_id, plan_item_id=item.get('id', ''),
                    run_id=run_id, error=err_msg,
                    duplicate_source_file=match.get('source_file', ''),
                    duplicate_existing_file=match.get('existing_file', ''),
                    duplicate_sha256=match.get('sha256', ''),
                    source_root=item.get('source_root', ''),
                    dest_root=plan_data.get('dest_root', ''),
                    source_signature=item.get('source_signature'),
                    provenance=item.get('provenance'),
                )
            skipped += 1
            continue

        if verbose:
            tag = '[DRY-PLAN]' if dry_run else '[MOVE]'
            flag = f"  *** LOW CONF={item.get('confidence', 0)}" if item.get('low_confidence') else ''
            log(f"  {tag} {disk_name!r}")
            log(f"    -> {dest}  [{item.get('confidence', 0)}]{flag}", also_print=verbose)

        if dry_run:
            moved += 1
            continue

        move_id = journal_record(
            src, dest, disk_name, item.get('clean_name', ''), category,
            int(item.get('confidence', 0)), status='pending',
            plan_id=plan_id, plan_item_id=item.get('id', ''), run_id=run_id,
            source_root=item.get('source_root', ''),
            dest_root=plan_data.get('dest_root', ''),
            source_signature=item.get('source_signature'),
            provenance=item.get('provenance'),
        )

        try:
            if not os.path.exists(src):
                raise FileNotFoundError(f"Source missing: {src}")
            _move_plan_item(item, plan_data)
            journal_update(move_id, 'done')
            already_moved.add(src)
            moved += 1
        except Exception as e:
            err_msg = str(e)
            partial = os.path.lexists(dest)
            partial_signature = (
                _safe_partial_destination_signature(dest) if partial else {})
            journal_update(move_id, 'failed', err_msg, partial_dest_exists=partial)
            log(f"    ERROR moving {disk_name!r}: {err_msg}")
            errors += 1
            error_log.append({
                'disk_name': disk_name,
                'src': src,
                'dest': dest,
                'category': category,
                'clean_name': item.get('clean_name', ''),
                'confidence': int(item.get('confidence', 0)),
                'error': err_msg,
                'partial_dest_exists': partial,
                'partial_dest_signature': partial_signature,
                'is_file_item': bool(item.get('is_file_item')),
                'file_ext': item.get('file_ext', ''),
                'plan_id': plan_id,
                'plan_item_id': item.get('id', ''),
                'run_id': run_id,
                'source_root': item.get('source_root', ''),
                'dest_root': plan_data.get('dest_root', ''),
                'source_signature': item.get('source_signature', {}),
                'provenance': item.get('provenance', {}),
            })

    tag = 'DRY PLAN' if dry_run else 'APPLIED PLAN'
    log(f"\n{tag}: {moved} moved, {skipped} skipped, {errors} errors, "
        f"{low_conf} low-conf routed to {REVIEW_SUBDIR}/")
    if plan_data.get('skipped'):
        by_reason = defaultdict(int)
        for item in plan_data['skipped']:
            by_reason[item.get('reason', 'unknown')] += 1
        reason_text = ', '.join(f"{reason}={count}" for reason, count in sorted(by_reason.items()))
        log(f"Plan skipped {len(plan_data['skipped'])} item(s): {reason_text}")

    if not dry_run and error_log:
        efile = errors_file(source_mode)
        with open(efile, 'w', encoding='utf-8') as f:
            json.dump(error_log, f, indent=2, ensure_ascii=False)
        log(f"\nErrors written to {efile} — run --retry-errors --source {source_mode} to attempt fixes")

    return {
        'plan_id': plan_id,
        'run_id': run_id,
        'moved': moved,
        'skipped': skipped,
        'errors': errors,
        'low_confidence': low_conf,
        'category_counts': dict(category_counts),
    }

def apply_moves(pairs: list, source_override: str,
                dry_run: bool = True, verbose: bool = True,
                source_mode: str = 'ae'):
    """Compatibility wrapper: build a move plan, then dry-run or apply it."""
    plan = build_move_plan(pairs, source_override, source_mode)
    result = apply_move_plan(plan, dry_run=dry_run, verbose=verbose)
    return result['moved'], result['skipped'], result['errors'], result['category_counts']

# ── CLI ───────────────────────────────────────────────────────────────────────
def retry_errors(source_mode: str = 'ae'):
    """Re-attempt items from the source-specific errors file."""
    efile = errors_file(source_mode)
    # Fall back to legacy path if source-specific file doesn't exist yet
    if not os.path.exists(efile) and os.path.exists(ERRORS_FILE):
        efile = ERRORS_FILE
    if not os.path.exists(efile):
        print(f"No errors file found at {efile}")
        return
    with open(efile, 'r', encoding='utf-8') as f:
        errors = json.load(f)
    log(f"Retrying {len(errors)} errored items (source={source_mode})...")
    retried = fixed = still_failed = 0
    remaining = []
    for e in errors:
        src  = e['src']
        source_root = e.get('source_root', '')
        persisted_dest_root = e.get('dest_root', '')
        if not source_root or not persisted_dest_root:
            msg = 'missing persisted source/destination boundaries'
            log(f"  BLOCKED (unsafe retry metadata): {e.get('disk_name', src)!r}: {msg}")
            remaining.append({**e, 'error': msg})
            retried += 1
            still_failed += 1
            continue
        dest_root = get_dest_root()
        eff_cat = e.get('category', '')
        clean = e.get('clean_name', '')
        conf = int(e.get('confidence', 0))
        if conf < MIN_CONFIDENCE:
            eff_cat = os.path.join(REVIEW_SUBDIR, eff_cat)
        dest = e.get('dest', '')
        approved_dest_root = persisted_dest_root
        if not os.path.exists(src):
            log(f"  SKIP (src gone): {e['disk_name']!r}")
            retried += 1
            fixed   += 1
            continue
        try:
            partial_dest = e.get('dest', '')
            if e.get('partial_dest_exists') and os.path.lexists(partial_dest):
                validate_move(
                    src,
                    partial_dest,
                    source_root=source_root,
                    dest_root=persisted_dest_root,
                    allow_existing_dest=True,
                )
                log(f"  Cleaning verified partial dest: {partial_dest!r}")
                _cleanup_partial_destination(
                    src, partial_dest, e.get('partial_dest_signature'))
                validate_move(
                    src,
                    partial_dest,
                    source_root=source_root,
                    dest_root=persisted_dest_root,
                )

            # Recompute only after stale partial output is safely removed so
            # collision allocation does not route the retry to a needless suffix.
            if eff_cat and clean:
                if e.get('is_file_item'):
                    file_ext = e.get('file_ext') or Path(src).suffix.lower()
                    dest = safe_dest_path_file(
                        dest_root, eff_cat, clean, file_ext)
                else:
                    dest = safe_dest_path(dest_root, eff_cat, clean)
                approved_dest_root = dest_root
            else:
                dest = e['dest']
                approved_dest_root = persisted_dest_root

            renamed = strip_trailing_spaces(src)
            if renamed:
                log(f"  Pre-sanitized {len(renamed)} trailing-space names in {e['disk_name']!r}")
            validate_move(
                src,
                dest,
                source_root=source_root,
                dest_root=approved_dest_root,
            )
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            robust_move(src, dest)
            journal_record(src, dest, e['disk_name'], e.get('clean_name', ''),
                           e.get('category', ''), int(e.get('confidence', 0)),
                           source_root=source_root, dest_root=approved_dest_root,
                           source_signature=e.get('source_signature'),
                           provenance=e.get('provenance'))
            log(f"  FIXED: {e['disk_name']!r}")
            fixed += 1
        except RetryCleanupError as ex:
            log(f"  BLOCKED [{ex.code}]: {e['disk_name']!r}: {ex}")
            still_failed += 1
            remaining.append({
                **e,
                'error': str(ex),
                'retry_error_code': ex.code,
                'partial_dest_exists': os.path.lexists(e.get('dest', '')),
            })
        except Exception as ex:
            log(f"  STILL FAILED: {e['disk_name']!r}: {ex}")
            still_failed += 1
            partial = bool(dest and os.path.lexists(dest))
            remaining.append({
                **e,
                'dest': dest,
                'dest_root': approved_dest_root,
                'error': str(ex),
                'retry_error_code': 'retry_failed',
                'partial_dest_exists': partial,
                'partial_dest_signature': (
                    _safe_partial_destination_signature(dest) if partial else {}),
            })
        retried += 1
    log(f"\nRetry complete: {fixed} fixed, {still_failed} still failing")
    if remaining:
        with open(efile, 'w', encoding='utf-8') as f:
            json.dump(remaining, f, indent=2, ensure_ascii=False)
        log(f"Remaining errors saved to {efile}")
    else:
        os.remove(efile)
        log("All errors resolved — errors file removed")

def cmd_validate(pairs: list, source_override: str = ''):
    """Pre-flight scan: find trailing spaces and long paths before attempting moves."""
    print("\nRunning pre-flight validation on source directories...")
    report = validate_sources(pairs, source_override)
    ts = report['trailing_spaces']
    lp = report['long_paths']
    ms = report['missing']
    print(f"\n  Trailing-space names : {len(ts)}")
    for p in ts[:20]:
        print(f"    {p!r}")
    if len(ts) > 20:
        print(f"    ... {len(ts) - 20} more")
    print(f"\n  Long paths (>260)    : {len(lp)}")
    for p in lp[:20]:
        print(f"    {p!r}")
    if len(lp) > 20:
        print(f"    ... {len(lp) - 20} more")
    print(f"\n  Missing sources      : {len(ms)}")
    for p in ms[:10]:
        print(f"    {p!r}")
    would_error = len(ts) + len(lp)
    print(f"\nPre-flight summary: {would_error} items would need remediation before apply")
    if would_error == 0:
        print("All sources look clean — safe to run --apply")
    else:
        print("Run --apply anyway (auto-remediates both issues via robocopy + pre-sanitize)")

def _md_cell(value) -> str:
    text = str(value if value is not None else '')
    return text.replace('\\', '\\\\').replace('|', '\\|').replace('\r', ' ').replace('\n', ' ')

def _report_name(identifier: str) -> str:
    return sanitize(identifier.replace(os.sep, '-'), 100) or f"report-{_compact_timestamp()}"

def generate_report(identifier: str, output: str = '') -> str:
    """Generate a Markdown report from a run id, plan id, or plan JSON path."""
    generated_at = _utc_now()
    rows = []
    skipped = []
    report_title = identifier

    if os.path.exists(identifier):
        plan = read_move_plan(identifier)
        report_title = plan.get('plan_id', identifier)
        rows = [
            {
                'status': item.get('status', 'planned'),
                'src': item.get('src', ''),
                'dest': item.get('dest', ''),
                'disk_name': item.get('disk_name', ''),
                'clean_name': item.get('clean_name', ''),
                'category': item.get('category', ''),
                'confidence': item.get('confidence', 0),
                'error': item.get('error', ''),
                'partial_dest_exists': 0,
                'provenance_id': (
                    item.get('provenance', {}).get('record_id', '')
                    if isinstance(item.get('provenance'), dict) else ''
                ),
            }
            for item in plan.get('items', [])
        ]
        skipped = plan.get('skipped', [])
    else:
        con = _journal_conn()
        found = con.execute(
            "SELECT * FROM moves WHERE run_id=? OR plan_id=? ORDER BY id",
            (identifier, identifier)
        ).fetchall()
        con.close()
        rows = [dict(row) for row in found]
        if not rows:
            raise RuntimeError(f"No journal entries found for report id: {identifier}")

    status_counts = defaultdict(int)
    category_counts = defaultdict(int)
    low_conf = 0
    for row in rows:
        status_counts[row.get('status') or 'unknown'] += 1
        category_counts[row.get('category') or 'Unknown'] += 1
        try:
            if int(row.get('confidence') or 0) < MIN_CONFIDENCE:
                low_conf += 1
        except (TypeError, ValueError):
            pass

    out = output or _default_report_path(_report_name(report_title))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    lines = [
        '# FileOrganizer Move Report',
        '',
        f'- Report id: `{_md_cell(report_title)}`',
        f'- Generated: `{generated_at}`',
        f'- Items: `{len(rows)}`',
        f'- Low confidence: `{low_conf}`',
        f'- Skipped before planning: `{len(skipped)}`',
        '',
        '## Status Summary',
        '',
        '| Status | Count |',
        '|---|---:|',
    ]
    for status, count in sorted(status_counts.items()):
        lines.append(f"| {_md_cell(status)} | {count} |")

    lines.extend(['', '## Category Summary', '', '| Category | Count |', '|---|---:|'])
    for category, count in sorted(category_counts.items(), key=lambda x: (-x[1], x[0])):
        lines.append(f"| {_md_cell(category)} | {count} |")

    failures = [row for row in rows if (row.get('status') == 'failed' or row.get('error'))]
    if failures:
        lines.extend(['', '## Failures', '', '| Item | Error | Partial Dest |', '|---|---|---:|'])
        for row in failures:
            lines.append(
                f"| {_md_cell(row.get('disk_name') or row.get('clean_name'))} "
                f"| {_md_cell(row.get('error'))} "
                f"| {int(bool(row.get('partial_dest_exists')))} |"
            )

    if skipped:
        lines.extend(['', '## Skipped Before Planning', '', '| Item | Reason | Source |', '|---|---|---|'])
        for row in skipped:
            lines.append(
                f"| {_md_cell(row.get('name', ''))} | {_md_cell(row.get('reason', ''))} "
                f"| {_md_cell(row.get('src', ''))} |"
            )

    lines.extend([
        '',
        '## Items',
        '',
        '| Status | Confidence | Category | Provenance | Source | Destination |',
        '|---|---:|---|---|---|---|',
    ])
    for row in rows:
        lines.append(
            f"| {_md_cell(row.get('status', 'planned'))} "
            f"| {_md_cell(row.get('confidence', 0))} "
            f"| {_md_cell(row.get('category', ''))} "
            f"| `{_md_cell(row.get('provenance_id', ''))}` "
            f"| `{_md_cell(row.get('src', ''))}` "
            f"| `{_md_cell(row.get('dest', ''))}` |"
        )

    with open(out, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    return out

def build_argument_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser()
    ap.add_argument('--preview', '--dry-run', dest='preview', action='store_true',
                    help='Dry run and emit an editable move plan (default)')
    ap.add_argument('--apply', '--commit', dest='apply', action='store_true',
                    help='Commit a generated or persisted move plan')
    ap.add_argument('--plan-out',      type=str,            help='Write generated move plan to this JSON path')
    ap.add_argument('--plan-file',     type=str,
                    help='Write a dry-run plan, or read it when used with --commit')
    ap.add_argument('--apply-plan',    type=str,            help='Apply a previously generated move plan JSON')
    ap.add_argument('--report',        type=str,            help='Generate Markdown report for a run id, plan id, or plan JSON path')
    ap.add_argument('--output',        type=str,            help='Output path for --report')
    ap.add_argument('--validate',      action='store_true', help='Pre-flight: scan for WinError 2/3 sources')
    ap.add_argument('--retry-errors',  action='store_true', help='Retry items in organize_errors.json')
    ap.add_argument('--undo-last',     type=int, metavar='N', help='Reverse last N moves from journal')
    ap.add_argument('--undo-all',      action='store_true',   help='Reverse ALL moves from journal')
    ap.add_argument('--load',          type=str,            help='Single JSON file (skips position mapping)')
    ap.add_argument('--source',        type=str, default='ae',
                    choices=['ae', 'design', 'design_org', 'loose_files', 'design_elements', 'i_organized_legacy'],
                    help='Source mode: ae (default), design, design_org, loose_files, design_elements, or i_organized_legacy')
    ap.add_argument('--stats',         action='store_true', help='Show batch file counts')
    ap.add_argument('--summary',       action='store_true', help='Category/marketplace breakdown')
    ap.add_argument('--quiet',         action='store_true', help='Suppress per-item output')
    ap.add_argument('--overflow-now',  action='store_true',
                    help='Force all moves to I:\\Organized immediately (bypass G:\\ free-space check)')
    ap.add_argument('--rules-file',    type=str,
                    help='Use a specific Hazel-style rule_chains.json file')
    ap.add_argument('--no-rules',      action='store_true',
                    help='Disable user rule-chain evaluation for this run')
    ap.add_argument('--skip-unchanged', action='store_true',
                    help='Skip folders whose cached fingerprint is unchanged')
    ap.add_argument('--invalidate-cache', action='store_true',
                    help='Clear the folder fingerprint cache and exit')
    ap.add_argument('--parallel', action='store_true',
                    help='Classify pending source batches concurrently before planning')
    ap.add_argument('--concurrency', type=int, choices=range(1, 9), metavar='N',
                    help='Concurrent classifier requests for --parallel (1-8)')
    ap.add_argument('--request-batch-size', type=int, choices=range(1, 61), metavar='N',
                    help='Folders in each parallel classifier request (1-60)')
    ap.add_argument('--rename', action='store_true',
                    help='Opt in to canonical batch names in the generated plan')
    ap.add_argument('--rename-template', type=str, default=CANONICAL_TEMPLATE,
                    help=f'Canonical rename template (default: {CANONICAL_TEMPLATE})')
    return ap


def main():
    ap = build_argument_parser()
    args = ap.parse_args()

    if args.plan_file and args.apply_plan:
        ap.error('--plan-file and --apply-plan cannot be used together')

    folder_cache = None
    if args.invalidate_cache or args.skip_unchanged:
        folder_cache = FolderCache()
    if args.invalidate_cache:
        assert folder_cache is not None
        folder_cache.invalidate_all()
        print('Folder fingerprint cache cleared.')
        if not args.skip_unchanged:
            return

    if args.overflow_now:
        global _FORCE_OVERFLOW
        _FORCE_OVERFLOW = True

    if args.report:
        out = generate_report(args.report, args.output or '')
        print(f"Report written: {out}")
        return

    persisted_plan = args.apply_plan or (args.plan_file if args.apply else '')
    if persisted_plan:
        plan = read_move_plan(persisted_plan)
        result = apply_move_plan(plan, dry_run=(args.preview and not args.apply), verbose=not args.quiet)
        print(f"Plan id: {result['plan_id']}")
        print(f"Run id: {result['run_id']}")
        print(f"Moved={result['moved']} skipped={result['skipped']} errors={result['errors']}")
        return

    if args.retry_errors:
        retry_errors(args.source)
        return

    if args.undo_last:
        undo_moves(last_n=args.undo_last)
        return

    if args.undo_all:
        undo_moves(last_n=0)
        return

    source_mode = args.source

    if args.parallel:
        if args.load:
            ap.error('--parallel cannot be combined with --load')
        classify_source = {
            'design': 'design_unorg',
            'design_org': 'design_org',
            'loose_files': 'loose_files',
            'design_elements': 'design_elements',
            'i_organized_legacy': 'i_organized_legacy',
        }.get(source_mode)
        if classify_source is None:
            ap.error('--parallel requires a design, loose_files, or legacy source')
        import classify_design
        try:
            classify_design.run_source(
                classify_source,
                parallel=True,
                concurrency=args.concurrency,
                request_batch_size=args.request_batch_size,
            )
        except FileNotFoundError as exc:
            raise SystemExit(str(exc)) from exc

    if args.stats:
        files = sorted(Path(RESULTS_DIR).glob('*.json'))
        total = 0
        print(f"\nClassification results ({RESULTS_DIR}):")
        for fp in files:
            items = load_one(str(fp))
            offset = batch_offset(fp.name, source_mode)
            print(f"  {fp.name:<35} {len(items):>4} items  [index {offset}-{offset+len(items)-1}]")
            total += len(items)
        print(f"\n  Total: {total} items across {len(files)} files")
        if os.path.exists(JOURNAL_FILE):
            con = _journal_conn()
            n_moved  = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NULL AND COALESCE(status, 'done')='done'"
            ).fetchone()[0]
            n_pending = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NULL AND COALESCE(status, 'done')='pending'"
            ).fetchone()[0]
            n_failed = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NULL AND COALESCE(status, 'done')='failed'"
            ).fetchone()[0]
            n_undone = con.execute(
                "SELECT COUNT(*) FROM moves WHERE undone_at IS NOT NULL OR COALESCE(status, 'done')='undone'"
            ).fetchone()[0]
            con.close()
            print(f"\n  Moves journal: {n_moved} done, {n_pending} pending, {n_failed} failed, {n_undone} undone")
        return

    if args.load:
        org = load_index_for_source(source_mode)
        name_map = {e['name']: e for e in org}
        items = load_one(args.load)
        log(f"Loaded {len(items)} items from {args.load}")
        pairs = []
        for item in items:
            n = item.get('name', '')
            entry = name_map.get(n) or next(
                (e for e in org if e['name'].startswith(n) or n.startswith(e['name'])), None)
            pairs.append((item, entry))
    else:
        pairs = load_all_with_index(source_mode)
        log(f"Loaded {len(pairs)} items via position-based index mapping (source={source_mode})")

    # Determine source directory override per mode
    _SOURCE_DIRS = {
        'design':              r'G:\Design Unorganized',
        'design_org':          r'G:\Design Organized',
        'loose_files':         r'G:\Design Unorganized',
        'design_elements':     r'G:\Design Organized\Design Elements',
        'i_organized_legacy':  r'I:\Organized',
    }
    source_dir_override = _SOURCE_DIRS.get(source_mode, '')

    if args.validate:
        cmd_validate(pairs, source_dir_override)
        return

    if args.summary:
        cats    = defaultdict(int)
        markets = defaultdict(int)
        low     = sum(1 for item, _ in pairs if int(item.get('confidence', 0)) < MIN_CONFIDENCE)
        for item, _ in pairs:
            cats[item.get('category', 'Unknown')] += 1
            markets[item.get('marketplace', 'Unknown')] += 1
        print(f"\n=== CATEGORY BREAKDOWN ({len(pairs)} items, {low} low-conf) ===")
        for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"  {cnt:>4}  {cat}")
        print(f"\n=== MARKETPLACE BREAKDOWN ===")
        for mkt, cnt in sorted(markets.items(), key=lambda x: -x[1]):
            print(f"  {cnt:>4}  {mkt}")
        return

    dry     = not args.apply
    verbose = not args.quiet
    rule_manager = None
    if not args.no_rules:
        rule_manager = RuleChainManager(args.rules_file)
        if rule_manager.load_error:
            raise SystemExit(f"Rule chains are invalid: {rule_manager.load_error}")
        if rule_manager.chains:
            log(f"Loaded {len(rule_manager.chains)} rule chain(s)")
    plan = build_move_plan(
        pairs,
        source_dir_override,
        source_mode,
        rule_manager=rule_manager,
        folder_cache=folder_cache,
        rename=args.rename,
        rename_template=args.rename_template,
    )
    plan_path = write_move_plan(plan, args.plan_out or args.plan_file or '')
    log(f"Move plan written: {plan_path}")
    result = apply_move_plan(plan, dry_run=dry, verbose=verbose)
    if not dry:
        log(f"Plan id: {result['plan_id']}")
        log(f"Run id: {result['run_id']}")

if __name__ == '__main__':
    main()
