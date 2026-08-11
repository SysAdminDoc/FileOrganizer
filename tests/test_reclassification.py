"""Tests for Browse drag/drop reclassification persistence."""

from __future__ import annotations

import json

import pytest

import fileorganizer.adaptive_corrector as adaptive_corrector
import fileorganizer.cache as cache
import fileorganizer.move_journal as move_journal
from fileorganizer.adaptive_corrector import AdaptiveCorrector
from fileorganizer.reclassification import reclassify_folder


def test_counter_is_durable_and_validates_increments(tmp_path, monkeypatch):
    database = tmp_path / "classification-cache.db"
    monkeypatch.setattr(cache, "_CACHE_DB", str(database))
    cache._close_cache_conn()
    try:
        assert cache.user_corrections_count() == 0
        assert cache.increment_user_corrections() == 1
        assert cache.increment_user_corrections(2) == 3
        assert cache.user_corrections_count() == 3
        with pytest.raises(ValueError):
            cache.increment_user_corrections(0)
    finally:
        cache._close_cache_conn()


def test_reclassify_moves_folder_and_records_fingerprint_correction(tmp_path, monkeypatch):
    app_data = tmp_path / "app-data"
    corrections_file = app_data / "corrections.json"
    database = app_data / "classification-cache.db"
    journal_db = app_data / "organize-moves.db"
    app_data.mkdir()
    monkeypatch.setattr(adaptive_corrector, "_CORRECTIONS_FILE", str(corrections_file))
    monkeypatch.setattr(cache, "_CORRECTIONS_FILE", str(corrections_file))
    monkeypatch.setattr(cache, "_CACHE_DB", str(database))
    monkeypatch.setattr(move_journal, "_JOURNAL_DB", str(journal_db))
    monkeypatch.setattr(move_journal, "_INITIALIZED_DB", None)
    cache._close_cache_conn()

    library = tmp_path / "organized"
    source = library / "Old Category" / "asset"
    source.mkdir(parents=True)
    (source / "project.aep").write_text("same", encoding="utf-8")

    try:
        result = reclassify_folder(str(source), str(library), "New Category", original_confidence=42)

        assert result.status == "moved"
        assert result.correction_recorded is True
        assert result.user_corrections == 1
        assert not source.exists()
        assert (library / "New Category" / "asset" / "project.aep").exists()
        correction = AdaptiveCorrector(corrections_file=str(corrections_file))
        match = correction.apply_correction(str(library / "New Category" / "asset"))
        assert match is not None
        assert match[0] == "New Category"
        payload = json.loads(corrections_file.read_text(encoding="utf-8"))
        assert payload["corrections"][0]["fingerprint"] == result.fingerprint
    finally:
        cache._close_cache_conn()
