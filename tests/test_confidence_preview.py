"""Headless coverage for the classification confidence preview widget."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication, QProgressBar, QPushButton

from fileorganizer.widgets import FilePreviewPanel


def test_preview_panel_renders_probabilities_and_emits_runner_up_override(tmp_path):
    app = QApplication.instance() or QApplication([])
    folder = tmp_path / "summer-flyer"
    folder.mkdir()
    panel = FilePreviewPanel()
    requested = []
    panel.override_requested.connect(requested.append)

    panel.show_file(
        str(folder),
        {},
        {
            "category": "Flyers & Print",
            "confidence": 84,
            "alternatives": [
                {"category": "After Effects - Templates", "confidence": 42},
                {"category": "Posters", "confidence": 18},
            ],
        },
    )

    bars = panel.findChildren(QProgressBar)
    assert [bar.value() for bar in bars] == [84, 42, 18]
    runner_up = next(
        button for button in panel.findChildren(QPushButton)
        if button.text() == "After Effects - Templates"
    )
    runner_up.click()

    assert requested == ["After Effects - Templates"]
    panel.clear()
    panel.deleteLater()
    app.processEvents()
