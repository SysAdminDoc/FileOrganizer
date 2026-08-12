"""Local Stable Diffusion / Flux generation metadata and routing.

The parser handles text chunks written by Automatic1111 and bounded JSON
prompt/workflow chunks written by ComfyUI. It never executes workflow nodes
and keeps only small, useful fields for classification and provenance.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

AI_ART_IMAGE_EXTENSIONS = [
    "jpg", "jpeg", "png", "webp", "tif", "tiff", "bmp", "avif",
]

_MAX_CHUNK_BYTES = 512 * 1024
_MAX_TEXT = 2_000
_MAX_ITEMS = 24
_A1111_FIELD_RE = re.compile(
    r"(?:^|,\s*)(Steps|Sampler|Schedule type|CFG scale|Seed|Size|Model hash|"
    r"Model|VAE|Clip skip|Version):\s*(.*?)(?=,\s*(?:Steps|Sampler|"
    r"Schedule type|CFG scale|Seed|Size|Model hash|Model|VAE|Clip skip|"
    r"Version):|$)",
    re.IGNORECASE | re.DOTALL,
)
_AI_ART_CATEGORIES = (
    ("AI Art - Landscape", "#22d3ee"),
    ("AI Art - Portrait", "#f472b6"),
    ("AI Art - Square", "#a78bfa"),
    ("AI Art - Other", "#94a3b8"),
)


def ai_art_categories() -> list[dict[str, Any]]:
    """Return a fresh category preset for ComfyUI/A1111 outputs."""
    return [
        {
            "name": name,
            "color": color,
            "rename_template": "",
            "extensions": list(AI_ART_IMAGE_EXTENSIONS),
        }
        for name, color in _AI_ART_CATEGORIES
    ]


def _bounded_text(value: Any, limit: int = _MAX_TEXT) -> str:
    if isinstance(value, bytes):
        value = value[:_MAX_CHUNK_BYTES].decode("utf-8", errors="replace")
    elif isinstance(value, (int, float)):
        value = str(value)
    if not isinstance(value, str):
        return ""
    return value.replace("\x00", "").strip()[:limit]


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> float | None:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _normalise_field_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", key.casefold()).strip("_")


def _store_generation_field(result: dict[str, Any], key: str, value: Any) -> None:
    """Store one known generation field after type and size bounds."""
    norm = _normalise_field_key(key)
    text = _bounded_text(value, 512)
    if not text:
        return
    if norm in {"steps", "step_count"}:
        parsed = _as_int(text)
        if parsed is not None and 1 <= parsed <= 1000:
            result["ai_steps"] = parsed
    elif norm in {"cfg_scale", "cfg"}:
        parsed = _as_float(text)
        if parsed is not None and 0 <= parsed <= 100:
            result["ai_cfg_scale"] = parsed
    elif norm == "seed":
        parsed = _as_int(text)
        if parsed is not None and -(2**63) <= parsed <= 2**63 - 1:
            result["ai_seed"] = parsed
    elif norm in {"sampler", "sampler_name"}:
        result["ai_sampler"] = text
    elif norm == "scheduler":
        result["ai_scheduler"] = text
    elif norm in {"model_hash", "checkpoint_hash", "hash"}:
        result["ai_checkpoint_hash"] = text[:128]
    elif norm in {"model", "checkpoint", "checkpoint_name", "ckpt_name", "unet_name"}:
        result["ai_checkpoint"] = text[:256]
    elif norm == "size" and re.fullmatch(r"\d{1,5}x\d{1,5}", text, re.IGNORECASE):
        result["ai_dimensions"] = text.lower()


def _parse_a1111(raw: str) -> dict[str, Any]:
    """Parse Automatic1111's ``parameters`` PNG text chunk."""
    raw = _bounded_text(raw, _MAX_CHUNK_BYTES)
    if not raw or not re.search(r"(?:Negative prompt:|(?:^|\n)Steps:)", raw):
        return {}

    negative = ""
    prompt_part = raw
    negative_match = re.search(r"\nNegative prompt:\s*", raw, re.IGNORECASE)
    if negative_match:
        prompt_part = raw[:negative_match.start()]
        negative_part = raw[negative_match.end():]
    else:
        negative_part = ""
    search_part = negative_part or prompt_part
    settings_match = re.search(r"\nSteps:\s*", search_part, re.IGNORECASE)
    if settings_match:
        settings_text = search_part[settings_match.start():].lstrip()
        if negative_part:
            negative = negative_part[:settings_match.start()].strip()
        else:
            prompt_part = prompt_part[:settings_match.start()]
    else:
        settings_text = ""
    result: dict[str, Any] = {
        "ai_art": True,
        "ai_art_source": "a1111",
        "ai_prompt": _bounded_text(prompt_part),
    }
    if negative:
        result["ai_negative_prompt"] = _bounded_text(negative)
    for match in _A1111_FIELD_RE.finditer(settings_text):
        _store_generation_field(result, match.group(1), match.group(2))
    if not settings_text and not result.get("ai_prompt"):
        return {}
    return result


