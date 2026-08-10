"""Canonical path and mutation-boundary checks for filesystem operations.

Every user- or persisted-data-driven move must validate both the resolved
source and destination immediately before it mutates the filesystem.  This
module deliberately has no UI or planner dependencies so command-line,
watcher, and PyQt callers can share the same policy.
"""

from __future__ import annotations

import os
import ntpath
import re
import stat
import string


class PathSafetyError(ValueError):
    """Raised when a filesystem operation would cross a safety boundary."""


_RENAME_FIELD = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_RENAME_FORMAT_SPEC = re.compile(
    r"^[<>=^+\- 0#]*\d*(?:\.\d+)?[bcdeEfFgGnosxX%]*$"
)
_WINDOWS_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
_RENAME_INVALID_LITERAL = set('<>:"|?*\x00')


def _is_windows_rooted(path: str) -> bool:
    """Recognize Windows rooted/drive/UNC paths on every host platform."""
    drive, _ = ntpath.splitdrive(path)
    return bool(drive) or path.startswith(("/", "\\")) or ntpath.isabs(path)


def _validate_relative_rename_path(path: str) -> str:
    """Validate a formatted rename path as safe relative Windows components."""
    if not isinstance(path, str) or not path.strip():
        raise PathSafetyError("rename destination must be a non-empty path")
    if "{" in path or "}" in path:
        raise PathSafetyError("rename destination contains an unexpanded template")
    if len(path) > 1024:
        raise PathSafetyError("rename destination is too long")
    if any(ord(char) < 32 for char in path) or "\x00" in path:
        raise PathSafetyError("rename destination contains a control character")
    if _is_windows_rooted(path):
        raise PathSafetyError("rename destination must be relative")

    components = re.split(r"[\\/]", path)
    if not components or any(not component for component in components):
        raise PathSafetyError("rename destination contains an empty path component")
    for component in components:
        if component in {".", ".."}:
            raise PathSafetyError("rename destination contains a dot path component")
        if component.endswith((".", " ")):
            raise PathSafetyError("rename destination has a trailing dot or space")
        stem = component.rstrip(" .").split(".", 1)[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise PathSafetyError("rename destination uses a reserved Windows name")
    return path


def validate_rename_template(
    template: str,
    allowed_fields: set[str] | frozenset[str] | tuple[str, ...],
) -> str:
    """Validate a tokenized rename template before any filesystem work.

    Templates may contain forward or backward separators to create nested
    destination folders, but every component must remain relative and safe.
    Only simple, explicitly allowed fields and numeric format specifications
    are accepted; attribute/index traversal and conversions are rejected.
    """
    if not isinstance(template, str) or not template.strip():
        raise PathSafetyError("rename template must be a non-empty string")
    if len(template) > 1024:
        raise PathSafetyError("rename template is too long")
    if any(ord(char) < 32 for char in template) or "\x00" in template:
        raise PathSafetyError("rename template contains a control character")
    if _is_windows_rooted(template):
        raise PathSafetyError("rename template must be relative")

    fields = set(allowed_fields)
    formatter = string.Formatter()
    static_parts: list[str] = []
    try:
        parsed = list(formatter.parse(template))
    except (TypeError, ValueError) as exc:
        raise PathSafetyError(f"invalid rename template: {exc}") from exc

    for literal, field_name, format_spec, conversion in parsed:
        if any(char in _RENAME_INVALID_LITERAL for char in literal):
            raise PathSafetyError("rename template contains an invalid filename character")
        static_parts.append(literal)
        if field_name is None:
            continue
        if not _RENAME_FIELD.fullmatch(field_name) or field_name not in fields:
            raise PathSafetyError(f"rename template field is not allowed: {field_name!r}")
        if conversion is not None:
            raise PathSafetyError("rename template conversions are not allowed")
        if "{" in format_spec or "}" in format_spec \
                or not _RENAME_FORMAT_SPEC.fullmatch(format_spec):
            raise PathSafetyError("rename template format specification is not allowed")
        static_parts.append("__field__")

    # Validate the literal shape with fields replaced by a safe component so
    # ../, rooted paths, empty components, and reserved literal names fail
    # before any user metadata is formatted.
    _validate_relative_rename_path("".join(static_parts))
    return template


def resolve_rename_destination(
    dest_root: str | os.PathLike[str],
    relative_path: str,
) -> str:
    """Resolve a formatted rename path and enforce containment under root."""
    _validate_relative_rename_path(relative_path)
    root = absolute_path(dest_root)
    candidate = absolute_path(os.path.join(root, relative_path))
    if not is_within(candidate, root):
        raise PathSafetyError("rename destination escapes its root")
    return candidate


def unique_rename_destination(
    candidate: str,
    source: str | os.PathLike[str],
    *,
    max_attempts: int = 10000,
) -> str:
    """Return a no-overwrite candidate, suffixing collisions as ``(2)``."""
    source_abs = absolute_path(source)
    candidate_abs = absolute_path(candidate)
    if os.path.normcase(candidate_abs) == os.path.normcase(source_abs):
        return candidate_abs
    if not os.path.lexists(candidate_abs):
        return candidate_abs

    stem, extension = os.path.splitext(candidate_abs)
    for index in range(2, max_attempts + 2):
        alternate = f"{stem} ({index}){extension}"
        if not os.path.lexists(alternate):
            return alternate
    raise PathSafetyError("could not find a collision-free rename destination")


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
