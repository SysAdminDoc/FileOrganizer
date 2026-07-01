"""Tests for fileorganizer.version_dedup — NEXT-21 version-aware dedup."""
import unittest

from fileorganizer.version_dedup import (
    extract_marketplace_id, extract_version_hint,
    find_version_groups, pick_best_version, generate_archive_plan,
    VersionCandidate,
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


if __name__ == "__main__":
    unittest.main()
