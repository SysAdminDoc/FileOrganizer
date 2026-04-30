"""FileOrganizer dialogs — Marketplace tools (Library Auditor, Archive Normalizer, Catalog Manager)."""
import importlib.util
import json
import os
import sys
from pathlib import Path

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QCheckBox, QTableWidget, QTableWidgetItem, QHeaderView, QFileDialog,
    QAbstractItemView, QProgressBar, QTabWidget, QTextEdit, QSplitter,
    QComboBox, QFrame, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QColor

from fileorganizer.config import get_active_theme


def _load_script(name: str):
    """Dynamically import a standalone script from the repo root."""
    repo = Path(__file__).parent.parent.parent
    spec = importlib.util.spec_from_file_location(name, repo / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ═══ LIBRARY AUDITOR ══════════════════════════════════════════════════════════

class _AuditWorker(QThread):
    log     = pyqtSignal(str)
    move    = pyqtSignal(dict)
    rename  = pyqtSignal(dict)
    done    = pyqtSignal(int, int, int)  # moves, renames, no_proj

    def __init__(self, root: str, only_cat: str | None,
                 do_classify: bool, do_rename: bool):
        super().__init__()
        self.root = root
        self.only_cat = only_cat
        self.do_classify = do_classify
        self.do_rename = do_rename
        self._stop = False

    def stop(self): self._stop = True

    def run(self):
        try:
            ao = _load_script("audit_organized")
        except Exception as e:
            self.log.emit(f"[ERROR] cannot load audit_organized: {e}")
            self.done.emit(0, 0, 0)
            return

        root = Path(self.root)
        if not root.is_dir():
            self.log.emit(f"[ERROR] root not found: {root}")
            self.done.emit(0, 0, 0)
            return

        all_cats = sorted(d.name for d in root.iterdir()
                          if d.is_dir() and d.name not in ao.SKIP_DIR_NAMES)

        n_moves = n_renames = n_noproj = project_count = 0
        for proj, cat in ao.iter_projects(root, self.only_cat):
            if self._stop:
                break
            project_count += 1
            if project_count % 250 == 0:
                self.log.emit(f"  ... scanned {project_count} projects")

            target_cat = None
            if self.do_classify:
                detected, counts = ao.detect_project_type(proj)
                target_cat = ao.find_correct_category(
                    detected, cat, all_cats, proj.name, counts)
                if detected is None:
                    n_noproj += 1
                if target_cat:
                    rec = {
                        "project": str(proj),
                        "from_category": cat,
                        "to_category": target_cat,
                        "detected_type": detected or "?",
                        "ext_counts": dict(counts.most_common(5)),
                    }
                    self.move.emit(rec)
                    n_moves += 1

            proj_after = (root / target_cat / proj.name) if target_cat else proj

            if self.do_rename:
                try:
                    inner = [p for p in proj.iterdir()
                             if p.is_file() and p.suffix.lower() not in ao.ARCHIVE_EXTS]
                except (PermissionError, OSError):
                    continue
                cohort = ao.find_foreign_cohort(proj.name, inner)
                sibling_stems = [p.stem for p in inner]
                for f in cohort:
                    new_name = ao.derive_english_name(f, proj.name, sibling_stems)
                    if new_name == f.name:
                        continue
                    self.rename.emit({
                        "from": str(f),
                        "to_name": new_name,
                        "project": str(proj),
                        "project_after_move": str(proj_after),
                    })
                    n_renames += 1

        self.log.emit(f"Done — {project_count} projects, {n_moves} misclassified, "
                      f"{n_renames} foreign filenames, {n_noproj} missing project file")
        self.done.emit(n_moves, n_renames, n_noproj)


class _ApplyAuditWorker(QThread):
    log  = pyqtSignal(str)
    done = pyqtSignal(int, int)

    def __init__(self, root: str, moves: list, renames: list):
        super().__init__()
        self.root = root
        self.moves = moves
        self.renames = renames

    def run(self):
        import os, shutil
        root = Path(self.root)
        try:
            ao = _load_script("audit_organized")
        except Exception as e:
            self.log.emit(f"[ERROR] {e}")
            self.done.emit(0, 0)
            return

        n_moved = n_renamed = 0
        for m in self.moves:
            src = Path(m["project"])
            dst_dir = root / m["to_category"]
            dst_dir.mkdir(parents=True, exist_ok=True)
            dst = ao.safe_target(dst_dir / src.name)
            try:
                os.rename(str(src), str(dst))
                m["_dst"] = str(dst)
                n_moved += 1
            except OSError:
                try:
                    shutil.move(str(src), str(dst))
                    m["_dst"] = str(dst)
                    n_moved += 1
                except Exception as e:
                    self.log.emit(f"  ERR move {src.name}: {e}")

        for r in self.renames:
            old_proj = Path(r["project"])
            proj_now = Path(r["project_after_move"])
            if not proj_now.exists():
                proj_now = old_proj
            if not proj_now.exists():
                continue
            old_path = proj_now / Path(r["from"]).name
            if not old_path.exists():
                old_path = Path(r["from"])
                if not old_path.exists():
                    continue
            new_path = ao.safe_target(old_path.parent / r["to_name"])
            try:
                os.rename(str(old_path), str(new_path))
                n_renamed += 1
            except OSError as e:
                self.log.emit(f"  ERR rename {old_path.name}: {e}")

        self.log.emit(f"Applied: {n_moved} moved, {n_renamed} renamed")
        self.done.emit(n_moved, n_renamed)


class LibraryAuditorPanel(QWidget):
    """Inline library auditor panel — misclassification detection + foreign filename repair."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._moves: list[dict] = []
        self._renames: list[dict] = []
        self._worker = None
        self._apply_worker = None
        self._build_ui()

    def _build_ui(self):
        _t = get_active_theme()
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 12, 16, 12)
        root_lay.setSpacing(10)

        # Header
        hdr = QLabel("Library Auditor")
        hdr.setProperty("class", "heading")
        root_lay.addWidget(hdr)
        sub = QLabel("Detect misclassified projects and repair foreign/CJK filenames in your organized library.")
        sub.setProperty("class", "meta")
        sub.setWordWrap(True)
        root_lay.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setProperty("class", "separator")
        sep.setFixedHeight(1)
        root_lay.addWidget(sep)

        # Root path row
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Organized root:"))
        self.txt_root = QLineEdit("I:/Organized")
        row1.addWidget(self.txt_root, 1)
        btn_browse = QPushButton("Browse")
        btn_browse.setFixedWidth(75)
        btn_browse.clicked.connect(self._browse_root)
        row1.addWidget(btn_browse)
        root_lay.addLayout(row1)

        # Category filter
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Category filter:"))
        self.cmb_cat = QComboBox()
        self.cmb_cat.addItem("All Categories")
        self.cmb_cat.setEditable(False)
        self.cmb_cat.setMinimumWidth(260)
        btn_load_cats = QPushButton("Load")
        btn_load_cats.setFixedWidth(55)
        btn_load_cats.setToolTip("Load categories from root folder")
        btn_load_cats.clicked.connect(self._load_categories)
        row2.addWidget(self.cmb_cat, 1)
        row2.addWidget(btn_load_cats)
        row2.addStretch()
        root_lay.addLayout(row2)

        # Options
        row3 = QHBoxLayout()
        self.chk_classify = QCheckBox("Fix misclassifications")
        self.chk_classify.setChecked(True)
        self.chk_rename = QCheckBox("Fix foreign filenames")
        self.chk_rename.setChecked(True)
        row3.addWidget(self.chk_classify)
        row3.addWidget(self.chk_rename)
        row3.addStretch()
        root_lay.addLayout(row3)

        # Action buttons
        row4 = QHBoxLayout()
        self.btn_scan = QPushButton("Scan")
        self.btn_scan.setProperty("class", "primary")
        self.btn_scan.setFixedHeight(32)
        self.btn_scan.clicked.connect(self._scan)
        self.btn_apply = QPushButton("Apply Selected")
        self.btn_apply.setProperty("class", "apply")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.lbl_stats = QLabel("")
        self.lbl_stats.setProperty("class", "meta")
        row4.addWidget(self.btn_scan)
        row4.addWidget(self.btn_apply)
        row4.addWidget(self.btn_stop)
        row4.addStretch()
        row4.addWidget(self.lbl_stats)
        root_lay.addLayout(row4)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        root_lay.addWidget(self.progress)

        # Results tabs + log splitter
        splitter = QSplitter(Qt.Orientation.Vertical)

        tabs_w = QWidget()
        tabs_lay = QVBoxLayout(tabs_w)
        tabs_lay.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()

        # Misclassifications tab
        self.tbl_moves = QTableWidget(0, 5)
        self.tbl_moves.setHorizontalHeaderLabels(
            ["", "Project", "From Category", "To Category", "Type"])
        self.tbl_moves.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.tbl_moves.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_moves.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_moves.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_moves.setColumnWidth(0, 28)
        self.tbl_moves.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_moves.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_moves.setAlternatingRowColors(True)
        self.tabs.addTab(self.tbl_moves, "Misclassifications (0)")

        # Foreign filenames tab
        self.tbl_renames = QTableWidget(0, 4)
        self.tbl_renames.setHorizontalHeaderLabels(
            ["", "Old Filename", "New Filename", "Project"])
        self.tbl_renames.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_renames.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_renames.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch)
        self.tbl_renames.setColumnWidth(0, 28)
        self.tbl_renames.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl_renames.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_renames.setAlternatingRowColors(True)
        self.tabs.addTab(self.tbl_renames, "Foreign Filenames (0)")

        tabs_lay.addWidget(self.tabs)
        splitter.addWidget(tabs_w)

        # Log
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(140)
        self.log_box.setProperty("class", "log")
        splitter.addWidget(self.log_box)
        splitter.setSizes([500, 140])

        root_lay.addWidget(splitter, 1)

    def _log(self, msg: str):
        self.log_box.append(msg)
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())

    def _browse_root(self):
        d = QFileDialog.getExistingDirectory(self, "Select organized root", self.txt_root.text())
        if d:
            self.txt_root.setText(d)

    def _load_categories(self):
        root = Path(self.txt_root.text())
        if not root.is_dir():
            return
        self.cmb_cat.clear()
        self.cmb_cat.addItem("All Categories")
        for d in sorted(root.iterdir()):
            if d.is_dir():
                self.cmb_cat.addItem(d.name)

    def _scan(self):
        if self._worker and self._worker.isRunning():
            return
        self._moves.clear()
        self._renames.clear()
        self.tbl_moves.setRowCount(0)
        self.tbl_renames.setRowCount(0)
        self.tabs.setTabText(0, "Misclassifications (0)")
        self.tabs.setTabText(1, "Foreign Filenames (0)")
        self.log_box.clear()
        self.btn_apply.setEnabled(False)
        self.lbl_stats.setText("")

        cat = self.cmb_cat.currentText()
        only_cat = None if cat == "All Categories" else cat

        self._worker = _AuditWorker(
            self.txt_root.text(), only_cat,
            self.chk_classify.isChecked(), self.chk_rename.isChecked())
        self._worker.log.connect(self._log)
        self._worker.move.connect(self._on_move)
        self._worker.rename.connect(self._on_rename)
        self._worker.done.connect(self._on_scan_done)
        self.progress.show()
        self.btn_scan.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._worker.start()

    def _stop(self):
        if self._worker:
            self._worker.stop()

    def _on_move(self, rec: dict):
        self._moves.append(rec)
        row = self.tbl_moves.rowCount()
        self.tbl_moves.insertRow(row)
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        chk.setCheckState(Qt.CheckState.Checked)
        self.tbl_moves.setItem(row, 0, chk)
        self.tbl_moves.setItem(row, 1, QTableWidgetItem(Path(rec["project"]).name))
        self.tbl_moves.setItem(row, 2, QTableWidgetItem(rec["from_category"]))
        item_to = QTableWidgetItem(rec["to_category"])
        item_to.setForeground(QColor(get_active_theme()['green']))
        self.tbl_moves.setItem(row, 3, item_to)
        self.tbl_moves.setItem(row, 4, QTableWidgetItem(rec["detected_type"]))
        self.tabs.setTabText(0, f"Misclassifications ({len(self._moves)})")

    def _on_rename(self, rec: dict):
        self._renames.append(rec)
        row = self.tbl_renames.rowCount()
        self.tbl_renames.insertRow(row)
        chk = QTableWidgetItem()
        chk.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
        chk.setCheckState(Qt.CheckState.Checked)
        self.tbl_renames.setItem(row, 0, chk)
        self.tbl_renames.setItem(row, 1, QTableWidgetItem(Path(rec["from"]).name))
        item_new = QTableWidgetItem(rec["to_name"])
        item_new.setForeground(QColor(get_active_theme()['green']))
        self.tbl_renames.setItem(row, 2, item_new)
        self.tbl_renames.setItem(row, 3, QTableWidgetItem(Path(rec["project"]).name))
        self.tabs.setTabText(1, f"Foreign Filenames ({len(self._renames)})")

    def _on_scan_done(self, n_moves: int, n_renames: int, n_noproj: int):
        self.progress.hide()
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_apply.setEnabled(n_moves + n_renames > 0)
        self.lbl_stats.setText(
            f"{n_moves} misclassified  •  {n_renames} foreign filenames  •  {n_noproj} missing project file")
        self._log(f"Scan complete — {n_moves} moves, {n_renames} renames pending")

    def _apply(self):
        # Collect only checked rows
        checked_moves = []
        for i, rec in enumerate(self._moves):
            if i < self.tbl_moves.rowCount():
                item = self.tbl_moves.item(i, 0)
                if item and item.checkState() == Qt.CheckState.Checked:
                    checked_moves.append(rec)

        checked_renames = []
        for i, rec in enumerate(self._renames):
            if i < self.tbl_renames.rowCount():
                item = self.tbl_renames.item(i, 0)
                if item and item.checkState() == Qt.CheckState.Checked:
                    checked_renames.append(rec)

        if not checked_moves and not checked_renames:
            QMessageBox.information(self, "Nothing selected", "No items checked to apply.")
            return

        n = len(checked_moves) + len(checked_renames)
        if QMessageBox.question(
                self, "Confirm", f"Apply {n} changes?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return

        self._apply_worker = _ApplyAuditWorker(
            self.txt_root.text(), checked_moves, checked_renames)
        self._apply_worker.log.connect(self._log)
        self._apply_worker.done.connect(self._on_apply_done)
        self.btn_apply.setEnabled(False)
        self.btn_scan.setEnabled(False)
        self.progress.show()
        self._apply_worker.start()

    def _on_apply_done(self, n_moved: int, n_renamed: int):
        self.progress.hide()
        self.btn_scan.setEnabled(True)
        self._log(f"Applied — {n_moved} projects moved, {n_renamed} files renamed")
        self.lbl_stats.setText(f"Applied: {n_moved} moved, {n_renamed} renamed")


# ═══ ARCHIVE NORMALIZER ═══════════════════════════════════════════════════════

class _NormWorker(QThread):
    log    = pyqtSignal(str)
    result = pyqtSignal(dict)   # one plan result per archive
    done   = pyqtSignal(int, int, int)  # total, to_rename, skipped

    def __init__(self, root: str, allow_online: bool, apply: bool):
        super().__init__()
        self.root = root
        self.allow_online = allow_online
        self.apply = apply
        self._stop = False

    def stop(self): self._stop = True

    def run(self):
        try:
            nan = _load_script("normalize_archive_names")
        except Exception as e:
            self.log.emit(f"[ERROR] cannot load normalize_archive_names: {e}")
            self.done.emit(0, 0, 0)
            return

        root = Path(self.root)
        if not root.exists():
            self.log.emit(f"[ERROR] root not found: {root}")
            self.done.emit(0, 0, 0)
            return

        cache = nan.load_cache()
        archives = sorted(
            f for f in root.iterdir()
            if f.is_file() and f.suffix.lower() in (".zip", ".rar", ".7z"))
        self.log.emit(f"Found {len(archives)} archives in {root}")

        total = to_rename = skipped = 0
        for archive in archives:
            if self._stop:
                break
            parts = nan.archive_group(archive)
            if not parts:
                continue
            total += 1

            new_path, source = nan.plan_rename(archive, cache,
                                               allow_online=self.allow_online)
            if new_path is None:
                skipped += 1
                continue

            target = nan.safe_target(new_path)
            rec = {
                "archive": str(archive),
                "current_name": archive.name,
                "new_name": target.name,
                "source": source,
                "parts": [str(p) for p in parts],
                "target_parts": [],
            }

            if len(parts) > 1:
                base = target.name[: -len(nan.part_suffix(target))] if nan.part_suffix(target) else target.stem
                for p in parts:
                    ps = nan.part_suffix(p)
                    t = p.parent / f"{base}{ps}"
                    if t.exists() and t != p:
                        t = nan.safe_target(t)
                    rec["target_parts"].append(str(t))

            to_rename += 1
            self.result.emit(rec)

            if self.apply:
                import os as _os
                try:
                    rename_pairs = list(zip(parts, [Path(tp) for tp in rec["target_parts"]])) \
                        if rec["target_parts"] else [(archive, target)]
                    for src, dst in rename_pairs:
                        _os.rename(str(src), str(dst))
                    self.log.emit(f"  Renamed: {archive.name} -> {target.name}")
                except OSError as e:
                    self.log.emit(f"  ERR: {archive.name}: {e}")

        if not self.apply:
            nan.save_cache(cache)

        self.log.emit(f"Done — {total} archives, {to_rename} to rename, {skipped} skipped")
        self.done.emit(total, to_rename, skipped)


class ArchiveNormalizerPanel(QWidget):
    """Inline archive normalizer panel — renames archives to canonical marketplace titles."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results: list[dict] = []
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        _t = get_active_theme()
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 12, 16, 12)
        root_lay.setSpacing(10)

        hdr = QLabel("Archive Normalizer")
        hdr.setProperty("class", "heading")
        root_lay.addWidget(hdr)
        sub = QLabel(
            "Rename design asset archives (VH-NNNNNNN.zip, etc.) to canonical marketplace titles "
            "using local cache + optional online lookup.")
        sub.setProperty("class", "meta")
        sub.setWordWrap(True)
        root_lay.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setProperty("class", "separator")
        sep.setFixedHeight(1)
        root_lay.addWidget(sep)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Archive root:"))
        self.txt_root = QLineEdit("I:/After Effects")
        row1.addWidget(self.txt_root, 1)
        btn_browse = QPushButton("Browse")
        btn_browse.setFixedWidth(75)
        btn_browse.clicked.connect(self._browse_root)
        row1.addWidget(btn_browse)
        root_lay.addLayout(row1)

        row2 = QHBoxLayout()
        self.chk_online = QCheckBox("Online lookup (Videohive redirect)")
        self.chk_online.setChecked(True)
        row2.addWidget(self.chk_online)
        row2.addStretch()
        root_lay.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_scan = QPushButton("Scan (Preview)")
        self.btn_scan.setProperty("class", "primary")
        self.btn_scan.setFixedHeight(32)
        self.btn_scan.clicked.connect(self._scan)
        self.btn_apply = QPushButton("Apply All")
        self.btn_apply.setProperty("class", "apply")
        self.btn_apply.setFixedHeight(32)
        self.btn_apply.setEnabled(False)
        self.btn_apply.clicked.connect(self._apply)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.lbl_stats = QLabel("")
        self.lbl_stats.setProperty("class", "meta")
        row3.addWidget(self.btn_scan)
        row3.addWidget(self.btn_apply)
        row3.addWidget(self.btn_stop)
        row3.addStretch()
        row3.addWidget(self.lbl_stats)
        root_lay.addLayout(row3)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        root_lay.addWidget(self.progress)

        splitter = QSplitter(Qt.Orientation.Vertical)

        self.tbl = QTableWidget(0, 3)
        self.tbl.setHorizontalHeaderLabels(["Current Filename", "Proposed Filename", "Source"])
        self.tbl.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Stretch)
        self.tbl.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl.setAlternatingRowColors(True)
        splitter.addWidget(self.tbl)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMaximumHeight(140)
        self.log_box.setProperty("class", "log")
        splitter.addWidget(self.log_box)
        splitter.setSizes([500, 140])

        root_lay.addWidget(splitter, 1)

    def _log(self, msg: str):
        self.log_box.append(msg)
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())

    def _browse_root(self):
        d = QFileDialog.getExistingDirectory(self, "Select archive root", self.txt_root.text())
        if d:
            self.txt_root.setText(d)

    def _run(self, apply: bool):
        if self._worker and self._worker.isRunning():
            return
        self._results.clear()
        self.tbl.setRowCount(0)
        self.log_box.clear()
        self.btn_apply.setEnabled(False)
        self.lbl_stats.setText("")

        self._worker = _NormWorker(self.txt_root.text(),
                                   self.chk_online.isChecked(), apply)
        self._worker.log.connect(self._log)
        self._worker.result.connect(self._on_result)
        self._worker.done.connect(self._on_done)
        self.progress.show()
        self.btn_scan.setEnabled(False)
        self.btn_apply.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self._worker.start()

    def _scan(self):
        self._run(apply=False)

    def _apply(self):
        if QMessageBox.question(
                self, "Confirm",
                f"Rename {self.tbl.rowCount()} archives? This cannot be undone.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        ) != QMessageBox.StandardButton.Yes:
            return
        self._run(apply=True)

    def _stop(self):
        if self._worker:
            self._worker.stop()

    def _on_result(self, rec: dict):
        self._results.append(rec)
        row = self.tbl.rowCount()
        self.tbl.insertRow(row)
        self.tbl.setItem(row, 0, QTableWidgetItem(rec["current_name"]))
        item_new = QTableWidgetItem(rec["new_name"])
        item_new.setForeground(QColor(get_active_theme()['green']))
        self.tbl.setItem(row, 1, item_new)
        src_label = rec["source"].split(":")[0]
        item_src = QTableWidgetItem(src_label)
        if src_label == "online":
            item_src.setForeground(QColor("#f472b6"))
        self.tbl.setItem(row, 2, item_src)

    def _on_done(self, total: int, to_rename: int, skipped: int):
        self.progress.hide()
        self.btn_scan.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.btn_apply.setEnabled(to_rename > 0)
        self.lbl_stats.setText(
            f"{total} archives  •  {to_rename} to rename  •  {skipped} skipped")


# ═══ CATALOG MANAGER ══════════════════════════════════════════════════════════

class _CatalogWorker(QThread):
    log  = pyqtSignal(str)
    done = pyqtSignal(int)  # new entries added

    def __init__(self, modes: list[str], parallel: bool, max_pages: int,
                 throttle: float, max_authors: int, author_pages: int):
        super().__init__()
        self.modes = modes
        self.parallel = parallel
        self.max_pages = max_pages
        self.throttle = throttle
        self.max_authors = max_authors
        self.author_pages = author_pages
        self._stop = False

    def stop(self): self._stop = True

    def run(self):
        try:
            bce = _load_script("bulk_catalog_envato")
        except Exception as e:
            self.log.emit(f"[ERROR] cannot load bulk_catalog_envato: {e}")
            self.done.emit(0)
            return

        orig_print = getattr(bce, '_safe_print', None)
        # Redirect print to Qt signal
        bce._gui_log = self.log.emit

        self.log.emit(f"Starting catalog run: modes={self.modes}, "
                      f"max_pages={self.max_pages}, throttle={self.throttle}")

        before = len(bce.load_cache())
        try:
            args_ns = type('Args', (), {
                'parallel': self.parallel,
                'max_pages': self.max_pages,
                'start_page': 0,
                'throttle': self.throttle,
                'subcategories': 'subcategories' in self.modes,
                'authors': 'authors' in self.modes,
                'sitemaps': 'sitemaps' in self.modes,
                'max_authors': self.max_authors,
                'author_pages': self.author_pages,
                'apply': True,
            })()
            bce.run_expansion(args_ns, log_cb=self.log.emit)
        except AttributeError:
            # Fallback: run the CLI entrypoint with sys.argv override
            import sys as _sys
            old_argv = _sys.argv[:]
            flags = ['bulk_catalog_envato.py', '--apply']
            if self.parallel: flags.append('--parallel')
            flags += ['--max-pages', str(self.max_pages),
                      '--throttle', str(self.throttle)]
            if 'subcategories' in self.modes: flags.append('--subcategories')
            if 'authors' in self.modes:
                flags += ['--authors', '--max-authors', str(self.max_authors),
                          '--author-pages', str(self.author_pages)]
            if 'sitemaps' in self.modes: flags.append('--sitemaps')
            _sys.argv = flags
            try:
                bce.main()
            except SystemExit:
                pass
            finally:
                _sys.argv = old_argv

        after = len(bce.load_cache())
        added = after - before
        self.log.emit(f"Done — {added:+,} new entries (cache now {after:,})")
        self.done.emit(added)


class CatalogManagerPanel(QWidget):
    """Inline catalog manager panel — build/refresh the Envato marketplace title cache."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._build_ui()
        self._refresh_stats()

    def _build_ui(self):
        _t = get_active_theme()
        root_lay = QVBoxLayout(self)
        root_lay.setContentsMargins(16, 12, 16, 12)
        root_lay.setSpacing(10)

        hdr = QLabel("Catalog Manager")
        hdr.setProperty("class", "heading")
        root_lay.addWidget(hdr)
        sub = QLabel(
            "Build and refresh the Envato marketplace title cache used by the Archive Normalizer. "
            "The lightweight cache (96K) ships with the app; the full catalog (10.6M) is optional.")
        sub.setProperty("class", "meta")
        sub.setWordWrap(True)
        root_lay.addWidget(sub)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.NoFrame)
        sep.setProperty("class", "separator")
        sep.setFixedHeight(1)
        root_lay.addWidget(sep)

        # Stats table
        stats_hdr = QLabel("Cache Statistics")
        stats_hdr.setProperty("class", "subheading-sm")
        root_lay.addWidget(stats_hdr)

        self.tbl_stats = QTableWidget(0, 3)
        self.tbl_stats.setHorizontalHeaderLabels(["Marketplace", "Entries", "Source"])
        self.tbl_stats.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_stats.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.ResizeToContents)
        self.tbl_stats.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch)
        self.tbl_stats.setFixedHeight(220)
        self.tbl_stats.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tbl_stats.setAlternatingRowColors(True)
        root_lay.addWidget(self.tbl_stats)

        btn_refresh_stats = QPushButton("Refresh Stats")
        btn_refresh_stats.setFixedWidth(110)
        btn_refresh_stats.clicked.connect(self._refresh_stats)
        root_lay.addWidget(btn_refresh_stats)

        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.NoFrame)
        sep2.setProperty("class", "separator")
        sep2.setFixedHeight(1)
        root_lay.addWidget(sep2)

        # Run options
        opts_hdr = QLabel("Expand Catalog")
        opts_hdr.setProperty("class", "subheading-sm")
        root_lay.addWidget(opts_hdr)

        row1 = QHBoxLayout()
        self.chk_search = QCheckBox("Global search (/search)")
        self.chk_search.setChecked(True)
        self.chk_subcats = QCheckBox("Subcategories")
        self.chk_subcats.setChecked(True)
        self.chk_authors = QCheckBox("Author portfolios")
        self.chk_sitemaps = QCheckBox("Sitemaps (complete catalog, slow)")
        row1.addWidget(self.chk_search)
        row1.addWidget(self.chk_subcats)
        row1.addWidget(self.chk_authors)
        row1.addWidget(self.chk_sitemaps)
        root_lay.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Max pages:"))
        self.cmb_pages = QComboBox()
        self.cmb_pages.addItems(["12", "30", "60", "200"])
        self.cmb_pages.setCurrentIndex(2)
        self.cmb_pages.setFixedWidth(70)
        row2.addWidget(self.cmb_pages)
        row2.addWidget(QLabel("  Throttle (s):"))
        self.cmb_throttle = QComboBox()
        self.cmb_throttle.addItems(["0.4", "0.6", "0.8", "1.2"])
        self.cmb_throttle.setCurrentIndex(2)
        self.cmb_throttle.setFixedWidth(70)
        row2.addWidget(self.cmb_throttle)
        row2.addWidget(QLabel("  Max authors:"))
        self.cmb_authors = QComboBox()
        self.cmb_authors.addItems(["20", "50", "80", "150"])
        self.cmb_authors.setCurrentIndex(2)
        self.cmb_authors.setFixedWidth(70)
        row2.addWidget(self.cmb_authors)
        self.chk_parallel = QCheckBox("Parallel (7 sites simultaneously)")
        self.chk_parallel.setChecked(True)
        row2.addWidget(self.chk_parallel)
        row2.addStretch()
        root_lay.addLayout(row2)

        row3 = QHBoxLayout()
        self.btn_run = QPushButton("Run Expansion")
        self.btn_run.setProperty("class", "primary")
        self.btn_run.setFixedHeight(32)
        self.btn_run.clicked.connect(self._run)
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setFixedHeight(32)
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self._stop)
        self.lbl_status = QLabel("")
        self.lbl_status.setProperty("class", "meta")
        row3.addWidget(self.btn_run)
        row3.addWidget(self.btn_stop)
        row3.addStretch()
        row3.addWidget(self.lbl_status)
        root_lay.addLayout(row3)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        root_lay.addWidget(self.progress)

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setProperty("class", "log")
        root_lay.addWidget(self.log_box, 1)

    def _log(self, msg: str):
        self.log_box.append(msg)
        self.log_box.verticalScrollBar().setValue(
            self.log_box.verticalScrollBar().maximum())

    def _refresh_stats(self):
        repo = Path(__file__).parent.parent.parent
        cache_file = repo / "marketplace_title_cache.json"
        self.tbl_stats.setRowCount(0)

        total = 0
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                counts: dict[str, int] = {}
                for key in data:
                    mkt = key.split(":")[0]
                    counts[mkt] = counts.get(mkt, 0) + 1
                for mkt, n in sorted(counts.items(), key=lambda x: -x[1]):
                    row = self.tbl_stats.rowCount()
                    self.tbl_stats.insertRow(row)
                    self.tbl_stats.setItem(row, 0, QTableWidgetItem(mkt))
                    item_n = QTableWidgetItem(f"{n:,}")
                    item_n.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.tbl_stats.setItem(row, 1, item_n)
                    self.tbl_stats.setItem(row, 2, QTableWidgetItem("marketplace_title_cache.json"))
                    total += n
            except Exception as e:
                row = self.tbl_stats.rowCount()
                self.tbl_stats.insertRow(row)
                self.tbl_stats.setItem(row, 0, QTableWidgetItem(f"(error: {e})"))

        catalog_dir = repo / "catalog"
        if catalog_dir.is_dir():
            import gzip
            for gz_file in sorted(catalog_dir.glob("*.json.gz")):
                try:
                    n = sum(1 for _ in json.loads(
                        gzip.decompress(gz_file.read_bytes()).decode("utf-8")))
                    row = self.tbl_stats.rowCount()
                    self.tbl_stats.insertRow(row)
                    self.tbl_stats.setItem(row, 0, QTableWidgetItem(gz_file.stem.rsplit("_", 1)[0]))
                    item_n = QTableWidgetItem(f"{n:,}")
                    item_n.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                    self.tbl_stats.setItem(row, 1, item_n)
                    self.tbl_stats.setItem(row, 2, QTableWidgetItem(f"catalog/{gz_file.name}"))
                    total += n
                except Exception:
                    pass

        if total:
            row = self.tbl_stats.rowCount()
            self.tbl_stats.insertRow(row)
            item_tot = QTableWidgetItem("TOTAL")
            item_tot.setForeground(QColor(get_active_theme()['green']))
            self.tbl_stats.setItem(row, 0, item_tot)
            item_n = QTableWidgetItem(f"{total:,}")
            item_n.setForeground(QColor(get_active_theme()['green']))
            item_n.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            self.tbl_stats.setItem(row, 1, item_n)

    def _run(self):
        if self._worker and self._worker.isRunning():
            return
        self.log_box.clear()

        modes = []
        if self.chk_search.isChecked(): modes.append("search")
        if self.chk_subcats.isChecked(): modes.append("subcategories")
        if self.chk_authors.isChecked(): modes.append("authors")
        if self.chk_sitemaps.isChecked(): modes.append("sitemaps")
        if not modes:
            QMessageBox.information(self, "Nothing selected", "Select at least one mode.")
            return

        self._worker = _CatalogWorker(
            modes=modes,
            parallel=self.chk_parallel.isChecked(),
            max_pages=int(self.cmb_pages.currentText()),
            throttle=float(self.cmb_throttle.currentText()),
            max_authors=int(self.cmb_authors.currentText()),
            author_pages=40,
        )
        self._worker.log.connect(self._log)
        self._worker.done.connect(self._on_done)
        self.btn_run.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.progress.show()
        self.lbl_status.setText("Running...")
        self._worker.start()

    def _stop(self):
        if self._worker:
            self._worker.stop()

    def _on_done(self, added: int):
        self.progress.hide()
        self.btn_run.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.lbl_status.setText(f"+{added:,} new entries")
        self._refresh_stats()
