"""Manifest-driven routing for Premiere Motion Graphics Templates."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fileorganizer.mogrt_parser import mogrt_to_category_hints, parse_mogrt

from ._types import MetadataHint

_CAT_MOTION = "Premiere Pro - Motion Graphics (.mogrt)"
_CAT_TEMPLATES = "Premiere Pro - Templates"
_CAT_TRANSITIONS = "Premiere Pro - Transitions & FX"
_CAT_TITLE = "Premiere Pro - Title & Typography"
_CAT_SOCIAL = "Premiere Pro - Social Media"
_CAT_OTHER = "Premiere Pro - Other"

_TEXT_PARAMETER_RE = re.compile(
    r"\b(?:title|subtitle|text|headline|caption|lower\s*third|name|date|"
    r"location|company|font|description|message)\b",
    re.IGNORECASE,
)


def extract(path: Path, detected_ext: str | None = None) -> Optional[MetadataHint]:
    """Parse a MOGRT manifest and return a canonical Premiere category hint."""
    if not path or not path.exists() or not path.is_file():
        return None
    ext = (detected_ext or path.suffix).lower()
    if ext != ".mogrt":
        return None

    metadata = parse_mogrt(str(path))
    if not metadata:
        return None

    category, confidence, reason, signals = _route_manifest(metadata)
    raw = dict(metadata)
    raw["category_signals"] = signals
    raw["source_path"] = path.name
    return MetadataHint(
        category=category,
        confidence=confidence,
        extractor="mogrt",
        reason=reason,
        raw=raw,
    )


def _route_manifest(metadata: dict) -> tuple[str, int, str, list[str]]:
    name = str(metadata.get("name") or "").strip()
    name_lower = name.casefold()
    parameters = _string_values(metadata.get("parameters"))
    required_fonts = _string_values(metadata.get("required_fonts"))
    parameter_count = _count(metadata.get("parameter_count"), parameters)
    font_count = _count(metadata.get("font_count"), required_fonts)

    parser_hints = mogrt_to_category_hints(metadata)
    signals = [str(signal) for signal in parser_hints.get("category_signals", [])]
    parameter_text = " | ".join(parameters)
    combined = f"{name_lower} {parameter_text.casefold()}"

    if any(signal in {"Transition", "Effect"} for signal in signals):
        category = _CAT_TRANSITIONS
        signals.append("transition/effect manifest name")
    elif re.search(r"\b(?:transition|wipe|dissolve|fade|glitch|effect|filter)\b", combined):
        category = _CAT_TRANSITIONS
        signals.append("transition/effect parameter signal")
    elif re.search(r"\b(?:social|reel|reels|story|stories|instagram|tiktok|shorts)\b", combined):
        category = _CAT_SOCIAL
        signals.append("social-format manifest signal")
    elif "Title / Lower Third" in signals or _TEXT_PARAMETER_RE.search(combined):
        category = _CAT_TITLE
        signals.append("text parameter/name signal")
    elif font_count > 0 and parameter_count > 0:
        # Required fonts plus editable controls are a strong typography signal
        # even when the vendor used a generic template name.
        category = _CAT_TITLE
        signals.append("required fonts + editable parameters")
    elif parameter_count >= 3:
        category = _CAT_MOTION
        signals.append("three or more editable parameters")
    elif any(signal == "Motion Graphic" for signal in signals):
        category = _CAT_MOTION
    elif name:
        category = _CAT_TEMPLATES
        signals.append("valid MOGRT manifest")
    else:
        category = _CAT_OTHER
        signals.append("valid unnamed MOGRT manifest")

    # A valid manifest is already strong evidence of a Premiere template;
    # subcategory signals can safely hard-route it without invoking an LLM.
    confidence = 96 if len(signals) > 1 else 92
    display_name = name or "unnamed template"
    reason = (
        f"MOGRT manifest: {display_name}; "
        f"{parameter_count} editable parameter(s); "
        f"{font_count} required font(s); "
        f"{signals[-1]}"
    )
    return category, confidence, reason, signals


def _string_values(value) -> list[str]:
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _count(value, fallback: list[str]) -> int:
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return len(fallback)
