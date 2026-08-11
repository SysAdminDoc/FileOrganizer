"""Regression tests for previously unreachable optional/runtime branches."""

from __future__ import annotations

import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from fileorganizer import engine, files, ollama, providers
from fileorganizer.classifier import infer_asset_type


def test_rule_engine_load_save_and_event_suggestion(tmp_path, monkeypatch):
    rules_file = tmp_path / "rules.json"
    monkeypatch.setattr(engine, "_RULES_FILE", str(rules_file))
    rules = [{"name": "Images", "conditions": [], "category": "Images"}]

    engine.RuleEngine.save_rules(rules)

    assert engine.RuleEngine.load_rules() == rules
    assert engine.EventGrouper.suggest_event_name(
        ["A red sunset over the ocean", "Ocean sunset"]
    ) == "Sunset Ocean Red"


def test_pc_classifier_handles_unknown_extension_with_fuzzy_and_mime_signals(
    tmp_path,
):
    path = tmp_path / "quarterly report.unknown"
    path.write_text("plain text", encoding="utf-8")
    categories = [{"name": "Documents", "keywords": ["quarterly report"]}]

    category, confidence, method = files._classify_pc_item(
        str(path), {}, categories=categories
    )

    assert category in {"Documents", "Other"}
    assert confidence >= 0
    assert method


def test_topic_context_classification_can_scan_design_files(tmp_path):
    folder = tmp_path / "Night Club"
    folder.mkdir()
    (folder / "flyer.psd").write_bytes(b"not-a-real-psd")

    result = infer_asset_type("Club & DJ", 70, str(folder), folder.name)

    assert isinstance(result, tuple)
    assert len(result) == 4


def test_ollama_id_hint_and_asset_folder_context_are_built(monkeypatch, tmp_path):
    captured = []

    def fake_generate(prompt, **_kwargs):
        captured.append(prompt)
        return json.dumps(
            {
                "kind": "classification",
                "name": "Project Name",
                "category": "Flyers & Print",
                "confidence": 80,
            }
        )

    monkeypatch.setattr(ollama, "_ollama_generate", fake_generate)
    monkeypatch.setattr(
        ollama,
        "_extract_name_hints",
        lambda _path: [("Project Name", "project.aep", 100)],
    )

    id_folder = tmp_path / "VH-12345678"
    id_folder.mkdir()
    id_result = ollama.ollama_classify_folder(id_folder.name, str(id_folder))

    asset_folder = tmp_path / "Project"
    asset_folder.mkdir()
    (asset_folder / "Footage").mkdir()
    asset_result = ollama.ollama_classify_folder(asset_folder.name, str(asset_folder))

    assert id_result["category"] == "Flyers & Print"
    assert asset_result["category"] == "Flyers & Print"
    assert "Project Name" in captured[0]
    assert "Asset folders" in captured[1]


def test_ollama_provider_passes_configured_batch_url_and_model(monkeypatch):
    received = {}
    monkeypatch.setattr(
        "fileorganizer.ollama.load_ollama_settings",
        lambda: {"url": "http://configured:11434", "model": "configured-model"},
    )

    def fake_batch(items, *, url, model):
        received.update({"items": items, "url": url, "model": model})
        return [{"category": "Images"}]

    monkeypatch.setattr("fileorganizer.ollama.ollama_classify_batch", fake_batch)
    items = [{"context": "folder"}]

    result = providers.OllamaProvider().classify_batch(items)

    assert result == [{"category": "Images"}]
    assert received == {
        "items": items,
        "url": "http://configured:11434",
        "model": "configured-model",
    }


