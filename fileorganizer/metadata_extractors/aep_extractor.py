"""
After Effects project metadata extractor.

Adobe After Effects .aep files use a RIFX-style binary container. The full
format is proprietary, but the container header and embedded strings are stable
enough to extract useful classification hints without a parser dependency.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path
from typing import Iterable, Optional

from ._types import MetadataHint

_CAT_OTHER = "After Effects - Other"

_CATEGORY_RULES = [
    (re.compile(r"\b(logo|brand|ident)\b", re.I), "After Effects - Logo Reveal"),
    (re.compile(r"\b(slideshow|slide show|photo album|gallery)\b", re.I), "After Effects - Slideshow"),
    (re.compile(r"\b(lower third|lower-third)\b", re.I), "After Effects - Lower Thirds"),
    (re.compile(r"\b(title|typography|text animation|kinetic type)\b", re.I), "After Effects - Title & Typography"),
    (re.compile(r"\b(broadcast|news|tv package)\b", re.I), "After Effects - Broadcast Package"),
    (re.compile(r"\b(social media|instagram|tiktok|reels?|stories|story)\b", re.I), "After Effects - Social Media"),
    (re.compile(r"\b(particle|element 3d|trapcode|particular|plexus|stardust)\b", re.I), "After Effects - 3D & Particle"),
    (re.compile(r"\b(wedding|romance|love story)\b", re.I), "After Effects - Wedding & Romance"),
    (re.compile(r"\b(intro|opener|opening)\b", re.I), "After Effects - Intro & Opener"),
    (re.compile(r"\b(promo|product|commercial)\b", re.I), "After Effects - Product Promo"),
]

_PLUGIN_RX = re.compile(
    r"\b("
    r"trapcode|particular|form|mir|stardust|plexus|element 3d|saber|"
    r"optical flares|red giant|boris|continuum|mocha|duik|newton|"
    r"video copilot|magic bullet"
    r")\b",
    re.I,
)
_VERSION_RX = re.compile(
    r"\b(?:after effects|ae|cc|cs)\s*(?:cc\s*)?(cs\d(?:\.\d)?|20\d{2}|\d{2}\.\d)\b",
    re.I,
)
_RESOLUTION_RX = re.compile(r"\b([1-9]\d{2,4})\s*[xX]\s*([1-9]\d{2,4})\b")
_DURATION_RX = re.compile(
    r"\b(?:duration|dur|length)\s*[:=]?\s*"
    r"(?:(\d{1,2}):([0-5]\d):([0-5]\d)(?::([0-5]\d))?|(\d+(?:\.\d+)?)\s*(?:s|sec|secs|seconds))\b",
    re.I,
)
_TIMECODE_RX = re.compile(r"\b(\d{1,2}):([0-5]\d):([0-5]\d)(?::([0-5]\d))?\b")
_FRAME_RATE_RX = re.compile(
    r"\b(23\.976|24(?:\.0+)?|25(?:\.0+)?|29\.97|30(?:\.0+)?|50(?:\.0+)?|59\.94|60(?:\.0+)?)\s*"
    r"(?:fps|frames/sec|frames per second)\b",
    re.I,
)
_NOISE_RX = re.compile(
    r"^(?:rifx|riff|egg!|utf8|xmp|xml|adobe after effects|composition|project|"
    r"null|nulls|solid|camera|light|footage|assets?|render queue)$",
    re.I,
)
_EXT_RX = re.compile(r"\.(?:aep|aepx|psd|png|jpe?g|mov|mp4|wav|mp3|ai|eps)$", re.I)

_MAX_SCAN_BYTES = 16 * 1024 * 1024


def extract(path: Path) -> Optional[MetadataHint]:
    """Extract .aep RIFX metadata and return an After Effects category hint."""
    if not path or not path.exists() or path.suffix.lower() != ".aep":
        return None
    try:
        data = path.read_bytes()[:_MAX_SCAN_BYTES]
    except OSError:
        return None

    header = _parse_header(data)
    if header is None:
        return None

    strings = _extract_strings(data, str(header["endian"]))
    composition_names = _composition_candidates(strings)
    required_plugins = _plugin_names(strings)
    ae_versions = _version_names(strings)
    resolutions = _resolution_pairs(strings)
    durations = _duration_values(strings)
    frame_rates = _frame_rate_values(strings)
    chunk_types = _chunk_types(data, header["endian"])

    category, confidence, reason = _route_category(
        path.stem,
        composition_names,
        required_plugins,
        strings,
    )

    return MetadataHint(
        category=category,
        confidence=confidence,
        extractor="aep",
        reason=reason,
        raw={
            "container": header["container"],
            "form_type": header["form_type"],
            "container_size": header["container_size"],
            "chunk_types": chunk_types,
            "composition_names": composition_names,
            "required_plugins": required_plugins,
            "ae_versions": ae_versions,
            "resolutions": resolutions,
            "durations": durations,
            "frame_rates": frame_rates,
            "sample_strings": strings[:20],
        },
    )


def _parse_header(data: bytes) -> Optional[dict[str, object]]:
    if len(data) < 12:
        return None
    container = data[:4]
    if container not in {b"RIFX", b"RIFF"}:
        return None
    endian = ">" if container == b"RIFX" else "<"
    try:
        container_size = struct.unpack(f"{endian}I", data[4:8])[0]
    except struct.error:
        return None
    form_type = data[8:12].decode("latin-1", errors="replace")
    return {
        "container": container.decode("ascii"),
        "endian": endian,
        "container_size": container_size,
        "form_type": form_type,
    }


def _chunk_types(data: bytes, endian: str) -> list[str]:
    out: list[str] = []
    pos = 12
    max_pos = len(data)
    while pos + 8 <= max_pos and len(out) < 64:
        chunk_id = data[pos:pos + 4]
        try:
            chunk_name = chunk_id.decode("latin-1")
            chunk_size = struct.unpack(f"{endian}I", data[pos + 4:pos + 8])[0]
        except (UnicodeDecodeError, struct.error):
            break
        if not _looks_like_chunk_id(chunk_name) or chunk_size < 0:
            break
        out.append(chunk_name)
        pos += 8 + chunk_size + (chunk_size % 2)
    return out


def _chunk_payloads(data: bytes, endian: str) -> list[bytes]:
    payloads: list[bytes] = []
    pos = 12
    max_pos = len(data)
    while pos + 8 <= max_pos and len(payloads) < 64:
        chunk_id = data[pos:pos + 4]
        try:
            chunk_name = chunk_id.decode("latin-1")
            chunk_size = struct.unpack(f"{endian}I", data[pos + 4:pos + 8])[0]
        except (UnicodeDecodeError, struct.error):
            break
        if not _looks_like_chunk_id(chunk_name) or chunk_size < 0:
            break
        start = pos + 8
        end = start + chunk_size
        if end > max_pos:
            break
        payloads.append(data[start:end])
        pos = end + (chunk_size % 2)
    return payloads


def _looks_like_chunk_id(value: str) -> bool:
    return len(value) == 4 and all(32 <= ord(ch) <= 126 for ch in value)


def _extract_strings(data: bytes, endian: str) -> list[str]:
    strings: list[str] = []
    scan_blobs = _chunk_payloads(data, endian) or [data]
    for blob in scan_blobs:
        strings.extend(_extract_ascii_strings(blob))
        strings.extend(_extract_utf16_strings(blob, "big"))
        strings.extend(_extract_utf16_strings(blob, "little"))
    return _dedupe(_clean_string(s) for s in strings if _clean_string(s))


def _extract_ascii_strings(data: bytes, min_len: int = 4) -> Iterable[str]:
    buf = bytearray()
    for byte in data:
        if 32 <= byte <= 126:
            buf.append(byte)
            continue
        if len(buf) >= min_len:
            yield buf.decode("ascii", errors="ignore")
        buf.clear()
    if len(buf) >= min_len:
        yield buf.decode("ascii", errors="ignore")


def _extract_utf16_strings(data: bytes, byteorder: str, min_len: int = 4) -> Iterable[str]:
    for start in (0, 1):
        chars: list[str] = []
        for i in range(start, len(data) - 1, 2):
            code = int.from_bytes(data[i:i + 2], byteorder)
            if 32 <= code <= 126:
                chars.append(chr(code))
                continue
            if len(chars) >= min_len:
                yield "".join(chars)
            chars.clear()
        if len(chars) >= min_len:
            yield "".join(chars)


def _clean_string(value: str) -> str:
    value = re.sub(r"\s+", " ", value).strip(" \t\r\n\0")
    if len(value) < 3 or len(value) > 120:
        return ""
    if sum(ch.isalpha() for ch in value) < 2 and not (
        _RESOLUTION_RX.search(value) or _TIMECODE_RX.search(value) or _FRAME_RATE_RX.search(value)
    ):
        return ""
    if value.startswith(("http://", "https://", "xmlns:")):
        return ""
    return value


def _dedupe(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
        if len(out) >= 128:
            break
    return out


def _composition_candidates(strings: list[str]) -> list[str]:
    candidates: list[str] = []
    for value in strings:
        if _NOISE_RX.match(value) or _EXT_RX.search(value) or "\\" in value or "/" in value:
            continue
        words = re.findall(r"[A-Za-z][A-Za-z0-9]+", value)
        if len(words) >= 2 or re.search(r"\b(comp|main|final|intro|logo|title|scene|render)\b", value, re.I):
            candidates.append(value)
        if len(candidates) >= 12:
            break
    return candidates


def _plugin_names(strings: list[str]) -> list[str]:
    plugins: list[str] = []
    for value in strings:
        for match in _PLUGIN_RX.finditer(value):
            plugins.append(match.group(1).strip())
    return _dedupe(plugins)[:12]


def _version_names(strings: list[str]) -> list[str]:
    versions: list[str] = []
    for value in strings:
        for match in _VERSION_RX.finditer(value):
            versions.append(match.group(0).strip())
    return _dedupe(versions)[:8]


def _resolution_pairs(strings: list[str]) -> list[str]:
    resolutions: list[str] = []
    for value in strings:
        for width, height in _RESOLUTION_RX.findall(value):
            resolutions.append(f"{width}x{height}")
    return _dedupe(resolutions)[:8]


def _duration_values(strings: list[str]) -> list[str]:
    durations: list[str] = []
    for value in strings:
        for match in _DURATION_RX.finditer(value):
            if match.group(5):
                durations.append(f"{float(match.group(5)):.3g}s")
                continue
            hours, minutes, seconds, frames = (
                match.group(1),
                match.group(2),
                match.group(3),
                match.group(4),
            )
            durations.append(f"{hours}:{minutes}:{seconds}" + (f":{frames}" if frames else ""))
        for hours, minutes, seconds, frames in _TIMECODE_RX.findall(value):
            durations.append(f"{hours}:{minutes}:{seconds}" + (f":{frames}" if frames else ""))
    return _dedupe(durations)[:8]


def _frame_rate_values(strings: list[str]) -> list[float]:
    rates: list[str] = []
    for value in strings:
        rates.extend(match.group(1) for match in _FRAME_RATE_RX.finditer(value))
    return [float(rate) for rate in _dedupe(rates)[:8]]


def _route_category(
    file_stem: str,
    composition_names: list[str],
    required_plugins: list[str],
    strings: list[str],
) -> tuple[str, int, str]:
    text = " ".join([file_stem, *composition_names, *required_plugins, *strings[:20]])
    for pattern, category in _CATEGORY_RULES:
        if pattern.search(text):
            return category, 92, f"RIFX AEP metadata matched {category}"
    if composition_names or required_plugins:
        reason_bits = []
        if composition_names:
            reason_bits.append(f"comps: {', '.join(composition_names[:3])}")
        if required_plugins:
            reason_bits.append(f"plugins: {', '.join(required_plugins[:3])}")
        return _CAT_OTHER, 90, "; ".join(reason_bits)
    return _CAT_OTHER, 82, "valid RIFX AEP container"
