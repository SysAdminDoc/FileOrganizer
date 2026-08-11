"""Run a saved GUI scan profile without creating a visible window."""

from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from fileorganizer.path_safety import validate_tree_pair


class ProfileRunError(RuntimeError):
    """Raised when a saved profile cannot safely run unattended."""


def validate_profile_config(config: Any) -> dict[str, Any]:
    """Validate the subset of saved GUI state required by an unattended scan."""
    if not isinstance(config, dict):
        raise ProfileRunError("saved profile must contain a JSON object")
    mode = config.get("mode")
    if isinstance(mode, bool) or not isinstance(mode, int) or mode not in range(4):
        raise ProfileRunError("saved profile has an unsupported scan mode")
    source = config.get("src")
    if not isinstance(source, str) or not os.path.isdir(source):
        raise ProfileRunError("saved profile source folder is missing or inaccessible")
    destination = config.get("dst", "")
    if mode in {1, 2}:
        if not isinstance(destination, str) or not destination.strip():
            raise ProfileRunError("categorization profiles require a destination folder")
        try:
            validate_tree_pair(source, destination)
        except Exception as exc:
            raise ProfileRunError(f"saved profile has unsafe folder roots: {exc}") from exc
    return dict(config)


def run_profile(profile_name: str, *, auto_apply: bool = False) -> int:
    """Scan a named profile offscreen and optionally apply its selected results."""
    # Set this before importing PyQt so a task never creates a physical-display window.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    from PyQt6.QtCore import QThread, QThreadPool, QTimer
    from PyQt6.QtWidgets import QApplication

    from fileorganizer.main_window import FileOrganizer
    from fileorganizer.move_journal import get_pending_summary
    from fileorganizer.plugins import ProfileManager

    try:
        config = validate_profile_config(ProfileManager.load(profile_name))
    except (OSError, ValueError, ProfileRunError) as exc:
        raise ProfileRunError(f"could not load profile '{profile_name}': {exc}") from exc

    app = QApplication.instance() or QApplication(["FileOrganizer", "--background"])
    app.setQuitOnLastWindowClosed(False)
    window = FileOrganizer(background_automation=True)
    window._apply_profile_config(config)
    mode = int(config["mode"])
    exit_code = 0

    def after_thread_stops(thread: Any, callback: Callable[[], None]) -> None:
        if thread.isRunning():
            QTimer.singleShot(25, lambda: after_thread_stops(thread, callback))
            return
        QTimer.singleShot(0, callback)

    def finish(code: int, message: str) -> None:
        nonlocal exit_code
        exit_code = code
        print(message, flush=True)
        QTimer.singleShot(0, lambda: app.exit(code))

    def after_apply(*result: object) -> None:
        errors = int(result[1]) if len(result) > 1 else 0
        apply_worker = window.apply_worker
        after_thread_stops(
            apply_worker,
            lambda: finish(
                1 if errors else 0,
                f"Profile '{profile_name}' apply finished with {errors} error(s).",
            ),
        )

    def begin_apply() -> None:
        if mode in {1, 2} and get_pending_summary():
            finish(
                1,
                "Unattended apply blocked because an interrupted move run needs review.",
            )
            return
        before = getattr(window, "apply_worker", None)
        if mode == window.OP_FILES:
            window._apply_files()
        elif mode in {window.OP_CAT, window.OP_SMART}:
            window._apply_cat()
        else:
            window._apply_aep()
        worker = getattr(window, "apply_worker", None)
        if worker is None or worker is before:
            blocked = bool(getattr(window, "_background_apply_blocked", False))
            finish(
                1 if blocked else 0,
                "Background apply was blocked by preflight."
                if blocked
                else f"Profile '{profile_name}' scan found no selected work to apply.",
            )
            return
        worker.finished.connect(after_apply)

    def finalize_scan() -> None:
        count = len(
            window.file_items
            if mode == window.OP_FILES
            else window.cat_items
            if mode in {window.OP_CAT, window.OP_SMART}
            else window.aep_items
        )
        print(f"Profile '{profile_name}' scan finished with {count} item(s).", flush=True)
        if not auto_apply:
            finish(0, "Preview-only schedule completed; no filesystem changes were made.")
            return
        QTimer.singleShot(0, begin_apply)

    def after_scan() -> None:
        after_thread_stops(window.worker, finalize_scan)

    window._on_scan()
    worker = getattr(window, "worker", None)
    if worker is None:
        window.close()
        raise ProfileRunError("profile scan did not start")
    worker.finished.connect(after_scan)
    app.exec()
    tracked_threads = {
        value
        for value in vars(window).values()
        if isinstance(value, QThread)
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
        # QThread wrappers owned by the window must be deleted while the Qt
        # application is still alive.  Leaving finished workers for Python's
        # interpreter shutdown can trigger a native abort on Windows.
        try:
            thread.deleteLater()
        except RuntimeError:
            pass
    QThreadPool.globalInstance().waitForDone(5_000)
    window.close()
    window.deleteLater()
    app.processEvents()
    return exit_code
