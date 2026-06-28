"""
Font metadata extractor — fonttools 4.62.1+ (CVE-2025-66034 pin from N-13).

Reads TTFont name table entries (family, style, foundry) and routes to the
canonical Fonts category at confidence 95. Font detection is the most reliable
extractor: a valid .ttf/.otf header is essentially incontrovertible.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Optional

from ._types import MetadataHint

_HAS_FONTTOOLS = importlib.util.find_spec("fontTools") is not None

_CAT_FONTS = "Fonts & Typography"


def _num(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    return int(numeric) if numeric.is_integer() else numeric


def _name_table_lookup(font, name_id: int) -> str:
    """Pull a name_id from the 'name' table — Unicode preferred, then Mac, then anything."""
    try:
        name_table = font["name"]
    except Exception:
        return ""
    # Preferred encodings: (platformID, platEncID, langID)
    preferences = [
        (3, 1, 0x0409),  # Windows Unicode English-US
        (3, 1, 0),
        (1, 0, 0),       # Mac Roman English
        (0, 3, 0),       # Unicode 2.0+
    ]
    # Try preferred encodings first.
    for platform_id, platenc_id, lang_id in preferences:
        try:
            entry = name_table.getName(name_id, platform_id, platenc_id, lang_id)
            if entry is not None:
                return str(entry).strip()
        except Exception:
            continue
    # Fallback: any entry with this name_id.
    try:
        for entry in name_table.names:
            if entry.nameID == name_id:
                try:
                    return entry.toUnicode().strip()
                except Exception:
                    continue
    except Exception:
        pass
    return ""


def _variable_axes(font) -> list[dict]:
    axes = []
    try:
        fvar = font["fvar"]
    except Exception:
        return axes
    for axis in getattr(fvar, "axes", []) or []:
        try:
            tag = str(getattr(axis, "axisTag", "") or "").strip()
            if not tag:
                continue
            name_id = int(getattr(axis, "axisNameID", 0) or 0)
            axis_meta = {
                "tag": tag,
                "name": _name_table_lookup(font, name_id) or tag,
                "min": _num(getattr(axis, "minValue", None)),
                "default": _num(getattr(axis, "defaultValue", None)),
                "max": _num(getattr(axis, "maxValue", None)),
            }
            axes.append({k: v for k, v in axis_meta.items() if v is not None})
        except Exception:
            continue
    return axes


def _color_flags(font) -> tuple[bool, bool]:
    has_colr = "COLR" in font
    has_colrv1 = False
    if has_colr:
        try:
            colr = font["COLR"]
            has_colrv1 = int(getattr(colr, "version", 0) or 0) >= 1
        except Exception:
            has_colrv1 = False
    return has_colr, has_colrv1


def _font_reason(family: str, full_name: str, axes: list[dict], has_colrv1: bool) -> str:
    reason = f"{family or full_name}".strip()
    traits = []
    if axes:
        traits.append("variable:" + ",".join(a["tag"] for a in axes if a.get("tag")))
    if has_colrv1:
        traits.append("COLRv1")
    if traits:
        reason = f"{reason} ({'; '.join(traits)})" if reason else "; ".join(traits)
    return reason or "valid font"


def extract(path: Path, detected_ext: str | None = None) -> Optional[MetadataHint]:
    """Read font name table and emit a Fonts & Typography hint at conf 95. Detects variable axes (NEXT-56)."""
    if not _HAS_FONTTOOLS:
        return None
    if not path or not path.exists():
        return None
    ext = (detected_ext or path.suffix).lower()
    if ext not in {".ttf", ".otf", ".ttc", ".woff", ".woff2"}:
        return None

    try:
        from fontTools.ttLib import TTFont  # type: ignore
        # lazy=True avoids loading every glyph; fontNumber=0 picks first face in TTC.
        if ext == ".ttc":
            font = TTFont(str(path), lazy=True, fontNumber=0)
        else:
            font = TTFont(str(path), lazy=True)
    except Exception:
        return None

    try:
        family = _name_table_lookup(font, 1)       # Font Family name
        subfamily = _name_table_lookup(font, 2)    # Font Subfamily name
        full_name = _name_table_lookup(font, 4)    # Full font name
        version = _name_table_lookup(font, 5)
        foundry = _name_table_lookup(font, 8)
        
        # NEXT-56: Detect variable axes and color font format.
        var_axes = _variable_axes(font)
        is_variable = bool(var_axes)
        has_colr, has_colrv1 = _color_flags(font)
    finally:
        try:
            font.close()
        except Exception:
            pass

    if not (family or full_name):
        # Header parsed but no usable name fields — still likely a font, low conf.
        return MetadataHint(
            category=_CAT_FONTS,
            confidence=80,
            extractor="font",
            reason=f"valid font header (no name fields) - {ext}",
            raw={
                "ext": ext,
                "original_ext": path.suffix.lower(),
                "is_variable": is_variable,
                "variable_axes": var_axes if var_axes else None,
                "variable_axis_tags": [a["tag"] for a in var_axes] if var_axes else None,
                "has_color": has_colr,
                "has_colrv1": has_colrv1,
                "is_colrv1": has_colrv1,
            },
        )

    reason = _font_reason(family, full_name, var_axes, has_colrv1)
    return MetadataHint(
        category=_CAT_FONTS,
        confidence=95,
        extractor="font",
        reason=reason,
        raw={
            "family": family,
            "subfamily": subfamily,
            "full_name": full_name,
            "version": version,
            "foundry": foundry,
            "ext": ext,
            "original_ext": path.suffix.lower(),
            "is_variable": is_variable,
            "variable_axes": var_axes if var_axes else None,
            "variable_axis_tags": [a["tag"] for a in var_axes] if var_axes else None,
            "has_color": has_colr,
            "has_colrv1": has_colrv1,
            "is_colrv1": has_colrv1,
        },
    )
