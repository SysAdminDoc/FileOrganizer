"""Headless contracts for the version-aware deduplication dialog."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QCheckBox

from fileorganizer.dialogs.version_dedup import VersionDedupDialog
from fileorganizer.version_dedup import scan_version_groups


_APP = QApplication.instance() or QApplication([])


def _version(root, name, files):
    folder = root / name
    folder.mkdir(parents=True)
    for relative, content in files.items():
        path = folder / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return folder


def test_version_dialog_shows_keeper_and_checked_archive_candidates(tmp_path):
    library = tmp_path / "library"
    _version(library, "22197897-v1", {"project.aep": "old"})
    _version(library, "22197897-v2", {"project.aep": "new", "readme.txt": "new"})
    groups = scan_version_groups([library])

    dialog = VersionDedupDialog(roots=[str(library)])
    try:
        dialog._on_scan_done(groups)
        assert dialog.tree.topLevelItemCount() == 1
        assert dialog.tree.topLevelItem(0).childCount() == 2
        assert dialog.btn_apply.isEnabled()
        archive_row = dialog.tree.topLevelItem(0).child(1)
        assert isinstance(dialog.tree.itemWidget(archive_row, 0), QCheckBox)
        assert dialog.tree.itemWidget(archive_row, 0).isChecked()
        assert "ID 22197897" in dialog.tree.topLevelItem(0).text(0)
    finally:
        dialog.close()
