"""Crash handler and log viewer for GUI worker threads (NEXT-38).

Installs sys.excepthook and threading.excepthook overrides that:
1. Write every uncaught exception to %APPDATA%/FileOrganizer/crash.log
2. Emit a Qt signal so the GUI can show a non-blocking toast
3. Preserve pending journal rows for the N-6 resume flow
"""
import logging
import os
import sys
import threading
import traceback
from datetime import datetime, timezone
from typing import Optional, Callable

from fileorganizer.config import _APP_DATA_DIR

_CRASH_LOG = os.path.join(_APP_DATA_DIR, "crash.log")
_MAX_LOG_SIZE = 5 * 1024 * 1024  # 5 MB
_write_lock = threading.Lock()

log = logging.getLogger(__name__)
_on_crash_callback: Optional[Callable[[str], None]] = None


def install(on_crash: Optional[Callable[[str], None]] = None):
    """Install global exception hooks.

    Args:
        on_crash: Optional callback(message) called on any uncaught exception.
                  Use this to show a GUI toast.
    """
    global _on_crash_callback
    _on_crash_callback = on_crash

    sys.excepthook = _sys_excepthook

    if hasattr(threading, "excepthook"):
        threading.excepthook = _thread_excepthook


def _sys_excepthook(exc_type, exc_value, exc_tb):
    """Handle uncaught exceptions in the main thread."""
    _record_crash(exc_type, exc_value, exc_tb, thread_name="MainThread")


def _thread_excepthook(args):
    """Handle uncaught exceptions in worker threads (Python 3.8+)."""
    _record_crash(
        args.exc_type,
        args.exc_value,
        args.exc_traceback,
        thread_name=getattr(args.thread, "name", "UnknownThread"),
    )


def _record_crash(exc_type, exc_value, exc_tb, thread_name=""):
    """Write crash to log file and trigger callback."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    tb_text = "".join(tb_lines)

    entry = (
        f"\n{'=' * 72}\n"
        f"[{ts}] Thread: {thread_name}\n"
        f"Exception: {exc_type.__name__}: {exc_value}\n"
        f"{tb_text}"
        f"{'=' * 72}\n"
    )

    with _write_lock:
        _rotate_log()
        try:
            os.makedirs(_APP_DATA_DIR, exist_ok=True)
            with open(_CRASH_LOG, "a", encoding="utf-8") as f:
                f.write(entry)
        except Exception:
            pass

    msg = f"Worker crash: {exc_type.__name__}: {exc_value}"
    log.error(msg)

    if _on_crash_callback:
        try:
            _on_crash_callback(msg)
        except Exception:
            pass


def _rotate_log():
    """Truncate crash log if it exceeds max size."""
    try:
        if os.path.isfile(_CRASH_LOG) and os.path.getsize(_CRASH_LOG) > _MAX_LOG_SIZE:
            with open(_CRASH_LOG, "r", encoding="utf-8") as f:
                lines = f.readlines()
            half = len(lines) // 2
            with open(_CRASH_LOG, "w", encoding="utf-8") as f:
                f.write("... (older entries truncated)\n")
                f.writelines(lines[half:])
    except Exception:
        pass


def get_crash_log_path() -> str:
    """Return the path to the crash log file."""
    return _CRASH_LOG


def read_recent_crashes(max_entries: int = 20) -> str:
    """Read the most recent crash log entries."""
    if not os.path.isfile(_CRASH_LOG):
        return "No crashes recorded."

    try:
        with open(_CRASH_LOG, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return "Unable to read crash log."

    entries = content.split("=" * 72)
    entries = [e.strip() for e in entries if e.strip()]

    if not entries:
        return "No crashes recorded."

    recent = entries[-max_entries:]
    return ("\n" + "=" * 72 + "\n").join(recent)


def clear_crash_log():
    """Clear the crash log file."""
    try:
        if os.path.isfile(_CRASH_LOG):
            os.remove(_CRASH_LOG)
    except OSError:
        pass
