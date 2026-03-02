#!/usr/bin/env python3
"""FileOrganizer v4.0 - Context-Aware Classification Engine"""

import sys, os, subprocess, re, shutil, json, csv, hashlib, gzip
from collections import Counter
import xml.etree.ElementTree as ET

def _bootstrap():
    """Auto-install dependencies before any imports."""
    if sys.version_info < (3, 8):
        print("Python 3.8+ required"); sys.exit(1)
    required = ['PyQt6']
    optional = ['rapidfuzz', 'psd-tools']
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

import traceback, ctypes
from datetime import datetime
from pathlib import Path
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QTableWidget, QTableWidgetItem,
    QCheckBox, QTextEdit, QHeaderView, QFileDialog, QAbstractItemView,
    QSlider, QMenu, QTreeWidget, QTreeWidgetItem, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QInputDialog, QSplitter, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QMimeData, QUrl
from PyQt6.QtGui import QColor, QDragEnterEvent, QDropEvent, QAction

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__)) if '__file__' in dir() else os.getcwd()

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
    background-color: #1a1a2e;
    color: #e0e0e0;
    font-family: 'Segoe UI', sans-serif;
}
QPushButton {
    background-color: #0078D4;
    color: white;
    border: none;
    padding: 8px 18px;
    border-radius: 5px;
    font-weight: bold;
    font-size: 12px;
}
QPushButton:hover { background-color: #1a8fe0; }
QPushButton:pressed { background-color: #006abc; }
QPushButton:disabled { background-color: #333; color: #666; }
QPushButton[class="secondary"] {
    background-color: #2a2a40;
    color: #ccc;
    font-weight: normal;
}
QPushButton[class="secondary"]:hover { background-color: #353550; }
QPushButton[class="apply"] {
    background-color: #16a34a;
    font-size: 13px;
    padding: 10px 24px;
}
QPushButton[class="apply"]:hover { background-color: #22c55e; }
QPushButton[class="apply"]:disabled { background-color: #333; color: #666; }
QLineEdit {
    background-color: #252536;
    color: #e0e0e0;
    border: 1px solid #3f3f56;
    border-radius: 4px;
    padding: 8px 10px;
    font-size: 13px;
    selection-background-color: #0078D4;
}
QLineEdit:read-only { color: #999; }
QComboBox {
    background-color: #252536;
    color: #e0e0e0;
    border: 1px solid #3f3f56;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 12px;
    min-height: 26px;
}
QComboBox::drop-down { border: none; width: 24px; }
QComboBox::down-arrow {
    image: none;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid #888;
    margin-right: 8px;
}
QComboBox QAbstractItemView {
    background-color: #252536;
    color: #e0e0e0;
    border: 1px solid #3f3f56;
    selection-background-color: #0078D4;
    outline: none;
}
QTableWidget {
    background-color: #16213e;
    alternate-background-color: #1a1a30;
    color: #e0e0e0;
    border: 1px solid #2a2a4a;
    border-radius: 6px;
    gridline-color: #2a2a4a;
    font-size: 12px;
    selection-background-color: #1e3a5f;
    selection-color: #e0e0e0;
}
QTableWidget::item { padding: 4px 8px; border-bottom: 1px solid #2a2a4a; }
QTableWidget::item:selected { background-color: #1e3a5f; color: #e0e0e0; }
QHeaderView::section {
    background-color: #0d1527;
    color: #aab;
    font-weight: bold;
    font-size: 11px;
    padding: 8px 10px;
    border: none;
    border-bottom: 1px solid #2a2a4a;
    border-right: 1px solid #2a2a4a;
}
QTextEdit {
    background-color: #0d1117;
    color: #4ade80;
    border: 1px solid #2a2a4a;
    border-radius: 4px;
    font-family: 'Consolas', 'Courier New', monospace;
    font-size: 11px;
    padding: 6px;
}
QScrollBar:vertical {
    background: #16213e; width: 10px; border: none; border-radius: 5px;
}
QScrollBar::handle:vertical {
    background: #3a3a5a; border-radius: 5px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #4a4a6a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QScrollBar:horizontal { background: #16213e; height: 10px; border: none; }
QScrollBar::handle:horizontal { background: #3a3a5a; border-radius: 5px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #4a4a6a; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QCheckBox { spacing: 6px; }
QCheckBox::indicator {
    width: 16px; height: 16px; border-radius: 3px;
    border: 1px solid #555; background: #252536;
}
QCheckBox::indicator:checked { background: #0078D4; border-color: #0078D4; }
QCheckBox::indicator:unchecked:hover { border-color: #888; }
"""

# ── Generic AEP names to exclude ──────────────────────────────────────────────
GENERIC_AEP_NAMES = {
    'cs6', 'project', '1', 'cc', 'ver_1', '(cs6)',
    'cs5', 'cs5.5', 'cs4', 'cc2014', 'cc2015', 'cc2017', 'cc2018', 'cc2019', 'cc2020',
}

def is_generic_aep(name: str) -> bool:
    return name.strip().lower() in GENERIC_AEP_NAMES


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

def get_all_categories():
    """Return built-in + custom categories."""
    return BUILTIN_CATEGORIES + load_custom_categories()

def get_all_category_names():
    """Return sorted list of all category names."""
    return sorted(set(name for name, _ in get_all_categories()))

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
    "ui8", "craftwork", "ls graphics",
    # Common abbreviations - ONLY match with separator + number: VH-12345, GR-9999
    # NOT in prefix list to avoid eating real words (ae->aerial, gr->grand)
]

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
                  [_normalize(p) for p in MARKETPLACE_PREFIXES] else m.group(0), name)

    # Strip item ID patterns
    for pat in _ID_PATTERNS:
        name = re.sub(pat, '', name, flags=re.IGNORECASE)

    # Normalize to work with the name
    norm = name.strip()

    # Try stripping source prefixes with common separators: " - ", "-", "_", " "
    norm_lower = norm.lower().replace('-', ' ').replace('_', ' ')
    norm_lower = re.sub(r'\s+', ' ', norm_lower).strip()

    # Sort prefixes longest-first so "envato elements" matches before "envato"
    sorted_prefixes = sorted(MARKETPLACE_PREFIXES, key=len, reverse=True)

    for prefix in sorted_prefixes:
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
    if result_check in [p.lower() for p in MARKETPLACE_PREFIXES]:
        return folder_name

    return norm if len(norm) > 2 else folder_name

def _normalize(text: str) -> str:
    t = text.lower()
    t = t.replace('-', ' ').replace('_', ' ').replace('.', ' ')
    t = re.sub(r'[^a-z0-9\s]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def categorize_folder(folder_name: str) -> tuple:
    """Match folder name against categories. Returns (category, score, cleaned_name) or (None, 0, cleaned).
    Strips marketplace prefixes and item IDs before matching."""
    cleaned = _strip_source_name(folder_name)

    # If the folder IS a bare marketplace name (nothing was stripped), skip categorization
    name_check = _normalize(folder_name)
    if name_check in [_normalize(p) for p in MARKETPLACE_PREFIXES]:
        return (None, 0, cleaned)

    norm = _normalize(cleaned)
    norm_loose = cleaned.lower().replace('-', ' ').replace('_', ' ').replace('.', ' ')
    norm_loose = re.sub(r'\s+', ' ', norm_loose).strip()
    tokens = set(norm.split())
    best_cat = None
    best_score = 0

    for cat_name, keywords in get_all_categories():
        score = 0

        # Auto-match: folder name matches category name itself
        cat_norm = _normalize(cat_name)
        if norm == cat_norm:
            score = 100
        elif len(norm) > 3 and norm in cat_norm:
            # Folder name is a substring of category name: "Chill" in "Music - Ambient & Chill"
            score = max(score, 50 + len(norm) * 2)

        for kw in keywords:
            kw_norm = _normalize(kw)
            kw_stripped = kw_norm.strip()

            # Exact full match
            if norm == kw_stripped:
                score = max(score, 100)
            # Short keywords (<=4 chars) must be exact token matches
            elif len(kw_stripped) <= 4 and kw_stripped in tokens:
                score = max(score, 50 + len(kw_stripped) * 2)
            # Longer phrase found in folder name
            elif len(kw_stripped) > 4 and kw_stripped in norm:
                score = max(score, 50 + len(kw_stripped) * 2)
            # Folder name found within keyword (reverse: "chill" inside "chill music")
            elif len(norm) > 3 and norm in kw_stripped:
                score = max(score, 50 + len(norm) * 2)
            # Phrase found in loose name
            elif len(kw_stripped) > 4 and kw_stripped in _normalize(norm_loose):
                score = max(score, 45 + len(kw_stripped) * 2)
            else:
                # Token overlap
                kw_tokens = set(kw_stripped.split())
                sig_kw = {t for t in kw_tokens if len(t) > 2}
                if sig_kw:
                    matching = sig_kw & tokens
                    if matching:
                        token_score = (len(matching) / len(sig_kw)) * 40
                        if len(matching) > 1:
                            token_score += len(matching) * 5
                        score = max(score, token_score)

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
        "1. CLEAN the folder name: remove marketplace IDs, item codes, numeric suffixes, "
        "version numbers, site names (GraphicRiver, CreativeMarket, CM_, Envato, etc), "
        "dashes/underscores used as separators, and any junk. Keep ONLY the meaningful "
        "project title in clean Title Case.\n"
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
            # Limit to 40 most relevant files (skip generic previews/thumbs)
            shown = [f for f in files[:80] if not f.lower().startswith('__macosx')][:40]
            context_lines.append(f"Files inside ({len(files)} total, showing {len(shown)}):")
            for f in shown:
                context_lines.append(f"  {f}")
        if subdirs:
            context_lines.append(f"Subfolders: {', '.join(subdirs[:20])}")

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

    # ── Pre-scan: Cache I/O-heavy results once for reuse across levels ──
    has_folder = folder_path and os.path.isdir(folder_path)
    ext_result = (None, 0, '')  # Cached L1 result
    if has_folder:
        ext_result = classify_by_extensions(folder_path)

    # ── Level 1: Extension-based classification ──
    ext_cat, ext_conf, ext_detail = ext_result
    if ext_cat and ext_conf >= 80:
            result.update(category=ext_cat, confidence=ext_conf,
                          method='extension', detail=ext_detail)
            if log_cb:
                log_cb(f"    L1 Extension: {ext_cat} ({ext_conf:.0f}%) [{ext_detail}]")
            # Don't return yet — still apply context post-processing below
            return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

    # ── Level 2: Keyword matching (primary engine) ──
    cat, conf, cleaned = categorize_folder(folder_name)
    result['cleaned_name'] = cleaned

    if cat and conf >= 65:  # Only short-circuit for high-confidence keyword matches
        result.update(category=cat, confidence=conf, method='keyword',
                      detail=f"keyword:\"{cleaned}\"→{cat}")
        if log_cb:
            log_cb(f"    L2 Keyword: {cat} ({conf:.0f}%)")
        return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

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
            return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

    # ── Level 3: Metadata extraction + re-classification ──
    if has_folder:
        meta = extract_folder_metadata(folder_path, log_cb)
        result['metadata'] = meta

        # Use extracted metadata to attempt classification
        meta_keywords = meta.get('project_names', []) + meta.get('keywords', [])

        if meta_keywords:
            # Try classifying using extracted metadata names
            for mk in meta_keywords[:10]:
                m_cat, m_conf, m_cleaned = categorize_folder(mk)
                if m_cat and m_conf >= 40:
                    # Metadata-enriched classification - boost confidence slightly
                    adj_conf = min(m_conf + 10, 90)
                    result.update(category=m_cat, confidence=adj_conf,
                                  method='metadata+keyword',
                                  detail=f"meta:\"{mk}\"→{m_cat}")
                    if log_cb:
                        log_cb(f"    L3 Metadata: {m_cat} ({adj_conf:.0f}%) from \"{mk}\"")
                    return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

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
                return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

        # ── Level 3.5: Envato API enrichment ──
        envato_id = meta.get('envato_id', '')
        if envato_id:
            api_cat, api_conf, api_detail = _envato_api_classify(envato_id)
            if api_cat:
                result.update(category=api_cat, confidence=api_conf,
                              method='envato_api', detail=api_detail)
                if log_cb:
                    log_cb(f"    L3.5 Envato API: {api_cat} ({api_conf:.0f}%) [{api_detail}]")
                return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

    # ── Level 4: Folder composition heuristics (reuses folder walk) ──
    if has_folder:
        comp = analyze_folder_composition(folder_path)
        comp_cat, comp_conf, comp_detail = _classify_by_composition(comp)
        if comp_cat and comp_conf >= 50:
            result.update(category=comp_cat, confidence=comp_conf,
                          method='composition', detail=comp_detail)
            if log_cb:
                log_cb(f"    L4 Composition: {comp_cat} ({comp_conf:.0f}%) [{comp_detail}]")
            return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

    # ── Level 1 low-confidence fallback (uses cached ext_result) ──
    if ext_cat and ext_conf >= 50:
        result.update(category=ext_cat, confidence=ext_conf,
                      method='extension', detail=ext_detail)
        if log_cb:
            log_cb(f"    L1 Extension (fallback): {ext_cat} ({ext_conf:.0f}%)")
        return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

    # ── Return best low-confidence result if any ──
    if keyword_fallback[0] and keyword_fallback[1] >= 15:
        result.update(category=keyword_fallback[0], confidence=keyword_fallback[1],
                      method='keyword_low', detail=f"keyword_low:\"{cleaned}\"")
        return _apply_context(result, folder_path, folder_name, has_folder, log_cb)

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
class ScanAepWorker(QThread):
    finished = pyqtSignal(list)
    log = pyqtSignal(str)

    def __init__(self, root_dir):
        super().__init__()
        self.root_dir = root_dir

    def run(self):
        results = []
        root = Path(self.root_dir)
        try:
            folders = sorted([f for f in root.iterdir() if f.is_dir()])
        except PermissionError:
            self.log.emit("ERROR: Permission denied")
            self.finished.emit([]); return

        for folder in folders:
            self.log.emit(f"Scanning: {folder.name}")
            aep_files = []
            try:
                for aep in folder.rglob("*.aep"):
                    try:
                        aep_files.append((aep, aep.stat().st_size))
                    except (PermissionError, OSError):
                        continue
            except (PermissionError, OSError):
                pass

            largest = max(aep_files, key=lambda x: x[1]) if aep_files else None
            results.append({
                'folder_name': folder.name,
                'folder_path': str(folder),
                'largest_aep': largest[0].name if largest else None,
                'aep_rel_path': str(largest[0].relative_to(folder)) if largest else None,
                'aep_size': largest[1] if largest else 0,
            })
        self.finished.emit(results)


class ScanCategoryWorker(QThread):
    finished = pyqtSignal(list)
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

    def __init__(self, root_dir, dest_dir):
        super().__init__()
        self.root_dir = root_dir
        self.dest_dir = dest_dir

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

            # Skip generic/junk folder names
            skip_names = {'assets', 'asset', 'source', 'src', 'dist', 'build', 'output',
                          'export', 'render', 'renders', 'preview', 'previews', 'temp',
                          'tmp', 'cache', '__macosx', '.ds_store', 'footage', 'fonts',
                          'images', 'img', 'audio', 'video', 'music', 'sound', 'sounds',
                          'textures', 'materials', 'elements', 'components', 'layers',
                          'compositions', 'comps', 'precomps', 'help', 'docs', 'documentation',
                          'readme', 'license', 'licenses'}
            if sub.name.lower() not in skip_names:
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
        results = []
        root = Path(self.root_dir)
        try:
            folders = sorted([f for f in root.iterdir() if f.is_dir()])
        except PermissionError:
            self.log.emit("ERROR: Permission denied")
            self.finished.emit([]); return

        # Log engine capabilities
        caps = ["keyword"]
        if HAS_RAPIDFUZZ: caps.append("fuzzy")
        if HAS_PSD_TOOLS: caps.append("psd-metadata")
        caps.extend(["extension-map", "prproj-metadata", "content-analysis"])
        self.log.emit(f"  Engine: tiered v4.0 [{', '.join(caps)}, context-inference]")

        total = len(folders)
        for idx, folder in enumerate(folders):
            self.progress.emit(idx + 1, total)

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

            results.append({
                'folder_name': folder.name,
                'folder_path': str(folder),
                'category': cat,
                'confidence': conf,
                'cleaned_name': cleaned if depth == 0 else f"{cleaned} (via: {source_name})",
                'source_depth': depth,
                'method': method,
                'detail': detail,
                'topic': topic,
            })
        self.finished.emit(results)


# ── LLM Classification Worker ─────────────────────────────────────────────────
class ScanLLMWorker(QThread):
    """Scans folders using Ollama LLM for classification and renaming.
    Processes every folder through the LLM for maximum accuracy."""
    finished = pyqtSignal(list)
    log = pyqtSignal(str)
    progress = pyqtSignal(int, int)

    def __init__(self, root_dir, dest_dir):
        super().__init__()
        self.root_dir = root_dir
        self.dest_dir = dest_dir

    def run(self):
        results = []
        root = Path(self.root_dir)
        settings = load_ollama_settings()

        try:
            folders = sorted([f for f in root.iterdir() if f.is_dir()])
        except PermissionError:
            self.log.emit("ERROR: Permission denied")
            self.finished.emit([]); return

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

        total = len(folders)
        llm_ok = 0; llm_fail = 0

        for idx, folder in enumerate(folders):
            self.progress.emit(idx + 1, total)

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

                results.append({
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

                results.append({
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

        self.log.emit(f"\n  LLM results: {llm_ok} classified, {llm_fail} fell back to rules")
        self.finished.emit(results)

    def _fallback_scan(self, folders):
        """Full rule-based fallback if Ollama is unreachable."""
        results = []
        total = len(folders)
        for idx, folder in enumerate(folders):
            self.progress.emit(idx + 1, total)
            top_result = tiered_classify(folder.name, str(folder))
            cat = top_result['category']
            if cat:
                self.log.emit(f"  {folder.name}  -->  {cat}  ({top_result['confidence']:.0f}%)")
            results.append({
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
        self.finished.emit(results)


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
            except Exception as e:
                err += 1
                self.log.emit(f"  \u274C Error: {e}")
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
        self.setWindowTitle("FileOrganizer v4.0")
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
        if src: self.txt_src.setText(src)
        if dst: self.txt_dst.setText(dst)
        if op < self.cmb_op.count(): self.cmb_op.setCurrentIndex(op)
        self.sld_conf.setValue(thresh)
        self.chk_llm.setChecked(use_llm)

    def _save_settings(self):
        self.settings.setValue("last_source", self.txt_src.text())
        self.settings.setValue("last_dest", self.txt_dst.text())
        self.settings.setValue("last_op", self.cmb_op.currentIndex())
        self.settings.setValue("confidence_threshold", self.sld_conf.value())
        self.settings.setValue("use_llm", self.chk_llm.isChecked())

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
        cw = QWidget(); self.setCentralWidget(cw); root = QVBoxLayout(cw); root.setSpacing(6)

        # ── Operation selector row ──
        row_op = QHBoxLayout()
        row_op.addWidget(QLabel("Operation:"))
        self.cmb_op = QComboBox()
        self.cmb_op.addItems(["Rename Folders by Largest .aep File", "Categorize Folders into Groups"])
        self.cmb_op.currentIndexChanged.connect(self._on_op_changed)
        row_op.addWidget(self.cmb_op, 1)
        # Custom categories button
        self.btn_custom_cats = QPushButton("Edit Categories")
        self.btn_custom_cats.setFixedWidth(120)
        self.btn_custom_cats.clicked.connect(self._open_custom_cats)
        row_op.addWidget(self.btn_custom_cats)
        # Envato API key button
        self.btn_envato = QPushButton("Envato API")
        self.btn_envato.setFixedWidth(90)
        self.btn_envato.setToolTip("Set Envato API key for marketplace metadata enrichment")
        self.btn_envato.clicked.connect(self._set_envato_key)
        row_op.addWidget(self.btn_envato)
        # Ollama LLM settings button
        self.btn_ollama = QPushButton("Ollama LLM")
        self.btn_ollama.setFixedWidth(90)
        self.btn_ollama.setToolTip("Configure Ollama LLM for AI-powered classification and renaming")
        self.btn_ollama.clicked.connect(self._open_ollama_settings)
        row_op.addWidget(self.btn_ollama)
        root.addLayout(row_op)

        # ── Source row ──
        row_src = QHBoxLayout()
        row_src.addWidget(QLabel("Source:"))
        self.txt_src = QLineEdit(); self.txt_src.setPlaceholderText("Folder containing subfolders to organize...")
        row_src.addWidget(self.txt_src, 1)
        btn_src = QPushButton("Browse..."); btn_src.setFixedWidth(80); btn_src.clicked.connect(self._browse_src)
        row_src.addWidget(btn_src)
        root.addLayout(row_src)

        # ── Destination row (categorize mode) ──
        self.row_dst_w = QWidget()
        row_dst = QHBoxLayout(self.row_dst_w); row_dst.setContentsMargins(0,0,0,0)
        row_dst.addWidget(QLabel("Output:"))
        self.txt_dst = QLineEdit(); self.txt_dst.setPlaceholderText("Destination root for category folders...")
        row_dst.addWidget(self.txt_dst, 1)
        btn_dst = QPushButton("Browse..."); btn_dst.setFixedWidth(80); btn_dst.clicked.connect(self._browse_dst)
        row_dst.addWidget(btn_dst)
        self.row_dst_w.hide()
        root.addWidget(self.row_dst_w)

        # ── Search bar + Confidence slider row ──
        row_filter = QHBoxLayout()
        row_filter.addWidget(QLabel("Filter:"))
        self.txt_search = QLineEdit(); self.txt_search.setPlaceholderText("Type to filter table results...")
        self.txt_search.textChanged.connect(self._apply_filter)
        row_filter.addWidget(self.txt_search, 1)

        row_filter.addWidget(QLabel("Min Confidence:"))
        self.sld_conf = QSlider(Qt.Orientation.Horizontal)
        self.sld_conf.setRange(0, 100); self.sld_conf.setValue(0)
        self.sld_conf.setFixedWidth(120)
        self.sld_conf.valueChanged.connect(self._on_conf_changed)
        row_filter.addWidget(self.sld_conf)
        self.lbl_conf = QLabel("0%"); self.lbl_conf.setFixedWidth(35)
        row_filter.addWidget(self.lbl_conf)
        root.addLayout(row_filter)

        # ── Button row ──
        row_btns = QHBoxLayout()
        self.btn_scan = QPushButton("Scan"); self.btn_scan.setFixedWidth(80); self.btn_scan.clicked.connect(self._on_scan)
        self.btn_apply = QPushButton("Apply"); self.btn_apply.setFixedWidth(80); self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._on_apply)
        # Preview tree
        self.btn_preview = QPushButton("Preview"); self.btn_preview.setFixedWidth(80)
        self.btn_preview.clicked.connect(self._show_preview); self.btn_preview.setEnabled(False)
        # Undo
        self.btn_undo = QPushButton("Undo Last"); self.btn_undo.setFixedWidth(90)
        self.btn_undo.clicked.connect(self._on_undo); self.btn_undo.setEnabled(bool(load_undo_log()))
        # Selection
        btn_all = QPushButton("Select All"); btn_all.setFixedWidth(80); btn_all.clicked.connect(self._sel_all)
        btn_none = QPushButton("Deselect All"); btn_none.setFixedWidth(90); btn_none.clicked.connect(self._sel_none)
        btn_inv = QPushButton("Invert"); btn_inv.setFixedWidth(60); btn_inv.clicked.connect(self._sel_inv)
        # Checkbox for hash checking
        self.chk_hash = QCheckBox("Deduplicate")
        self.chk_hash.setToolTip("Skip identical files (MD5 hash) instead of overwriting")
        # LLM checkbox
        self.chk_llm = QCheckBox("Use LLM")
        self.chk_llm.setToolTip("Use Ollama LLM for AI-powered classification and folder name cleanup")
        self.chk_llm.setStyleSheet("QCheckBox { color: #e879f9; font-weight: bold; }")
        for w in [self.btn_scan, self.btn_apply, self.btn_preview, self.btn_undo,
                  btn_all, btn_none, btn_inv, self.chk_llm, self.chk_hash]:
            row_btns.addWidget(w)
        row_btns.addStretch()
        root.addLayout(row_btns)

        # ── Table ──
        self.tbl = QTableWidget(); self.tbl.setAlternatingRowColors(True)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tbl.customContextMenuRequested.connect(self._context_menu)
        self._setup_aep_tbl()
        root.addWidget(self.tbl, 1)

        # ── Empty state label ──
        self.lbl_empty = QLabel("Select source folder and click Scan")
        self.lbl_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_empty.setStyleSheet("color:#666; font-size:14px; padding:40px;")
        root.addWidget(self.lbl_empty)

        # ── Stats bar ──
        self.lbl_stats = QLabel(""); root.addWidget(self.lbl_stats)

        # ── Log panel ──
        self.txt_log = QTextEdit(); self.txt_log.setReadOnly(True); self.txt_log.setMaximumHeight(150)
        root.addWidget(self.txt_log)

        # ── Progress label ──
        row_bottom = QHBoxLayout()
        self.lbl_prog = QLabel(""); row_bottom.addWidget(self.lbl_prog)
        row_bottom.addStretch()
        self.lbl_llm_status = QLabel("LLM: checking...")
        self.lbl_llm_status.setStyleSheet("color: #f59e0b; font-size: 11px;")
        row_bottom.addWidget(self.lbl_llm_status)
        root.addLayout(row_bottom)

    # ═══ CONTEXT MENU (RIGHT-CLICK) ══════════════════════════════════════════
    def _context_menu(self, pos):
        row = self.tbl.rowAt(pos.y())
        if row < 0: return
        menu = QMenu(self)
        is_cat = self.cmb_op.currentIndex() == self.OP_CAT

        # Open folder in explorer
        act_open = menu.addAction("Open Folder in Explorer")
        # Reassign category (categorize mode only)
        act_reassign = None
        if is_cat and row < len(self.cat_items):
            act_reassign = menu.addAction("Change Category...")

        action = menu.exec(self.tbl.viewport().mapToGlobal(pos))
        if action == act_open:
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
            # Update table row
            ci = self.tbl.item(row, 4)
            if ci: ci.setText(new_cat)
            # Update confidence to show it was manual
            cfi = self.tbl.item(row, 5)
            if cfi: cfi.setText("--"); cfi.setForeground(QColor("#38bdf8"))
            # Update method column
            mi = self.tbl.item(row, 6)
            if mi: mi.setText("Manual"); mi.setForeground(QColor("#38bdf8"))
            self._log(f"  Reassigned: {it.folder_name}  ->  {new_cat}")
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
        self.tbl.setHorizontalHeaderLabels(["","Current Name","","New Name","AEP File","Size","Status"])
        h = self.tbl.horizontalHeader(); h.setFixedHeight(36)
        for c,m in [(0,"Fixed"),(1,"Stretch"),(2,"Fixed"),(3,"Stretch"),(4,"Stretch"),(5,"Fixed"),(6,"Fixed")]:
            h.setSectionResizeMode(c, getattr(QHeaderView.ResizeMode, m))
        self.tbl.setColumnWidth(0,40); self.tbl.setColumnWidth(2,36); self.tbl.setColumnWidth(5,80); self.tbl.setColumnWidth(6,80)

    def _setup_cat_tbl(self):
        self.tbl.setColumnCount(8)
        self.tbl.setHorizontalHeaderLabels(["","Folder Name","Detected As","","Target Category","Conf","Method","Status"])
        h = self.tbl.horizontalHeader(); h.setFixedHeight(36)
        for c,m in [(0,"Fixed"),(1,"Stretch"),(2,"Stretch"),(3,"Fixed"),(4,"Stretch"),(5,"Fixed"),(6,"Fixed"),(7,"Fixed")]:
            h.setSectionResizeMode(c, getattr(QHeaderView.ResizeMode, m))
        self.tbl.setColumnWidth(0,40); self.tbl.setColumnWidth(3,36); self.tbl.setColumnWidth(5,55); self.tbl.setColumnWidth(6,80); self.tbl.setColumnWidth(7,70)

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
        src = self.txt_src.text()
        if not src or not os.path.isdir(src):
            self._log("Invalid source directory"); return
        self.lbl_empty.hide(); self.tbl.setRowCount(0)
        self.btn_scan.setEnabled(False); self.btn_apply.setEnabled(False); self.btn_preview.setEnabled(False)
        if self.cmb_op.currentIndex() == self.OP_CAT:
            dst = self.txt_dst.text()
            if not dst: self._log("Set output directory first"); self.btn_scan.setEnabled(True); return
            self._scan_cat(src, dst)
        else:
            self._scan_aep(src)

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
        self.worker = ScanAepWorker(src)
        self.worker.log.connect(self._log)
        self.worker.finished.connect(self._aep_done); self.worker.start()

    def _aep_done(self, results):
        self.tbl.setRowCount(0); self.aep_items.clear(); shown = 0
        for r in results:
            if not r['largest_aep']: continue
            aep_stem = os.path.splitext(r['largest_aep'])[0]
            if is_generic_aep(aep_stem): continue
            new_name = f"{r['folder_name']} - {aep_stem}"
            if r['folder_name'] in new_name and aep_stem in r['folder_name']: continue
            it = RenameItem(); it.current_name = r['folder_name']; it.new_name = new_name
            it.aep_file = r.get('aep_rel_path', r['largest_aep'])
            it.file_size = format_size(r['aep_size'])
            it.full_current_path = r['folder_path']
            it.full_new_path = os.path.join(os.path.dirname(r['folder_path']), new_name)
            it.status = "Pending"; it.selected = True; shown += 1
            self.aep_items.append(it); self._add_aep_row(it, len(self.aep_items)-1)

        self.btn_scan.setEnabled(True); self.btn_apply.setEnabled(shown > 0); self.lbl_prog.setText("")
        self._stats_aep()
        self._log(f"Scan complete: {shown} eligible folders found")
        if shown == 0: self.lbl_empty.setText("No eligible folders found"); self.lbl_empty.show()

    def _add_aep_row(self, it, idx):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setCellWidget(r, 0, self._make_cb(it.selected, self._aep_cb, idx))
        self.tbl.setItem(r, 1, self._it(it.current_name))
        self.tbl.setItem(r, 2, self._make_arrow())
        ni = self._it(it.new_name); ni.setForeground(QColor("#4ade80")); f=ni.font(); f.setBold(True); ni.setFont(f); self.tbl.setItem(r, 3, ni)
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

        if self.chk_llm.isChecked():
            if not self._ollama_ready:
                self._log("  WARNING: Ollama LLM not ready yet (still setting up or unavailable)")
                self._log("  Falling back to rule-based classification...")
                self.worker = ScanCategoryWorker(src, dst)
            else:
                self._log("  Mode: LLM-powered (all folders processed through Ollama)")
                self.worker = ScanLLMWorker(src, dst)
        else:
            self.worker = ScanCategoryWorker(src, dst)

        self.worker.log.connect(self._log)
        self.worker.progress.connect(lambda c,t: self.lbl_prog.setText(f"Scanning {c}/{t}..."))
        self.worker.finished.connect(self._cat_done); self.worker.start()

    def _cat_done(self, results):
        self.tbl.setRowCount(0); self.cat_items.clear(); matched = unmatched = 0
        dst = self.txt_dst.text()
        thresh = self.sld_conf.value()
        method_counts = Counter()
        context_count = 0; llm_renamed = 0
        for r in results:
            if not r['category']: unmatched += 1; continue
            it = CategorizeItem(); it.folder_name = r['folder_name']; it.category = r['category']
            it.cleaned_name = r.get('cleaned_name', r['folder_name'])
            it.confidence = r['confidence']; it.full_source_path = r['folder_path']

            # Use LLM-cleaned name for dest path if available (rename-on-move)
            llm_name = r.get('llm_name')
            dest_folder_name = llm_name if llm_name and llm_name != r['folder_name'] else r['folder_name']
            it.full_dest_path = os.path.join(dst, r['category'], dest_folder_name)

            it.method = r.get('method', ''); it.detail = r.get('detail', '')
            it.topic = r.get('topic', '') or ''
            it.status = "Pending"
            it.selected = it.confidence >= thresh
            matched += 1
            if it.topic:
                context_count += 1
            if llm_name and llm_name != r['folder_name']:
                llm_renamed += 1
            method_counts[it.method or 'unknown'] += 1
            self.cat_items.append(it); self._add_cat_row(it, len(self.cat_items)-1)

        self.btn_scan.setEnabled(True); self.btn_apply.setEnabled(matched > 0)
        self.btn_preview.setEnabled(matched > 0)
        self.lbl_prog.setText("")
        self._cat_unmatched = unmatched; self._stats_cat()
        methods_str = ', '.join(f"{k}:{v}" for k, v in method_counts.most_common())
        self._log(f"Categorization complete: {matched} matched, {unmatched} uncategorized")
        self._log(f"  Methods used: {methods_str}")
        if context_count:
            self._log(f"  Context overrides: {context_count} (topic → asset type)")
        if llm_renamed:
            self._log(f"  LLM renamed: {llm_renamed} folders will be renamed on move")
        if matched == 0: self.lbl_empty.setText("No folders could be categorized"); self.lbl_empty.show()

    def _add_cat_row(self, it, idx):
        r = self.tbl.rowCount(); self.tbl.insertRow(r)
        self.tbl.setCellWidget(r, 0, self._make_cb(it.selected, self._cat_cb, idx))
        self.tbl.setItem(r, 1, self._it(it.folder_name))
        # Show cleaned/detected name - highlight LLM renames and context overrides
        # Check if dest path has a different folder name (LLM rename-on-move)
        dest_basename = os.path.basename(it.full_dest_path)
        is_llm_renamed = dest_basename != it.folder_name and it.method == 'llm'
        if is_llm_renamed:
            det = self._it(f"{dest_basename}")
            det.setForeground(QColor("#f472b6"))  # pink = LLM renamed
            det.setToolTip(f"LLM will rename \"{it.folder_name}\" to \"{dest_basename}\" during move")
        elif it.topic:
            det = self._it(f"{it.cleaned_name} [{it.topic}]")
            det.setForeground(QColor("#e879f9"))  # purple = context override from topic
            det.setToolTip(f"Topic \"{it.topic}\" overridden to asset type \"{it.category}\" because design files were found")
        elif it.cleaned_name != it.folder_name:
            det = self._it(it.cleaned_name)
            det.setForeground(QColor("#38bdf8"))  # bright blue = source was stripped
        else:
            det = self._it(it.cleaned_name)
            det.setForeground(QColor("#777"))
        self.tbl.setItem(r, 2, det)
        self.tbl.setItem(r, 3, self._make_arrow())
        ci = self._it(it.category); ci.setForeground(QColor("#4ade80")); f=ci.font(); f.setBold(True); ci.setFont(f); self.tbl.setItem(r, 4, ci)
        clr = "#4ade80" if it.confidence >= 80 else "#f59e0b" if it.confidence >= 50 else "#ef4444"
        cfi = self._it(f"{it.confidence:.0f}%"); cfi.setForeground(QColor(clr)); cfi.setTextAlignment(Qt.AlignmentFlag.AlignCenter); self.tbl.setItem(r, 5, cfi)
        # Method column with color coding
        METHOD_COLORS = {'extension': '#a78bfa', 'keyword': '#4ade80', 'fuzzy': '#facc15',
                         'metadata': '#38bdf8', 'metadata+keyword': '#2dd4bf',
                         'keyword_low': '#f97316', 'Manual': '#38bdf8',
                         'envato_api': '#f472b6', 'composition': '#a3e635',
                         'context': '#e879f9', 'llm': '#f472b6'}
        method_label = it.method.replace('_', ' ').replace('+', '+') if it.method else ''
        mi = self._it(method_label); mi.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        mi.setForeground(QColor(METHOD_COLORS.get(it.method, '#888')))
        if it.detail: mi.setToolTip(it.detail)
        self.tbl.setItem(r, 6, mi)
        sti = self._it("Pending"); sti.setTextAlignment(Qt.AlignmentFlag.AlignCenter); sti.setForeground(QColor("#f59e0b")); self.tbl.setItem(r, 7, sti)

    def _cat_cb(self, idx, st):
        if idx < len(self.cat_items):
            self.cat_items[idx].selected = bool(st); self._upd_stats()

    def _stats_cat(self):
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

    # ═══ APPLY ════════════════════════════════════════════════════════════════
    def _on_apply(self):
        (self._apply_cat if self.cmb_op.currentIndex()==self.OP_CAT else self._apply_aep)()

    def _apply_aep(self):
        work = [(i,it) for i,it in enumerate(self.aep_items) if it.selected and it.status=="Pending"]
        if not work: self._log("No items selected"); return
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
        self._set_status(row_idx, status, color, 7)
        self.tbl.scrollToItem(self.tbl.item(row_idx, 1))

    def _on_cat_apply_done(self, ok, err, undo_ops):
        self.btn_scan.setEnabled(True); self.cmb_op.setEnabled(True); self._stats_cat()
        self._log(f"Complete: {ok} moved, {err} errors"); self.lbl_prog.setText(f"Complete: {ok} moved, {err} errors")
        if undo_ops:
            save_undo_log(undo_ops); self.undo_ops = undo_ops; self.btn_undo.setEnabled(True)
            append_csv_log(undo_ops)
            self._log(f"Undo log and CSV log saved")


# ── Entry Point ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    window = FileOrganizer()
    window.show()
    sys.exit(app.exec())
