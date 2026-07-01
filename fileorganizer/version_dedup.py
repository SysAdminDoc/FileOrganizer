"""Version-aware deduplication (NEXT-21).

When two items share a marketplace ID but have different file counts or
fingerprints, one is likely a newer version. Keeps the one with more files;
archives the other with a reason note.
"""
import os
import re
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class VersionCandidate:
    """A potential version of an asset."""
    path: str
    marketplace_id: str
    file_count: int = 0
    total_bytes: int = 0
    fingerprint: Optional[str] = None
    version_hint: Optional[str] = None

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
)


def extract_marketplace_id(folder_name: str) -> Optional[str]:
    """Extract marketplace ID from folder name."""
    m = _MARKETPLACE_ID_PATTERN.search(folder_name)
    if m:
        return next(g for g in m.groups() if g is not None)
    return None


def extract_version_hint(folder_name: str) -> Optional[str]:
    """Extract version number from folder name."""
    m = _VERSION_PATTERN.search(folder_name)
    if m:
        return next(g for g in m.groups() if g is not None)
    return None


def find_version_groups(
    items: List[Dict],
) -> Dict[str, List[VersionCandidate]]:
    """Group items by marketplace ID to find version duplicates.

    Args:
        items: list of dicts with 'path', 'folder_name', and optionally
               'file_count', 'total_bytes', 'fingerprint' keys.

    Returns:
        Dict mapping marketplace_id -> list of VersionCandidates.
        Only groups with 2+ members are returned.
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
        )

        if mid not in groups:
            groups[mid] = []
        groups[mid].append(candidate)

    return {mid: members for mid, members in groups.items() if len(members) >= 2}


def pick_best_version(candidates: List[VersionCandidate]) -> Tuple[VersionCandidate, List[VersionCandidate]]:
    """Pick the best version from a group of candidates.

    Strategy: prefer the one with the most files. Ties broken by total bytes.
    If version hints exist, prefer the highest version number.

    Returns:
        (best, [rest]) where rest are the candidates to archive.
    """
    def sort_key(c: VersionCandidate):
        ver = 0.0
        if c.version_hint:
            try:
                parts = c.version_hint.split(".")
                ver = sum(float(p) * (1000 ** (3 - i)) for i, p in enumerate(parts[:4]))
            except (ValueError, IndexError):
                pass
        return (ver, c.file_count, c.total_bytes)

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
    groups = find_version_groups(items)
    plan = []

    for mid, candidates in groups.items():
        best, rest = pick_best_version(candidates)
        for obsolete in rest:
            reason_parts = []
            if best.file_count > obsolete.file_count:
                reason_parts.append(
                    f"fewer files ({obsolete.file_count} vs {best.file_count})"
                )
            if best.total_bytes > obsolete.total_bytes:
                reason_parts.append("smaller total size")
            if best.version_hint and obsolete.version_hint:
                reason_parts.append(
                    f"older version ({obsolete.version_hint} vs {best.version_hint})"
                )
            if best.fingerprint and obsolete.fingerprint and best.fingerprint != obsolete.fingerprint:
                reason_parts.append("different fingerprint")

            plan.append({
                "marketplace_id": mid,
                "keep": best.path,
                "archive": obsolete.path,
                "reason": "; ".join(reason_parts) or "duplicate marketplace ID",
            })

    return plan
