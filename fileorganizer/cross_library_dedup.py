"""Cross-library folder fingerprinting and guarded duplicate actions.

The ordinary folder cache deliberately uses cheap metadata.  Cross-library
deduplication needs a stronger identity, so this module hashes every regular
file and folds sorted ``relative_path|sha256`` records into a folder SHA-256.
The action helpers never trust a stale scan: the selected source and keeper
are rehashed immediately before a merge or archive operation.
"""

from __future__ import annotations

import hashlib
import os
from collections import defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from pathlib import Path

from fileorganizer.path_safety import (
    PathSafetyError,
    is_within,
    validate_move,
    validate_path,
)


HASH_CHUNK_BYTES = 1_048_576
DEFAULT_SCAN_DEPTH = 1
DEFAULT_MAX_FOLDERS = 25_000


class CrossLibraryScanCancelled(Exception):
    """Raised when a caller cancels a cross-library scan."""


@dataclass(frozen=True)
class FolderFingerprint:
    """Complete content identity and bounded scan statistics for one folder."""

    path: str
    library_root: str
    fingerprint: str
    file_count: int
    total_bytes: int
    modified_ns: int

    @property
    def name(self) -> str:
        return os.path.basename(self.path.rstrip(os.sep))

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CrossLibraryDuplicateGroup:
    """A complete-content duplicate group spanning at least two roots."""

    fingerprint: str
    members: tuple[FolderFingerprint, ...]

    @property
    def library_roots(self) -> tuple[str, ...]:
        return tuple(sorted({member.library_root for member in self.members}))

    @property
    def total_bytes(self) -> int:
        return sum(member.total_bytes for member in self.members)

    def member(self, path: str) -> FolderFingerprint:
        """Return the member matching *path*, using canonical case rules."""
        wanted = _canonical_path(path)
        for member in self.members:
            if _canonical_path(member.path) == wanted:
                return member
        raise ValueError(f"path is not a member of fingerprint group: {path!r}")

    def to_dict(self) -> dict:
        return {
            "fingerprint": self.fingerprint,
            "library_roots": list(self.library_roots),
            "total_bytes": self.total_bytes,
            "members": [member.to_dict() for member in self.members],
        }


@dataclass(frozen=True)
class CrossLibraryActionResult:
    """Result of one explicit merge, keep, or archive decision."""

    action: str
    source: str
    destination: str = ""
    status: str = "completed"
    message: str = ""
    moved_files: int = 0
    skipped_files: int = 0
    manifest: tuple[dict, ...] = ()

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["manifest"] = list(self.manifest)
        return payload


def _canonical_path(path: str | os.PathLike[str]) -> str:
    """Normalize a path for comparisons without following missing leaves."""
    return os.path.normcase(os.path.normpath(os.path.realpath(os.fspath(path))))


def _display_path(path: str | os.PathLike[str]) -> str:
    """Normalize a path for UI/report output while preserving its casing."""
    return os.path.normpath(os.path.realpath(os.fspath(path)))


def _normalise_roots(roots: Iterable[str | os.PathLike[str]]) -> list[str]:
    """Validate, deduplicate, and de-overlap readable library roots."""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_root in roots:
        if not str(raw_root).strip():
            continue
        root = _display_path(os.path.abspath(os.path.normpath(os.fspath(raw_root))))
        if not os.path.isdir(root):
            raise ValueError(f"library root is not an existing directory: {raw_root!r}")
        if os.path.islink(root):
            raise PathSafetyError("library root cannot be a symlink or reparse point")
        canonical = _canonical_path(root)
        if canonical in seen:
            continue
        seen.add(canonical)
        normalized.append(canonical)

    # A nested root is not an independent library.  Ignoring it prevents the
    # same physical folder from being reported as a cross-root duplicate.
    normalized.sort(key=lambda value: (len(value), value))
    roots_out: list[str] = []
    for root in normalized:
        if any(is_within(root, parent, allow_equal=False) for parent in roots_out):
            continue
        roots_out.append(root)
    return roots_out


