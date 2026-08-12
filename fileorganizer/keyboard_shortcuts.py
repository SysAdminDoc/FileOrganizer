"""Validated persistence for the legacy desktop keyboard shortcuts."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Mapping

from fileorganizer.config import _APP_DATA_DIR


SHORTCUTS_FILE = Path(_APP_DATA_DIR) / "keyboard_shortcuts.json"

DEFAULT_SHORTCUTS: dict[str, dict[str, str]] = {
    "open_source": {"label": "Choose source folder", "default": "Ctrl+O"},
    "scan": {"label": "Scan", "default": "F5"},
    "apply": {"label": "Apply selected plan", "default": "Ctrl+Shift+O"},
    "preview": {"label": "Preview selected plan", "default": "Ctrl+P"},
    "undo": {"label": "Open move history / undo", "default": "Ctrl+Z"},
    "open_destination": {"label": "Open destination", "default": "Ctrl+Shift+E"},
}

_MODIFIERS = {"Alt", "Ctrl", "Meta", "Shift"}
_KEY_RE = re.compile(
    r"^(?:[A-Za-z0-9]|F(?:[1-9]|1[0-2])|Return|Enter|Space|Tab|Esc|Escape|"
    r"Backspace|Delete|Home|End|PageUp|PageDown|Up|Down|Left|Right|Insert|"
    r"Plus|Minus|Comma|Period)$"
)


def normalize_shortcut(value: object, fallback: str = "") -> str:
    """Return a portable Qt shortcut string or the supplied fallback."""
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 48 or any(ord(char) < 32 for char in text):
        return fallback
    parts = text.split("+")
    if not parts or parts[-1] == "" or any(part == "" for part in parts):
        return fallback
    modifiers = parts[:-1]
    if any(modifier not in _MODIFIERS for modifier in modifiers):
        return fallback
    if len(modifiers) != len(set(modifiers)) or not _KEY_RE.fullmatch(parts[-1]):
        return fallback
    return "+".join(parts)


def load_shortcuts() -> dict[str, str]:
    """Load known shortcuts and ignore malformed or unknown JSON entries."""
    result = {
        key: values["default"] for key, values in DEFAULT_SHORTCUTS.items()
    }
    try:
        raw = json.loads(SHORTCUTS_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return result
    if not isinstance(raw, dict):
        return result
    for key, values in DEFAULT_SHORTCUTS.items():
        if key in raw:
            result[key] = normalize_shortcut(raw[key], values["default"])
    return result


def save_shortcuts(values: Mapping[str, object]) -> dict[str, str]:
    """Normalize and atomically persist known shortcut overrides."""
    normalized = {
        key: normalize_shortcut(
            values[key] if key in values else spec["default"], spec["default"]
        )
        for key, spec in DEFAULT_SHORTCUTS.items()
    }
    payload = json.dumps(normalized, indent=2, ensure_ascii=False) + "\n"
    SHORTCUTS_FILE.parent.mkdir(parents=True, exist_ok=True)
    temporary = SHORTCUTS_FILE.with_name(f".{SHORTCUTS_FILE.name}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(temporary, SHORTCUTS_FILE)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return normalized


__all__ = [
    "DEFAULT_SHORTCUTS",
    "SHORTCUTS_FILE",
    "load_shortcuts",
    "normalize_shortcut",
    "save_shortcuts",
]
