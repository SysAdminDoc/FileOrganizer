"""Tests for fileorganizer.version_dedup — NEXT-21 version-aware dedup."""
import unittest
from pathlib import Path

import pytest

from fileorganizer.version_dedup import (
    extract_marketplace_id, extract_version_hint,
    find_version_groups, pick_best_version, generate_archive_plan,
    VersionCandidate,
    archive_version_candidate, scan_version_groups,
)


class TestExtractMarketplaceId(unittest.TestCase):
    def test_videohive_9digit(self):
        self.assertEqual(extract_marketplace_id("22197897-broadcast-INTRO"), "22197897")

    def test_vh_prefix(self):
        self.assertEqual(extract_marketplace_id("VH-1234567"), "1234567")

    def test_no_id(self):
        self.assertIsNone(extract_marketplace_id("my-cool-template"))

    def test_trailing_id(self):
        self.assertEqual(extract_marketplace_id("template_12345678"), "12345678")


class TestExtractVersionHint(unittest.TestCase):
    def test_v_prefix(self):
        self.assertEqual(extract_version_hint("template_v2.0"), "2.0")

    def test_version_word(self):
        self.assertEqual(extract_version_hint("template-version-3.1"), "3.1")

    def test_brackets(self):
        self.assertEqual(extract_version_hint("template (v4)"), "4")

    def test_no_version(self):
        self.assertIsNone(extract_version_hint("just-a-name"))


class TestFindVersionGroups(unittest.TestCase):
    def test_groups_by_id(self):
        items = [
            {"path": "/a", "folder_name": "22197897-v1"},
            {"path": "/b", "folder_name": "22197897-v2"},
            {"path": "/c", "folder_name": "99999999-other"},
        ]
        groups = find_version_groups(items)
        self.assertIn("22197897", groups)
        self.assertEqual(len(groups["22197897"]), 2)
        self.assertNotIn("99999999", groups)

    def test_no_groups_for_singles(self):
        items = [
            {"path": "/a", "folder_name": "11111111-x"},
            {"path": "/b", "folder_name": "22222222-y"},
        ]
        groups = find_version_groups(items)
        self.assertEqual(len(groups), 0)


class TestPickBestVersion(unittest.TestCase):
    def test_prefers_more_files(self):
        candidates = [
            VersionCandidate(path="/a", marketplace_id="1", file_count=5),
            VersionCandidate(path="/b", marketplace_id="1", file_count=10),
        ]
        best, rest = pick_best_version(candidates)
        self.assertEqual(best.path, "/b")
        self.assertEqual(len(rest), 1)

    def test_prefers_higher_version(self):
        candidates = [
            VersionCandidate(path="/a", marketplace_id="1", file_count=5, version_hint="1.0"),
            VersionCandidate(path="/b", marketplace_id="1", file_count=5, version_hint="2.0"),
        ]
        best, _ = pick_best_version(candidates)
        self.assertEqual(best.path, "/b")

    def test_file_count_beats_higher_version_hint(self):
        candidates = [
            VersionCandidate(path="/complete", marketplace_id="1", file_count=10, version_hint="1.0"),
            VersionCandidate(path="/partial", marketplace_id="1", file_count=5, version_hint="2.0"),
        ]
        best, _ = pick_best_version(candidates)
        self.assertEqual(best.path, "/complete")


class TestGenerateArchivePlan(unittest.TestCase):
    def test_generates_plan(self):
        items = [
            {"path": "/a", "folder_name": "22197897-v1", "file_count": 5},
            {"path": "/b", "folder_name": "22197897-v2", "file_count": 10},
        ]
        plan = generate_archive_plan(items)
        self.assertEqual(len(plan), 1)
        self.assertEqual(plan[0]["keep"], "/b")
        self.assertEqual(plan[0]["archive"], "/a")

    def test_empty_items(self):
        self.assertEqual(generate_archive_plan([]), [])

    def test_identical_same_id_items_are_not_version_plan(self):
        items = [
            {"path": "/a", "folder_name": "22197897-copy-a", "file_count": 5, "fingerprint": "same"},
            {"path": "/b", "folder_name": "22197897-copy-b", "file_count": 5, "fingerprint": "same"},
        ]
        self.assertEqual(generate_archive_plan(items), [])


def _write_version(folder: Path, name: str, files: dict[str, str]) -> Path:
    target = folder / name
    target.mkdir(parents=True)
    for relative, content in files.items():
        path = target / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return target


def test_scan_version_groups_hashes_and_filters_exact_copies(tmp_path):
    library = tmp_path / "library"
    _write_version(library, "22197897-v1", {"project.aep": "old"})
    _write_version(library, "22197897-v2", {"project.aep": "new", "readme.txt": "new"})
    _write_version(library, "99999999-copy-a", {"file.txt": "same"})
    _write_version(library, "99999999-copy-b", {"file.txt": "same"})

    groups = scan_version_groups([library])

    assert set(groups) == {"22197897"}
    assert {candidate.file_count for candidate in groups["22197897"]} == {1, 2}


def test_archive_version_candidate_revalidates_keeper_and_source(tmp_path):
    library = tmp_path / "library"
    archive = tmp_path / "archive"
    archive.mkdir()
    keeper_path = _write_version(library, "22197897-v2", {"project.aep": "new", "readme.txt": "new"})
    obsolete_path = _write_version(library, "22197897-v1", {"project.aep": "old"})
    groups = scan_version_groups([library])
    keeper, obsolete_candidates = pick_best_version(groups["22197897"])
    obsolete = obsolete_candidates[0]

    result = archive_version_candidate(keeper, obsolete, archive_root=archive, reason="fewer files")

    assert result.status == "completed"
    assert not obsolete_path.exists()
    assert Path(result.destination, "project.aep").read_text(encoding="utf-8") == "old"
    assert keeper_path.exists()


def test_archive_version_candidate_rejects_stale_source(tmp_path):
    library = tmp_path / "library"
    archive = tmp_path / "archive"
    archive.mkdir()
    _write_version(library, "22197897-v2", {"project.aep": "new", "readme.txt": "new"})
    obsolete_path = _write_version(library, "22197897-v1", {"project.aep": "old"})
    keeper, obsolete_candidates = pick_best_version(scan_version_groups([library])["22197897"])
    obsolete = obsolete_candidates[0]
    (obsolete_path / "project.aep").write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="changed since it was scanned"):
        archive_version_candidate(keeper, obsolete, archive_root=archive)


if __name__ == "__main__":
    unittest.main()
