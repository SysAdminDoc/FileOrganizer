"""Tests for fileorganizer.taxonomy_export — NEXT-93 taxonomy export."""
import json
import os
import tempfile
import unittest

from fileorganizer.taxonomy_export import (
    export_taxonomy_json, export_taxonomy_yaml, get_taxonomy_stats,
)


class TestTaxonomyExportJson(unittest.TestCase):
    def test_json_is_valid(self):
        result = export_taxonomy_json()
        data = json.loads(result)
        self.assertIn("categories", data)
        self.assertIn("schema_version", data)
        self.assertIn("category_count", data)

    def test_categories_present(self):
        data = json.loads(export_taxonomy_json())
        self.assertGreater(len(data["categories"]), 100)
        names = {c["category"] for c in data["categories"]}
        self.assertIn("After Effects - Templates", names)

    def test_keywords_present(self):
        data = json.loads(export_taxonomy_json())
        for cat in data["categories"]:
            self.assertIn("keywords", cat)
            self.assertIsInstance(cat["keywords"], list)

    def test_negative_keywords_included(self):
        data = json.loads(export_taxonomy_json())
        has_negatives = any("negative_keywords" in c for c in data["categories"])
        self.assertTrue(has_negatives)

    def test_writes_to_file(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            export_taxonomy_json(path)
            self.assertTrue(os.path.isfile(path))
            with open(path, "r") as fh:
                data = json.load(fh)
            self.assertGreater(len(data["categories"]), 100)
        finally:
            os.unlink(path)


class TestTaxonomyExportYaml(unittest.TestCase):
    def test_yaml_output(self):
        result = export_taxonomy_yaml()
        self.assertIn("categories:", result)
        self.assertIn("schema_version:", result)

    def test_contains_categories(self):
        result = export_taxonomy_yaml()
        self.assertIn("After Effects - Templates", result)

    def test_writes_to_file(self):
        with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False) as f:
            path = f.name
        try:
            export_taxonomy_yaml(path)
            self.assertTrue(os.path.isfile(path))
        finally:
            os.unlink(path)


class TestTaxonomyStats(unittest.TestCase):
    def test_stats_keys(self):
        stats = get_taxonomy_stats()
        self.assertIn("total_categories", stats)
        self.assertIn("total_keywords", stats)
        self.assertIn("sections", stats)
        self.assertIn("negative_rules", stats)

    def test_reasonable_counts(self):
        stats = get_taxonomy_stats()
        self.assertGreater(stats["total_categories"], 100)
        self.assertGreater(stats["total_keywords"], 500)


if __name__ == "__main__":
    unittest.main()
