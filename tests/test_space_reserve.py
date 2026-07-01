"""Tests for fileorganizer.space_reserve — NEXT-36 free-space reserve."""
import os
import tempfile
import unittest

from fileorganizer.space_reserve import (
    create_reserve, release_reserve, has_reserve, _get_free_space,
)


class TestSpaceReserve(unittest.TestCase):
    def test_create_and_release(self):
        with tempfile.TemporaryDirectory() as d:
            path = create_reserve(d, 1024)
            self.assertIsNotNone(path)
            self.assertTrue(has_reserve(d))
            release_reserve(d)
            self.assertFalse(has_reserve(d))

    def test_zero_bytes_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(create_reserve(d, 0))

    def test_negative_bytes_returns_none(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertIsNone(create_reserve(d, -100))

    def test_has_reserve_false_initially(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(has_reserve(d))

    def test_release_nonexistent_no_error(self):
        with tempfile.TemporaryDirectory() as d:
            release_reserve(d)

    def test_get_free_space(self):
        with tempfile.TemporaryDirectory() as d:
            free = _get_free_space(d)
            self.assertIsNotNone(free)
            self.assertGreater(free, 0)


if __name__ == "__main__":
    unittest.main()
