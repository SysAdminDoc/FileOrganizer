"""Version-aware deduplication (NEXT-21).

When two items share a marketplace ID but have different file counts or
fingerprints, one is likely a newer version. Keeps the one with more files;
archives the other with a reason note.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Tuple

from fileorganizer.path_safety import PathSafetyError, is_within, validate_move, validate_path


@dataclass
class VersionCandidate:
    """A potential version of an asset."""
    path: str
    marketplace_id: str
    file_count: int = 0
    total_bytes: int = 0
    fingerprint: Optional[str] = None
    version_hint: Optional[str] = None
    library_root: str = ""
    modified_ns: int = 0

    @property
    def name(self) -> str:
        return os.path.basename(self.path)


_VERSION_PATTERN = re.compile(
    r'[_\-\s]v?(\d+(?:\.\d+){0,3})'
    r'|[\(\[]v?(\d+(?:\.\d+){0,3})[\)\]]'
    r'|version[_\-\s]?(\d+(?:\.\d+){0,3})',
    re.IGNORECASE,
)

_MARKETPLACE_ID_PATTERN = re.compile(
    r'^(\d{7,10})'
    r'|^VH[_\-]?(\d{5,10})'
    r'|^(\d{8,10})[_\-]'
    r'|_(\d{7,10})$'
    r'|^(?:envato|videohive|themeforest|freepik|shutterstock|'
    r'adobestock|motionarray|filtergrade|creativemarket)[_\-:#]?(\d{5,12})'
)


def extract_marketplace_id(folder_name: str) -> Optional[str]:
    """Extract marketplace ID from folder name."""
    if not isinstance(folder_name, str):
        return None
    m = _MARKETPLACE_ID_PATTERN.search(folder_name)
    if m:
        return next(g for g in m.groups() if g is not None)
    return None


def extract_version_hint(folder_name: str) -> Optional[str]:
    """Extract version number from folder name."""
    if not isinstance(folder_name, str):
        return None
    m = _VERSION_PATTERN.search(folder_name)
    if m:
        return next(g for g in m.groups() if g is not None)
    return None


def find_version_groups(
    items: List[Dict],
    *,
    require_difference: bool = False,
) -> Dict[str, List[VersionCandidate]]:
    """Group items by marketplace ID to find version duplicates.

    Args:
        items: list of dicts with 'path', 'folder_name', and optionally
               'file_count', 'total_bytes', 'fingerprint' keys.

    Returns:
        Dict mapping marketplace_id -> list of VersionCandidates.
        Only groups with 2+ members are returned.  When ``require_difference``
        is true, groups whose members have the same file count and fingerprint
        are excluded because they are exact copies rather than versions.
    """
    groups: Dict[str, List[VersionCandidate]] = {}

    for item in items:
        name = item.get("folder_name", os.path.basename(item.get("path", "")))
        mid = extract_marketplace_id(name)
        if not mid:
            continue

        candidate = VersionCandidate(
            path=item.get("path", ""),
            marketplace_id=mid,
            file_count=item.get("file_count", 0),
            total_bytes=item.get("total_bytes", 0),
            fingerprint=item.get("fingerprint"),
            version_hint=extract_version_hint(name),
            library_root=item.get("library_root", ""),
            modified_ns=item.get("modified_ns", 0),
        )

        if mid not in groups:
            groups[mid] = []
        groups[mid].append(candidate)

    result = {mid: members for mid, members in groups.items() if len(members) >= 2}
    if require_difference:
        result = {
            mid: members for mid, members in result.items()
            if _group_has_version_difference(members)
        }
    return result


def _group_has_version_difference(candidates: List[VersionCandidate]) -> bool:
    """Return true when a same-ID group has meaningful content differences."""
    counts = {candidate.file_count for candidate in candidates}
    fingerprints = {
        candidate.fingerprint for candidate in candidates if candidate.fingerprint
    }
    return len(counts) > 1 or len(fingerprints) > 1


def _version_sort_value(version_hint: Optional[str]) -> float:
    if not version_hint:
        return 0.0
    try:
        parts = version_hint.split(".")
        return sum(float(part) * (1000 ** (3 - index)) for index, part in enumerate(parts[:4]))
    except (TypeError, ValueError, IndexError):
        return 0.0


def pick_best_version(candidates: List[VersionCandidate]) -> Tuple[VersionCandidate, List[VersionCandidate]]:
    """Pick the best version from a group of candidates.

    Strategy: prefer the one with the most files.  Ties use an explicit
    version hint, then total bytes, then a stable path ordering.  The file
    count is deliberately the first signal: a higher ``v2`` label must not
    cause a visibly incomplete folder to replace a fuller version.

    Returns:
        (best, [rest]) where rest are the candidates to archive.
    """
    if not candidates:
        raise ValueError("at least one version candidate is required")

    def sort_key(c: VersionCandidate):
        return (c.file_count, _version_sort_value(c.version_hint), c.total_bytes, c.path)

    sorted_candidates = sorted(candidates, key=sort_key, reverse=True)
    best = sorted_candidates[0]
    rest = sorted_candidates[1:]
    return best, rest


def generate_archive_plan(
    items: List[Dict],
) -> List[Dict]:
    """Generate a plan for archiving older versions.

    Returns list of dicts: {
        'marketplace_id': str,
        'keep': str (path),
        'archive': str (path),
        'reason': str,
    }
    """
    groups = find_version_groups(items, require_difference=True)
    plan = []

    for mid, candidates in groups.items():
        best, rest = pick_best_version(candidates)
        for obsolete in rest:
            plan.append({
                "marketplace_id": mid,
                "keep": best.path,
                "archive": obsolete.path,
                "reason": version_archive_reason(best, obsolete),
            })

    return plan


def version_archive_reason(best: VersionCandidate, obsolete: VersionCandidate) -> str:
    """Explain why *obsolete* is the archive candidate."""
    reason_parts = []
    if best.file_count > obsolete.file_count:
        reason_parts.append(f"more files ({best.file_count} vs {obsolete.file_count})")
    elif best.file_count == obsolete.file_count and best.total_bytes != obsolete.total_bytes:
        reason_parts.append(
            f"different total size ({best.total_bytes} vs {obsolete.total_bytes})"
        )
    if best.version_hint and obsolete.version_hint:
        reason_parts.append(
            f"older version ({obsolete.version_hint} vs {best.version_hint})"
        )
    if best.fingerprint and obsolete.fingerprint and best.fingerprint != obsolete.fingerprint:
        reason_parts.append("different fingerprint")
    return "; ".join(reason_parts) or "duplicate marketplace ID"


def scan_version_groups(
    roots: Iterable[str | os.PathLike[str]],
    *,
    depth: int = 1,
    max_folders: int = 25_000,
    progress_cb: Callable[[str], None] | None = None,
    cancel_cb: Callable[[], bool] | None = None,
) -> Dict[str, List[VersionCandidate]]:
    """Hash library folders and return only same-ID groups that differ."""
    from fileorganizer.cross_library_dedup import scan_library_folders

    records = scan_library_folders(
        roots,
        depth=depth,
        max_folders=max_folders,
        progress_cb=progress_cb,
        cancel_cb=cancel_cb,
    )
    items = [
        {
            "path": record.path,
            "folder_name": record.name,
            "file_count": record.file_count,
            "total_bytes": record.total_bytes,
            "fingerprint": record.fingerprint,
            "library_root": record.library_root,
            "modified_ns": record.modified_ns,
        }
        for record in records
    ]
    return find_version_groups(items, require_difference=True)


@dataclass(frozen=True)
class VersionArchiveResult:
    """Result of archiving one stale version candidate."""

    source: str
    destination: str
    status: str
    reason: str
    moved_files: int = 0
    skipped_files: int = 0
    manifest: tuple[dict, ...] = ()


def _unique_archive_destination(path: str) -> str:
    if not os.path.lexists(path):
        return path
    for index in range(2, 10_002):
        candidate = f"{path} ({index})"
        if not os.path.lexists(candidate):
            return candidate
    raise PathSafetyError("could not allocate a collision-free version archive destination")


def archive_version_candidate(
    keeper: VersionCandidate,
    obsolete: VersionCandidate,
    *,
    archive_root: str | os.PathLike[str],
    reason: str = "older version",
    log_cb: Callable[[str], None] | None = None,
) -> VersionArchiveResult:
    """Archive an obsolete version after revalidating both folder snapshots."""
    if not keeper.fingerprint or not obsolete.fingerprint:
        raise PathSafetyError("version archive requires complete folder fingerprints")
    from fileorganizer.cross_library_dedup import compute_folder_fingerprint

    current_keeper = compute_folder_fingerprint(keeper.path, library_root=keeper.library_root)
    current_obsolete = compute_folder_fingerprint(obsolete.path, library_root=obsolete.library_root)
    if (
        current_keeper is None
        or current_keeper.fingerprint != keeper.fingerprint
        or current_obsolete is None
        or current_obsolete.fingerprint != obsolete.fingerprint
        or current_obsolete.file_count != obsolete.file_count
    ):
        raise PathSafetyError("version candidate changed since it was scanned")

    approved_archive = validate_path(archive_root)
    if is_within(approved_archive, obsolete.path) or is_within(approved_archive, keeper.path):
        raise PathSafetyError("archive root cannot be inside a version candidate")
    destination = _unique_archive_destination(os.path.join(
        approved_archive,
        os.path.basename(obsolete.path.rstrip(os.sep)),
    ))
    validate_move(obsolete.path, destination)

    from fileorganizer.workers import safe_merge_move

    manifest: list[dict] = []
    moved, skipped = safe_merge_move(
        obsolete.path,
        destination,
        log_cb=log_cb,
        check_hashes=False,
        manifest=manifest,
    )
    return VersionArchiveResult(
        source=obsolete.path,
        destination=destination,
        status="completed",
        reason=reason,
        moved_files=moved,
        skipped_files=skipped,
        manifest=tuple(manifest),
    )


__all__ = [
    "VersionArchiveResult",
    "VersionCandidate",
    "archive_version_candidate",
    "extract_marketplace_id",
    "extract_version_hint",
    "find_version_groups",
    "generate_archive_plan",
    "pick_best_version",
    "scan_version_groups",
    "version_archive_reason",
]
