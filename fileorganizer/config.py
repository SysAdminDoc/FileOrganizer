"""FileOrganizer — Configuration, paths, thresholds, themes, and protection."""
import os, sys, re, json, shutil, time
from datetime import datetime
from pathlib import Path

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()

# ── App Data Directory ────────────────────────────────────────────────────────
# All settings, caches, logs stored in %APPDATA%/FileOrganizer (never beside script)
_APP_DATA_DIR = os.path.join(os.environ.get('APPDATA', os.path.expanduser('~')),
                              'FileOrganizer')
os.makedirs(_APP_DATA_DIR, exist_ok=True)

# One-time migration: move legacy files from script dir into _APP_DATA_DIR
_MIGRATE_FILES = [
    'corrections.json', 'classification_cache.db', 'custom_categories.json',
    'envato_api_key.txt', 'ollama_settings.json', 'undo_log.json',
    'move_log.csv', 'crash.log',
]
for _mf in _MIGRATE_FILES:
    _old = os.path.join(_SCRIPT_DIR, _mf)
    _new = os.path.join(_APP_DATA_DIR, _mf)
    if os.path.exists(_old) and not os.path.exists(_new):
        try:
            shutil.move(_old, _new)
        except Exception:
            pass
del _mf, _old, _new

# ── Checkbox checkmark SVG ─────────────────────────────────────────────────────
# Qt6 doesn't support ::after pseudo-elements in QSS — write an SVG and reference
# it via image: url(...) on QCheckBox::indicator:checked instead.
_CHECK_SVG = os.path.join(_APP_DATA_DIR, 'check.svg')
_CHECK_SVG_URL = _CHECK_SVG.replace('\\', '/')
try:
    if not os.path.exists(_CHECK_SVG):
        with open(_CHECK_SVG, 'w') as _f:
            _f.write('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 12 12">'
                     '<path d="M2 6l3 3 5-5" stroke="#fff" stroke-width="2.5" fill="none"'
                     ' stroke-linecap="round" stroke-linejoin="round"/></svg>')
except OSError:
    _CHECK_SVG_URL = ''

# ── Confidence Thresholds ─────────────────────────────────────────────────────
CONF_HIGH   = 80   # green — high confidence
CONF_MEDIUM = 50   # yellow — medium confidence (below = red)
CONF_FUZZY_CAP = 80   # max confidence for fuzzy-match results


# ── Theme System ──────────────────────────────────────────────────────────────
# Each theme is a dict of color tokens → hex values. _build_theme_qss() renders
# them into a full QSS stylesheet. "Steam Dark" is the default palette.

