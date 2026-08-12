"""Organized-library browser with controlled drag/drop reclassification."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPixmap
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton, QInputDialog, QMessageBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fileorganizer.config import get_active_stylesheet, get_active_theme
from fileorganizer.asset_bundles import (
    add_assets, asset_fingerprint, bundle_members, create_bundle, delete_bundle,
    list_bundles, remove_members,
)
from fileorganizer.library_search import index_library, search_library
from fileorganizer.reclassification import reclassify_folder
from fileorganizer.workers import format_size
from fileorganizer.waveform import AUDIO_EXTENSIONS, render_waveform


BUNDLE_ID_ROLE = Qt.ItemDataRole.UserRole + 20
BUNDLE_FINGERPRINT_ROLE = Qt.ItemDataRole.UserRole + 21


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

    def __init__(self, parent=None, bundle_db_path=None):
        super().__init__(parent)
        self.setStyleSheet(get_active_stylesheet())
        self._indexed_search_root = ""
        self._bundle_db_path = bundle_db_path
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

        search_row = QHBoxLayout()
        search_row.addWidget(QLabel("Natural-language search:"))
        self.txt_query = QLineEdit()
        self.txt_query.setPlaceholderText("e.g. show invoice scans or mountain landscape")
        self.txt_query.returnPressed.connect(self._search)
        search_row.addWidget(self.txt_query, 1)
        search = QPushButton("Search")
        search.clicked.connect(self._search)
        search_row.addWidget(search)
        reindex = QPushButton("Reindex")
        reindex.setToolTip("Refresh the local FTS5 index from the organized root")
        reindex.clicked.connect(self._reindex_search)
        search_row.addWidget(reindex)
        lay.addLayout(search_row)

        bundle_row = QHBoxLayout()
        bundle_row.addWidget(QLabel("Virtual bundles:"))
        new_bundle = QPushButton("New Bundle")
        new_bundle.setToolTip("Create a named, non-destructive virtual folder")
        new_bundle.clicked.connect(self._new_bundle)
        bundle_row.addWidget(new_bundle)
        add_bundle = QPushButton("Add Selected")
        add_bundle.setToolTip("Add selected asset folders to a virtual bundle")
        add_bundle.clicked.connect(self._add_selected_to_bundle)
        bundle_row.addWidget(add_bundle)
        remove_bundle = QPushButton("Remove Selected")
        remove_bundle.setToolTip("Remove selected assets from their virtual bundle")
        remove_bundle.clicked.connect(self._remove_selected_from_bundle)
        bundle_row.addWidget(remove_bundle)
        delete_bundle_button = QPushButton("Delete Bundle")
        delete_bundle_button.setToolTip("Delete a virtual bundle without deleting assets")
        delete_bundle_button.clicked.connect(self._delete_selected_bundle)
        bundle_row.addWidget(delete_bundle_button)
        bundle_row.addStretch()
        lay.addLayout(bundle_row)

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
        self.tree.itemSelectionChanged.connect(
            lambda: self._show_item_details(self.tree)
        )
        lay.addWidget(self.tree, 1)

        self.search_tree = QTreeWidget()
        self.search_tree.setHeaderLabels(["Match", "Category", "Description", "Score"])
        self.search_tree.setAlternatingRowColors(True)
        self.search_tree.setRootIsDecorated(False)
        self.search_tree.setMinimumHeight(130)
        self.search_tree.setVisible(False)
        self.search_tree.itemSelectionChanged.connect(
            lambda: self._show_item_details(self.search_tree)
        )
        lay.addWidget(self.search_tree)

        self.detail_panel = QWidget()
        self.detail_panel.setMaximumHeight(220)
        detail_layout = QVBoxLayout(self.detail_panel)
        detail_layout.setContentsMargins(0, 4, 0, 0)
        self.lbl_detail_name = QLabel("Select an asset to inspect")
        self.lbl_detail_name.setProperty("class", "subheading-sm")
        detail_layout.addWidget(self.lbl_detail_name)
        self.lbl_detail_meta = QLabel("")
        self.lbl_detail_meta.setProperty("class", "meta")
        detail_layout.addWidget(self.lbl_detail_meta)
        self.lbl_waveform = QLabel("No audio waveform selected")
        self.lbl_waveform.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_waveform.setMinimumHeight(140)
        self.lbl_waveform.setProperty("class", "preview-surface")
        detail_layout.addWidget(self.lbl_waveform)
        lay.addWidget(self.detail_panel)

        self.lbl_status = QLabel("Choose an organized root to browse.")
        self.lbl_status.setProperty("class", "meta")
        lay.addWidget(self.lbl_status)

        self._green = QColor(theme["green"])

    def _browse_root(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Organized Library")
        if folder:
            self.txt_root.setText(folder)
            self.refresh()

    def _reindex_search(self):
        root = self.txt_root.text().strip()
        if not root or not os.path.isdir(root):
            self.lbl_status.setText("Choose an existing organized root before indexing.")
            return
        count = index_library(root)
        self._indexed_search_root = os.path.normcase(os.path.abspath(root))
        self.lbl_status.setText(f"Search index refreshed: {count} folders/files.")
        if self.txt_query.text().strip():
            self._run_search(root)

    def _search(self):
        root = self.txt_root.text().strip()
        if not root or not os.path.isdir(root):
            self.lbl_status.setText("Choose an existing organized root before searching.")
            return
        query = self.txt_query.text().strip()
        if not query:
            self.search_tree.clear()
            self.search_tree.setVisible(False)
            self.lbl_status.setText("Enter a search phrase.")
            return
        normalized = os.path.normcase(os.path.abspath(root))
        if normalized != self._indexed_search_root:
            self._reindex_search()
        self._run_search(root)

    def _run_search(self, root: str):
        results = search_library(self.txt_query.text().strip(), library_root=root)
        self.search_tree.clear()
        for result in results:
            item = QTreeWidgetItem([
                result["name"],
                result["category"],
                result["description"],
                f"{result['score']:.3f}",
            ])
            item.setData(0, Qt.ItemDataRole.UserRole, result["path"])
            item.setToolTip(0, result["citation"])
            self.search_tree.addTopLevelItem(item)
        self.search_tree.setVisible(True)
        self.lbl_status.setText(
            f"Search: {len(results)} result(s). Results include local path citations."
        )

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
                item.setData(0, BUNDLE_FINGERPRINT_ROLE, asset_fingerprint(asset_entry.path))
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

        # Virtual bundles are rendered as a separate, non-filesystem tree after
        # categories are scanned so a bundle can resolve members that moved.
        bundles = list_bundles(db_path=self._bundle_db_path) if self._bundle_db_path else list_bundles()
        if bundles:
            virtual_root = QTreeWidgetItem(["Virtual Bundles", "", "", ""])
            virtual_root.setToolTip(0, "Non-destructive groupings; files stay in their categories")
            virtual_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.tree.addTopLevelItem(virtual_root)
            records_by_fingerprint = {}
            for category_item_index in range(self.tree.topLevelItemCount() - 1):
                category_item = self.tree.topLevelItem(category_item_index)
                for member_index in range(category_item.childCount()):
                    member = category_item.child(member_index)
                    fingerprint = member.data(0, BUNDLE_FINGERPRINT_ROLE)
                    if fingerprint:
                        records_by_fingerprint.setdefault(fingerprint, []).append(member)
            for bundle in bundles:
                bundle_item = QTreeWidgetItem([
                    bundle["name"],
                    f"{bundle['member_count']} assets",
                    "",
                    "",
                ])
                bundle_item.setData(0, BUNDLE_ID_ROLE, int(bundle["id"]))
                bundle_item.setToolTip(0, "Virtual bundle — no files are moved")
                bundle_item.setFlags(
                    Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                )
                virtual_root.addChild(bundle_item)
                resolved_count = 0
                for member in bundle_members(int(bundle["id"]), db_path=self._bundle_db_path) if self._bundle_db_path else bundle_members(int(bundle["id"])):
                    fingerprint = member["fingerprint"]
                    matches = records_by_fingerprint.get(fingerprint, [])
                    if not matches:
                        missing = QTreeWidgetItem([
                            f"[Missing] {member['asset_name'] or member['path_hint'] or fingerprint[:12]}",
                            "",
                            "",
                            "",
                        ])
                        missing.setData(0, BUNDLE_ID_ROLE, int(bundle["id"]))
                        missing.setData(0, BUNDLE_FINGERPRINT_ROLE, fingerprint)
                        missing.setToolTip(0, member["path_hint"] or "Asset is not in the current Browse root")
                        missing.setFlags(
                            Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                        )
                        bundle_item.addChild(missing)
                        continue
                    for source_item in matches:
                        child = QTreeWidgetItem([
                            source_item.text(0),
                            source_item.text(1),
                            source_item.text(2),
                            source_item.text(3),
                        ])
                        child.setData(0, Qt.ItemDataRole.UserRole, source_item.data(0, Qt.ItemDataRole.UserRole))
                        child.setData(0, BUNDLE_ID_ROLE, int(bundle["id"]))
                        child.setData(0, BUNDLE_FINGERPRINT_ROLE, fingerprint)
                        child.setToolTip(0, source_item.toolTip(0))
                        child.setFlags(
                            Qt.ItemFlag.ItemIsEnabled
                            | Qt.ItemFlag.ItemIsSelectable
                            | Qt.ItemFlag.ItemIsDragEnabled
                        )
                        bundle_item.addChild(child)
                        resolved_count += 1
                bundle_item.setText(2, str(resolved_count))
                bundle_item.setExpanded(True)
            virtual_root.setText(1, f"{len(bundles)} bundles")
            virtual_root.setExpanded(True)

    def _new_bundle(self):
        name, accepted = QInputDialog.getText(self, "New Virtual Bundle", "Bundle name:")
        if not accepted:
            return
        try:
            create_bundle(name, **({"db_path": self._bundle_db_path} if self._bundle_db_path else {}))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Bundle not created", str(exc))
            return
        self.lbl_status.setText(f"Created virtual bundle: {name.strip()}")
        self.refresh()

    def _selected_asset_paths(self) -> list[str]:
        paths = []
        for item in self.tree.selectedItems():
            value = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(value, str) and value and os.path.exists(value):
                paths.append(value)
        return list(dict.fromkeys(paths))

    def _add_selected_to_bundle(self):
        paths = self._selected_asset_paths()
        if not paths:
            self.lbl_status.setText("Select one or more asset folders first.")
            return
        bundles = list_bundles(db_path=self._bundle_db_path) if self._bundle_db_path else list_bundles()
        if not bundles:
            self.lbl_status.setText("Create a virtual bundle first.")
            return
        names = [bundle["name"] for bundle in bundles]
        name, accepted = QInputDialog.getItem(self, "Add to Virtual Bundle", "Bundle:", names, 0, False)
        if not accepted:
            return
        bundle = next(bundle for bundle in bundles if bundle["name"] == name)
        kwargs = {"db_path": self._bundle_db_path} if self._bundle_db_path else {}
        added = add_assets(int(bundle["id"]), paths, **kwargs)
        self.lbl_status.setText(f"Added {added} asset(s) to {name}.")
        self.refresh()

    def _remove_selected_from_bundle(self):
        removals = []
        for item in self.tree.selectedItems():
            fingerprint = item.data(0, BUNDLE_FINGERPRINT_ROLE)
            bundle_id = item.data(0, BUNDLE_ID_ROLE)
            if fingerprint and bundle_id:
                removals.append((int(bundle_id), str(fingerprint)))
        if not removals:
            self.lbl_status.setText("Select virtual-bundle members to remove.")
            return
        kwargs = {"db_path": self._bundle_db_path} if self._bundle_db_path else {}
        removed = sum(
            remove_members(bundle_id, [fingerprint], **kwargs)
            for bundle_id, fingerprint in removals
        )
        self.lbl_status.setText(f"Removed {removed} asset(s) from virtual bundles.")
        self.refresh()

    def _delete_selected_bundle(self):
        selected = self.tree.selectedItems()
        if not selected:
            self.lbl_status.setText("Select a virtual bundle first.")
            return
        item = selected[0]
        bundle_id = item.data(0, BUNDLE_ID_ROLE)
        if not bundle_id and item.parent():
            bundle_id = item.parent().data(0, BUNDLE_ID_ROLE)
        if not bundle_id:
            self.lbl_status.setText("Select a virtual bundle first.")
            return
        answer = QMessageBox.question(
            self,
            "Delete Virtual Bundle",
            "Delete this virtual bundle? The underlying files will not be changed.",
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        kwargs = {"db_path": self._bundle_db_path} if self._bundle_db_path else {}
        delete_bundle(int(bundle_id), **kwargs)
        self.lbl_status.setText("Virtual bundle deleted; files were not changed.")
        self.refresh()

    def _on_reclassify(self, source_path: str, root: str, target_category: str):
        try:
            result = reclassify_folder(source_path, root, target_category)
        except Exception as exc:
            self.lbl_status.setText(f"Reclassification blocked: {exc}")
            return
        self.refresh()
        self._indexed_search_root = ""
        self.lbl_status.setText(
            f"{result.message} User corrections: {result.user_corrections}."
        )

    @staticmethod
    def _find_audio_preview(path: str) -> str | None:
        if os.path.isfile(path) and os.path.splitext(path)[1].casefold() in AUDIO_EXTENSIONS:
            return path
        if not os.path.isdir(path):
            return None
        try:
            for dirpath, dirnames, filenames in os.walk(path, followlinks=False):
                dirnames[:] = sorted(
                    name for name in dirnames
                    if not os.path.islink(os.path.join(dirpath, name))
                )
                for filename in sorted(filenames):
                    if os.path.splitext(filename)[1].casefold() in AUDIO_EXTENSIONS:
                        return os.path.join(dirpath, filename)
        except OSError:
            return None
        return None

    def _show_item_details(self, tree):
        selected = tree.selectedItems()
        if not selected:
            return
        path = selected[0].data(0, Qt.ItemDataRole.UserRole)
        if not isinstance(path, str) or not path:
            self.lbl_detail_name.setText(selected[0].text(0))
            self.lbl_detail_meta.setText("Virtual folder")
            self.lbl_waveform.clear()
            self.lbl_waveform.setText("Select an asset to inspect")
            return
        self.lbl_detail_name.setText(os.path.basename(path) or path)
        if os.path.isdir(path):
            _folders, files, total = self._folder_stats(path)
            self.lbl_detail_meta.setText(f"{files} files · {format_size(total)} · {path}")
        else:
            try:
                self.lbl_detail_meta.setText(
                    f"{format_size(os.path.getsize(path))} · {path}"
                )
            except OSError:
                self.lbl_detail_meta.setText(path)
        audio_path = self._find_audio_preview(path)
        if not audio_path:
            self.lbl_waveform.clear()
            self.lbl_waveform.setText("No audio waveform selected")
            return
        waveform = render_waveform(
            audio_path,
            width=max(320, self.lbl_waveform.width()),
            height=140,
        )
        if waveform:
            pixmap = QPixmap(waveform)
            if not pixmap.isNull():
                self.lbl_waveform.setPixmap(
                    pixmap.scaled(
                        max(320, self.lbl_waveform.width()),
                        140,
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                )
                return
        self.lbl_waveform.clear()
        self.lbl_waveform.setText("Waveform unavailable for this audio format")


__all__ = ["BrowsePanel", "BrowseTreeWidget"]
