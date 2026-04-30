"""Size-guarded psd_tools wrapper — N-13 PSD parser hardening.

Maliciously crafted PSDs can trigger psd_tools parser bugs (excessive memory
allocation, infinite recursion, integer overflow on layer counts).  In-process
parsing without a size guard means a single bad file can crash the whole GUI.

This module provides one helper:

    safe_psd_open(path) -> PSDImage | None

It returns None instead of raising if:
    - psd_tools is not installed
    - the file is missing or unreadable
    - the file exceeds PSD_PARSE_LIMIT_BYTES (default 200 MB)
    - psd_tools raises any exception during parse

Callers should treat None as "skip this file" — never as "the file is fine".

Subprocess isolation is the more conservative option (kill the subprocess on
hang or crash) but adds significant overhead for the common small-PSD case
that is FileOrganizer's bread and butter.  The size guard plus exception
isolation strikes the right balance for now; subprocess mode can land later
under a `--strict-psd` flag if/when a real exploit surfaces.
"""
from __future__ import annotations

import os
from typing import Optional


# Tunable.  PSDs larger than this are skipped entirely; the layer-tree parse
# is O(layers) and 1 GB+ files have hit OOM during real organize runs.
PSD_PARSE_LIMIT_BYTES = 200 * 1024 * 1024


def safe_psd_open(path: str,
                  size_limit: int = PSD_PARSE_LIMIT_BYTES) -> Optional[object]:
    """Open `path` as a PSDImage, or return None on any failure.

    Always returns None when psd_tools is not installed; the caller's
    HAS_PSD_TOOLS check normally short-circuits before reaching this, but
    the module is safe to import regardless.
    """
    try:
        from psd_tools import PSDImage
    except Exception:
        return None
    try:
        if not os.path.isfile(path):
            return None
        if os.path.getsize(path) > size_limit:
            return None
    except OSError:
        return None
    try:
        return PSDImage.open(path)
    except Exception:
        return None


def file_too_large(path: str,
                   size_limit: int = PSD_PARSE_LIMIT_BYTES) -> bool:
    """True iff `path` exists and is larger than `size_limit`.  Used by
    callers that want to log "skipped: too large" rather than silently None.
    """
    try:
        return os.path.isfile(path) and os.path.getsize(path) > size_limit
    except OSError:
        return False