def _build_theme_qss(t: dict) -> str:
    """Generate a full QSS stylesheet from a theme color token dict.

    Global utility classes available across the app (set via setProperty('class', ...)):
        QPushButton: 'primary' | 'apply' | 'toolbar' | 'danger'
        QLabel:      'heading' | 'subheading' | 'caption' | 'muted' | 'hint' | 'mono'
                     'badge-success' | 'badge-warning' | 'badge-danger' | 'badge-neutral' | 'badge-accent'
        QFrame:      'separator' | 'card' | 'card-elevated'
        QTextEdit:   'log'
    """
    return f"""
/* ── Base ────────────────────────────────────────────────────────────────── */
QMainWindow, QWidget {{
    background-color: {t['bg']}; color: {t['fg']};
    font-family: 'Segoe UI', 'SF Pro Display', system-ui, sans-serif; font-size: 13px;
}}
QWidget:disabled {{ color: {t['disabled']}; }}

/* ── Buttons ─────────────────────────────────────────────────────────────── */
QPushButton {{
    background-color: {t['btn_bg']}; color: {t['btn_fg']};
    border: 1px solid {t['border']}; padding: 7px 16px;
    border-radius: 5px; font-weight: 500; font-size: 12px;
}}
QPushButton:hover {{ background-color: {t['btn_hover']}; color: {t['fg']}; border-color: {t['border_hover']}; }}
QPushButton:pressed {{ background-color: {t['btn_pressed']}; }}
QPushButton:focus {{ border: 1px solid {t['accent']}; }}
QPushButton:disabled {{ background-color: {t['bg_alt']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}
QPushButton[class="primary"] {{
    background-color: {t['accent']}; color: #ffffff; border: 1px solid {t['accent']};
    font-weight: bold; font-size: 13px; padding: 8px 24px; border-radius: 5px;
}}
QPushButton[class="primary"]:hover {{ background-color: {t['accent_hover']}; border-color: {t['accent_hover']}; }}
QPushButton[class="primary"]:pressed {{ background-color: {t['accent_pressed']}; border-color: {t['accent_pressed']}; }}
QPushButton[class="primary"]:focus {{ border: 1px solid {t['fg_bright']}; }}
QPushButton[class="primary"]:disabled {{ background-color: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}
QPushButton[class="apply"] {{
    background-color: {t['green']}; color: #ffffff; border: 1px solid {t['green']};
    font-weight: bold; font-size: 13px; padding: 8px 24px; border-radius: 5px;
}}
QPushButton[class="apply"]:hover {{ background-color: {t['green_hover']}; border-color: {t['green_hover']}; }}
QPushButton[class="apply"]:pressed {{ background-color: {t['green_pressed']}; border-color: {t['green_pressed']}; }}
QPushButton[class="apply"]:focus {{ border: 1px solid {t['fg_bright']}; }}
QPushButton[class="apply"]:disabled {{ background-color: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}
QPushButton[class="toolbar"] {{
    background-color: transparent; color: {t['muted']};
    border: 1px solid transparent; padding: 5px 12px; font-size: 11px; border-radius: 4px;
}}
QPushButton[class="toolbar"]:hover {{ background-color: {t['btn_bg']}; color: {t['fg']}; border-color: {t['border']}; }}
QPushButton[class="toolbar"]:focus {{ border-color: {t['accent']}; }}
QPushButton[class="toolbar"]:disabled {{ color: {t['border']}; }}
QPushButton[class="danger"] {{
    background-color: {t['btn_bg']}; color: {t['danger']}; font-weight: bold;
    border: 1px solid {t['danger_border']}; border-radius: 5px; padding: 4px 16px;
}}
QPushButton[class="danger"]:hover {{ background-color: {t['danger_hover_bg']}; color: {t['danger_hover_fg']}; }}
QPushButton[class="danger"]:focus {{ border-color: {t['danger']}; }}
QPushButton[class="danger"]:disabled {{ background-color: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['border']}; }}
/* Cancel = same button, just text-color override (used for Scan/Cancel toggle) */
QPushButton[class="cancel"] {{
    color: {t['danger']}; font-weight: bold;
}}
QPushButton[class="cancel"]:hover {{
    background-color: {t['danger_hover_bg']}; color: {t['danger_hover_fg']};
    border-color: {t['danger_border']};
}}
/* Compact accented secondary button (small toolbar action) */
QPushButton[class="secondary"] {{
    font-size: 11px; padding: 2px 10px;
    background: {t['selection']}; color: {t['sidebar_btn_active_fg']};
    border: 1px solid {t['border']}; border-radius: 4px;
}}
QPushButton[class="secondary"]:hover {{ background: {t['btn_hover']}; }}
QPushButton[class="secondary"]:disabled {{ background: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}
/* Toggleable variant (used for view-mode switches like Grid / Map / Graph) */
QPushButton[class="toggle"] {{
    font-size: 11px; padding: 2px 8px;
    background: {t['selection']}; color: {t['sidebar_btn_active_fg']};
    border: 1px solid {t['border']}; border-radius: 4px;
}}
QPushButton[class="toggle"]:hover {{ background: {t['btn_hover']}; }}
QPushButton[class="toggle"]:checked {{ background: {t['sidebar_btn_active_fg']}; color: {t['sidebar_brand']}; }}
QPushButton[class="toggle"]:disabled {{ background: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}
/* Secondary button colored variants — for distinct meaning (success/accent) */
QPushButton[class="secondary-success"] {{
    font-size: 11px; padding: 2px 10px;
    background: {t['selection']}; color: {t['green']};
    border: 1px solid {t['border']}; border-radius: 4px;
}}
QPushButton[class="secondary-success"]:hover {{ background: {t['btn_hover']}; }}
QPushButton[class="secondary-success"]:disabled {{ background: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}
QPushButton[class="secondary-accent"] {{
    font-size: 11px; padding: 2px 8px;
    background: {t['selection']}; color: {t['accent_hover']};
    border: 1px solid {t['border']}; border-radius: 4px;
}}
QPushButton[class="secondary-accent"]:hover {{ background: {t['btn_hover']}; }}
QPushButton[class="secondary-accent"]:disabled {{ background: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}
/* Console log header buttons (flat ghost / monospace) */
QPushButton[class="log-toggle"] {{
    background: transparent; color: {t['muted']}; font-size: 11px;
    border: none; padding: 2px 4px; text-align: left;
    font-family: 'Consolas', 'Courier New', monospace;
}}
QPushButton[class="log-toggle"]:hover {{ color: {t['fg']}; }}
QPushButton[class="log-toggle"]:checked {{ color: {t['sidebar_btn_active_fg']}; }}
QPushButton[class="log-clear"] {{
    background: transparent; color: {t['muted']}; font-size: 11px;
    border: none; padding: 2px 6px;
}}
QPushButton[class="log-clear"]:hover {{ color: {t['danger']}; }}
/* Toggle variant with green semantics (used for Map view toggle) */
QPushButton[class="toggle-success"] {{
    font-size: 11px; padding: 2px 8px;
    background: {t['selection']}; color: {t['green']};
    border: 1px solid {t['border']}; border-radius: 4px;
}}
QPushButton[class="toggle-success"]:hover {{ background: {t['btn_hover']}; }}
QPushButton[class="toggle-success"]:checked {{ background: {t['green']}; color: {t['sidebar_brand']}; }}
QPushButton[class="toggle-success"]:disabled {{ background: {t['btn_bg']}; color: {t['disabled']}; border-color: {t['btn_bg']}; }}

/* ── Tool buttons ────────────────────────────────────────────────────────── */
QToolButton {{
    background: transparent; color: {t['muted']};
    border: 1px solid transparent; border-radius: 4px;
    padding: 4px 8px;
}}
QToolButton:hover {{ background: {t['btn_bg']}; color: {t['fg']}; border-color: {t['border']}; }}
QToolButton:pressed {{ background: {t['btn_hover']}; }}
QToolButton:checked {{ background: {t['selection']}; color: {t['sidebar_btn_active_fg']}; border-color: {t['border']}; }}
QToolButton:focus {{ border-color: {t['accent']}; }}
QToolButton:disabled {{ color: {t['disabled']}; }}

/* ── Inputs ──────────────────────────────────────────────────────────────── */
QLineEdit, QPlainTextEdit {{
    background-color: {t['input_bg']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: 5px;
    padding: 8px 12px; font-size: 13px; selection-background-color: {t['accent']}; selection-color: #ffffff;
}}
QLineEdit:hover, QPlainTextEdit:hover {{ border-color: {t['border_hover']}; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: {t['accent']}; }}
QLineEdit:read-only {{ color: {t['muted']}; background-color: {t['bg_alt']}; }}
QLineEdit:disabled, QPlainTextEdit:disabled {{ color: {t['disabled']}; background-color: {t['bg_alt']}; border-color: {t['btn_bg']}; }}

QComboBox {{
    background-color: {t['input_bg']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: 5px;
    padding: 7px 12px; font-size: 13px; min-height: 28px;
}}
QComboBox:hover {{ border-color: {t['border_hover']}; }}
QComboBox:focus {{ border-color: {t['accent']}; }}
QComboBox:disabled {{ color: {t['disabled']}; background-color: {t['bg_alt']}; border-color: {t['btn_bg']}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{
    image: none; border-left: 5px solid transparent;
    border-right: 5px solid transparent; border-top: 5px solid {t['muted']}; margin-right: 10px;
}}
QComboBox::down-arrow:hover {{ border-top-color: {t['fg']}; }}
QComboBox QAbstractItemView {{
    background-color: {t['input_bg']}; color: {t['fg']}; border: 1px solid {t['border']}; border-radius: 6px;
    selection-background-color: {t['accent']}; selection-color: #ffffff; outline: none; padding: 4px;
}}

QSpinBox, QDoubleSpinBox, QDateEdit, QTimeEdit, QDateTimeEdit {{
    background-color: {t['input_bg']}; color: {t['fg']};
    border: 1px solid {t['border']}; border-radius: 5px; padding: 4px 8px; font-size: 12px;
}}
QSpinBox:hover, QDoubleSpinBox:hover, QDateEdit:hover, QTimeEdit:hover, QDateTimeEdit:hover {{ border-color: {t['border_hover']}; }}
QSpinBox:focus, QDoubleSpinBox:focus, QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {{ border-color: {t['accent']}; }}
QSpinBox:disabled, QDoubleSpinBox:disabled, QDateEdit:disabled, QTimeEdit:disabled, QDateTimeEdit:disabled {{ color: {t['disabled']}; background-color: {t['bg_alt']}; }}

/* ── Tables / lists / trees ──────────────────────────────────────────────── */
QTableWidget, QTableView {{
    background-color: {t['bg']}; alternate-background-color: {t['bg_alt']};
    color: {t['fg']}; border: 1px solid {t['btn_bg']}; border-radius: 6px;
    gridline-color: transparent; font-size: 12px;
    selection-background-color: {t['selection']}; selection-color: {t['fg_bright']}; outline: none;
}}
QTableWidget::item, QTableView::item {{ padding: 6px 10px; border-bottom: 1px solid {t['btn_bg']}; }}
QTableWidget::item:selected, QTableView::item:selected {{ background-color: {t['selection']}; }}
QTableWidget::item:hover, QTableView::item:hover {{ background-color: {t['row_hover']}; }}
QHeaderView {{ background: {t['header_bg']}; }}
QHeaderView::section {{
    background-color: {t['header_bg']}; color: {t['muted']}; font-weight: 600; font-size: 11px;
    padding: 9px 12px; border: none; border-bottom: 2px solid {t['btn_bg']}; border-right: 1px solid {t['btn_bg']};
}}
QHeaderView::section:hover {{ color: {t['fg']}; }}
QHeaderView::section:first {{ padding-left: 16px; }}

QListWidget, QListView {{
    background-color: {t['input_bg']}; color: {t['fg']};
    border: 1px solid {t['btn_bg']}; border-radius: 5px; outline: none;
}}
QListWidget::item, QListView::item {{ padding: 7px 12px; border-radius: 3px; }}
QListWidget::item:selected, QListView::item:selected {{ background-color: {t['selection']}; color: {t['fg_bright']}; }}
QListWidget::item:hover, QListView::item:hover {{ background-color: {t['row_hover']}; }}
QListWidget::item:selected:active, QListView::item:selected:active {{ color: {t['sidebar_btn_active_fg']}; }}

QTreeWidget, QTreeView {{
    background-color: {t['input_bg']}; color: {t['fg']};
    border: 1px solid {t['btn_bg']}; border-radius: 5px; outline: none;
    alternate-background-color: {t['bg_alt']};
}}
QTreeWidget::item, QTreeView::item {{ padding: 4px 6px; border: none; }}
QTreeWidget::item:selected, QTreeView::item:selected {{ background: {t['selection']}; color: {t['fg_bright']}; }}
QTreeWidget::item:hover, QTreeView::item:hover {{ background: {t['row_hover']}; }}

/* ── Text edit / log panels ──────────────────────────────────────────────── */
QTextEdit {{
    background-color: {t['input_bg']}; color: {t['fg']};
    border: 1px solid {t['btn_bg']}; border-radius: 5px;
    font-size: 12px; padding: 8px; selection-background-color: {t['accent']}; selection-color: #ffffff;
}}
QTextEdit:focus {{ border-color: {t['accent']}; }}
QTextEdit[class="log"] {{
    background-color: {t['bg']}; color: {t['muted']};
    font-family: 'Consolas', 'Courier New', monospace; font-size: 10px;
    border: 1px solid {t['border']}; border-radius: 5px; padding: 8px;
}}

/* ── Scrollbars ──────────────────────────────────────────────────────────── */
QScrollBar:vertical {{ background: transparent; width: 10px; border: none; margin: 4px 0; }}
QScrollBar::handle:vertical {{ background: {t['border']}; border-radius: 5px; min-height: 30px; margin: 0 2px; }}
QScrollBar::handle:vertical:hover {{ background: {t['border_hover']}; }}
QScrollBar::handle:vertical:pressed {{ background: {t['muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; border: none; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; border: none; margin: 0 4px; }}
QScrollBar::handle:horizontal {{ background: {t['border']}; border-radius: 5px; min-width: 30px; margin: 2px 0; }}
QScrollBar::handle:horizontal:hover {{ background: {t['border_hover']}; }}
QScrollBar::handle:horizontal:pressed {{ background: {t['muted']}; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; border: none; }}
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: none; }}

/* ── Checkbox / radio ────────────────────────────────────────────────────── */
QCheckBox, QRadioButton {{ spacing: 8px; color: {t['fg']}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {t['disabled']}; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 18px; height: 18px; border: 2px solid {t['border']}; background: {t['input_bg']}; }}
QCheckBox::indicator {{ border-radius: 4px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:unchecked:hover, QRadioButton::indicator:unchecked:hover {{ border-color: {t['border_hover']}; }}
QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; image: url({_CHECK_SVG_URL}); }}
QRadioButton::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{ background: {t['bg_alt']}; border-color: {t['btn_bg']}; }}
QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{ background: {t['btn_bg']}; border-color: {t['btn_bg']}; }}
/* Accent-colored emphasized checkbox (used to highlight key options like LLM) */
QCheckBox[class="accent"] {{
    color: {t['sidebar_profile_fg']}; font-weight: bold; font-size: 12px;
    background: transparent;
}}

/* ── Slider ──────────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{ background: {t['btn_bg']}; height: 6px; border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {t['accent']}; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; }}
QSlider::handle:horizontal:hover {{ background: {t['accent_hover']}; }}
QSlider::handle:horizontal:pressed {{ background: {t['accent_pressed']}; }}
QSlider::groove:vertical {{ background: {t['btn_bg']}; width: 6px; border-radius: 3px; }}
QSlider::handle:vertical {{ background: {t['accent']}; width: 16px; height: 16px; margin: 0 -5px; border-radius: 8px; }}

/* ── Menus ───────────────────────────────────────────────────────────────── */
QMenuBar {{ background-color: {t['header_bg']}; color: {t['muted']}; border-bottom: 1px solid {t['btn_bg']}; padding: 2px 0; font-size: 12px; }}
QMenuBar::item {{ padding: 6px 14px; border-radius: 4px; }}
QMenuBar::item:selected {{ background-color: {t['btn_bg']}; color: {t['fg']}; }}
QMenu {{ background-color: {t['input_bg']}; color: {t['fg']}; border: 1px solid {t['border']}; border-radius: 6px; padding: 6px; }}
QMenu::item {{ padding: 8px 24px 8px 16px; border-radius: 4px; }}
QMenu::item:selected {{ background-color: {t['selection']}; color: {t['fg_bright']}; }}
QMenu::item:disabled {{ color: {t['disabled']}; }}
QMenu::separator {{ height: 1px; background: {t['btn_bg']}; margin: 4px 8px; }}

/* ── Group box ───────────────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {t['bg_alt']}; border: 1px solid {t['btn_bg']}; border-radius: 8px;
    margin-top: 14px; padding: 14px 12px 10px 12px;
    font-weight: 600; font-size: 11px; color: {t['muted']};
}}
QGroupBox::title {{
    subcontrol-origin: margin; subcontrol-position: top left;
    left: 12px; padding: 0 8px; color: {t['muted']};
    text-transform: uppercase; letter-spacing: 0.5px;
}}

/* ── Tooltip ─────────────────────────────────────────────────────────────── */
QToolTip {{
    background-color: {t['header_bg']}; color: {t['fg_bright']};
    border: 1px solid {t['border']}; border-radius: 6px;
    padding: 7px 11px; font-size: 12px;
}}

/* ── Progress ────────────────────────────────────────────────────────────── */
QProgressBar {{
    background-color: {t['btn_bg']}; border: none; border-radius: 4px;
    height: 8px; text-align: center; color: {t['fg']}; font-size: 11px;
}}
QProgressBar::chunk {{ background-color: {t['accent']}; border-radius: 4px; }}

/* ── Tabs ────────────────────────────────────────────────────────────────── */
QTabWidget::pane {{ border: 1px solid {t['border']}; background: {t['bg_alt']}; border-radius: 0 6px 6px 6px; top: -1px; }}
QTabBar::tab {{
    background: transparent; color: {t['muted']};
    padding: 8px 16px; border: 1px solid transparent; border-bottom: none;
    margin-right: 2px; font-size: 12px; border-radius: 6px 6px 0 0; min-width: 60px;
}}
QTabBar::tab:selected {{ background: {t['bg_alt']}; color: {t['sidebar_btn_active_fg']}; font-weight: 600; border-color: {t['border']}; }}
QTabBar::tab:hover:!selected {{ background: {t['btn_bg']}; color: {t['fg']}; }}
QTabBar::tab:disabled {{ color: {t['disabled']}; }}

/* ── Splitter ────────────────────────────────────────────────────────────── */
QSplitter::handle {{ background: {t['btn_bg']}; }}
QSplitter::handle:hover {{ background: {t['border']}; }}
QSplitter::handle:horizontal {{ width: 1px; }}
QSplitter::handle:vertical {{ height: 1px; }}

/* ── Status bar ──────────────────────────────────────────────────────────── */
QStatusBar {{
    background: {t['header_bg']}; color: {t['muted']};
    border-top: 1px solid {t['btn_bg']}; padding: 4px 12px; font-size: 11px;
}}
QStatusBar::item {{ border: none; }}
QStatusBar QLabel {{ color: {t['muted']}; }}

/* ── Dialog ──────────────────────────────────────────────────────────────── */
QDialog {{ background: {t['bg']}; }}
QMessageBox {{ background: {t['bg']}; }}
QMessageBox QLabel {{ color: {t['fg']}; font-size: 13px; }}

/* ── Utility classes ─────────────────────────────────────────────────────── */
QFrame[class="separator"] {{ background-color: {t['border']}; border: none; max-height: 1px; min-height: 1px; }}
QFrame[class="separator-vertical"] {{ background-color: {t['btn_bg']}; border: none; max-width: 1px; min-width: 1px; }}
QFrame[class="separator-strong"] {{ background-color: {t['btn_bg']}; border: none; max-height: 1px; min-height: 1px; }}
QFrame[class="card"] {{
    background-color: {t['bg_alt']}; border: 1px solid {t['btn_bg']};
    border-radius: 8px; padding: 14px;
}}
QFrame[class="card-elevated"] {{
    background-color: {t['bg_alt']}; border: 1px solid {t['border']};
    border-radius: 10px; padding: 16px;
}}

/* ── Typography utilities ────────────────────────────────────────────────── */
QLabel[class="heading"] {{
    color: {t['fg_bright']}; font-size: 16px; font-weight: 600; padding: 0;
}}
QLabel[class="subheading"] {{
    color: {t['fg']}; font-size: 13px; font-weight: 600; padding: 0;
}}
QLabel[class="caption"] {{
    color: {t['muted']}; font-size: 10px; font-weight: 600;
    letter-spacing: 0.6px; text-transform: uppercase;
}}
QLabel[class="form-label"] {{
    color: {t['muted']}; font-weight: 700; font-size: 10px;
    letter-spacing: 1px; background: transparent;
}}
QLabel[class="option-label"] {{
    color: {t['sidebar_btn_active_fg']}; font-weight: bold; font-size: 11px;
    background: transparent;
}}
QLabel[class="muted"] {{ color: {t['muted']}; }}
QLabel[class="hint"] {{ color: {t['muted']}; font-size: 11px; font-style: italic; }}
QLabel[class="meta"] {{ color: {t['muted']}; font-size: 11px; }}
QLabel[class="empty-state"] {{
    color: {t['muted']}; font-size: 13px; font-weight: 500; padding: 40px;
}}
QLabel[class="stats"] {{
    color: {t['muted']}; font-size: 12px; padding: 4px 0;
}}
QLabel[class="summary"] {{
    color: {t['sidebar_btn_active_fg']}; font-size: 12px; font-weight: 600;
}}
QLabel[class="toast"] {{
    background: {t['selection']}; color: {t['fg']};
    font-size: 13px; font-weight: bold;
    padding: 10px 20px; border-radius: 8px;
    border: 1px solid {t['border']};
}}
QLabel[class="meta-mono"] {{
    color: {t['muted']}; font-size: 11px; font-family: 'Consolas', 'Courier New', monospace;
}}
QLabel[class="mono"] {{
    color: {t['muted']}; font-family: 'Consolas', 'Courier New', monospace; font-size: 11px;
}}
QLabel[class="section-title"] {{
    color: {t['sidebar_btn_active_fg']}; font-size: 13px; font-weight: bold;
}}
QLabel[class="phase-label"] {{
    color: {t['sidebar_btn_active_fg']}; font-size: 12px; font-weight: bold; letter-spacing: 0.5px;
}}
QLabel[class="brand-title"] {{
    color: {t['fg_bright']}; font-size: 15px; font-weight: 700; letter-spacing: -0.5px;
    background: transparent;
}}
QLabel[class="brand-version"] {{
    color: {t['muted']}; font-size: 10px; font-weight: 600; background: transparent;
}}
QLabel[class="badge-success"] {{
    background: {t['green']}; color: #ffffff;
    padding: 2px 9px; border-radius: 9px; font-size: 10px; font-weight: 600;
}}
QLabel[class="badge-danger"] {{
    background: {t['danger']}; color: #ffffff;
    padding: 2px 9px; border-radius: 9px; font-size: 10px; font-weight: 600;
}}
QLabel[class="badge-warning"] {{
    background: #c79324; color: #ffffff;
    padding: 2px 9px; border-radius: 9px; font-size: 10px; font-weight: 600;
}}
QLabel[class="badge-accent"] {{
    background: {t['accent']}; color: #ffffff;
    padding: 2px 9px; border-radius: 9px; font-size: 10px; font-weight: 600;
}}
QLabel[class="badge-neutral"] {{
    background: {t['btn_bg']}; color: {t['muted']};
    padding: 2px 9px; border-radius: 9px; font-size: 10px; font-weight: 600;
}}

/* ── Semantic status labels ──────────────────────────────────────────────── */
QLabel[class="status-success"] {{ color: {t['green']};   font-size: 11px; font-weight: 600; }}
QLabel[class="status-warning"] {{ color: {t['warning']}; font-size: 11px; font-weight: 600; }}
QLabel[class="status-error"]   {{ color: {t['danger']};  font-size: 11px; font-weight: 600; }}

/* ── Sidebar navigation ──────────────────────────────────────────────────── */
QPushButton[class="sidebar-nav"] {{
    background: transparent; color: {t['sidebar_btn']}; border: none;
    border-left: 3px solid transparent; padding: 10px 14px;
    font-size: 12px; font-weight: 500; text-align: left;
}}
QPushButton[class="sidebar-nav"]:hover {{
    background: {t['sidebar_btn_hover_bg']}; color: {t['fg']};
    border-left: 3px solid {t['sidebar_btn_hover_border']};
}}
QPushButton[class="sidebar-nav"]:checked {{
    background: {t['sidebar_btn_active_bg']}; color: {t['sidebar_btn_active_fg']};
    border-left: 3px solid {t['sidebar_btn_active_border']}; font-weight: 600;
}}
QLabel[class="sidebar-section"] {{
    color: {t['sidebar_section']}; font-size: 10px; font-weight: 700;
    letter-spacing: 1.5px; padding: 12px 16px 4px 16px; background: transparent;
}}
/* Sidebar surface bands (header + footer rows that hold brand / status) */
QWidget[class="sidebar-band-top"] {{
    background: {t['sidebar_brand']};
    border-bottom: 1px solid {t['sidebar_border']};
}}
QWidget[class="sidebar-band-bottom"] {{
    background: {t['sidebar_brand']};
    border-top: 1px solid {t['sidebar_border']};
}}
/* Sidebar profile combo */
QComboBox[class="sidebar-profile"] {{
    background: {t['sidebar_profile_bg']}; color: {t['sidebar_profile_fg']};
    border: 1px solid {t['sidebar_profile_border']};
    border-radius: 4px; padding: 6px 10px; font-size: 11px; font-weight: bold;
}}
QComboBox[class="sidebar-profile"]:hover {{ border-color: {t['sidebar_profile_fg']}; }}
QComboBox[class="sidebar-profile"]::drop-down {{ border: none; }}
QComboBox[class="sidebar-profile"] QAbstractItemView {{
    background: {t['sidebar_profile_bg']}; color: {t['fg']};
    selection-background-color: {t['selection']};
    border: 1px solid {t['sidebar_profile_border']};
}}
/* Compact accent-colored filter combo (used for file-type / face filters) */
QComboBox[class="combo-accent"] {{
    background: {t['input_bg']}; color: {t['accent_hover']};
    border: 1px solid {t['border']}; border-radius: 3px;
    padding: 2px 6px; font-size: 11px; font-weight: bold;
}}
QComboBox[class="combo-accent"]:hover {{ border-color: {t['accent_hover']}; }}
QComboBox[class="combo-accent"]::drop-down {{ border: none; }}
QComboBox[class="combo-accent"] QAbstractItemView {{
    background: {t['input_bg']}; color: {t['fg']};
    selection-background-color: {t['selection']}; border: 1px solid {t['border']};
}}
/* Green-tinted compact filter combo */
QComboBox[class="combo-success"] {{
    background: {t['selection']}; color: {t['green']};
    border: 1px solid {t['border']}; border-radius: 4px;
    padding: 2px 6px; font-size: 11px;
}}
/* Dashboard panel (overview stats container above the results table) */
QWidget[class="dashboard-panel"] {{
    background: {t['header_bg']};
    border-radius: 6px;
}}
"""

