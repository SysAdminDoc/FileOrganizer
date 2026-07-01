"""Tests for fileorganizer.watch_daemon — NEXT-60 watchfiles foundation."""
import os
import tempfile
import time
import unittest

from fileorganizer.watch_daemon import WatchDaemon, WatchConfig, FileEvent


class TestWatchConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = WatchConfig()
        self.assertEqual(cfg.debounce_ms, 30000)
        self.assertEqual(cfg.max_queue, 1000)
        self.assertTrue(cfg.recursive)

    def test_custom_config(self):
        cfg = WatchConfig(paths=["/tmp"], debounce_ms=5000, max_queue=100)
        self.assertEqual(cfg.debounce_ms, 5000)
        self.assertEqual(cfg.max_queue, 100)


class TestWatchDaemon(unittest.TestCase):
    def test_enqueue_and_pending_count(self):
        cfg = WatchConfig(debounce_ms=60000)
        daemon = WatchDaemon(cfg)
        daemon._enqueue("/tmp/file1.txt", "added")
        daemon._enqueue("/tmp/file2.txt", "modified")
        self.assertEqual(daemon.pending_count(), 2)

    def test_enqueue_updates_existing(self):
        cfg = WatchConfig(debounce_ms=60000)
        daemon = WatchDaemon(cfg)
        daemon._enqueue("/tmp/file1.txt", "added")
        daemon._enqueue("/tmp/file1.txt", "modified")
        self.assertEqual(daemon.pending_count(), 1)
        self.assertEqual(daemon._queue["/tmp/file1.txt"].change_type, "modified")

    def test_should_ignore(self):
        cfg = WatchConfig()
        daemon = WatchDaemon(cfg)
        self.assertTrue(daemon._should_ignore("/tmp/__pycache__"))
        self.assertTrue(daemon._should_ignore("/tmp/.DS_Store"))
        self.assertFalse(daemon._should_ignore("/tmp/design.psd"))

    def test_max_queue_enforced(self):
        cfg = WatchConfig(max_queue=5, debounce_ms=60000)
        daemon = WatchDaemon(cfg)
        for i in range(10):
            daemon._enqueue(f"/tmp/file{i}.txt", "added")
        self.assertLessEqual(daemon.pending_count(), 5)

    def test_get_stable_paths_empty(self):
        cfg = WatchConfig(debounce_ms=60000)
        daemon = WatchDaemon(cfg)
        self.assertEqual(daemon.get_stable_paths(), [])

    def test_get_stable_paths_after_debounce(self):
        cfg = WatchConfig(debounce_ms=10)
        daemon = WatchDaemon(cfg)
        daemon._enqueue("/tmp/file.txt", "added")
        time.sleep(0.05)
        stable = daemon.get_stable_paths()
        self.assertEqual(len(stable), 1)
        self.assertEqual(stable[0].path, "/tmp/file.txt")
        self.assertEqual(daemon.pending_count(), 0)

    def test_get_stable_paths_not_yet(self):
        cfg = WatchConfig(debounce_ms=60000)
        daemon = WatchDaemon(cfg)
        daemon._enqueue("/tmp/file.txt", "added")
        stable = daemon.get_stable_paths()
        self.assertEqual(len(stable), 0)
        self.assertEqual(daemon.pending_count(), 1)

    def test_scan_dir(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "test.txt"), "w").close()
            cfg = WatchConfig()
            daemon = WatchDaemon(cfg)
            result = daemon._scan_dir(d)
            self.assertEqual(len(result), 1)

    def test_scan_dir_ignores_patterns(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "test.txt"), "w").close()
            open(os.path.join(d, "Thumbs.db"), "w").close()
            cfg = WatchConfig()
            daemon = WatchDaemon(cfg)
            result = daemon._scan_dir(d)
            self.assertEqual(len(result), 1)

    def test_stop(self):
        cfg = WatchConfig()
        daemon = WatchDaemon(cfg)
        daemon._running = True
        daemon.stop()
        self.assertFalse(daemon._running)


if __name__ == "__main__":
    unittest.main()
