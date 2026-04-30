"""Tests for fileorganizer/thumbnail_cache.py.

These tests exercise the cache key, the synthetic extension-badge renderer,
the synchronous render_pixmap() fallback, and the QPixmapCache round-trip.
PSD parsing is not exercised in CI (psd_tools is optional and the heavy
parse path is best validated against real assets).

A QApplication is required because QPixmap construction touches the Qt
graphics platform; we use the offscreen platform so this works headless.
"""
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PyQt6.QtGui import QPixmap
from PyQt6.QtWidgets import QApplication

from fileorganizer import thumbnail_cache as tc


_app = QApplication.instance() or QApplication(sys.argv)


class CacheKey(unittest.TestCase):
    def test_cache_key_normalizes_path(self):
        a = tc._cache_key(r"C:\foo\bar.png")
        b = tc._cache_key(r"C:\FOO\BAR.PNG")
        self.assertEqual(a, b, "cache key must be case-insensitive on Windows")

    def test_cache_key_includes_size(self):
        self.assertNotEqual(
            tc._cache_key("foo.png", 32),
            tc._cache_key("foo.png", 64),
            "different sizes must yield different cache keys",
        )


class ExtensionBadge(unittest.TestCase):
    def test_badge_returns_valid_pixmap(self):
        pm = tc.extension_badge(".aep", 64)
        self.assertIsInstance(pm, QPixmap)
        self.assertFalse(pm.isNull())
        self.assertEqual(pm.width(), 64)
        self.assertEqual(pm.height(), 64)

    def test_empty_extension_still_renders(self):
        pm = tc.extension_badge("", 32)
        self.assertFalse(pm.isNull())

    def test_palette_is_stable_per_extension(self):
        a = tc._badge_color_for(".psd")
        b = tc._badge_color_for(".psd")
        c = tc._badge_color_for(".aep")
        self.assertEqual(a, b, "same extension must hash to the same color")
        self.assertNotEqual(a, c, "different extensions should typically differ")


class CacheRoundTrip(unittest.TestCase):
    def test_cache_pixmap_then_lookup(self):
        path = r"C:\nonexistent\probe.png"
        pm = tc.extension_badge(".png", 64)
        # Warm the cache, then fetch.
        tc.cache_pixmap(path, pm)
        got = tc.cached_pixmap(path)
        self.assertIsNotNone(got)
        self.assertFalse(got.isNull())

    def test_lookup_miss_returns_none(self):
        # Use a path nothing has ever cached.
        self.assertIsNone(tc.cached_pixmap(r"C:\never\cached\xxxxx.png"))

    def test_cache_ignores_null_pixmap(self):
        path = r"C:\nonexistent\null.png"
        tc.cache_pixmap(path, QPixmap())   # null pixmap
        self.assertIsNone(tc.cached_pixmap(path))


class RenderFallback(unittest.TestCase):
    def test_render_missing_path_returns_badge(self):
        # Path doesn't exist on disk → falls through to extension badge.
        pm = tc.render_pixmap(r"C:\does-not-exist\x.png", ext=".png", size=48)
        self.assertFalse(pm.isNull())
        self.assertEqual(pm.width(), 48)

    def test_render_empty_path_returns_badge(self):
        pm = tc.render_pixmap("", ext=".aep", size=32)
        self.assertFalse(pm.isNull())


class LoaderWorkerContract(unittest.TestCase):
    def test_queue_and_stop_does_not_hang(self):
        """The loader's stop() must unblock its queue.get() promptly."""
        worker = tc.ThumbnailLoaderWorker()
        worker.start()
        # Push one job pointing at a missing file (worker will fall back to
        # an extension badge), then stop.
        worker.queue(0, r"C:\does-not-exist\probe.png", ".png")
        worker.stop()
        # If stop() doesn't unblock the queue, this wait() will time out.
        self.assertTrue(worker.wait(3000), "worker did not exit on stop()")


if __name__ == "__main__":
    unittest.main()