# ── Theme Palettes ───────────────────────────────────────────────────────────
THEME_STEAM_DARK = {
    'name': 'Steam Dark', 'sidebar_bg': '#080e16', 'sidebar_brand': '#060b12',
    'sidebar_border': '#1b2838', 'sidebar_section': '#3a4f65',
    'sidebar_btn': '#7a8a9a', 'sidebar_btn_hover_bg': '#0d1926',
    'sidebar_btn_hover_border': '#1e3a5c', 'sidebar_btn_active_bg': '#0f1f30',
    'sidebar_btn_active_fg': '#4fc3f7', 'sidebar_btn_active_border': '#1a6bc4',
    'sidebar_profile_bg': '#0d1520', 'sidebar_profile_fg': '#a78bfa',
    'sidebar_profile_border': '#1e3050',
    'bg': '#0f1923', 'bg_alt': '#121e2b', 'fg': '#c5cdd8', 'fg_bright': '#e0e6ec',
    'btn_bg': '#1b2838', 'btn_fg': '#8f98a0', 'btn_hover': '#1e3a5f',
    'btn_pressed': '#254a73', 'border': '#2a3f5f', 'border_hover': '#3d6a9e',
    'input_bg': '#141d26', 'header_bg': '#0a1219',
    'accent': '#1a6bc4', 'accent_hover': '#2080e0', 'accent_pressed': '#1560b0',
    'green': '#1b8553', 'green_hover': '#22a366', 'green_pressed': '#167045',
    'selection': '#1a3a5c', 'row_hover': '#152535',
    'muted': '#6b7785', 'disabled': '#3a4654',
    'danger': '#ef4444', 'danger_border': '#5c2e2e',
    'danger_hover_bg': '#4a1a1a', 'danger_hover_fg': '#fca5a5',
    'warning': '#f59e0b',
}

