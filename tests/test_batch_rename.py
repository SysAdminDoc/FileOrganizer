from __future__ import annotations

from fileorganizer.batch_rename import (
    CANONICAL_TEMPLATE,
    category_code,
    extract_identifier,
    proposed_filename,
    render_name,
)


def test_canonical_template_uses_category_code_and_marketplace_id():
    item = {
        "category": "After Effects - Slideshow",
        "clean_name": "Summer Opener",
        "_marketplace_id": "videohive:12345678",
    }

    assert category_code(item["category"]) == "AES"
    assert extract_identifier(item) == "12345678"
    assert render_name(item, template=CANONICAL_TEMPLATE) == "AES_12345678_Summer Opener"


def test_file_preview_preserves_extension_and_supports_counter_format():
    item = {
        "category": "Print - Flyers & Posters",
        "name": "old-poster.png",
        "full_src": "/source/old-poster.png",
        "is_file_item": True,
    }

    assert proposed_filename(item, index=7) == "PFP_0007_old-poster.png"
    assert render_name(item, index=7, template="{COUNTER:03d}_{NAME}") == "007_old-poster"


def test_unknown_template_fields_resolve_to_safe_empty_values():
    item = {"category": "Docs", "clean_name": "Guide"}

    assert render_name(item, template="{CAT_CODE}_{UNKNOWN}_{CLEAN_NAME}") == "D_Guide"
