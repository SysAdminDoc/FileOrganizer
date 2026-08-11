"""Integration tests for manifest-aware legacy folder classification."""

from __future__ import annotations

import json
from zipfile import ZipFile

from fileorganizer import classifier


def test_tiered_classifier_routes_mogrt_using_manifest_counts(tmp_path, monkeypatch):
    folder = tmp_path / "generic-template-pack"
    folder.mkdir()
    manifest = {
        "templateName": "Editable Lower Third",
        "parameters": [
            {"name": "Title"},
            {"name": "Subtitle"},
            {"name": "Accent Color"},
        ],
        "requiredFonts": ["Montserrat", "Roboto"],
    }
    with ZipFile(folder / "template.mogrt", "w") as archive:
        archive.writestr("Manifest.json", json.dumps(manifest))

    monkeypatch.setattr(classifier, "_fingerprint_db_lookup", lambda *_a, **_k: {})

    result = classifier.tiered_classify(folder.name, str(folder))

    assert result["category"] == "Premiere Pro - Titles & Text"
    assert result["confidence"] >= 90
    assert result["method"] == "mogrt_metadata"
    assert result["metadata"]["primary_app"] == "Premiere Pro"
    assert result["metadata"]["mogrt_metadata"]["parameter_count"] == 3
    assert result["metadata"]["mogrt_metadata"]["font_count"] == 2
    assert "font requirements" in result["detail"]