THEME_CATPPUCCIN_MOCHA = {
    'name': 'Catppuccin Mocha', 'sidebar_bg': '#11111b', 'sidebar_brand': '#0e0e18',
    'sidebar_border': '#313244', 'sidebar_section': '#585b70',
    'sidebar_btn': '#a6adc8', 'sidebar_btn_hover_bg': '#181825',
    'sidebar_btn_hover_border': '#45475a', 'sidebar_btn_active_bg': '#1e1e2e',
    'sidebar_btn_active_fg': '#89b4fa', 'sidebar_btn_active_border': '#89b4fa',
    'sidebar_profile_bg': '#181825', 'sidebar_profile_fg': '#cba6f7',
    'sidebar_profile_border': '#45475a',
    'bg': '#1e1e2e', 'bg_alt': '#181825', 'fg': '#cdd6f4', 'fg_bright': '#e4e8f4',
    'btn_bg': '#313244', 'btn_fg': '#a6adc8', 'btn_hover': '#45475a',
    'btn_pressed': '#585b70', 'border': '#45475a', 'border_hover': '#585b70',
    'input_bg': '#181825', 'header_bg': '#11111b',
    'accent': '#89b4fa', 'accent_hover': '#a6c8ff', 'accent_pressed': '#6d9de8',
    'green': '#a6e3a1', 'green_hover': '#b8f0b4', 'green_pressed': '#8ad085',
    'selection': '#313244', 'row_hover': '#252536',
    'muted': '#6c7086', 'disabled': '#45475a',
    'danger': '#f38ba8', 'danger_border': '#5c2838',
    'danger_hover_bg': '#3a1520', 'danger_hover_fg': '#ffb3c8',
    'warning': '#fab387',
}