def test_secondary_pyqt_dialogs_and_main_window_import(tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    import fileorganizer.main_window  # noqa: F401
    from fileorganizer.dialogs.editors import _FileBrowserDialog
    from fileorganizer.dialogs.settings import FaceManagerDialog

    folder = tmp_path / "assets"
    folder.mkdir()
    (folder / "project.psd").write_bytes(b"not-a-real-psd")
    browser = _FileBrowserDialog(
        str(folder), "Original", "After Effects - Other", 42
    )
    faces = FaceManagerDialog()

    monkeypatch.setattr(
        "fileorganizer.dialogs.editors.QInputDialog.getItem",
        lambda *_args, **_kwargs: ("Print - Flyers & Posters", True),
    )
    browser._choose_correction()

    assert browser.tree.columnCount() == 3
    assert browser.corrected_category == "Print - Flyers & Posters"
    assert browser.btn_ok.isEnabled()
    assert faces.windowTitle() == "Face Manager"
    browser.close()
    faces.close()
    app.processEvents()


def test_move_history_dialog_renders_journal_rows(monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from fileorganizer.dialogs import MoveHistoryDialog
    import fileorganizer.dialogs.tools as tools

    app = QApplication.instance() or QApplication([])
    monkeypatch.setattr(tools, "_load_undo_stack", lambda: [])
    monkeypatch.setattr(
        "fileorganizer.move_journal.get_move_history",
        lambda limit=1000: [{
            "kind": "run",
            "id": 7,
            "run_id": "run-demo",
            "action_id": "",
            "source": r"C:\source\asset",
            "destination": r"C:\destination\asset",
            "confidence": 91,
            "status": "done",
            "timestamp": "2026-08-10T12:00:00Z",
            "can_undo": True,
        }],
    )

    dialog = MoveHistoryDialog()
    try:
        assert dialog.windowTitle() == "Move History"
        assert dialog.tbl_history.rowCount() == 1
        assert dialog.tbl_history.item(0, 4).text() == "91%"
        dialog.tbl_history.selectRow(0)
        app.processEvents()
        assert dialog.btn_undo_selected.isEnabled()
        assert dialog.btn_undo_run.isEnabled()
    finally:
        dialog.close()
        app.processEvents()


def test_batch_rename_dialog_supports_category_filter_and_inline_edit(tmp_path):
    from types import SimpleNamespace
    from PyQt6.QtWidgets import QApplication
    from fileorganizer.dialogs import BatchRenameDialog

    app = QApplication.instance() or QApplication([])
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized" / "After Effects - Other"
    source = source_root / "Original Folder"
    source.mkdir(parents=True)
    destination_root.mkdir(parents=True)
    item = SimpleNamespace(
        category="After Effects - Other",
        folder_name="Original Folder",
        cleaned_name="Human Name",
        full_source_path=str(source),
        full_dest_path=str(destination_root / "Original Folder"),
        selected=True,
        status="Pending",
    )

    dialog = BatchRenameDialog([item])
    try:
        assert dialog.tbl_preview.rowCount() == 1
        dialog.tbl_preview.item(0, 2).setText("Edited Name")
        app.processEvents()
        dialog._accept()
        assert dialog.result() == dialog.DialogCode.Accepted
        assert dialog.renamed_items == [(item, "Edited Name")]
    finally:
        dialog.close()
        app.processEvents()


def test_full_face_recognition_builds_person_thumbnail(monkeypatch, tmp_path):
    numpy = pytest.importorskip("numpy")
    from fileorganizer import photos

    class FakeFaceRecognition:
        @staticmethod
        def load_image_file(_path):
            return numpy.zeros((24, 24, 3), dtype=numpy.uint8)

        @staticmethod
        def face_locations(_image, model):
            assert model == "hog"
            return [(2, 20, 20, 2)]

        @staticmethod
        def face_encodings(_image, locations):
            assert len(locations) == 1
            return ["encoding"]

    class FakeFaceDB:
        def __init__(self):
            self.thumbnail = None

        def add_or_update(self, _encoding, thumbnail):
            self.thumbnail = thumbnail
            return "Person 1"

    monkeypatch.setattr(photos, "_face_recognition", FakeFaceRecognition)
    image = tmp_path / "photo.jpg"
    image.write_bytes(b"fixture")
    face_db = FakeFaceDB()

    result = photos._detect_faces_full(str(image), face_db)

    assert result == {
        "face_count": 1,
        "persons": ["Person 1"],
        "primary_person": "Person 1",
    }
    assert face_db.thumbnail
