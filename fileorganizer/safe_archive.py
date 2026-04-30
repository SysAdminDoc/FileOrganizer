r"""Safe archive extraction primitives — N-13 path-traversal guard.

Untrusted ZIP/RAR/7z archives can ship entries whose names contain `..` or
absolute paths, causing naive extractors to write outside the intended
target directory.  This module exposes one primitive — `safe_extract_path()` —
that resolves an archive entry name against a target root and rejects any
path that escapes.

Used by:
    - L-7 archive content inspection (planned)
    - L-19 executable quarantine on archive scan (planned)
    - Anywhere we call `zipfile.extract*`, `rarfile.extract*`, or
      `py7zr.SevenZipFile.extract*` on untrusted input.

Design notes:
    - We intentionally do NOT call os.path.realpath() on the entry name; it
      would resolve the symlink target on systems where the dest already
      exists, defeating the check.  Instead we work with abspath/normpath of
      the joined string, which is path-only and never touches the FS.
    - The check rejects:
        * absolute entry names (`/etc/passwd`, `C:\Windows\evil.exe`)
        * `..` traversal (`../etc/passwd`, `subdir/../../escape.txt`)
        * UNC roots (`\\server\share\evil.exe`)
        * Drive-letter prefixes that don't match the target
        * Empty / whitespace-only names
"""
from __future__ import annotations

import os
from typing import Iterable


class UnsafeArchiveEntryError(ValueError):
    """Raised when an archive entry would extract outside the target root."""


def _norm(p: str) -> str:
    """abspath + normpath, case-folded on Windows.  No FS calls."""
    return os.path.normcase(os.path.abspath(p))


def safe_extract_path(target_root: str, entry_name: str) -> str:
    """Resolve `entry_name` under `target_root` and validate it stays inside.

    Returns the absolute, normalized path the caller should write to.
    Raises `UnsafeArchiveEntryError` for any path that escapes the target.

    Examples:
        >>> safe_extract_path('/tmp/x', 'docs/readme.txt')
        '/tmp/x/docs/readme.txt'    # (or '\\\\tmp\\\\x\\\\docs\\\\readme.txt' on Win)
        >>> safe_extract_path('/tmp/x', '../etc/passwd')
        Traceback (most recent call last):
            ...
        UnsafeArchiveEntryError: archive entry escapes target root: ...
    """
    if not entry_name or not entry_name.strip():
        raise UnsafeArchiveEntryError("empty archive entry name")

    # Reject absolute paths and UNC roots up front — joining an abs path
    # with a target root drops the target prefix on POSIX and produces
    # surprising paths on Windows.
    if os.path.isabs(entry_name) or entry_name.startswith(('\\\\', '//')):
        raise UnsafeArchiveEntryError(
            f"absolute or UNC archive entry rejected: {entry_name!r}"
        )

    # Reject Windows drive-letter prefixes even when the rest is "relative".
    drive, _ = os.path.splitdrive(entry_name)
    if drive:
        raise UnsafeArchiveEntryError(
            f"drive-letter archive entry rejected: {entry_name!r}"
        )

    target_norm = _norm(target_root)
    candidate   = _norm(os.path.join(target_root, entry_name))

    # The candidate must be the target itself OR live under it as a child.
    # The trailing-sep guard prevents a sibling named `targetX` from
    # passing when target_norm is `/tmp/target`.
    if candidate != target_norm and not candidate.startswith(target_norm + os.sep):
        raise UnsafeArchiveEntryError(
            f"archive entry escapes target root: {entry_name!r} -> {candidate!r}"
        )
    return candidate


def filter_safe_entries(target_root: str,
                        entry_names: Iterable[str]) -> list[tuple[str, str]]:
    """Bulk variant — returns (entry_name, resolved_path) pairs for every
    entry that passes the check.  Unsafe entries are silently dropped; use
    `safe_extract_path` directly if you need to surface the rejection.
    """
    out: list[tuple[str, str]] = []
    for name in entry_names:
        try:
            out.append((name, safe_extract_path(target_root, name)))
        except UnsafeArchiveEntryError:
            continue
    return out
