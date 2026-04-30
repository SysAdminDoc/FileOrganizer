"""Thumbnail rendering + cache for the ReviewPanel and Browse tab.

Pattern adapted from TagStudio `qt/cache_manager.py` + `qt/previews/renderer.py`
[S56] but trimmed to FileOrganizer's needs:

- In-process `QPixmapCache` (RAM-only) keyed by absolute thumbnail-source path.
  The disk-backed LRU folder cache is overkill for the ReviewPanel; NEXT-22
  Browse tab can revisit if needed.
- A single QThread (`ThumbnailLoaderWorker`) owns all I/O so the UI never
  blocks on Pillow / psd_tools parses.
- Loaders are tried in priority order:
    1. `.psd` → psd_tools composite (fallback to extension badge if it fails)
    2. Other image extensions → Pillow.thumbnail()
    3. Anything else → extension badge (colored rect + ext text)
- Public API:
    * `cached_pixmap(path) -> QPixmap | None`        — fast cache lookup
    * `cache_pixmap(path, pixmap)`                    — store after load
    * `extension_badge(ext, theme) -> QPixmap`        — synthetic fallback
    * `ThumbnailLoaderWorker.queue(row, path, ext)`   — async load → emits
        `loaded(row: int, pixmap: QPixmap)`
"""
from __future__ import annotations

import os
from pathlib import Path
from queue import Empty, Queue

from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen, QPixmap, QPixmapCache


THUMB_SIZE = 64   # square px for ReviewPanel rows
# Note: PSD size limit lives in fileorganizer.psd_safe so every call site
# shares the same threshold.

_RASTER_EXTS = {
    '.jpg', '.jpeg', '.png', '.gif', '.bmp',
    '.webp', '.tiff', '.tif',
}

# Generous RAM budget — 2048 * 64*64 RGBA pixmaps is well under 50 MB.
QPixmapCache.setCacheLimit(50 * 1024)   # value is in KiB


# ── cache helpers ────────────────────────────────────────────────────────────

def _cache_key(path: str, size: int = THUMB_SIZE) -> str:
    """Cache key includes target size so resize re-renders don't hit stale."""
    return f"thumb::{size}::{os.path.normcase(os.path.abspath(path))}"


def cached_pixmap(path: str, size: int = THUMB_SIZE):
    """Return a cached QPixmap or None.

    PyQt6's `QPixmapCache.find(str)` returns Optional[QPixmap] directly; the
    two-arg PyQt5/Qt-C++ overload is gone.
    """
    pm = QPixmapCache.find(_cache_key(path, size))
    if pm is None or pm.isNull():
        return None
    return pm


def cache_pixmap(path: str, pixmap: QPixmap, size: int = THUMB_SIZE) -> None:
    if pixmap is None or pixmap.isNull():
        return
    QPixmapCache.insert(_cache_key(path, size), pixmap)


# ── extension badge fallback ─────────────────────────────────────────────────

# Stable color palette: hash extension into one of these so `.psd` always
# renders the same blue, `.aep` always the same magenta, etc.
_BADGE_PALETTE = [
    "#3b82f6", "#8b5cf6", "#ec4899", "#f97316",
    "#eab308", "#22c55e", "#06b6d4", "#64748b",
]


def _badge_color_for(ext: str) -> str:
    if not ext:
        return "#475569"
    return _BADGE_PALETTE[hash(ext.lower()) % len(_BADGE_PALETTE)]


def extension_badge(ext: str, size: int = THUMB_SIZE) -> QPixmap:
    """Synthetic colored badge with the extension drawn in the centre.

    Used when the item has no preview image, when the image fails to load,
    or for non-image file types (e.g. .aep, .mogrt, .zip).
    """
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    label = (ext.lstrip('.') or '?').upper()[:5]
    color = QColor(_badge_color_for(ext))

    painter = QPainter(pm)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(color)
        painter.setPen(QPen(color.darker(140), 1))
        painter.drawRoundedRect(2, 2, size - 4, size - 4, 8, 8)

        font = painter.font()
        # Scale the label so longer extensions still fit.
        font.setBold(True)
        font.setPointSize(max(7, int((size / 4) - max(0, len(label) - 3))))
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(pm.rect(), Qt.AlignmentFlag.AlignCenter, label)
    finally:
        painter.end()
    return pm


