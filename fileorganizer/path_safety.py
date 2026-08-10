"""Canonical path and mutation-boundary checks for filesystem operations.

Every user- or persisted-data-driven move must validate both the resolved
source and destination immediately before it mutates the filesystem.  This
module deliberately has no UI or planner dependencies so command-line,
watcher, and PyQt callers can share the same policy.
"""

from __future__ import annotations

import os
import stat


class PathSafetyError(ValueError):
    """Raised when a filesystem operation would cross a safety boundary."""


def absolute_path(path: str | os.PathLike[str]) -> str:
    """Return a normalized absolute path without resolving symlinks."""
    try:
        value = os.fspath(path)
    except TypeError as exc:
        raise PathSafetyError("path must be a string or path-like value") from exc
    if not isinstance(value, str) or not value.strip():
        raise PathSafetyError("path must be a non-empty string")
    if "\x00" in value:
        raise PathSafetyError("path contains a NUL character")
    return os.path.abspath(os.path.normpath(value))


def canonical_path(path: str | os.PathLike[str]) -> str:
    """Return the case-normalized real path, including resolved parents."""
    try:
        resolved = os.path.realpath(absolute_path(path))
    except (OSError, RuntimeError) as exc:
        raise PathSafetyError(f"cannot resolve path {path!r}: {exc}") from exc
    return os.path.normcase(os.path.normpath(resolved))


def is_within(path: str | os.PathLike[str], root: str | os.PathLike[str], *,
              allow_equal: bool = False) -> bool:
    """Return whether *path* is contained by *root* after canonicalization."""
    try:
        child = canonical_path(path)
        parent = canonical_path(root)
        common = os.path.commonpath((child, parent))
    except (OSError, RuntimeError, ValueError, PathSafetyError):
        return False
    if common != parent:
        return False
    return allow_equal or child != parent


def _ancestors(path: str) -> list[str]:
    current = absolute_path(path)
    out: list[str] = []
    while True:
        out.append(current)
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent
    return out


def has_reparse_component(path: str | os.PathLike[str]) -> bool:
    """Return whether an existing component is a symlink/junction/reparse point."""
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x0400)
    for component in _ancestors(path):
        try:
            info = os.lstat(component)
        except FileNotFoundError:
            continue
        except OSError:
            # The mutation will fail closed in ``validate_move`` if the path
            # cannot be inspected; do not silently treat an inaccessible
            # component as safe.
            return True
        if os.path.islink(component):
            return True
        if getattr(info, "st_file_attributes", 0) & reparse_flag:
            return True
    return False


def is_protected_path(path: str | os.PathLike[str]) -> bool:
    """Apply the configured protected-path policy to every path component."""
    try:
        from fileorganizer.config import is_protected
    except Exception as exc:  # pragma: no cover - import failure is fail-closed
        raise PathSafetyError("protected-path policy is unavailable") from exc

    for component in _ancestors(path):
        if is_protected(component):
            return True
    return False


def source_signature(path: str | os.PathLike[str]) -> dict:
    """Capture filesystem identity used to bind persisted operations."""
    value = absolute_path(path)
    info = os.stat(value, follow_symlinks=False)
    return {
        'st_dev': int(getattr(info, 'st_dev', 0)),
        'st_ino': int(getattr(info, 'st_ino', 0)),
        'size': int(info.st_size),
        'mtime_ns': int(getattr(info, 'st_mtime_ns', int(info.st_mtime * 1_000_000_000))),
        'is_file': bool(os.path.isfile(value)),
        'is_dir': bool(os.path.isdir(value)),
    }


def validate_source_signature(path: str | os.PathLike[str], expected: dict) -> None:
    """Fail closed when a persisted operation has no matching source identity."""
    if not isinstance(expected, dict) or not expected:
        raise PathSafetyError("persisted operation has no source identity metadata")
    try:
        actual = source_signature(path)
    except OSError as exc:
        raise PathSafetyError(f"cannot inspect source identity: {exc}") from exc
    for key in ('st_dev', 'st_ino', 'size', 'mtime_ns', 'is_file', 'is_dir'):
        if key in expected and expected[key] != actual[key]:
            raise PathSafetyError(f"source identity changed ({key})")


def validate_path(
    path: str | os.PathLike[str],
    *,
    root: str | os.PathLike[str] | None = None,
    require_exists: bool = True,
    reject_reparse: bool = True,
    check_protected: bool = True,
) -> str:
    """Validate a single path for non-move reads/writes and return its real path."""
    absolute = absolute_path(path)
    resolved = canonical_path(absolute)
    if root is not None and not is_within(resolved, root):
        raise PathSafetyError(f"path escapes approved root: {path!r}")
    if require_exists and not os.path.lexists(absolute):
        raise PathSafetyError(f"path does not exist: {path!r}")
    if reject_reparse and has_reparse_component(absolute):
        raise PathSafetyError("path contains a symlink/reparse point")
    if check_protected and is_protected_path(absolute):
        raise PathSafetyError("path is protected")
    return resolved


def validate_move(
    src: str | os.PathLike[str],
    dest: str | os.PathLike[str],
    *,
    source_root: str | os.PathLike[str] | None = None,
    dest_root: str | os.PathLike[str] | None = None,
    allow_existing_dest: bool = False,
    require_source: bool = True,
    reject_reparse: bool = True,
    check_protected: bool = True,
) -> tuple[str, str]:
    """Validate one move and return canonical source/destination paths.

    Missing destination leaves are allowed, but their existing parents are
    resolved and checked.  A caller that intentionally replaces an existing
    destination must opt in explicitly; the default is no-overwrite.
    """
    src_abs = absolute_path(src)
    dest_abs = absolute_path(dest)
    src_real = canonical_path(src_abs)
    dest_real = canonical_path(dest_abs)

    if source_root is not None and not is_within(src_real, source_root):
        raise PathSafetyError(f"source escapes approved root: {src!r}")
    if dest_root is not None and not is_within(dest_real, dest_root):
        raise PathSafetyError(f"destination escapes approved root: {dest!r}")
    if src_real == dest_real:
        raise PathSafetyError("source and destination are the same path")

    source_exists = os.path.lexists(src_abs)
    if require_source and not source_exists:
        raise PathSafetyError(f"source does not exist: {src!r}")
    if source_exists and os.path.isdir(src_abs) and is_within(dest_real, src_real):
        raise PathSafetyError("destination is inside the source directory")
    if os.path.lexists(dest_abs) and not allow_existing_dest:
        raise PathSafetyError(f"destination already exists: {dest!r}")

    if reject_reparse and (has_reparse_component(src_abs) or has_reparse_component(dest_abs)):
        raise PathSafetyError("source or destination contains a symlink/reparse point")
    if check_protected and (is_protected_path(src_abs) or is_protected_path(dest_abs)):
        raise PathSafetyError("source or destination is protected")
    return src_real, dest_real


def validate_tree_pair(src_root: str | os.PathLike[str], dest_root: str | os.PathLike[str]) -> tuple[str, str]:
    """Validate two roots for watcher/copy use and reject overlapping trees."""
    source = canonical_path(src_root)
    dest = canonical_path(dest_root)
    if source == dest or is_within(dest, source) or is_within(source, dest):
        raise PathSafetyError("source and destination trees overlap")
    if has_reparse_component(src_root) or has_reparse_component(dest_root):
        raise PathSafetyError("source or destination root contains a symlink/reparse point")
    if is_protected_path(src_root) or is_protected_path(dest_root):
        raise PathSafetyError("source or destination root is protected")
    return source, dest
