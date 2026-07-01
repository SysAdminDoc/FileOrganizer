"""Tests for fileorganizer.scan_timer — NEXT-31 scan time measurement."""
import time
import unittest

from fileorganizer.scan_timer import ScanTimer

_SLEEP = 0.05  # 50ms — enough to be reliably measurable on CI


class TestScanTimer(unittest.TestCase):
    def test_start_stop_records_time(self):
        t = ScanTimer()
        t.start("classify")
        time.sleep(_SLEEP)
        t.stop()
        self.assertGreater(t.elapsed_ms("classify"), 20)

    def test_multiple_phases(self):
        t = ScanTimer()
        t.start("index")
        time.sleep(_SLEEP)
        t.start("classify")
        time.sleep(_SLEEP)
        t.stop()
        self.assertGreater(t.elapsed_ms("index"), 20)
        self.assertGreater(t.elapsed_ms("classify"), 20)

    def test_total_ms(self):
        t = ScanTimer()
        t.start("a")
        time.sleep(_SLEEP)
        t.start("b")
        time.sleep(_SLEEP)
        t.stop()
        self.assertGreater(t.total_ms(), 50)

    def test_unrecorded_phase_zero(self):
        t = ScanTimer()
        self.assertEqual(t.elapsed_ms("nonexistent"), 0)

    def test_summary_dict(self):
        t = ScanTimer()
        t.start("phase1")
        time.sleep(_SLEEP)
        t.stop()
        s = t.summary()
        self.assertIn("phase1", s)
        self.assertIsInstance(s["phase1"], int)

    def test_format_summary_string(self):
        t = ScanTimer()
        t.start("scan")
        time.sleep(_SLEEP)
        t.stop()
        result = t.format_summary()
        self.assertIn("scan:", result)
        self.assertIn("Total:", result)

    def test_reset_clears(self):
        t = ScanTimer()
        t.start("x")
        time.sleep(_SLEEP)
        t.stop()
        t.reset()
        self.assertEqual(t.elapsed_ms("x"), 0)
        self.assertEqual(t.total_ms(), 0)

    def test_run_elapsed_ms(self):
        t = ScanTimer()
        time.sleep(_SLEEP)
        self.assertGreater(t.run_elapsed_ms(), 20)

    def test_accumulates_same_phase(self):
        t = ScanTimer()
        t.start("x")
        time.sleep(_SLEEP)
        t.stop()
        t.start("x")
        time.sleep(_SLEEP)
        t.stop()
        self.assertGreater(t.elapsed_ms("x"), 50)


if __name__ == "__main__":
    unittest.main()
