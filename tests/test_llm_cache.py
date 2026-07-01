"""Tests for llm_cache.py — NEXT-44 LLM response caching."""
import json
import os
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch

import llm_cache


class TestLlmCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_db = llm_cache.DB_FILE
        llm_cache.DB_FILE = os.path.join(self._tmp, "test_llm_cache.db")
        con = sqlite3.connect(str(llm_cache.DB_FILE))
        con.execute("""
            CREATE TABLE IF NOT EXISTS llm_cache (
                fingerprint  TEXT NOT NULL,
                model_id     TEXT NOT NULL,
                prompt_hash  TEXT NOT NULL,
                response_json TEXT NOT NULL,
                created_at   INTEGER NOT NULL,
                accessed_at  INTEGER NOT NULL,
                PRIMARY KEY (fingerprint, model_id, prompt_hash)
            )
        """)
        con.commit()
        con.close()

    def tearDown(self):
        llm_cache.DB_FILE = self._orig_db

    def test_prompt_hash_deterministic(self):
        h1 = llm_cache.prompt_hash("test prompt")
        h2 = llm_cache.prompt_hash("test prompt")
        self.assertEqual(h1, h2)

    def test_prompt_hash_different_inputs(self):
        h1 = llm_cache.prompt_hash("prompt A")
        h2 = llm_cache.prompt_hash("prompt B")
        self.assertNotEqual(h1, h2)

    @patch("llm_cache.folder_fingerprint", return_value="abc123")
    def test_store_and_lookup(self, _):
        response = {"category": "After Effects - Slideshow", "confidence": 85}
        llm_cache.store_cached("/tmp/folder", "deepseek-v4-flash", "classify this", response)
        result = llm_cache.lookup_cached("/tmp/folder", "deepseek-v4-flash", "classify this")
        self.assertIsNotNone(result)
        self.assertEqual(result["category"], "After Effects - Slideshow")

    @patch("llm_cache.folder_fingerprint", return_value="abc123")
    def test_lookup_miss(self, _):
        result = llm_cache.lookup_cached("/tmp/folder", "model-x", "unknown prompt")
        self.assertIsNone(result)

    @patch("llm_cache.folder_fingerprint", return_value="abc123")
    def test_lookup_expired(self, _):
        response = {"category": "Test"}
        llm_cache.store_cached("/tmp/folder", "model", "prompt", response)
        con = sqlite3.connect(str(llm_cache.DB_FILE))
        old_ts = int(time.time()) - (60 * 86400)
        con.execute("UPDATE llm_cache SET created_at=?, accessed_at=?", (old_ts, old_ts))
        con.commit()
        con.close()
        result = llm_cache.lookup_cached("/tmp/folder", "model", "prompt")
        self.assertIsNone(result)

    @patch("llm_cache.folder_fingerprint", return_value=None)
    def test_store_no_fingerprint(self, _):
        result = llm_cache.store_cached("/tmp/none", "model", "prompt", {"x": 1})
        self.assertFalse(result)

    @patch("llm_cache.folder_fingerprint", return_value="abc123")
    def test_cleanup_expired(self, _):
        response = {"category": "Test"}
        llm_cache.store_cached("/tmp/folder", "model", "prompt", response)
        con = sqlite3.connect(str(llm_cache.DB_FILE))
        old_ts = int(time.time()) - (60 * 86400)
        con.execute("UPDATE llm_cache SET accessed_at=?", (old_ts,))
        con.commit()
        con.close()
        deleted = llm_cache.cleanup_expired(max_age_days=30)
        self.assertEqual(deleted, 1)

    @patch("llm_cache.folder_fingerprint", return_value="abc123")
    def test_get_cache_stats(self, _):
        llm_cache.store_cached("/tmp/a", "model-a", "p1", {"x": 1})
        llm_cache.store_cached("/tmp/b", "model-b", "p2", {"x": 2})
        stats = llm_cache.get_cache_stats()
        self.assertEqual(stats["total_entries"], 2)
        self.assertIn("model-a", stats["by_model"])
        self.assertIn("model-b", stats["by_model"])


if __name__ == "__main__":
    unittest.main()
