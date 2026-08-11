import json

import pytest

from fileorganizer.chroma_index import (
    ChromaIndex,
    document_for_path,
    record_id,
)


def test_chroma_record_ids_are_stable_without_exposing_paths():
    first = record_id(r"C:\Pictures\sunset.jpg")
    assert first == record_id(r"C:\Pictures\sunset.jpg")
    assert first != record_id(r"C:\Pictures\other.jpg")
    assert r"Pictures" not in first


def test_document_for_path_normalizes_filename_tokens():
    assert document_for_path(r"C:\Pictures\Sunset-Over_mountains.jpg") == (
        "Sunset Over mountains"
    )


def test_chroma_collection_name_is_bounded():
    with pytest.raises(ValueError):
        ChromaIndex("db", collection="Bad Collection")
    with pytest.raises(ValueError):
        ChromaIndex("db", collection="ab")


def test_chroma_runner_reports_missing_optional_capability(tmp_path, monkeypatch, capsys):
    import chroma_run

    monkeypatch.setattr(
        chroma_run,
        "get_capability",
        lambda *_args: {"status": "unavailable"},
    )
    root = tmp_path / "images"
    root.mkdir()
    chroma_run._PROTOCOL.reset()
    assert chroma_run.main(["--root", str(root), "--db", str(tmp_path / "chroma")]) == 3
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    assert rows[-1]["event"] == "error"
    assert rows[-1]["code"] == "capability_unavailable"