def _json_value(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    text = _bounded_text(raw, _MAX_CHUNK_BYTES)
    if not text or text[0] not in "[{":
        return None
    try:
        return json.loads(text)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _parse_comfy(value: Any) -> dict[str, Any]:
    """Extract scalar evidence from ComfyUI prompt/workflow JSON."""
    if isinstance(value, str):
        value = _json_value(value)
    if not isinstance(value, (dict, list)):
        return {}

    prompts: list[str] = []
    negative_prompts: list[str] = []
    result: dict[str, Any] = {
        "ai_art": True,
        "ai_art_source": "comfyui",
    }
    visited = 0
    node_count = 0

    def walk(node: Any, path: tuple[str, ...] = (), depth: int = 0) -> None:
        nonlocal visited, node_count
        if depth > 16 or visited >= 2_000:
            return
        visited += 1
        if isinstance(node, list):
            for item in node[:_MAX_ITEMS]:
                walk(item, path, depth + 1)
            return
        if not isinstance(node, dict):
            return
        class_type = _bounded_text(node.get("class_type") or node.get("type"), 128).casefold()
        if class_type:
            node_count += 1
        title = _bounded_text(
            node.get("_meta", {}).get("title")
            if isinstance(node.get("_meta"), dict)
            else "",
            128,
        ).casefold()
        inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else node
        if isinstance(inputs, dict):
            for key, raw_item in list(inputs.items())[:80]:
                key_text = _bounded_text(key, 80)
                norm = _normalise_field_key(key_text)
                if isinstance(raw_item, (str, int, float)):
                    text = _bounded_text(raw_item, 512)
                    if norm in {"text", "prompt", "positive", "positive_prompt"}:
                        if text and len(text) >= 3:
                            (negative_prompts if "negative" in title else prompts).append(text)
                    if norm in {
                        "steps", "cfg", "cfg_scale", "seed", "sampler", "sampler_name",
                        "scheduler", "ckpt_name", "checkpoint", "checkpoint_name",
                        "model", "model_name", "unet_name", "model_hash", "hash",
                    }:
                        _store_generation_field(result, norm, raw_item)
                elif isinstance(raw_item, (dict, list)):
                    walk(raw_item, (*path, norm), depth + 1)
                if norm in {"model_hash", "checkpoint_hash", "hash"}:
                    _store_generation_field(result, norm, raw_item)
        for key, child in list(node.items())[:80]:
            if key in {"inputs", "_meta"}:
                continue
            if isinstance(child, (dict, list)):
                walk(child, (*path, _normalise_field_key(str(key))), depth + 1)

    walk(value)
    if prompts:
        result["ai_prompt"] = _bounded_text(" | ".join(dict.fromkeys(prompts)))
    if negative_prompts:
        result["ai_negative_prompt"] = _bounded_text(
            " | ".join(dict.fromkeys(negative_prompts))
        )
    if node_count:
        result["ai_workflow_nodes"] = min(node_count, 2_000)
    if not any(key.startswith("ai_") and key not in {"ai_art", "ai_art_source"}
               for key in result):
        return {}
    return result


def extract_ai_art_metadata(filepath: str | os.PathLike[str]) -> dict[str, Any]:
    """Read bounded A1111/ComfyUI metadata from a raster image."""
    path = Path(filepath)
    if path.suffix.casefold() not in {f".{ext}" for ext in AI_ART_IMAGE_EXTENSIONS}:
        return {}
    try:
        from PIL import Image

        with Image.open(path) as image:
            info = dict(image.info)
    except Exception:
        return {}

    for key in ("parameters", "Parameters", "comment", "Comment"):
        parsed = _parse_a1111(info.get(key, ""))
        if parsed:
            return parsed
    for key in ("prompt", "workflow", "comfyui", "ComfyUI"):
        parsed = _parse_comfy(info.get(key))
        if parsed:
            return parsed
    return {}


def classify_ai_art(filepath: str, metadata: dict[str, Any] | None = None) -> tuple[str, int] | None:
    """Return an AI-art category from generation evidence, or ``None``."""
    data = (
        metadata
        if isinstance(metadata, dict) and metadata.get("ai_art")
        else extract_ai_art_metadata(filepath)
    )
    if not data.get("ai_art"):
        return None
    prompt = " ".join(
        str(data.get(key, "")) for key in ("ai_prompt", "ai_negative_prompt", "ai_checkpoint")
    ).casefold()
    portrait_terms = ("portrait", "person", "people", "face", "headshot", "character", "woman", "man")
    landscape_terms = ("landscape", "mountain", "forest", "ocean", "beach", "cityscape", "scenery", "panorama")
    portrait_score = sum(prompt.count(term) for term in portrait_terms)
    landscape_score = sum(prompt.count(term) for term in landscape_terms)
    width = _as_int(data.get("width"))
    height = _as_int(data.get("height"))
    if width and height and height > 0:
        ratio = width / height
        if ratio >= 1.18:
            landscape_score += 2
        elif ratio <= 0.85:
            portrait_score += 2
    if portrait_score > landscape_score:
        category = "AI Art - Portrait"
    elif landscape_score > portrait_score:
        category = "AI Art - Landscape"
    elif width and height and 0.88 <= width / height <= 1.12:
        category = "AI Art - Square"
    else:
        category = "AI Art - Other"
    evidence = sum(bool(data.get(key)) for key in (
        "ai_prompt", "ai_checkpoint", "ai_checkpoint_hash", "ai_sampler",
        "ai_steps", "ai_cfg_scale", "width", "height",
    ))
    confidence = min(98, 82 + evidence * 2)
    return category, confidence


AI_ART_PRESET = ai_art_categories()
