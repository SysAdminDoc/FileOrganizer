"""
PSD metadata extractor — psd-tools 1.16.0+.

Reads the PSD header (width, height, color mode, layer count) without
rendering the composite. Routes high-confidence cases (social-media canvas
sizes, square mockup canvases) directly to the matching Photoshop subcategory.

Falls back to None when psd-tools is missing or the file is corrupt.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

from ._types import MetadataHint

_HAS_PSD_TOOLS = importlib.util.find_spec("psd_tools") is not None


# Canonical Photoshop categories. These names MUST match classify_design.CATEGORIES;
# the caller validates against _CATEGORY_SET before emitting.
_CAT_SOCIAL_PRINT = "Print - Social Media Graphics"
_CAT_SMART_OBJECTS = "Photoshop - Smart Objects & Templates"
_CAT_FLYERS = "Print - Flyers & Posters"
_CAT_BUSINESS_CARDS = "Print - Business Cards & Stationery"
_CAT_PHOTOSHOP_OTHER = "Photoshop - Other"


def _ratio(w: int, h: int) -> float:
    if h <= 0:
        return 0.0
    return w / h


def _is_vertical_9x16(w: int, h: int) -> bool:
    """Story / Reel canvas (1080x1920, 720x1280, etc.)."""
    if w <= 0 or h <= 0 or w >= h:
        return False
    r = _ratio(w, h)
    return 0.55 <= r <= 0.58  # 9/16 = 0.5625


def _is_square_post(w: int, h: int) -> bool:
    """Instagram square post (1080x1080, etc.)."""
    if w <= 0 or h <= 0:
        return False
    return abs(w - h) <= 2 and 800 <= w <= 4500


def _is_business_card(w: int, h: int) -> bool:
    """Standard business-card aspect (3.5"x2" / 1050x600 @300DPI etc.)."""
    if w <= 0 or h <= 0:
        return False
    r = _ratio(max(w, h), min(w, h))
    return 1.65 <= r <= 1.85 and 600 <= min(w, h) <= 1500


def _is_flyer_a4_or_letter(w: int, h: int) -> bool:
    """A4 / US Letter portrait at common print DPIs (2480x3508 / 2550x3300 etc.)."""
    if w <= 0 or h <= 0:
        return False
    if w >= h:
        return False
    r = _ratio(h, w)
    return 1.29 <= r <= 1.45 and h >= 2000


def extract(path: Path) -> Optional[MetadataHint]:
    """Read a PSD/PSB header and emit a category hint if the canvas is recognizable."""
    if not _HAS_PSD_TOOLS:
        return None
    if not path or not path.exists():
        return None
    if path.suffix.lower() not in {".psd", ".psb"}:
        return None

    try:
        # Lazy import keeps the module importable when psd_tools isn't installed.
        from psd_tools import PSDImage  # type: ignore
        psd = PSDImage.open(str(path))
        width = int(getattr(psd, "width", 0) or 0)
        height = int(getattr(psd, "height", 0) or 0)
    except Exception:
        return None

    raw = {"width": width, "height": height, "ext": path.suffix.lower()}

    if width <= 0 or height <= 0:
        return None

    # Aspect-driven routing (highest signal first).
    if _is_vertical_9x16(width, height):
        return MetadataHint(
            category=_CAT_SOCIAL_PRINT,
            confidence=92,
            extractor="psd",
            reason=f"9:16 canvas ({width}x{height})",
            raw=raw,
        )
    if _is_square_post(width, height):
        return MetadataHint(
            category=_CAT_SOCIAL_PRINT,
            confidence=90,
            extractor="psd",
            reason=f"square post canvas ({width}x{height})",
            raw=raw,
        )
    if _is_business_card(width, height):
        return MetadataHint(
            category=_CAT_BUSINESS_CARDS,
            confidence=92,
            extractor="psd",
            reason=f"business-card aspect ({width}x{height})",
            raw=raw,
        )
    if _is_flyer_a4_or_letter(width, height):
        return MetadataHint(
            category=_CAT_FLYERS,
            confidence=90,
            extractor="psd",
            reason=f"A4/Letter portrait ({width}x{height})",
            raw=raw,
        )

    # Generic PSD with no recognizable canvas — emit a low-confidence hint.
    # The caller's >=90 threshold means this is informational only.
    return MetadataHint(
        category=_CAT_PHOTOSHOP_OTHER,
        confidence=40,
        extractor="psd",
        reason=f"unrecognized canvas ({width}x{height})",
        raw=raw,
    )
