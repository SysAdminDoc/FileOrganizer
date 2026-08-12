"""Local-only analytics dashboard dialog."""

from __future__ import annotations

from typing import Any

from PyQt6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QHeaderView,
    QAbstractItemView,
)

from fileorganizer.analytics import load_analytics_snapshot
from fileorganizer.config import get_active_stylesheet


def _format_bytes(value: object) -> str:
    try:
        raw = value if isinstance(value, (int, float, str)) else 0
        amount = max(0, int(raw))
    except (TypeError, ValueError):
        amount = 0
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.1f} {unit}" if unit != "B" else f"{amount} B"
        amount /= 1024
    return "0 B"


class AnalyticsDashboardDialog(QDialog):
    """Show aggregate local activity without exposing file paths or prompts."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Local Analytics Dashboard")
        self.setMinimumSize(820, 600)
        self.setStyleSheet(get_active_stylesheet())

        layout = QVBoxLayout(self)
        title = QLabel("FileOrganizer impact")
        title.setProperty("class", "title")
        layout.addWidget(title)
        self.lbl_note = QLabel(
            "Local-only aggregates from move history, duplicate reviews, and classification provenance. "
            "No paths, prompts, or telemetry are sent."
        )
        self.lbl_note.setWordWrap(True)
        layout.addWidget(self.lbl_note)

        self.metric_values: dict[str, QLabel] = {}
        metrics = QGridLayout()
        metric_names = (
            ("organized", "Organized"),
            ("duplicates", "Duplicates detected"),
            ("accuracy", "Correction-free rate"),
            ("storage", "Moved to Archives"),
        )
        for index, (key, label) in enumerate(metric_names):
            card = QVBoxLayout()
            card.addWidget(QLabel(label))
            value = QLabel("0")
            value.setProperty("class", "stat-value")
            card.addWidget(value)
            self.metric_values[key] = value
            metrics.addLayout(card, index // 2, index % 2)
        layout.addLayout(metrics)

        self.tabs = QTabWidget()
        self.tbl_categories = self._table(("Category", "Count", "Share"))
        self.tbl_types = self._table(("File type", "Count"))
        self.tbl_accuracy = self._table(("Month", "Classified", "Corrections", "Rate"))
        self.tbl_confusion = self._table(("Suggested", "Final", "Count"))
        self.tabs.addTab(self.tbl_categories, "Categories")
        self.tabs.addTab(self.tbl_types, "File types")
        self.tabs.addTab(self.tbl_accuracy, "Model trend")
        self.tabs.addTab(self.tbl_confusion, "Confusion matrix")
        layout.addWidget(self.tabs, 1)

        buttons = QHBoxLayout()
        buttons.addStretch()
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        buttons.addWidget(refresh)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        buttons.addWidget(close)
        layout.addLayout(buttons)
        self.refresh()

    @staticmethod
    def _table(headers: tuple[str, ...]) -> QTableWidget:
        table = QTableWidget(0, len(headers))
        table.setHorizontalHeaderLabels(list(headers))
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = table.horizontalHeader()
        if header is not None:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    @staticmethod
    def _set_empty(table: QTableWidget, columns: int) -> None:
        table.setRowCount(1)
        table.setSpan(0, 0, 1, columns)
        table.setItem(0, 0, QTableWidgetItem("No local history yet."))

    @staticmethod
    def _rate(value: object) -> str:
        try:
            raw = value if isinstance(value, (int, float, str)) else 0
            return f"{float(raw) * 100:.1f}%"
        except (TypeError, ValueError):
            return "0.0%"

    def refresh(self) -> None:
        snapshot = load_analytics_snapshot()
        organized = snapshot.get("organized", {})
        model = snapshot.get("model", {})
        duplicates = snapshot.get("duplicates", {})
        total_organized = int(organized.get("total", 0) or 0)
        duplicate_total = int(duplicates.get("duplicates", 0) or 0)
        self.metric_values["organized"].setText(f"{total_organized:,}")
        self.metric_values["duplicates"].setText(
            f"{duplicate_total:,} ({self._rate(duplicates.get('rate'))})"
        )
        self.metric_values["accuracy"].setText(self._rate(model.get("accuracy")))
        self.metric_values["storage"].setText(
            _format_bytes(snapshot.get("storage_reclaimed_bytes", 0))
        )
        self._populate_categories(organized.get("by_category", []), total_organized)
        self._populate_simple(
            self.tbl_types,
            organized.get("top_file_types", []),
            ("extension", "count"),
            (str, lambda value: f"{int(value or 0):,}"),
        )
        self._populate_simple(
            self.tbl_accuracy,
            model.get("by_month", []),
            ("month", "total", "corrected", "accuracy"),
            (str, lambda value: f"{int(value or 0):,}", lambda value: f"{int(value or 0):,}", self._rate),
        )
        self._populate_simple(
            self.tbl_confusion,
            model.get("confusion_matrix", []),
            ("suggested", "final", "count"),
            (str, str, lambda value: f"{int(value or 0):,}"),
        )

    def _populate_categories(self, rows: object, total: int) -> None:
        records = rows if isinstance(rows, list) else []
        self.tbl_categories.clearContents()
        if not records:
            self._set_empty(self.tbl_categories, 3)
            return
        maximum = max(int(record.get("count", 0) or 0) for record in records)
        self.tbl_categories.setRowCount(len(records))
        for row_index, record in enumerate(records):
            count = int(record.get("count", 0) or 0)
            self.tbl_categories.setItem(
                row_index, 0, QTableWidgetItem(str(record.get("category", "")))
            )
            self.tbl_categories.setItem(row_index, 1, QTableWidgetItem(f"{count:,}"))
            self.tbl_categories.setItem(
                row_index, 2, QTableWidgetItem(self._rate(count / total if total else 0))
            )
            bar = QProgressBar()
            bar.setRange(0, maximum or 1)
            bar.setValue(count)
            bar.setTextVisible(False)
            self.tbl_categories.setCellWidget(row_index, 2, bar)

    def _populate_simple(
        self,
        table: QTableWidget,
        rows: object,
        keys: tuple[str, ...],
        formatters: tuple[Any, ...],
    ) -> None:
        records = rows if isinstance(rows, list) else []
        table.clearContents()
        if not records:
            self._set_empty(table, len(keys))
            return
        table.setRowCount(len(records))
        for row_index, record in enumerate(records):
            for column, (key, formatter) in enumerate(zip(keys, formatters)):
                value = record.get(key, "") if isinstance(record, dict) else ""
                try:
                    text = formatter(value)
                except (TypeError, ValueError):
                    text = str(value)
                table.setItem(row_index, column, QTableWidgetItem(text))


__all__ = ["AnalyticsDashboardDialog"]
