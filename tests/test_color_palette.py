from __future__ import annotations

from pathlib import Path

from PIL import Image

from fileorganizer.color_palette import (
    extract_palette,
    hex_to_rgb,
    min_delta_e,
    palette_from_bytes,
    palette_to_bytes,
    rgb_to_hex,
)
from fileorganizer.metadata import MetadataExtractor


def test_extract_palette_finds_dominant_color(tmp_path: Path):
    img_path = tmp_path / "red.png"
    image = Image.new("RGB", (80, 80), (240, 20, 20))
    for x in range(20):
        for y in range(80):
            image.putpixel((x, y), (20, 40, 220))
    image.save(img_path)

    palette = extract_palette(img_path)

    assert palette is not None
    assert palette.hex
    r, g, b = palette.rgb[0]
    assert r > 200
    assert g < 60
    assert b < 60


def test_palette_bytes_and_delta_e_roundtrip():
    colors = [(255, 0, 0), (0, 128, 255)]
    packed = palette_to_bytes(colors)

    assert palette_from_bytes(packed) == colors
    assert rgb_to_hex(colors[0]) == "#ff0000"
    assert hex_to_rgb("#08f") == (0, 136, 255)
    assert min_delta_e(colors, (250, 5, 5)) < 5
    assert min_delta_e(colors, (0, 255, 0)) > 50


def test_metadata_extractor_adds_palette_fields(tmp_path: Path):
    img_path = tmp_path / "green.png"
    Image.new("RGB", (16, 16), (20, 200, 40)).save(img_path)

    meta = MetadataExtractor.extract(str(img_path))

    assert meta["_type"] == "image"
    assert meta["_palette_hex"]
    assert meta["_palette_rgb"]
    assert len(bytes.fromhex(meta["_palette_rgb_bytes"])) % 3 == 0
    assert "palette" in MetadataExtractor.format_summary(meta)