THEME_OLED_BLACK = {
    'name': 'OLED Black', 'sidebar_bg': '#000000', 'sidebar_brand': '#000000',
    'sidebar_border': '#1a1a1a', 'sidebar_section': '#444444',
    'sidebar_btn': '#888888', 'sidebar_btn_hover_bg': '#0a0a0a',
    'sidebar_btn_hover_border': '#333333', 'sidebar_btn_active_bg': '#111111',
    'sidebar_btn_active_fg': '#00d4ff', 'sidebar_btn_active_border': '#0099cc',
    'sidebar_profile_bg': '#080808', 'sidebar_profile_fg': '#b388ff',
    'sidebar_profile_border': '#222222',
    'bg': '#000000', 'bg_alt': '#0a0a0a', 'fg': '#d0d0d0', 'fg_bright': '#f0f0f0',
    'btn_bg': '#1a1a1a', 'btn_fg': '#909090', 'btn_hover': '#252525',
    'btn_pressed': '#333333', 'border': '#2a2a2a', 'border_hover': '#444444',
    'input_bg': '#0d0d0d', 'header_bg': '#000000',
    'accent': '#0099cc', 'accent_hover': '#00bbee', 'accent_pressed': '#007799',
    'green': '#00aa55', 'green_hover': '#00cc66', 'green_pressed': '#008844',
    'selection': '#1a1a2e', 'row_hover': '#111118',
    'muted': '#666666', 'disabled': '#333333',
    'danger': '#ff4444', 'danger_border': '#5c2020',
    'danger_hover_bg': '#3a0f0f', 'danger_hover_fg': '#ff9090',
    'warning': '#ffaa00',
}