# ── loader paths ─────────────────────────────────────────────────────────────

def _load_raster(path: str, size: int) -> QPixmap | None:
    """Load any Pillow-readable raster.  Returns None on any failure."""
    try:
        from PIL import Image
        from PIL.ImageQt import ImageQt
    except Exception:
        # Pillow always installed (it's a hard requirement) but defensive.
        return None
    try:
        with Image.open(path) as im:
            im.thumbnail((size * 2, size * 2))
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            qim = ImageQt(im)
            pm = QPixmap.fromImage(qim)
            return pm.scaled(
                size, size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
    except Exception:
        return None


def _load_psd(path: str, size: int) -> QPixmap | None:
    """Load the embedded composite from a PSD via psd_tools.

    Routes through `fileorganizer.psd_safe.safe_psd_open` (N-13) which skips
    files over PSD_PARSE_LIMIT_BYTES and isolates parser exceptions so a
    malformed PSD can't crash the loader thread.
    """
    try:
        from PIL.ImageQt import ImageQt
        from fileorganizer.psd_safe import safe_psd_open
    except Exception:
        return None
    psd = safe_psd_open(path)
    if psd is None:
        return None
    try:
        im = psd.composite() if hasattr(psd, "composite") else psd.topil()
        if im is None:
            return None
        im.thumbnail((size * 2, size * 2))
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        qim = ImageQt(im)
        pm = QPixmap.fromImage(qim)
        return pm.scaled(
            size, size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    except Exception:
        return None


def render_pixmap(path: str, ext: str = "", size: int = THUMB_SIZE) -> QPixmap:
    """Synchronous render — cache lookup → real load → extension badge.

    Always returns a valid QPixmap; this never blocks on a network mount
    longer than Pillow.open() does on first read.
    """
    cached = cached_pixmap(path, size) if path else None
    if cached is not None:
        return cached

    pm: QPixmap | None = None
    if path and os.path.isfile(path):
        suffix = (Path(path).suffix or ext or '').lower()
        if suffix == '.psd':
            pm = _load_psd(path, size)
        if pm is None and suffix in _RASTER_EXTS:
            pm = _load_raster(path, size)

    if pm is None or pm.isNull():
        # Fallback: render a colored badge with the extension text.
        pm = extension_badge(ext or Path(path).suffix if path else '', size)

    if path:
        cache_pixmap(path, pm, size)
    return pm


# ── async loader QThread ─────────────────────────────────────────────────────

class ThumbnailLoaderWorker(QThread):
    """Single background worker that drains a queue of (row, path, ext) jobs
    and emits `loaded(row, pixmap)` per job.

    Owned by the panel; call `stop()` and `wait()` on teardown.  Multiple
    panels each get their own instance — no cross-panel sharing because
    QPixmap is bound to its source thread (we send via signal which Qt
    marshals safely).
    """
    loaded = pyqtSignal(int, QPixmap)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._queue: "Queue[tuple[int, str, str]]" = Queue()
        self._stop = False

    def queue(self, row: int, path: str, ext: str = "") -> None:
        self._queue.put((row, path, ext))

    def stop(self) -> None:
        self._stop = True
        # Sentinel so a blocking get() unblocks immediately.
        self._queue.put((-1, "", ""))

    def run(self) -> None:
        while not self._stop:
            try:
                row, path, ext = self._queue.get(timeout=0.5)
            except Empty:
                continue
            if self._stop or row < 0:
                break
            try:
                pm = render_pixmap(path, ext=ext, size=THUMB_SIZE)
            except Exception:
                pm = extension_badge(ext, THUMB_SIZE)
            if pm is not None and not pm.isNull():
                self.loaded.emit(row, pm)
