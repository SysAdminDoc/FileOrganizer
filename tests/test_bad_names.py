"""Tests for fileorganizer.bad_names — NEXT-42 bad filename detection."""
import os
import tempfile
import unittest

from fileorganizer.bad_names import check_bad_names, fix_bad_names, _check_filename


class TestCheckFilename(unittest.TestCase):
    def test_clean_filename_no_issues(self):
        issues = _check_filename("clean_name.txt", "/tmp/clean_name.txt")
        self.assertEqual(issues, [])

    def test_non_ascii_detected(self):
        issues = _check_filename("日本語.psd", "/tmp/日本語.psd")
        self.assertTrue(any("Non-ASCII" in desc for _, desc in issues))

    def test_reserved_chars_detected(self):
        issues = _check_filename("file<name>.txt", "/tmp/file<name>.txt")
        self.assertTrue(any("Reserved Windows" in desc for _, desc in issues))

    def test_leading_space_detected(self):
        issues = _check_filename(" leadingspace.txt", "/tmp/ leadingspace.txt")
        self.assertTrue(any("Leading or trailing" in desc for _, desc in issues))

    def test_trailing_space_detected(self):
        issues = _check_filename("trailingspace.txt ", "/tmp/trailingspace.txt ")
        self.assertTrue(any("Leading or trailing" in desc for _, desc in issues))

    def test_long_filename_detected(self):
        long_name = "a" * 201 + ".txt"
        issues = _check_filename(long_name, f"/tmp/{long_name}")
        self.assertTrue(any(">200" in desc for _, desc in issues))

    def test_filename_at_200_ok(self):
        name = "a" * 196 + ".txt"
        issues = _check_filename(name, f"/tmp/{name}")
        self.assertFalse(any(">200" in desc for _, desc in issues))

    def test_uppercase_extension_detected(self):
        issues = _check_filename("photo.JPG", "/tmp/photo.JPG")
        self.assertTrue(any("Uppercase extension" in desc for _, desc in issues))

    def test_lowercase_extension_ok(self):
        issues = _check_filename("photo.jpg", "/tmp/photo.jpg")
        self.assertFalse(any("Uppercase extension" in desc for _, desc in issues))

    def test_mixed_case_extension_detected(self):
        issues = _check_filename("photo.Jpg", "/tmp/photo.Jpg")
        self.assertTrue(any("Uppercase extension" in desc for _, desc in issues))

    def test_multiple_issues_single_file(self):
        issues = _check_filename(" bad<file>.JPG ", "/tmp/ bad<file>.JPG ")
        self.assertGreaterEqual(len(issues), 2)


class TestCheckBadNames(unittest.TestCase):
    def test_nonexistent_dir(self):
        self.assertEqual(check_bad_names("/nonexistent/path"), [])

    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(check_bad_names(d), [])

    def test_finds_issues_in_dir(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "photo.JPG"), "w").close()
            issues = check_bad_names(d)
            self.assertTrue(len(issues) > 0)

    def test_clean_files_no_issues(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "clean.txt"), "w").close()
            open(os.path.join(d, "also_clean.png"), "w").close()
            issues = check_bad_names(d)
            self.assertEqual(issues, [])


class TestFixBadNames(unittest.TestCase):
    def test_nonexistent_dir(self):
        self.assertEqual(fix_bad_names("/nonexistent/path"), [])

    def test_dry_run_no_rename(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "photo.JPG")
            open(path, "w").close()
            results = fix_bad_names(d, dry_run=True)
            self.assertTrue(any("would rename" in action for _, _, action in results))
            self.assertTrue(os.path.exists(path))

    def test_actual_rename_uppercase_ext(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "photo.JPG")
            open(path, "w").close()
            results = fix_bad_names(d, dry_run=False)
            self.assertTrue(len(results) > 0)
            expected = os.path.join(d, "photo.jpg")
            self.assertTrue(os.path.exists(expected))

    def test_clean_files_no_results(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "file_test.txt")
            open(path, "w").close()
            results = fix_bad_names(d, dry_run=True)
            self.assertEqual(results, [])


if __name__ == "__main__":
    unittest.main()
