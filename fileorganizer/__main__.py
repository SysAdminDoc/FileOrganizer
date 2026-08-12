"""FileOrganizer — Application entry point."""
# PyInstaller fork-bomb safeguard. MUST be the first executable statement
# in the entry script: when the bundled exe re-spawns itself (e.g., a
# child process for a Pool worker), freeze_support intercepts and runs
# the worker entry instead of re-running main(). Skipping this is the
# canonical PyInstaller fork-bomb.
import multiprocessing as _mp
_mp.freeze_support()

import os, sys
from datetime import datetime
from pathlib import Path
from PyQt6.QtGui import QIcon


# codex-branding:start
def _branding_icon_path() -> Path:
    candidates = []
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "icon.ico", exe_dir / "icon.png"])
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidates.extend([Path(meipass) / "icon.ico", Path(meipass) / "icon.png"])
    current = Path(__file__).resolve()
    for base in (current.parent, current.parent.parent, current.parent.parent.parent):
        candidates.extend([base / "icon.ico", base / "icon.png"])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return Path("icon.ico")
# codex-branding:end


def main():
    """Launch the FileOrganizer application."""
    # Crash handler
    from fileorganizer.config import _APP_DATA_DIR
    from fileorganizer.audit_log import configure_audit

    configure_audit(console=False)

    _CRASH_LOG = os.path.join(_APP_DATA_DIR, 'crash.log')
    _CRASH_LOG_MAX = 512 * 1024  # 500 KB

    def _rotate_crash_log():
        try:
            if os.path.exists(_CRASH_LOG) and os.path.getsize(_CRASH_LOG) > _CRASH_LOG_MAX:
                rotated = _CRASH_LOG + '.1'
                if os.path.exists(rotated):
                    os.remove(rotated)
                os.rename(_CRASH_LOG, rotated)
        except OSError:
            pass

    def _crash_handler(exc_type, exc_value, exc_tb):
        import traceback as _tb
        lines = _tb.format_exception(exc_type, exc_value, exc_tb)
        crash_text = ''.join(lines)
        timestamp = datetime.now().isoformat()
        entry = f"\n{'='*60}\n[{timestamp}] Unhandled {exc_type.__name__}\n{crash_text}"
        try:
            _rotate_crash_log()
            with open(_CRASH_LOG, 'a', encoding='utf-8') as f:
                f.write(entry)
        except OSError:
            pass
        from PyQt6.QtWidgets import QApplication, QMessageBox
        qapp = QApplication.instance()
        if qapp:
            QMessageBox.critical(None, "FileOrganizer — Crash",
                f"An unexpected error occurred:\n\n{exc_type.__name__}: {exc_value}\n\n"
                f"Details saved to:\n{_CRASH_LOG}")
        sys.__excepthook__(exc_type, exc_value, exc_tb)

    import argparse
    sys.excepthook = _crash_handler

    parser = argparse.ArgumentParser(description="FileOrganizer — Context-Aware File Organizer")
    parser.add_argument("--source", type=str, default=None,
                        help="Source folder to auto-scan (used by shell integration)")
    parser.add_argument("--headless", action="store_true",
                        help="Scan offscreen for Explorer integration; pair with --auto-apply")
    parser.add_argument("--profile", type=str, default=None,
                        help="Load a named profile for scheduled/automated scans")
    parser.add_argument("--auto-apply", action="store_true",
                        help="Automatically apply after scan (for scheduled tasks)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate apply without moving/renaming files")
    parser.add_argument("--schedule", type=str, default=None, metavar="PROFILE",
                        help="Register a saved profile with the operating-system scheduler")
    parser.add_argument("--schedule-name", type=str, default=None,
                        help="Optional task name for --schedule")
    parser.add_argument("--schedule-frequency", choices=("daily", "weekly", "monthly", "on_logon"),
                        default="daily")
    parser.add_argument("--schedule-time", default="09:00", metavar="HH:MM")
    parser.add_argument("--schedule-day", type=int, default=None,
                        help="Weekday 0-6 or day of month 1-31, depending on frequency")
    args, qt_args = parser.parse_known_args()

    if args.schedule:
        from schedule_task_run import main as schedule_main

        schedule_args = [
            "--schedule", args.schedule,
            "--frequency", args.schedule_frequency,
            "--time", args.schedule_time,
        ]
        if args.schedule_name:
            schedule_args += ["--name", args.schedule_name]
        if args.schedule_day is not None:
            option = "--day-of-month" if args.schedule_frequency == "monthly" else "--day-of-week"
            schedule_args += [option, str(args.schedule_day)]
        if args.auto_apply:
            schedule_args.append("--auto-apply")
        raise SystemExit(schedule_main(schedule_args))

    if args.headless:
        from fileorganizer.context_menu import run_headless

        raise SystemExit(
            run_headless(args.source, auto_apply=args.auto_apply, dry_run=args.dry_run)
        )

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QTimer
    from fileorganizer.accessibility import install_accessibility
    from fileorganizer.config import get_active_stylesheet
    from fileorganizer.i18n import install_locale
    from fileorganizer.main_window import FileOrganizer
    from fileorganizer.plugins import ProfileManager

    app = QApplication(qt_args)
    locale_manager = install_locale(app)
    accessibility_manager = install_accessibility(app)

    branding_icon = QIcon(str(_branding_icon_path()))

    app.setWindowIcon(branding_icon)
    app.setStyle("Fusion")
    app.setStyleSheet(get_active_stylesheet())
    window = FileOrganizer()
    locale_manager.apply(window)
    accessibility_manager.apply(window)
    window._cli_dry_run = args.dry_run

    if args.profile:
        try:
            profile = ProfileManager.load(args.profile)
            if profile:
                window._apply_profile_config(profile)
                window._log(f"Loaded profile: {args.profile}")
        except Exception as e:
            window._log(f"Failed to load profile '{args.profile}': {e}")
    window.show()

    if args.source and os.path.isdir(args.source):
        window.cmb_op.setCurrentIndex(FileOrganizer.OP_FILES)
        # The preset combo is intentionally not editable; a shell path must
        # select its Custom entry before assigning the requested source.
        window.cmb_pc_src.blockSignals(True)
        custom_index = next(
            (i for i, (label, _path) in enumerate(window._pc_src_presets)
             if label == "Custom…"),
            -1,
        )
        if custom_index >= 0:
            window.cmb_pc_src.setCurrentIndex(custom_index)
        window.cmb_pc_src.blockSignals(False)
        window.txt_pc_src.setReadOnly(False)
        window.txt_pc_src.setText(args.source)
        if hasattr(window, 'txt_pc_src'):
            window.txt_pc_src.setText(args.source)
        QTimer.singleShot(200, window._on_scan)
    elif args.profile and args.auto_apply:
        def _auto_scan_apply():
            window._on_scan()
            def _check_and_apply():
                if not hasattr(window, '_scan_worker') or window._scan_worker is None:
                    window._apply_files(dry_run=args.dry_run)
                else:
                    QTimer.singleShot(500, _check_and_apply)
            QTimer.singleShot(1000, _check_and_apply)
        QTimer.singleShot(200, _auto_scan_apply)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
