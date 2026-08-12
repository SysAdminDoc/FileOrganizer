import json

from PIL import Image
from PIL.PngImagePlugin import PngInfo

from fileorganizer.ai_art import (
    AI_ART_PRESET,
    classify_ai_art,
    extract_ai_art_metadata,
)
from fileorganizer.metadata import MetadataExtractor
from fileorganizer.plugins import CategoryPresetManager, PluginManager


def _write_png(path, **chunks):
    image = Image.new("RGB", (768, 512), "white")
    png_info = PngInfo()
    for key, value in chunks.items():
        png_info.add_text(key, value)
    image.save(path, pnginfo=png_info)


def test_parse_a1111_parameters_and_route_by_prompt_and_dimensions(tmp_path):
    image_path = tmp_path / "ComfyUI_00001_.png"
    _write_png(
        image_path,
        parameters=(
            "wide mountain landscape at sunset, cinematic lighting\n"
            "Negative prompt: portrait, blurry\n"
            "Steps: 28, Sampler: DPM++ 2M Karras, CFG scale: 7, Seed: 42, "
            "Size: 768x512, Model hash: abc123, Model: flux-dev"
        ),
    )

    metadata = extract_ai_art_metadata(image_path)

    assert metadata["ai_art_source"] == "a1111"
    assert metadata["ai_prompt"].startswith("wide mountain landscape")
    assert metadata["ai_negative_prompt"] == "portrait, blurry"
    assert metadata["ai_steps"] == 28
    assert metadata["ai_sampler"] == "DPM++ 2M Karras"
    assert metadata["ai_checkpoint_hash"] == "abc123"
    metadata.update({"width": 768, "height": 512})
    assert classify_ai_art(str(image_path), metadata)[0] == "AI Art - Landscape"


def test_parse_comfyui_prompt_without_exposing_workflow_json(tmp_path):
    image_path = tmp_path / "flux.png"
    prompt = {
        "3": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "portrait of a woman in studio light"},
            "_meta": {"title": "Positive prompt"},
        },
        "4": {
            "class_type": "CheckpointLoaderSimple",
            "inputs": {"ckpt_name": "flux_dev_q8.gguf", "model_hash": "deadbeef"},
        },
        "5": {
            "class_type": "KSampler",
            "inputs": {
                "steps": 20, "cfg": 3.5, "sampler_name": "euler", "seed": 9,
            },
        },
    }
    _write_png(image_path, prompt=json.dumps(prompt))

    metadata = MetadataExtractor.extract(str(image_path))

    assert metadata["ai_art_source"] == "comfyui"
    assert "portrait of a woman" in metadata["ai_prompt"]
    assert metadata["ai_checkpoint"] == "flux_dev_q8.gguf"
    assert metadata["ai_checkpoint_hash"] == "deadbeef"
    assert metadata["ai_sampler"] == "euler"
    assert metadata["ai_steps"] == 20
    assert "workflow" not in metadata
    assert classify_ai_art(str(image_path), metadata)[0] == "AI Art - Portrait"


def test_unmarked_image_is_not_routed_to_ai_art(tmp_path):
    image_path = tmp_path / "family.jpg"
    Image.new("RGB", (600, 800), "white").save(image_path)

    assert extract_ai_art_metadata(image_path) == {}
    assert classify_ai_art(str(image_path), {}) is None


def test_ai_art_preset_is_available_and_plugin_hook_routes_metadata():
    assert CategoryPresetManager.builtin_presets()["AI Art — ComfyUI / A1111"] == AI_ART_PRESET
    previous = PluginManager._plugins
    PluginManager._plugins = []
    try:
        result = PluginManager.run_classifiers(
            "render.png",
            {"ai_art": True, "ai_prompt": "mountain landscape", "width": 1024, "height": 512},
        )
    finally:
        PluginManager._plugins = previous
    assert result[0] == "AI Art - Landscape"