THEME_GITHUB_DARK = {
    'name': 'GitHub Dark', 'sidebar_bg': '#0d1117', 'sidebar_brand': '#090c10',
    'sidebar_border': '#21262d', 'sidebar_section': '#484f58',
    'sidebar_btn': '#8b949e', 'sidebar_btn_hover_bg': '#161b22',
    'sidebar_btn_hover_border': '#30363d', 'sidebar_btn_active_bg': '#1a2030',
    'sidebar_btn_active_fg': '#58a6ff', 'sidebar_btn_active_border': '#1f6feb',
    'sidebar_profile_bg': '#0d1117', 'sidebar_profile_fg': '#d2a8ff',
    'sidebar_profile_border': '#30363d',
    'bg': '#0d1117', 'bg_alt': '#161b22', 'fg': '#c9d1d9', 'fg_bright': '#e6edf3',
    'btn_bg': '#21262d', 'btn_fg': '#8b949e', 'btn_hover': '#30363d',
    'btn_pressed': '#3d444d', 'border': '#30363d', 'border_hover': '#484f58',
    'input_bg': '#0d1117', 'header_bg': '#010409',
    'accent': '#1f6feb', 'accent_hover': '#388bfd', 'accent_pressed': '#1a5cc8',
    'green': '#238636', 'green_hover': '#2ea043', 'green_pressed': '#1a7f37',
    'selection': '#1a2332', 'row_hover': '#131920',
    'muted': '#484f58', 'disabled': '#30363d',
    'danger': '#f85149', 'danger_border': '#5c2020',
    'danger_hover_bg': '#3d1a1a', 'danger_hover_fg': '#ffadad',
    'warning': '#d29922',
}

