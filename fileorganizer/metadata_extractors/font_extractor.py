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


def extract(path: Path) -> Optional[MetadataHint]:
    """Read font name table and emit a Fonts & Typography hint at conf 95. Detects variable axes (NEXT-56)."""
    if not _HAS_FONTTOOLS:
        return None
    if not path or not path.exists():
        return None
    if path.suffix.lower() not in {".ttf", ".otf", ".ttc", ".woff", ".woff2"}:
        return None

    try:
        from fontTools.ttLib import TTFont  # type: ignore
        # lazy=True avoids loading every glyph; fontNumber=0 picks first face in TTC.
        if path.suffix.lower() == ".ttc":
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
        
        # NEXT-56: Detect variable axes and color formats
        is_variable = "fvar" in font
        var_axes = []
        if is_variable:
            try:
                fvar = font["fvar"]
                var_axes = [ax.axisTag for ax in fvar.axes]
            except Exception:
                pass
        
        has_colr = "COLR" in font
        has_colrv1 = False
        if has_colr:
            try:
                colr = font["COLR"]
                has_colrv1 = colr.version >= 1
            except Exception:
                pass
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
            reason=f"valid font header (no name fields) — {path.suffix.lower()}",
            raw={"ext": path.suffix.lower(), "is_variable": is_variable, "color": has_colr},
        )

    return MetadataHint(
        category=_CAT_FONTS,
        confidence=95,
        extractor="font",
        reason=f"{family or full_name}".strip(),
        raw={
            "family": family,
            "subfamily": subfamily,
            "full_name": full_name,
            "version": version,
            "foundry": foundry,
            "ext": path.suffix.lower(),
            "is_variable": is_variable,
            "variable_axes": var_axes if var_axes else None,
            "has_color": has_colr,
            "has_colrv1": has_colrv1,
        },
    )
