"""Headless contracts for the cross-library deduplication dialogs."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from fileorganizer.cross_library_dedup import scan_cross_library
from fileorganizer.dialogs.duplicates import (
    CrossLibraryDedupDialog,
    CrossLibraryReviewDialog,
)


_APP = QApplication.instance() or QApplication([])


def _folder(path, name, content):
    folder = path / name
    folder.mkdir(parents=True)
    (folder / "file.txt").write_text(content, encoding="utf-8")
    return folder


def test_review_dialog_switches_keeper_and_exposes_actions(tmp_path):
    root_a = tmp_path / "a"
    root_b = tmp_path / "b"
    source = _folder(root_a, "asset", "same")
    keeper = _folder(root_b, "asset", "same")
    groups = scan_cross_library([root_a, root_b])

    dialog = CrossLibraryReviewDialog(groups)
    try:
        assert dialog.table.rowCount() == 2
        assert not dialog._action_boxes[0].isEnabled()
        assert dialog._action_boxes[1].isEnabled()

        dialog._keeper_radios[1].setChecked(True)
        _APP.processEvents()
        assert dialog._action_boxes[0].isEnabled()
        assert not dialog._action_boxes[1].isEnabled()
        assert dialog._selected_keeper() == str(keeper.resolve())
        assert source.exists()
    finally:
        dialog.close()


def test_root_dialog_parses_multiple_roots_without_scanning(tmp_path):
    dialog = CrossLibraryDedupDialog(roots=[str(tmp_path / "a"), str(tmp_path / "b")])
    try:
        dialog.txt_roots.setText(f"{tmp_path / 'a'};\n{tmp_path / 'b'}")
        assert dialog._roots() == [str(tmp_path / "a"), str(tmp_path / "b")]
        assert not dialog.btn_review_cross.isEnabled()
    finally:
        dialog.close()
