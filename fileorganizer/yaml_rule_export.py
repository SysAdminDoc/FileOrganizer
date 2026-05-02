"""
YAML rule export — NEXT-2.

Serialises the FileOrganizer canonical taxonomy + alias map into a portable
rules file in the organize-cli (tfeldmann/organize) format::

    rules:
      - name: After Effects - Intro & Opener
        locations: G:\\Design Unorganized
        filters:
          - extension:
              - aep
              - mogrt
          - name:
              contains:
                - intro
                - opener
        actions:
          - move: G:\\Organized\\After Effects - Intro & Opener\\

The intended workflow is: a user who has been running FileOrganizer can hand
their `organize_rules.yaml` to a teammate (or to organize-cli directly)
without re-deriving the taxonomy from prompts.

Hard-coded extension hints + the existing `organize_run.CATEGORY_ALIASES`
dictionary are the two structured-rule sources we have today. A future
follow-up can fold in `corrections.json` (NEXT-7) once that lands.

PyYAML is optional. When it's installed the emitter uses it; otherwise we
hand-roll deterministic YAML. The output of either path round-trips through
`yaml.safe_load` if PyYAML is available downstream.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Iterable, Optional

# Defensive imports — the module is loadable even if these aren't.
try:
    from classify_design import CATEGORIES, _CATEGORY_SET  # type: ignore[import]
except Exception:
    CATEGORIES = []   # type: ignore[assignment]
    _CATEGORY_SET = frozenset()

try:
    from organize_run import CATEGORY_ALIASES  # type: ignore[import]
except Exception:
    CATEGORY_ALIASES = {}  # type: ignore[assignment]

_HAS_PYYAML = importlib.util.find_spec("yaml") is not None


# ── Per-category extension hints ──────────────────────────────────────────
#
# Static map from canonical category name → list of file extensions that are
# strongly indicative of that category. Kept tight; the LLM-derived rules
# carry the heavy lifting and we only emit hints we'd defend without an LLM.
# Categories not in this map get an empty extension filter (name filter only).

_CATEGORY_EXT_HINTS: dict[str, list[str]] = {
    "After Effects - Intro & Opener": ["aep", "mogrt"],
    "After Effects - Logo Reveal": ["aep"],
    "After Effects - Lower Thirds": ["aep", "mogrt"],
    "After Effects - Title & Typography": ["aep", "mogrt"],
    "After Effects - Transition Pack": ["aep", "mogrt"],
    "After Effects - Other": ["aep"],
    "Premiere Pro - Motion Graphics (.mogrt)": ["mogrt"],
    "Premiere Pro - Templates": ["prproj"],
    "Premiere Pro - Other": ["prproj"],
    "Photoshop - Smart Objects & Templates": ["psd", "psb"],
    "Photoshop - Mockups": ["psd"],
    "Photoshop - Patterns & Textures": ["pat", "psd"],
    "Photoshop - Brushes": ["abr"],
    "Photoshop - Actions & Presets": ["atn"],
    "Photoshop - Styles & Layer Effects": ["asl", "psd"],
    "Photoshop - Other": ["psd"],
    "Illustrator - Vectors & Assets": ["ai", "eps", "svg"],
    "Illustrator - Brushes & Swatches": ["ai"],
    "Illustrator - Icons & UI Kits": ["ai", "svg"],
    "Illustrator - Other": ["ai"],
    "Color Grading & LUTs": ["cube", "3dl", "look"],
    "Lightroom - Presets & Profiles": ["xmp", "lrtemplate", "dng"],
    "Fonts & Typography": ["ttf", "otf", "ttc", "woff", "woff2"],
    "Procreate - Brushes & Stamps": ["brushset"],
    "Procreate - Templates & Canvases": ["procreate"],
    "Print - Flyers & Posters": ["psd", "ai", "indd", "pdf"],
    "Print - Business Cards & Stationery": ["psd", "ai", "indd"],
    "Print - Brochures & Books": ["psd", "ai", "indd", "pdf"],
    "Print - Invitations & Events": ["psd", "ai"],
    "Print - Social Media Graphics": ["psd"],
    "Print - Other": ["psd", "ai"],
    "Stock Music & Audio": ["mp3", "wav", "flac"],
    "Sound Effects & SFX": ["wav", "mp3"],
    "Stock Footage - Abstract & VFX": ["mp4", "mov"],
    "Stock Footage - Aerial & Drone": ["mp4", "mov"],
    "Stock Footage - Green Screen": ["mp4", "mov"],
    "Stock Footage - General": ["mp4", "mov", "mxf"],
    "Stock Footage - Nature & Landscape": ["mp4", "mov"],
    "Stock Footage - People & Lifestyle": ["mp4", "mov"],
    "Stock Footage - Timelapse": ["mp4", "mov"],
    "Stock Photos - Food & Drink": ["jpg", "jpeg"],
    "Stock Photos - General": ["jpg", "jpeg"],
    "Stock Photos - Nature & Outdoors": ["jpg", "jpeg"],
    "Plugins & Extensions": ["zxp", "jsxbin", "jsx", "aex"],
    "3D - Materials & Textures": ["mtl", "blend", "c4d"],
    "3D - Models & Objects": ["obj", "fbx", "blend", "c4d", "stl"],
    "3D - Scenes & Environments": ["blend", "c4d", "fbx"],
    "Web Template": ["html", "css", "js"],
    "UI Resources & Icon Sets": ["svg", "ai", "ico", "iconpackage"],
    "Cinematic FX & Overlays": ["mp4", "mov"],
    "VFX & Compositing": ["aep", "nk", "mov"],
    "Video Editing - General": ["mp4", "mov", "mxf"],
    "Software & Utilities": ["exe", "msi", "zip"],
    "Tutorial & Education": ["mp4", "pdf"],
}

# Categories that MUST NOT appear as a destination (they are routing-only).
_EXCLUDE_CATEGORIES: frozenset[str] = frozenset({"_Review", "_Skip"})


def _alias_keywords_for(category: str) -> list[str]:
    """Reverse-lookup all aliases that route TO this canonical category.

    Each alias is split into individual words; we only keep the longer (≥4
    char) tokens since organize-cli's ``name.contains`` filter is a substring
    match and short tokens like 'and' would over-match.
    """
    aliases = [
        alias for alias, target in CATEGORY_ALIASES.items()
        if target == category and target in _CATEGORY_SET
    ]
    keywords: list[str] = []
    seen: set[str] = set()
    for alias in aliases:
        for token in _normalize_tokens(alias):
            lower = token.lower()
            if lower in seen:
                continue
            if len(lower) < 4:
                continue
            seen.add(lower)
            keywords.append(lower)
    return keywords


def _normalize_tokens(text: str) -> list[str]:
    """Split a category-style label into clean word tokens (no punctuation)."""
    out: list[str] = []
    word = []
    for ch in text:
        if ch.isalnum():
            word.append(ch)
        else:
            if word:
                out.append("".join(word))
                word = []
    if word:
        out.append("".join(word))
    return out


def _action_dest(dest_root: str, category: str) -> str:
    """Build the move destination for a category folder under dest_root."""
    root = str(Path(dest_root))
    sep = "\\" if "\\" in root or len(root) > 1 and root[1] == ":" else "/"
    return f"{root.rstrip(sep)}{sep}{category}{sep}"


def build_organize_cli_rules(
    dest_root: str = "G:\\Organized",
    *,
    source: str = "G:\\Design Unorganized",
    categories: Optional[Iterable[str]] = None,
) -> list[dict]:
    """Build the rule list (one rule per canonical category).

    Returns a Python list of dicts that, when wrapped under a top-level
    ``rules:`` key, are valid organize-cli configuration.
    """
    cats: Iterable[str] = categories if categories is not None else CATEGORIES
    rules: list[dict] = []
    for category in cats:
        if category in _EXCLUDE_CATEGORIES:
            continue
        if _CATEGORY_SET and category not in _CATEGORY_SET:
            continue
        filters: list[dict] = []
        exts = _CATEGORY_EXT_HINTS.get(category)
        if exts:
            filters.append({"extension": list(exts)})
        keywords = _alias_keywords_for(category)
        if keywords:
            filters.append({"name": {"contains": keywords}})
        if not filters:
            # No structured signal for this category — emit a name-only rule
            # using the category's own tokens as a last-resort hint.
            tokens = [
                t.lower() for t in _normalize_tokens(category)
                if len(t) >= 4
            ]
            if tokens:
                filters.append({"name": {"contains": tokens}})
        if not filters:
            continue
        rules.append({
            "name": category,
            "locations": source,
            "filters": filters,
            "actions": [
                {"move": _action_dest(dest_root, category)},
            ],
        })
    return rules


# ── YAML emitter ──────────────────────────────────────────────────────────


def render_yaml(rules: list[dict]) -> str:
    """Return YAML text for the rule set. Uses PyYAML if installed."""
    payload = {"rules": rules}
    if _HAS_PYYAML:
        import yaml  # type: ignore
        return yaml.safe_dump(
            payload,
            sort_keys=False,
            allow_unicode=True,
            default_flow_style=False,
            width=4096,
        )
    return _hand_render(payload)


def _hand_render(payload: dict) -> str:
    """Deterministic YAML emitter for the narrow subset we produce.

    Only handles the structures build_organize_cli_rules emits:
      - top-level mapping
      - list of mappings
      - mappings whose values are str / list[str] / list[mapping] / mapping
    """
    rules = payload.get("rules", [])
    out: list[str] = ["rules:"]
    if not rules:
        out[-1] = "rules: []"
        return "\n".join(out) + "\n"
    for rule in rules:
        first = True
        for key, value in rule.items():
            if first:
                prefix = "  - "
                first = False
            else:
                prefix = "    "
            out.extend(_render_kv(prefix, key, value))
    return "\n".join(out) + "\n"


def _render_kv(prefix: str, key: str, value, indent: str = "      ") -> list[str]:
    """Render one key/value pair for the hand-rolled emitter."""
    lines: list[str] = []
    if isinstance(value, str):
        lines.append(f"{prefix}{key}: {_yaml_scalar(value)}")
    elif isinstance(value, list):
        lines.append(f"{prefix}{key}:")
        for entry in value:
            if isinstance(entry, dict):
                first = True
                for subkey, subval in entry.items():
                    p = f"{indent}- " if first else f"{indent}  "
                    first = False
                    lines.extend(_render_kv(p, subkey, subval, indent + "  "))
            else:
                lines.append(f"{indent}- {_yaml_scalar(str(entry))}")
    elif isinstance(value, dict):
        lines.append(f"{prefix}{key}:")
        for subkey, subval in value.items():
            lines.extend(_render_kv(f"{indent}", subkey, subval, indent + "  "))
    else:
        lines.append(f"{prefix}{key}: {_yaml_scalar(str(value))}")
    return lines


def _yaml_scalar(value: str) -> str:
    """Quote a scalar when it contains characters that confuse YAML parsers."""
    needs_quote = any(ch in value for ch in (":", "#", "\n", "{", "}", "[", "]"))
    if needs_quote or value != value.strip():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return value


def export(
    output: Optional[str] = None,
    *,
    dest_root: str = "G:\\Organized",
    source: str = "G:\\Design Unorganized",
) -> str:
    """Convenience helper: build rules + render YAML + (optionally) write to disk.

    Returns the YAML text. When ``output`` is provided, the text is also
    written to that path (UTF-8, with a trailing newline).
    """
    rules = build_organize_cli_rules(dest_root=dest_root, source=source)
    text = render_yaml(rules)
    if output:
        Path(output).write_text(text, encoding="utf-8")
    return text
