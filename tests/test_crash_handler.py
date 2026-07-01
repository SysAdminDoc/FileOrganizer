"""Tests for fileorganizer.crash_handler — NEXT-38 crash handling."""
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

import fileorganizer.crash_handler as ch


class TestCrashHandler(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self._orig_log = ch._CRASH_LOG
        ch._CRASH_LOG = os.path.join(self._tmp, "test_crash.log")

    def tearDown(self):
        ch._CRASH_LOG = self._orig_log

    def test_record_crash_creates_log(self):
        try:
            raise ValueError("test error")
        except ValueError:
            import sys
            exc_type, exc_value, exc_tb = sys.exc_info()
            ch._record_crash(exc_type, exc_value, exc_tb, "TestThread")

        self.assertTrue(os.path.isfile(ch._CRASH_LOG))
        with open(ch._CRASH_LOG, "r") as f:
            content = f.read()
        self.assertIn("ValueError", content)
        self.assertIn("test error", content)
        self.assertIn("TestThread", content)

    def test_read_recent_crashes_empty(self):
        result = ch.read_recent_crashes()
        self.assertIn("No crashes", result)

    def test_read_recent_crashes_with_data(self):
        try:
            raise RuntimeError("crash test")
        except RuntimeError:
            import sys
            ch._record_crash(*sys.exc_info(), "Worker")

        result = ch.read_recent_crashes()
        self.assertIn("RuntimeError", result)

    def test_clear_crash_log(self):
        try:
            raise RuntimeError("test")
        except RuntimeError:
            import sys
            ch._record_crash(*sys.exc_info(), "Worker")

        self.assertTrue(os.path.isfile(ch._CRASH_LOG))
        ch.clear_crash_log()
        self.assertFalse(os.path.isfile(ch._CRASH_LOG))

    def test_get_crash_log_path(self):
        path = ch.get_crash_log_path()
        self.assertTrue(path.endswith("crash.log") or path.endswith("test_crash.log"))

    def test_callback_fires(self):
        messages = []
        ch._on_crash_callback = messages.append

        try:
            raise TypeError("callback test")
        except TypeError:
            import sys
            ch._record_crash(*sys.exc_info(), "Worker")

        ch._on_crash_callback = None
        self.assertEqual(len(messages), 1)
        self.assertIn("TypeError", messages[0])

    def test_install_sets_excepthook(self):
        original = sys.excepthook
        ch.install()
        self.assertEqual(sys.excepthook, ch._sys_excepthook)
        sys.excepthook = original

    def test_rotate_log(self):
        ch._MAX_LOG_SIZE = 100
        for i in range(50):
            try:
                raise RuntimeError(f"error {i}")
            except RuntimeError:
                import sys
                ch._record_crash(*sys.exc_info(), "Worker")

        size = os.path.getsize(ch._CRASH_LOG)
        self.assertLess(size, 100000)
        ch._MAX_LOG_SIZE = 5 * 1024 * 1024


if __name__ == "__main__":
    unittest.main()
