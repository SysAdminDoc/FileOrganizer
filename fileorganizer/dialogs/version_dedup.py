"""Version-aware duplicate review dialog."""

from __future__ import annotations

import os
import re

from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QProgressBar,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QHeaderView,
)
from PyQt6.QtGui import QColor

from fileorganizer.config import get_active_stylesheet, get_active_theme
from fileorganizer.workers import format_size


class VersionDedupDialog(QDialog):
    """Scan library folders for same-ID versions and review archive plans."""

    def __init__(self, parent=None, roots=None):
        super().__init__(parent)
        self.setWindowTitle("Version-Aware Deduplication")
        self.resize(1080, 680)
        self.setStyleSheet(get_active_stylesheet())
        self._groups = {}
        self._rows = []
        self._worker = None
        self._build_ui(roots)

    def _build_ui(self, roots):
        theme = get_active_theme()
        lay = QVBoxLayout(self)
        lay.setSpacing(8)

        intro = QLabel(
            "Find folders whose names share a marketplace ID but whose complete "
            "fingerprints or file counts differ. The fullest version is proposed "
            "as keeper; selected older versions are archived with a reason note."
        )
        intro.setWordWrap(True)
        intro.setProperty("class", "stats")
        lay.addWidget(intro)

        roots_row = QHBoxLayout()
        roots_row.addWidget(QLabel("Library roots:"))
        self.txt_roots = QLineEdit()
        self.txt_roots.setPlaceholderText(r"G:\Organized;I:\Organized")
        self.txt_roots.setText(";".join(roots or [r"G:\Organized", r"I:\Organized"]))
        roots_row.addWidget(self.txt_roots, 1)
        btn_browse = QPushButton("Add Folder")
        btn_browse.clicked.connect(self._browse_root)
        roots_row.addWidget(btn_browse)
        lay.addLayout(roots_row)

        options = QHBoxLayout()
        options.addWidget(QLabel("Child depth:"))
        self.spn_depth = QSpinBox()
        self.spn_depth.setRange(1, 8)
        self.spn_depth.setValue(1)
        self.spn_depth.setToolTip("How many folder levels below each root to inspect")
        options.addWidget(self.spn_depth)
        options.addStretch()
        lay.addLayout(options)

        scan_row = QHBoxLayout()
        self.btn_scan = QPushButton("Scan Versions")
        self.btn_scan.setStyleSheet(
            f"QPushButton {{ background: {theme['green']}; color: white; "
            "font-weight: bold; padding: 6px 14px; border-radius: 4px; }}"
        )
        self.btn_scan.clicked.connect(self._start_scan)
        scan_row.addWidget(self.btn_scan)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setVisible(False)
        scan_row.addWidget(self.progress, 1)
        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("class", "meta")
        scan_row.addWidget(self.lbl_status)
        lay.addLayout(scan_row)

        archive_row = QHBoxLayout()
        archive_row.addWidget(QLabel("Archive root:"))
        self.txt_archive = QLineEdit()
        self.txt_archive.setPlaceholderText("Existing folder required before applying")
        archive_row.addWidget(self.txt_archive, 1)
        btn_archive = QPushButton("Browse")
        btn_archive.clicked.connect(self._browse_archive)
        archive_row.addWidget(btn_archive)
        lay.addLayout(archive_row)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Archive", "Folder", "Version", "Files", "Size", "Reason"])
        self.tree.setAlternatingRowColors(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        header = self.tree.header()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        lay.addWidget(self.tree, 1)

        bottom = QHBoxLayout()
        self.lbl_summary = QLabel("")
        self.lbl_summary.setProperty("class", "summary")
        bottom.addWidget(self.lbl_summary, 1)
        self.btn_apply = QPushButton("Archive Selected Older Versions")
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet(
            f"QPushButton {{ background: {theme['green']}; color: white; "
            "font-weight: bold; padding: 6px 14px; border-radius: 4px; }}"
        )
        self.btn_apply.clicked.connect(self._apply_selected)
        bottom.addWidget(self.btn_apply)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        bottom.addWidget(btn_close)
        lay.addLayout(bottom)

    def _roots(self):
        return [value.strip() for value in re.split(r"[;\r\n]+", self.txt_roots.text()) if value.strip()]

    def _browse_root(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Library Root")
        if folder and folder not in self._roots():
            self.txt_roots.setText(";".join(self._roots() + [folder]))

    def _browse_archive(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Version Archive Root")
        if folder:
            self.txt_archive.setText(folder)

    def _start_scan(self):
        roots = self._roots()
        if not roots:
            self.lbl_status.setText("Enter at least one library root.")
            return
        self.btn_scan.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.tree.clear()
        self._rows = []
        self.progress.setVisible(True)
        self.lbl_status.setText("Starting scan…")
        from fileorganizer.workers import VersionDedupScanWorker

        self._worker = VersionDedupScanWorker(roots, depth=self.spn_depth.value(), parent=self)
        self._worker.progress.connect(self.lbl_status.setText)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

    def _on_scan_done(self, result):
        self._worker = None
        self.btn_scan.setEnabled(True)
        self.progress.setVisible(False)
        if isinstance(result, dict) and "error" in result:
            self.lbl_status.setText(result["error"])
            return
        self._groups = dict(result or {})
        self._populate_results()

    def _populate_results(self):
        from fileorganizer.version_dedup import pick_best_version, version_archive_reason

        self.tree.clear()
        self._rows = []
        for marketplace_id, candidates in sorted(self._groups.items()):
            keeper, obsolete = pick_best_version(candidates)
            header = QTreeWidgetItem([
                f"ID {marketplace_id} — keep {keeper.name}",
                keeper.path,
                keeper.version_hint or "—",
                str(keeper.file_count),
                format_size(keeper.total_bytes),
                "Newest/fullest candidate",
            ])
            header.setForeground(0, QColor("#4fc3f7"))
            self.tree.addTopLevelItem(header)

            keeper_row = QTreeWidgetItem([
                "KEEP", keeper.name, keeper.version_hint or "—", str(keeper.file_count),
                format_size(keeper.total_bytes), "Selected by file count/version priority",
            ])
            keeper_row.setToolTip(1, keeper.path)
            keeper_row.setForeground(0, QColor(get_active_theme()["green"]))
            header.addChild(keeper_row)

            for candidate in obsolete:
                reason = version_archive_reason(keeper, candidate)
                row = QTreeWidgetItem([
                    "", candidate.name, candidate.version_hint or "—",
                    str(candidate.file_count), format_size(candidate.total_bytes), reason,
                ])
                row.setToolTip(1, candidate.path)
                checkbox = QCheckBox()
                checkbox.setChecked(True)
                checkbox.setToolTip("Archive this candidate after revalidation")
                header.addChild(row)
                self.tree.setItemWidget(row, 0, checkbox)
                self._rows.append((checkbox, keeper, candidate, reason))
            header.setExpanded(True)

        self.lbl_summary.setText(
            f"{len(self._groups)} version group(s) — {len(self._rows)} archive candidate(s)"
            if self._groups else "No differing same-ID versions found"
        )
        self.btn_apply.setEnabled(bool(self._rows))

    def _apply_selected(self):
        selected = [row for row in self._rows if row[0].isChecked() and row[0].isEnabled()]
        archive_root = self.txt_archive.text().strip()
        if not selected:
            self.lbl_status.setText("No archive candidates selected.")
            return
        if not os.path.isdir(archive_root):
            self.lbl_status.setText("Choose an existing archive root first.")
            return
        confirm = QMessageBox.question(
            self,
            "Confirm Version Archive",
            f"Archive {len(selected)} older version folder(s) into:\n{archive_root}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        from fileorganizer.version_dedup import archive_version_candidate

        completed = 0
        errors = []
        for checkbox, keeper, obsolete, reason in selected:
            try:
                archive_version_candidate(
                    keeper,
                    obsolete,
                    archive_root=archive_root,
                    reason=reason,
                )
                checkbox.setChecked(False)
                checkbox.setEnabled(False)
                completed += 1
            except Exception as exc:
                errors.append(f"{obsolete.name}: {exc}")
        self.lbl_status.setText(
            f"Archived {completed} version(s)" + (f"; {errors[0]}" if errors else "")
        )
        self.btn_apply.setEnabled(any(checkbox.isEnabled() for checkbox, *_ in self._rows))

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(1000)
        super().closeEvent(event)


__all__ = ["VersionDedupDialog"]
