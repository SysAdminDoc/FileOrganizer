"""Small, dependency-free accessibility layer for the PyQt6 desktop UI."""

from __future__ import annotations

import re

from PyQt6.QtCore import QEvent, QPoint, QObject, Qt
from PyQt6.QtWidgets import (
    QAbstractButton, QAbstractItemView, QAbstractSlider,
    QAbstractSpinBox, QComboBox, QDialog, QLineEdit, QMainWindow, QPlainTextEdit,
    QTabWidget, QTextEdit, QWidget,
)


_INTERACTIVE_TYPES = (
    QAbstractButton,
    QComboBox,
    QLineEdit,
    QAbstractSpinBox,
    QAbstractSlider,
    QAbstractItemView,
    QTabWidget,
    QTextEdit,
    QPlainTextEdit,
)


def _humanize(value: str) -> str:
    value = re.sub(r"([a-z])([A-Z])", r"\1 \2", value)
    value = re.sub(r"[_-]+", " ", value).strip()
    return value or "Control"


def _visible_text(widget: QWidget) -> str:
    if isinstance(widget, QAbstractButton):
        return widget.text().replace("&", "").strip()
    if isinstance(widget, QLineEdit):
        return widget.placeholderText().strip()
    if isinstance(widget, QComboBox):
        return widget.currentText().strip() or "Combo box"
    if isinstance(widget, QTabWidget):
        return widget.tabText(widget.currentIndex()).strip() or "Tab panel"
    if isinstance(widget, (QTextEdit, QPlainTextEdit)):
        return widget.placeholderText().strip()
    if isinstance(widget, QAbstractItemView):
        return "Results list"
    if isinstance(widget, (QAbstractSpinBox, QAbstractSlider)):
        return "Value control"
    if isinstance(widget, (QDialog, QMainWindow)):
        return widget.windowTitle().strip()
    return ""


def _accessible_name(widget: QWidget) -> str:
    text = _visible_text(widget)
    if text:
        return text
    object_name = widget.objectName().strip()
    if object_name:
        return _humanize(object_name)
    return _humanize(widget.metaObject().className())


def _apply_names(root: QWidget) -> None:
    for widget in (root, *root.findChildren(QWidget)):
        if not isinstance(widget, _INTERACTIVE_TYPES):
            continue
        if not widget.accessibleName().strip():
            widget.setAccessibleName(_accessible_name(widget))
        if not widget.accessibleDescription().strip():
            description = widget.toolTip().strip()
            if not description:
                description = f"Interactive control: {widget.accessibleName()}"
            widget.setAccessibleDescription(description)


def _apply_tab_order(root: QWidget) -> None:
    """Make the visible focus chain deterministic for each top-level window."""
    if not root.isVisible():
        return
    focusable = [
        widget for widget in (root, *root.findChildren(QWidget))
        if (
            widget is not root
            and widget.isVisibleTo(root)
            and widget.isEnabled()
            and widget.focusPolicy() != Qt.FocusPolicy.NoFocus
        )
    ]
    focusable.sort(key=lambda widget: widget.mapTo(root, QPoint(0, 0)).toTuple()[::-1])
    for first, second in zip(focusable, focusable[1:]):
        QWidget.setTabOrder(first, second)


def apply_accessibility(root: QWidget) -> None:
    """Assign names/descriptions and refresh the visible focus chain."""
    _apply_names(root)
    if isinstance(root, (QDialog, QMainWindow)):
        _apply_tab_order(root)


class AccessibilityManager(QObject):
    """Apply accessibility metadata to dialogs and controls created later."""

    def __init__(self, app, parent=None):
        super().__init__(parent or app)
        self.app = app

    def apply(self, root: QWidget) -> None:
        apply_accessibility(root)

    def eventFilter(self, watched, event):  # noqa: N802 - Qt virtual method name
        if not isinstance(watched, QWidget):
            return False
        if event.type() in {QEvent.Type.Show, QEvent.Type.Polish}:
            top_level = watched.window()
            if top_level is watched:
                self.apply(top_level)
            else:
                _apply_names(watched)
        elif event.type() == QEvent.Type.KeyPress:
            key_event = event
            if (
                isinstance(watched, QAbstractButton)
                and key_event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and watched.isEnabled()
                and not key_event.isAutoRepeat()
            ):
                watched.click()
                return True
        return False


def install_accessibility(app) -> AccessibilityManager:
    """Install the application-wide accessibility metadata and key handler."""
    old_manager = getattr(app, "_fileorganizer_accessibility_manager", None)
    if old_manager is not None:
        app.removeEventFilter(old_manager)
    manager = AccessibilityManager(app, app)
    app.installEventFilter(manager)
    app._fileorganizer_accessibility_manager = manager
    return manager
