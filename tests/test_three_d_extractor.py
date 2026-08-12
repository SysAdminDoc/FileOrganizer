"""Tests for content-aware glTF, Draco, USD, and USDZ extraction."""
from __future__ import annotations

import json
import struct
import zipfile
from pathlib import Path

from fileorganizer import capabilities
from fileorganizer.metadata_extractors import extract_for_path
from fileorganizer.metadata_extractors import three_d_extractor as three_d


def _write_gltf(path: Path, **overrides) -> None:
    document = {
        "asset": {
            "version": "2.0",
            "generator": "Fixture Exporter",
            "copyright": "Fixture Author",
        },
        "extensionsUsed": ["KHR_draco_mesh_compression", "MSFT_lod"],
        "extensionsRequired": ["KHR_draco_mesh_compression"],
        "meshes": [
            {
                "primitives": [
                    {"extensions": {"KHR_draco_mesh_compression": {"bufferView": 0}}}
                ]
            }
        ],
        "nodes": [{"mesh": 0, "skin": 0}],
        "skins": [{"joints": [0]}],
        "animations": [{"name": "Walk"}],
        "textures": [{"source": 0}, {"source": 1}],
        "images": [{"uri": "albedo.png"}, {"uri": "normal.png"}],
        "scenes": [{"nodes": [0]}],
        "extensions": {"MSFT_lod": {"ids": [0, 1, 2]}},
    }
    document.update(overrides)
    path.write_text(json.dumps(document), encoding="utf-8", newline="\n")


def _write_glb(path: Path, document: dict) -> None:
    payload = json.dumps(document, separators=(",", ":")).encode("utf-8")
    payload += b" " * ((4 - len(payload) % 4) % 4)
    binary = b"fixture geometry"
    total_length = 12 + 8 + len(payload) + 8 + len(binary)
    path.write_bytes(
        struct.pack("<4sII", b"glTF", 2, total_length)
        + struct.pack("<II", len(payload), 0x4E4F534A)
        + payload
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )


def test_gltf_extracts_metadata_and_3d_subtaxonomy(tmp_path):
    path = tmp_path / "robot.gltf"
    _write_gltf(path)

    hint = three_d.extract(path)

    assert hint is not None
    assert hint.category == "3D - Models & Objects"
    assert hint.confidence >= 90
    assert hint.extractor == "three_d"
    assert hint.raw["taxonomy"] == "3d_model"
    assert hint.raw["generator"] == "Fixture Exporter"
    assert hint.raw["copyright"] == "Fixture Author"
    assert hint.raw["has_draco"] is True
    assert hint.raw["rigged"] is True
    assert hint.raw["lod_count"] == 4
    assert hint.raw["texture_count"] == 2
    assert hint.raw["subtaxonomy"] == {
        "rigging": "rigged",
        "lod_count": 4,
        "texture_count": 2,
    }


def test_glb_dispatches_and_counts_binary_chunk(tmp_path):
    path = tmp_path / "robot.glb"
    document = {
        "asset": {"version": "2.0", "generator": "GLB Fixture"},
        "meshes": [{"primitives": [{}]}],
    }
    _write_glb(path, document)

    hint = extract_for_path(path)

    assert hint is not None
    assert hint.raw["format"] == "glb"
    assert hint.raw["binary_chunk_bytes"] == len(b"fixture geometry")
    assert hint.raw["mesh_count"] == 1


def test_invalid_gltf_and_glb_are_ignored(tmp_path):
    invalid_json = tmp_path / "broken.gltf"
    invalid_json.write_text('{"asset": {"version": "1.0"}}', encoding="utf-8")
    assert three_d.extract(invalid_json) is None

    invalid_glb = tmp_path / "broken.glb"
    invalid_glb.write_bytes(struct.pack("<4sII", b"not!", 2, 12))
    assert three_d.extract(invalid_glb) is None


def test_standalone_draco_routes_to_model_category(tmp_path):
    path = tmp_path / "mesh.drc"
    path.write_bytes(b"draco fixture")

    hint = extract_for_path(path)

    assert hint is not None
    assert hint.category == "3D - Models & Objects"
    assert hint.raw["has_draco"] is True
    assert hint.raw["taxonomy"] == "3d_model"


def test_usdz_enumerates_layers_and_textures_without_usdcat(tmp_path, monkeypatch):
    monkeypatch.setattr(three_d, "_find_usdcat", lambda: None)
    path = tmp_path / "scene.usdz"
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("Scene.usdc", b"usd layer")
        archive.writestr("Textures/albedo.png", b"png fixture")

    hint = three_d.extract(path)

    assert hint is not None
    assert hint.category == "3D - Models & Objects"
    assert hint.raw["layer_count"] == 1
    assert hint.raw["layers"] == ["Scene.usdc"]
    assert hint.raw["texture_count"] == 1
    assert hint.raw["usdcat"] == "not_detected"
    assert hint.raw["subtaxonomy"]["rigging"] == "unrigged"


def test_usdz_rejects_path_traversal(tmp_path, monkeypatch):
    monkeypatch.setattr(three_d, "_find_usdcat", lambda: None)
    path = tmp_path / "unsafe.usdz"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../outside.usdc", b"unsafe")

    assert three_d.extract(path) is None


def test_usdcat_preview_adds_rigging_evidence(tmp_path, monkeypatch):
    path = tmp_path / "rig.usda"
    path.write_text("#usda 1.0", encoding="utf-8")
    monkeypatch.setattr(three_d, "_find_usdcat", lambda: "usdcat")
    monkeypatch.setattr(
        three_d,
        "_run_usdcat",
        lambda _binary, _path: {
            "returncode": 0,
            "stdout": "def SkelRoot \"Rig\" {}",
            "stderr": "",
        },
    )

    hint = three_d.extract(path)

    assert hint is not None
    assert hint.raw["usdcat"] == "available"
    assert hint.raw["rigged"] is True
    assert hint.raw["subtaxonomy"]["rigging"] == "rigged"


def test_folder_primary_selection_prefers_3d_asset(tmp_path):
    folder = tmp_path / "model-pack"
    folder.mkdir()
    (folder / "preview.png").write_bytes(b"preview")
    model = folder / "model.gltf"
    _write_gltf(model)

    from fileorganizer.metadata_extractors import _select_primary_file

    assert _select_primary_file(folder, []) == model


def test_three_d_capabilities_are_explicit():
    rows = {row["capability"]: row for row in capabilities.capability_matrix("metadata")}

    assert rows["three_d_asset_metadata"]["status"] == "available"
    assert rows["usdcat_layer_inspection"]["status"] in {"available", "unavailable"}
