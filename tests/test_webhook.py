"""Tests for fileorganizer.webhook — NEXT-28 webhook notifications."""
import json
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

import fileorganizer.webhook as wh


class TestWebhook(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig = wh._SETTINGS_FILE
        wh._SETTINGS_FILE = os.path.join(self._tmp, "webhook_settings.json")

    def tearDown(self):
        wh._SETTINGS_FILE = self._orig

    def test_load_empty_returns_empty(self):
        self.assertEqual(wh.load_webhook_urls(), [])

    def test_save_and_load(self):
        urls = ["https://example.com/hook", "https://other.com/hook"]
        wh.save_webhook_urls(urls)
        loaded = wh.load_webhook_urls()
        self.assertEqual(loaded, urls)

    def test_build_payload(self):
        payload = wh.build_payload("run-1", 10, 2, {"AE": 5, "PS": 7}, "design")
        self.assertEqual(payload["event"], "organize_complete")
        self.assertEqual(payload["run_id"], "run-1")
        self.assertEqual(payload["ok"], 10)
        self.assertEqual(payload["errors"], 2)
        self.assertEqual(payload["total"], 12)
        self.assertEqual(payload["source"], "design")
        self.assertEqual(payload["categories"]["AE"], 5)

    @patch("fileorganizer.webhook.urlopen")
    def test_send_webhook_success(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp
        result = wh.send_webhook("https://example.com/hook", {"test": True})
        self.assertTrue(result)

    @patch("fileorganizer.webhook.urlopen", side_effect=Exception("timeout"))
    def test_send_webhook_failure(self, _):
        result = wh.send_webhook("https://example.com/hook", {"test": True})
        self.assertFalse(result)

    def test_notify_all_no_urls(self):
        wh.notify_all("run-1", 5, 0, {"AE": 5})

    @patch("fileorganizer.webhook.send_webhook")
    def test_notify_all_fires_webhooks(self, mock_send):
        wh.save_webhook_urls(["https://a.com/hook", "https://b.com/hook"])
        mock_send.return_value = True
        wh.notify_all("run-1", 5, 0, {"AE": 5})
        import time
        time.sleep(0.2)
        self.assertTrue(mock_send.called)

    def test_blocks_file_url(self):
        result = wh.send_webhook("file:///etc/passwd", {"test": True})
        self.assertFalse(result)

    def test_blocks_localhost_url(self):
        result = wh.send_webhook("http://localhost:8080/hook", {"test": True})
        self.assertFalse(result)

    def test_blocks_metadata_url(self):
        result = wh.send_webhook("http://169.254.169.254/latest/", {"test": True})
        self.assertFalse(result)

    def test_allows_https_url(self):
        self.assertTrue(wh._is_safe_url("https://example.com/hook"))

    def test_blocks_ftp_url(self):
        self.assertFalse(wh._is_safe_url("ftp://example.com/file"))


if __name__ == "__main__":
    unittest.main()