THEME_NORD = {
    'name': 'Nord', 'sidebar_bg': '#242933', 'sidebar_brand': '#1e222b',
    'sidebar_border': '#3b4252', 'sidebar_section': '#616e88',
    'sidebar_btn': '#b0bec5', 'sidebar_btn_hover_bg': '#2e3440',
    'sidebar_btn_hover_border': '#434c5e', 'sidebar_btn_active_bg': '#3b4252',
    'sidebar_btn_active_fg': '#88c0d0', 'sidebar_btn_active_border': '#5e81ac',
    'sidebar_profile_bg': '#2e3440', 'sidebar_profile_fg': '#b48ead',
    'sidebar_profile_border': '#434c5e',
    'bg': '#2e3440', 'bg_alt': '#3b4252', 'fg': '#d8dee9', 'fg_bright': '#eceff4',
    'btn_bg': '#3b4252', 'btn_fg': '#b0bec5', 'btn_hover': '#434c5e',
    'btn_pressed': '#4c566a', 'border': '#434c5e', 'border_hover': '#4c566a',
    'input_bg': '#2e3440', 'header_bg': '#242933',
    'accent': '#5e81ac', 'accent_hover': '#81a1c1', 'accent_pressed': '#4c6d96',
    'green': '#a3be8c', 'green_hover': '#b4d09c', 'green_pressed': '#8aab73',
    'selection': '#3b4252', 'row_hover': '#353c4a',
    'muted': '#616e88', 'disabled': '#4c566a',
    'danger': '#bf616a', 'danger_border': '#5c3034',
    'danger_hover_bg': '#3a2025', 'danger_hover_fg': '#d09098',
    'warning': '#ebcb8b',
}

THEME_DRACULA = {
    'name': 'Dracula', 'sidebar_bg': '#1e1f29', 'sidebar_brand': '#191a23',
    'sidebar_border': '#44475a', 'sidebar_section': '#6272a4',
    'sidebar_btn': '#b0b8d1', 'sidebar_btn_hover_bg': '#282a36',
    'sidebar_btn_hover_border': '#44475a', 'sidebar_btn_active_bg': '#2c2e3e',
    'sidebar_btn_active_fg': '#bd93f9', 'sidebar_btn_active_border': '#bd93f9',
    'sidebar_profile_bg': '#282a36', 'sidebar_profile_fg': '#ff79c6',
    'sidebar_profile_border': '#44475a',
    'bg': '#282a36', 'bg_alt': '#2c2e3e', 'fg': '#f8f8f2', 'fg_bright': '#ffffff',
    'btn_bg': '#44475a', 'btn_fg': '#b0b8d1', 'btn_hover': '#515470',
    'btn_pressed': '#5e6180', 'border': '#44475a', 'border_hover': '#6272a4',
    'input_bg': '#21222c', 'header_bg': '#191a23',
    'accent': '#bd93f9', 'accent_hover': '#d0aaff', 'accent_pressed': '#a77de0',
    'green': '#50fa7b', 'green_hover': '#70ff95', 'green_pressed': '#38d960',
    'selection': '#383a4c', 'row_hover': '#30323f',
    'muted': '#6272a4', 'disabled': '#44475a',
    'danger': '#ff5555', 'danger_border': '#6b2525',
    'danger_hover_bg': '#4a1515', 'danger_hover_fg': '#ff9090',
    'warning': '#ffb86c',
}

# Registry: name → palette dict
THEMES = {
    'Steam Dark':        THEME_STEAM_DARK,
    'Catppuccin Mocha':  THEME_CATPPUCCIN_MOCHA,
    'OLED Black':        THEME_OLED_BLACK,
    'GitHub Dark':       THEME_GITHUB_DARK,
    'Nord':              THEME_NORD,
    'Dracula':           THEME_DRACULA,
}

_THEME_SETTINGS_FILE = os.path.join(_APP_DATA_DIR, 'theme.json')
_cached_theme_name: str | None = None

def load_theme_name() -> str:
    global _cached_theme_name
    if _cached_theme_name is not None:
        return _cached_theme_name
    try:
        with open(_THEME_SETTINGS_FILE, 'r') as f:
            _cached_theme_name = json.load(f).get('theme', 'Steam Dark')
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _cached_theme_name = 'Steam Dark'
    return _cached_theme_name

def save_theme_name(name: str):
    global _cached_theme_name
    _cached_theme_name = name
    try:
        with open(_THEME_SETTINGS_FILE, 'w') as f:
            json.dump({'theme': name}, f)
    except OSError:
        pass

def get_active_theme() -> dict:
    return THEMES.get(load_theme_name(), THEME_STEAM_DARK)

def get_active_stylesheet() -> str:
    return _build_theme_qss(THEMES.get(load_theme_name(), THEME_STEAM_DARK))

# ── Protected Paths ──────────────────────────────────────────────────────────
# System folders and important files that should NEVER be moved/deleted/renamed.

_PROTECTED_PATHS_FILE = os.path.join(_APP_DATA_DIR, 'protected_paths.json')
_cached_protected_paths: dict | None = None

def _default_protected_paths() -> list:
    """Platform-aware default protected system paths."""
    paths = []
    if sys.platform == 'win32':
        win = os.environ.get('SystemRoot', r'C:\Windows')
        paths += [
            win,
            os.path.join(os.environ.get('SystemDrive', 'C:'), os.sep, 'Program Files'),
            os.path.join(os.environ.get('SystemDrive', 'C:'), os.sep, 'Program Files (x86)'),
            os.path.join(os.environ.get('SystemDrive', 'C:'), os.sep, 'ProgramData'),
            os.path.join(os.environ.get('USERPROFILE', ''), 'AppData'),
            os.path.join(os.environ.get('USERPROFILE', ''), 'NTUSER.DAT'),
            os.environ.get('SystemRoot', r'C:\Windows') + r'\System32',
            os.environ.get('SystemRoot', r'C:\Windows') + r'\SysWOW64',
            '$RECYCLE.BIN', 'System Volume Information', 'Recovery',
            'pagefile.sys', 'hiberfil.sys', 'swapfile.sys',
            'desktop.ini', 'thumbs.db', 'ntldr', 'bootmgr',
        ]
    else:
        paths += [
            '/bin', '/sbin', '/usr', '/lib', '/lib64', '/boot', '/dev',
            '/proc', '/sys', '/etc', '/var/run', '/var/lock',
        ]
    # Universal
    paths += [
        '.git', '.svn', '.hg', '__pycache__', 'node_modules',
        '.env', '.ssh', '.gnupg', '.aws', '.kube',
    ]
    return paths

