"""Visual editor for nested Hazel-style rule chains."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from fileorganizer.config import get_active_stylesheet
from fileorganizer.rule_chains import (
    ACTION_TYPES,
    CONDITION_OPERATORS,
    CONDITION_TYPES,
    RuleAction,
    RuleChain,
    RuleChainManager,
    RuleCondition,
    RuleValidationError,
)


_EDITABLE_ACTION_TYPES = ("move", "rename", "skip", "webhook")


class RuleChainEditorDialog(QDialog):
    """Edit root rules, nested THEN rules, conditions, and ordered actions."""

    def __init__(self, parent=None, manager: RuleChainManager | None = None):
        super().__init__(parent)
        self.setWindowTitle("Automation Rule Chains")
        self.resize(1080, 700)
        self.setStyleSheet(get_active_stylesheet())
        self.manager = manager or RuleChainManager()
        self.chains = [RuleChain.from_dict(chain.to_dict()) for chain in self.manager.chains]
        self._loading = False
        self.rule_tree: QTreeWidget
        self.name_edit: QLineEdit
        self.enabled_check: QCheckBox
        self.logic_combo: QComboBox
        self.conditions_table: QTableWidget
        self.actions_table: QTableWidget
        self.status_label: QLabel

        root = QVBoxLayout(self)
        intro = QLabel(
            "Rules run in order before the standard organize destination is planned. "
            "Skip omits an item; Move and Rename are written into the editable move plan "
            "and retain its validation, dry-run, journal, and undo protections."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)
        splitter.addWidget(self._build_tree_panel())
        splitter.addWidget(self._build_editor_panel())
        splitter.setSizes([300, 760])

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save_all)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._refresh_tree()
        if self.manager.load_error:
            self.status_label.setText(
                f"The existing rules file could not be loaded: {self.manager.load_error}"
            )

    def _build_tree_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.addWidget(QLabel("RULE ORDER / THEN CHAINS"))
        self.rule_tree = QTreeWidget()
        self.rule_tree.setHeaderHidden(True)
        self.rule_tree.currentItemChanged.connect(self._selection_changed)
        layout.addWidget(self.rule_tree, 1)

        row = QHBoxLayout()
        add_root = QPushButton("+ Rule")
        add_root.clicked.connect(lambda: self._add_root())
        add_then = QPushButton("+ THEN")
        add_then.clicked.connect(lambda: self._add_then())
        remove = QPushButton("Remove")
        remove.clicked.connect(lambda: self._remove_selected())
        row.addWidget(add_root)
        row.addWidget(add_then)
        row.addWidget(remove)
        layout.addLayout(row)
        return panel

    def _build_editor_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(8, 0, 0, 0)

        form = QFormLayout()
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("Rule name")
        form.addRow("Name", self.name_edit)
        self.enabled_check = QCheckBox("Enabled")
        self.enabled_check.setChecked(True)
        form.addRow("State", self.enabled_check)
        self.logic_combo = QComboBox()
        self.logic_combo.addItems(["AND", "OR"])
        form.addRow("Match conditions", self.logic_combo)
        layout.addLayout(form)

        condition_header = QHBoxLayout()
        condition_header.addWidget(QLabel("IF CONDITIONS"))
        condition_header.addStretch()
        add_condition = QPushButton("+ Condition")
        add_condition.clicked.connect(lambda: self._add_condition())
        remove_condition = QPushButton("Remove selected")
        remove_condition.clicked.connect(
            lambda: self._remove_rows(self.conditions_table)
        )
        condition_header.addWidget(add_condition)
        condition_header.addWidget(remove_condition)
        layout.addLayout(condition_header)

        self.conditions_table = QTableWidget(0, 4)
        self.conditions_table.setHorizontalHeaderLabels(
            ["Type", "Operator", "Metadata property", "Value"]
        )
        condition_header_view = self.conditions_table.horizontalHeader()
        if condition_header_view is not None:
            condition_header_view.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.conditions_table, 1)

        action_header = QHBoxLayout()
        action_header.addWidget(QLabel("THEN ACTIONS (ORDERED)"))
        action_header.addStretch()
        add_action = QPushButton("+ Action")
        add_action.clicked.connect(lambda: self._add_action())
        remove_action = QPushButton("Remove selected")
        remove_action.clicked.connect(lambda: self._remove_rows(self.actions_table))
        action_header.addWidget(add_action)
        action_header.addWidget(remove_action)
        layout.addLayout(action_header)

        self.actions_table = QTableWidget(0, 2)
        self.actions_table.setHorizontalHeaderLabels(["Action", "Destination / template"])
        action_header_view = self.actions_table.horizontalHeader()
        if action_header_view is not None:
            action_header_view.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.actions_table, 1)
        hint = QLabel(
            "Move destinations may be relative to the configured destination root and use "
            "$DEST_ROOT, $CATEGORY, $NAME, $YEAR, $MONTH, or $DAY. Rename values must "
            "resolve to one filename component. Webhooks are retained as deferred plan "
            "metadata and are not sent during organize. Action order is top to bottom."
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        return panel

    def _refresh_tree(self, selected: RuleChain | None = None) -> None:
        self._loading = True
        self.rule_tree.clear()

        def add_chain(chain: RuleChain, parent: QTreeWidgetItem | None = None) -> None:
            label = chain.name or "Unnamed rule"
            if not chain.enabled:
                label += " (disabled)"
            item = QTreeWidgetItem([label])
            item.setData(0, Qt.ItemDataRole.UserRole, chain)
            if parent is None:
                self.rule_tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            for child in chain.then_chains:
                add_chain(child, item)
            if chain is selected:
                self.rule_tree.setCurrentItem(item)

        for chain in self.chains:
            add_chain(chain)
        self.rule_tree.expandAll()
        if self.rule_tree.currentItem() is None and self.rule_tree.topLevelItemCount():
            self.rule_tree.setCurrentItem(self.rule_tree.topLevelItem(0))
        self._loading = False
        current = self.rule_tree.currentItem()
        self._load_chain(self._chain_for_item(current) if current else None)

    @staticmethod
    def _chain_for_item(item: QTreeWidgetItem | None) -> RuleChain | None:
        if item is None:
            return None
        value = item.data(0, Qt.ItemDataRole.UserRole)
        return value if isinstance(value, RuleChain) else None

    def _selection_changed(
        self,
        current: QTreeWidgetItem | None,
        previous: QTreeWidgetItem | None,
    ) -> None:
        if self._loading:
            return
        self._save_editor_to_chain(self._chain_for_item(previous))
        self._load_chain(self._chain_for_item(current))

    def _load_chain(self, chain: RuleChain | None) -> None:
        self._loading = True
        enabled = chain is not None
        for widget in (
            self.name_edit,
            self.enabled_check,
            self.logic_combo,
            self.conditions_table,
            self.actions_table,
        ):
            widget.setEnabled(enabled)
        self.conditions_table.setRowCount(0)
        self.actions_table.setRowCount(0)
        if chain is not None:
            self.name_edit.setText(chain.name or "")
            self.enabled_check.setChecked(chain.enabled)
            self.logic_combo.setCurrentText(chain.logical_operator)
            for condition in chain.conditions:
                self._add_condition(condition)
            for action in chain.actions:
                self._add_action(action)
        else:
            self.name_edit.clear()
        self._loading = False

    def _add_condition(self, condition: RuleCondition | None = None) -> None:
        row = self.conditions_table.rowCount()
        self.conditions_table.insertRow(row)
        type_combo = QComboBox()
        type_combo.addItems(sorted(CONDITION_TYPES))
        type_combo.setCurrentText(condition.type if condition else "filename_pattern")
        operator_combo = QComboBox()
        operator_combo.addItems(sorted(CONDITION_OPERATORS))
        operator_combo.setCurrentText(condition.operator if condition else "contains")
        self.conditions_table.setCellWidget(row, 0, type_combo)
        self.conditions_table.setCellWidget(row, 1, operator_combo)
        self.conditions_table.setItem(
            row, 2, QTableWidgetItem(condition.property or "" if condition else "")
        )
        value = "" if condition is None or condition.value is None else str(condition.value)
        self.conditions_table.setItem(row, 3, QTableWidgetItem(value))

    def _add_action(self, action: RuleAction | None = None) -> None:
        row = self.actions_table.rowCount()
        self.actions_table.insertRow(row)
        type_combo = QComboBox()
        type_combo.addItems(list(_EDITABLE_ACTION_TYPES))
        action_type = action.type if action and action.type in ACTION_TYPES else "skip"
        type_combo.setCurrentText(action_type)
        self.actions_table.setCellWidget(row, 0, type_combo)
        value = ""
        if action is not None:
            value = action.destination or action.template or action.url or ""
        self.actions_table.setItem(row, 1, QTableWidgetItem(value))

    @staticmethod
    def _remove_rows(table: QTableWidget) -> None:
        rows = sorted({index.row() for index in table.selectedIndexes()}, reverse=True)
        for row in rows:
            table.removeRow(row)

    def _save_editor_to_chain(self, chain: RuleChain | None) -> None:
        if chain is None or self._loading:
            return
        chain.name = self.name_edit.text().strip() or None
        chain.enabled = self.enabled_check.isChecked()
        chain.logical_operator = self.logic_combo.currentText()
        conditions: list[RuleCondition] = []
        for row in range(self.conditions_table.rowCount()):
            type_combo = self.conditions_table.cellWidget(row, 0)
            operator_combo = self.conditions_table.cellWidget(row, 1)
            if not isinstance(type_combo, QComboBox) or not isinstance(
                operator_combo, QComboBox
            ):
                raise RuleValidationError(f"condition row {row + 1} is incomplete")
            property_item = self.conditions_table.item(row, 2)
            value_item = self.conditions_table.item(row, 3)
            conditions.append(RuleCondition(
                type=type_combo.currentText(),
                operator=operator_combo.currentText(),
                property=(property_item.text().strip() or None) if property_item else None,
                value=value_item.text() if value_item else "",
            ))
        chain.conditions = conditions
        actions: list[RuleAction] = []
        for row in range(self.actions_table.rowCount()):
            type_combo = self.actions_table.cellWidget(row, 0)
            if not isinstance(type_combo, QComboBox):
                raise RuleValidationError(f"action row {row + 1} is incomplete")
            value_item = self.actions_table.item(row, 1)
            action_type = type_combo.currentText()
            value = value_item.text().strip() if value_item else ""
            actions.append(RuleAction(
                type=action_type,
                destination=value if action_type == "move" else None,
                template=value if action_type == "rename" else None,
                url=value if action_type == "webhook" else None,
            ))
        chain.actions = actions

    def _add_root(self) -> None:
        current = self._chain_for_item(self.rule_tree.currentItem())
        self._save_editor_to_chain(current)
        chain = RuleChain(name=f"Rule {len(self.chains) + 1}")
        self.chains.append(chain)
        self._refresh_tree(chain)

    def _add_then(self) -> None:
        current = self._chain_for_item(self.rule_tree.currentItem())
        if current is None:
            self.status_label.setText("Select a parent rule before adding THEN.")
            return
        self._save_editor_to_chain(current)
        child = RuleChain(name="Then rule")
        current.then_chains.append(child)
        self._refresh_tree(child)

    def _remove_selected(self) -> None:
        selected = self._chain_for_item(self.rule_tree.currentItem())
        if selected is None:
            return

        def remove(chains: list[RuleChain]) -> bool:
            for index, chain in enumerate(chains):
                if chain is selected:
                    chains.pop(index)
                    return True
                if remove(chain.then_chains):
                    return True
            return False

        remove(self.chains)
        self._refresh_tree()

    def _save_all(self) -> None:
        self._save_editor_to_chain(self._chain_for_item(self.rule_tree.currentItem()))
        try:
            self.manager.replace_chains(self.chains)
        except RuleValidationError as exc:
            self.status_label.setText(str(exc))
            QMessageBox.warning(self, "Rule chains not saved", str(exc))
            return
        self.accept()
