"""Tests for fileorganizer.provider_cost_manager — NEXT-34 cost cap, backoff, failover."""
import os
import tempfile
import unittest
from unittest.mock import patch

import fileorganizer.provider_cost_manager as pcm


class TestProviderCostManager(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_db = pcm._COST_DB
        pcm._COST_DB = os.path.join(self._tmp, "test_costs.db")
        pcm._init_db()

    def tearDown(self):
        pcm._COST_DB = self._orig_db

    def test_record_api_call_tracks_cost(self):
        pcm.record_api_call("deepseek", 1000)
        cost = pcm.get_daily_cost("deepseek")
        self.assertGreater(cost, 0)

    def test_ollama_has_zero_cost(self):
        pcm.record_api_call("ollama", 10000)
        cost = pcm.get_daily_cost("ollama")
        self.assertEqual(cost, 0.0)

    def test_is_over_budget_false_initially(self):
        self.assertFalse(pcm.is_over_budget("deepseek"))

    def test_is_over_budget_true_when_exceeded(self):
        pcm.record_api_call("deepseek", 1000)
        self.assertTrue(pcm.is_over_budget("deepseek", daily_budget=0.0001))

    def test_set_and_check_backoff(self):
        pcm.set_backoff("deepseek", 60, "test")
        locked, remaining = pcm.is_locked("deepseek")
        self.assertTrue(locked)
        self.assertIsNotNone(remaining)
        self.assertGreater(remaining, 0)

    def test_clear_backoff(self):
        pcm.set_backoff("deepseek", 60, "test")
        pcm.clear_backoff("deepseek")
        locked, _ = pcm.is_locked("deepseek")
        self.assertFalse(locked)

    def test_not_locked_initially(self):
        locked, remaining = pcm.is_locked("deepseek")
        self.assertFalse(locked)
        self.assertIsNone(remaining)

    def test_max_backoff_capped(self):
        pcm.set_backoff("deepseek", 999999, "test")
        locked, remaining = pcm.is_locked("deepseek")
        self.assertTrue(locked)
        self.assertLessEqual(remaining, pcm._MAX_BACKOFF_SECONDS + 1)

    def test_failover_chain_order(self):
        chain = pcm.get_failover_chain()
        self.assertEqual(chain, ["deepseek", "github", "ollama"])

    def test_get_next_available_provider(self):
        provider = pcm.get_next_available_provider()
        self.assertEqual(provider, "deepseek")

    def test_get_next_available_skips_locked(self):
        pcm.set_backoff("deepseek", 3600, "test")
        provider = pcm.get_next_available_provider()
        self.assertEqual(provider, "github")

    def test_get_next_available_skips_specified(self):
        provider = pcm.get_next_available_provider(skip=["deepseek"])
        self.assertEqual(provider, "github")

    def test_get_next_available_returns_none_all_locked(self):
        for p in pcm.get_failover_chain():
            pcm.set_backoff(p, 3600, "test")
        provider = pcm.get_next_available_provider()
        self.assertIsNone(provider)

    def test_handle_rate_limit_response(self):
        headers = {
            "X-RateLimit-Limit": "100",
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1719900000",
        }
        pcm.handle_rate_limit_response("deepseek", headers)
        locked, _ = pcm.is_locked("deepseek")
        self.assertTrue(locked)

    def test_get_cost_summary_empty(self):
        summary = pcm.get_cost_summary()
        self.assertIsInstance(summary, dict)

    def test_get_cost_summary_with_data(self):
        pcm.record_api_call("deepseek", 5000)
        summary = pcm.get_cost_summary()
        self.assertIn("deepseek", summary)
        self.assertGreater(summary["deepseek"]["cost_usd"], 0)
        self.assertEqual(summary["deepseek"]["requests"], 1)

    def test_multiple_calls_accumulate(self):
        pcm.record_api_call("github", 1000)
        pcm.record_api_call("github", 2000)
        cost = pcm.get_daily_cost("github")
        self.assertGreater(cost, 0)


if __name__ == "__main__":
    unittest.main()
