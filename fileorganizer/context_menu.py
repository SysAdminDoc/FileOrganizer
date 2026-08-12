"""Windows Explorer launch helpers and the offscreen context-menu runner."""

from __future__ import annotations

import os
import sys
from collections.abc import Callable
from typing import Any


def build_shell_command(
    executable: str,
    entrypoint: str | None = None,
    *,
    frozen: bool = False,
    source_token: str = "%V",
    headless: bool = False,
    auto_apply: bool = False,
) -> str:
    """Build a Windows Explorer command for a selected directory.

    ``%V`` is intentionally quoted as a registry placeholder.  Explorer
    expands it after reading the command, so it must remain a literal token in
    the value written to the registry.
    """
    if not executable:
        raise ValueError("an executable path is required")
    if not frozen and not entrypoint:
        raise ValueError("a Python entrypoint is required for an unfrozen launch")

    command = [f'"{executable}"']
    if not frozen:
        command.append(f'"{entrypoint}"')
    command.extend(("--source", f'"{source_token}"'))
    if headless:
        command.append("--headless")
    if auto_apply:
        command.append("--auto-apply")
    return " ".join(command)


def _set_source(window: Any, source: str) -> None:
    """Put a context-menu source into the PC panel's custom-path field."""
    window.cmb_op.setCurrentIndex(window.OP_FILES)
    combo = window.cmb_pc_src
    combo.blockSignals(True)
    try:
        custom_index = next(
            (
                index
                for index, (label, _path) in enumerate(window._pc_src_presets)
                if label == "Custom…"
            ),
            -1,
        )
        if custom_index >= 0:
            combo.setCurrentIndex(custom_index)
    finally:
        combo.blockSignals(False)
    window.txt_pc_src.setReadOnly(False)
    window.txt_pc_src.setText(source)


def _wait_for_thread(thread: Any, callback: Callable[[], None], timer: Any) -> None:
    """Run a callback once a QThread has fully stopped emitting signals."""
    if thread.isRunning():
        timer.singleShot(25, lambda: _wait_for_thread(thread, callback, timer))
        return
    timer.singleShot(0, callback)


def run_headless(source: str | None, *, auto_apply: bool = False, dry_run: bool = False) -> int:
    """Scan a folder without showing the GUI and optionally apply its plan.

    This deliberately creates the normal ``FileOrganizer`` window offscreen
    instead of duplicating destination mapping, rename templates, conflict
    handling, or apply safety checks in a second implementation.
    """
    if not source or not os.path.isdir(source):
        print("Headless context scan requires an accessible source folder.", file=sys.stderr)
        return 2

    # Must be set before QApplication is constructed so Explorer launches do
    # not require a physical display or flash a hidden window on screen.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtCore import QThread, QThreadPool, QTimer
    from PyQt6.QtWidgets import QApplication

    from fileorganizer.main_window import FileOrganizer

    source = os.path.abspath(os.path.normpath(source))
    app = QApplication.instance() or QApplication(["FileOrganizer", "--headless"])
    app.setQuitOnLastWindowClosed(False)
    window = FileOrganizer(background_automation=True)
    window._cli_dry_run = dry_run
    _set_source(window, source)
    window.hide()

    exit_code = 1
    finished = False

    def output(message: str) -> None:
        """Write worker logs even when a Windows console uses cp1252."""
        stream = sys.stdout
        encoding = getattr(stream, "encoding", None) or "utf-8"
        safe_message = str(message).encode(encoding, errors="replace").decode(encoding)
        print(safe_message, file=stream, flush=True)

    def log(message: str) -> None:
        output(message)

    def finish(code: int, message: str) -> None:
        nonlocal exit_code, finished
        if finished:
            return
        finished = True
        exit_code = code
        output(message)
        QTimer.singleShot(0, lambda: app.exit(code))

    def after_apply(*result: object) -> None:
        errors = int(result[1]) if len(result) > 1 else 0
        apply_worker = getattr(window, "apply_worker", None)
        if apply_worker is None:
            finish(1, "Context apply did not start.")
            return
        _wait_for_thread(
            apply_worker,
            lambda: finish(
                1 if errors else 0,
                f"Context apply finished: {errors} error(s).",
            ),
            QTimer,
        )

    def begin_apply() -> None:
        try:
            before = getattr(window, "apply_worker", None)
            window._apply_files(dry_run=dry_run)
            apply_worker = getattr(window, "apply_worker", None)
            if apply_worker is None or apply_worker is before:
                blocked = bool(getattr(window, "_background_apply_blocked", False))
                finish(
                    1 if blocked else 0,
                    "Context apply was blocked by preflight."
                    if blocked
                    else "Context scan found no selected work to apply.",
                )
                return
            apply_worker.log.connect(log)
            apply_worker.finished.connect(after_apply)
        except Exception as exc:  # pragma: no cover - defensive CLI boundary
            finish(1, f"Context apply failed: {exc}")

    def finalize_scan() -> None:
        count = len(window.file_items)
        output(f"Context scan finished: {count} item(s).")
        if not auto_apply:
            finish(0, "Preview-only context scan completed; no filesystem changes were made.")
            return
        QTimer.singleShot(0, begin_apply)

    result_generation = [0]

    def mark_result(_result: dict) -> None:
        result_generation[0] += 1

    def wait_for_results(generation: int) -> None:
        """Allow queued result_ready slots to drain after QThread finished."""
        if generation != result_generation[0]:
            QTimer.singleShot(100, lambda: wait_for_results(result_generation[0]))
            return
        QTimer.singleShot(0, finalize_scan)

    def after_scan() -> None:
        scan_worker = getattr(window, "worker", None)
        if scan_worker is None:
            finish(1, "Context scan did not start.")
            return
        _wait_for_thread(
            scan_worker,
            lambda: QTimer.singleShot(
                100, lambda: wait_for_results(result_generation[0])
            ),
            QTimer,
        )

    def configure_worker(scan_worker: Any) -> None:
        """Attach CLI observers before the worker thread can emit results."""
        scan_worker.log.connect(log)
        scan_worker.result_ready.connect(mark_result)
        scan_worker.finished.connect(after_scan)

    window._before_scan_worker_start = configure_worker

    try:
        window._on_scan()
        scan_worker = getattr(window, "worker", None)
        if scan_worker is None:
            finish(1, "Context scan did not start.")
        else:
            app.exec()
    except Exception as exc:  # pragma: no cover - defensive CLI boundary
        finish(1, f"Context scan failed: {exc}")
        if not finished:
            app.exec()

    tracked_threads = {
        value for value in vars(window).values() if isinstance(value, QThread)
    }
    tracked_threads.update(window.findChildren(QThread))
    for thread in tracked_threads:
        if thread.isRunning():
            cancel = getattr(thread, "cancel", None)
            if callable(cancel):
                cancel()
            thread.requestInterruption()
            thread.quit()
            thread.wait(5_000)
        try:
            thread.deleteLater()
        except RuntimeError:
            pass
    QThreadPool.globalInstance().waitForDone(5_000)
    window.close()
    window.deleteLater()
    app.processEvents()
    return exit_code