def load_protected_paths() -> dict:
    """Returns {'system': [...], 'custom': [...], 'enabled': bool}."""
    global _cached_protected_paths
    if _cached_protected_paths is not None:
        return _cached_protected_paths
    system = _default_protected_paths()
    try:
        with open(_PROTECTED_PATHS_FILE, 'r') as f:
            data = json.load(f)
        _cached_protected_paths = {
            'system': system,
            'custom': data.get('custom', []),
            'enabled': data.get('enabled', True),
        }
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        _cached_protected_paths = {'system': system, 'custom': [], 'enabled': True}
    return _cached_protected_paths

def save_protected_paths(custom: list, enabled: bool = True):
    global _cached_protected_paths
    _cached_protected_paths = {
        'system': _default_protected_paths(),
        'custom': custom,
        'enabled': enabled,
    }
    try:
        with open(_PROTECTED_PATHS_FILE, 'w') as f:
            json.dump({'custom': custom, 'enabled': enabled}, f, indent=2)
    except OSError:
        pass

def is_protected(path: str) -> bool:
    """Check if a path (file or folder) is protected from operations.
    Matches by exact path, basename, or if the path is inside a protected directory."""
    prot = load_protected_paths()
    if not prot['enabled']:
        return False
    norm = os.path.normcase(os.path.normpath(path))
    basename = os.path.basename(norm)
    all_protected = prot['system'] + prot['custom']
    for p in all_protected:
        p_norm = os.path.normcase(os.path.normpath(p))
        # Exact match
        if norm == p_norm:
            return True
        # Basename match (for entries like 'desktop.ini', '.git')
        if os.sep not in p and '/' not in p and '\\' not in p:
            if basename == os.path.normcase(p):
                return True
        # Path-is-inside check
        elif norm.startswith(p_norm + os.sep) or norm == p_norm:
            return True
    return False


# ── File path constants ────────────────────────────────────────────────────────
# ── Undo / operation log ──────────────────────────────────────────────────────
_UNDO_LOG_FILE = os.path.join(_APP_DATA_DIR, 'undo_log.json')
_UNDO_STACK_FILE = os.path.join(_APP_DATA_DIR, 'undo_stack.json')
_CSV_LOG_FILE = os.path.join(_APP_DATA_DIR, 'move_log.csv')
_LAST_CONFIG_FILE = os.path.join(_APP_DATA_DIR, 'last_scan_config.json')
_WATCH_HISTORY_FILE = os.path.join(_APP_DATA_DIR, 'watch_history.json')
_WATCH_HISTORY_MAX = 500

def append_watch_event(event: dict):
    """Append an event to the watch history log. Each event is a dict with
    keys like: timestamp, folder, action, files, details."""
    event.setdefault('timestamp', datetime.now().isoformat())
    try:
        history = load_watch_history()
    except Exception:
        history = []
    history.append(event)
    if len(history) > _WATCH_HISTORY_MAX:
        history = history[-_WATCH_HISTORY_MAX:]
    try:
        with open(_WATCH_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=1)
    except OSError:
        pass

def load_watch_history() -> list:
    try:
        with open(_WATCH_HISTORY_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []

def clear_watch_history():
    try:
        os.remove(_WATCH_HISTORY_FILE)
    except OSError:
        pass
_PROFILES_DIR = os.path.join(_APP_DATA_DIR, 'profiles')
os.makedirs(_PROFILES_DIR, exist_ok=True)

# ── Category Presets ─────────────────────────────────────────────────────────
_PRESETS_DIR = os.path.join(_APP_DATA_DIR, 'category_presets')
os.makedirs(_PRESETS_DIR, exist_ok=True)

_CUSTOM_CATS_FILE = os.path.join(_APP_DATA_DIR, 'custom_categories.json')
_FACE_DB_FILE = os.path.join(_APP_DATA_DIR, 'face_db.json')

_PC_SCAN_CACHE_DB = os.path.join(_APP_DATA_DIR, 'scan_cache.db')

# ── Design Workflow Settings ──────────────────────────────────────────────────
_DESIGN_SETTINGS_FILE = os.path.join(_APP_DATA_DIR, 'design_settings.json')

_DESIGN_DEFAULTS = {
    'primary_dest':        r'I:\Organized',
    'overflow_dest':       r'G:\\',
    'overflow_threshold_gb': 50,     # Switch to overflow when primary has < N GB free
    'extract_archives':    True,     # Unpack ZIP/RAR/7z before organizing
    'catalog_lookup':      True,     # Use DeepSeek to identify marketplace items
    'dynamic_categories':  True,     # Allow AI to propose new categories
    'confirm_duplicates':  True,     # Hash-verify before marking as duplicate
    'delete_archives_after_extract': False,  # Keep original archives after extraction
}

def load_design_settings() -> dict:
    try:
        with open(_DESIGN_SETTINGS_FILE, 'r', encoding='utf-8') as f:
            s = json.load(f)
        return {**_DESIGN_DEFAULTS, **s}
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return dict(_DESIGN_DEFAULTS)

def save_design_settings(settings: dict):
    try:
        with open(_DESIGN_SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=2)
    except OSError:
        pass

def get_dest_path(item_size_bytes: int = 0) -> str:
    """Return primary destination path, falling back to overflow when low on space."""
    s = load_design_settings()
    primary = s.get('primary_dest', r'I:\Organized')
    overflow = s.get('overflow_dest', r'G:\\')
    threshold_bytes = int(s.get('overflow_threshold_gb', 50)) * 1_073_741_824
    try:
        import shutil as _shutil
        free = _shutil.disk_usage(primary).free if os.path.exists(os.path.splitdrive(primary)[0] + '\\') else 0
        if free - item_size_bytes < threshold_bytes:
            return overflow
    except Exception:
        pass
    return primary
