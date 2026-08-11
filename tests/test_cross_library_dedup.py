"""Tests for exact cross-library folder deduplication."""

from __future__ import annotations

from pathlib import Path

import pytest

from fileorganizer.cross_library_dedup import (
    PathSafetyError,
    apply_cross_library_action,
    compute_folder_fingerprint,
    folder_fingerprint,
    scan_cross_library,
)


def _write_tree(root: Path, files: dict[str, str]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def test_fingerprint_is_complete_and_order_independent(tmp_path):
    first = _write_tree(tmp_path / "first", {
        "nested/b.txt": "beta",
        "a.txt": "alpha",
    })
    second = _write_tree(tmp_path / "second", {
        "a.txt": "alpha",
        "nested/b.txt": "beta",
    })

    record = compute_folder_fingerprint(first)
    assert record is not None
    assert record.file_count == 2
    assert record.total_bytes == len("alpha") + len("beta")
    assert record.fingerprint == folder_fingerprint(second)

    (second / "nested/b.txt").write_text("changed", encoding="utf-8")
    assert folder_fingerprint(first) != folder_fingerprint(second)


def test_scan_reports_only_groups_spanning_distinct_roots(tmp_path):
    library_a = tmp_path / "library-a"
    library_b = tmp_path / "library-b"
    identical = {"project/file.prproj": "same", "preview.png": "preview"}
    _write_tree(library_a / "asset-one", identical)
    _write_tree(library_a / "asset-one-copy", identical)
    _write_tree(library_b / "renamed-asset", identical)
    _write_tree(library_b / "different", {"file.prproj": "other"})

    groups = scan_cross_library([library_a, library_b], depth=1)

    assert len(groups) == 1
    group = groups[0]
    assert len(group.members) == 3
    assert set(group.library_roots) == {
        str(library_a.resolve()),
        str(library_b.resolve()),
    }
    assert {member.name for member in group.members} == {
        "asset-one",
        "asset-one-copy",
        "renamed-asset",
    }


def test_scan_depth_and_cancel_are_bounded(tmp_path):
    library_a = tmp_path / "library-a"
    library_b = tmp_path / "library-b"
    _write_tree(library_a / "level-one", {"root.txt": "different-a"})
    _write_tree(library_a / "level-one" / "level-two", {"file.txt": "same"})
    _write_tree(library_b / "other", {"root.txt": "different-b"})
    _write_tree(library_b / "other" / "level-two", {"file.txt": "same"})

    assert scan_cross_library([library_a, library_b], depth=1) == []
    assert len(scan_cross_library([library_a, library_b], depth=2)) == 1
    with pytest.raises(ValueError, match="positive integer"):
        scan_cross_library([library_a], depth=0)


def test_action_revalidates_before_mutating(tmp_path):
    library_a = tmp_path / "library-a"
    library_b = tmp_path / "library-b"
    source = _write_tree(library_a / "asset", {"file.txt": "same"})
    keeper = _write_tree(library_b / "asset", {"file.txt": "same"})
    group = scan_cross_library([library_a, library_b])[0]

    (source / "file.txt").write_text("changed", encoding="utf-8")
    with pytest.raises(PathSafetyError, match="changed since it was scanned"):
        apply_cross_library_action(
            group,
            str(source),
            action="merge",
            keep_path=str(keeper),
        )


def test_archive_action_moves_only_revalidated_duplicate(tmp_path):
    library_a = tmp_path / "library-a"
    library_b = tmp_path / "library-b"
    source = _write_tree(library_a / "asset", {"nested/file.txt": "same"})
    keeper = _write_tree(library_b / "asset", {"nested/file.txt": "same"})
    archive = tmp_path / "archive"
    archive.mkdir()
    group = scan_cross_library([library_a, library_b])[0]

    result = apply_cross_library_action(
        group,
        str(source),
        action="archive",
        keep_path=str(keeper),
        archive_root=str(archive),
    )

    assert result.status == "completed"
    assert result.action == "archive"
    assert not source.exists()
    assert Path(result.destination, "nested", "file.txt").read_text(encoding="utf-8") == "same"
    assert keeper.exists()
