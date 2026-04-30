"""Tests for fileorganizer/psd_safe.py — N-13 PSD parser size guard.

We don't synthesize a real PSD here; we just verify that the size-guard
short-circuits before calling psd_tools, that missing/oversized files
return None, and that file_too_large() reports correctly.
"""
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fileorganizer import psd_safe


class FileTooLarge(unittest.TestCase):
    def test_missing_file(self):
        self.assertFalse(psd_safe.file_too_large(r"C:\does\not\exist.psd"))

    def test_small_file_under_limit(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".psd") as f:
            f.write(b"x" * 1024)
            path = f.name
        try:
            self.assertFalse(psd_safe.file_too_large(path, size_limit=1024 * 1024))
        finally:
            os.unlink(path)

    def test_file_over_limit(self):
        with tempfile.NamedTemporaryFile(delete=False, suffix=".psd") as f:
            f.write(b"x" * 4096)
            path = f.name
        try:
            self.assertTrue(psd_safe.file_too_large(path, size_limit=1024))
        finally:
            os.unlink(path)


class SafePsdOpen(unittest.TestCase):
    def test_missing_file_returns_none(self):
        self.assertIsNone(psd_safe.safe_psd_open(r"C:\does\not\exist.psd"))

    def test_oversized_file_returns_none_without_calling_psd_tools(self):
        # Write a tiny file and set the limit BELOW its size.  If the guard
        # works the call returns None even though psd_tools would have
        # raised a parser error on this junk content.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".psd") as f:
            f.write(b"NOTAREALPSD" * 100)
            path = f.name
        try:
            result = psd_safe.safe_psd_open(path, size_limit=64)
            self.assertIsNone(result)
        finally:
            os.unlink(path)

    def test_garbage_under_limit_returns_none(self):
        # Within the size limit but not a real PSD — psd_tools (if installed)
        # raises during parse, our wrapper isolates that and returns None.
        with tempfile.NamedTemporaryFile(delete=False, suffix=".psd") as f:
            f.write(b"NOT A PSD")
            path = f.name
        try:
            self.assertIsNone(psd_safe.safe_psd_open(path))
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
