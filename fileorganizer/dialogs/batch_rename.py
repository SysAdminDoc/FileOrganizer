"""Inline batch-rename preview dialog."""

from __future__ import annotations

import os

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from fileorganizer.batch_rename import (
    CANONICAL_TEMPLATE,
    item_source_path,
    item_target_path,
    item_value,
    proposed_filename,
)
from fileorganizer.config import get_active_stylesheet
from fileorganizer.path_safety import PathSafetyError, validate_storage_name


class BatchRenameDialog(QDialog):
    """Preview and edit safe names for the pending items in a category."""

    _COLUMNS = ('Category', 'Current name', 'Proposed name', 'Pending target')

    def __init__(self, items: list, parent=None, *, template: str = CANONICAL_TEMPLATE):
        super().__init__(parent)
        self.setWindowTitle("Batch Rename Preview")
        self.setMinimumSize(900, 520)
        self.setStyleSheet(get_active_stylesheet())
        self.items = list(items)
        self.template = template
        self.renamed_items: list[tuple[object, str]] = []
        self._proposals: dict[int, str] = {}
        self._manual_indexes: set[int] = set()
        self._updating = False

        lay = QVBoxLayout(self)
        intro = QLabel(
            "Review the proposed canonical names before they are added to the "
            "pending operation plan. Editing a row changes the plan only; disk "
            "is not touched until Apply."
        )
        intro.setWordWrap(True)
        lay.addWidget(intro)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Category:"))
        self.cmb_category = QComboBox()
        self.cmb_category.addItem("All categories", "")
        categories = sorted({
            str(item_value(item, 'category', '') or '')
            for item in self.items
            if item_value(item, 'category', '')
        })
        for category in categories:
            self.cmb_category.addItem(category, category)
        self.cmb_category.currentIndexChanged.connect(self._refresh_table)
        controls.addWidget(self.cmb_category, 1)
        controls.addWidget(QLabel("Template:"))
        self.txt_template = QLineEdit(template)
        self.txt_template.setToolTip(
            "Fields: {CAT_CODE}, {ID}, {CLEAN_NAME}, {CATEGORY}, {NAME}, {COUNTER}"
        )
        self.txt_template.editingFinished.connect(self._template_changed)
        controls.addWidget(self.txt_template, 2)
        lay.addLayout(controls)

        self.tbl_preview = QTableWidget(0, len(self._COLUMNS))
        self.tbl_preview.setHorizontalHeaderLabels(self._COLUMNS)
        self.tbl_preview.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_preview.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tbl_preview.setEditTriggers(QAbstractItemView.EditTrigger.DoubleClicked)
        self.tbl_preview.horizontalHeader().setStretchLastSection(True)
        self.tbl_preview.setColumnWidth(0, 180)
        self.tbl_preview.setColumnWidth(1, 220)
        self.tbl_preview.setColumnWidth(2, 220)
        self.tbl_preview.itemChanged.connect(self._on_item_changed)
        lay.addWidget(self.tbl_preview, 1)

        self.lbl_status = QLabel("")
        self.lbl_status.setWordWrap(True)
        lay.addWidget(self.lbl_status)

        buttons = QHBoxLayout()
        buttons.addStretch()
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        buttons.addWidget(btn_cancel)
        btn_apply = QPushButton("Use Names")
        btn_apply.setDefault(True)
        btn_apply.clicked.connect(self._accept)
        buttons.addWidget(btn_apply)
        lay.addLayout(buttons)

        self._refresh_table()

    def _visible_indexes(self) -> list[int]:
        category = self.cmb_category.currentData()
        if not category:
            return list(range(len(self.items)))
        return [
            index for index, item in enumerate(self.items)
            if item_value(item, 'category', '') == category
        ]

    @staticmethod
    def _current_name(item) -> str:
        source = item_source_path(item)
        return os.path.basename(source) or str(item_value(item, 'name', '') or '')

    @staticmethod
    def _target_parent(item) -> str:
        target = item_target_path(item)
        return os.path.dirname(target) or os.path.dirname(item_source_path(item))

    def _default_proposal(self, index: int) -> str:
        return proposed_filename(item=self.items[index], index=index + 1, template=self.template)

    def _refresh_table(self):
        self._updating = True
        try:
            indexes = self._visible_indexes()
            self.tbl_preview.setRowCount(0)
            for row, index in enumerate(indexes):
                item = self.items[index]
                proposal = self._proposals.setdefault(index, self._default_proposal(index))
                current = self._current_name(item)
                target = os.path.join(self._target_parent(item), proposal)
                self.tbl_preview.insertRow(row)
                values = (
                    str(item_value(item, 'category', '') or 'Uncategorized'),
                    current,
                    proposal,
                    target,
                )
                for column, value in enumerate(values):
                    cell = QTableWidgetItem(value)
                    cell.setData(Qt.ItemDataRole.UserRole, index)
                    if column != 2:
                        cell.setFlags(cell.flags() & ~Qt.ItemFlag.ItemIsEditable)
                    self.tbl_preview.setItem(row, column, cell)
        finally:
            self._updating = False
        self._validate_preview(update_status=True)

    def _template_changed(self):
        new_template = self.txt_template.text().strip()
        if not new_template:
            self.lbl_status.setText("Template cannot be empty.")
            return
        self.template = new_template
        for index in range(len(self.items)):
            if index not in self._manual_indexes:
                try:
                    self._proposals[index] = self._default_proposal(index)
                except (PathSafetyError, ValueError) as exc:
                    self.lbl_status.setText(f"Template error: {exc}")
                    return
        self._refresh_table()

    def _on_item_changed(self, cell: QTableWidgetItem):
        if self._updating or cell.column() != 2:
            return
        index = cell.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index, int) or not 0 <= index < len(self.items):
            return
        self._manual_indexes.add(index)
        self._proposals[index] = cell.text().strip()
        self._updating = True
        try:
            self.tbl_preview.item(cell.row(), 3).setText(
                os.path.join(self._target_parent(self.items[index]), self._proposals[index])
            )
        finally:
            self._updating = False
        self._validate_preview(update_status=True)

    def _validate_preview(self, *, update_status: bool = False) -> bool:
        seen: set[str] = set()
        errors = []
        for index in self._visible_indexes():
            item = self.items[index]
            proposal = self._proposals.get(index, '')
            try:
                validate_storage_name(proposal)
            except PathSafetyError as exc:
                errors.append(f"{self._current_name(item)}: {exc}")
                continue
            target = os.path.normcase(os.path.abspath(
                os.path.join(self._target_parent(item), proposal)
            ))
            if target in seen:
                errors.append(f"Duplicate target: {proposal}")
            seen.add(target)
            current_target = os.path.normcase(os.path.abspath(item_target_path(item)))
            if os.path.lexists(target) and target != current_target:
                errors.append(f"Target already exists: {proposal}")
        if update_status:
            if errors:
                self.lbl_status.setText("; ".join(errors[:3]))
            else:
                self.lbl_status.setText(
                    f"{len(self._visible_indexes())} item(s) previewed; names are valid."
                )
        return not errors

    def _accept(self):
        if not self._validate_preview(update_status=True):
            return
        self.renamed_items = []
        for index in self._visible_indexes():
            item = self.items[index]
            proposal = self._proposals[index]
            if proposal != self._current_name(item):
                self.renamed_items.append((item, proposal))
        self.accept()


__all__ = ['BatchRenameDialog']
