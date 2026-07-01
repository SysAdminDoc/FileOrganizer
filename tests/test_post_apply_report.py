"""Tests for fileorganizer.post_apply_report — NEXT-25 HTML report."""
import os
import unittest

from fileorganizer.post_apply_report import generate_html_report


class TestPostApplyReport(unittest.TestCase):
    def _sample_ops(self):
        return [
            {"dst": "/src/a", "src": "/dst/a", "category": "After Effects - Slideshow",
             "confidence": "85", "status": "Done"},
            {"dst": "/src/b", "src": "/dst/b", "category": "After Effects - Slideshow",
             "confidence": "72", "status": "Done"},
            {"dst": "/src/c", "src": "/dst/c", "category": "Print - Flyers & Posters",
             "confidence": "90", "status": "Done"},
            {"dst": "/src/d", "src": "/dst/d", "category": "After Effects - Logo Reveals",
             "confidence": "?", "status": "Error"},
        ]

    def test_generates_html_file(self):
        path = generate_html_report("test-run-1", self._sample_ops(), 3, 1, auto_open=False)
        try:
            self.assertTrue(os.path.isfile(path))
            self.assertTrue(path.endswith(".html"))
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_html_contains_categories(self):
        path = generate_html_report("test-run-2", self._sample_ops(), 3, 1, auto_open=False)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("After Effects - Slideshow", content)
            self.assertIn("Print - Flyers &amp; Posters", content)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_html_contains_counts(self):
        path = generate_html_report("test-run-3", self._sample_ops(), 3, 1, auto_open=False)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn(">3<", content)
            self.assertIn(">1<", content)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_with_timing(self):
        timing = {"index": 500, "classify": 2500, "apply": 1200}
        path = generate_html_report("test-run-4", self._sample_ops(), 3, 1,
                                    timing_summary=timing, auto_open=False)
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            self.assertIn("index", content)
            self.assertIn("500ms", content)
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_empty_ops(self):
        path = generate_html_report("test-run-5", [], 0, 0, auto_open=False)
        try:
            self.assertTrue(os.path.isfile(path))
        finally:
            if os.path.exists(path):
                os.unlink(path)


if __name__ == "__main__":
    unittest.main()
