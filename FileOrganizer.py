#!/usr/bin/env python3
"""FileOrganizer v5.3 - Context-Aware Classification + Smart Naming + Scan Performance"""

import sys, os, subprocess, re, shutil, json, csv, hashlib, gzip, sqlite3, time, math
from collections import Counter
from functools import lru_cache
import xml.etree.ElementTree as ET

def _bootstrap():
    """Auto-install dependencies before any imports."""
    if sys.version_info < (3, 8):
        print("Python 3.8+ required"); sys.exit(1)
    required = ['PyQt6']
    optional = ['rapidfuzz', 'psd-tools', 'unidecode']
    for pkg in required:
        try:
            __import__(pkg.replace('-', '_').lower())
        except ImportError:
            for flags in [[], ['--user'], ['--break-system-packages']]:
                try:
                    subprocess.check_call(
                        [sys.executable, '-m', 'pip', 'install', pkg, '-q'] + flags,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except subprocess.CalledProcessError:
                    continue
    for pkg in optional:
        try:
            __import__(pkg.replace('-', '_').lower())
        except ImportError:
            for flags in [[], ['--user'], ['--break-system-packages']]:
                try:
                    subprocess.check_call(
                        [sys.executable, '-m', 'pip', 'install', pkg, '-q'] + flags,
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
                except subprocess.CalledProcessError:
                    continue

# Optional imports with graceful fallback
_bootstrap()

try:
    from rapidfuzz import fuzz as _rfuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

try:
    import psd_tools as _psd_tools
    HAS_PSD_TOOLS = True
except ImportError:
    HAS_PSD_TOOLS = False

try:
    from unidecode import unidecode as _unidecode
    HAS_UNIDECODE = True
except ImportError:
    HAS_UNIDECODE = False

import traceback, ctypes
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QCheckBox, QTextEdit, QHeaderView, QFileDialog, QAbstractItemView,
    QSlider, QMenu, QTreeWidget, QTreeWidgetItem, QDialog, QDialogButtonBox, QSpinBox,
    QListWidget, QListWidgetItem, QInputDialog, QSplitter, QMessageBox, QFrame
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QMimeData, QUrl
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QAction

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()

# ── Correction Learning ───────────────────────────────────────────────────────
_CORRECTIONS_FILE = os.path.join(_SCRIPT_DIR, 'corrections.json')

def load_corrections():
    """Load user corrections: {folder_name_pattern: category}"""
    try:
        with open(_CORRECTIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# In-memory corrections cache for scan performance (avoids re-reading JSON per folder)
_corrections_cache = None

def _preload_corrections():
    """Pre-load corrections into memory. Call once at scan start."""
    global _corrections_cache
    _corrections_cache = load_corrections()

def _invalidate_corrections_cache():
    """Invalidate cache after edits."""
    global _corrections_cache
    _corrections_cache = None

def save_correction(folder_name, category):
    """Save a single correction for future learning."""
    corrections = load_corrections()
    # Store the cleaned folder name as key
    key = re.sub(r'[\d_\-]+$', '', folder_name).strip().lower()
    if key:
        corrections[key] = category
    corrections[folder_name.lower()] = category
    with open(_CORRECTIONS_FILE, 'w', encoding='utf-8') as f:
        json.dump(corrections, f, indent=2)
    _invalidate_corrections_cache()

def check_corrections(folder_name):
    """Check if we have a prior correction for this folder name.
    Returns category string or None. Uses in-memory cache when available."""
    corrections = _corrections_cache if _corrections_cache is not None else load_corrections()
    if not corrections:
        return None
    name_lower = folder_name.lower()
    # Exact match
    if name_lower in corrections:
        return corrections[name_lower]
    # Pattern match (cleaned name)
    key = re.sub(r'[\d_\-]+$', '', folder_name).strip().lower()
    if key and key in corrections:
        return corrections[key]
    # Fuzzy match against correction keys
    if HAS_RAPIDFUZZ:
        for ck, cv in corrections.items():
            if _rfuzz.token_set_ratio(name_lower, ck) >= 90:
                return cv
    return None


# ── Classification Cache (SQLite) ─────────────────────────────────────────────
_CACHE_DB = os.path.join(_SCRIPT_DIR, 'classification_cache.db')
_cache_conn = None  # Persistent connection for scan performance

def _get_cache_conn():
    """Get persistent SQLite connection, creating if needed."""
    global _cache_conn
    if _cache_conn is None:
        _cache_conn = sqlite3.connect(_CACHE_DB)
        _cache_conn.execute('CREATE TABLE IF NOT EXISTS cache ('
            'fingerprint TEXT PRIMARY KEY,'
            'category TEXT,'
            'confidence REAL,'
            'cleaned_name TEXT,'
            'method TEXT,'
            'detail TEXT,'
            'topic TEXT,'
            'created_at TEXT DEFAULT CURRENT_TIMESTAMP'
        ')')
        _cache_conn.commit()
    return _cache_conn

def _close_cache_conn():
    """Close persistent connection (call after scan completes)."""
    global _cache_conn
    if _cache_conn:
        try:
            _cache_conn.close()
        except Exception:
            pass
        _cache_conn = None

def _init_cache_db():
    """Initialize the cache database. Uses persistent connection."""
    return _get_cache_conn()

def _folder_fingerprint(folder_name, folder_path):
    """Compute a fingerprint based on folder name + file listing."""
    try:
        files = sorted(f.name for f in Path(folder_path).iterdir() if f.is_file())[:50]
    except (PermissionError, OSError):
        files = []
    raw = f"{folder_name}|{'|'.join(files)}"
    return hashlib.md5(raw.encode()).hexdigest()

def cache_lookup(folder_name, folder_path):
    """Check the cache for a prior classification. Returns dict or None."""
    try:
        fp = _folder_fingerprint(folder_name, folder_path)
        conn = _get_cache_conn()
        row = conn.execute('SELECT category, confidence, cleaned_name, method, detail, topic FROM cache WHERE fingerprint=?', (fp,)).fetchone()
        if row:
            return {'category': row[0], 'confidence': row[1], 'cleaned_name': row[2],
                    'method': row[3], 'detail': row[4], 'topic': row[5]}
    except Exception:
        pass
    return None

def cache_store(folder_name, folder_path, result):
    """Store a classification result in the cache."""
    try:
        fp = _folder_fingerprint(folder_name, folder_path)
        conn = _get_cache_conn()
        conn.execute('INSERT OR REPLACE INTO cache (fingerprint, category, confidence, cleaned_name, method, detail, topic) VALUES (?,?,?,?,?,?,?)',
                     (fp, result.get('category'), result.get('confidence', 0),
                      result.get('cleaned_name', ''), result.get('method', ''),
                      result.get('detail', ''), result.get('topic', '')))
        conn.commit()
    except Exception:
        pass

def cache_clear():
    """Clear the entire classification cache."""
    try:
        conn = _get_cache_conn()
        conn.execute('DELETE FROM cache')
        conn.commit()
    except Exception:
        pass

def cache_count():
    """Return the number of cached classifications."""
    try:
        conn = _get_cache_conn()
        n = conn.execute('SELECT COUNT(*) FROM cache').fetchone()[0]
        return n
    except Exception:
        return 0


# ── Duplicate Folder Detection ────────────────────────────────────────────────
def compute_file_fingerprint(folder_path, max_files=20):
    """Compute a content fingerprint for a folder based on file names and sizes."""
    try:
        entries = []
        for f in sorted(Path(folder_path).iterdir()):
            if f.is_file():
                try:
                    entries.append(f"{f.name}:{f.stat().st_size}")
                except (PermissionError, OSError):
                    continue
            if len(entries) >= max_files:
                break
        return hashlib.md5('|'.join(entries).encode()).hexdigest() if entries else None
    except (PermissionError, OSError):
        return None


# ── Backup Snapshot ───────────────────────────────────────────────────────────
def create_backup_snapshot(src_dir, items):
    """Save a directory listing snapshot before apply operations."""
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    snap_file = os.path.join(_SCRIPT_DIR, f'snapshot_{ts}.txt')
    try:
        with open(snap_file, 'w', encoding='utf-8') as f:
            f.write(f"FileOrganizer Backup Snapshot - {datetime.now().isoformat()}\n")
            f.write(f"Source: {src_dir}\n")
            f.write(f"Items: {len(items)}\n")
            f.write("=" * 80 + "\n\n")
            for it in items:
                src = getattr(it, 'full_source_path', getattr(it, 'full_current_path', ''))
                dst = getattr(it, 'full_dest_path', getattr(it, 'full_new_path', ''))
                f.write(f"FROM: {src}\n  TO: {dst}\n\n")
        return snap_file
    except Exception:
        return None


# ── Export/Import Classification Rules ────────────────────────────────────────
def export_rules_bundle(filepath):
    """Export custom categories + corrections as a single JSON bundle."""
    bundle = {
        'version': '5.0',
        'custom_categories': load_custom_categories(),
        'corrections': load_corrections(),
    }
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(bundle, f, indent=2)

def import_rules_bundle(filepath):
    """Import custom categories + corrections from a JSON bundle."""
    with open(filepath, 'r', encoding='utf-8') as f:
        bundle = json.load(f)
    if 'custom_categories' in bundle:
        save_custom_categories(bundle['custom_categories'])
    if 'corrections' in bundle:
        with open(_CORRECTIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(bundle['corrections'], f, indent=2)
    return bundle


# ── Crash handler ──────────────────────────────────────────────────────────────
def exception_handler(exc_type, exc_value, exc_tb):
    msg = ''.join(traceback.format_exception(exc_type, exc_value, exc_tb))
    crash_file = os.path.join(_SCRIPT_DIR, 'crash.log')
    with open(crash_file, 'w') as f:
        f.write(msg)
    if sys.platform == 'win32':
        ctypes.windll.user32.MessageBoxW(0, f"Crash log: {crash_file}\n\n{msg[:500]}", "Fatal Error", 0x10)
    sys.exit(1)

sys.excepthook = exception_handler

# ── Dark Theme ─────────────────────────────────────────────────────────────────
DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #0f1923; color: #c5cdd8;
    font-family: 'Segoe UI', 'SF Pro Display', system-ui, sans-serif; font-size: 13px;
}
QPushButton {
    background-color: #1b2838; color: #8f98a0;
    border: 1px solid #2a3f5f; padding: 7px 16px;
    border-radius: 4px; font-weight: 500; font-size: 12px;
}
QPushButton:hover { background-color: #1e3a5f; color: #c5cdd8; border-color: #3d6a9e; }
QPushButton:pressed { background-color: #254a73; }
QPushButton:disabled { background-color: #141d26; color: #3a4654; border-color: #1b2838; }
QPushButton[class="primary"] {
    background-color: #1a6bc4; color: #ffffff; border: none;
    font-weight: bold; font-size: 13px; padding: 8px 24px;
}
QPushButton[class="primary"]:hover { background-color: #2080e0; }
QPushButton[class="primary"]:pressed { background-color: #1560b0; }
QPushButton[class="primary"]:disabled { background-color: #1b2838; color: #3a4654; }
QPushButton[class="apply"] {
    background-color: #1b8553; color: #ffffff; border: none;
    font-weight: bold; font-size: 13px; padding: 8px 24px;
}
QPushButton[class="apply"]:hover { background-color: #22a366; }
QPushButton[class="apply"]:pressed { background-color: #167045; }
QPushButton[class="apply"]:disabled { background-color: #1b2838; color: #3a4654; }
QPushButton[class="toolbar"] {
    background-color: transparent; color: #6b7785;
    border: 1px solid transparent; padding: 5px 12px; font-size: 11px;
}
QPushButton[class="toolbar"]:hover { background-color: #1b2838; color: #c5cdd8; border-color: #2a3f5f; }
QLineEdit {
    background-color: #141d26; color: #c5cdd8;
    border: 1px solid #2a3f5f; border-radius: 4px;
    padding: 8px 12px; font-size: 13px; selection-background-color: #1a6bc4;
}
QLineEdit:focus { border-color: #1a6bc4; }
QLineEdit:read-only { color: #5a6672; }
QComboBox {
    background-color: #141d26; color: #c5cdd8;
    border: 1px solid #2a3f5f; border-radius: 4px;
    padding: 7px 12px; font-size: 13px; min-height: 28px;
}
QComboBox:hover { border-color: #3d6a9e; }
QComboBox::drop-down { border: none; width: 28px; }
QComboBox::down-arrow {
    image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 5px solid #6b7785; margin-right: 10px;
}
QComboBox QAbstractItemView {
    background-color: #141d26; color: #c5cdd8; border: 1px solid #2a3f5f;
    selection-background-color: #1a6bc4; selection-color: #ffffff; outline: none; padding: 4px;
}
QSpinBox {
    background-color: #141d26; color: #c5cdd8;
    border: 1px solid #2a3f5f; border-radius: 4px; padding: 4px 8px; font-size: 12px;
}
QSpinBox:focus { border-color: #1a6bc4; }
QTableWidget {
    background-color: #0f1923; alternate-background-color: #121e2b;
    color: #c5cdd8; border: 1px solid #1b2838; border-radius: 6px;
    gridline-color: transparent; font-size: 12px;
    selection-background-color: #1a3a5c; selection-color: #e0e6ec; outline: none;
}
QTableWidget::item { padding: 6px 10px; border-bottom: 1px solid #1b2838; }
QTableWidget::item:selected { background-color: #1a3a5c; }
QTableWidget::item:hover { background-color: #152535; }
QHeaderView::section {
    background-color: #0a1219; color: #6b7785; font-weight: 600; font-size: 11px;
    padding: 10px 12px; border: none; border-bottom: 2px solid #1b2838; border-right: 1px solid #1b2838;
}
QHeaderView::section:hover { color: #c5cdd8; }
QTextEdit {
    background-color: #0a1219; color: #5cb85c;
    border: 1px solid #1b2838; border-radius: 4px;
    font-family: 'Cascadia Code', 'JetBrains Mono', 'Consolas', monospace;
    font-size: 11px; padding: 8px; selection-background-color: #1a6bc4;
}
QScrollBar:vertical { background: transparent; width: 8px; border: none; margin: 4px 0; }
QScrollBar::handle:vertical { background: #2a3f5f; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #3d6a9e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: transparent; height: 8px; border: none; margin: 0 4px; }
QScrollBar::handle:horizontal { background: #2a3f5f; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #3d6a9e; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QCheckBox { spacing: 8px; color: #c5cdd8; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 4px; border: 2px solid #2a3f5f; background: #141d26; }
QCheckBox::indicator:checked { background: #1a6bc4; border-color: #1a6bc4; }
QCheckBox::indicator:unchecked:hover { border-color: #3d6a9e; }
QSlider::groove:horizontal { background: #1b2838; height: 6px; border-radius: 3px; }
QSlider::handle:horizontal { background: #1a6bc4; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }
QSlider::handle:horizontal:hover { background: #2080e0; }
QMenuBar { background-color: #0a1219; color: #6b7785; border-bottom: 1px solid #1b2838; padding: 2px 0; font-size: 12px; }
QMenuBar::item { padding: 6px 14px; border-radius: 4px; }
QMenuBar::item:selected { background-color: #1b2838; color: #c5cdd8; }
QMenu { background-color: #141d26; color: #c5cdd8; border: 1px solid #2a3f5f; border-radius: 6px; padding: 6px; }
QMenu::item { padding: 8px 24px 8px 16px; border-radius: 4px; }
QMenu::item:selected { background-color: #1a3a5c; }
QMenu::separator { height: 1px; background: #1b2838; margin: 4px 8px; }
QGroupBox { background-color: #121a24; border: 1px solid #1b2838; border-radius: 8px; margin-top: 8px; padding: 12px 10px 8px 10px; font-weight: 600; font-size: 11px; color: #6b7785; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 8px; color: #6b7785; }
QToolTip { background-color: #1b2838; color: #c5cdd8; border: 1px solid #2a3f5f; border-radius: 4px; padding: 6px 10px; font-size: 12px; }
QListWidget { background-color: #141d26; color: #c5cdd8; border: 1px solid #1b2838; border-radius: 4px; outline: none; }
QListWidget::item { padding: 6px 10px; }
QListWidget::item:selected { background-color: #1a3a5c; }
QListWidget::item:hover { background-color: #152535; }
QProgressBar { background-color: #1b2838; border: none; border-radius: 3px; text-align: center; color: #c5cdd8; font-size: 11px; height: 6px; }
QProgressBar::chunk { background-color: #1a6bc4; border-radius: 3px; }
"""


# ── Generic AEP names to exclude ──────────────────────────────────────────────
GENERIC_AEP_NAMES = {
    'cs6', 'project', '1', 'cc', 'ver_1', '(cs6)',
    'cs5', 'cs5.5', 'cs4', 'cc2014', 'cc2015', 'cc2017', 'cc2018', 'cc2019', 'cc2020',
    'cc2021', 'cc2022', 'cc2023', 'cc2024', 'cc2025',
    'main', 'comp', 'comp 1', 'comp1', 'composition', 'final', 'final project',
    'output', 'render', 'preview', 'thumbnail', 'template', 'source', 'original',
    'backup', 'copy', 'test', 'temp', 'draft', 'wip', 'new project', 'untitled',
    'element', 'precomp', 'pre-comp', 'pre comp', 'assets',
    # Discovered from 23K-folder scan (v5.4)
    '001', '002', '003', '16', '01',  # Bare numbers used as project names
}

def is_generic_aep(name: str) -> bool:
    return name.strip().lower() in GENERIC_AEP_NAMES


def _score_aep(aep_path, folder_path, folder_name):
    """Score an AEP file for how likely it is to be the main project file.
    Higher score = better candidate for naming.

    Scoring signals:
      +50  base score
      +30  descriptive name (>8 alpha chars, not generic)
      +20  name resembles folder name (shared significant words)
      +15  located at top level of folder (depth 0)
      +10  not inside an asset subfolder (Footage, Audio, etc.)
      +5   larger files get a small bonus (tiebreaker, not dominant)
      -40  generic/version name (project.aep, cs6.aep, comp.aep)
      -25  inside asset folder like (Footage), Elements, etc.
      -10  per depth level beyond top
      -15  very short name (1-3 chars, likely abbreviations)
    """
    stem = aep_path.stem  # filename without .aep
    stem_lower = stem.strip().lower()
    stem_norm = _normalize(stem)
    folder_norm = _normalize(folder_name)
    size = 0
    try:
        size = aep_path.stat().st_size
    except (PermissionError, OSError):
        pass

    score = 50  # Base score

    # ── Depth: prefer top-level AEPs ──
    try:
        rel = aep_path.relative_to(folder_path)
        depth = len(rel.parts) - 1  # 0 = directly in folder
    except (ValueError, TypeError):
        depth = 0
    score += max(0, 15 - depth * 10)  # +15 at depth 0, +5 at depth 1, -5 at depth 2, etc.

    # ── Asset folder penalty: AEPs inside (Footage), Assets, etc. ──
    if depth > 0:
        parent_parts = rel.parts[:-1]  # All parent dirs relative to folder root
        for part in parent_parts:
            part_lower = part.lower().strip()
            part_stripped = re.sub(r'^[\(\[\{]|[\)\]\}]$', '', part_lower).strip()
            if part_lower in _ASSET_FOLDER_NAMES or part_stripped in _ASSET_FOLDER_NAMES:
                score -= 25
                break

    # ── Generic name penalty ──
    if stem_lower in GENERIC_AEP_NAMES:
        score -= 40
    # Also penalize pure version patterns: "v1", "v2", "ver2", number-only
    elif re.match(r'^(v\d+|ver[_\s]?\d+|\d{1,3})$', stem_lower):
        score -= 35
    # Penalize names that are just the AE version: "CC 2020", "After Effects"
    elif re.match(r'^(cc\s*\d{4}|after\s*effects?)$', stem_lower):
        score -= 35

    # ── Pre-render / auto-save / copy penalties (from 23K scan) ──
    # Pre-rendered versions are secondary to the editable project
    if re.search(r'pre[_\-\s]?render', stem_lower):
        score -= 20
    # Auto-save files are never the main project
    if 'auto-save' in stem_lower or 'auto_save' in stem_lower:
        score -= 50
    # "copy" suffix indicates a duplicate
    if re.search(r'\bcopy\b', stem_lower):
        score -= 15
    # "(converted)" suffix from AE version conversion
    if '(converted)' in stem_lower:
        score -= 10

    # ── CC version preference (from 23K scan: CS/CC version pairs are most common multi-AEP pattern) ──
    cc_match = re.search(r'cc[_\s]?(\d{4})', stem_lower)
    if cc_match:
        cc_year = int(cc_match.group(1))
        if cc_year >= 2020:
            score += 8
        elif cc_year >= 2018:
            score += 5
    elif re.search(r'\bcc\b', stem_lower) and not re.match(r'^cc$', stem_lower):
        score += 3
    # CS versions are less preferred than CC
    if re.search(r'\b(cs[456]|cs5\.5)\b', stem_lower):
        score -= 8
    # ── Short name penalty ──
    alpha_count = sum(1 for c in stem if c.isalpha())
    if alpha_count <= 3:
        score -= 15
    elif alpha_count <= 5:
        score -= 5

    # ── Descriptive name bonus ──
    if alpha_count > 8 and stem_lower not in GENERIC_AEP_NAMES:
        score += 30
    elif alpha_count > 5 and stem_lower not in GENERIC_AEP_NAMES:
        score += 15

    # ── Folder name similarity bonus ──
    if stem_norm and folder_norm:
        stem_tokens = set(stem_norm.split())
        folder_tokens = set(folder_norm.split())
        # Remove noise tokens (numbers, short words)
        sig_stem = {t for t in stem_tokens if len(t) > 2 and not t.isdigit()}
        sig_folder = {t for t in folder_tokens if len(t) > 2 and not t.isdigit()}
        if sig_stem and sig_folder:
            overlap = sig_stem & sig_folder
            if overlap:
                score += min(20, len(overlap) * 10)

    # ── Size bonus (minor tiebreaker: log-scaled, max +8 points) ──
    if size > 0:
        # 1MB = +2, 10MB = +4, 100MB = +6, 1GB = +8
        score += min(8, max(0, int(math.log10(max(size, 1)) - 4)))

    return score, size


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORY ENGINE
# ══════════════════════════════════════════════════════════════════════════════

CATEGORIES = [
    # ══════════════════════════════════════════════════════════════════════════
    # ADOBE & DIGITAL DESIGN TOOLS
    # ══════════════════════════════════════════════════════════════════════════
    ("After Effects - Templates", ["after effects template", "ae template", "aep template", "ae project", "after effects project"]),
    ("After Effects - Intros & Openers", ["intro", "opener", "opening", "ae intro", "logo intro", "logo reveal", "logo sting", "logo animation", "intro sequence", "channel intro", "broadcast intro"]),
    ("After Effects - Slideshows", ["slideshow", "slide show", "photo slideshow", "video slideshow", "gallery slideshow", "memory slideshow", "image slideshow"]),
    ("After Effects - Titles & Typography", ["title sequence", "title animation", "kinetic typography", "kinetic type", "text animation", "animated title", "title reveal", "movie title", "film title", "cinematic title", "title pack", "animated text"]),
    ("After Effects - Lower Thirds", ["lower third", "lower thirds", "name tag", "l3rd", "lower 3rd", "call out", "callout", "callout title"]),
    ("After Effects - Transitions", ["transition", "transitions", "transition pack", "seamless transition", "glitch transition", "zoom transition", "ink transition", "liquid transition", "light transition", "smooth transition"]),
    ("After Effects - Logo Reveals", ["logo reveal", "logo animation", "logo sting", "logo intro", "logo opener", "3d logo", "logo template", "logo motion"]),
    ("After Effects - Infographics & Data", ["infographic", "infographics", "data visualization", "chart animation", "graph animation", "pie chart", "bar chart", "statistics", "animated chart", "data driven"]),
    ("After Effects - HUD & UI", ["hud", "heads up display", "sci-fi ui", "futuristic ui", "hud element", "hud pack", "interface animation", "screen ui", "hologram", "holographic", "tech ui"]),
    ("After Effects - Particles & FX", ["particle", "particles", "particle effect", "particular", "trapcode", "plexus", "stardust", "magic particles", "dust particles", "spark", "sparks"]),
    ("After Effects - Explainer & Promo", ["explainer", "explainer video", "product promo", "app promo", "website promo", "service promo", "corporate promo", "promotional video"]),
    ("After Effects - Character Animation", ["character animation", "character rig", "character", "animated character", "cartoon character", "rigged character", "duik", "rubberhose", "puppet", "limber"]),
    ("After Effects - Social Media Templates", ["social media template", "instagram template", "facebook template", "youtube template", "tiktok template", "social media pack", "stories template", "post template"]),
    ("After Effects - Broadcast Package", ["broadcast package", "broadcast design", "broadcast graphics", "channel branding", "tv package", "news package", "sports broadcast", "broadcast bundle"]),
    ("After Effects - Wedding & Events", ["wedding template", "wedding slideshow", "wedding intro", "wedding invitation video", "save the date video", "event promo", "event opener"]),
    ("After Effects - Photo & Gallery", ["photo gallery", "photo album", "photo animation", "photo template", "gallery template", "photo collage", "photo mosaic", "photo wall"]),
    ("After Effects - Countdown & Timer", ["countdown", "countdown timer", "timer", "clock animation", "new year countdown", "event countdown"]),
    ("After Effects - Presets & Scripts", ["ae preset", "ae presets", "after effects preset", "ae script", "after effects script", "expression", "expressions", "ae plugin", "aescript", "aescripts"]),
    ("After Effects - Map & Location", ["map animation", "map", "travel map", "world map", "animated map", "location pin", "route animation", "country map", "infographic map"]),
    ("After Effects - Lyric Video", ["lyric video", "lyrics", "lyric template", "lyrics video", "karaoke template"]),
    ("After Effects - Mockup & Device", ["device mockup", "phone mockup", "laptop mockup", "screen mockup", "app mockup", "website mockup", "mockup animation", "device animation"]),
    ("After Effects - Emoji & Stickers", ["emoji", "sticker", "stickers", "animated emoji", "animated sticker", "reaction", "emoticon"]),

    ("Premiere Pro - Templates", ["premiere pro template", "premiere template", "mogrt", "prproj", "premiere project"]),
    ("Premiere Pro - Transitions", ["premiere transition", "premiere transitions", "video transition", "film transition", "cinematic transition", "handy seamless"]),
    ("Premiere Pro - Titles & Text", ["premiere title", "mogrt title", "premiere text", "premiere lower third", "premiere caption"]),
    ("Premiere Pro - LUTs & Color", ["lut", "luts", "color grading", "color correction", "color grade", "color lookup", "cinematic lut", "film lut", "3dl", "cube lut"]),
    ("Premiere Pro - Presets & Effects", ["premiere preset", "premiere effect", "video effect", "film effect", "cinematic effect", "speed ramp", "premiere plugin"]),
    ("Premiere Pro - Sound Design", ["sound design", "audio design", "whoosh", "swoosh", "riser", "impact sound", "cinematic sound", "boom", "hit sound"]),

    ("Photoshop - Actions", ["photoshop action", "ps action", "photo action", "atn", "action set", "photo manipulation action", "retouching action", "color action", "hdr action"]),
    ("Photoshop - Brushes", ["photoshop brush", "ps brush", "abr", "brush set", "paint brush", "watercolor brush", "grunge brush", "smoke brush", "hair brush", "foliage brush", "cloud brush"]),
    ("Photoshop - Styles & Effects", ["photoshop style", "layer style", "asl", "text style", "photoshop effect", "photo effect", "double exposure", "dispersion", "shatter effect", "glitch effect"]),
    ("Photoshop - Overlays", ["photoshop overlay", "photo overlay", "light overlay", "rain overlay", "snow overlay", "fire overlay", "smoke overlay", "bokeh overlay", "lens flare overlay", "dust overlay", "scratch overlay"]),
    ("Photoshop - Mockups", ["mockup", "mock-up", "mockup psd", "product mockup", "packaging mockup", "branding mockup", "stationery mockup", "apparel mockup", "scene creator", "hero image"]),
    ("Photoshop - Templates & Composites", ["psd template", "photoshop template", "photo template", "composite", "photo composite", "manipulation", "photo manipulation", "matte painting"]),
    ("Photoshop - Retouching & Skin", ["retouch", "retouching", "skin retouch", "beauty retouch", "portrait retouch", "frequency separation", "dodge and burn", "skin smoothing"]),
    ("Photoshop - Patterns", ["photoshop pattern", "ps pattern", "pat file", "seamless pattern", "tileable pattern", "repeat pattern"]),
    ("Photoshop - Gradients & Swatches", ["gradient", "gradients", "swatch", "swatches", "color palette", "color scheme", "aco", "grd"]),
    ("Photoshop - Smart Objects & PSDs", ["smart object", "smart psd", "layered psd", "editable psd", "organized psd"]),
    ("Photoshop - Shapes & Custom Shapes", ["custom shape", "photoshop shape", "csh", "vector shape", "ps shape"]),

    ("Illustrator - Vectors & Assets", ["illustrator", "vector art", "vector illustration", "ai file", "eps file", "vector graphic", "vector pack", "vector set", "vector bundle"]),
    ("Illustrator - Brushes & Swatches", ["illustrator brush", "ai brush", "vector brush", "scatter brush", "pattern brush", "art brush", "illustrator swatch"]),
    ("Illustrator - Patterns & Styles", ["illustrator pattern", "vector pattern", "illustrator style", "graphic style"]),
    ("Illustrator - Icons & UI Kits", ["icon set", "icon pack", "icon bundle", "ui kit", "ui pack", "wireframe", "wireframe kit"]),

    ("InDesign - Templates & Layouts", ["indesign", "indd", "indesign template", "indesign layout", "indt", "idml"]),
    ("InDesign - Magazine & Editorial", ["magazine template", "magazine layout", "editorial", "editorial layout", "editorial design", "lookbook", "catalog layout"]),
    ("InDesign - Print Templates", ["print template", "print ready", "print design", "press ready", "cmyk", "bleed", "crop marks"]),

    ("Lightroom - Presets & Profiles", ["lightroom preset", "lr preset", "lightroom profile", "lrtemplate", "xmp preset", "dng preset", "lightroom mobile", "lightroom filter"]),

    # ══════════════════════════════════════════════════════════════════════════
    # MOTION GRAPHICS & VIDEO PRODUCTION
    # ══════════════════════════════════════════════════════════════════════════
    ("Motion Graphics", ["motion graphics", "motion design", "mograph", "animated graphic", "motion pack"]),
    ("Animated Backgrounds", ["animated background", "motion background", "video background", "loop background", "loopable background", "vj loop", "vj loops"]),
    ("Animated Icons", ["animated icon", "animated icons", "icon animation", "lottie", "bodymovin", "motion icon"]),
    ("Animated Elements", ["animated element", "animated shape", "shape animation", "geometric animation", "element pack", "motion element"]),
    ("Kinetic Typography", ["kinetic type", "kinetic typography", "type animation", "word animation", "lyric animation"]),
    ("Reveal & Unveil Animations", ["reveal", "unveil", "unfold", "uncover", "curtain reveal", "paper reveal"]),
    ("Glitch & Distortion FX", ["glitch", "glitch effect", "distortion", "digital distortion", "data glitch", "tv glitch", "rgb split", "chromatic aberration", "signal error", "bad tv", "vhs effect", "analog"]),
    ("Smoke & Fluid FX", ["smoke effect", "fluid", "fluid effect", "ink bleed", "ink drop", "watercolor animation", "liquid animation", "fluid dynamics", "flowing", "ink flow"]),
    ("Cinematic Effects", ["cinematic", "cinematic effect", "film grain", "film burn", "light leak", "anamorphic", "letterbox", "widescreen", "film strip", "film reel", "old film"]),
    ("Speed & Action FX", ["speed lines", "action lines", "comic effect", "anime effect", "manga effect", "energy", "power", "impact frame", "speed ramp"]),
    ("Nature & Weather FX", ["rain effect", "snow effect", "fog", "mist", "lightning", "thunder", "storm", "wind effect", "leaves falling", "falling snow", "weather"]),
    ("Fire & Explosion FX", ["fire effect", "explosion", "blast", "detonation", "shockwave", "fire burst", "fireball", "pyrotechnic", "flame effect"]),
    ("Light & Lens FX", ["lens flare", "light effect", "light ray", "light beam", "light streak", "optical flare", "sun ray", "god ray", "volumetric light", "prism"]),
    ("Parallax & Ken Burns", ["parallax", "parallax effect", "ken burns", "2.5d", "photo animation", "depth effect", "camera projection"]),
    ("Split Screen", ["split screen", "multiscreen", "multi screen", "screen split", "collage video"]),
    ("Frame & Border", ["frame", "border", "photo frame", "video frame", "decorative frame", "ornamental frame", "vintage frame"]),
    ("Countdown & Numbers", ["countdown", "number animation", "counter", "numeric", "timer animation", "number reveal"]),
    ("Call-Outs & Pointers", ["call out", "callout", "pointer", "annotation", "line callout", "info box", "tooltip animation"]),
    ("Ribbon & Banner Animations", ["ribbon animation", "banner animation", "flag animation", "waving", "cloth simulation"]),

    # ══════════════════════════════════════════════════════════════════════════
    # STOCK FOOTAGE & MEDIA
    # ══════════════════════════════════════════════════════════════════════════
    ("Stock Footage - General", ["stock footage", "stock video", "video clip", "footage", "royalty free video", "b-roll", "b roll", "broll"]),
    ("Stock Footage - Aerial & Drone", ["aerial footage", "drone footage", "drone shot", "aerial view", "birds eye", "drone video", "flyover"]),
    ("Stock Footage - Nature & Landscape", ["nature footage", "landscape footage", "mountain footage", "ocean footage", "forest footage", "waterfall footage", "sunset footage", "timelapse nature"]),
    ("Stock Footage - City & Urban", ["city footage", "urban footage", "timelapse city", "traffic footage", "street footage", "downtown footage", "nightlife footage"]),
    ("Stock Footage - People & Lifestyle", ["people footage", "lifestyle footage", "business people", "diverse people", "crowd footage", "family footage"]),
    ("Stock Footage - Technology", ["technology footage", "computer footage", "screen footage", "data center", "server room", "coding footage", "tech footage"]),
    ("Stock Footage - Green Screen", ["green screen", "chroma key", "greenscreen", "blue screen", "keying"]),
    ("Stock Footage - Slow Motion", ["slow motion", "slow mo", "slowmo", "high speed", "high frame rate"]),
    ("Stock Footage - Timelapse", ["timelapse", "time lapse", "hyperlapse", "hyper lapse"]),
    ("Stock Footage - Abstract & VFX", ["abstract footage", "abstract video", "vfx footage", "visual effects footage", "cgi footage", "fractal", "kaleidoscope"]),
    ("Stock Footage - Countdown Leaders", ["countdown leader", "film leader", "academy leader", "film countdown", "reel leader"]),
    ("Stock Photos - General", ["stock photo", "stock image", "stock photography", "royalty free photo", "royalty free image"]),
    ("Stock Photos - People & Portraits", ["portrait photo", "headshot", "people photo", "model photo", "lifestyle photo"]),
    ("Stock Photos - Food & Drink", ["food photo", "food photography", "food stock", "drink photo", "beverage photo"]),
    ("Stock Photos - Business", ["business photo", "office photo", "corporate photo", "meeting photo", "teamwork photo"]),
    ("Stock Photos - Nature & Outdoors", ["nature photo", "landscape photo", "outdoor photo", "scenery photo"]),
    ("Stock Photos - Flat Lay & Styled", ["flat lay", "flatlay", "styled stock", "styled photo", "desktop photo", "workspace photo", "styled scene"]),
    ("Stock Music & Audio", ["stock music", "royalty free music", "background music", "production music", "music track", "audio track", "music loop", "audio loop"]),
    ("Sound Effects & SFX", ["sound effect", "sound effects", "sfx", "foley", "ambient sound", "ambiance", "audio sfx", "whoosh", "impact", "riser"]),

    # ══════════════════════════════════════════════════════════════════════════
    # DESIGN ELEMENTS & ASSETS
    # ══════════════════════════════════════════════════════════════════════════
    ("3D", ["3d", "three dimensional", "3d render", "3d model", "cinema4d", "c4d", "blender3d", "element 3d", "3d object", "3d scene", "3d asset", "3d text", "3d logo"]),
    ("3D - Models & Objects", ["3d model", "obj", "fbx", "3ds", "stl", "3d object", "3d prop", "3d asset pack"]),
    ("3D - Materials & Textures", ["3d material", "3d texture", "pbr material", "pbr texture", "substance", "material pack", "shader", "hdri", "hdr environment", "environment map"]),
    ("3D - Scenes & Environments", ["3d scene", "3d environment", "3d room", "3d stage", "3d studio", "virtual set", "virtual studio"]),
    ("Abstract", ["abstract", "generative", "procedural", "abstract art", "abstract design"]),
    ("Alpha Channels & Mattes", ["alpha channel", "alpha matte", "matte", "luma matte", "track matte"]),
    ("Animated GIFs & Cinemagraphs", ["gif", "animated gif", "cinemagraph", "living photo"]),
    ("Backgrounds & Textures", ["background", "backgrounds", "texture", "textures", "wallpaper", "pattern", "backdrop", "studio background"]),
    ("Badges & Emblems", ["badge", "badges", "emblem", "crest", "seal", "stamp", "vintage badge"]),
    ("Banners", ["banner", "banners", "web banner", "display banner", "ad banner", "leaderboard", "skyscraper"]),
    ("Borders & Dividers", ["border", "divider", "separator", "line divider", "decorative border", "ornamental border"]),
    ("Brushes & Presets", ["brush", "brushes", "preset", "presets", "procreate brush"]),
    ("Buttons & UI Elements", ["button", "buttons", "ui element", "web element", "ui component", "gui element"]),
    ("Clipart & Illustrations", ["clipart", "clip art", "illustration", "vector", "svg", "hand drawn", "doodle", "sketch"]),
    ("Color Palettes & Swatches", ["color palette", "color scheme", "swatch", "swatches", "color combination"]),
    ("Confetti & Celebration FX", ["confetti", "streamer", "party popper", "celebration effect", "balloon pop"]),
    ("Dust & Debris", ["dust", "debris", "dirt", "grime", "particle debris", "floating dust"]),
    ("Flares & Light Effects", ["flare", "flares", "lens flare", "light leak", "bokeh", "light effect", "glow", "neon", "anamorphic flare"]),
    ("Flat Design", ["flat design", "flat style", "material design", "flat icon", "flat illustration"]),
    ("Frames & Borders", ["frame", "frames", "photo frame", "picture frame", "border", "decorative frame", "ornate frame"]),
    ("Grunge & Distressed", ["grunge", "distressed", "grungy", "scratch", "scratches", "noise", "grain", "film grain"]),
    ("Icons & Symbols", ["icon", "icons", "symbol", "glyph", "icon set", "iconography", "line icon", "filled icon", "outline icon"]),
    ("Isometric Design", ["isometric", "isometric illustration", "isometric icon", "isometric design", "iso", "2.5d illustration"]),
    ("Maps & Cartography", ["map", "maps", "cartography", "world map", "country map", "city map", "infographic map"]),
    ("Mockups - Apparel", ["tshirt mockup", "hoodie mockup", "apparel mockup", "clothing mockup", "hat mockup", "cap mockup"]),
    ("Mockups - Branding", ["branding mockup", "stationery mockup", "identity mockup", "logo mockup", "brand mockup"]),
    ("Mockups - Devices", ["device mockup", "phone mockup", "iphone mockup", "macbook mockup", "laptop mockup", "tablet mockup", "ipad mockup", "screen mockup", "monitor mockup"]),
    ("Mockups - Packaging", ["packaging mockup", "box mockup", "bag mockup", "bottle mockup", "can mockup", "pouch mockup", "label mockup"]),
    ("Mockups - Print", ["flyer mockup", "poster mockup", "magazine mockup", "book mockup", "brochure mockup", "business card mockup", "invitation mockup"]),
    ("Mockups - Signage", ["sign mockup", "signage mockup", "billboard mockup", "storefront mockup", "window mockup", "neon sign mockup"]),
    ("Overlays & Effects", ["overlay", "overlays", "effect", "effects", "photo overlay", "light overlay", "texture overlay"]),
    ("Patterns - Seamless", ["seamless pattern", "tileable", "repeat pattern", "surface pattern", "fabric pattern", "geometric pattern"]),
    ("PNG - Transparent Assets", ["png", "transparent", "cutout", "isolated", "png asset", "transparent background"]),
    ("Ribbons & Labels", ["ribbon", "ribbons", "label", "tag", "price tag", "sale tag", "decorative ribbon"]),
    ("Shapes & Geometric", ["shape", "shapes", "geometric", "polygon", "circle", "triangle", "hexagon", "abstract shape"]),
    ("Silhouettes", ["silhouette", "silhouettes", "shadow", "outline figure"]),
    ("Smoke & Fog", ["smoke", "fog", "mist", "haze", "atmosphere", "atmospheric", "smoke png"]),
    ("Sparkle & Glitter", ["sparkle", "glitter", "shimmer", "twinkle", "shine", "star burst"]),
    ("Splash & Paint", ["splash", "paint splash", "ink splash", "color splash", "paint splatter", "watercolor splash"]),
    ("Vectors & SVG", ["vector", "vectors", "svg", "vector art", "vector graphic", "scalable vector"]),
    ("Watercolor & Artistic", ["watercolor", "watercolour", "artistic", "hand painted", "gouache", "acrylic"]),

    # ══════════════════════════════════════════════════════════════════════════
    # FONTS, TYPOGRAPHY & TEXT
    # ══════════════════════════════════════════════════════════════════════════
    ("Fonts & Typography", ["font", "fonts", "typography", "typeface", "lettering", "calligraphy", "handwriting", "otf", "ttf", "woff", "opentype", "truetype"]),
    ("Fonts - Display & Decorative", ["display font", "decorative font", "fancy font", "ornamental font", "headline font"]),
    ("Fonts - Script & Handwritten", ["script font", "handwritten font", "cursive font", "calligraphy font", "signature font", "brush font"]),
    ("Fonts - Sans Serif", ["sans serif", "sans-serif", "modern font", "clean font", "geometric font"]),
    ("Fonts - Serif", ["serif font", "classic font", "elegant font", "editorial font"]),
    ("Fonts - Monospace & Code", ["monospace font", "coding font", "mono font", "typewriter font"]),
    ("Font Collections", ["font collection", "font bundle", "font pack", "gomedia", "go media"]),
    ("Text Effects & Styles", ["text effect", "text style", "3d text", "font effect", "text animation", "text preset", "type effect", "letter effect"]),

    # ══════════════════════════════════════════════════════════════════════════
    # PRINT & DOCUMENT DESIGN
    # ══════════════════════════════════════════════════════════════════════════
    ("Flyers & Print", ["flyer", "flyers", "print", "printable", "print ready", "leaflet"]),
    ("Posters", ["poster", "posters", "wall art", "art print", "print poster"]),
    ("Brochures & Bi-Fold & Tri-Fold", ["brochure", "bi-fold", "bifold", "tri-fold", "trifold", "pamphlet"]),
    ("Business Cards", ["business card", "business cards", "visiting card", "name card"]),
    ("Resume & CV", ["resume", "cv", "curriculum vitae", "cover letter"]),
    ("Postcards", ["postcard", "postcards", "greeting card", "greetings card"]),
    ("Certificate", ["certificate", "diploma", "credential", "award certificate"]),
    ("Invitations & Save the Date", ["invitation", "invitations", "invite", "save the date", "rsvp", "announcement card"]),
    ("Letterhead & Stationery", ["letterhead", "stationery", "stationary", "envelope", "notepad"]),
    ("Rollup Banners & Signage", ["rollup", "roll-up", "signage", "sign", "yard sign", "pull up banner", "retractable banner"]),
    ("Billboard", ["billboard", "outdoor advertising", "large format"]),
    ("Menu Design", ["menu design", "restaurant menu", "food menu", "drink menu", "bar menu", "cafe menu"]),
    ("Calendar", ["calendar", "planner", "desk calendar", "wall calendar"]),
    ("Gift Voucher & Coupon", ["gift voucher", "gift card", "coupon", "gift certificate", "discount card", "loyalty card"]),
    ("Annual Report", ["annual report", "company report"]),
    ("Packaging & Product", ["packaging", "package design", "product packaging", "label", "box design", "die cut", "dieline"]),
    ("Book & Literature", ["book cover", "book fair", "bookmark", "books", "literature", "library", "reading", "ebook cover"]),
    ("Forms & Documents", ["form", "forms", "document", "worksheet", "contract"]),

    # ══════════════════════════════════════════════════════════════════════════
    # SOCIAL MEDIA & WEB
    # ══════════════════════════════════════════════════════════════════════════
    ("Social Media", ["social media", "social network", "twitter", "tiktok", "snapchat", "linkedin", "social post"]),
    ("Instagram & Stories", ["instagram", "insta", "ig stories", "reels", "ig post", "instagram carousel"]),
    ("Facebook & Social Covers", ["facebook", "fb cover", "social media cover", "facebook ad", "fb ad"]),
    ("YouTube & Video Platform", ["youtube", "youtuber", "vlog", "thumbnail", "youtube banner", "end screen", "end card", "subscribe", "youtube intro"]),
    ("Pinterest", ["pinterest", "pin design"]),
    ("Twitch & Streaming", ["twitch", "stream overlay", "streaming", "stream package", "stream alert", "webcam frame", "obs overlay", "stream deck", "gaming overlay"]),
    ("Email & Newsletter", ["email", "newsletter", "email template", "mailchimp", "email marketing", "html email"]),
    ("Blog & Content", ["blog", "blogging", "blog post", "content template"]),
    ("Website Design", ["website", "web design", "landing page", "homepage", "web template", "html template", "css template", "wordpress", "webflow"]),
    ("Mobile App Design", ["app design", "mobile app", "app ui", "mobile ui", "app screen", "app template"]),
    ("UI & UX Design", ["ui design", "ux design", "user interface", "user experience", "wireframe", "prototype", "ui kit", "design system"]),
    ("Ad & Banner Design", ["ad design", "banner ad", "google ads", "display ad", "web ad", "facebook ad", "instagram ad", "social ad"]),
    ("Thumbnails", ["thumbnail", "thumbnails", "youtube thumbnail", "video thumbnail"]),

    # ══════════════════════════════════════════════════════════════════════════
    # PRESENTATION & INFOGRAPHIC
    # ══════════════════════════════════════════════════════════════════════════
    ("Presentations & PowerPoint", ["presentation", "powerpoint", "pptx", "keynote", "slide", "slides", "slideshow", "google slides", "pitch deck"]),
    ("Infographic", ["infographic", "infographics", "data visualization", "chart", "diagram", "flowchart", "process diagram"]),

    # ══════════════════════════════════════════════════════════════════════════
    # LOGO & BRANDING
    # ══════════════════════════════════════════════════════════════════════════
    ("Logo & Identity", ["logo", "logos", "identity", "brand mark", "logotype", "logo design", "logo template", "brand identity"]),
    ("Branding & Identity Kits", ["branding kit", "brand kit", "identity kit", "brand guidelines", "style guide", "brand board"]),
    ("Design Inspiration Packs", ["inspiration pack", "identity pack", "branding pack", "mega branding", "toolkit", "graphics toolkit", "pixelsquid", "juicedrops"]),

    # ══════════════════════════════════════════════════════════════════════════
    # VIDEO & CINEMA
    # ══════════════════════════════════════════════════════════════════════════
    ("Cinema & Film", ["cinema", "film", "movie", "theater", "theatre", "screening", "premiere", "hollywood", "trailer", "storyboard"]),
    ("Documentary", ["documentary", "docuseries", "doc film", "mini doc"]),
    ("Music Video", ["music video", "mv", "music clip", "performance video"]),
    ("VFX & Compositing", ["vfx", "visual effects", "compositing", "green screen", "chroma key", "rotoscope", "matte painting", "cgi"]),
    ("Color Grading & LUTs", ["color grading", "color correction", "lut", "luts", "color grade", "color lookup", "cinematic lut", "film lut", "3dl", "cube"]),
    ("Video Editing - General", ["video editing", "video edit", "film editing", "cut", "montage", "compilation"]),
    ("Drone & Aerial Video", ["drone", "aerial", "drone shot", "aerial video", "fpv", "quadcopter"]),
    ("Slow Motion & High Speed", ["slow motion", "slow mo", "slowmo", "high speed", "high frame rate", "ramping"]),
    ("Timelapse & Hyperlapse", ["timelapse", "time lapse", "hyperlapse", "hyper lapse", "time ramp"]),
    ("Stop Motion", ["stop motion", "stop-motion", "claymation", "frame by frame"]),
    ("Screen Recording & Tutorial", ["screen recording", "screencast", "tutorial video", "how to video", "walkthrough"]),
    ("Aspect Ratio & Letterbox", ["letterbox", "widescreen", "anamorphic", "cinemascope", "aspect ratio", "pillarbox"]),

    # ══════════════════════════════════════════════════════════════════════════
    # AUDIO & MUSIC PRODUCTION
    # ══════════════════════════════════════════════════════════════════════════
    ("Music", ["music", "musical", "musician", "band", "album", "playlist", "vinyl", "record", "audio", "sound"]),
    ("Music - Loops & Beats", ["music loop", "drum loop", "beat", "beats", "drum kit", "sample pack", "loop pack"]),
    ("Music - Cinematic & Orchestral", ["cinematic music", "orchestral", "epic music", "trailer music", "film score", "soundtrack"]),
    ("Music - Electronic & EDM", ["electronic music", "edm music", "techno", "house music", "trance", "dubstep", "synthwave"]),
    ("Music - Ambient & Chill", ["ambient music", "chill music", "lofi", "lo-fi", "relaxing music", "meditation music", "calm"]),
    ("Music - Corporate & Upbeat", ["corporate music", "upbeat", "uplifting", "positive music", "happy music", "motivational music"]),
    ("Podcast & Voiceover", ["podcast", "voiceover", "voice over", "narration", "podcast intro", "podcast template"]),
    ("Audio Visualizer", ["audio visualizer", "music visualizer", "spectrum", "equalizer", "audio spectrum", "waveform"]),

    # ══════════════════════════════════════════════════════════════════════════
    # PHOTOGRAPHY & IMAGE EDITING
    # ══════════════════════════════════════════════════════════════════════════
    ("Art & Photography", ["art photography", "photography", "photo studio", "photographer", "camera", "photoshoot", "polaroid"]),
    ("Photography Presets & Actions", ["photoshop", "lightroom", "actions", "styles", "presets", "photo editing", "photo filter"]),
    ("HDR & Tone Mapping", ["hdr", "high dynamic range", "tone mapping", "hdr effect", "hdr photo"]),
    ("Black & White Photography", ["black and white", "monochrome", "grayscale", "bw photo", "noir"]),
    ("Long Exposure", ["long exposure", "light trail", "light painting", "motion blur photo", "smooth water"]),
    ("Macro & Close-Up", ["macro", "close up", "closeup", "micro", "detail shot"]),
    ("Portrait Photography", ["portrait", "headshot", "portrait photography", "portrait lighting", "portrait retouch"]),
    ("Product Photography", ["product photography", "product photo", "product shoot", "ecommerce photo", "catalog photo"]),
    ("Flat Lay & Styled Photography", ["flat lay", "flatlay", "styled stock", "styled photo", "desktop photo", "workspace photo"]),

    # ══════════════════════════════════════════════════════════════════════════
    # TOPICS, THEMES & EVENTS
    # ══════════════════════════════════════════════════════════════════════════
    ("Accounting & Finance", ["accountant", "accounting", "bookkeeping", "income tax", "tax refund", "tax", "invoice", "invoices", "financial", "finance", "money", "bank", "stocks", "stock market", "trading", "investment", "bitcoin", "crypto", "cryptocurrency", "blockchain"]),
    ("Advertising & Marketing", ["advertising", "advertisement", "marketing", "promo", "promotional", "commerce", "seo", "branding", "brand identity"]),
    ("Africa & Afro", ["africa", "african", "afro"]),
    ("Agriculture & Farming", ["agriculture", "farming", "farm", "harvest", "crop"]),
    ("Air Balloon", ["air balloon", "hot air balloon"]),
    ("Aircraft & Aviation", ["aircraft", "airplane", "plane", "aviation", "flight", "jet", "airline", "airport"]),
    ("Alternative Energy", ["alternative power", "alternative energy", "solar power", "solar panel", "wind turbine", "renewable", "green energy"]),
    ("Amusement Park", ["amusement park", "theme park", "roller coaster", "carnival ride"]),
    ("Animals & Pets", ["animal", "animals", "pet", "pets", "pet shop", "dog", "cat", "puppy", "kitten", "wildlife", "zoo", "veterinary", "vet"]),
    ("Anniversary", ["anniversary"]),
    ("April Fools Day", ["april fool", "april fools"]),
    ("Arabian & Middle Eastern", ["arabian", "arabic", "middle eastern", "ramadan", "eid", "mosque", "islamic"]),
    ("Archery", ["archery", "bow and arrow"]),
    ("Architecture & Construction", ["architecture", "architectural", "construction", "building", "contractor", "blueprint"]),
    ("Armed Forces & Military", ["armed forces", "military", "army", "navy", "marines", "air force", "troops", "memorial day", "camo", "camouflage"]),
    ("Arts & Crafts", ["arts", "crafts", "handmade", "artisan"]),
    ("Astrology & Zodiac", ["astrology", "zodiac", "horoscope", "star sign"]),
    ("Auction", ["auction", "bidding"]),
    ("Australia Day", ["australia day", "aussie"]),
    ("Autism Awareness", ["autism"]),
    ("Awards & Ceremonies", ["awards", "award ceremony", "oscars", "grammy", "emmy", "golden globe", "trophy"]),
    ("Baby & Newborn", ["baby", "newborn", "infant", "baby shower", "nursery"]),
    ("Bachelor & Bachelorette", ["bachelor", "bachelorette"]),
    ("Bakery & Pastry", ["bakery", "pastry", "bread", "baking", "donut", "cupcake"]),
    ("Balloons", ["balloon", "balloons"]),
    ("Bar & Nightlife", ["bar lounge", "sports bar", "nightclub", "nightlife", "lounge", "cocktail bar", "hookah", "shisha", "pub crawl", "wine bar"]),
    ("Barbershop & Grooming", ["barbershop", "barber", "grooming", "mens grooming", "haircut", "movember"]),
    ("Baseball", ["baseball", "softball"]),
    ("Basketball", ["basketball", "nba", "hoops"]),
    ("Bat Mitzvah", ["bat mitzvah", "bar mitzvah", "mitzvah"]),
    ("Beach & Coastal", ["beach", "coastal", "ocean", "seaside", "shore", "surfing", "surf"]),
    ("Beauty, Fashion & Spa", ["beauty", "fashion", "spa", "hair salon", "nail salon", "cosmetic", "makeup", "skincare", "glamour"]),
    ("Beer & Alcohol", ["beer", "alcohol", "whiskey", "vodka", "rum", "tequila", "spirits", "liquor", "wine", "winery", "brewery", "craft beer", "happy hour", "cocktail"]),
    ("Bike & Cycling", ["bike", "bicycle", "cycling", "mountain bike", "bmx", "motorcycle", "motorbike", "biker"]),
    ("Billiards & Pool", ["billiard", "billiards", "pool table", "snooker"]),
    ("Bingo", ["bingo"]),
    ("Birthday", ["birthday", "bday"]),
    ("Black Friday", ["black friday"]),
    ("Black History Month", ["black history", "african american history"]),
    ("Black Party & Dark Themes", ["black party", "all black", "dark party", "black and red"]),
    ("Blood Drive", ["blood drive", "blood donation", "donate blood"]),
    ("Blues & Jazz", ["blues", "jazz", "blues festival", "jazz festival", "smooth jazz"]),
    ("Boat & Yacht", ["boat", "yacht", "sailing", "marina", "cruise", "nautical"]),
    ("Boss Day", ["boss day", "bosses day"]),
    ("Bowling", ["bowling"]),
    ("Boxing & MMA", ["boxing", "mma", "mixed martial arts", "ufc", "fight night", "wrestling"]),
    ("Burning Man", ["burning man"]),
    ("Business & Corporate", ["business", "corporate", "company", "enterprise", "professional", "office", "consulting"]),
    ("Cab & Taxi", ["cab", "taxi", "rideshare", "uber", "lyft"]),
    ("Cabaret & Burlesque", ["cabaret", "burlesque"]),
    ("Cafe & Restaurant", ["cafe", "restaurant", "diner", "bistro", "dining", "food truck"]),
    ("Cake & Chocolate", ["cake", "chocolate", "dessert", "confectionery", "candy", "sweets"]),
    ("Call Center & Support", ["call center", "customer service", "helpdesk"]),
    ("Camp & Outdoors", ["camp", "camping", "outdoor", "outdoors", "hiking", "trail", "wilderness", "nature"]),
    ("Canada Day", ["canada day", "canadian"]),
    ("Cancer Awareness", ["cancer", "breast cancer", "pink ribbon", "relay for life"]),
    ("Car & Auto", ["car wash", "car show", "car dealership", "automobile", "mechanic", "automotive", "dealership", "vehicle", "auto repair", "auto body", "car rental"]),
    ("Career & Job Fair", ["career expo", "career fair", "job fair", "job vacancy", "hiring", "recruitment", "jobs", "trades", "employment"]),
    ("Carnival & Mardi Gras", ["carnival", "mardi gras", "fat tuesday", "masquerade"]),
    ("Catering", ["catering", "caterer", "banquet"]),
    ("Charity & Fundraiser", ["charity", "fundraiser", "fundraising", "donation", "nonprofit", "benefit", "volunteer"]),
    ("Cheerleading", ["cheerleading", "cheerleader", "cheer"]),
    ("Chess", ["chess"]),
    ("Children & Kids", ["children", "childrens", "kids", "toddler", "playground"]),
    ("Chinese & Lunar New Year", ["chinese", "chinese new year", "lunar new year"]),
    ("Christmas", ["christmas", "xmas", "santa", "noel", "yuletide", "advent"]),
    ("Church & Gospel", ["church", "gospel", "worship", "faith", "christian", "religious", "spiritual", "praise", "sermon", "good friday"]),
    ("Cinco de Mayo", ["cinco de mayo"]),
    ("Circus", ["circus", "big top", "ringmaster", "clown"]),
    ("City & Urban", ["city", "urban", "downtown", "metro", "skyline", "cityscape"]),
    ("Cleaning Service", ["cleaning service", "cleaning", "maid", "janitorial", "pressure washing"]),
    ("Clothing & Apparel", ["clothing", "tshirt", "t-shirt", "hoodie", "shoes", "sneaker", "apparel", "streetwear", "merch"]),
    ("Club & DJ", ["club", "dj", "nightclub", "night club", "edm", "electro", "electronic music", "rave", "dance party", "dj night"]),
    ("Coffee & Tea", ["coffee", "tea", "espresso", "latte", "barista"]),
    ("College & University", ["college", "university", "campus", "sorority", "fraternity"]),
    ("Colorful & Vibrant", ["colorful", "colourful", "vibrant", "rainbow", "multicolor"]),
    ("Columbus Day", ["columbus day"]),
    ("Comedy & Standup", ["comedy", "comedy show", "standup", "stand-up", "comedian"]),
    ("Communication", ["communication", "telecom"]),
    ("Community", ["community", "neighborhood", "town hall"]),
    ("Computer & IT Services", ["computer repair", "computer", "it services", "tech support", "hardware", "software"]),
    ("Concert & Live Music", ["concert", "live music", "live show", "gig"]),
    ("Conference & Summit", ["conference", "summit", "symposium", "seminar", "convention", "expo", "trade show"]),
    ("Cooking & Grill", ["cooking", "grill", "bbq", "barbecue", "cookout", "recipe", "chef"]),
    ("Cornhole", ["cornhole"]),
    ("Country Music", ["country music", "honky tonk", "bluegrass"]),
    ("Covers & Headers", ["cover", "covers", "facebook cover", "header", "timeline cover"]),
    ("COVID-19", ["covid", "covid19", "coronavirus", "pandemic", "quarantine", "vaccine"]),
    ("Crawfish & Seafood", ["crawfish", "crayfish", "seafood", "lobster", "shrimp", "fish fry"]),
    ("Cyber Monday", ["cyber monday"]),
    ("Dance", ["dance", "dancing", "dancer", "ballet", "salsa", "zumba"]),
    ("Dating & Romance", ["dating", "romance", "romantic", "love", "couples", "valentines", "valentine", "vday", "sweetest day"]),
    ("Dentist & Dental", ["dentist", "dental", "teeth", "orthodontist"]),
    ("Diet & Nutrition", ["diet", "nutrition", "meal plan", "healthy eating", "weight loss"]),
    ("Disco Party", ["disco", "disco party", "funk"]),
    ("Diving & Water Sports", ["diving", "scuba", "snorkeling", "water sport"]),
    ("Earth Day & Environment", ["earth day", "environment", "eco", "recycle", "sustainability", "climate"]),
    ("Easter", ["easter", "easter egg", "resurrection"]),
    ("Education & School", ["education", "school", "student", "teacher", "classroom", "learning", "academy", "tutoring", "training", "spelling bee", "admission"]),
    ("Election & Political", ["election", "political", "politics", "politicians", "campaign", "vote", "voting", "presidents day"]),
    ("Electrician & Electrical", ["electrician", "electrical", "wiring"]),
    ("Electronics & Technology", ["electronics", "technology", "tech", "gadget", "device", "smartphone", "mobile", "digital"]),
    ("Elegant & Luxury", ["elegant", "luxury", "premium", "classy", "sophisticated", "upscale", "vip", "red carpet"]),
    ("Entertainment", ["entertainment", "show", "variety show"]),
    ("Erotic & Adult", ["erotic", "sexy", "sensual"]),
    ("Events & Occasions", ["event", "events", "occasion", "celebration"]),
    ("Exterior & Landscape Design", ["exterior design", "landscape", "landscaping", "garden", "gardening", "patio"]),
    ("Eye & Optical", ["eye exam", "optical", "optometrist", "eyewear", "vision"]),
    ("Family", ["family", "family day", "reunion", "family reunion", "high school reunion"]),
    ("Fathers Day", ["fathers day", "father's day", "dad"]),
    ("Festival", ["festival", "fest", "festive"]),
    ("Fire & Fireworks", ["fire", "flame", "fireworks", "pyro", "bonfire"]),
    ("Fishing", ["fishing", "angler", "bass fishing", "fly fishing"]),
    ("Fitness & Gym", ["fitness", "gym", "workout", "exercise", "bodybuilding", "crossfit", "personal trainer"]),
    ("Flags & Patriotic", ["flag", "flags", "patriotic", "independence day", "4th of july", "fourth of july", "flag day"]),
    ("Florist & Flowers", ["florist", "flower", "flowers", "floral", "bouquet", "rose", "blossom"]),
    ("Food & Menu", ["food", "food menu", "meal", "snack", "fast food"]),
    ("Football", ["football", "nfl", "super bowl", "touchdown"]),
    ("Funeral & Memorial", ["funeral", "memorial", "obituary", "remembrance"]),
    ("Furniture & Interior", ["furniture", "home decor", "interior design", "interior", "home improvement"]),
    ("Futuristic & Sci-Fi", ["future", "futuristic", "sci-fi", "scifi", "cyberpunk", "space", "galaxy", "cosmic", "astronaut"]),
    ("Games & Gaming", ["game", "games", "gaming", "gamer", "esports", "video game", "arcade", "game of thrones", "harry potter"]),
    ("Garage Sale & Yard Sale", ["garage sale", "yard sale", "flea market", "rummage sale"]),
    ("Gay & LGBT Pride", ["gay", "lgbt", "lgbtq", "pride", "queer", "transgender"]),
    ("Girls Night & Ladies Night", ["girls night", "ladies night"]),
    ("Gold & Metallic", ["gold", "golden", "metallic", "silver", "bronze", "chrome"]),
    ("Golf", ["golf", "golfing", "golf course"]),
    ("Graduation & Prom", ["graduation", "grad", "commencement", "prom", "class of"]),
    ("Graffiti & Street Art", ["graffiti", "street art", "mural", "spray paint"]),
    ("Grand Opening", ["grand opening", "now open", "ribbon cutting", "store opening"]),
    ("Halloween", ["halloween", "spooky", "haunted", "trick or treat", "costume", "witch", "zombie", "horror"]),
    ("Handyman & Home Repair", ["handyman", "home repair", "plumber", "plumbing", "hvac", "air conditioner"]),
    ("Hanukkah & Jewish Holidays", ["hanukkah", "chanukah", "jewish", "passover", "rosh hashanah", "kwanzaa"]),
    ("Health & Medical", ["health", "medical", "healthcare", "pharmacy", "hospital", "doctor", "nurse", "clinic", "wellness"]),
    ("Hockey", ["hockey", "nhl", "ice hockey"]),
    ("Holidays & Seasonal", ["holiday", "holidays", "seasonal"]),
    ("Home Security", ["home security", "security camera", "alarm system", "surveillance"]),
    ("Hotel & Hospitality", ["hotel", "hospitality", "resort", "lodge", "motel"]),
    ("Ice Cream & Frozen", ["ice cream", "gelato", "frozen yogurt", "popsicle"]),
    ("Indie & Alternative", ["indie", "indie music", "alternative", "acoustic"]),
    ("Insurance", ["insurance", "life insurance", "coverage"]),
    ("Isometric Design", ["isometric", "isometric design"]),
    ("Karaoke", ["karaoke", "sing along", "open mic"]),
    ("Kentucky Derby", ["kentucky", "derby", "horse racing"]),
    ("Labor Day", ["labor day", "labour day", "workers day"]),
    ("Laundry & Dry Cleaning", ["laundry", "dry cleaning", "laundromat"]),
    ("Lawn Care & Landscaping", ["lawn care", "lawn mowing", "yard work", "lawn service"]),
    ("Lawyer & Legal", ["lawyer", "legal", "attorney", "law firm", "court", "justice"]),
    ("Marijuana & Cannabis", ["marijuana", "cannabis", "hemp", "weed", "420", "dispensary", "cbd"]),
    ("Martin Luther King Day", ["martin luther king", "mlk"]),
    ("Masks", ["mask", "masks", "masquerade mask"]),
    ("Minimal & Clean", ["minimal", "minimalist", "clean style", "simple"]),
    ("Mothers Day", ["mothers day", "mother's day", "mom"]),
    ("Multipurpose", ["multipurpose", "multi-purpose", "all purpose"]),
    ("New Year", ["new year", "new years", "nye", "countdown"]),
    ("Olympic Games", ["olympic", "olympics"]),
    ("Paintball", ["paintball", "airsoft"]),
    ("Party & Celebration", ["party", "celebration", "fiesta", "bash"]),
    ("Pizza & Italian", ["pizza", "italian", "pasta", "pizzeria"]),
    ("Poker & Casino", ["poker", "gambling", "casino", "slot", "blackjack", "roulette", "jackpot"]),
    ("Polar Plunge", ["polar plunge"]),
    ("Pool Party", ["pool party", "swimming pool"]),
    ("Quotes & Motivational", ["quote", "quotes", "motivational", "inspirational"]),
    ("Rap & Hip Hop", ["rap", "hip hop", "hiphop", "rap battle", "freestyle", "emcee"]),
    ("Real Estate", ["real estate", "property", "house", "realtor", "realty", "mortgage"]),
    ("Retirement", ["retirement", "retire", "pension"]),
    ("Retro & Vintage", ["retro", "vintage", "classic", "old school", "throwback", "60s", "70s", "80s", "90s", "nostalgia"]),
    ("Running & Marathon", ["running", "marathon", "5k", "10k", "jogging"]),
    ("Saint Patricks Day", ["saint patrick", "st patrick", "shamrock", "irish", "leprechaun"]),
    ("Shop & Retail", ["shop", "store", "retail", "boutique", "sale", "clearance"]),
    ("Soccer", ["soccer", "futbol"]),
    ("Sports", ["sport", "sports", "athletic", "athlete", "championship", "tournament", "league", "volleyball"]),
    ("Spring", ["spring", "springtime", "cherry blossom"]),
    ("Summer & Tropical", ["summer", "summertime", "tropical", "island", "palm tree", "hawaii"]),
    ("Tattoo", ["tattoo", "ink", "tattoo parlor", "body art"]),
    ("Thanksgiving & Fall", ["thanksgiving", "fall", "autumn", "harvest", "pumpkin", "turkey"]),
    ("Toy Drive", ["toy drive", "toy donation", "angel tree"]),
    ("Travel & Tourism", ["travel", "tourism", "tourist", "vacation", "trip", "wanderlust", "passport", "destination"]),
    ("TV & Broadcast", ["tv", "television", "broadcast"]),
    ("Vape & Smoke", ["vape", "vaping", "e-cigarette"]),
    ("Veterans Day", ["veterans day", "veteran"]),
    ("Wedding", ["wedding", "bride", "groom", "bridal", "engagement", "nuptial"]),
    ("Winter & Snow", ["winter", "snow", "snowflake", "blizzard", "frost", "skiing"]),
    ("Womens Day", ["women day", "womens day", "international women", "girl power"]),
    ("Yoga & Meditation", ["yoga", "yoga class", "meditation", "zen", "mindfulness", "chakra", "pilates"]),

    # ══════════════════════════════════════════════════════════════════════════
    # PLATFORMS & MARKETPLACES
    # ══════════════════════════════════════════════════════════════════════════
]

BUILTIN_CATEGORIES = list(CATEGORIES)  # Keep original copy

# ── Build TOPIC_CATEGORIES set ────────────────────────────────────────────────
# Topic categories describe WHAT a design is ABOUT ("Night Club", "Christmas")
# NOT what the design IS ("Flyers", "Business Cards").
# When design files (PSD/AI) are found in a topic-named folder,
# the context engine overrides the topic with the actual asset type.
TOPIC_CATEGORIES = set()
_in_topics = False
for _cat_name, _ in CATEGORIES:
    if _cat_name == "Accounting & Finance":
        _in_topics = True
    if _in_topics:
        TOPIC_CATEGORIES.add(_cat_name)
    if _cat_name == "Yoga & Meditation":
        break

# Also mark some non-topic categories that are too generic and should be overridden
# when design files + a specific topic are detected
TOPIC_CATEGORIES.update({
    'Cinema & Film', 'Music', 'Art & Photography', 'Photography Presets & Actions',
})

# ── Custom categories persistence ─────────────────────────────────────────────
_CUSTOM_CATS_FILE = os.path.join(_SCRIPT_DIR, 'custom_categories.json')

def load_custom_categories():
    """Load user-defined categories from JSON file."""
    if os.path.exists(_CUSTOM_CATS_FILE):
        try:
            with open(_CUSTOM_CATS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return [(c['name'], c['keywords']) for c in data]
        except Exception:
            pass
    return []

def save_custom_categories(custom_cats):
    """Save user-defined categories to JSON file."""
    data = [{'name': name, 'keywords': kws} for name, kws in custom_cats]
    with open(_CUSTOM_CATS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    _CategoryIndex.invalidate()  # Rebuild keyword index on next scan

def get_all_categories():
    """Return built-in + custom categories."""
    return BUILTIN_CATEGORIES + load_custom_categories()

def get_all_category_names():
    """Return sorted list of all category names."""
    return sorted(set(name for name, _ in get_all_categories()))


# ── Pre-computed category keyword index ──────────────────────────────────────
# Avoids calling _normalize() on every keyword for every folder during scan.
# Built once on first use, invalidated when custom categories change.
class _CategoryIndex:
    """Pre-normalized keyword index for fast category matching."""
    _instance = None
    _custom_cats_mtime = None

    def __init__(self):
        self._build()

    def _build(self):
        """Build the pre-normalized index from all categories."""
        all_cats = get_all_categories()
        # Pre-normalized list: [(cat_name, cat_norm, [(kw, kw_norm, kw_tokens_sig), ...]), ...]
        self.entries = []
        for cat_name, keywords in all_cats:
            cat_norm = _normalize(cat_name)
            kw_list = []
            for kw in keywords:
                kw_norm = _normalize(kw).strip()
                sig_tokens = frozenset(t for t in kw_norm.split() if len(t) > 2)
                kw_list.append((kw, kw_norm, sig_tokens))
            self.entries.append((cat_name, cat_norm, kw_list))
        try:
            self._custom_cats_mtime = os.path.getmtime(_CUSTOM_CATS_FILE) if os.path.exists(_CUSTOM_CATS_FILE) else None
        except OSError:
            self._custom_cats_mtime = None

    def _is_stale(self):
        """Check if custom categories file has changed since last build."""
        try:
            current = os.path.getmtime(_CUSTOM_CATS_FILE) if os.path.exists(_CUSTOM_CATS_FILE) else None
        except OSError:
            current = None
        return current != self._custom_cats_mtime

    @classmethod
    def get(cls):
        """Get the singleton index, rebuilding if stale."""
        if cls._instance is None or cls._instance._is_stale():
            cls._instance = cls()
        return cls._instance

    @classmethod
    def invalidate(cls):
        """Force rebuild on next access (call after editing custom categories)."""
        cls._instance = None

# ── Undo / operation log ──────────────────────────────────────────────────────
_UNDO_LOG_FILE = os.path.join(_SCRIPT_DIR, 'undo_log.json')
_CSV_LOG_FILE = os.path.join(_SCRIPT_DIR, 'move_log.csv')

def save_undo_log(operations):
    """Save list of operations for undo. Each op: {type, src, dst, timestamp}"""
    with open(_UNDO_LOG_FILE, 'w', encoding='utf-8') as f:
        json.dump(operations, f, indent=2)

def load_undo_log():
    if os.path.exists(_UNDO_LOG_FILE):
        try:
            with open(_UNDO_LOG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []

def clear_undo_log():
    if os.path.exists(_UNDO_LOG_FILE):
        os.remove(_UNDO_LOG_FILE)

def append_csv_log(operations):
    """Append operations to CSV audit log."""
    exists = os.path.exists(_CSV_LOG_FILE)
    with open(_CSV_LOG_FILE, 'a', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(['Timestamp', 'Operation', 'Source', 'Destination', 'Category', 'Confidence', 'Status'])
        for op in operations:
            w.writerow([op.get('timestamp',''), op.get('type',''), op.get('src',''),
                        op.get('dst',''), op.get('category',''), op.get('confidence',''), op.get('status','')])

# ── File hashing for duplicate detection ──────────────────────────────────────
def hash_file(filepath, chunk_size=65536):
    """Fast MD5 hash of a file."""
    h = hashlib.md5()
    try:
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk: break
                h.update(chunk)
        return h.hexdigest()
    except (PermissionError, OSError):
        return None
# These are download sites, not content categories. The actual content name follows them.
MARKETPLACE_PREFIXES = [
    # Envato ecosystem
    "videohive", "graphicriver", "themeforest", "audiojungle", "photodune",
    "codecanyon", "envato elements", "envato", "envato market",
    # Stock media sites
    "shutterstock", "adobe stock", "istockphoto", "istock", "getty images", "getty",
    "depositphotos", "dreamstime", "123rf", "pond5", "storyblocks", "videoblocks",
    "audioblocks", "artlist", "artgrid", "epidemic sound", "musicbed",
    "motion array", "motionarray", "mixkit",
    "motionelements", "motion elements",
    # Design marketplaces
    "creative market", "creativemarket", "creative fabrica", "creativefabrica",
    "design bundles", "designbundles", "design cuts", "designcuts",
    "mighty deals", "mightydeals", "the hungry jpeg", "thehungryjpeg",
    "yellow images", "placeit", "smartmockups", "vecteezy", "vectorstock",
    "freepik", "flaticon", "pngtree", "pikbest", "lovepik",
    # Font sites
    "myfonts", "fontbundles", "font bundles", "fontspring", "linotype",
    "dafont", "fontsquirrel", "font squirrel",
    # Misc
    "pixelsquid", "juicedrops", "99designs", "fiverr", "upwork",
    "ui8", "craftwork", "ls graphics", "artstation",
    # Common abbreviations - ONLY match with separator + number: VH-12345, GR-9999
    # NOT in prefix list to avoid eating real words (ae->aerial, gr->grand)
]

# Pre-computed prefix lookups (actual initialization after _normalize is defined below)
_SORTED_PREFIXES = sorted(MARKETPLACE_PREFIXES, key=len, reverse=True)
_LOWER_PREFIX_SET = frozenset(p.lower() for p in MARKETPLACE_PREFIXES)

# Regex patterns for item IDs and noise to strip
_ID_PATTERNS = [
    r'^\d{5,}[\s\-_]',            # Leading numeric ID: "22832058-Christmas"
    r'[\s\-_]\d{5,}$',            # Trailing numeric ID: "Christmas-22832058"
    r'^[A-Z]{1,3}[\-_]\d{4,}[\s\-_]?',  # Prefixed ID: "VH-22832058", "GR-12345-"
    r'\(\d{5,}\)',                 # ID in parens: "(22832058)"
    r'\[\d{5,}\]',                 # ID in brackets: "[22832058]"
]

def _strip_source_name(folder_name: str) -> str:
    """Remove marketplace names, item IDs, and other noise from folder names.
    'Creative Market - Watercolor Brushes' -> 'Watercolor Brushes'
    'VH-22832058-Christmas-Slideshow' -> 'Christmas-Slideshow'
    """
    name = folder_name

    # Remove bracketed source names: [VideoHive], (CreativeMarket), {Envato}
    name = re.sub(r'[\[\(\{](.*?)[\]\)\}]', lambda m: '' if _normalize(m.group(1)) in
                  _NORMALIZED_PREFIX_SET else m.group(0), name)

    # Strip item ID patterns
    for pat in _ID_PATTERNS:
        name = re.sub(pat, '', name, flags=re.IGNORECASE)

    # Normalize to work with the name
    norm = name.strip()

    # Try stripping source prefixes with common separators: " - ", "-", "_", " "
    norm_lower = norm.lower().replace('-', ' ').replace('_', ' ')
    norm_lower = re.sub(r'\s+', ' ', norm_lower).strip()

    # Sort prefixes longest-first so "envato elements" matches before "envato"
    for prefix in _SORTED_PREFIXES:
        p_lower = prefix.lower()
        # Check if the normalized name starts with this prefix
        if norm_lower.startswith(p_lower):
            remainder = norm_lower[len(p_lower):].strip()
            # Must have meaningful content left after stripping
            if len(remainder) > 2:
                # Find where the prefix ends in the original string
                # Try matching with common separators
                for sep in [' - ', ' _ ', '-', '_', ' ']:
                    pattern = re.compile(re.escape(prefix) + re.escape(sep), re.IGNORECASE)
                    match = pattern.match(norm)
                    if match:
                        norm = norm[match.end():].strip()
                        norm_lower = norm.lower().replace('-', ' ').replace('_', ' ')
                        norm_lower = re.sub(r'\s+', ' ', norm_lower).strip()
                        break
                else:
                    # No separator found, try direct prefix strip
                    pattern = re.compile(re.escape(prefix) + r'[\s\-_]*', re.IGNORECASE)
                    match = pattern.match(norm)
                    if match and len(norm[match.end():].strip()) > 2:
                        norm = norm[match.end():].strip()
                        norm_lower = norm.lower().replace('-', ' ').replace('_', ' ')
                        norm_lower = re.sub(r'\s+', ' ', norm_lower).strip()

    # Clean up any leading/trailing separators left behind
    norm = re.sub(r'^[\s\-_.,]+|[\s\-_.,]+$', '', norm)

    # If result is itself a known marketplace name, it means we can't extract real content
    result_check = norm.lower().replace('-', ' ').replace('_', ' ')
    result_check = re.sub(r'\s+', ' ', result_check).strip()
    if result_check in _LOWER_PREFIX_SET:
        return folder_name

    return norm if len(norm) > 2 else folder_name


# ── International text support ───────────────────────────────────────────────
# Detect non-Latin scripts and transliterate to ASCII for keyword matching and naming.

import unicodedata

def _has_non_latin(text: str) -> bool:
    """Check if text contains significant non-Latin characters (CJK, Cyrillic, Arabic, etc.).
    Returns True if >25% of alpha characters are non-Latin."""
    if not text:
        return False
    alpha = [c for c in text if c.isalpha()]
    if not alpha:
        return False
    non_latin = sum(1 for c in alpha if ord(c) > 0x024F)  # Beyond Latin Extended-B
    return non_latin / len(alpha) > 0.25


def _detect_scripts(text: str) -> set:
    """Detect which Unicode script blocks are present in text.
    Returns set of script names: 'latin', 'cjk', 'cyrillic', 'arabic', 'thai', 'hangul', etc."""
    scripts = set()
    for c in text:
        cp = ord(c)
        if c.isspace() or not c.isalpha():
            continue
        if cp <= 0x024F:
            scripts.add('latin')
        elif 0x0400 <= cp <= 0x04FF or 0x0500 <= cp <= 0x052F:
            scripts.add('cyrillic')
        elif (0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF or
              0x20000 <= cp <= 0x2A6DF or 0xF900 <= cp <= 0xFAFF):
            scripts.add('cjk')
        elif 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
            scripts.add('japanese')
        elif 0xAC00 <= cp <= 0xD7AF or 0x1100 <= cp <= 0x11FF:
            scripts.add('hangul')
        elif 0x0600 <= cp <= 0x06FF or 0x0750 <= cp <= 0x077F:
            scripts.add('arabic')
        elif 0x0E00 <= cp <= 0x0E7F:
            scripts.add('thai')
        elif 0x0900 <= cp <= 0x097F:
            scripts.add('devanagari')
        else:
            scripts.add('other')
    return scripts


# Fallback Cyrillic→Latin transliteration table (when unidecode unavailable)
_CYRILLIC_MAP = str.maketrans({
    'а':'a', 'б':'b', 'в':'v', 'г':'g', 'д':'d', 'е':'e', 'ё':'yo', 'ж':'zh',
    'з':'z', 'и':'i', 'й':'y', 'к':'k', 'л':'l', 'м':'m', 'н':'n', 'о':'o',
    'п':'p', 'р':'r', 'с':'s', 'т':'t', 'у':'u', 'ф':'f', 'х':'kh', 'ц':'ts',
    'ч':'ch', 'ш':'sh', 'щ':'shch', 'ъ':'', 'ы':'y', 'ь':'', 'э':'e', 'ю':'yu',
    'я':'ya',
    'А':'A', 'Б':'B', 'В':'V', 'Г':'G', 'Д':'D', 'Е':'E', 'Ё':'Yo', 'Ж':'Zh',
    'З':'Z', 'И':'I', 'Й':'Y', 'К':'K', 'Л':'L', 'М':'M', 'Н':'N', 'О':'O',
    'П':'P', 'Р':'R', 'С':'S', 'Т':'T', 'У':'U', 'Ф':'F', 'Х':'Kh', 'Ц':'Ts',
    'Ч':'Ch', 'Ш':'Sh', 'Щ':'Shch', 'Ъ':'', 'Ы':'Y', 'Ь':'', 'Э':'E', 'Ю':'Yu',
    'Я':'Ya',
})


def _transliterate(text: str) -> str:
    """Transliterate non-Latin text to ASCII/Latin characters.
    Uses unidecode if available (best quality), falls back to Cyrillic table.
    Returns the original text if no transliteration is possible (e.g. CJK without unidecode)."""
    if not text or not _has_non_latin(text):
        return text

    if HAS_UNIDECODE:
        result = _unidecode(text)
        # Clean up: unidecode can produce brackets and junk for some chars
        result = re.sub(r'\[.*?\]', '', result)
        result = re.sub(r'\s+', ' ', result).strip()
        return result if result else text

    # Fallback: handle Cyrillic manually
    scripts = _detect_scripts(text)
    if 'cyrillic' in scripts:
        result = text.translate(_CYRILLIC_MAP)
        # Strip any remaining non-Latin after transliteration
        result = re.sub(r'[^\x00-\x7F]+', ' ', result)
        result = re.sub(r'\s+', ' ', result).strip()
        return result if result else text

    # CJK/Arabic/Thai without unidecode — can't transliterate meaningfully
    return text


@lru_cache(maxsize=4096)
def _normalize(text: str) -> str:
    t = text.lower()
    # Transliterate non-Latin characters to ASCII before stripping
    if _has_non_latin(t):
        t = _transliterate(t).lower()
    t = t.replace('-', ' ').replace('_', ' ').replace('.', ' ')
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t


# Now that _normalize is defined, build the normalized prefix set
_NORMALIZED_PREFIX_SET = frozenset(_normalize(p) for p in MARKETPLACE_PREFIXES)


# ── Name beautification pipeline ────────────────────────────────────────────
# Transforms raw marketplace folder names into clean, readable titles.
# Used as the non-LLM fallback for destination folder names.

# Words to strip entirely (noise that adds no meaning to the folder name)
_NOISE_WORDS = {
    # Version/quality tags
    'v1', 'v2', 'v3', 'v4', 'v5', 'v6', 'hq', 'hd', '4k', '1080p', '720p', 'uhd', '2k',
    # Status words
    'final', 'updated', 'new', 'free', 'premium', 'preview', 'sample', 'pro', 'lite',
    # File/format noise
    'psd', 'ai', 'eps', 'svg', 'aep', 'prproj', 'mogrt', 'indd', 'idml',
    'download', 'zip', 'rar',
    # License noise
    'personal use', 'commercial license', 'royalty free', 'rf',
}

# Common short marketplace prefix codes (2-3 letter + separator, no digits required)
_SHORT_PREFIX_PATTERN = re.compile(
    r'^(?:CM|EE|GR|VH|AJ|TF|CC|PD|CF|DF)[\s\-_]+',
    re.IGNORECASE
)

# Title case exceptions (stay lowercase unless first word)
_TITLE_LOWER = {'a', 'an', 'the', 'and', 'or', 'but', 'nor', 'for', 'of', 'in',
                'on', 'at', 'to', 'by', 'up', 'as', 'is', 'it', 'if', 'vs', 'via', 'with'}


def _beautify_name(folder_name: str) -> str:
    """Full name beautification pipeline for folder names.
    Strips marketplace noise, IDs, junk suffixes, normalizes separators,
    splits CamelCase, deduplicates tokens, and applies Title Case.

    '553035-Advertisment-Company-Flyer-Template' → 'Advertisement Company Flyer Template'
    'CM_NightClub-Party-Flyer-v2-PSD' → 'Night Club Party Flyer'
    'VH-22832058-Christmas-Slideshow-FINAL' → 'Christmas Slideshow'
    """
    name = folder_name

    # Step 0: Transliterate non-Latin text (Cyrillic, CJK, etc.) to ASCII
    if _has_non_latin(name):
        name = _transliterate(name)
        # If transliteration produced nothing useful, return the original as-is
        alpha_count = sum(1 for c in name if c.isalpha())
        if alpha_count < 2:
            return folder_name

    # Step 1: Strip marketplace prefixes and IDs (reuse existing function)
    name = _strip_source_name(name)

    # Step 1.5: Second-pass prefix strip on space-normalized name
    # Catches hyphenated multi-word prefixes like "envato-elements-..." where
    # _strip_source_name only partially strips (it matches "envato" but misses "envato elements")
    # Check both the original folder name and the stripped result
    for candidate in (folder_name, name):
        name_spaced = candidate.replace('-', ' ').replace('_', ' ')
        name_spaced = re.sub(r'\s+', ' ', name_spaced).strip()
        name_spaced_lower = name_spaced.lower()
        for prefix in _SORTED_PREFIXES:
            p_lower = prefix.lower()
            if name_spaced_lower.startswith(p_lower):
                remainder = name_spaced[len(p_lower):].strip()
                if len(remainder) > 2:
                    name = remainder
                    break
        else:
            continue  # No prefix matched this candidate, try next
        break  # Prefix matched and stripped, done

    # Step 2: Strip short marketplace prefix codes (CM_, EE_, GR_, VH_, etc)
    name = _SHORT_PREFIX_PATTERN.sub('', name).strip()

    # Step 3: Split CamelCase before normalizing separators
    # 'NightClubParty' → 'Night Club Party'
    name = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', name)
    name = re.sub(r'(?<=[A-Z])(?=[A-Z][a-z])', ' ', name)  # 'HTMLParser' → 'HTML Parser'

    # Step 4: Normalize separators to spaces
    name = name.replace('-', ' ').replace('_', ' ').replace('.', ' ')
    name = re.sub(r'\s+', ' ', name).strip()

    # Step 5: Strip noise words and version patterns
    tokens = name.split()
    cleaned_tokens = []
    for t in tokens:
        t_lower = t.lower()
        # Skip noise words
        if t_lower in _NOISE_WORDS:
            continue
        # Skip standalone version patterns: v1, v2.1, V3
        if re.match(r'^v\d+(\.\d+)?$', t_lower):
            continue
        # Skip bare large numbers (leftover IDs)
        if re.match(r'^\d{5,}$', t):
            continue
        # Skip dimension patterns like 300x250, 1920x1080
        if re.match(r'^\d{2,4}x\d{2,4}$', t_lower):
            continue
        cleaned_tokens.append(t)

    # Step 6: Deduplicate consecutive repeated tokens
    # 'Flyer Flyer Template' → 'Flyer Template'
    deduped = []
    for t in cleaned_tokens:
        if not deduped or t.lower() != deduped[-1].lower():
            deduped.append(t)

    # Step 7: Apply Title Case
    result_tokens = []
    for i, t in enumerate(deduped):
        if i == 0:
            # First word always capitalized
            result_tokens.append(t.capitalize() if t.islower() or t.isupper() else t)
        elif t.lower() in _TITLE_LOWER and len(t) <= 4:
            result_tokens.append(t.lower())
        elif t.isupper() and len(t) > 1:
            # ALL CAPS → Title Case (but preserve short acronyms like 'DJ', 'FX')
            if len(t) <= 3:
                result_tokens.append(t.upper())
            else:
                result_tokens.append(t.capitalize())
        else:
            result_tokens.append(t.capitalize() if t.islower() else t)

    result = ' '.join(result_tokens).strip()

    # Safety: if we stripped everything, return the _strip_source_name result
    if len(result) < 3:
        result = _strip_source_name(folder_name)
        # At minimum, normalize separators
        result = result.replace('-', ' ').replace('_', ' ')
        result = re.sub(r'\s+', ' ', result).strip()

    return result


# Generic asset-type names that indicate the LLM stripped too aggressively.
# These are meaningless as folder names because the category already conveys this.
_GENERIC_ASSET_NAMES = {
    _normalize(n) for n in [
        'Flyer', 'Flyer Template', 'Flyers', 'Template', 'Templates',
        'Business Card', 'Business Card Template', 'Business Cards',
        'Poster', 'Poster Template', 'Posters',
        'Brochure', 'Brochure Template', 'Brochures',
        'Slideshow', 'Slideshow Template', 'Presentation', 'Presentation Template',
        'Logo', 'Logo Template', 'Logo Design',
        'Mockup', 'Mockup Template', 'Mockup PSD',
        'Resume', 'Resume Template', 'CV Template',
        'Certificate', 'Certificate Template',
        'Invitation', 'Invitation Template',
        'Banner', 'Banner Template', 'Web Banner',
        'Social Media', 'Social Media Template', 'Social Media Post',
        'Intro', 'Outro', 'Opener', 'Title', 'Titles',
        'Lower Third', 'Lower Thirds', 'Transition', 'Transitions',
        'After Effects Template', 'Premiere Template', 'Photoshop Template',
        'Project', 'Design', 'Asset', 'Pack', 'Bundle', 'Kit', 'Set',
    ]
}


def _is_generic_name(name: str, category: str) -> bool:
    """Check if a cleaned name is just a generic asset type that restates the category.
    Returns True if the name should be rejected in favor of a rule-based fallback."""
    norm = _normalize(name)
    if not norm or len(norm) < 3:
        return True
    # Direct match against known generic names
    if norm in _GENERIC_ASSET_NAMES:
        return True
    # Check if the name is just the category name or a substring of it
    cat_norm = _normalize(category)
    if norm == cat_norm:
        return True
    # Name is a subset of category words (e.g., "Templates" for "After Effects - Templates")
    name_tokens = set(norm.split())
    cat_tokens = set(cat_norm.split())
    if name_tokens and name_tokens.issubset(cat_tokens):
        return True
    return False


# ── Project name hint extraction ─────────────────────────────────────────────
# Scans folder contents for AEP/project file names and meaningful subfolders
# to discover the real project name when the folder name is generic or noisy.

# Asset/utility folder names that should NEVER be used as project name sources.
# Matches both plain ("footage") and parenthesized ("(Footage)") variants.
_ASSET_FOLDER_NAMES = frozenset({
    # Generic asset/resource folders
    'assets', 'asset', 'source', 'src', 'dist', 'build', 'output',
    'export', 'render', 'renders', 'preview', 'previews', 'temp',
    'tmp', 'cache', '__macosx', '.ds_store', 'footage', 'fonts',
    'images', 'img', 'audio', 'video', 'music', 'sound', 'sounds',
    'textures', 'materials', 'elements', 'components', 'layers',
    'compositions', 'comps', 'precomps', 'help', 'docs', 'documentation',
    'readme', 'license', 'licenses', 'media', 'resources', 'data',
    'backup', 'backups', 'old', 'original', 'originals', 'raw',
    'final', 'finals', 'versions', 'archive', 'archives',
    'screenshots', 'thumbs', 'thumbnails', 'icons', 'sprites',
    'overlays', 'transitions', 'effects', 'fx', 'sfx', 'luts',
    'presets', 'scripts', 'expressions', 'plugins', 'extras',
    # Web/dev project structure folders
    'themes', 'ui', 'animations', 'demo', 'bootstrap', 'bootstrap-colorpick',
    'js', 'css', 'code', 'pages', 'includes', 'helpers', 'modules',
    'examples', 'integration', 'styling', 'lib', 'workflows',
    # Font/link/doc folders
    'font', 'font link', 'links', 'demo link', 'logo',
    # Media/music folders
    'soundtrack', 'manual', 'github',
    # ── Discovered from 23K-folder library scan (v5.4) ──
    # App/format named folders (contain project files, not project names)
    'after effects', 'aftereffects', 'after effect', 'ae',
    'photoshop', 'psd', 'ai', 'eps', 'pdf', 'word', 'ms word',
    'jpg', 'jpeg', 'jpegs', 'png', 'html', 'scss',
    # Container/wrapper folders
    'main', 'main file', 'main files', 'mainfile', 'main 1',
    'project', 'project file', 'project files',
    'file', 'files', 'misc', 'other', 'bonus',
    # Numbered project containers (common Envato pattern)
    '01. project file', '01. project', '02. project',
    '01 - help files', '02 project files',
    '01. help', '00. help', '00_help',
    '03. assets', '03. others',
    # Tutorial/help folders
    'tutorial', 'tutorials', 'video tutorial', 'videotutorial',
    'help file', 'help files', 'help documentation',
    'user guide', 'read me', '00_read_me_first',
    '01_watch_video_tutorials',
    # Color space / size variant folders
    'cmyk', 'cmyk-psd', 'a4', 'us letter', 'us letter size', 'letter',
    # Media subfolders
    'photo', 'footages', 'loops', 'element', '3d',
    'free font', 'audio link',
    # Marketing spam folders
    '~get your graphic files',
    # Photoshop source folders
    '01_photoshop_files', 'psd files', 'flyer-sourcefiles',
})

# Project file extensions whose filenames are most likely to contain the real project name
_PROJECT_NAME_EXTS = {'.aep', '.aet', '.prproj', '.psd', '.psb', '.mogrt', '.ai', '.indd'}

# Generic project filenames to skip (the file itself has no useful name)
_GENERIC_PROJECT_NAMES = frozenset({
    'main', 'project', 'comp', 'composition', 'untitled', 'new project',
    'final', 'final project', 'edit', 'master', 'output', 'render',
    'preview', 'thumbnail', 'template', 'source', 'original', 'backup',
    'copy', 'test', 'temp', 'draft', 'wip', 'v1', 'v2', 'v3',
    # Chinese generic names (discovered from 23K scan)
    '\u5de5\u7a0b\u6587\u4ef6',  # "project file" in Chinese
    '\u6587\u4ef6',        # "file" in Chinese
    '\u6a21\u677f',        # "template" in Chinese
})


def _extract_name_hints(folder_path: str) -> list:
    """Scan a folder for project file names and meaningful subfolder names.
    Returns a list of (name_hint, source, priority) sorted best-first.

    Sources: 'aep', 'prproj', 'psd', 'mogrt', 'subfolder'
    Priority: higher = better quality hint (0-100)

    Example: folder contains 'Christmas_Slideshow.aep' and subfolder '(Footage)'
    Returns: [('Christmas Slideshow', 'aep', 90)]
    """
    hints = []
    if not folder_path or not os.path.isdir(folder_path):
        return hints

    try:
        for root, dirs, files in os.walk(folder_path):
            rel = os.path.relpath(root, folder_path)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > 2:
                dirs.clear(); continue

            # ── Collect project file name hints ──
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext not in _PROJECT_NAME_EXTS:
                    continue

                # Clean the filename (strip extension, separators, IDs)
                raw_name = os.path.splitext(f)[0]
                # Strip leading/trailing noise
                clean = re.sub(r'^\d{5,}[\s\-_]*', '', raw_name)  # Leading IDs
                clean = re.sub(r'[\s\-_]*\d{5,}$', '', clean)     # Trailing IDs
                clean = clean.replace('-', ' ').replace('_', ' ').replace('.', ' ')
                clean = re.sub(r'\s+', ' ', clean).strip()

                # Transliterate non-Latin characters (Chinese, Russian, etc.)
                if _has_non_latin(clean):
                    clean = _transliterate(clean)
                    clean = re.sub(r'\s+', ' ', clean).strip()

                if len(clean) < 3:
                    continue
                if clean.lower() in _GENERIC_PROJECT_NAMES:
                    continue
                # Skip if it's just the marketplace prefix
                if _normalize(clean) in _NORMALIZED_PREFIX_SET:
                    continue

                # Priority based on file type (AEP/PRPROJ are strongest signals)
                if ext in ('.aep', '.aet'):
                    priority = 90
                elif ext == '.prproj':
                    priority = 88
                elif ext == '.mogrt':
                    priority = 85
                elif ext in ('.psd', '.psb'):
                    priority = 75  # PSD names can be generic layer exports
                elif ext == '.ai':
                    priority = 72
                elif ext in ('.indd',):
                    priority = 70
                else:
                    priority = 60

                # Depth penalty (deeper = less likely to be the main project)
                priority -= depth * 8

                hints.append((clean, ext.lstrip('.'), priority))

            # ── Collect meaningful subfolder name hints (depth 0 only) ──
            if depth == 0:
                for d in dirs:
                    d_lower = d.lower().strip()
                    d_stripped = re.sub(r'^[\(\[\{]|[\)\]\}]$', '', d_lower).strip()
                    if d_stripped in _ASSET_FOLDER_NAMES or d_lower in _ASSET_FOLDER_NAMES:
                        continue
                    if len(d_stripped) < 3:
                        continue
                    # Only use subfolders that look like project names (not generic)
                    d_clean = d.replace('-', ' ').replace('_', ' ')
                    d_clean = re.sub(r'\s+', ' ', d_clean).strip()
                    if _normalize(d_clean) not in _GENERIC_PROJECT_NAMES:
                        hints.append((d_clean, 'subfolder', 50))

    except (PermissionError, OSError):
        pass

    # Sort by priority (highest first), deduplicate by normalized name
    hints.sort(key=lambda x: -x[2])
    seen = set()
    unique = []
    for name, source, priority in hints:
        norm = _normalize(name)
        if norm not in seen:
            seen.add(norm)
            unique.append((name, source, priority))
    return unique[:10]  # Cap at 10 hints


def _smart_name(folder_name: str, folder_path: str = None, category: str = None) -> str:
    """Intelligent project naming using folder name + project file/subfolder hints.
    Falls back to _beautify_name() when no better name is found.

    Logic:
    1. Beautify the folder name
    2. If the result is generic, noisy, or mostly numeric — look for AEP/project file hints
    3. Pick the best hint and beautify it
    4. If the hint is also generic, fall back to the beautified folder name
    """
    beautified = _beautify_name(folder_name)

    # Check if the beautified name needs improvement
    needs_hints = False

    # Case 1: Name is a generic asset type that restates the category
    if category and _is_generic_name(beautified, category):
        needs_hints = True

    # Case 2: Name is mostly numeric (leftover IDs not fully stripped)
    if not needs_hints:
        alpha_chars = sum(1 for c in beautified if c.isalpha())
        digit_chars = sum(1 for c in beautified if c.isdigit())
        if digit_chars > alpha_chars:
            needs_hints = True

    # Case 3: Name is very short (likely just abbreviations/codes)
    if not needs_hints and len(beautified.replace(' ', '')) <= 4:
        needs_hints = True

    # Case 4: Name is a known marketplace prefix that survived stripping
    if not needs_hints and _normalize(beautified) in _NORMALIZED_PREFIX_SET:
        needs_hints = True

    # Case 5: Original folder name contains non-Latin characters (Chinese, Russian, etc.)
    # Transliteration may produce awkward results, so try project file hints first
    if not needs_hints and _has_non_latin(folder_name):
        needs_hints = True

    if not needs_hints:
        return beautified

    # Folder name was inadequate — try to find a better name from project files
    if not folder_path:
        return beautified

    hints = _extract_name_hints(folder_path)
    if not hints:
        return beautified

    # Try each hint, pick the first non-generic one
    for name, source, priority in hints:
        hint_beautified = _beautify_name(name)
        if len(hint_beautified) >= 3:
            if not category or not _is_generic_name(hint_beautified, category):
                return hint_beautified

    return beautified

def categorize_folder(folder_name: str) -> tuple:
    """Match folder name against categories. Returns (category, score, cleaned_name) or (None, 0, cleaned).
    Strips marketplace prefixes and item IDs before matching.
    Uses pre-computed keyword index for speed."""
    cleaned = _strip_source_name(folder_name)

    # If the folder IS a bare marketplace name (nothing was stripped), skip categorization
    name_check = _normalize(folder_name)
    if name_check in _NORMALIZED_PREFIX_SET:
        return (None, 0, cleaned)

    norm = _normalize(cleaned)
    norm_loose = _normalize(cleaned.lower().replace('-', ' ').replace('_', ' ').replace('.', ' '))
    tokens = set(norm.split())
    best_cat = None
    best_score = 0

    index = _CategoryIndex.get()

    for cat_name, cat_norm, kw_list in index.entries:
        score = 0

        # Auto-match: folder name matches category name itself
        if norm == cat_norm:
            return (cat_name, 100, cleaned)  # Perfect match, early exit
        elif len(norm) > 3 and norm in cat_norm:
            score = max(score, 50 + len(norm) * 2)

        for kw, kw_norm, sig_tokens in kw_list:
            # Exact full match
            if norm == kw_norm:
                score = 100
                break  # Can't do better than 100, exit keyword loop
            # Short keywords (<=4 chars) must be exact token matches
            elif len(kw_norm) <= 4 and kw_norm in tokens:
                score = max(score, 50 + len(kw_norm) * 2)
            # Longer phrase found in folder name
            elif len(kw_norm) > 4 and kw_norm in norm:
                score = max(score, 50 + len(kw_norm) * 2)
            # Folder name found within keyword (reverse: "chill" inside "chill music")
            elif len(norm) > 3 and norm in kw_norm:
                score = max(score, 50 + len(norm) * 2)
            # Phrase found in loose name
            elif len(kw_norm) > 4 and kw_norm in norm_loose:
                score = max(score, 45 + len(kw_norm) * 2)
            else:
                # Token overlap (using pre-computed significant tokens)
                if sig_tokens:
                    matching = sig_tokens & tokens
                    if matching:
                        token_score = (len(matching) / len(sig_tokens)) * 40
                        if len(matching) > 1:
                            token_score += len(matching) * 5
                        score = max(score, token_score)

        if score >= 100:
            return (cat_name, 100, cleaned)  # Early exit on perfect match
        if score > best_score:
            best_score = score
            best_cat = cat_name

    if best_score >= 15:
        return (best_cat, min(best_score, 100), cleaned)
    return (None, 0, cleaned)


# ══════════════════════════════════════════════════════════════════════════════
# TIERED CLASSIFICATION ENGINE (v4.0)
# Level 1: Extension mapping (deterministic, instant)
# Level 2: Keyword matching (existing engine + fuzzy via rapidfuzz)
# Level 3: Metadata extraction (.prproj XML, .psd layers, Envato API)
# Level 4: Metadata-enriched re-classification
# ══════════════════════════════════════════════════════════════════════════════

# ── Level 1: Extension-based classification ───────────────────────────────────
# Maps dominant file extensions to categories with base confidence.
# When >50% of files in a folder share an extension group, classification is near-certain.

EXTENSION_CATEGORY_MAP = [
    # (extension_set, category, base_confidence)
    # NOTE: Every category name here MUST exist in CATEGORIES or custom_categories
    ({'.ttf', '.otf', '.woff', '.woff2'},       "Fonts & Typography",                95),
    ({'.cube', '.3dl'},                          "Premiere Pro - LUTs & Color",       92),
    ({'.lut'},                                   "Premiere Pro - LUTs & Color",       92),
    ({'.lrtemplate'},                             "Lightroom - Presets & Profiles",    92),
    ({'.xmp'},                                   "Lightroom - Presets & Profiles",    85),
    ({'.abr'},                                   "Photoshop - Brushes",               92),
    ({'.atn'},                                   "Photoshop - Actions",               92),
    ({'.grd'},                                   "Photoshop - Gradients & Swatches",  90),
    ({'.pat'},                                   "Photoshop - Patterns",              90),
    ({'.asl'},                                   "Photoshop - Styles & Effects",      90),
    ({'.ffx'},                                   "After Effects - Presets & Scripts",  90),
    ({'.mogrt'},                                  "Premiere Pro - Templates",          92),
    ({'.jsx', '.jsxbin'},                        "After Effects - Presets & Scripts",  85),
    ({'.c4d'},                                   "3D",                                88),
    ({'.blend'},                                 "3D",                                88),
    ({'.obj', '.fbx', '.stl', '.3ds', '.dae'},  "3D - Models & Objects",             82),
    ({'.aep', '.aet'},                           "After Effects - Templates",         65),
    ({'.prproj'},                                "Premiere Pro - Templates",          65),
    ({'.psd', '.psb'},                           "Photoshop - Templates & Composites", 70),
    ({'.ai'},                                    "Illustrator - Vectors & Assets",    70),
    ({'.indd', '.idml'},                         "InDesign - Templates & Layouts",    85),
    ({'.svg'},                                   "Vectors & SVG",                     75),
    ({'.eps'},                                   "Illustrator - Vectors & Assets",    75),
]

def classify_by_extensions(folder_path: str) -> tuple:
    """Level 1: Classify folder by dominant file extension pattern.
    Returns (category, confidence, method_detail) or (None, 0, '')."""
    ext_counts = Counter()
    total_project_files = 0

    try:
        for root, dirs, files in os.walk(folder_path):
            rel = os.path.relpath(root, folder_path)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > 3: dirs.clear(); continue  # Cap traversal depth
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext and ext not in {'.txt', '.html', '.htm', '.url', '.ini', '.log',
                                        '.md', '.json', '.xml', '.csv', '.rtf', '.nfo',
                                        '.ds_store', '.zip', '.rar', '.7z'}:
                    ext_counts[ext] += 1
                    total_project_files += 1
    except (PermissionError, OSError):
        return (None, 0, '')

    if total_project_files == 0:
        return (None, 0, '')

    best = (None, 0, '')

    for ext_set, category, base_conf in EXTENSION_CATEGORY_MAP:
        matching = sum(ext_counts.get(e, 0) for e in ext_set)
        if matching == 0:
            continue

        ratio = matching / total_project_files

        # Confidence scales with how dominant the extension type is
        if ratio >= 0.7:
            conf = base_conf
        elif ratio >= 0.4:
            conf = base_conf - 10
        elif ratio >= 0.15:
            conf = base_conf - 20
        elif matching >= 2:
            conf = base_conf - 30
        else:
            continue

        # Bonus for higher absolute count (more files = more certain)
        if matching >= 10:
            conf = min(conf + 5, 100)

        ext_list = ', '.join(f"{e}({ext_counts[e]})" for e in ext_set if ext_counts.get(e, 0) > 0)
        if conf > best[1]:
            best = (category, conf, f"ext:{ext_list} ({ratio:.0%} of {total_project_files} files)")

    return best


# ── Level 1.5: Folder content structure analysis ─────────────────────────────
# Uses file composition patterns to infer asset type when extensions alone are mixed.

def analyze_folder_composition(folder_path: str) -> dict:
    """Analyze file composition of a folder for classification signals.
    Returns dict with extension counts, dominant types, and structural indicators."""
    ext_counts = Counter()
    subfolder_names = []
    total_size = 0
    file_count = 0

    try:
        for root, dirs, files in os.walk(folder_path):
            rel = os.path.relpath(root, folder_path)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth == 0:
                subfolder_names = [d.lower() for d in dirs]
            if depth > 3:
                dirs.clear(); continue
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext:
                    ext_counts[ext] += 1
                    file_count += 1
                    try:
                        total_size += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
    except (PermissionError, OSError):
        pass

    return {
        'ext_counts': dict(ext_counts),
        'subfolder_names': subfolder_names,
        'total_size': total_size,
        'file_count': file_count,
        'has_footage': any(d in subfolder_names for d in ['footage', 'video', 'media', 'clips']),
        'has_audio': any(d in subfolder_names for d in ['audio', 'music', 'sound', 'sfx']),
        'has_preview': any(d in subfolder_names for d in ['preview', 'previews', 'thumbnail', 'thumbnails']),
    }


# ── Level 3: Metadata extraction ─────────────────────────────────────────────

def extract_prproj_metadata(filepath: str) -> list:
    """Extract sequence/clip names from .prproj files (gzipped XML).
    Returns list of name strings useful for categorization."""
    names = []
    try:
        with gzip.open(filepath, 'rt', encoding='utf-8', errors='ignore') as f:
            content = f.read(500_000)  # Cap read to 500KB

        # Search for descriptive elements in Premiere XML
        # Match content inside common name/title tags
        for pattern in [
            r'<(?:Name|Title|SequenceName|ActualName|n)>(.*?)</(?:Name|Title|SequenceName|ActualName|n)>',
            r'ObjectURef="([^"]+)"',
            r'<Label>(.*?)</Label>',
        ]:
            for match in re.finditer(pattern, content, re.IGNORECASE):
                name = match.group(1).strip()
                if (name and len(name) > 3
                    and not name.startswith(('Sequence', 'Untitled', 'Comp'))
                    and not name.isdigit()
                    and not re.match(r'^[0-9a-f\-]{20,}$', name)):  # Skip UUIDs
                    names.append(name)
    except Exception:
        pass
    return names[:20]  # Cap results


def extract_psd_metadata(filepath: str) -> list:
    """Extract layer names and metadata from .psd files via psd-tools.
    Falls back gracefully if psd-tools not installed."""
    if not HAS_PSD_TOOLS:
        return []
    names = []
    try:
        psd = _psd_tools.PSDImage.open(filepath)
        for layer in psd.descendants():
            if hasattr(layer, 'name') and layer.name:
                name = layer.name.strip()
                # Skip generic Photoshop layer names
                if name.lower() not in {'layer 1', 'layer 2', 'layer 3', 'background',
                                          'group 1', 'group 2', 'copy', 'shape 1', 'shape 2',
                                          'layer', 'group', 'effect', 'mask'}:
                    names.append(name)
        # Also extract document info if available
        if hasattr(psd, 'image_resources'):
            pass  # Could extract title from IPTC/XMP but keeping it simple
    except Exception:
        pass
    return names[:30]  # Cap results


# Envato item code pattern: 7-8 digit numbers common in Envato downloads
_ENVATO_ID_PATTERN = re.compile(r'(?:^|[\-_\s])(\d{7,8})(?:[\-_\s]|$)')

def detect_envato_item_code(folder_name: str) -> str:
    """Detect Envato marketplace item codes in folder names.
    Returns the item code string or empty string."""
    match = _ENVATO_ID_PATTERN.search(folder_name)
    return match.group(1) if match else ''


def extract_folder_metadata(folder_path: str, log_cb=None) -> dict:
    """Extract all available metadata from files inside a folder.
    Returns dict with keywords, project_names, envato_id, etc."""
    metadata = {
        'keywords': [],         # Keywords extracted from file metadata
        'project_names': [],    # Named sequences, compositions, etc.
        'envato_id': '',        # Envato item code if detected
        'primary_app': '',      # Detected primary Adobe app
        'has_aep': False,
        'has_prproj': False,
        'has_psd': False,
        'has_mogrt': False,
    }

    folder_p = Path(folder_path)

    # Detect Envato item code from folder name
    metadata['envato_id'] = detect_envato_item_code(folder_p.name)

    # Scan files for metadata (limit depth and count for performance)
    scanned = 0
    max_scan = 10  # Max files to parse metadata from

    try:
        for item in folder_p.rglob('*'):
            if not item.is_file():
                continue
            ext = item.suffix.lower()

            # Track what app-specific files exist
            if ext in ('.aep', '.aet'):
                metadata['has_aep'] = True
                metadata['primary_app'] = metadata['primary_app'] or 'After Effects'
            elif ext == '.prproj':
                metadata['has_prproj'] = True
                metadata['primary_app'] = metadata['primary_app'] or 'Premiere Pro'
                if scanned < max_scan:
                    names = extract_prproj_metadata(str(item))
                    metadata['project_names'].extend(names)
                    scanned += 1
            elif ext in ('.psd', '.psb'):
                metadata['has_psd'] = True
                metadata['primary_app'] = metadata['primary_app'] or 'Photoshop'
                if scanned < max_scan and HAS_PSD_TOOLS:
                    names = extract_psd_metadata(str(item))
                    metadata['keywords'].extend(names)
                    scanned += 1
            elif ext == '.mogrt':
                metadata['has_mogrt'] = True
                metadata['primary_app'] = metadata['primary_app'] or 'After Effects'

            if scanned >= max_scan:
                break
    except (PermissionError, OSError):
        pass

    return metadata


# ── Level 3.5: Envato API metadata enrichment ────────────────────────────────

# Envato API category → FileOrganizer category mapping
_ENVATO_CAT_MAP = {
    'after-effects-project-files': 'After Effects - Templates',
    'after-effects-presets': 'After Effects - Presets & Scripts',
    'after-effects-scripts': 'After Effects - Presets & Scripts',
    'premiere-pro-templates': 'Premiere Pro - Templates',
    'premiere-pro-presets': 'Premiere Pro - Presets & Effects',
    'motion-graphics': 'Motion Graphics',
    'stock-footage': 'Stock Footage - General',
    'stock-music': 'Stock Music & Audio',
    'sound-effects': 'Sound Effects & SFX',
    'fonts': 'Fonts & Typography',
    'graphics': 'Illustrator - Vectors & Assets',
    'add-ons': 'Photoshop - Actions',
    'photos': 'Stock Photos - General',
    'video-templates': 'Video Editing - General',
    'presentation-templates': 'Presentations & PowerPoint',
    '3d': '3D - Models & Objects',
    'logos': 'Logo & Identity',
    'product-mockups': 'Photoshop - Mockups',
    'infographics': 'Infographic',
    'web-templates': 'UI & UX Design',
    'backgrounds': 'Backgrounds & Textures',
    'textures': 'Photoshop - Patterns',
    'icons': 'Illustrator - Icons & UI Kits',
    'illustrations': 'Clipart & Illustrations',
}

# Persistent API key storage path
_ENVATO_KEY_FILE = os.path.join(_SCRIPT_DIR, 'envato_api_key.txt')

def _load_envato_api_key() -> str:
    """Load Envato API key from file. Returns empty string if not set."""
    try:
        with open(_ENVATO_KEY_FILE, 'r') as f:
            return f.read().strip()
    except (FileNotFoundError, OSError):
        return ''

def _save_envato_api_key(key: str):
    """Save Envato API key to file."""
    try:
        with open(_ENVATO_KEY_FILE, 'w') as f:
            f.write(key.strip())
    except OSError:
        pass

# Simple in-memory cache for API responses
_envato_cache = {}

def _envato_api_classify(item_id: str) -> tuple:
    """Query Envato Market API to get item category and tags.
    Returns (category, confidence, detail) or (None, 0, '').
    Requires API key stored in envato_api_key.txt alongside the script."""
    if not item_id:
        return (None, 0, '')

    api_key = _load_envato_api_key()
    if not api_key:
        return (None, 0, '')

    # Check cache
    if item_id in _envato_cache:
        return _envato_cache[item_id]

    try:
        import urllib.request, urllib.error
        url = f"https://api.envato.com/v3/market/catalog/item?id={item_id}"
        req = urllib.request.Request(url, headers={
            'Authorization': f'Bearer {api_key}',
            'User-Agent': 'FileOrganizer/3.0'
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode('utf-8'))

        # Extract classification signals
        api_cat = data.get('classification', '')
        api_tags = data.get('tags', [])
        api_name = data.get('name', '')

        # Try direct category mapping
        cat_slug = api_cat.lower().replace(' ', '-') if api_cat else ''
        for envato_key, fo_cat in _ENVATO_CAT_MAP.items():
            if envato_key in cat_slug:
                result = (fo_cat, 88, f"envato_api:{item_id}→{api_cat}")
                _envato_cache[item_id] = result
                return result

        # Fallback: classify the API-provided item name through keyword engine
        if api_name:
            kw_cat, kw_conf, _ = categorize_folder(api_name)
            if kw_cat and kw_conf >= 40:
                result = (kw_cat, min(kw_conf + 15, 92), f"envato_name:\"{api_name}\"")
                _envato_cache[item_id] = result
                return result

        # Fallback: try classifying tags
        for tag in api_tags[:5]:
            t_cat, t_conf, _ = categorize_folder(tag)
            if t_cat and t_conf >= 60:
                result = (t_cat, min(t_conf + 5, 85), f"envato_tag:\"{tag}\"")
                _envato_cache[item_id] = result
                return result

    except Exception:
        pass

    _envato_cache[item_id] = (None, 0, '')
    return (None, 0, '')


# ── Level 4: Folder composition heuristics ───────────────────────────────────
# Uses structural patterns (subfolder names + extension mixtures) for classification.

# Composition patterns: (condition_fn, category, base_confidence, description)
def _classify_by_composition(comp: dict) -> tuple:
    """Classify based on folder composition analysis.
    Returns (category, confidence, detail) or (None, 0, '')."""
    ext = comp.get('ext_counts', {})
    subs = comp.get('subfolder_names', [])
    total = comp.get('file_count', 0)

    if total == 0:
        return (None, 0, '')

    # Count file types by category
    video_exts = sum(ext.get(e, 0) for e in ['.mp4', '.mov', '.avi', '.wmv', '.mkv', '.webm'])
    audio_exts = sum(ext.get(e, 0) for e in ['.mp3', '.wav', '.flac', '.aif', '.ogg', '.aac'])
    image_exts = sum(ext.get(e, 0) for e in ['.jpg', '.jpeg', '.png', '.tif', '.tiff', '.gif', '.webp'])
    vector_exts = sum(ext.get(e, 0) for e in ['.svg', '.eps', '.ai'])
    font_exts = sum(ext.get(e, 0) for e in ['.ttf', '.otf', '.woff', '.woff2'])
    doc_exts = sum(ext.get(e, 0) for e in ['.pdf', '.pptx', '.docx', '.xlsx', '.indd', '.idml'])

    # ── Subfolder structure heuristics ──

    # AEP + Footage subfolder = After Effects Template with footage
    if ext.get('.aep', 0) >= 1 and comp.get('has_footage'):
        return ('After Effects - Templates', 72, f"composition:.aep+/footage/ subfolder")

    # AEP + Audio subfolder = likely a full template pack
    if ext.get('.aep', 0) >= 1 and comp.get('has_audio'):
        return ('After Effects - Templates', 68, f"composition:.aep+/audio/ subfolder")

    # Multiple video files without project files = stock footage
    if video_exts >= 5 and video_exts / total >= 0.5:
        return ('Stock Footage - General', 75, f"composition:{video_exts} video files ({video_exts/total:.0%})")

    # Multiple audio files = music/sound pack
    if audio_exts >= 5 and audio_exts / total >= 0.5:
        return ('Stock Music & Audio', 75, f"composition:{audio_exts} audio files ({audio_exts/total:.0%})")

    # Photo-heavy folder (lots of JPGs/PNGs, few other types)
    if image_exts >= 10 and image_exts / total >= 0.7:
        return ('Stock Photos - General', 65, f"composition:{image_exts} images ({image_exts/total:.0%})")

    # Vector-heavy folder
    if vector_exts >= 3 and vector_exts / total >= 0.3:
        return ('Vectors & SVG', 65, f"composition:{vector_exts} vectors ({vector_exts/total:.0%})")

    # Font-heavy (lower threshold than Level 1 since this is fallback)
    if font_exts >= 2 and font_exts / total >= 0.3:
        return ('Fonts & Typography', 65, f"composition:{font_exts} font files ({font_exts/total:.0%})")

    # Document templates
    if doc_exts >= 2 and doc_exts / total >= 0.3:
        if ext.get('.pptx', 0) >= 1:
            return ('Presentations & PowerPoint', 60, f"composition:{doc_exts} docs (pptx found)")
        if ext.get('.indd', 0) >= 1 or ext.get('.idml', 0) >= 1:
            return ('InDesign - Templates & Layouts', 65, f"composition:InDesign files found")
        return ('Forms & Documents', 55, f"composition:{doc_exts} document files")

    # Texture/pattern folder: many identically-sized images, no project files
    if image_exts >= 8 and not any(ext.get(e, 0) for e in ['.aep', '.psd', '.prproj', '.ai']):
        return ('Backgrounds & Textures', 55, f"composition:{image_exts} images, no project files")

    return (None, 0, '')


# ── Perceptual Hash Deduplication ────────────────────────────────────────────

def _compute_phash(filepath: str, hash_size: int = 8) -> str:
    """Compute perceptual hash of an image using average hash algorithm.
    Pure Python implementation using PIL - no heavy ML dependencies.
    Returns hex string of the hash, or empty string on failure."""
    try:
        from PIL import Image
        img = Image.open(filepath).convert('L').resize((hash_size + 1, hash_size), Image.LANCZOS)
        pixels = list(img.getdata())
        # Difference hash (dHash): compare adjacent pixels
        bits = []
        for row in range(hash_size):
            for col in range(hash_size):
                bits.append(pixels[row * (hash_size + 1) + col] < pixels[row * (hash_size + 1) + col + 1])
        return ''.join('1' if b else '0' for b in bits)
    except Exception:
        return ''

def _hamming_distance(hash1: str, hash2: str) -> int:
    """Compute Hamming distance between two binary hash strings."""
    if len(hash1) != len(hash2):
        return 999
    return sum(c1 != c2 for c1, c2 in zip(hash1, hash2))

IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp'}

def find_near_duplicates(folder_path: str, threshold: int = 10, log_cb=None) -> list:
    """Scan a folder for near-duplicate images using perceptual hashing.
    Returns list of (file1, file2, distance) tuples for pairs below threshold.
    Threshold of 10 catches visually similar images (0 = identical, 64 = max different)."""
    hashes = {}  # {filepath: phash_string}

    try:
        for root, dirs, files in os.walk(folder_path):
            for f in files:
                if os.path.splitext(f)[1].lower() in IMAGE_EXTS:
                    fpath = os.path.join(root, f)
                    ph = _compute_phash(fpath)
                    if ph:
                        hashes[fpath] = ph
    except (PermissionError, OSError):
        pass

    if log_cb:
        log_cb(f"  Perceptual hashed {len(hashes)} images")

    # Compare all pairs (O(n^2) but fine for typical folder sizes)
    duplicates = []
    paths = list(hashes.keys())
    for i in range(len(paths)):
        for j in range(i + 1, len(paths)):
            dist = _hamming_distance(hashes[paths[i]], hashes[paths[j]])
            if dist <= threshold:
                duplicates.append((paths[i], paths[j], dist))

    return sorted(duplicates, key=lambda x: x[2])


# ── Level 2 Enhancement: Fuzzy keyword matching ──────────────────────────────

def fuzzy_match_categories(name: str, threshold: int = 75) -> tuple:
    """Use rapidfuzz to find best fuzzy match against all category keywords.
    Returns (category, confidence, match_detail) or (None, 0, '')."""
    if not HAS_RAPIDFUZZ:
        return (None, 0, '')

    norm = _normalize(name)
    if len(norm) < 5:  # Need meaningful input for fuzzy matching
        return (None, 0, '')

    best_cat = None
    best_score = 0
    best_detail = ''

    for cat_name, keywords in get_all_categories():
        # Check against category name itself
        cat_norm = _normalize(cat_name)
        ratio = _rfuzz.token_sort_ratio(norm, cat_norm)
        if ratio > best_score and ratio >= threshold:
            best_score = ratio
            best_cat = cat_name
            best_detail = f"fuzzy:cat_name({ratio:.0f}%)"

        # Check against each keyword (only multi-word keywords to avoid short word collisions)
        for kw in keywords:
            kw_norm = _normalize(kw)
            if len(kw_norm) < 5:  # Skip short keywords - too many false positives
                continue
            ratio = _rfuzz.token_sort_ratio(norm, kw_norm)
            if ratio > best_score and ratio >= threshold:
                best_score = ratio
                best_cat = cat_name
                best_detail = f"fuzzy:\"{kw}\"({ratio:.0f}%)"

            # Partial ratio for longer folder names - higher threshold, heavier discount
            if len(norm) > len(kw_norm) + 5 and len(kw_norm) >= 8:
                partial = _rfuzz.partial_ratio(kw_norm, norm)
                adj_score = partial * 0.7  # Heavy discount for partial matches
                if adj_score > best_score and adj_score >= threshold:
                    best_score = adj_score
                    best_cat = cat_name
                    best_detail = f"fuzzy_partial:\"{kw}\"({partial:.0f}%)"

    # Convert rapidfuzz score (0-100) to our confidence scale
    if best_cat:
        # Fuzzy matches are inherently less certain than exact matches
        confidence = min(best_score * 0.7, 80)  # Cap at 80% for fuzzy
        return (best_cat, confidence, best_detail)

    return (None, 0, '')


# ══════════════════════════════════════════════════════════════════════════════
# OLLAMA LLM INTEGRATION (v4.0)
# Optional local LLM for intelligent folder classification and renaming.
# Requires Ollama running locally (https://ollama.com)
# ══════════════════════════════════════════════════════════════════════════════

_OLLAMA_SETTINGS_FILE = os.path.join(_SCRIPT_DIR, 'ollama_settings.json')

_OLLAMA_DEFAULTS = {
    'url': 'http://localhost:11434',
    'model': 'qwen2.5:7b',
    'enabled': True,
    'timeout': 30,
}

def load_ollama_settings() -> dict:
    try:
        with open(_OLLAMA_SETTINGS_FILE, 'r') as f:
            s = json.load(f)
        return {**_OLLAMA_DEFAULTS, **s}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return dict(_OLLAMA_DEFAULTS)

def save_ollama_settings(settings: dict):
    try:
        with open(_OLLAMA_SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass

def ollama_test_connection(url: str = None, model: str = None) -> tuple:
    """Test Ollama connection and model availability.
    Returns (success: bool, message: str, models: list)."""
    import urllib.request, urllib.error
    s = load_ollama_settings()
    url = url or s['url']
    model = model or s['model']

    # Test server is running
    try:
        req = urllib.request.Request(f"{url}/api/tags", method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        models = [m['name'] for m in data.get('models', [])]
    except (urllib.error.URLError, OSError, json.JSONDecodeError) as e:
        return (False, f"Cannot reach Ollama at {url}\n{e}", [])

    if not models:
        return (False, f"Ollama is running but no models installed.\nRun: ollama pull {model}", models)

    # Check if requested model is available (match by prefix)
    model_base = model.split(':')[0]
    found = any(model_base in m for m in models)
    if not found:
        return (True, f"Connected but model '{model}' not found.\n"
                      f"Available: {', '.join(models[:8])}\n"
                      f"Run: ollama pull {model}", models)

    return (True, f"Connected to Ollama\nModel: {model}\n{len(models)} models available", models)


def _ollama_generate(prompt: str, system: str = '', url: str = None,
                     model: str = None, timeout: int = None) -> str:
    """Send a prompt to Ollama and return the response text.
    Raises on connection/timeout errors."""
    import urllib.request, urllib.error
    s = load_ollama_settings()
    url = url or s['url']
    model = model or s['model']
    timeout = timeout or s.get('timeout', 30)

    payload = {
        'model': model,
        'prompt': prompt,
        'stream': False,
        'options': {'temperature': 0.1, 'num_predict': 200},
    }
    if system:
        payload['system'] = system

    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        f"{url}/api/generate",
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        result = json.loads(resp.read().decode())
    return result.get('response', '')


def _build_llm_system_prompt() -> str:
    """Build the system prompt with all category names for LLM classification."""
    cats = get_all_category_names()
    cat_list = '\n'.join(cats)
    return (
        "You are a design asset file organizer specializing in creative marketplace content "
        "(Envato, Creative Market, Freepik, etc).\n\n"
        "Your job:\n"
        "1. CLEAN the folder name: remove ONLY true noise — marketplace IDs, item codes "
        "(numeric strings like 553035, 22832058), version numbers (v1, v2.1), "
        "site names (GraphicRiver, CreativeMarket, CM_, Envato, VideoHive, VH-, etc), "
        "and replace dashes/underscores with spaces. Convert to clean Title Case.\n\n"
        "CRITICAL NAME CLEANING RULES:\n"
        "- PRESERVE the subject, topic, and descriptive words. These describe WHAT the design "
        "is about and are the most important part of the name.\n"
        "- The category already tells the user what TYPE of asset it is, so the cleaned name "
        "should focus on the SUBJECT/THEME. For example:\n"
        "  '553035-Advertisement-Company-Flyer-Template' → 'Advertisement Company Flyer Template'\n"
        "  'VH-22832058-Christmas-Slideshow' → 'Christmas Slideshow'\n"
        "  'Night-Club-Party-Flyer-PSD' → 'Night Club Party Flyer'\n"
        "  'CM_Jetstyle_Corporate-Business-Card' → 'Corporate Business Card'\n"
        "- NEVER return just a generic asset type like 'Flyer Template', 'Business Card', "
        "'Slideshow', 'Logo' etc. The name MUST include the specific subject/theme.\n"
        "- If the original name IS only a generic type after removing noise, keep it as-is.\n\n"
        "NAMING FROM PROJECT FILES (IMPORTANT):\n"
        "- If the folder name is mostly numeric IDs or marketplace noise, look at the .aep, "
        ".prproj, .psd, and .mogrt filenames inside the folder. These often contain the REAL "
        "project name.\n"
        "- Example: folder '22832058-VH' contains 'Epic_Corporate_Slideshow.aep' → name should "
        "be 'Epic Corporate Slideshow', NOT a guess based on the folder name.\n"
        "- .aep and .prproj filenames are the strongest signal for the true project name.\n"
        "- Ignore generic project filenames like 'main.aep', 'project.aep', 'comp.aep', "
        "'final.aep', 'preview.aep'.\n"
        "- Ignore subfolder names that are just asset containers: Footage, (Footage), Audio, "
        "Media, Elements, Preview, etc.\n\n"
        "NON-ENGLISH CONTENT:\n"
        "- Folder names, subfolders, and project files may be in Chinese, Russian, Korean, "
        "Arabic, Japanese, Thai, or other languages.\n"
        "- You MUST translate the name to English. The cleaned name in your response must "
        "ALWAYS be in English.\n"
        "- Translate the MEANING, not just transliterate. "
        "For example: '圣诞节幻灯片' → 'Christmas Slideshow', "
        "'Рождественское слайдшоу' → 'Christmas Slideshow', "
        "'企业宣传片' → 'Corporate Promo'.\n"
        "- If the name mixes languages (e.g. '22832058-圣诞节-Template'), extract the meaning "
        "from all parts and produce a clean English name.\n"
        "- Category assignment should still be based on the content type regardless of language.\n\n"
        "2. CATEGORIZE the folder into the single best category from the list below, "
        "based on the folder name AND the actual files inside it.\n\n"
        "IMPORTANT: Look at the filenames to determine what TYPE of design this is. "
        "For example, if files contain 'flyer' it's a flyer template. If files contain "
        "'business-card' it's a business card. If there are .aep files, it's an After Effects template. "
        "If there are .psd files with topic names like 'Night Club', it's likely a flyer.\n\n"
        "Respond ONLY with valid JSON, no other text:\n"
        '{\"name\": \"Clean Project Name\", \"category\": \"Exact Category Name\", \"confidence\": 85}\n\n'
        "VALID CATEGORIES (pick exactly one):\n"
        f"{cat_list}"
    )


def ollama_classify_folder(folder_name: str, folder_path: str = None,
                           url: str = None, model: str = None) -> dict:
    """Use Ollama LLM to classify and rename a folder.
    Returns dict: {name, category, confidence, method, detail} or empty on failure."""
    result = {'name': None, 'category': None, 'confidence': 0,
              'method': 'llm', 'detail': ''}

    # Collect file/subfolder context from the folder
    context_lines = [f"Folder name: \"{folder_name}\""]
    if folder_path and os.path.isdir(folder_path):
        files = []
        subdirs = []
        try:
            for entry in os.scandir(folder_path):
                if entry.is_file():
                    files.append(entry.name)
                elif entry.is_dir():
                    subdirs.append(entry.name)
                    # Also list files one level deeper
                    try:
                        for sub_entry in os.scandir(entry.path):
                            if sub_entry.is_file():
                                files.append(f"{entry.name}/{sub_entry.name}")
                    except (PermissionError, OSError):
                        pass
        except (PermissionError, OSError):
            pass

        if files:
            # Separate project files (strong naming signals) from other files
            project_exts = {'.aep', '.aet', '.prproj', '.psd', '.psb', '.mogrt', '.ai', '.indd'}
            project_files = []
            other_files = []
            for f in files[:80]:
                if f.lower().startswith('__macosx'):
                    continue
                ext = os.path.splitext(f)[1].lower()
                if ext in project_exts:
                    project_files.append(f)
                else:
                    other_files.append(f)

            # Show project files first with a clear label (these are the naming signals)
            if project_files:
                context_lines.append(f"PROJECT FILES (use these names for the project title):")
                for f in project_files[:15]:
                    context_lines.append(f"  ** {f}")
            if other_files:
                shown = other_files[:max(25, 40 - len(project_files))]
                context_lines.append(f"Other files ({len(files)} total, showing {len(shown) + len(project_files)}):")
                for f in shown:
                    context_lines.append(f"  {f}")
        if subdirs:
            # Filter out asset/utility folders — they're never the project name
            meaningful = []
            for d in subdirs[:20]:
                d_lower = d.lower().strip()
                d_stripped = re.sub(r'^[\(\[\{]|[\)\]\}]$', '', d_lower).strip()
                if d_stripped not in _ASSET_FOLDER_NAMES and d_lower not in _ASSET_FOLDER_NAMES:
                    meaningful.append(d)
            if meaningful:
                context_lines.append(f"Subfolders: {', '.join(meaningful)}")
            # Note asset folders separately so the LLM knows they exist but ignores them for naming
            asset_dirs = [d for d in subdirs[:20] if d not in meaningful]
            if asset_dirs:
                context_lines.append(f"Asset folders (ignore for naming): {', '.join(asset_dirs)}")

    prompt = '\n'.join(context_lines)

    try:
        system = _build_llm_system_prompt()
        raw = _ollama_generate(prompt, system=system, url=url, model=model)

        # Parse JSON from response (handle markdown code blocks)
        raw = raw.strip()
        if raw.startswith('```'):
            raw = re.sub(r'^```\w*\n?', '', raw)
            raw = re.sub(r'\n?```$', '', raw)
            raw = raw.strip()

        # Find JSON object in response
        match = re.search(r'\{[^}]+\}', raw, re.DOTALL)
        if not match:
            result['detail'] = f"llm:no_json_in_response"
            return result

        parsed = json.loads(match.group())
        clean_name = parsed.get('name', '').strip()
        category = parsed.get('category', '').strip()
        confidence = int(parsed.get('confidence', 0))

        # Validate category exists
        valid_cats = get_all_category_names()
        if category not in valid_cats:
            # Try fuzzy match on category name
            if HAS_RAPIDFUZZ:
                best_match = None
                best_score = 0
                for vc in valid_cats:
                    score = _rfuzz.ratio(category.lower(), vc.lower())
                    if score > best_score:
                        best_score = score
                        best_match = vc
                if best_match and best_score >= 75:
                    category = best_match
                    confidence = max(confidence - 10, 30)
                else:
                    category = None
            else:
                category = None

        if category:
            result['name'] = clean_name or folder_name
            result['category'] = category
            result['confidence'] = min(max(confidence, 30), 95)
            result['detail'] = f"llm:{load_ollama_settings().get('model', '?')}→{category}"

            # ── Post-validation: reject over-stripped names ──
            # If the LLM returned a name that's just the category or a generic asset type,
            # fall back to rule-based cleaning which preserves subject/topic words
            if clean_name:
                _rejected = _is_generic_name(clean_name, category)
                if _rejected:
                    # LLM stripped too aggressively — use smart naming (AEP/project hints)
                    fallback_name = _smart_name(folder_name, folder_path, category)
                    result['name'] = fallback_name
                    result['detail'] += f" (name_override:{clean_name}→{fallback_name})"
        else:
            result['detail'] = f"llm:invalid_category:\"{parsed.get('category', '')}\" not found"

    except json.JSONDecodeError as e:
        result['detail'] = f"llm:json_parse_error:{e}"
    except Exception as e:
        result['detail'] = f"llm:error:{e}"

    return result


def _find_ollama_binary() -> str:
    """Find ollama executable. Returns path or empty string."""
    # Check PATH first
    ollama_cmd = 'ollama.exe' if sys.platform == 'win32' else 'ollama'
    for p in os.environ.get('PATH', '').split(os.pathsep):
        candidate = os.path.join(p, ollama_cmd)
        if os.path.isfile(candidate):
            return candidate

    # Windows common install locations
    if sys.platform == 'win32':
        for loc in [
            os.path.expandvars(r'%LOCALAPPDATA%\Programs\Ollama\ollama.exe'),
            os.path.expandvars(r'%PROGRAMFILES%\Ollama\ollama.exe'),
            os.path.expandvars(r'%USERPROFILE%\AppData\Local\Programs\Ollama\ollama.exe'),
        ]:
            if os.path.isfile(loc):
                return loc

    # Linux/macOS common locations
    for loc in ['/usr/local/bin/ollama', '/usr/bin/ollama', os.path.expanduser('~/.local/bin/ollama')]:
        if os.path.isfile(loc):
            return loc

    return ''


def _is_ollama_server_running(url: str = None) -> bool:
    """Check if Ollama server is responding."""
    import urllib.request, urllib.error
    url = url or load_ollama_settings()['url']
    try:
        req = urllib.request.Request(f"{url}/api/tags", method='GET')
        with urllib.request.urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def _ollama_has_model(model: str, url: str = None) -> bool:
    """Check if a specific model is already pulled."""
    import urllib.request, urllib.error
    url = url or load_ollama_settings()['url']
    try:
        req = urllib.request.Request(f"{url}/api/tags", method='GET')
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        models = [m['name'] for m in data.get('models', [])]
        model_base = model.split(':')[0]
        return any(model_base in m for m in models)
    except Exception:
        return False


# ══════════════════════════════════════════════════════════════════════════════
# CONTEXT-AWARE ASSET TYPE INFERENCE (v4.0)
# When a folder matches a TOPIC category ("Club & DJ") but contains design
# template files (.psd, .ai), infer the actual ASSET TYPE ("Flyers & Print")
# so the folder is organized by what the design IS, not just what it's about.
#
# Example: "Night Club" folder with PSDs → dest/Flyers & Print/Night Club/
# ══════════════════════════════════════════════════════════════════════════════

# File types that indicate this is a design template (print/web design work)
DESIGN_TEMPLATE_EXTS = {'.psd', '.psb', '.ai', '.indd', '.idml', '.eps'}

# File types that indicate this is a video/motion template (NOT print design)
VIDEO_TEMPLATE_EXTS = {'.aep', '.aet', '.prproj', '.mogrt'}

# Filename keywords → asset type category mapping
# When these words appear in filenames inside a folder, they tell us WHAT the design IS
# (keyword_set, category, priority) - higher priority overrides lower
FILENAME_ASSET_MAP = [
    # ── PRINT DESIGN ──
    ({'flyer', 'flier', 'leaflet'},                                          'Flyers & Print',                    90),
    ({'poster'},                                                              'Posters',                           90),
    ({'brochure', 'bifold', 'bi fold', 'trifold', 'tri fold', 'pamphlet'},  'Brochures & Bi-Fold & Tri-Fold',   90),
    ({'business card', 'bcard', 'visiting card', 'name card', 'businesscard'}, 'Business Cards',                  95),
    ({'menu design', 'food menu', 'restaurant menu', 'drink menu', 'bar menu', 'cafe menu'}, 'Menu Design',       88),
    ({'resume', 'curriculum vitae'},                                          'Resume & CV',                       90),
    ({'certificate', 'diploma', 'credential'},                                'Certificate',                       90),
    ({'invitation', 'invite', 'rsvp', 'save the date'},                      'Invitations & Save the Date',       90),
    ({'letterhead', 'stationery', 'envelope', 'notepad'},                     'Letterhead & Stationery',           90),
    ({'postcard', 'greeting card', 'greetings card'},                         'Postcards',                         90),
    ({'rollup', 'roll up', 'pull up banner', 'yard sign', 'signage'},        'Rollup Banners & Signage',          90),
    ({'billboard', 'outdoor ad'},                                             'Billboard',                         90),
    ({'calendar', 'planner', 'desk calendar'},                                'Calendar',                          85),
    ({'voucher', 'coupon', 'gift card', 'gift certificate', 'discount card'},'Gift Voucher & Coupon',             90),
    ({'annual report', 'company report'},                                     'Annual Report',                     90),
    ({'packaging', 'box design', 'label design', 'die cut', 'dieline'},      'Packaging & Product',               85),
    ({'book cover', 'ebook cover', 'bookmark'},                               'Book & Literature',                 90),
    # ── SOCIAL MEDIA ──
    ({'instagram', 'ig story', 'ig post', 'ig stories', 'insta'},            'Instagram & Stories',               88),
    ({'facebook', 'fb cover', 'fb post', 'fb ad'},                           'Facebook & Social Covers',          88),
    ({'youtube', 'yt thumbnail', 'end screen', 'end card'},                  'YouTube & Video Platform',          88),
    ({'social media', 'social post'},                                         'Social Media',                      78),
    ({'thumbnail'},                                                           'Thumbnails',                        78),
    ({'web banner', 'ad banner', 'display banner', 'leaderboard'},           'Banners',                           82),
    # ── OTHER DESIGN TYPES ──
    ({'mockup', 'mock up'},                                                   'Photoshop - Mockups',               95),
    ({'logo design', 'logo template'},                                        'Logo & Identity',                   88),
    ({'presentation', 'powerpoint', 'pitch deck', 'keynote'},                'Presentations & PowerPoint',        90),
    ({'infographic'},                                                         'Infographic',                       90),
    # ── FRONT/BACK patterns (strong signals for specific asset types) ──
    ({'front and back', 'front back', 'frontback'},                          'Business Cards',                    92),
    ({'a4', 'letter size', '8.5x11', '8.5 x 11', 'a3'},                     'Flyers & Print',                    75),
    ({'4x6', '4 x 6', '5x7', '5 x 7', '6x4'},                              'Flyers & Print',                    72),
    ({'dl', 'rack card'},                                                     'Flyers & Print',                    80),
]

# Categories that should ALSO check filenames even though they're asset-type categories
# (because the category was detected by extension mapping, not content inference)
_GENERIC_DESIGN_CATEGORIES = {
    'Photoshop - Templates & Composites',
    'Illustrator - Vectors & Assets',
    'InDesign - Templates & Layouts',
}


def scan_filenames_for_asset_clues(folder_path: str) -> dict:
    """Scan filenames inside a folder for asset-type keywords.
    Returns dict with detected asset type, design file count, and filename hints."""
    result = {
        'asset_type': None, 'asset_confidence': 0, 'asset_detail': '',
        'design_file_count': 0, 'video_template_count': 0,
        'has_design_files': False, 'has_video_templates': False,
        'filename_hints': []
    }

    design_count = 0
    video_count = 0
    all_filenames = []

    try:
        for root, dirs, files in os.walk(folder_path):
            rel = os.path.relpath(root, folder_path)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth > 3:
                dirs.clear(); continue
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in DESIGN_TEMPLATE_EXTS:
                    design_count += 1
                if ext in VIDEO_TEMPLATE_EXTS:
                    video_count += 1
                # Collect filenames for keyword analysis (clean them for matching)
                name_clean = os.path.splitext(f)[0].lower()
                name_clean = name_clean.replace('-', ' ').replace('_', ' ').replace('.', ' ')
                name_clean = re.sub(r'\s+', ' ', name_clean).strip()
                if len(name_clean) > 2:
                    all_filenames.append(name_clean)
    except (PermissionError, OSError):
        pass

    result['design_file_count'] = design_count
    result['video_template_count'] = video_count
    result['has_design_files'] = design_count > 0
    result['has_video_templates'] = video_count > 0

    if not all_filenames:
        return result

    # Also add subfolder names as search candidates (they often contain asset type hints)
    try:
        for d in os.listdir(folder_path):
            if os.path.isdir(os.path.join(folder_path, d)):
                d_clean = d.lower().replace('-', ' ').replace('_', ' ')
                all_filenames.append(d_clean)
    except (PermissionError, OSError):
        pass

    # Combine all filenames into one search corpus
    combined = ' | '.join(all_filenames)

    best_cat = None
    best_priority = 0
    best_keyword = ''

    for keywords, category, priority in FILENAME_ASSET_MAP:
        for kw in keywords:
            if kw in combined:
                if priority > best_priority:
                    best_cat = category
                    best_priority = priority
                    best_keyword = kw
                result['filename_hints'].append((kw, category))
                break  # Found one keyword in this set, move to next

    if best_cat:
        result['asset_type'] = best_cat
        result['asset_confidence'] = best_priority
        result['asset_detail'] = f"filename:\"{best_keyword}\"→{best_cat}"

    return result


def infer_asset_type(initial_category: str, initial_confidence: float,
                     folder_path: str, folder_name: str, log_cb=None) -> tuple:
    """Context-aware post-processing: when a TOPIC category is detected alongside
    design template files, infer the actual asset type.

    Example: "Night Club" (topic: Club & DJ) + PSD files → "Flyers & Print"

    Also handles generic design categories like "Photoshop - Templates & Composites"
    by checking filenames for more specific asset type clues.

    Returns (category, confidence, method, detail) or (None, 0, '', '') if no override."""

    should_check = (initial_category in TOPIC_CATEGORIES or
                    initial_category in _GENERIC_DESIGN_CATEGORIES)

    if not should_check:
        return (None, 0, '', '')

    # Scan filenames for explicit asset type clues
    clues = scan_filenames_for_asset_clues(folder_path)

    # If video template files dominate, don't override — these are AE/Premiere templates
    if clues['has_video_templates'] and clues['video_template_count'] >= clues['design_file_count']:
        return (None, 0, '', '')

    if not clues['has_design_files']:
        # No design files → this is probably genuinely a topic-based asset bundle
        # (e.g., a Christmas photo pack, stock footage collection)
        return (None, 0, '', '')

    # ── Priority 1: Filenames explicitly name the asset type ──
    if clues['asset_type']:
        conf = min(clues['asset_confidence'], 92)
        detail = f"context:{initial_category}+{clues['asset_detail']}"
        if log_cb:
            log_cb(f"    Context: {initial_category} + filename \"{clues['asset_detail'].split('\"')[1]}\" → {clues['asset_type']}")
        return (clues['asset_type'], conf, 'context', detail)

    # ── Priority 2: Folder name itself hints at an asset type ──
    folder_norm = _normalize(folder_name)
    for keywords, category, priority in FILENAME_ASSET_MAP:
        for kw in keywords:
            if kw in folder_norm:
                conf = min(priority - 5, 88)
                detail = f"context:name_hint:\"{kw}\"→{category}"
                if log_cb:
                    log_cb(f"    Context: folder name hint \"{kw}\" + design files → {category}")
                return (category, conf, 'context', detail)

    # ── Priority 3: Default inference for generic design categories ──
    # For "Photoshop - Templates & Composites" with no other clues, keep it as-is
    if initial_category in _GENERIC_DESIGN_CATEGORIES:
        return (None, 0, '', '')

    # ── Priority 4: Default inference for topic categories + design files ──
    # In the marketplace, topic-named PSD/AI folders are overwhelmingly flyers/print templates
    # This is the "Night Club" + PSD → Flyers & Print rule
    conf = 72
    detail = f"context:design({clues['design_file_count']})+topic:{initial_category}→Flyers & Print"
    if log_cb:
        log_cb(f"    Context: {clues['design_file_count']} design files + topic \"{initial_category}\" → Flyers & Print (default)")
    return ('Flyers & Print', conf, 'context', detail)


# ── Tiered Classification Orchestrator ────────────────────────────────────────

# File extensions to exclude from "project file" counts
_NOISE_EXTS = {'.txt', '.html', '.htm', '.url', '.ini', '.log',
               '.md', '.json', '.xml', '.csv', '.rtf', '.nfo',
               '.ds_store', '.zip', '.rar', '.7z'}

def _scan_folder_once(folder_path: str) -> dict:
    """Single-pass folder scan that collects ALL data needed by every classification level.
    Eliminates the 3-4 redundant os.walk() calls per folder.

    Returns dict with:
        ext_counts: Counter of ALL extensions
        project_ext_counts: Counter excluding noise extensions
        total_project_files: int
        subfolder_names: list[str]  (lowercase)
        total_size: int
        file_count: int
        all_filenames_clean: list[str]  (cleaned for keyword matching)
        design_file_count: int
        video_template_count: int
        has_design_files: bool
        has_video_templates: bool
        has_footage/has_audio/has_preview: bool
        project_files: list[tuple[str, str]]  (filepath, ext) for metadata extraction
    """
    ext_counts = Counter()
    project_ext_counts = Counter()
    total_project_files = 0
    subfolder_names = []
    total_size = 0
    file_count = 0
    all_filenames_clean = []
    design_count = 0
    video_count = 0
    project_files = []  # Files to extract metadata from

    try:
        for root, dirs, files in os.walk(folder_path):
            rel = os.path.relpath(root, folder_path)
            depth = 0 if rel == '.' else rel.count(os.sep) + 1
            if depth == 0:
                subfolder_names = [d.lower() for d in dirs]
            if depth > 3:
                dirs.clear(); continue
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if not ext:
                    continue
                ext_counts[ext] += 1
                file_count += 1
                try:
                    total_size += os.path.getsize(os.path.join(root, f))
                except OSError:
                    pass

                # Project file counts (exclude noise)
                if ext not in _NOISE_EXTS:
                    project_ext_counts[ext] += 1
                    total_project_files += 1

                # Design/video template tracking
                if ext in DESIGN_TEMPLATE_EXTS:
                    design_count += 1
                if ext in VIDEO_TEMPLATE_EXTS:
                    video_count += 1

                # Collect project files for metadata extraction
                if ext in ('.prproj', '.psd', '.psb', '.aep', '.aet', '.mogrt'):
                    project_files.append((os.path.join(root, f), ext))

                # Collect cleaned filenames for keyword matching
                name_clean = os.path.splitext(f)[0].lower()
                name_clean = name_clean.replace('-', ' ').replace('_', ' ').replace('.', ' ')
                name_clean = re.sub(r'\s+', ' ', name_clean).strip()
                if len(name_clean) > 2:
                    all_filenames_clean.append(name_clean)
    except (PermissionError, OSError):
        pass

    # Also add subfolder names as search candidates
    for d in subfolder_names:
        d_clean = d.replace('-', ' ').replace('_', ' ')
        if len(d_clean) > 2:
            all_filenames_clean.append(d_clean)

    return {
        'ext_counts': ext_counts,
        'project_ext_counts': project_ext_counts,
        'total_project_files': total_project_files,
        'subfolder_names': subfolder_names,
        'total_size': total_size,
        'file_count': file_count,
        'all_filenames_clean': all_filenames_clean,
        'design_file_count': design_count,
        'video_template_count': video_count,
        'has_design_files': design_count > 0,
        'has_video_templates': video_count > 0,
        'has_footage': any(d in subfolder_names for d in ['footage', 'video', 'media', 'clips']),
        'has_audio': any(d in subfolder_names for d in ['audio', 'music', 'sound', 'sfx']),
        'has_preview': any(d in subfolder_names for d in ['preview', 'previews', 'thumbnail', 'thumbnails']),
        'project_files': project_files,
    }


def _classify_ext_from_scan(scan: dict) -> tuple:
    """Level 1 extension classification using pre-scanned data (no os.walk)."""
    ext_counts = scan['project_ext_counts']
    total_project_files = scan['total_project_files']
    if total_project_files == 0:
        return (None, 0, '')

    best = (None, 0, '')
    for ext_set, category, base_conf in EXTENSION_CATEGORY_MAP:
        matching = sum(ext_counts.get(e, 0) for e in ext_set)
        if matching == 0:
            continue
        ratio = matching / total_project_files
        if ratio >= 0.7:     conf = base_conf
        elif ratio >= 0.4:   conf = base_conf - 10
        elif ratio >= 0.15:  conf = base_conf - 20
        elif matching >= 2:  conf = base_conf - 30
        else: continue
        if matching >= 10:
            conf = min(conf + 5, 100)
        ext_list = ', '.join(f"{e}({ext_counts[e]})" for e in ext_set if ext_counts.get(e, 0) > 0)
        if conf > best[1]:
            best = (category, conf, f"ext:{ext_list} ({ratio:.0%} of {total_project_files} files)")
    return best


def _classify_composition_from_scan(scan: dict) -> tuple:
    """Level 4 composition classification using pre-scanned data (no os.walk)."""
    ext = scan['ext_counts']
    total = scan['file_count']
    if total == 0:
        return (None, 0, '')

    video_exts = sum(ext.get(e, 0) for e in ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.webm', '.m4v'])
    audio_exts = sum(ext.get(e, 0) for e in ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.aif', '.aiff'])
    image_exts = sum(ext.get(e, 0) for e in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tif', '.tiff', '.webp', '.psd', '.psb'])
    vector_exts = sum(ext.get(e, 0) for e in ['.svg', '.eps', '.ai'])
    font_exts = sum(ext.get(e, 0) for e in ['.ttf', '.otf', '.woff', '.woff2'])
    doc_exts = sum(ext.get(e, 0) for e in ['.pdf', '.pptx', '.docx', '.xlsx', '.indd', '.idml'])

    if ext.get('.aep', 0) >= 1 and scan['has_footage']:
        return ('After Effects - Templates', 72, f"composition:.aep+/footage/ subfolder")
    if ext.get('.aep', 0) >= 1 and scan['has_audio']:
        return ('After Effects - Templates', 68, f"composition:.aep+/audio/ subfolder")
    if video_exts >= 5 and video_exts / total >= 0.5:
        return ('Stock Footage - General', 75, f"composition:{video_exts} video files ({video_exts/total:.0%})")
    if audio_exts >= 5 and audio_exts / total >= 0.5:
        return ('Stock Music & Audio', 75, f"composition:{audio_exts} audio files ({audio_exts/total:.0%})")
    if image_exts >= 10 and image_exts / total >= 0.7:
        return ('Stock Photos - General', 65, f"composition:{image_exts} images ({image_exts/total:.0%})")
    if vector_exts >= 3 and vector_exts / total >= 0.3:
        return ('Vectors & SVG', 65, f"composition:{vector_exts} vectors ({vector_exts/total:.0%})")
    if font_exts >= 2 and font_exts / total >= 0.3:
        return ('Fonts & Typography', 65, f"composition:{font_exts} font files ({font_exts/total:.0%})")
    if doc_exts >= 2 and doc_exts / total >= 0.3:
        if ext.get('.pptx', 0) >= 1:
            return ('Presentations & PowerPoint', 60, f"composition:{doc_exts} docs (pptx found)")
        if ext.get('.indd', 0) >= 1 or ext.get('.idml', 0) >= 1:
            return ('InDesign - Templates & Layouts', 65, f"composition:InDesign files found")
        return ('Forms & Documents', 55, f"composition:{doc_exts} document files")
    if image_exts >= 8 and not any(ext.get(e, 0) for e in ['.aep', '.psd', '.prproj', '.ai']):
        return ('Backgrounds & Textures', 55, f"composition:{image_exts} images, no project files")
    return (None, 0, '')


def _asset_clues_from_scan(scan: dict, folder_path: str) -> dict:
    """Asset type clue detection using pre-scanned data (no os.walk)."""
    result = {
        'asset_type': None, 'asset_confidence': 0, 'asset_detail': '',
        'design_file_count': scan['design_file_count'],
        'video_template_count': scan['video_template_count'],
        'has_design_files': scan['has_design_files'],
        'has_video_templates': scan['has_video_templates'],
        'filename_hints': []
    }
    if not scan['all_filenames_clean']:
        return result

    combined = ' | '.join(scan['all_filenames_clean'])
    best_cat = None
    best_priority = 0
    best_keyword = ''

    for keywords, category, priority in FILENAME_ASSET_MAP:
        for kw in keywords:
            if kw in combined:
                if priority > best_priority:
                    best_cat = category
                    best_priority = priority
                    best_keyword = kw
                result['filename_hints'].append((kw, category))
                break
    if best_cat:
        result['asset_type'] = best_cat
        result['asset_confidence'] = best_priority
        result['asset_detail'] = f"filename:\"{best_keyword}\"→{best_cat}"
    return result


def _extract_metadata_from_scan(scan: dict, folder_name: str, log_cb=None) -> dict:
    """Metadata extraction using pre-scanned project file list (no rglob)."""
    metadata = {
        'keywords': [], 'project_names': [],
        'envato_id': detect_envato_item_code(folder_name),
        'primary_app': '',
        'has_aep': False, 'has_prproj': False, 'has_psd': False, 'has_mogrt': False,
    }
    scanned = 0
    max_scan = 10

    for filepath, ext in scan['project_files']:
        if ext in ('.aep', '.aet'):
            metadata['has_aep'] = True
            metadata['primary_app'] = metadata['primary_app'] or 'After Effects'
        elif ext == '.prproj':
            metadata['has_prproj'] = True
            metadata['primary_app'] = metadata['primary_app'] or 'Premiere Pro'
            if scanned < max_scan:
                names = extract_prproj_metadata(filepath)
                metadata['project_names'].extend(names)
                scanned += 1
        elif ext in ('.psd', '.psb'):
            metadata['has_psd'] = True
            metadata['primary_app'] = metadata['primary_app'] or 'Photoshop'
            if scanned < max_scan and HAS_PSD_TOOLS:
                names = extract_psd_metadata(filepath)
                metadata['keywords'].extend(names)
                scanned += 1
        elif ext == '.mogrt':
            metadata['has_mogrt'] = True
            metadata['primary_app'] = metadata['primary_app'] or 'After Effects'
        if scanned >= max_scan:
            break
    return metadata


def _apply_context_from_scan(result: dict, scan: dict, folder_path: str,
                              folder_name: str, log_cb=None) -> dict:
    """Post-processing using pre-scanned data (no os.walk in infer_asset_type)."""
    if not result['category']:
        return result

    initial_category = result['category']
    should_check = (initial_category in TOPIC_CATEGORIES or
                    initial_category in _GENERIC_DESIGN_CATEGORIES)
    if not should_check:
        return result

    clues = _asset_clues_from_scan(scan, folder_path)

    # If video template files dominate, don't override
    if clues['has_video_templates'] and clues['video_template_count'] >= clues['design_file_count']:
        return result
    if not clues['has_design_files']:
        return result

    # Priority 1: Filenames explicitly name the asset type
    if clues['asset_type']:
        conf = min(clues['asset_confidence'], 92)
        detail = f"context:{initial_category}+{clues['asset_detail']}"
        if log_cb:
            log_cb(f"    Context: {initial_category} + filename \"{clues['asset_detail'].split('\"')[1]}\" → {clues['asset_type']}")
        result['topic'] = result['category']
        result['category'] = clues['asset_type']
        result['confidence'] = conf
        result['method'] = 'context'
        result['detail'] = detail
        return result

    # Priority 2: Folder name hints
    folder_norm = _normalize(folder_name)
    for keywords, category, priority in FILENAME_ASSET_MAP:
        for kw in keywords:
            if kw in folder_norm:
                conf = min(priority - 5, 88)
                detail = f"context:name_hint:\"{kw}\"→{category}"
                if log_cb:
                    log_cb(f"    Context: folder name hint \"{kw}\" + design files → {category}")
                result['topic'] = result['category']
                result['category'] = category
                result['confidence'] = conf
                result['method'] = 'context'
                result['detail'] = detail
                return result

    # Priority 3: Generic design categories — keep as-is
    if initial_category in _GENERIC_DESIGN_CATEGORIES:
        return result

    # Priority 4: Default topic + design files → Flyers & Print
    conf = 72
    detail = f"context:design({clues['design_file_count']})+topic:{initial_category}→Flyers & Print"
    if log_cb:
        log_cb(f"    Context: {clues['design_file_count']} design files + topic \"{initial_category}\" → Flyers & Print (default)")
    result['topic'] = result['category']
    result['category'] = 'Flyers & Print'
    result['confidence'] = conf
    result['method'] = 'context'
    result['detail'] = detail
    return result


def tiered_classify(folder_name: str, folder_path: str = None, log_cb=None) -> dict:
    """Run the full tiered classification pipeline on a folder.

    Returns dict:
        category: str or None
        confidence: float 0-100
        cleaned_name: str
        method: str  ('extension', 'keyword', 'fuzzy', 'metadata', 'metadata+keyword', 'context')
        detail: str  (human-readable explanation of how it was classified)
        metadata: dict (extracted metadata if any)
        topic: str or None  (original topic category before context override, if any)
    """
    result = {
        'category': None, 'confidence': 0, 'cleaned_name': folder_name,
        'method': '', 'detail': '', 'metadata': {}, 'topic': None
    }

    # ── Single-pass folder scan: collect ALL data once for all levels ──
    has_folder = folder_path and os.path.isdir(folder_path)
    scan = None
    if has_folder:
        scan = _scan_folder_once(folder_path)

    # ── Level 1: Extension-based classification ──
    if scan:
        ext_cat, ext_conf, ext_detail = _classify_ext_from_scan(scan)
    else:
        ext_cat, ext_conf, ext_detail = (None, 0, '')

    if ext_cat and ext_conf >= 80:
            result.update(category=ext_cat, confidence=ext_conf,
                          method='extension', detail=ext_detail)
            if log_cb:
                log_cb(f"    L1 Extension: {ext_cat} ({ext_conf:.0f}%) [{ext_detail}]")
            if scan:
                return _apply_context_from_scan(result, scan, folder_path, folder_name, log_cb)
            return result

    # Helper: context application using scan data when available
    def _ctx(r):
        if scan:
            return _apply_context_from_scan(r, scan, folder_path, folder_name, log_cb)
        elif has_folder:
            return _apply_context(r, folder_path, folder_name, has_folder, log_cb)
        return r

    # ── Level 2: Keyword matching (primary engine) ──
    cat, conf, cleaned = categorize_folder(folder_name)
    result['cleaned_name'] = cleaned

    if cat and conf >= 65:  # Only short-circuit for high-confidence keyword matches
        result.update(category=cat, confidence=conf, method='keyword',
                      detail=f"keyword:\"{cleaned}\"→{cat}")
        if log_cb:
            log_cb(f"    L2 Keyword: {cat} ({conf:.0f}%)")
        return _ctx(result)

    # Store lower-confidence keyword result as fallback
    keyword_fallback = (cat, conf) if cat else (None, 0)

    # ── Level 2.5: Fuzzy matching (rapidfuzz) ──
    if HAS_RAPIDFUZZ:
        fz_cat, fz_conf, fz_detail = fuzzy_match_categories(cleaned)
        if fz_cat and fz_conf > (keyword_fallback[1] if keyword_fallback[0] else 0):
            result.update(category=fz_cat, confidence=fz_conf, method='fuzzy',
                          detail=fz_detail)
            if log_cb:
                log_cb(f"    L2.5 Fuzzy: {fz_cat} ({fz_conf:.0f}%) [{fz_detail}]")
            return _ctx(result)

    # ── Level 3: Metadata extraction + re-classification ──
    if scan:
        meta = _extract_metadata_from_scan(scan, folder_name, log_cb)
        result['metadata'] = meta

        # Use extracted metadata to attempt classification
        meta_keywords = meta.get('project_names', []) + meta.get('keywords', [])

        if meta_keywords:
            for mk in meta_keywords[:10]:
                m_cat, m_conf, m_cleaned = categorize_folder(mk)
                if m_cat and m_conf >= 40:
                    adj_conf = min(m_conf + 10, 90)
                    result.update(category=m_cat, confidence=adj_conf,
                                  method='metadata+keyword',
                                  detail=f"meta:\"{mk}\"→{m_cat}")
                    if log_cb:
                        log_cb(f"    L3 Metadata: {m_cat} ({adj_conf:.0f}%) from \"{mk}\"")
                    return _ctx(result)

        # Use primary_app detection as last resort from metadata
        if meta.get('primary_app') and not keyword_fallback[0]:
            app = meta['primary_app']
            app_map = {
                'After Effects': 'After Effects - Templates',
                'Premiere Pro': 'Premiere Pro - Templates',
                'Photoshop': 'Photoshop - Templates & Composites',
            }
            if app in app_map:
                result.update(category=app_map[app], confidence=55,
                              method='metadata', detail=f"app_detect:{app}")
                if log_cb:
                    log_cb(f"    L3 App detect: {app_map[app]} (55%) [{app} files found]")
                return _ctx(result)

        # ── Level 3.5: Envato API enrichment ──
        envato_id = meta.get('envato_id', '')
        if envato_id:
            api_cat, api_conf, api_detail = _envato_api_classify(envato_id)
            if api_cat:
                result.update(category=api_cat, confidence=api_conf,
                              method='envato_api', detail=api_detail)
                if log_cb:
                    log_cb(f"    L3.5 Envato API: {api_cat} ({api_conf:.0f}%) [{api_detail}]")
                return _ctx(result)

    # ── Level 4: Folder composition heuristics (uses pre-scanned data) ──
    if scan:
        comp_cat, comp_conf, comp_detail = _classify_composition_from_scan(scan)
        if comp_cat and comp_conf >= 50:
            result.update(category=comp_cat, confidence=comp_conf,
                          method='composition', detail=comp_detail)
            if log_cb:
                log_cb(f"    L4 Composition: {comp_cat} ({comp_conf:.0f}%) [{comp_detail}]")
            return _ctx(result)

    # ── Level 1 low-confidence fallback ──
    if ext_cat and ext_conf >= 50:
        result.update(category=ext_cat, confidence=ext_conf,
                      method='extension', detail=ext_detail)
        if log_cb:
            log_cb(f"    L1 Extension (fallback): {ext_cat} ({ext_conf:.0f}%)")
        return _ctx(result)

    # ── Return best low-confidence result if any ──
    if keyword_fallback[0] and keyword_fallback[1] >= 15:
        result.update(category=keyword_fallback[0], confidence=keyword_fallback[1],
                      method='keyword_low', detail=f"keyword_low:\"{cleaned}\"")
        return _ctx(result)

    return result


def _apply_context(result: dict, folder_path: str, folder_name: str,
                   has_folder: bool, log_cb=None) -> dict:
    """Post-processing: apply context-aware asset type inference.
    If the initial category is a topic or generic design category AND the folder
    contains design template files, override with the inferred asset type."""

    if not has_folder or not result['category']:
        return result

    ctx_cat, ctx_conf, ctx_method, ctx_detail = infer_asset_type(
        result['category'], result['confidence'],
        folder_path, folder_name, log_cb)

    if ctx_cat:
        # Preserve the original topic for subfolder naming
        result['topic'] = result['category']
        result['category'] = ctx_cat
        result['confidence'] = ctx_conf
        result['method'] = ctx_method
        result['detail'] = ctx_detail

    return result


# ── Data structures ────────────────────────────────────────────────────────────
class RenameItem:
    def __init__(self):
        self.selected = True
        self.current_name = ""
        self.new_name = ""
        self.aep_file = ""
        self.file_size = ""
        self.full_current_path = ""
        self.full_new_path = ""
        self.status = "Pending"

class CategorizeItem:
    def __init__(self):
        self.selected = True
        self.folder_name = ""
        self.cleaned_name = ""
        self.category = ""
        self.confidence = 0
        self.full_source_path = ""
        self.full_dest_path = ""
        self.status = "Pending"
        self.method = ""        # classification method: extension, keyword, fuzzy, metadata, context
        self.detail = ""        # human-readable detail of how it was classified
        self.topic = ""         # original topic if context engine overrode it


# ── Workers ────────────────────────────────────────────────────────────────────
def _collect_scan_folders(root: Path, scan_depth: int = 0) -> list:
    """Collect folders to process at the specified depth.
    depth=0: immediate children (default, original behavior)
    depth=1: grandchildren (subfolders within each top-level folder)
    depth=2+: deeper nesting levels"""
    try:
        top_dirs = sorted([f for f in root.iterdir() if f.is_dir()])
    except PermissionError:
        return []

    if scan_depth <= 0:
        return top_dirs

    # Recurse into deeper levels
    folders = []
    for top_dir in top_dirs:
        try:
            subs = _collect_scan_folders(top_dir, scan_depth - 1)
            folders.extend(subs)
        except (PermissionError, OSError):
            continue
    return folders


class ScanAepWorker(QThread):
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, root_dir, scan_depth=0):
        super().__init__()
        self.root_dir = root_dir
        self.scan_depth = scan_depth
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        root = Path(self.root_dir)
        folders = _collect_scan_folders(root, self.scan_depth)
        if not folders:
            self.log.emit("ERROR: No folders found or permission denied")
            self.finished.emit(); return

        if self.scan_depth > 0:
            self.log.emit(f"  Deep scan (depth {self.scan_depth}): processing {len(folders)} subfolders")

        total = len(folders)
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)
            self.log.emit(f"Scanning: {folder.name}")
            aep_files = []
            try:
                for aep in folder.rglob("*.aep"):
                    try:
                        aep_files.append(aep)
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                pass

            # Score each AEP and pick the best candidate for naming
            best_aep = None
            best_score = -999
            best_size = 0
            for aep in aep_files:
                aep_score, aep_size = _score_aep(aep, folder, folder.name)
                if aep_score > best_score or (aep_score == best_score and aep_size > best_size):
                    best_aep = aep
                    best_score = aep_score
                    best_size = aep_size

            self.result_ready.emit({
                'folder_name': folder.name,
                'folder_path': str(folder),
                'largest_aep': best_aep.name if best_aep else None,
                'aep_rel_path': str(best_aep.relative_to(folder)) if best_aep else None,
                'aep_size': best_size,
            })
        self.finished.emit()


class ScanCategoryWorker(QThread):
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    # Extensions that indicate real project content
    PROJECT_EXTS = {
        '.aep', '.aet', '.prproj', '.psd', '.ai', '.indd', '.idml',
        '.mogrt', '.ffx', '.atn', '.abr', '.jsx', '.jsxbin',
        '.c4d', '.blend', '.obj', '.fbx', '.stl',
        '.cube', '.3dl', '.lut', '.lrtemplate', '.xmp',
        '.ttf', '.otf', '.woff', '.woff2',
        '.mp4', '.mov', '.avi', '.wmv', '.mkv',
        '.mp3', '.wav', '.flac', '.aif', '.ogg',
        '.jpg', '.jpeg', '.png', '.tif', '.tiff', '.gif', '.svg', '.eps', '.pdf',
        '.pptx', '.docx', '.xlsx',
    }

    def __init__(self, root_dir, dest_dir, scan_depth=0, use_cache=True):
        super().__init__()
        self.root_dir = root_dir
        self.dest_dir = dest_dir
        self.scan_depth = scan_depth
        self.use_cache = use_cache
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _collect_candidate_names(self, folder: Path, max_depth=4):
        """Walk into a folder to find all candidate names for categorization.
        Returns list of (name, depth, has_project_files) sorted by quality."""
        candidates = []
        # Always include the top-level folder itself
        top_has_files = any(
            f.suffix.lower() in self.PROJECT_EXTS
            for f in folder.iterdir() if f.is_file()
        ) if folder.is_dir() else False
        candidates.append((folder.name, 0, top_has_files))

        # Walk deeper
        try:
            self._walk_candidates(folder, folder, 1, max_depth, candidates)
        except (PermissionError, OSError):
            pass
        return candidates

    def _walk_candidates(self, base, current, depth, max_depth, candidates):
        """Recursively collect subfolder names as categorization candidates."""
        if depth > max_depth:
            return
        try:
            subdirs = [d for d in current.iterdir() if d.is_dir()]
        except (PermissionError, OSError):
            return

        for sub in subdirs:
            # Check if this subfolder has project files
            has_files = False
            try:
                has_files = any(
                    f.suffix.lower() in self.PROJECT_EXTS
                    for f in sub.iterdir() if f.is_file()
                )
            except (PermissionError, OSError):
                pass

            # Skip generic/junk folder names (asset folders, not project names)
            sub_lower = sub.name.lower().strip()
            # Strip parentheses for matching: "(Footage)" → "footage"
            sub_stripped = re.sub(r'^[\(\[\{]|[\)\]\}]$', '', sub_lower).strip()
            if sub_lower not in _ASSET_FOLDER_NAMES and sub_stripped not in _ASSET_FOLDER_NAMES:
                candidates.append((sub.name, depth, has_files))

            # If this is a single-subfolder wrapper, always go deeper
            # Also go deeper if no project files found yet at this level
            self._walk_candidates(base, sub, depth + 1, max_depth, candidates)

    def _best_categorization(self, folder: Path):
        """Find the best category using the tiered classification pipeline.
        Tries extension mapping and metadata on the actual folder, then
        keyword/fuzzy matching on all candidate subfolder names.
        Returns (category, confidence, cleaned_name, source_name, depth, method, detail, topic)."""

        # First: try tiered classification on the top-level folder itself
        # This runs extension mapping + metadata extraction on the actual folder contents
        top_result = tiered_classify(folder.name, str(folder))

        if top_result['category'] and top_result['confidence'] >= 70:
            return (top_result['category'], top_result['confidence'],
                    top_result['cleaned_name'], folder.name, 0,
                    top_result['method'], top_result['detail'],
                    top_result.get('topic'))

        # Cache the top-level result to avoid re-running I/O for depth-0
        best = None  # (cat, conf, cleaned, source_name, depth, method, detail, topic)

        # If top_result had any match (even low confidence), include it as a candidate
        if top_result['category']:
            best = (top_result['category'], top_result['confidence'],
                    top_result['cleaned_name'], folder.name, 0,
                    top_result['method'], top_result['detail'],
                    top_result.get('topic'))

        # Second: collect candidate subfolder names and try keyword matching on each
        candidates = self._collect_candidate_names(folder)

        for name, depth, has_files in candidates:
            if depth == 0:
                continue  # Already handled by top_result above

            # For deeper candidates, just use keyword + fuzzy matching (no redundant I/O)
            result = tiered_classify(name, None)

            if not result['category']:
                continue

            # Score bonus for having project files nearby
            effective_score = result['confidence']
            if has_files:
                effective_score += 5
            # Slight penalty for deeper folders (prefer top-level matches)
            effective_score -= depth * 2

            if best is None or effective_score > best[1]:
                best = (result['category'], result['confidence'],
                        result['cleaned_name'], name, depth,
                        result['method'], result['detail'],
                        result.get('topic'))

        if best:
            return best
        return (None, 0, folder.name, folder.name, 0, '', '', None)

    def run(self):
        root = Path(self.root_dir)
        folders = _collect_scan_folders(root, self.scan_depth)
        if not folders:
            self.log.emit("ERROR: No folders found or permission denied")
            self.finished.emit(); return

        # ── Pre-load caches for scan performance ──
        _preload_corrections()
        _CategoryIndex.get()  # Build keyword index once

        # Log engine capabilities
        caps = ["keyword"]
        if HAS_RAPIDFUZZ: caps.append("fuzzy")
        if HAS_PSD_TOOLS: caps.append("psd-metadata")
        caps.extend(["extension-map", "prproj-metadata", "content-analysis"])
        self.log.emit(f"  Engine: tiered v5.3 [{', '.join(caps)}, context-inference, cache, corrections, smart-naming]")
        if self.scan_depth > 0:
            self.log.emit(f"  Deep scan (depth {self.scan_depth}): processing {len(folders)} subfolders")

        total = len(folders)
        t0 = time.time(); cached_hits = 0; correction_hits = 0
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)

            # Check corrections first (learned from user overrides)
            corr_cat = check_corrections(folder.name)
            if corr_cat:
                correction_hits += 1
                self.log.emit(f"  {folder.name}")
                self.log.emit(f"    -->  {corr_cat}  (100%) [learned]")
                self.result_ready.emit({
                    'folder_name': folder.name, 'folder_path': str(folder),
                    'category': corr_cat, 'confidence': 100,
                    'cleaned_name': folder.name, 'source_depth': 0,
                    'method': 'learned', 'detail': 'From user correction history',
                    'topic': None,
                })
                continue

            # Check cache
            if self.use_cache:
                cached = cache_lookup(folder.name, str(folder))
                if cached and cached.get('category'):
                    cached_hits += 1
                    self.log.emit(f"  {folder.name}")
                    self.log.emit(f"    -->  {cached['category']}  ({cached['confidence']:.0f}%) [cached]")
                    self.result_ready.emit({
                        'folder_name': folder.name, 'folder_path': str(folder),
                        'category': cached['category'], 'confidence': cached['confidence'],
                        'cleaned_name': cached.get('cleaned_name', folder.name), 'source_depth': 0,
                        'method': f"cached:{cached.get('method', '')}", 'detail': cached.get('detail', ''),
                        'topic': cached.get('topic'),
                    })
                    continue

            cat, conf, cleaned, source_name, depth, method, detail, topic = self._best_categorization(folder)

            # Log what happened
            if depth > 0:
                self.log.emit(f"  {folder.name}")
                self.log.emit(f"    Found via subfolder: \"{source_name}\" (depth {depth})")
            elif cleaned != folder.name:
                self.log.emit(f"  {folder.name}  (detected: \"{cleaned}\")")
            else:
                self.log.emit(f"  {folder.name}")

            if cat:
                method_tag = f" [{method}]" if method else ""
                topic_tag = f" (topic: {topic})" if topic else ""
                self.log.emit(f"    -->  {cat}{topic_tag}  ({conf:.0f}%){method_tag}")
            else:
                self.log.emit(f"    -->  [no match]")

            result_dict = {
                'folder_name': folder.name,
                'folder_path': str(folder),
                'category': cat,
                'confidence': conf,
                'cleaned_name': cleaned if depth == 0 else f"{cleaned} (via: {source_name})",
                'source_depth': depth,
                'method': method,
                'detail': detail,
                'topic': topic,
            }
            self.result_ready.emit(result_dict)
            # Store in cache for future runs
            if cat and self.use_cache:
                cache_store(folder.name, str(folder), result_dict)

        elapsed = time.time() - t0
        if cached_hits: self.log.emit(f"  Cache hits: {cached_hits}")
        if correction_hits: self.log.emit(f"  Learned corrections applied: {correction_hits}")
        if elapsed > 1: self.log.emit(f"  Scan time: {elapsed:.1f}s ({elapsed/max(total,1)*1000:.0f}ms/folder)")
        _close_cache_conn()  # Release persistent DB connection
        self.finished.emit()


# ── LLM Classification Worker ─────────────────────────────────────────────────
class ScanLLMWorker(QThread):
    """Scans folders using Ollama LLM for classification and renaming.
    Processes every folder through the LLM for maximum accuracy."""
    result_ready = pyqtSignal(dict)
    finished = pyqtSignal()
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, root_dir, dest_dir, scan_depth=0, use_cache=True):
        super().__init__()
        self.root_dir = root_dir
        self.dest_dir = dest_dir
        self.scan_depth = scan_depth
        self.use_cache = use_cache
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def run(self):
        root = Path(self.root_dir)
        settings = load_ollama_settings()

        folders = _collect_scan_folders(root, self.scan_depth)
        if not folders:
            self.log.emit("ERROR: No folders found or permission denied")
            self.finished.emit(); return

        # ── Pre-load caches for scan performance ──
        _preload_corrections()
        _CategoryIndex.get()

        # Verify Ollama connection first
        ok, msg, _ = ollama_test_connection(settings['url'], settings['model'])
        if not ok:
            self.log.emit(f"ERROR: {msg}")
            self.log.emit("Falling back to rule-based classification...")
            # Fall back to rule-based scanning
            self._fallback_scan(folders)
            return

        self.log.emit(f"  Engine: LLM via Ollama [{settings['model']}]")
        self.log.emit(f"  Processing {len(folders)} folders through LLM...")
        if self.scan_depth > 0:
            self.log.emit(f"  Deep scan (depth {self.scan_depth}): scanning subfolders")

        total = len(folders)
        llm_ok = 0; llm_fail = 0

        t0 = time.time(); cached_hits = 0; correction_hits = 0
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)

            # Check corrections first
            corr_cat = check_corrections(folder.name)
            if corr_cat:
                correction_hits += 1
                self.result_ready.emit({
                    'folder_name': folder.name, 'folder_path': str(folder),
                    'category': corr_cat, 'confidence': 100,
                    'cleaned_name': folder.name, 'source_depth': 0,
                    'method': 'learned', 'detail': 'From correction history',
                    'topic': None, 'llm_name': None,
                })
                continue

            # Check cache
            if self.use_cache:
                cached = cache_lookup(folder.name, str(folder))
                if cached and cached.get('category'):
                    cached_hits += 1
                    self.result_ready.emit({
                        'folder_name': folder.name, 'folder_path': str(folder),
                        'category': cached['category'], 'confidence': cached['confidence'],
                        'cleaned_name': cached.get('cleaned_name', folder.name), 'source_depth': 0,
                        'method': f"cached:{cached.get('method', '')}", 'detail': cached.get('detail', ''),
                        'topic': cached.get('topic'), 'llm_name': cached.get('cleaned_name'),
                    })
                    continue

            # Try LLM classification
            llm_result = ollama_classify_folder(
                folder.name, str(folder),
                url=settings['url'], model=settings['model'])

            if llm_result.get('category'):
                llm_ok += 1
                clean_name = llm_result.get('name', folder.name)
                self.log.emit(f"  {folder.name}")
                if clean_name != folder.name:
                    self.log.emit(f"    LLM renamed: \"{clean_name}\"")
                self.log.emit(f"    -->  {llm_result['category']}  ({llm_result['confidence']}%) [llm]")

                self.result_ready.emit({
                    'folder_name': folder.name,
                    'folder_path': str(folder),
                    'category': llm_result['category'],
                    'confidence': llm_result['confidence'],
                    'cleaned_name': clean_name,
                    'source_depth': 0,
                    'method': 'llm',
                    'detail': llm_result.get('detail', ''),
                    'topic': None,
                    'llm_name': clean_name,
                })
            else:
                # LLM failed for this folder — fall back to rule-based
                llm_fail += 1
                self.log.emit(f"  {folder.name}")
                self.log.emit(f"    LLM failed ({llm_result.get('detail', 'unknown')}), using rule-based...")
                rule_result = tiered_classify(folder.name, str(folder))
                cat = rule_result['category']
                conf = rule_result['confidence']
                method = rule_result['method']
                detail = rule_result['detail']
                topic = rule_result.get('topic')

                if cat:
                    self.log.emit(f"    -->  {cat}  ({conf:.0f}%) [{method}] (fallback)")

                self.result_ready.emit({
                    'folder_name': folder.name,
                    'folder_path': str(folder),
                    'category': cat,
                    'confidence': conf,
                    'cleaned_name': rule_result['cleaned_name'],
                    'source_depth': 0,
                    'method': method or 'none',
                    'detail': detail,
                    'topic': topic,
                    'llm_name': None,
                })

        elapsed = time.time() - t0
        self.log.emit(f"\n  LLM results: {llm_ok} classified, {llm_fail} fell back to rules")
        if cached_hits: self.log.emit(f"  Cache hits: {cached_hits}")
        if correction_hits: self.log.emit(f"  Learned corrections: {correction_hits}")
        if elapsed > 1: self.log.emit(f"  Scan time: {elapsed:.1f}s")
        _close_cache_conn()
        self.finished.emit()

    def _fallback_scan(self, folders):
        """Full rule-based fallback if Ollama is unreachable."""
        total = len(folders)
        for idx, folder in enumerate(folders):
            if self._cancelled:
                self.log.emit(f"  Scan cancelled at {idx}/{total}")
                break
            self.progress.emit(idx + 1, total)
            top_result = tiered_classify(folder.name, str(folder))
            cat = top_result['category']
            if cat:
                self.log.emit(f"  {folder.name}  -->  {cat}  ({top_result['confidence']:.0f}%)")
            self.result_ready.emit({
                'folder_name': folder.name,
                'folder_path': str(folder),
                'category': cat,
                'confidence': top_result['confidence'],
                'cleaned_name': top_result['cleaned_name'],
                'source_depth': 0,
                'method': top_result['method'],
                'detail': top_result['detail'],
                'topic': top_result.get('topic'),
                'llm_name': None,
            })
        _close_cache_conn()
        self.finished.emit()


# ── Ollama Auto-Setup Worker ──────────────────────────────────────────────────
class OllamaSetupWorker(QThread):
    """Background worker that ensures Ollama is installed, running, and has the
    required model. Runs on app launch so LLM is ready when the user hits Scan."""
    log = pyqtSignal(str)
    status = pyqtSignal(str)  # short status for UI label
    finished = pyqtSignal(bool)  # True = ready, False = setup failed

    def __init__(self, model: str = None, url: str = None):
        super().__init__()
        s = load_ollama_settings()
        self.model = model or s['model']
        self.url = url or s['url']

    def run(self):
        import time
        try:
            self._setup()
        except Exception as e:
            self.log.emit(f"  Ollama setup error: {e}")
            self.status.emit("LLM: setup failed")
            self.finished.emit(False)

    def _setup(self):
        import time

        # ── Step 1: Check if Ollama binary exists ──
        binary = _find_ollama_binary()
        if binary:
            self.log.emit(f"  Ollama found: {binary}")
        else:
            self.log.emit("  Ollama not found, installing...")
            self.status.emit("LLM: installing Ollama...")
            if not self._install_ollama():
                self.status.emit("LLM: install failed")
                self.finished.emit(False)
                return
            binary = _find_ollama_binary()
            if not binary:
                self.log.emit("  ERROR: Ollama installed but binary not found in PATH")
                self.status.emit("LLM: not in PATH")
                self.finished.emit(False)
                return
            self.log.emit(f"  Ollama installed: {binary}")

        # ── Step 2: Ensure Ollama server is running ──
        if _is_ollama_server_running(self.url):
            self.log.emit("  Ollama server is running")
        else:
            self.log.emit("  Starting Ollama server...")
            self.status.emit("LLM: starting server...")
            self._start_server(binary)
            # Wait for server to come up (up to 15 seconds)
            for i in range(30):
                time.sleep(0.5)
                if _is_ollama_server_running(self.url):
                    break
            if _is_ollama_server_running(self.url):
                self.log.emit("  Ollama server started")
            else:
                self.log.emit("  WARNING: Ollama server did not start within 15s")
                self.log.emit("  You may need to start it manually: ollama serve")
                self.status.emit("LLM: server not responding")
                self.finished.emit(False)
                return

        # ── Step 3: Check if model is pulled ──
        if _ollama_has_model(self.model, self.url):
            self.log.emit(f"  Model ready: {self.model}")
            self.status.emit(f"LLM: {self.model}")
            self.finished.emit(True)
            return

        # ── Step 4: Pull the model ──
        self.log.emit(f"  Pulling model: {self.model} (this may take several minutes)...")
        self.status.emit(f"LLM: pulling {self.model}...")
        if self._pull_model(binary):
            self.log.emit(f"  Model ready: {self.model}")
            self.status.emit(f"LLM: {self.model}")
            self.finished.emit(True)
        else:
            self.log.emit(f"  WARNING: Model pull may have failed. Check: ollama list")
            self.status.emit(f"LLM: pull failed")
            self.finished.emit(False)

    def _install_ollama(self) -> bool:
        """Install Ollama. Returns True on success."""
        try:
            if sys.platform == 'win32':
                return self._install_windows()
            else:
                return self._install_unix()
        except Exception as e:
            self.log.emit(f"  Install error: {e}")
            return False

    def _install_windows(self) -> bool:
        """Download and silently install Ollama on Windows."""
        import urllib.request
        installer_url = "https://ollama.com/download/OllamaSetup.exe"
        installer_path = os.path.join(os.environ.get('TEMP', '.'), 'OllamaSetup.exe')
        self.log.emit(f"  Downloading Ollama installer...")
        try:
            urllib.request.urlretrieve(installer_url, installer_path)
        except Exception as e:
            self.log.emit(f"  Download failed: {e}")
            return False
        self.log.emit("  Running installer (silent)...")
        try:
            # /VERYSILENT = no UI, /SUPPRESSMSGBOXES = no dialogs
            result = subprocess.run(
                [installer_path, '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'],
                timeout=300, capture_output=True)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.log.emit("  Installer timed out (5 min)")
            return False
        except Exception as e:
            self.log.emit(f"  Installer failed: {e}")
            return False
        finally:
            try: os.remove(installer_path)
            except OSError: pass

    def _install_unix(self) -> bool:
        """Install Ollama on Linux/macOS via official script."""
        self.log.emit("  Running: curl -fsSL https://ollama.com/install.sh | sh")
        try:
            result = subprocess.run(
                ['bash', '-c', 'curl -fsSL https://ollama.com/install.sh | sh'],
                timeout=120, capture_output=True, text=True)
            if result.returncode == 0:
                return True
            self.log.emit(f"  Install script output: {result.stderr[-200:]}")
            return False
        except FileNotFoundError:
            self.log.emit("  curl or bash not found")
            return False
        except Exception as e:
            self.log.emit(f"  Install failed: {e}")
            return False

    def _start_server(self, binary: str):
        """Start Ollama server in background."""
        try:
            if sys.platform == 'win32':
                # On Windows, 'ollama serve' or just launching ollama starts the server
                subprocess.Popen(
                    [binary, 'serve'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
            else:
                subprocess.Popen(
                    [binary, 'serve'],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    start_new_session=True)
        except Exception as e:
            self.log.emit(f"  Failed to start server: {e}")

    def _pull_model(self, binary: str) -> bool:
        """Pull a model using the ollama CLI. Returns True on success."""
        try:
            result = subprocess.run(
                [binary, 'pull', self.model],
                timeout=600,  # 10 min max for model download
                capture_output=True, text=True)
            return result.returncode == 0
        except subprocess.TimeoutExpired:
            self.log.emit("  Model pull timed out (10 min)")
            return False
        except Exception as e:
            self.log.emit(f"  Model pull error: {e}")
            return False


# ── Safe merge (standalone for use in workers) ─────────────────────────────────
def safe_merge_move(src, dst, log_cb=None, check_hashes=False):
    """Move src into dst, merging contents. Only overwrites duplicate files.
    Preserves all unique files in both src and dst. Never deletes data.
    If check_hashes=True, skips identical files instead of overwriting."""
    merged = 0; skipped = 0
    for dirpath, dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        dest_dir = os.path.join(dst, rel) if rel != '.' else dst
        os.makedirs(dest_dir, exist_ok=True)
        for fname in filenames:
            src_file = os.path.join(dirpath, fname)
            dst_file = os.path.join(dest_dir, fname)
            if os.path.exists(dst_file):
                if check_hashes:
                    src_hash = hash_file(src_file)
                    dst_hash = hash_file(dst_file)
                    if src_hash and dst_hash and src_hash == dst_hash:
                        if log_cb:
                            log_cb(f"    Skipped (identical): {os.path.relpath(src_file, src)}")
                        skipped += 1
                        os.remove(src_file)  # Remove source since dest is identical
                        continue
                os.remove(dst_file)
                merged += 1
            if log_cb:
                log_cb(f"    Moving: {os.path.relpath(src_file, src)}")
            shutil.move(src_file, dst_file)
    for dirpath, dirnames, filenames in os.walk(src, topdown=False):
        try:
            os.rmdir(dirpath)
        except OSError:
            pass
    return merged, skipped


# ── Apply Workers ──────────────────────────────────────────────────────────────
class ApplyAepWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    item_done = pyqtSignal(int, str)
    finished = pyqtSignal(int, int, list)  # ok, err, undo_ops

    def __init__(self, work_items, check_hashes=False):
        super().__init__()
        self.work_items = work_items
        self.check_hashes = check_hashes

    def run(self):
        ok = err = 0; undo_ops = []
        total = len(self.work_items)
        ts = datetime.now().isoformat()
        for idx, (ri, it) in enumerate(self.work_items):
            self.progress.emit(idx + 1, total)
            self.log.emit(f"  [{idx+1}/{total}] {it.current_name}  ->  {it.new_name}")
            try:
                d = it.full_new_path
                if os.path.exists(d):
                    merged, skipped = safe_merge_move(it.full_current_path, d,
                        log_cb=self.log.emit, check_hashes=self.check_hashes)
                    self.log.emit(f"  Merged ({merged} replaced, {skipped} identical skipped)")
                else:
                    os.rename(it.full_current_path, d)
                ok += 1
                undo_ops.append({'type': 'rename', 'src': d, 'dst': it.full_current_path,
                    'timestamp': ts, 'category': '', 'confidence': '', 'status': 'Done'})
                self.log.emit(f"  \u2705 Done")
                self.item_done.emit(ri, "Done")
            except Exception as e:
                err += 1
                self.log.emit(f"  \u274C Error: {e}")
                # Attempt atomic rollback
                if os.path.exists(it.full_new_path) and not os.path.exists(it.full_current_path):
                    try:
                        os.rename(it.full_new_path, it.full_current_path)
                        self.log.emit(f"  Rolled back to original location")
                    except Exception:
                        pass
                self.item_done.emit(ri, "Error")
        self.finished.emit(ok, err, undo_ops)


class ApplyCatWorker(QThread):
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)
    item_done = pyqtSignal(int, str)
    finished = pyqtSignal(int, int, list)  # ok, err, undo_ops

    def __init__(self, work_items, check_hashes=False):
        super().__init__()
        self.work_items = work_items
        self.check_hashes = check_hashes

    def run(self):
        ok = err = 0; undo_ops = []
        total = len(self.work_items)
        ts = datetime.now().isoformat()
        for idx, (ri, it) in enumerate(self.work_items):
            self.progress.emit(idx + 1, total)
            self.log.emit(f"  [{idx+1}/{total}] {it.folder_name}  ->  {it.category}/")
            try:
                os.makedirs(os.path.dirname(it.full_dest_path), exist_ok=True)
                d = it.full_dest_path
                if os.path.exists(d):
                    merged, skipped = safe_merge_move(it.full_source_path, d,
                        log_cb=self.log.emit, check_hashes=self.check_hashes)
                    self.log.emit(f"  Merged ({merged} replaced, {skipped} identical skipped)")
                else:
                    shutil.move(it.full_source_path, d)
                ok += 1
                undo_ops.append({'type': 'move', 'src': d, 'dst': it.full_source_path,
                    'timestamp': ts, 'category': it.category, 'confidence': f'{it.confidence:.0f}',
                    'status': 'Done'})
                self.log.emit(f"  \u2705 Done")
                self.item_done.emit(ri, "Done")
                # Store successful classification in cache
                cache_store(it.folder_name, it.full_source_path,
                    {'category': it.category, 'confidence': it.confidence,
                     'cleaned_name': it.cleaned_name, 'method': it.method,
                     'detail': it.detail, 'topic': it.topic})
            except Exception as e:
                err += 1
                self.log.emit(f"  \u274C Error: {e}")
                # Attempt atomic rollback for this folder
                if os.path.exists(it.full_dest_path) and not os.path.exists(it.full_source_path):
                    try:
                        shutil.move(it.full_dest_path, it.full_source_path)
                        self.log.emit(f"  Rolled back to original location")
                    except Exception:
                        pass
                self.item_done.emit(ri, "Error")
        self.finished.emit(ok, err, undo_ops)



# ── Helpers ────────────────────────────────────────────────────────────────────
def format_size(b):
    if b >= 1_073_741_824: return f"{b/1_073_741_824:.1f} GB"
    if b >= 1_048_576: return f"{b/1_048_576:.1f} MB"
    if b >= 1024: return f"{b/1024:.1f} KB"
    return f"{b} B"


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOM CATEGORIES DIALOG
# ══════════════════════════════════════════════════════════════════════════════
class CustomCategoriesDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Custom Categories")
        self.setMinimumSize(550, 450)
        self.setStyleSheet(DARK_STYLE)
        self.custom_cats = load_custom_categories()

        lay = QVBoxLayout(self)
        lbl = QLabel("Add, edit, or remove custom categories. These supplement the built-in categories.")
        lbl.setWordWrap(True); lay.addWidget(lbl)

        self.lst = QListWidget()
        self._refresh_list()
        lay.addWidget(self.lst)

        btn_row = QHBoxLayout()
        for text, cb in [("Add", self._add), ("Edit Keywords", self._edit), ("Remove", self._remove)]:
            b = QPushButton(text); b.clicked.connect(cb); btn_row.addWidget(b)
        lay.addLayout(btn_row)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.accepted.connect(self.accept); bb.rejected.connect(self.reject)
        lay.addWidget(bb)

    def _refresh_list(self):
        self.lst.clear()
        for name, kws in self.custom_cats:
            self.lst.addItem(f"{name}  [{', '.join(kws[:5])}{'...' if len(kws)>5 else ''}]")

    def _add(self):
        name, ok = QInputDialog.getText(self, "New Category", "Category name:")
        if not ok or not name.strip(): return
        kws, ok2 = QInputDialog.getText(self, "Keywords", "Comma-separated keywords:")
        if not ok2: return
        keywords = [k.strip().lower() for k in kws.split(',') if k.strip()]
        if not keywords: keywords = [name.strip().lower()]
        self.custom_cats.append((name.strip(), keywords))
        self._refresh_list()

    def _edit(self):
        row = self.lst.currentRow()
        if row < 0: return
        name, kws = self.custom_cats[row]
        new_kws, ok = QInputDialog.getText(self, f"Edit Keywords: {name}",
            "Comma-separated keywords:", text=', '.join(kws))
        if not ok: return
        keywords = [k.strip().lower() for k in new_kws.split(',') if k.strip()]
        if keywords:
            self.custom_cats[row] = (name, keywords)
            self._refresh_list()

    def _remove(self):
        row = self.lst.currentRow()
        if row < 0: return
        self.custom_cats.pop(row)
        self._refresh_list()

    def get_categories(self):
        return list(self.custom_cats)


# ══════════════════════════════════════════════════════════════════════════════
# DESTINATION TREE PREVIEW DIALOG
# ══════════════════════════════════════════════════════════════════════════════
class DestTreeDialog(QDialog):
    def __init__(self, items, dest_root, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Destination Preview")
        self.setMinimumSize(500, 500)
        self.setStyleSheet(DARK_STYLE)

        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"Output structure under: {dest_root}"))

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Folder / Category", "Count"])
        self.tree.setColumnWidth(0, 350)

        # Build tree from items
        cats = {}
        for it in items:
            if it.selected and it.status == "Pending":
                cats.setdefault(it.category, []).append(it.folder_name)

        for cat in sorted(cats.keys()):
            cat_item = QTreeWidgetItem([cat, str(len(cats[cat]))])
            cat_item.setForeground(0, QColor("#4ade80"))
            for folder in sorted(cats[cat]):
                child = QTreeWidgetItem([folder, ""])
                cat_item.addChild(child)
            self.tree.addTopLevelItem(cat_item)

        self.tree.expandAll()
        lay.addWidget(self.tree)

        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN WINDOW
# ══════════════════════════════════════════════════════════════════════════════
class OllamaSettingsDialog(QDialog):
    """Dialog for configuring Ollama LLM integration."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Ollama LLM Settings")
        self.setMinimumWidth(480)
        self.settings = load_ollama_settings()
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        # URL
        row_url = QHBoxLayout()
        row_url.addWidget(QLabel("Ollama URL:"))
        self.txt_url = QLineEdit(self.settings['url'])
        self.txt_url.setPlaceholderText("http://localhost:11434")
        row_url.addWidget(self.txt_url, 1)
        layout.addLayout(row_url)

        # Model
        row_model = QHBoxLayout()
        row_model.addWidget(QLabel("Model:"))
        self.txt_model = QLineEdit(self.settings['model'])
        self.txt_model.setPlaceholderText("qwen2.5:7b")
        row_model.addWidget(self.txt_model, 1)
        layout.addLayout(row_model)

        # Recommended models info
        info = QLabel(
            "Recommended models for classification:\n"
            "  qwen2.5:7b - Best accuracy/speed balance\n"
            "  llama3.2:3b - Fastest, lightweight\n"
            "  gemma3:4b - Good structured output\n"
            "  mistral:7b - Strong reasoning\n\n"
            "Install: ollama pull qwen2.5:7b"
        )
        info.setStyleSheet("color: #888; font-size: 11px; padding: 8px; "
                           "background: rgba(255,255,255,0.05); border-radius: 4px;")
        info.setWordWrap(True)
        layout.addWidget(info)

        # Test connection button + status
        row_test = QHBoxLayout()
        btn_test = QPushButton("Test Connection")
        btn_test.clicked.connect(self._test)
        row_test.addWidget(btn_test)
        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        row_test.addWidget(self.lbl_status, 1)
        layout.addLayout(row_test)

        # Buttons
        row_btns = QHBoxLayout()
        btn_save = QPushButton("Save")
        btn_save.clicked.connect(self._save)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        row_btns.addStretch()
        row_btns.addWidget(btn_save)
        row_btns.addWidget(btn_cancel)
        layout.addLayout(row_btns)

    def _test(self):
        self.lbl_status.setText("Testing...")
        self.lbl_status.setStyleSheet("color: #f59e0b;")
        QApplication.processEvents()
        ok, msg, models = ollama_test_connection(self.txt_url.text().strip(),
                                                  self.txt_model.text().strip())
        self.lbl_status.setText(msg)
        self.lbl_status.setStyleSheet(f"color: {'#4ade80' if ok else '#ef4444'};")

    def _save(self):
        self.settings['url'] = self.txt_url.text().strip() or _OLLAMA_DEFAULTS['url']
        self.settings['model'] = self.txt_model.text().strip() or _OLLAMA_DEFAULTS['model']
        save_ollama_settings(self.settings)
        self.accept()



class FileOrganizer(QMainWindow):
    OP_AEP = 0
    OP_CAT = 1

    def __init__(self):
        super().__init__()
        self.setWindowTitle("FileOrganizer v5.4")
        self.setMinimumSize(1050, 700)
        self.aep_items = []
        self.cat_items = []
        self._cat_unmatched = 0
        self.undo_ops = []
        self.settings = QSettings("FileOrganizer", "FileOrganizer")
        self._ollama_ready = False

        # Enable drag & drop
        self.setAcceptDrops(True)

        self._build_ui()
        self._load_settings()

        # Launch Ollama auto-setup in background
        self._start_ollama_setup()

    # ═══ DRAG & DROP ═══════════════════════════════════════════════════════════
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if os.path.isdir(path):
                self.txt_src.setText(path)
                self._log(f"Dropped: {path}")

    # ═══ SETTINGS PERSISTENCE ═════════════════════════════════════════════════
    def _load_settings(self):
        src = self.settings.value("last_source", "")
        dst = self.settings.value("last_dest", "")
        op = self.settings.value("last_op", 0, type=int)
        thresh = self.settings.value("confidence_threshold", 0, type=int)
        use_llm = self.settings.value("use_llm", True, type=bool)
        scan_depth = self.settings.value("scan_depth", 0, type=int)
        if src: self.txt_src.setText(src)
        if dst: self.txt_dst.setText(dst)
        if op < self.cmb_op.count(): self.cmb_op.setCurrentIndex(op)
        self.sld_conf.setValue(thresh)
        self.chk_llm.setChecked(use_llm)
        self.spn_depth.setValue(scan_depth)

    def _save_settings(self):
        self.settings.setValue("last_source", self.txt_src.text())
        self.settings.setValue("last_dest", self.txt_dst.text())
        self.settings.setValue("last_op", self.cmb_op.currentIndex())
        self.settings.setValue("confidence_threshold", self.sld_conf.value())
        self.settings.setValue("use_llm", self.chk_llm.isChecked())
        self.settings.setValue("scan_depth", self.spn_depth.value())

    def closeEvent(self, event):
        self._save_settings()
        super().closeEvent(event)

    # ═══ OLLAMA AUTO-SETUP ════════════════════════════════════════════════════
    def _start_ollama_setup(self):
        """Launch background Ollama setup (install + pull model) on app start."""
        self._log("Ollama LLM: initializing...")
        s = load_ollama_settings()
        self._ollama_worker = OllamaSetupWorker(s['model'], s['url'])
        self._ollama_worker.log.connect(self._log)
        self._ollama_worker.status.connect(self._on_ollama_status)
        self._ollama_worker.finished.connect(self._on_ollama_ready)
        self._ollama_worker.start()

    def _on_ollama_status(self, msg):
        self.lbl_llm_status.setText(msg)
        color = '#4ade80' if 'ready' in msg.lower() or ':' in msg and 'failed' not in msg.lower() \
                else '#ef4444' if 'failed' in msg.lower() else '#f59e0b'
        self.lbl_llm_status.setStyleSheet(f"color: {color}; font-size: 11px;")

    def _on_ollama_ready(self, success):
        self._ollama_ready = success
        if success:
            s = load_ollama_settings()
            self.lbl_llm_status.setText(f"LLM: {s['model']}")
            self.lbl_llm_status.setStyleSheet("color: #4ade80; font-size: 11px;")
            self._log("Ollama LLM: ready")
        else:
            self.lbl_llm_status.setText("LLM: unavailable")
            self.lbl_llm_status.setStyleSheet("color: #ef4444; font-size: 11px;")
            self._log("Ollama LLM: not available (rule-based engine will be used)")

    # ═══ BUILD UI ═════════════════════════════════════════════════════════════

    def _build_ui(self):
        cw = QWidget(); self.setCentralWidget(cw)
        root = QVBoxLayout(cw)
        root.setSpacing(0)
        root.setContentsMargins(0, 0, 0, 0)

        # Menu bar - moves config buttons out of the cramped toolbar
        mbar = self.menuBar()
        menu_tools = mbar.addMenu("Settings")
        menu_tools.addAction("Edit Categories", self._open_custom_cats)
        menu_tools.addAction("Envato API Key", self._set_envato_key)
        menu_tools.addAction("Ollama LLM", self._open_ollama_settings)
        menu_tools.addSeparator()
        menu_tools.addAction("Import Rules", self._import_rules)
        menu_tools.addAction("Export Rules", self._export_rules)
        menu_tools.addSeparator()
        menu_tools.addAction("Clear Cache", self._clear_cache)

        # Header bar
        header = QWidget()
        header.setFixedHeight(44)
        header.setStyleSheet("background-color: #0a1219; border-bottom: 1px solid #1b2838;")
        h_lay = QHBoxLayout(header)
        h_lay.setContentsMargins(20, 0, 20, 0)
        lbl_brand = QLabel("FileOrganizer")
        lbl_brand.setStyleSheet("color: #c5cdd8; font-size: 16px; font-weight: 700; letter-spacing: -0.5px;")
        h_lay.addWidget(lbl_brand)
        lbl_ver = QLabel("v5.4")
        lbl_ver.setStyleSheet("color: #3d6a9e; font-size: 11px; font-weight: 600; padding-top: 3px;")
        h_lay.addWidget(lbl_ver)
        h_lay.addStretch()
        self.lbl_llm_status = QLabel("LLM: checking...")
        self.lbl_llm_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
        h_lay.addWidget(self.lbl_llm_status)
        root.addWidget(header)

        # Main content area
        body = QWidget()
        main = QVBoxLayout(body)
        main.setSpacing(10)
        main.setContentsMargins(16, 14, 16, 10)

        # Mode selector
        row_op = QHBoxLayout(); row_op.setSpacing(10)
        lbl_op = QLabel("MODE")
        lbl_op.setStyleSheet("color: #6b7785; font-weight: 600; font-size: 11px;")
        lbl_op.setFixedWidth(42)
        row_op.addWidget(lbl_op)
        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Rename Folders by Best .aep File", "Categorize Folders into Groups"])
        self.cmb_op.currentIndexChanged.connect(self._on_op_changed)
        row_op.addWidget(self.cmb_op, 1)
        main.addLayout(row_op)

        # Source path
        row_src = QHBoxLayout(); row_src.setSpacing(8)
        lbl_src = QLabel("SOURCE")
        lbl_src.setStyleSheet("color: #6b7785; font-weight: 600; font-size: 11px;")
        lbl_src.setFixedWidth(55)
        row_src.addWidget(lbl_src)
        self.txt_src = QLineEdit()
        self.txt_src.setPlaceholderText("Drag a folder here or click Browse...")
        row_src.addWidget(self.txt_src, 1)
        btn_src = QPushButton("Browse"); btn_src.setFixedWidth(75)
        btn_src.clicked.connect(self._browse_src)
        row_src.addWidget(btn_src)
        main.addLayout(row_src)

        # Destination path (categorize mode)
        self.row_dst_w = QWidget()
        row_dst = QHBoxLayout(self.row_dst_w)
        row_dst.setContentsMargins(0, 0, 0, 0); row_dst.setSpacing(8)
        lbl_dst = QLabel("OUTPUT")
        lbl_dst.setStyleSheet("color: #6b7785; font-weight: 600; font-size: 11px;")
        lbl_dst.setFixedWidth(55)
        row_dst.addWidget(lbl_dst)
        self.txt_dst = QLineEdit()
        self.txt_dst.setPlaceholderText("Destination root for category folders...")
        row_dst.addWidget(self.txt_dst, 1)
        btn_dst = QPushButton("Browse"); btn_dst.setFixedWidth(75)
        btn_dst.clicked.connect(self._browse_dst)
        row_dst.addWidget(btn_dst)
        self.row_dst_w.hide()
        main.addWidget(self.row_dst_w)

        # Action toolbar
        toolbar = QHBoxLayout(); toolbar.setSpacing(6)

        self.btn_scan = QPushButton("  Scan  ")
        self.btn_scan.setProperty("class", "primary")
        self.btn_scan.setFixedHeight(34)
        self.btn_scan.clicked.connect(self._on_scan)
        toolbar.addWidget(self.btn_scan)

        self.btn_apply = QPushButton("  Apply  ")
        self.btn_apply.setProperty("class", "apply")
        self.btn_apply.setFixedHeight(34)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_apply)
        toolbar.addWidget(self.btn_apply)

        self.btn_preview = QPushButton("Preview")
        self.btn_preview.setFixedHeight(34)
        self.btn_preview.clicked.connect(self._show_preview)
        self.btn_preview.setEnabled(False)
        toolbar.addWidget(self.btn_preview)

        self.btn_export = QPushButton("Export Plan")
        self.btn_export.setFixedHeight(34); self.btn_export.setEnabled(False)
        self.btn_export.setToolTip("Export the classification plan as CSV")
        self.btn_export.clicked.connect(self._export_plan)
        toolbar.addWidget(self.btn_export)

        self.btn_undo = QPushButton("Undo")
        self.btn_undo.setFixedHeight(34)
        self.btn_undo.clicked.connect(self._on_undo)
        self.btn_undo.setEnabled(bool(load_undo_log()))
        toolbar.addWidget(self.btn_undo)

        sep = QFrame(); sep.setFrameShape(QFrame.Shape.VLine)
        sep.setStyleSheet("color: #1b2838;"); sep.setFixedHeight(22)
        toolbar.addWidget(sep)

        for text, slot in [("All", self._sel_all), ("None", self._sel_none), ("Invert", self._sel_inv)]:
            b = QPushButton(text); b.setProperty("class", "toolbar")
            b.clicked.connect(slot); toolbar.addWidget(b)

        btn_chk = QPushButton("\u2611 Check"); btn_chk.setProperty("class", "toolbar")
        btn_chk.setToolTip("Check highlighted rows"); btn_chk.clicked.connect(self._check_selected)
        toolbar.addWidget(btn_chk)
        btn_uchk = QPushButton("\u2610 Uncheck"); btn_uchk.setProperty("class", "toolbar")
        btn_uchk.setToolTip("Uncheck highlighted rows"); btn_uchk.clicked.connect(self._uncheck_selected)
        toolbar.addWidget(btn_uchk)

        toolbar.addStretch()

        self.chk_llm = QCheckBox("LLM")
        self.chk_llm.setToolTip("Use Ollama LLM for AI-powered classification")
        self.chk_llm.setStyleSheet("QCheckBox { color: #bb86fc; font-weight: bold; font-size: 12px; }")
        toolbar.addWidget(self.chk_llm)

        self.chk_hash = QCheckBox("Dedup")
        self.chk_hash.setToolTip("Skip identical files (MD5 hash)")
        toolbar.addWidget(self.chk_hash)

        lbl_depth = QLabel("Depth:")
        lbl_depth.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 12px;")
        toolbar.addWidget(lbl_depth)
        self.spn_depth = QSpinBox()
        self.spn_depth.setRange(0, 3); self.spn_depth.setValue(0)
        self.spn_depth.setFixedWidth(48)
        self.spn_depth.setToolTip("Scan depth: 0=top-level, 1+=subfolders")
        toolbar.addWidget(self.spn_depth)

        main.addLayout(toolbar)

        # Filter bar
        row_filter = QHBoxLayout(); row_filter.setSpacing(8)
        self.txt_search = QLineEdit()
        self.txt_search.setPlaceholderText("\U0001f50d  Filter results...")
        self.txt_search.textChanged.connect(self._apply_filter)
        row_filter.addWidget(self.txt_search, 1)
        lbl_cf = QLabel("Confidence:")
        lbl_cf.setStyleSheet("color: #6b7785; font-size: 11px;")
        row_filter.addWidget(lbl_cf)
        self.sld_conf = QSlider(Qt.Orientation.Horizontal)
        self.sld_conf.setRange(0, 100); self.sld_conf.setValue(0)
        self.sld_conf.setFixedWidth(120)
        self.sld_conf.valueChanged.connect(self._on_conf_changed)
        row_filter.addWidget(self.sld_conf)
        self.lbl_conf = QLabel("0%"); self.lbl_conf.setFixedWidth(35)
        self.lbl_conf.setStyleSheet("color: #6b7785; font-size: 12px;")
        row_filter.addWidget(self.lbl_conf)
        main.addLayout(row_filter)

        # Table
        self.tbl = QTableWidget()
        self.tbl.setAlternatingRowColors(True)
        self.tbl.setSortingEnabled(False)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._context_menu)
        self.tbl.setShowGrid(False)
        self._setup_aep_tbl()
        main.addWidget(self.tbl, 1)

        # Empty state
        self.lbl_empty = QLabel("Drop a folder here or click Browse, then Scan")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("color: #2a3f5f; font-size: 15px; padding: 50px; font-weight: 500;")
        main.addWidget(self.lbl_empty)

        # Stats
        self.lbl_stats = QLabel("")
        self.lbl_stats.setStyleSheet("color: #6b7785; font-size: 12px; padding: 4px 0;")
        main.addWidget(self.lbl_stats)

        # Log console
        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True); self.txt_log.setMaximumHeight(130)
        main.addWidget(self.txt_log)

        root.addWidget(body, 1)

        # Status bar
        status = QWidget()
        status.setFixedHeight(30)
        status.setStyleSheet("background-color: #0a1219; border-top: 1px solid #1b2838;")
        s_lay = QHBoxLayout(status)
        s_lay.setContentsMargins(16, 0, 16, 0)
        self.lbl_prog = QLabel("")
        self.lbl_prog.setStyleSheet("color: #6b7785; font-size: 11px;")
        s_lay.addWidget(self.lbl_prog)
        s_lay.addStretch()
        root.addWidget(status)

        self.setStyleSheet(DARK_STYLE)

        # Backward compat refs (moved to menu bar)
        self.btn_custom_cats = None
        self.btn_envato = None
        self.btn_ollama = None
        self.btn_export_rules = None
        self.btn_import_rules = None
        self.btn_clear_cache = None

    # ═══ CONTEXT MENU (RIGHT-CLICK) ══════════════════════════════════════════
    def _context_menu(self, pos):
        row = self.tbl.rowAt(pos.y())
        if row < 0: return
        menu = QMenu(self)
        is_cat = self.cmb_op.currentIndex() == self.OP_CAT

        # Check/uncheck selected rows
        sel_rows = sorted(set(idx.row() for idx in self.tbl.selectionModel().selectedRows()))
        act_check = act_uncheck = None
        if len(sel_rows) > 1:
            act_check = menu.addAction(f"\u2611 Check {len(sel_rows)} Rows")
            act_uncheck = menu.addAction(f"\u2610 Uncheck {len(sel_rows)} Rows")
            menu.addSeparator()

        # Open folder in explorer
        act_open = menu.addAction("Open Folder in Explorer")
        # Reassign category (categorize mode only)
        act_reassign = None; act_batch = None
        if is_cat and row < len(self.cat_items):
            act_reassign = menu.addAction("Change Category...")
            if len(sel_rows) > 1:
                act_batch = menu.addAction(f"Batch Reassign ({len(sel_rows)} rows)...")

        action = menu.exec(self.tbl.viewport().mapToGlobal(pos))
        if action == act_check:
            self._check_selected()
        elif action == act_uncheck:
            self._uncheck_selected()
        elif action == act_open:
            items = self.cat_items if is_cat else self.aep_items
            if row < len(items):
                path = items[row].full_source_path if is_cat else items[row].full_current_path
                if sys.platform == 'win32':
                    os.startfile(path)
                elif sys.platform == 'darwin':
                    subprocess.Popen(['open', path])
                else:
                    subprocess.Popen(['xdg-open', path])
        elif action == act_reassign and is_cat and row < len(self.cat_items):
            self._reassign_category(row)
        elif action == act_batch and is_cat:
            self._batch_reassign(sel_rows)

    def _reassign_category(self, row):
        it = self.cat_items[row]
        all_cats = get_all_category_names()
        current_idx = all_cats.index(it.category) if it.category in all_cats else 0
        new_cat, ok = QInputDialog.getItem(self, "Change Category",
            f"Select category for: {it.folder_name}", all_cats, current_idx, False)
        if ok and new_cat:
            it.category = new_cat; it.method = 'Manual'; it.detail = 'User override'; it.topic = ''
            dst_dir = self.txt_dst.text()
            it.full_dest_path = os.path.join(dst_dir, new_cat, it.folder_name)
            # Update dest path column
            di = self.tbl.item(row, 3)
            if di: di.setText(it.full_dest_path); di.setForeground(QColor("#38bdf8")); di.setToolTip(it.full_dest_path)
            # Update confidence to show it was manual
            cfi = self.tbl.item(row, 4)
            if cfi: cfi.setText("--"); cfi.setForeground(QColor("#38bdf8"))
            # Update method column
            mi = self.tbl.item(row, 5)
            if mi: mi.setText("Manual"); mi.setForeground(QColor("#38bdf8"))
            self._log(f"  Reassigned: {it.folder_name}  ->  {new_cat}")
            # Save correction for future learning
            save_correction(it.folder_name, new_cat)
            self._stats_cat()

    def _batch_reassign(self, rows):
        """Reassign multiple selected rows to a single category."""
        all_cats = get_all_category_names()
        new_cat, ok = QInputDialog.getItem(self, "Batch Reassign",
            f"Select category for {len(rows)} folders:", all_cats, 0, False)
        if not ok or not new_cat: return
        dst_dir = self.txt_dst.text()
        for row in rows:
            if row >= len(self.cat_items): continue
            it = self.cat_items[row]
            it.category = new_cat; it.method = 'Manual'; it.detail = 'Batch user override'; it.topic = ''
            it.full_dest_path = os.path.join(dst_dir, new_cat, it.folder_name)
            # Update table cells
            di = self.tbl.item(row, 3)
            if di: di.setText(it.full_dest_path); di.setForeground(QColor("#38bdf8")); di.setToolTip(it.full_dest_path)
            cfi = self.tbl.item(row, 4)
            if cfi: cfi.setText("--"); cfi.setForeground(QColor("#38bdf8"))
            mi = self.tbl.item(row, 5)
            if mi: mi.setText("Manual"); mi.setForeground(QColor("#38bdf8"))
            # Save correction for learning
            save_correction(it.folder_name, new_cat)
        self._log(f"  Batch reassigned {len(rows)} folders  ->  {new_cat}")
        self._stats_cat()

    # ═══ CUSTOM CATEGORIES DIALOG ════════════════════════════════════════════
    def _open_custom_cats(self):
        dlg = CustomCategoriesDialog(self)
        if dlg.exec():
            save_custom_categories(dlg.get_categories())
            self._log(f"Custom categories saved ({len(dlg.get_categories())} categories)")

    # ═══ ENVATO API KEY ══════════════════════════════════════════════════════
    def _set_envato_key(self):
        current = _load_envato_api_key()
        key, ok = QInputDialog.getText(self, "Envato API Key",
            "Enter your Envato personal token (from build.envato.com):\n"
            "Leave blank to disable API enrichment.",
            text=current)
        if ok:
            key = key.strip()
            _save_envato_api_key(key)
            if key:
                self._log(f"Envato API key saved ({len(key)} chars)")
            else:
                self._log("Envato API key cleared")

    # ═══ OLLAMA LLM SETTINGS ═════════════════════════════════════════════════
    def _open_ollama_settings(self):
        dlg = OllamaSettingsDialog(self)
        if dlg.exec():
            self._log(f"Ollama settings saved: {dlg.settings['url']} / {dlg.settings['model']}")

    # ═══ DESTINATION TREE PREVIEW ════════════════════════════════════════════
    def _show_preview(self):
        if self.cmb_op.currentIndex() != self.OP_CAT: return
        dst = self.txt_dst.text()
        if not dst: return
        dlg = DestTreeDialog(self.cat_items, dst, self)
        dlg.exec()

    # ═══ UNDO ════════════════════════════════════════════════════════════════
    def _on_undo(self):
        ops = load_undo_log()
        if not ops:
            self._log("No operations to undo"); return

        count = len(ops)
        self._log(f"Undoing {count} operations...")
        ok = err = 0
        for op in reversed(ops):
            src = op.get('src', '')
            dst = op.get('dst', '')
            try:
                if os.path.exists(src):
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    shutil.move(src, dst)
                    ok += 1
                    self._log(f"  Restored: {os.path.basename(src)}")
                else:
                    self._log(f"  Skipped (not found): {src}")
            except Exception as e:
                err += 1
                self._log(f"  Error: {e}")

        clear_undo_log()
        self.btn_undo.setEnabled(False)
        self._log(f"Undo complete: {ok} restored, {err} errors")

    # ═══ FILTER / SEARCH ════════════════════════════════════════════════════
    def _apply_filter(self):
        text = self.txt_search.text().lower()
        for row in range(self.tbl.rowCount()):
            # Check if any cell in the row contains the search text
            show = True
            if text:
                show = False
                for col in range(self.tbl.columnCount()):
                    item = self.tbl.item(row, col)
                    if item and text in item.text().lower():
                        show = True; break
            self.tbl.setRowHidden(row, not show)

    # ═══ CONFIDENCE THRESHOLD ════════════════════════════════════════════════
    def _on_conf_changed(self, val):
        self.lbl_conf.setText(f"{val}%")
        if self.cmb_op.currentIndex() != self.OP_CAT: return
        # Auto-deselect items below threshold
        for idx, it in enumerate(self.cat_items):
            should_select = it.confidence >= val
            if it.selected != should_select:
                it.selected = should_select
                cb = self.tbl.cellWidget(idx, 0)
                if cb:
                    cb_inner = cb.findChild(QCheckBox)
                    if cb_inner:
                        cb_inner.blockSignals(True)
                        cb_inner.setChecked(should_select)
                        cb_inner.blockSignals(False)
        self._upd_stats()

    # ═══ OPERATION SWITCH ════════════════════════════════════════════════════
    def _on_op_changed(self, idx):
        self.row_dst_w.setVisible(idx == self.OP_CAT)
        self.btn_preview.setVisible(idx == self.OP_CAT)
        self.tbl.setRowCount(0); self.aep_items.clear(); self.cat_items.clear()
        self.lbl_stats.clear(); self.btn_apply.setEnabled(False); self.btn_preview.setEnabled(False)
        (self._setup_cat_tbl if idx == self.OP_CAT else self._setup_aep_tbl)()
        self.lbl_empty.setText("Select source folder and click Scan"); self.lbl_empty.show()

    def _setup_aep_tbl(self):
        self.tbl.setColumnCount(7)
        self.tbl.setHorizontalHeaderLabels(["","Source Path","\u2192","New Path","AEP File","Size","Status"])
        h = self.tbl.horizontalHeader(); h.setFixedHeight(36)
        for c,m in [(0,"Fixed"),(1,"Stretch"),(2,"Fixed"),(3,"Stretch"),(4,"Stretch"),(5,"Fixed"),(6,"Fixed")]:
            h.setSectionResizeMode(c, getattr(QHeaderView.ResizeMode, m))
        self.tbl.setColumnWidth(0,40); self.tbl.setColumnWidth(2,30); self.tbl.setColumnWidth(5,80); self.tbl.setColumnWidth(6,80)

    def _setup_cat_tbl(self):
        self.tbl.setColumnCount(7)
        self.tbl.setHorizontalHeaderLabels(["","Source Path","\u2192","Destination Path","Conf","Method","Status"])
        h = self.tbl.horizontalHeader(); h.setFixedHeight(36)
        for c,m in [(0,"Fixed"),(1,"Stretch"),(2,"Fixed"),(3,"Stretch"),(4,"Fixed"),(5,"Fixed"),(6,"Fixed")]:
            h.setSectionResizeMode(c, getattr(QHeaderView.ResizeMode, m))
        self.tbl.setColumnWidth(0,40); self.tbl.setColumnWidth(2,30); self.tbl.setColumnWidth(4,55); self.tbl.setColumnWidth(5,80); self.tbl.setColumnWidth(6,70)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if hasattr(self, 'lbl_empty'):
            self.lbl_empty.setGeometry(self.tbl.geometry())

    def _log(self, m):
        self.txt_log.append(m)
        self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())

    def _browse_src(self):
        d = QFileDialog.getExistingDirectory(self, "Select Source Folder", self.txt_src.text())
        if d: self.txt_src.setText(d)

    def _browse_dst(self):
        d = QFileDialog.getExistingDirectory(self, "Select Output Folder", self.txt_dst.text())
        if d: self.txt_dst.setText(d)

    def _on_scan(self):
        # If already scanning, cancel
        if getattr(self, '_scanning', False):
            self._cancel_scan()
            return

        src = self.txt_src.text()
        if not src or not os.path.isdir(src):
            self._log("Invalid source directory"); return
        self.lbl_empty.hide(); self.tbl.setRowCount(0)
        self._scanning = True
        self.tbl.setSortingEnabled(False)
        self.btn_scan.setText("Cancel"); self.btn_scan.setStyleSheet("QPushButton { color: #ef4444; font-weight: bold; }")
        self.btn_apply.setEnabled(False); self.btn_preview.setEnabled(False); self.btn_export.setEnabled(False)
        self._scan_start_time = time.time()
        if self.cmb_op.currentIndex() == self.OP_CAT:
            dst = self.txt_dst.text()
            if not dst:
                self._log("Set output directory first")
                self._reset_scan_ui(); return
            self._scan_cat(src, dst)
        else:
            self._scan_aep(src)

    def _cancel_scan(self):
        """Signal the worker to stop."""
        if hasattr(self, 'worker') and self.worker and self.worker.isRunning():
            self.worker.cancel()
            self._log("Cancelling scan...")

    def _reset_scan_ui(self):
        """Restore Scan button and state after scan completes or is cancelled."""
        self._scanning = False
        self.btn_scan.setText("Scan"); self.btn_scan.setStyleSheet("")
        self.btn_scan.setEnabled(True)
        self.lbl_prog.setText("")

    def _update_progress(self, current, total):
        """Update progress label with ETA."""
        elapsed = time.time() - getattr(self, '_scan_start_time', time.time())
        if current > 1 and elapsed > 0.5:
            avg = elapsed / current
            remaining = avg * (total - current)
            if remaining >= 60:
                eta = f"~{remaining/60:.0f}m left"
            else:
                eta = f"~{remaining:.0f}s left"
            self.lbl_prog.setText(f"Scanning {current}/{total}... ({eta})")
        else:
            self.lbl_prog.setText(f"Scanning {current}/{total}...")

    # ═══ TABLE HELPERS ═══════════════════════════════════════════════════════
    def _it(self, text):
        i = QTableWidgetItem(str(text)); i.setFlags(i.flags() & ~Qt.ItemFlag.ItemIsEditable); return i

    def _make_cb(self, checked, callback, idx):
        w = QWidget(); l = QHBoxLayout(w); l.setContentsMargins(0,0,0,0); l.setAlignment(Qt.AlignmentFlag.AlignCenter)
        cb = QCheckBox(); cb.setChecked(checked)
        cb.stateChanged.connect(lambda st, i=idx: callback(i, st))
        l.addWidget(cb); return w

    def _make_arrow(self):
        a = self._it("\u2192"); a.setTextAlignment(Qt.AlignmentFlag.AlignCenter); return a

    def _set_status(self, row, text, color, col):
        i = self.tbl.item(row, col)
        if i:
            i.setText(text); i.setForeground(QColor(color))

    # ═══ AEP SCAN ════════════════════════════════════════════════════════════
    def _scan_aep(self, src):
        self._log(f"Scanning for .aep files in: {src}")
        self.aep_items.clear(); self.tbl.setRowCount(0)
        self._aep_dest_paths = {}  # collision tracking for AEP renames
        self.worker = ScanAepWorker(src, scan_depth=self.spn_depth.value())
        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._update_progress)
        self.worker.result_ready.connect(self._on_aep_result)
        self.worker.finished.connect(self._on_aep_scan_done)
        self.worker.start()

    def _deduplicate_aep_path(self, dest_path):
        """Auto-suffix AEP rename paths that collide."""
        key = dest_path.lower()
        if key not in self._aep_dest_paths and not os.path.exists(dest_path):
            self._aep_dest_paths[key] = 1
            return dest_path

        parent = os.path.dirname(dest_path)
        base = os.path.basename(dest_path)
        n = self._aep_dest_paths.get(key, 1) + 1
        while True:
            new_name = f"{base} ({n})"
            new_path = os.path.join(parent, new_name)
            new_key = new_path.lower()
            if new_key not in self._aep_dest_paths and not os.path.exists(new_path):
                self._aep_dest_paths[key] = n
                self._aep_dest_paths[new_key] = 1
                return new_path
            n += 1

    def _on_aep_result(self, r):
        """Process a single AEP scan result live."""
        if not r['largest_aep']: return
        aep_stem = os.path.splitext(r['largest_aep'])[0]
        if is_generic_aep(aep_stem): return
        new_name = f"{r['folder_name']} - {aep_stem}"
        if r['folder_name'] in new_name and aep_stem in r['folder_name']: return
        it = RenameItem(); it.current_name = r['folder_name']; it.new_name = new_name
        it.aep_file = r.get('aep_rel_path', r['largest_aep'])
        it.file_size = format_size(r['aep_size'])
        it.full_current_path = r['folder_path']
        raw_path = os.path.join(os.path.dirname(r['folder_path']), new_name)
        it.full_new_path = self._deduplicate_aep_path(raw_path)
        # Update display name if deduped
        deduped_name = os.path.basename(it.full_new_path)
        if deduped_name != new_name:
            it.new_name = deduped_name
        it.status = "Pending"; it.selected = True
        self.aep_items.append(it); self._add_aep_row(it, len(self.aep_items)-1)

    def _on_aep_scan_done(self):
        """Finalize after AEP scan completes."""
        self._reset_scan_ui()
        self.tbl.setSortingEnabled(True)
        shown = len(self.aep_items)
        self.btn_apply.setEnabled(shown > 0)
        self.btn_export.setEnabled(shown > 0)
        self._stats_aep()
        self._log(f"Scan complete: {shown} eligible folders found")
        if shown == 0: self.lbl_empty.setText("No eligible folders found"); self.lbl_empty.show()

    def _add_aep_row(self, it, idx):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setCellWidget(r, 0, self._make_cb(it.selected, self._aep_cb, idx))
        # Col 1: Full source path
        src_item = self._it(it.full_current_path)
        src_item.setForeground(QColor("#999")); src_item.setToolTip(it.full_current_path)
        self.tbl.setItem(r, 1, src_item)
        self.tbl.setItem(r, 2, self._make_arrow())
        # Col 3: Full new path
        ni = self._it(it.full_new_path); ni.setForeground(QColor("#4ade80")); ni.setToolTip(it.full_new_path)
        f=ni.font(); f.setBold(True); ni.setFont(f); self.tbl.setItem(r, 3, ni)
        self.tbl.setItem(r, 4, self._it(it.aep_file))
        si = self._it(it.file_size); si.setTextAlignment(Qt.AlignmentFlag.AlignRight|Qt.AlignmentFlag.AlignVCenter); self.tbl.setItem(r, 5, si)
        sti = self._it("Pending"); sti.setTextAlignment(Qt.AlignmentFlag.AlignCenter); sti.setForeground(QColor("#f59e0b")); self.tbl.setItem(r, 6, sti)

    def _aep_cb(self, idx, st):
        if idx < len(self.aep_items):
            self.aep_items[idx].selected = bool(st); self._upd_stats()

    def _stats_aep(self):
        sel = sum(1 for it in self.aep_items if it.selected)
        done = sum(1 for it in self.aep_items if it.status == "Done")
        self.lbl_stats.setText(f"{len(self.aep_items)} eligible | {sel} selected | {done} renamed")

    # ═══ CATEGORY SCAN ═══════════════════════════════════════════════════════
    def _scan_cat(self, src, dst):
        self._log(f"Scanning & categorizing: {src}")
        self.cat_items.clear(); self.tbl.setRowCount(0)
        self._cat_unmatched = 0
        self._cat_context_count = 0
        self._cat_llm_renamed = 0
        self._cat_method_counts = Counter()
        self._cat_dest_paths = {}  # dest_path_lower -> count for collision detection
        self._cat_fingerprints = {}  # file_fingerprint -> first folder_name for duplicate detection
        depth = self.spn_depth.value()

        if self.chk_llm.isChecked():
            if not self._ollama_ready:
                self._log("  WARNING: Ollama LLM not ready yet (still setting up or unavailable)")
                self._log("  Falling back to rule-based classification...")
                self.worker = ScanCategoryWorker(src, dst, scan_depth=depth)
            else:
                self._log("  Mode: LLM-powered (all folders processed through Ollama)")
                self.worker = ScanLLMWorker(src, dst, scan_depth=depth)
        else:
            self.worker = ScanCategoryWorker(src, dst, scan_depth=depth)

        self.worker.log.connect(self._log)
        self.worker.progress.connect(self._update_progress)
        self.worker.result_ready.connect(self._on_cat_result)
        self.worker.finished.connect(self._on_cat_scan_done)
        self.worker.start()

    def _deduplicate_dest_path(self, dest_path):
        """If dest_path already claimed by another item (or exists on disk),
        append (2), (3), etc. to the folder name to avoid collisions."""
        key = dest_path.lower()
        if key not in self._cat_dest_paths and not os.path.exists(dest_path):
            self._cat_dest_paths[key] = 1
            return dest_path

        parent = os.path.dirname(dest_path)
        base = os.path.basename(dest_path)
        n = self._cat_dest_paths.get(key, 1) + 1
        while True:
            new_name = f"{base} ({n})"
            new_path = os.path.join(parent, new_name)
            new_key = new_path.lower()
            if new_key not in self._cat_dest_paths and not os.path.exists(new_path):
                self._cat_dest_paths[key] = n
                self._cat_dest_paths[new_key] = 1
                return new_path
            n += 1

    def _on_cat_result(self, r):
        """Process a single categorization result live into the table."""
        dst = self.txt_dst.text()
        thresh = self.sld_conf.value()

        if not r['category']:
            self._cat_unmatched += 1
            # Show uncategorized folders in the table
            it = CategorizeItem(); it.folder_name = r['folder_name']; it.category = '[Uncategorized]'
            it.cleaned_name = r.get('cleaned_name', r['folder_name'])
            it.confidence = 0; it.full_source_path = r['folder_path']
            it.full_dest_path = ''
            it.method = ''; it.detail = 'No classification match'; it.topic = ''
            it.status = "Skip"; it.selected = False
            self.cat_items.append(it); self._add_cat_row(it, len(self.cat_items)-1)
            self._stats_cat()
            return

        it = CategorizeItem(); it.folder_name = r['folder_name']; it.category = r['category']
        it.cleaned_name = r.get('cleaned_name', r['folder_name'])
        it.confidence = r['confidence']; it.full_source_path = r['folder_path']

        # Use LLM-cleaned name for dest path if available (rename-on-move)
        llm_name = r.get('llm_name')
        if llm_name and llm_name != r['folder_name']:
            dest_folder_name = llm_name
        else:
            # No LLM name available — use smart naming (checks AEP/project files + subfolders)
            dest_folder_name = _smart_name(r['folder_name'], r.get('folder_path'), r.get('category'))
        raw_dest = os.path.join(dst, r['category'], dest_folder_name)
        it.full_dest_path = self._deduplicate_dest_path(raw_dest)

        it.method = r.get('method', ''); it.detail = r.get('detail', '')
        it.topic = r.get('topic', '') or ''
        it.status = "Pending"
        it.selected = it.confidence >= thresh

        if it.topic:
            self._cat_context_count += 1
        if llm_name and llm_name != r['folder_name']:
            self._cat_llm_renamed += 1
        self._cat_method_counts[it.method or 'unknown'] += 1

        # Duplicate detection
        fp = compute_file_fingerprint(r['folder_path'])
        if fp and fp in self._cat_fingerprints:
            it.detail = f"Possible duplicate of: {self._cat_fingerprints[fp]}"
        elif fp:
            self._cat_fingerprints[fp] = r['folder_name']

        self.cat_items.append(it); self._add_cat_row(it, len(self.cat_items)-1)
        self._stats_cat()

    def _on_cat_scan_done(self):
        """Finalize after category scan completes."""
        self._reset_scan_ui()
        self.tbl.setSortingEnabled(True)
        matched = len(self.cat_items)
        self.btn_apply.setEnabled(matched > 0)
        self.btn_preview.setEnabled(matched > 0)
        self.btn_export.setEnabled(len(self.cat_items) > 0)
        self._stats_cat()
        methods_str = ', '.join(f"{k}:{v}" for k, v in self._cat_method_counts.most_common())
        self._log(f"Categorization complete: {matched} matched, {self._cat_unmatched} uncategorized")
        if methods_str:
            self._log(f"  Methods used: {methods_str}")
        if self._cat_context_count:
            self._log(f"  Context overrides: {self._cat_context_count} (topic → asset type)")
        if self._cat_llm_renamed:
            self._log(f"  LLM renamed: {self._cat_llm_renamed} folders will be renamed on move")
        if matched == 0: self.lbl_empty.setText("No folders could be categorized"); self.lbl_empty.show()

    def _add_cat_row(self, it, idx):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setCellWidget(r, 0, self._make_cb(it.selected, self._cat_cb, idx))

        # Col 1: Source Path (full path, dimmed)
        src_item = self._it(it.full_source_path)
        src_item.setForeground(QColor("#999"))
        src_item.setToolTip(it.full_source_path)
        self.tbl.setItem(r, 1, src_item)

        # Col 2: Arrow
        self.tbl.setItem(r, 2, self._make_arrow())

        # Col 3: Destination Path (full path, colored by method)
        dest_item = self._it(it.full_dest_path if it.full_dest_path else '[No match]')
        dest_basename = os.path.basename(it.full_dest_path)
        is_llm_renamed = dest_basename != it.folder_name and it.method == 'llm'
        if is_llm_renamed:
            dest_item.setForeground(QColor("#f472b6"))  # pink = LLM renamed
            dest_item.setToolTip(f"LLM renamed \"{it.folder_name}\" \u2192 \"{dest_basename}\"")
        elif it.topic:
            dest_item.setForeground(QColor("#e879f9"))  # purple = context override
            dest_item.setToolTip(f"Topic \"{it.topic}\" overridden to \"{it.category}\"")
        else:
            dest_item.setForeground(QColor("#4ade80"))
            dest_item.setToolTip(it.full_dest_path)
        f = dest_item.font(); f.setBold(True); dest_item.setFont(f)
        self.tbl.setItem(r, 3, dest_item)

        # Col 4: Confidence
        clr = "#4ade80" if it.confidence >= 80 else "#f59e0b" if it.confidence >= 50 else "#ef4444"
        cfi = self._it(f"{it.confidence:.0f}%"); cfi.setForeground(QColor(clr)); cfi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        self.tbl.setItem(r, 4, cfi)

        # Col 5: Method with color coding
        METHOD_COLORS = {'extension': '#a78bfa', 'keyword': '#4ade80', 'fuzzy': '#facc15',
                         'metadata': '#38bdf8', 'metadata+keyword': '#2dd4bf',
                         'keyword_low': '#f97316', 'Manual': '#38bdf8',
                         'envato_api': '#f472b6', 'composition': '#a3e635',
                         'context': '#e879f9', 'llm': '#f472b6', 'learned': '#06b6d4'}
        method_label = it.method.replace('_', ' ').replace('+', '+') if it.method else ''
        mi = self._it(method_label); mi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        mi.setForeground(QColor(METHOD_COLORS.get(it.method, '#888')))
        if it.detail: mi.setToolTip(it.detail)
        self.tbl.setItem(r, 5, mi)

        # Col 6: Status
        sti = self._it("Pending"); sti.setTextAlignment(Qt.AlignmentFlag.AlignCenter); sti.setForeground(QColor("#f59e0b"))
        self.tbl.setItem(r, 6, sti)

        # Row background tinting by confidence
        if it.category == '[Uncategorized]':
            bg = QColor(239, 68, 68, 25)  # red tint
        elif 'Possible duplicate' in (it.detail or ''):
            bg = QColor(251, 191, 36, 25)  # amber tint
        elif it.confidence >= 80:
            bg = QColor(74, 222, 128, 15)  # green tint
        elif it.confidence >= 50:
            bg = QColor(245, 158, 11, 15)  # yellow tint
        else:
            bg = QColor(239, 68, 68, 15)  # red tint
        for col in range(self.tbl.columnCount()):
            item = self.tbl.item(r, col)
            if item:
                item.setBackground(bg)

    def _cat_cb(self, idx, st):
        if idx < len(self.cat_items):
            self.cat_items[idx].selected = bool(st); self._upd_stats()

    def _stats_cat(self):
        # Count duplicates and uncategorized
        dupes = sum(1 for it in self.cat_items if 'Possible duplicate' in (it.detail or ''))
        uncat = sum(1 for it in self.cat_items if it.category == '[Uncategorized]')
        sel = sum(1 for it in self.cat_items if it.selected)
        done = sum(1 for it in self.cat_items if it.status == "Done")
        cats = len(set(it.category for it in self.cat_items))
        self.lbl_stats.setText(f"{len(self.cat_items)} matched | {sel} selected | {cats} categories | {self._cat_unmatched} uncategorized | {done} moved")

    # ═══ SELECTION HELPERS ═══════════════════════════════════════════════════
    def _items(self):
        return self.cat_items if self.cmb_op.currentIndex() == self.OP_CAT else self.aep_items

    def _upd_stats(self):
        (self._stats_cat if self.cmb_op.currentIndex() == self.OP_CAT else self._stats_aep)()

    def _sel_all(self):
        for it in self._items(): it.selected = True
        for r in range(self.tbl.rowCount()):
            cb = self.tbl.cellWidget(r, 0)
            if cb:
                inner = cb.findChild(QCheckBox)
                if inner: inner.blockSignals(True); inner.setChecked(True); inner.blockSignals(False)
        self._upd_stats()

    def _sel_none(self):
        for it in self._items(): it.selected = False
        for r in range(self.tbl.rowCount()):
            cb = self.tbl.cellWidget(r, 0)
            if cb:
                inner = cb.findChild(QCheckBox)
                if inner: inner.blockSignals(True); inner.setChecked(False); inner.blockSignals(False)
        self._upd_stats()

    def _sel_inv(self):
        for idx, it in enumerate(self._items()):
            it.selected = not it.selected
            cb = self.tbl.cellWidget(idx, 0)
            if cb:
                inner = cb.findChild(QCheckBox)
                if inner: inner.blockSignals(True); inner.setChecked(it.selected); inner.blockSignals(False)
        self._upd_stats()

    def _check_selected(self):
        """Check (tick) only the highlighted/selected rows in the table."""
        self._set_highlighted_check(True)

    def _uncheck_selected(self):
        """Uncheck (untick) only the highlighted/selected rows in the table."""
        self._set_highlighted_check(False)

    def _set_highlighted_check(self, checked: bool):
        """Toggle checkboxes for all currently highlighted rows."""
        rows = sorted(set(idx.row() for idx in self.tbl.selectionModel().selectedRows()))
        if not rows:
            return
        items = self._items()
        for r in rows:
            if r < len(items):
                items[r].selected = checked
                cb = self.tbl.cellWidget(r, 0)
                if cb:
                    inner = cb.findChild(QCheckBox)
                    if inner:
                        inner.blockSignals(True)
                        inner.setChecked(checked)
                        inner.blockSignals(False)
        self._upd_stats()

    # ═══ APPLY ════════════════════════════════════════════════════════════════
    def _on_apply(self):
        (self._apply_cat if self.cmb_op.currentIndex()==self.OP_CAT else self._apply_aep)()

    def _apply_aep(self):
        work = [(i,it) for i,it in enumerate(self.aep_items) if it.selected and it.status=="Pending"]
        if not work: self._log("No items selected"); return
        # Backup snapshot
        snap = create_backup_snapshot(self.txt_src.text(), [it for _,it in work])
        if snap: self._log(f"Backup snapshot saved: {snap}")
        self.btn_apply.setEnabled(False); self.btn_scan.setEnabled(False); self.cmb_op.setEnabled(False)
        self._log(f"Renaming {len(work)} folders...")
        self.apply_worker = ApplyAepWorker(work, check_hashes=self.chk_hash.isChecked())
        self.apply_worker.log.connect(self._log)
        self.apply_worker.progress.connect(lambda c,t: self.lbl_prog.setText(f"Renaming {c}/{t}..."))
        self.apply_worker.item_done.connect(self._on_aep_item_done)
        self.apply_worker.finished.connect(self._on_aep_apply_done)
        self.apply_worker.start()

    def _on_aep_item_done(self, row_idx, status):
        self.aep_items[row_idx].status = status
        color = "#4ade80" if status == "Done" else "#ef4444"
        self._set_status(row_idx, status, color, 6)
        self.tbl.scrollToItem(self.tbl.item(row_idx, 1))

    def _on_aep_apply_done(self, ok, err, undo_ops):
        self.btn_scan.setEnabled(True); self.cmb_op.setEnabled(True); self._stats_aep()
        self._log(f"Complete: {ok} renamed, {err} errors"); self.lbl_prog.setText(f"Complete: {ok} renamed, {err} errors")
        if undo_ops:
            save_undo_log(undo_ops); self.undo_ops = undo_ops; self.btn_undo.setEnabled(True)
            append_csv_log(undo_ops)
            self._log(f"Undo log and CSV log saved")

    def _apply_cat(self):
        work = [(i,it) for i,it in enumerate(self.cat_items) if it.selected and it.status=="Pending"]
        if not work: self._log("No items selected"); return
        # Backup snapshot
        snap = create_backup_snapshot(self.txt_src.text(), [it for _,it in work])
        if snap: self._log(f"Backup snapshot saved: {snap}")
        self.btn_apply.setEnabled(False); self.btn_scan.setEnabled(False); self.cmb_op.setEnabled(False)
        self._log(f"Moving {len(work)} folders...")
        self.apply_worker = ApplyCatWorker(work, check_hashes=self.chk_hash.isChecked())
        self.apply_worker.log.connect(self._log)
        self.apply_worker.progress.connect(lambda c,t: self.lbl_prog.setText(f"Moving {c}/{t}..."))
        self.apply_worker.item_done.connect(self._on_cat_item_done)
        self.apply_worker.finished.connect(self._on_cat_apply_done)
        self.apply_worker.start()

    def _on_cat_item_done(self, row_idx, status):
        self.cat_items[row_idx].status = status
        color = "#4ade80" if status == "Done" else "#ef4444"
        self._set_status(row_idx, status, color, 6)
        self.tbl.scrollToItem(self.tbl.item(row_idx, 1))

    def _on_cat_apply_done(self, ok, err, undo_ops):
        self.btn_scan.setEnabled(True); self.cmb_op.setEnabled(True); self._stats_cat()
        self._log(f"Complete: {ok} moved, {err} errors"); self.lbl_prog.setText(f"Complete: {ok} moved, {err} errors")
        if undo_ops:
            save_undo_log(undo_ops); self.undo_ops = undo_ops; self.btn_undo.setEnabled(True)
            append_csv_log(undo_ops)
            self._log(f"Undo log and CSV log saved")



    # ═══ DRY-RUN / EXPORT PLAN ═══════════════════════════════════════════════
    def _export_plan(self):
        """Export the current classification plan as CSV (dry-run report)."""
        items = self.cat_items if self.cmb_op.currentIndex() == self.OP_CAT else self.aep_items
        if not items: self._log("No items to export"); return
        path, _ = QFileDialog.getSaveFileName(self, "Export Plan", "", "CSV Files (*.csv)")
        if not path: return
        try:
            with open(path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                if self.cmb_op.currentIndex() == self.OP_CAT:
                    w.writerow(["Selected", "Source Path", "Destination Path", "Category", "Confidence", "Method", "Detail", "Status"])
                    for it in items:
                        w.writerow([it.selected, it.full_source_path, it.full_dest_path,
                                    it.category, f"{it.confidence:.0f}", it.method, it.detail, it.status])
                else:
                    w.writerow(["Selected", "Source Path", "New Path", "AEP File", "Size", "Status"])
                    for it in items:
                        w.writerow([it.selected, it.full_current_path, it.full_new_path,
                                    it.aep_file, it.file_size, it.status])
            self._log(f"Plan exported to: {path}")
        except Exception as e:
            self._log(f"Export error: {e}")

    # ═══ EXPORT/IMPORT RULES ═════════════════════════════════════════════════
    def _export_rules(self):
        """Export custom categories + corrections as JSON."""
        path, _ = QFileDialog.getSaveFileName(self, "Export Rules", "fileorganizer_rules.json", "JSON Files (*.json)")
        if not path: return
        try:
            export_rules_bundle(path)
            corr_count = len(load_corrections())
            cat_count = len(load_custom_categories())
            self._log(f"Rules exported: {cat_count} custom categories, {corr_count} corrections -> {path}")
        except Exception as e:
            self._log(f"Export error: {e}")

    def _import_rules(self):
        """Import custom categories + corrections from JSON."""
        path, _ = QFileDialog.getOpenFileName(self, "Import Rules", "", "JSON Files (*.json)")
        if not path: return
        try:
            bundle = import_rules_bundle(path)
            cats = len(bundle.get('custom_categories', []))
            corrs = len(bundle.get('corrections', {}))
            self._log(f"Rules imported: {cats} custom categories, {corrs} corrections from {path}")
        except Exception as e:
            self._log(f"Import error: {e}")

    def _clear_cache(self):
        """Clear the classification cache."""
        n = cache_count()
        cache_clear()
        self._log(f"Cache cleared ({n} entries removed)")

# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    window = FileOrganizer()
    window.show()
    sys.exit(app.exec())
