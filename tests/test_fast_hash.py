"""Tests for fileorganizer.fast_hash — NEXT-33 fast fingerprint mode."""
import os
import tempfile
import unittest

from fileorganizer.fast_hash import (
    hash_file, partial_hash, tiered_hash,
    default_algo, available_algorithms,
    ALGO_SHA256, ALGO_BLAKE3,
)


def _make_file(size=1024):
    f = tempfile.NamedTemporaryFile(delete=False)
    f.write(os.urandom(size))
    f.close()
    return f.name


class TestHashFile(unittest.TestCase):
    def test_sha256_hash(self):
        path = _make_file()
        try:
            result = hash_file(path, algo=ALGO_SHA256)
            self.assertIsNotNone(result)
            digest, algo = result
            self.assertEqual(algo, ALGO_SHA256)
            self.assertEqual(len(digest), 64)
        finally:
            os.unlink(path)

    def test_default_algo(self):
        path = _make_file()
        try:
            result = hash_file(path)
            self.assertIsNotNone(result)
            _, algo = result
            self.assertIn(algo, available_algorithms())
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        self.assertIsNone(hash_file("/nonexistent/file.bin"))

    def test_same_content_same_hash(self):
        content = b"test content for hashing"
        f1 = tempfile.NamedTemporaryFile(delete=False)
        f1.write(content)
        f1.close()
        f2 = tempfile.NamedTemporaryFile(delete=False)
        f2.write(content)
        f2.close()
        try:
            h1 = hash_file(f1.name, algo=ALGO_SHA256)
            h2 = hash_file(f2.name, algo=ALGO_SHA256)
            self.assertEqual(h1[0], h2[0])
        finally:
            os.unlink(f1.name)
            os.unlink(f2.name)

    def test_different_content_different_hash(self):
        f1 = _make_file()
        f2 = _make_file()
        try:
            h1 = hash_file(f1, algo=ALGO_SHA256)
            h2 = hash_file(f2, algo=ALGO_SHA256)
            self.assertNotEqual(h1[0], h2[0])
        finally:
            os.unlink(f1)
            os.unlink(f2)


class TestPartialHash(unittest.TestCase):
    def test_partial_hash_short_file(self):
        path = _make_file(size=100)
        try:
            result = partial_hash(path)
            self.assertIsNotNone(result)
        finally:
            os.unlink(path)

    def test_partial_hash_large_file(self):
        path = _make_file(size=200000)
        try:
            p = partial_hash(path)
            f = hash_file(path)
            self.assertIsNotNone(p)
            self.assertIsNotNone(f)
            # Partial and full should differ for large files
            self.assertNotEqual(p[0], f[0])
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        self.assertIsNone(partial_hash("/nonexistent/file.bin"))


class TestTieredHash(unittest.TestCase):
    def test_returns_three_values(self):
        path = _make_file(size=200000)
        try:
            result = tiered_hash(path)
            self.assertIsNotNone(result)
            size_key, partial_digest, full_digest = result
            self.assertEqual(size_key, "200000")
            self.assertIsInstance(partial_digest, str)
            self.assertIsInstance(full_digest, str)
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        self.assertIsNone(tiered_hash("/nonexistent/file.bin"))


class TestAvailableAlgorithms(unittest.TestCase):
    def test_always_includes_sha256(self):
        algos = available_algorithms()
        self.assertIn(ALGO_SHA256, algos)

    def test_default_algo_is_available(self):
        self.assertIn(default_algo(), available_algorithms())


if __name__ == "__main__":
    unittest.main()
