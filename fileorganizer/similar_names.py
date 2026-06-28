"""Fuzzy similar-name grouping for pre-flight checks."""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

try:
    from rapidfuzz import fuzz as _fuzz
except Exception:  # pragma: no cover - optional dependency guard
    _fuzz = None


DEFAULT_THRESHOLD = 92.0
DEFAULT_MAX_PER_ROOT = 5000
DEFAULT_MAX_GROUPS = 50


@dataclass(frozen=True)
class SimilarNameGroup:
    root: str
    pattern: str
    names: tuple[str, ...]
    paths: tuple[str, ...]
    score: float
    truncated: int = 0

    @property
    def representative(self) -> str:
        return self.names[0] if self.names else self.pattern


def group_similar_names(
    names: Sequence[str],
    paths: Sequence[str] | None = None,
    *,
    root: str = "",
    threshold: float = DEFAULT_THRESHOLD,
    max_items: int = DEFAULT_MAX_PER_ROOT,
) -> list[SimilarNameGroup]:
    """Cluster names whose token-sort similarity is at least threshold."""
    if _fuzz is None or max_items <= 1:
        return []

    raw_paths = paths if paths is not None else names
    entries = [
        (str(name), str(raw_paths[idx] if idx < len(raw_paths) else name))
        for idx, name in enumerate(names[:max_items])
        if str(name).strip()
    ]
    if len(entries) <= 1:
        return []
    limited_names = [name for name, _path in entries]
    limited_paths = [path for _name, path in entries]

    normalized = [_normalize_name(n) for n in limited_names]
    parent = list(range(len(limited_names)))
    scores: dict[tuple[int, int], float] = {}

    def find(idx: int) -> int:
        while parent[idx] != idx:
            parent[idx] = parent[parent[idx]]
            idx = parent[idx]
        return idx

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(len(limited_names)):
        left = normalized[i]
        if not left:
            continue
        for j in range(i + 1, len(limited_names)):
            right = normalized[j]
            if not right or not _likely_comparable(left, right):
                continue
            score = float(_fuzz.token_sort_ratio(left, right))
            if score >= threshold:
                scores[(i, j)] = score
                union(i, j)

    clusters: dict[int, list[int]] = {}
    for idx in range(len(limited_names)):
        clusters.setdefault(find(idx), []).append(idx)

    groups: list[SimilarNameGroup] = []
    for members in clusters.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda m: _natural_key(limited_names[m]))
        pair_scores = [
            scores.get((min(a, b), max(a, b)), 100.0)
            for pos, a in enumerate(members)
            for b in members[pos + 1:]
            if find(a) == find(b)
        ]
        group_names = tuple(limited_names[m] for m in members)
        groups.append(SimilarNameGroup(
            root=root,
            pattern=_pattern_for(group_names),
            names=group_names,
            paths=tuple(limited_paths[m] for m in members),
            score=min(pair_scores) if pair_scores else threshold,
        ))

    groups.sort(key=lambda g: (-len(g.names), -g.score, g.pattern.lower()))
    return groups


def scan_paths(
    roots: Iterable[str | os.PathLike | None],
    *,
    threshold: float = DEFAULT_THRESHOLD,
    max_per_root: int = DEFAULT_MAX_PER_ROOT,
    max_groups: int = DEFAULT_MAX_GROUPS,
) -> list[SimilarNameGroup]:
    """Find similar file-name groups inside each root path."""
    groups: list[SimilarNameGroup] = []
    for root in roots:
        if root is None:
            continue
        path = Path(root)
        names, paths, truncated = _collect_file_names(path, max_per_root)
        for group in group_similar_names(
            names, paths, root=str(path), threshold=threshold, max_items=max_per_root,
        ):
            groups.append(SimilarNameGroup(
                root=group.root,
                pattern=group.pattern,
                names=group.names,
                paths=group.paths,
                score=group.score,
                truncated=truncated,
            ))
            if len(groups) >= max_groups:
                return groups
    return groups


def _collect_file_names(root: Path, max_items: int) -> tuple[list[str], list[str], int]:
    names: list[str] = []
    paths: list[str] = []
    truncated = 0

    if max_items <= 0:
        return names, paths, 0
    if root.is_file():
        return [root.name], [str(root)], 0
    if not root.is_dir():
        return names, paths, 0

    try:
        walker = os.walk(root)
        for current, dirs, files in walker:
            for filename in files:
                if len(names) >= max_items:
                    truncated = 1
                    dirs[:] = []
                    return names, paths, truncated
                names.append(filename)
                paths.append(str(Path(current) / filename))
    except (OSError, PermissionError):
        return names, paths, truncated
    return names, paths, truncated


_VERSION_TOKEN = re.compile(
    r"(?ix)"
    r"\b("
    r"v(?:er(?:sion)?)?\s*\d+(?:\.\d+)*"
    r"|final(?:\s*\d+)?"
    r"|copy\s*\d*"
    r"|rev\s*\d+"
    r"|draft\s*\d*"
    r"|old|new"
    r")\b"
)
_SEPARATORS = re.compile(r"[_\-.]+")
_SPACE = re.compile(r"\s+")


def _normalize_name(name: str) -> str:
    stem = Path(name).stem.lower()
    stem = _SEPARATORS.sub(" ", stem)
    stem = _VERSION_TOKEN.sub(" ", stem)
    stem = re.sub(r"\b\d{1,4}\b", " ", stem)
    stem = _SPACE.sub(" ", stem).strip()
    return stem


def _likely_comparable(left: str, right: str) -> bool:
    lt = set(left.split())
    rt = set(right.split())
    if not lt or not rt:
        return False
    return bool(lt & rt)


def _pattern_for(names: Sequence[str]) -> str:
    stems = [Path(n).stem for n in names]
    prefix = os.path.commonprefix(stems).rstrip(" _-.")
    if len(prefix) >= 4:
        return f"{prefix}*"
    tokens = _normalize_name(min(names, key=len)).split()
    if tokens:
        return " ".join(tokens[:4]) + "*"
    return min(names, key=len)


def _natural_key(value: str) -> list[object]:
    parts = re.split(r"(\d+)", value.lower())
    return [int(p) if p.isdigit() else p for p in parts]
