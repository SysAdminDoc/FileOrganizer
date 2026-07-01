"""Tests for fileorganizer.symlink_detector — NEXT-35 reparse point detection."""
import os
import sys
import tempfile
import unittest

from fileorganizer.symlink_detector import (
    is_symlink_or_junction,
    scan_for_reparse_points,
    is_path_traversal_risk,
    validate_junction_target,
)


class TestIsSymlinkOrJunction(unittest.TestCase):
    def test_regular_file(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "regular.txt")
            open(p, "w").close()
            is_reparse, rtype = is_symlink_or_junction(p)
            self.assertFalse(is_reparse)
            self.assertIsNone(rtype)

    def test_regular_directory(self):
        with tempfile.TemporaryDirectory() as d:
            sub = os.path.join(d, "subdir")
            os.makedirs(sub)
            is_reparse, rtype = is_symlink_or_junction(sub)
            self.assertFalse(is_reparse)
            self.assertIsNone(rtype)

    def test_nonexistent_path(self):
        is_reparse, rtype = is_symlink_or_junction("/nonexistent/path/xyz")
        self.assertFalse(is_reparse)
        self.assertIsNone(rtype)

    def test_return_types(self):
        with tempfile.TemporaryDirectory() as d:
            result = is_symlink_or_junction(d)
            self.assertIsInstance(result, tuple)
            self.assertEqual(len(result), 2)


class TestScanForReparsePoints(unittest.TestCase):
    def test_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            issues = scan_for_reparse_points(d)
            self.assertEqual(issues, [])

    def test_dir_with_regular_files(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "a.txt"), "w").close()
            os.makedirs(os.path.join(d, "subdir"))
            issues = scan_for_reparse_points(d)
            self.assertEqual(issues, [])

    def test_nonexistent_dir(self):
        issues = scan_for_reparse_points("/nonexistent/path/xyz")
        self.assertEqual(issues, [])

    def test_returns_list(self):
        with tempfile.TemporaryDirectory() as d:
            result = scan_for_reparse_points(d)
            self.assertIsInstance(result, list)


class TestIsPathTraversalRisk(unittest.TestCase):
    @unittest.skipUnless(sys.platform == "win32", "Windows paths only")
    def test_windows_dir_risky(self):
        self.assertTrue(is_path_traversal_risk(r"C:\Windows\System32"))

    @unittest.skipUnless(sys.platform == "win32", "Windows paths only")
    def test_program_files_risky(self):
        self.assertTrue(is_path_traversal_risk(r"C:\Program Files\SomeApp"))

    @unittest.skipUnless(sys.platform == "win32", "Windows paths only")
    def test_appdata_risky(self):
        self.assertTrue(is_path_traversal_risk(r"C:\Users\test\AppData\Local"))

    @unittest.skipUnless(sys.platform == "win32", "Windows paths only")
    def test_user_data_drive_safe(self):
        self.assertFalse(is_path_traversal_risk(r"G:\Organized\After Effects"))

    def test_empty_path(self):
        result = is_path_traversal_risk("")
        self.assertIsInstance(result, bool)


class TestValidateJunctionTarget(unittest.TestCase):
    def test_nonexistent_target(self):
        is_safe, reason = validate_junction_target("/nonexistent/path/xyz")
        self.assertFalse(is_safe)

    @unittest.skipUnless(sys.platform == "win32", "Windows paths only")
    def test_data_drive_target_safe(self):
        test_path = r"G:\Organized"
        if os.path.isdir(test_path):
            is_safe, reason = validate_junction_target(test_path)
            self.assertTrue(is_safe)
        else:
            self.skipTest("G:\\Organized not available")

    def test_returns_tuple(self):
        result = validate_junction_target("/nonexistent/path/xyz")
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)


if __name__ == "__main__":
    unittest.main()
