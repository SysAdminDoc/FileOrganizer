"""Safe routing helpers for executable payloads discovered in archives."""

from __future__ import annotations

import os
import re
from pathlib import Path


QUARANTINE_EXTENSIONS = frozenset({
    ".exe", ".bat", ".ps1", ".scr", ".cmd", ".msi", ".lnk", ".vbs",
})
_INVALID_COMPONENTS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def is_quarantine_member(name: str) -> bool:
    """Return whether an archive member is an executable/script payload."""
    normalized = str(name or "").replace("\\", "/")
    if normalized.rstrip().endswith("/"):
        return False
    return Path(normalized).suffix.casefold() in QUARANTINE_EXTENSIONS


def safe_quarantine_component(value: str, fallback: str = "archive") -> str:
    """Make a single Windows-safe folder component, never a relative path."""
    component = _INVALID_COMPONENTS.sub("_", os.path.basename(str(value or "")))
    component = component.strip(" .")[:120]
    if not component:
        return fallback
    if component.rstrip(" .").split(".", 1)[0].upper() in _WINDOWS_RESERVED_NAMES:
        component = f"_{component}"
    return component


def quarantine_source_name(archive_name: str) -> str:
    """Return the quarantine folder name for an archive filename."""
    stem = Path(os.path.basename(str(archive_name or ""))).stem
    return safe_quarantine_component(stem)


def quarantine_destination(
    destination_root: str,
    archive_name: str,
    filename: str,
) -> tuple[str, str]:
    """Return ``(<quarantine root>, <file destination>)`` for one archive."""
    approved_root = os.path.abspath(os.fspath(destination_root))
    source_name = quarantine_source_name(archive_name)
    safe_filename = safe_quarantine_component(os.path.basename(filename), "payload")
    quarantine_root = os.path.join(approved_root, "_Quarantine", source_name)
    return quarantine_root, os.path.join(quarantine_root, safe_filename)


__all__ = [
    "QUARANTINE_EXTENSIONS", "is_quarantine_member", "quarantine_destination",
    "quarantine_source_name", "safe_quarantine_component",
]