def _iter_candidate_folders(root: str, depth: int):
    """Yield non-symlink directories below *root* up to *depth* levels."""
    root_depth = len(Path(root).parts)
    for dirpath, dirnames, _filenames in os.walk(root, topdown=True, followlinks=False):
        dirnames[:] = sorted(
            name for name in dirnames
            if not os.path.islink(os.path.join(dirpath, name))
        )
        current_depth = len(Path(dirpath).parts) - root_depth
        if current_depth >= depth:
            dirnames[:] = []
        if current_depth >= 1 and current_depth <= depth:
            yield dirpath


def _hash_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for chunk in iter(lambda: stream.read(HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_folder_fingerprint(
    folder_path: str | os.PathLike[str],
    *,
    library_root: str | os.PathLike[str] = "",
    progress_cb: Callable[[str], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> FolderFingerprint | None:
    """Hash every regular file below *folder_path*.

    A folder is omitted when any file cannot be read, rather than producing a
    partial identity that could cause an unsafe merge.  Symlink/reparse files
    and directories are ignored.  ``progress_cb`` receives bounded path
    messages and ``cancel_cb`` may stop a long external-drive scan.
    """
    root = _display_path(os.path.abspath(os.path.normpath(os.fspath(folder_path))))
    if not os.path.isdir(root) or os.path.islink(root):
        return None
    owner = _display_path(library_root) if library_root else root

    entries: list[tuple[str, str, int, int]] = []
    try:
        for dirpath, dirnames, filenames in os.walk(root, topdown=True, followlinks=False):
            if cancel_cb and cancel_cb():
                raise CrossLibraryScanCancelled()
            dirnames[:] = sorted(
                name for name in dirnames
                if not os.path.islink(os.path.join(dirpath, name))
            )
            for filename in sorted(filenames):
                if cancel_cb and cancel_cb():
                    raise CrossLibraryScanCancelled()
                path = os.path.join(dirpath, filename)
                if os.path.islink(path):
                    continue
                try:
                    stat = os.stat(path, follow_symlinks=False)
                    if not os.path.isfile(path):
                        continue
                    relative = os.path.relpath(path, root).replace(os.sep, "/")
                    if progress_cb:
                        progress_cb(f"Hashing {path}")
                    digest = _hash_file(path)
                    entries.append((relative, digest, int(stat.st_size), int(stat.st_mtime_ns)))
                except (OSError, PermissionError):
                    # A partial hash is never safe to compare across libraries.
                    return None
    except (OSError, PermissionError):
        return None

    if not entries:
        return None

    digest = hashlib.sha256()
    for relative, file_hash, _size, _mtime_ns in sorted(entries):
        digest.update(f"{relative}|{file_hash}\n".encode("utf-8"))
    return FolderFingerprint(
        path=root,
        library_root=owner,
        fingerprint=digest.hexdigest(),
        file_count=len(entries),
        total_bytes=sum(entry[2] for entry in entries),
        modified_ns=max(entry[3] for entry in entries),
    )


def folder_fingerprint(
    folder_path: str | os.PathLike[str],
    **kwargs,
) -> str | None:
    """Return only the complete SHA-256 folder identity."""
    record = compute_folder_fingerprint(folder_path, **kwargs)
    return record.fingerprint if record else None


def scan_cross_library(
    roots: Iterable[str | os.PathLike[str]],
    *,
    depth: int = DEFAULT_SCAN_DEPTH,
    max_folders: int = DEFAULT_MAX_FOLDERS,
    progress_cb: Callable[[str], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> list[CrossLibraryDuplicateGroup]:
    """Find exact folder duplicates whose members belong to distinct roots."""
    if isinstance(depth, bool) or not isinstance(depth, int) or depth < 1:
        raise ValueError("scan depth must be a positive integer")
    if isinstance(max_folders, bool) or not isinstance(max_folders, int) or max_folders < 1:
        raise ValueError("max_folders must be a positive integer")

    library_roots = _normalise_roots(roots)
    by_fingerprint: dict[str, list[FolderFingerprint]] = defaultdict(list)
    scanned = 0
    for library_root in library_roots:
        for folder in _iter_candidate_folders(library_root, depth):
            if cancel_cb and cancel_cb():
                raise CrossLibraryScanCancelled()
            scanned += 1
            if scanned > max_folders:
                raise ValueError(f"cross-library scan exceeded {max_folders} folders")
            record = compute_folder_fingerprint(
                folder,
                library_root=library_root,
                progress_cb=progress_cb,
                cancel_cb=cancel_cb,
            )
            if record:
                by_fingerprint[record.fingerprint].append(record)

    groups: list[CrossLibraryDuplicateGroup] = []
    for fingerprint, members in by_fingerprint.items():
        roots_for_group = {member.library_root for member in members}
        if len(roots_for_group) < 2:
            continue
        groups.append(CrossLibraryDuplicateGroup(
            fingerprint=fingerprint,
            members=tuple(sorted(members, key=lambda item: (item.library_root, item.path))),
        ))
    groups.sort(key=lambda group: (group.members[0].path, group.fingerprint))
    if progress_cb:
        progress_cb(f"Cross-library scan complete: {scanned} folders, {len(groups)} duplicate groups")
    return groups


def _unique_destination(path: str) -> str:
    if not os.path.lexists(path):
        return path
    stem = path
    index = 2
    while index <= 10_000:
        candidate = f"{stem} ({index})"
        if not os.path.lexists(candidate):
            return candidate
        index += 1
    raise PathSafetyError("could not allocate a collision-free archive destination")


def _revalidate_member(group: CrossLibraryDuplicateGroup, path: str) -> FolderFingerprint:
    member = group.member(path)
    current = compute_folder_fingerprint(member.path, library_root=member.library_root)
    if current is None or current.fingerprint != group.fingerprint:
        raise PathSafetyError("duplicate group changed since it was scanned")
    return current


def apply_cross_library_action(
    group: CrossLibraryDuplicateGroup,
    source_path: str,
    *,
    action: str,
    keep_path: str,
    archive_root: str | os.PathLike[str] | None = None,
    log_cb: Callable[[str], None] | None = None,
) -> CrossLibraryActionResult:
    """Apply one explicit group decision after full fingerprint revalidation.

    ``keep`` is intentionally a no-op and records the user's decision.  A
    merge removes only source files proven identical by the shared safe merge
    manifest; archive moves the source into a new child of an existing archive
    root.  Neither operation overwrites a destination.
    """
    if action not in {"keep", "merge", "archive"}:
        raise ValueError("cross-library action must be keep, merge, or archive")
    source = group.member(source_path)
    keeper = group.member(keep_path)
    if _canonical_path(source.path) == _canonical_path(keeper.path):
        if action != "keep":
            raise ValueError("keeper cannot be selected as a merge or archive source")
        return CrossLibraryActionResult("keep", source.path, message="Keeper retained.")

    _revalidate_member(group, source.path)
    _revalidate_member(group, keeper.path)
    if action == "keep":
        return CrossLibraryActionResult("keep", source.path, message="Duplicate retained.")

    # Importing the existing journaled merge helper lazily keeps the scanner
    # usable without importing the full Qt worker module.
    from fileorganizer.workers import safe_merge_move

    manifest: list[dict] = []
    if action == "merge":
        moved, skipped = safe_merge_move(
            source.path,
            keeper.path,
            log_cb=log_cb,
            check_hashes=True,
            manifest=manifest,
        )
        return CrossLibraryActionResult(
            "merge",
            source.path,
            keeper.path,
            moved_files=moved,
            skipped_files=skipped,
            manifest=tuple(manifest),
            message=f"Merged into {keeper.name}; {skipped} identical files removed from the duplicate.",
        )

    if not archive_root:
        raise ValueError("archive action requires an existing archive root")
    approved_archive = validate_path(archive_root)
    if is_within(approved_archive, source.path) or is_within(approved_archive, keeper.path):
        raise PathSafetyError("archive root cannot be inside a duplicate folder")
    destination = _unique_destination(os.path.join(approved_archive, source.name))
    validate_move(source.path, destination)
    moved, skipped = safe_merge_move(
        source.path,
        destination,
        log_cb=log_cb,
        check_hashes=False,
        manifest=manifest,
    )
    return CrossLibraryActionResult(
        "archive",
        source.path,
        destination,
        moved_files=moved,
        skipped_files=skipped,
        manifest=tuple(manifest),
        message=f"Archived duplicate as {destination}.",
    )


__all__ = [
    "CrossLibraryActionResult",
    "CrossLibraryDuplicateGroup",
    "CrossLibraryScanCancelled",
    "FolderFingerprint",
    "apply_cross_library_action",
    "compute_folder_fingerprint",
    "folder_fingerprint",
    "scan_cross_library",
]
