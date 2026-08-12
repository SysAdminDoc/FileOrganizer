from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QDialog, QLineEdit, QPushButton

from fileorganizer.accessibility import AccessibilityManager, apply_accessibility


_APP = QApplication.instance() or QApplication([])


def test_interactive_controls_receive_accessible_metadata():
    dialog = QDialog()
    dialog.setWindowTitle("Settings")
    edit = QLineEdit(dialog)
    edit.setPlaceholderText("Source folder")
    button = QPushButton("Scan", dialog)
    button.setToolTip("Start a scan")
    apply_accessibility(dialog)

    assert edit.accessibleName() == "Source folder"
    assert edit.accessibleDescription().startswith("Interactive control:")
    assert button.accessibleName() == "Scan"
    assert button.accessibleDescription() == "Start a scan"


def test_enter_activates_a_focused_button():
    dialog = QDialog()
    button = QPushButton("Apply", dialog)
    button.show()
    activated = []
    button.clicked.connect(lambda: activated.append(True))
    installed = AccessibilityManager(_APP, _APP)
    _APP.installEventFilter(installed)
    try:
        button.setFocus()
        QTest.keyClick(button, Qt.Key.Key_Return)
        assert activated == [True]
    finally:
        _APP.removeEventFilter(installed)
        installed.deleteLater()
