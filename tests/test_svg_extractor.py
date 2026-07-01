"""Tests for fileorganizer.svg_extractor — NEXT-78 SVG metadata extraction."""
import os
import tempfile
import unittest

from fileorganizer.svg_extractor import extract_svg_metadata

_SIMPLE_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 200 100">
  <title>Test Icon</title>
  <desc>A test SVG file</desc>
  <rect width="200" height="100" fill="blue"/>
</svg>"""

_ICON_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">
  <path d="M12 2L2 22h20z"/>
</svg>"""

_ANIMATED_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100">
  <circle cx="50" cy="50" r="40">
    <animate attributeName="r" from="40" to="10" dur="1s" repeatCount="indefinite"/>
  </circle>
</svg>"""

_RDF_SVG = """<?xml version="1.0"?>
<svg xmlns="http://www.w3.org/2000/svg"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     width="500" height="500">
  <metadata>
    <rdf:RDF>
      <rdf:Description>
        <dc:title>RDF Title</dc:title>
        <dc:creator>Test Author</dc:creator>
        <dc:date>2026-01-15</dc:date>
        <dc:rights>CC-BY-4.0</dc:rights>
      </rdf:Description>
    </rdf:RDF>
  </metadata>
  <rect width="500" height="500"/>
</svg>"""


def _write_svg(content):
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".svg", delete=False, encoding="utf-8")
    f.write(content)
    f.close()
    return f.name


class TestExtractSvgMetadata(unittest.TestCase):
    def test_simple_svg(self):
        path = _write_svg(_SIMPLE_SVG)
        try:
            meta = extract_svg_metadata(path)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["title"], "Test Icon")
            self.assertEqual(meta["description"], "A test SVG file")
            self.assertEqual(meta["width"], 200)
            self.assertEqual(meta["height"], 100)
            self.assertFalse(meta["has_animation"])
            self.assertEqual(meta["svg_type"], "illustration")
        finally:
            os.unlink(path)

    def test_icon_svg(self):
        path = _write_svg(_ICON_SVG)
        try:
            meta = extract_svg_metadata(path)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["svg_type"], "icon")
            self.assertEqual(meta["width"], 24)
            self.assertEqual(meta["height"], 24)
        finally:
            os.unlink(path)

    def test_animated_svg(self):
        path = _write_svg(_ANIMATED_SVG)
        try:
            meta = extract_svg_metadata(path)
            self.assertIsNotNone(meta)
            self.assertTrue(meta["has_animation"])
            self.assertEqual(meta["svg_type"], "animation")
        finally:
            os.unlink(path)

    def test_rdf_metadata(self):
        path = _write_svg(_RDF_SVG)
        try:
            meta = extract_svg_metadata(path)
            self.assertIsNotNone(meta)
            self.assertEqual(meta["title"], "RDF Title")
            self.assertEqual(meta["author"], "Test Author")
            self.assertEqual(meta["creation_date"], "2026-01-15")
            self.assertEqual(meta["license"], "CC-BY-4.0")
        finally:
            os.unlink(path)

    def test_nonexistent_file(self):
        self.assertIsNone(extract_svg_metadata("/nonexistent/file.svg"))

    def test_invalid_xml(self):
        path = _write_svg("not xml at all <<>>")
        try:
            self.assertIsNone(extract_svg_metadata(path))
        finally:
            os.unlink(path)

    def test_viewbox_fallback_dimensions(self):
        svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 300 150"><rect/></svg>'
        path = _write_svg(svg)
        try:
            meta = extract_svg_metadata(path)
            self.assertEqual(meta["width"], 300)
            self.assertEqual(meta["height"], 150)
        finally:
            os.unlink(path)


if __name__ == "__main__":
    unittest.main()
