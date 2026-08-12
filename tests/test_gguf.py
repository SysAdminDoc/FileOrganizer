"""Tests for bounded GGUF inspection and explicit Ollama registration."""

from __future__ import annotations

import struct

import pytest

from fileorganizer import gguf


def _gguf_string(value: str) -> bytes:
    payload = value.encode("utf-8")
    return struct.pack("<Q", len(payload)) + payload


def _write_fixture(path):
    entries = [
        ("general.architecture", 8, _gguf_string("llama")),
        ("llama.context_length", 4, struct.pack("<I", 8192)),
        ("general.file_type", 4, struct.pack("<I", 15)),
        ("tokenizer.chat_template", 8, _gguf_string("{{ .System }} {{ .Prompt }}")),
    ]
    payload = bytearray(struct.pack("<4sIQQ", b"GGUF", 3, 0, len(entries)))
    for key, value_type, value in entries:
        payload.extend(_gguf_string(key))
        payload.extend(struct.pack("<I", value_type))
        payload.extend(value)
    path.write_bytes(payload)


def test_inspect_gguf_reads_runtime_metadata(tmp_path):
    model = tmp_path / "custom-model.gguf"
    _write_fixture(model)

    result = gguf.inspect_gguf(model)

    assert result["architecture"] == "llama"
    assert result["context_length"] == 8192
    assert result["quantization"] == "Q4_K_M"
    assert result["chat_template"] == "{{ .System }} {{ .Prompt }}"
    assert result["metadata_count"] == 4


def test_register_gguf_persists_and_replaces_by_path(tmp_path, monkeypatch):
    model = tmp_path / "custom-model.gguf"
    _write_fixture(model)
    registry_path = tmp_path / "gguf_models.json"
    monkeypatch.setattr(gguf, "_REGISTRY_FILE", str(registry_path))

    first = gguf.register_gguf(model)
    second = gguf.register_gguf(model, ollama_name="fileorganizer/renamed:latest")
    registered = gguf.load_registered_models()

    assert first["ollama_name"] == "fileorganizer/custom-model:latest"
    assert second["ollama_name"] == "fileorganizer/renamed:latest"
    assert len(registered) == 1
    assert registered[0]["context_length"] == 8192
    assert registered[0]["quantization"] == "Q4_K_M"


def test_create_ollama_model_uses_argument_list_and_metadata_template(tmp_path, monkeypatch):
    model = tmp_path / "custom-model.gguf"
    _write_fixture(model)
    monkeypatch.setattr(gguf, "_REGISTRY_FILE", str(tmp_path / "registry.json"))
    record = gguf.register_gguf(model)
    calls = []

    class Completed:
        returncode = 0
        stdout = "created"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        modelfile = next(value for value in command if value.endswith("Modelfile"))
        content = open(modelfile, encoding="utf-8").read()
        assert "PARAMETER num_ctx 8192" in content
        assert "TEMPLATE" in content
        return Completed()

    monkeypatch.setattr(gguf.subprocess, "run", fake_run)

    result = gguf.create_ollama_model(record, ollama_binary="ollama")

    assert result["ollama_name"] == record["ollama_name"]
    assert calls[0][0][:3] == ["ollama", "create", record["ollama_name"]]
    assert "shell" not in calls[0][1]


def test_invalid_gguf_fails_closed(tmp_path):
    invalid = tmp_path / "not-a-model.gguf"
    invalid.write_bytes(b"not gguf")

    with pytest.raises(gguf.GgufError):
        gguf.inspect_gguf(invalid)
