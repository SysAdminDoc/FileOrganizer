"""Dominant color palette extraction and matching."""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class Palette:
    rgb: list[tuple[int, int, int]]
    hex: list[str]
    lab: list[tuple[float, float, float]]


_RASTER_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_PSD_EXTS = {".psd", ".psb"}


def extract_palette(path: str | Path, max_colors: int = 5, sample_size: int = 160) -> Optional[Palette]:
    """Extract up to max_colors dominant RGB swatches from an image-like file."""
    p = Path(path)
    if max_colors <= 0 or not p.is_file() or p.suffix.lower() not in (_RASTER_EXTS | _PSD_EXTS):
        return None
    try:
        image = _open_image(p)
    except Exception:
        return None
    if image is None:
        return None
    try:
        image.thumbnail((sample_size, sample_size))
        rgb_image = _flatten_to_rgb(image)
        colors = _dominant_colors(rgb_image, max_colors)
    finally:
        try:
            image.close()
        except Exception:
            pass
    if not colors:
        return None
    return Palette(
        rgb=colors,
        hex=[rgb_to_hex(c) for c in colors],
        lab=[rgb_to_lab(c) for c in colors],
    )


def palette_to_bytes(colors: Iterable[tuple[int, int, int]]) -> bytes:
    """Pack RGB swatches as a 5x3 byte-style blob."""
    out = bytearray()
    for r, g, b in list(colors)[:5]:
        out.extend((_clamp_byte(r), _clamp_byte(g), _clamp_byte(b)))
    return bytes(out)


def palette_from_bytes(data: bytes | bytearray | memoryview | None) -> list[tuple[int, int, int]]:
    if not data:
        return []
    raw = bytes(data)
    return [tuple(raw[i:i + 3]) for i in range(0, len(raw) - 2, 3)]


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#{:02x}{:02x}{:02x}".format(*(_clamp_byte(v) for v in rgb))


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6:
        raise ValueError(f"Invalid RGB hex color: {value!r}")
    return int(text[0:2], 16), int(text[2:4], 16), int(text[4:6], 16)


def min_delta_e(palette: Iterable[tuple[int, int, int]], target: tuple[int, int, int]) -> float:
    target_lab = rgb_to_lab(target)
    best = math.inf
    for rgb in palette:
        best = min(best, delta_e(rgb_to_lab(rgb), target_lab))
    return best


def delta_e(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    """CIE76 distance, sufficient for palette filtering."""
    return math.sqrt(sum((a[i] - b[i]) ** 2 for i in range(3)))


def rgb_to_lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(_clamp_byte(v) / 255.0) for v in rgb)
    x = r * 0.4124564 + g * 0.3575761 + b * 0.1804375
    y = r * 0.2126729 + g * 0.7151522 + b * 0.0721750
    z = r * 0.0193339 + g * 0.1191920 + b * 0.9503041
    x /= 0.95047
    y /= 1.00000
    z /= 1.08883
    fx, fy, fz = (_lab_f(v) for v in (x, y, z))
    return (116.0 * fy - 16.0, 500.0 * (fx - fy), 200.0 * (fy - fz))


def _open_image(path: Path):
    ext = path.suffix.lower()
    if ext in _PSD_EXTS:
        try:
            from fileorganizer.psd_safe import safe_psd_open
            psd = safe_psd_open(str(path))
            if psd is None:
                return None
            return psd.composite() if hasattr(psd, "composite") else psd.topil()
        except Exception:
            return None
    from PIL import Image
    return Image.open(path)


def _flatten_to_rgb(image):
    from PIL import Image

    if image.mode in ("RGBA", "LA") or image.info.get("transparency") is not None:
        rgba = image.convert("RGBA")
        bg = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        bg.alpha_composite(rgba)
        return bg.convert("RGB")
    return image.convert("RGB")


def _dominant_colors(image, max_colors: int) -> list[tuple[int, int, int]]:
    if image.width == 0 or image.height == 0:
        return []
    quantized = image.quantize(colors=max_colors, method=2)
    palette = quantized.getpalette() or []
    counts = quantized.getcolors(maxcolors=image.width * image.height) or []
    ranked: list[tuple[int, tuple[int, int, int]]] = []
    for count, index in counts:
        offset = index * 3
        if offset + 2 >= len(palette):
            continue
        rgb = tuple(int(v) for v in palette[offset:offset + 3])
        ranked.append((count, rgb))
    ranked.sort(key=lambda row: row[0], reverse=True)
    colors: list[tuple[int, int, int]] = []
    for _count, rgb in ranked:
        if rgb not in colors:
            colors.append(rgb)
        if len(colors) >= max_colors:
            break
    return colors


def _srgb_to_linear(value: float) -> float:
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


def _lab_f(value: float) -> float:
    if value > 0.008856:
        return value ** (1.0 / 3.0)
    return (7.787 * value) + (16.0 / 116.0)


def _clamp_byte(value: int | float) -> int:
    return max(0, min(255, int(round(value))))
