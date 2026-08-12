"""Headless contracts for the organized-library Browse tree."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

import fileorganizer.dialogs.browse as browse
from fileorganizer.dialogs.browse import BrowsePanel


_APP = QApplication.instance() or QApplication([])


def test_browse_panel_builds_category_drop_targets(tmp_path, monkeypatch):
    root = tmp_path / "organized"
    source = root / "Old Category" / "asset"
    source.mkdir(parents=True)
    (source / "file.txt").write_text("content", encoding="utf-8")
    (root / "New Category").mkdir(parents=True)

    calls = []
    monkeypatch.setattr(
        browse,
        "reclassify_folder",
        lambda source_path, library_root, target_category: (
            calls.append((source_path, library_root, target_category))
            or SimpleNamespace(message="test reclassified", user_corrections=1)
        ),
    )
    panel = BrowsePanel()
    try:
        panel.txt_root.setText(str(root))
        panel.refresh()
        assert panel.tree.topLevelItemCount() == 2
        old = panel.tree.topLevelItem(0)
        assert old.text(0) == "New Category"
        if old.text(0) != "Old Category":
            old = panel.tree.topLevelItem(1)
        assert old.text(0) == "Old Category"
        assert old.childCount() == 1
        asset = old.child(0)
        assert asset.data(0, Qt.ItemDataRole.UserRole) == str(source)
        assert old.flags() & Qt.ItemFlag.ItemIsDropEnabled

        panel._on_reclassify(str(source), str(root), "New Category")
        assert calls == [(str(source), str(root), "New Category")]
    finally:
        panel.close()


def test_browse_panel_search_renders_citations(tmp_path, monkeypatch):
    root = tmp_path / "organized"
    (root / "Documents").mkdir(parents=True)
    indexed = []
    monkeypatch.setattr(browse, "index_library", lambda path: indexed.append(path) or 2)
    monkeypatch.setattr(
        browse,
        "search_library",
        lambda query, **kwargs: [{
            "name": "invoice.pdf",
            "category": "Documents",
            "description": "August vendor invoice",
            "score": 0.75,
            "path": str(root / "Documents" / "invoice.pdf"),
            "citation": "[1] invoice.pdf — August vendor invoice",
        }],
    )
    panel = BrowsePanel()
    try:
        panel.txt_root.setText(str(root))
        panel.txt_query.setText("show invoices")
        panel._search()
        assert indexed == [str(root)]
        assert panel.search_tree.topLevelItemCount() == 1
        result = panel.search_tree.topLevelItem(0)
        assert result.text(0) == "invoice.pdf"
        assert result.data(0, Qt.ItemDataRole.UserRole).endswith("invoice.pdf")
        assert "August vendor invoice" in result.toolTip(0)
    finally:
        panel.close()
