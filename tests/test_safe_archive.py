"""Tests for fileorganizer/safe_archive.py — N-13 path-traversal guard.

Goal: prove that no realistic crafted archive entry name can resolve to a
path outside the target root.  We exercise the common attack shapes:

    - traversal via '..'
    - absolute paths (POSIX and Windows)
    - UNC roots
    - drive-letter prefixes
    - empty / whitespace
    - sibling-prefix collisions ('targetX' vs 'target')
    - happy paths (subdirs, dot-prefix names, deeply nested entries)

The check is path-only — it never touches the filesystem — so these tests
work identically on Windows and POSIX.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fileorganizer.safe_archive import (
    UnsafeArchiveEntryError,
    filter_safe_entries,
    safe_extract_path,
)


class SafeExtractPath(unittest.TestCase):

    def setUp(self):
        # Fresh temp root per test so we never reuse stale paths.
        self._tmp = tempfile.mkdtemp(prefix="safe_archive_test_")
        self.target = self._tmp

    def tearDown(self):
        try:
            os.rmdir(self._tmp)
        except OSError:
            pass

    # ── Happy paths ──────────────────────────────────────────────────────

    def test_simple_filename(self):
        out = safe_extract_path(self.target, "readme.txt")
        self.assertTrue(out.endswith(os.path.normcase("readme.txt")))
        self.assertTrue(out.startswith(os.path.normcase(os.path.abspath(self.target))))

    def test_nested_subdir(self):
        out = safe_extract_path(self.target, "a/b/c/file.txt")
        # Must live under target, regardless of separator translation.
        self.assertTrue(out.startswith(os.path.normcase(os.path.abspath(self.target))))

    def test_dotfile_is_safe(self):
        out = safe_extract_path(self.target, ".hidden")
        self.assertTrue(out.startswith(os.path.normcase(os.path.abspath(self.target))))

    def test_double_dot_in_filename_is_safe(self):
        # '..foo' is not a traversal; only '..' as a path component is.
        out = safe_extract_path(self.target, "..foo")
        self.assertTrue(out.startswith(os.path.normcase(os.path.abspath(self.target))))

    # ── Traversal rejected ───────────────────────────────────────────────

    def test_dotdot_root_traversal_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "../escape.txt")

    def test_dotdot_nested_traversal_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "subdir/../../escape.txt")

    def test_dotdot_at_end_rejected_when_escapes(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "a/b/../../../escape.txt")

    # ── Absolute paths rejected ──────────────────────────────────────────

    def test_posix_absolute_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "/etc/passwd")

    def test_windows_absolute_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "C:\\Windows\\System32\\evil.exe")

    def test_drive_letter_prefix_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "C:relative.txt")

    def test_unc_root_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "\\\\server\\share\\evil.exe")

    def test_unc_forward_slash_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "//server/share/evil.exe")

    # ── Sibling prefix collision ─────────────────────────────────────────

    def test_sibling_prefix_collision_rejected(self):
        # If target is /tmp/xxx, '/tmp/xxxY' must NOT pass.  We exercise this
        # by joining a relative entry that resolves outside target — the
        # `target_norm + os.sep` guard in safe_extract_path covers this.
        # The crafted entry uses Windows separators which Python normalizes.
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "../" + os.path.basename(self.target) + "X/leak.txt")

    # ── Edge cases ───────────────────────────────────────────────────────

    def test_empty_entry_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "")

    def test_whitespace_entry_rejected(self):
        with self.assertRaises(UnsafeArchiveEntryError):
            safe_extract_path(self.target, "   ")


class FilterSafeEntries(unittest.TestCase):
    def test_drops_unsafe_keeps_safe(self):
        entries = [
            "ok.txt",
            "../escape.txt",
            "/abs.txt",
            "subdir/inner.txt",
            "",
        ]
        with tempfile.TemporaryDirectory() as tmp:
            kept = filter_safe_entries(tmp, entries)
            kept_names = [n for n, _ in kept]
            self.assertEqual(set(kept_names), {"ok.txt", "subdir/inner.txt"})

    def test_returns_resolved_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            kept = dict(filter_safe_entries(tmp, ["a/b.txt"]))
            self.assertIn("a/b.txt", kept)
            resolved = kept["a/b.txt"]
            self.assertTrue(resolved.startswith(os.path.normcase(os.path.abspath(tmp))))


if __name__ == "__main__":
    unittest.main()
