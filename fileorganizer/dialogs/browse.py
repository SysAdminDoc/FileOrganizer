"""Organized-library browser with controlled drag/drop reclassification."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fileorganizer.config import get_active_stylesheet, get_active_theme
from fileorganizer.reclassification import reclassify_folder
from fileorganizer.workers import format_size


class BrowseTreeWidget(QTreeWidget):
    """Tree that turns a child-to-category drop into an explicit signal."""

    reclassify_requested = pyqtSignal(str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.library_root = ""
        self.setAcceptDrops(True)
        self.setDragEnabled(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)

    @staticmethod
    def _category_item(item):
        if item is None:
            return None
        return item if item.parent() is None else item.parent()

    def dragMoveEvent(self, event):
        target = self._category_item(self.itemAt(event.position().toPoint()))
        if target is not None and target.parent() is None:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
            return
        event.ignore()

    def dropEvent(self, event):
        target = self._category_item(self.itemAt(event.position().toPoint()))
        selected = self.selectedItems()
        if (
            target is None
            or target.parent() is not None
            or not selected
            or selected[0].parent() is None
            or not self.library_root
        ):
            event.ignore()
            return
        source = selected[0]
        source_path = source.data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(source_path, str) or not source_path:
            event.ignore()
            return
        self.reclassify_requested.emit(source_path, self.library_root, target.text(0))
        event.ignore()


class BrowsePanel(QWidget):
    """Browse immediate category children and drag them between categories."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet(get_active_stylesheet())
        self._build_ui()

    def _build_ui(self):
        theme = get_active_theme()
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        intro = QLabel(
            "Browse the organized library. Drag an asset folder onto another "
            "category to move it and teach its exact folder fingerprint."
        )
        intro.setWordWrap(True)
        intro.setProperty("class", "stats")
        lay.addWidget(intro)

        root_row = QHBoxLayout()
        root_row.addWidget(QLabel("Organized root:"))
        self.txt_root = QLineEdit()
        self.txt_root.setPlaceholderText(r"G:\Organized")
        root_row.addWidget(self.txt_root, 1)
        browse = QPushButton("Browse")
        browse.clicked.connect(self._browse_root)
        root_row.addWidget(browse)
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        root_row.addWidget(refresh)
        lay.addLayout(root_row)

        self.tree = BrowseTreeWidget()
        self.tree.setHeaderLabels(["Asset / Category", "Items", "Files", "Size"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.header().setStretchLastSection(False)
        self.tree.setColumnWidth(0, 480)
        self.tree.setColumnWidth(1, 100)
        self.tree.setColumnWidth(2, 90)
        self.tree.setColumnWidth(3, 120)
        self.tree.reclassify_requested.connect(self._on_reclassify)
        lay.addWidget(self.tree, 1)

        self.lbl_status = QLabel("Choose an organized root to browse.")
        self.lbl_status.setProperty("class", "meta")
        lay.addWidget(self.lbl_status)

        self._green = QColor(theme["green"])

    def _browse_root(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Organized Library")
        if folder:
            self.txt_root.setText(folder)
            self.refresh()

    @staticmethod
    def _folder_stats(path: str) -> tuple[int, int, int]:
        folders = 0
        files = 0
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
                dirnames[:] = [name for name in dirnames if not os.path.islink(os.path.join(dirpath, name))]
                folders += len(dirnames)
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    if os.path.islink(file_path):
                        continue
                    try:
                        files += 1
                        total += os.path.getsize(file_path)
                    except OSError:
                        continue
        except OSError:
            pass
        return folders, files, total

    def refresh(self):
        root = self.txt_root.text().strip()
        self.tree.clear()
        self.tree.library_root = root
        if not root or not os.path.isdir(root):
            self.lbl_status.setText("Choose an existing organized root.")
            return

        category_count = 0
        asset_count = 0
        try:
            categories = sorted(
                [entry for entry in os.scandir(root)
                 if entry.is_dir(follow_symlinks=False) and not entry.name.startswith(".")],
                key=lambda entry: entry.name.casefold(),
            )
        except OSError as exc:
            self.lbl_status.setText(f"Cannot browse root: {exc}")
            return

        for category_entry in categories:
            category_count += 1
            category_item = QTreeWidgetItem([category_entry.name, "", "", ""])
            category_item.setForeground(0, self._green)
            category_item.setToolTip(0, category_entry.path)
            category_item.setFlags(
                Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsSelectable
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            self.tree.addTopLevelItem(category_item)
            try:
                assets = sorted(
                    [entry for entry in os.scandir(category_entry.path)
                     if not entry.name.startswith(".")],
                    key=lambda entry: entry.name.casefold(),
                )
            except OSError:
                assets = []
            for asset_entry in assets:
                if not asset_entry.is_dir(follow_symlinks=False):
                    continue
                asset_count += 1
                _folders, files, total = self._folder_stats(asset_entry.path)
                item = QTreeWidgetItem([
                    asset_entry.name,
                    category_entry.name,
                    str(files),
                    format_size(total),
                ])
                item.setToolTip(0, asset_entry.path)
                item.setData(0, Qt.ItemDataRole.UserRole, asset_entry.path)
                item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled
                    | Qt.ItemFlag.ItemIsSelectable
                    | Qt.ItemFlag.ItemIsDragEnabled
                )
                category_item.addChild(item)
            category_item.setText(1, str(category_item.childCount()))
            category_item.setExpanded(True)

        self.lbl_status.setText(
            f"{category_count} categories · {asset_count} assets · "
            "drag an asset onto a category to reclassify"
        )

    def _on_reclassify(self, source_path: str, root: str, target_category: str):
        try:
            result = reclassify_folder(source_path, root, target_category)
        except Exception as exc:
            self.lbl_status.setText(f"Reclassification blocked: {exc}")
            return
        self.refresh()
        self.lbl_status.setText(
            f"{result.message} User corrections: {result.user_corrections}."
        )


__all__ = ["BrowsePanel", "BrowseTreeWidget"]
