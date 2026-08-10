"""Persist and register the per-user Windows watch-mode logon task."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any, Callable

from fileorganizer.path_safety import validate_tree_pair


SCHEMA_VERSION = 1
TASK_NAME = "FileOrganizer_WatchMode"
MIN_DEBOUNCE_SECONDS = 2
MAX_DEBOUNCE_SECONDS = 120
MAX_WATCHES = 128
MAX_LOG_BYTES = 1_048_576
MAX_LOG_LINES = 250


def _app_data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "FileOrganizer"


CONFIG_FILE = _app_data_dir() / "watch_task.json"
LOG_FILE = _app_data_dir() / "logs" / "watch_task.log"


class WatchTaskError(RuntimeError):
    """Raised when watch-task configuration or registration is unsafe."""


def _validate_debounce(value: Any) -> int:
    if isinstance(value, bool):
        raise WatchTaskError("debounce must be an integer")
    try:
        debounce = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise WatchTaskError("debounce must be an integer") from exc
    if str(value).strip() not in {str(debounce), f"+{debounce}"}:
        raise WatchTaskError("debounce must be an integer")
    if not MIN_DEBOUNCE_SECONDS <= debounce <= MAX_DEBOUNCE_SECONDS:
        raise WatchTaskError(
            f"debounce must be between {MIN_DEBOUNCE_SECONDS} and "
            f"{MAX_DEBOUNCE_SECONDS} seconds"
        )
    return debounce


def _validate_watches(
    raw_watches: Any,
    *,
    require_sources: bool = True,
) -> list[dict[str, Any]]:
    if not isinstance(raw_watches, list):
        raise WatchTaskError("watches must be a JSON array")
    if len(raw_watches) > MAX_WATCHES:
        raise WatchTaskError(f"at most {MAX_WATCHES} watches may be configured")

    watches: list[dict[str, Any]] = []
    seen_sources: set[str] = set()
    for index, raw in enumerate(raw_watches):
        if not isinstance(raw, dict):
            raise WatchTaskError(f"watch[{index}] must be an object")
        source = raw.get("src")
        destination = raw.get("dest")
        copy = raw.get("copy", False)
        if not isinstance(source, str) or not source.strip():
            raise WatchTaskError(f"watch[{index}].src must be a nonempty string")
        if not isinstance(destination, str) or not destination.strip():
            raise WatchTaskError(f"watch[{index}].dest must be a nonempty string")
        if not isinstance(copy, bool):
            raise WatchTaskError(f"watch[{index}].copy must be true or false")
        if require_sources and not os.path.isdir(source):
            raise WatchTaskError(f"watch[{index}].src is not an existing folder")
        try:
            source_root, destination_root = validate_tree_pair(source, destination)
        except Exception as exc:
            raise WatchTaskError(f"watch[{index}] has unsafe roots: {exc}") from exc
        source_key = os.path.normcase(source_root)
        if source_key in seen_sources:
            raise WatchTaskError(f"watch[{index}].src is configured more than once")
        seen_sources.add(source_key)
        watches.append({
            "src": source_root,
            "dest": destination_root,
            "copy": copy,
        })
    return watches


def default_config() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": False,
        "debounce_seconds": 30,
        "watches": [],
    }


def load_config(path: Path = CONFIG_FILE) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default_config()
    except (OSError, json.JSONDecodeError) as exc:
        raise WatchTaskError(f"could not read watch configuration: {exc}") from exc
    if not isinstance(raw, dict) or raw.get("schema_version") != SCHEMA_VERSION:
        raise WatchTaskError("watch configuration schema is unsupported")
    return {
        "schema_version": SCHEMA_VERSION,
        "enabled": bool(raw.get("enabled", False)),
        "debounce_seconds": _validate_debounce(raw.get("debounce_seconds", 30)),
        "watches": _validate_watches(raw.get("watches", []), require_sources=False),
    }


def save_config(
    watches: Any,
    debounce_seconds: Any,
    *,
    enabled: bool | None = None,
    path: Path = CONFIG_FILE,
    require_sources: bool = True,
) -> dict[str, Any]:
    validated_watches = _validate_watches(
        watches,
        require_sources=require_sources,
    )
    debounce = _validate_debounce(debounce_seconds)
    previous_enabled = False
    if enabled is None:
        try:
            previous_enabled = bool(load_config(path).get("enabled", False))
        except WatchTaskError:
            previous_enabled = False
    config = {
        "schema_version": SCHEMA_VERSION,
        "enabled": previous_enabled if enabled is None else bool(enabled),
        "debounce_seconds": debounce,
        "watches": validated_watches,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temp_name = stream.name
            json.dump(config, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
        raise WatchTaskError(f"could not save watch configuration: {exc}") from exc
    return config


def _update_enabled(enabled: bool, path: Path = CONFIG_FILE) -> dict[str, Any]:
    config = load_config(path)
    return save_config(
        config["watches"],
        config["debounce_seconds"],
        enabled=enabled,
        path=path,
        require_sources=False,
    )


def _is_windows() -> bool:
    return os.name == "nt"


def _run_schtasks(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "check": False,
    }
    if _is_windows():
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(["schtasks.exe", *arguments], **kwargs)


def _pythonw_executable(python_executable: str | None = None) -> str:
    executable = Path(python_executable or sys.executable)
    if executable.name.lower() == "pythonw.exe" and executable.is_file():
        return str(executable)
    candidate = executable.with_name("pythonw.exe")
    if candidate.is_file():
        return str(candidate)
    raise WatchTaskError(
        "pythonw.exe was not found beside the configured Python interpreter"
    )


def _task_action(
    runner_path: Path,
    python_executable: str | None = None,
) -> str:
    pythonw = _pythonw_executable(python_executable)
    return subprocess.list2cmdline([pythonw, str(runner_path), "--run"])


def task_registered() -> bool:
    if not _is_windows():
        return False
    result = _run_schtasks(["/Query", "/TN", TASK_NAME])
    return result.returncode == 0


def register_task(
    runner_path: Path,
    *,
    python_executable: str | None = None,
    config_path: Path = CONFIG_FILE,
) -> None:
    if not _is_windows():
        raise WatchTaskError("Windows Task Scheduler is unavailable on this platform")
    config = load_config(config_path)
    if not config["watches"]:
        raise WatchTaskError("configure at least one watch before enabling startup")
    _validate_watches(config["watches"], require_sources=True)
    if not runner_path.is_file():
        raise WatchTaskError(f"watch task runner is missing: {runner_path}")
    action = _task_action(runner_path, python_executable)
    result = _run_schtasks([
        "/Create",
        "/TN", TASK_NAME,
        "/SC", "ONLOGON",
        "/TR", action,
        "/RL", "LIMITED",
        "/F",
    ])
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise WatchTaskError(f"Task Scheduler registration failed: {message}")
    _update_enabled(True, config_path)


def set_task_enabled(enabled: bool, path: Path = CONFIG_FILE) -> None:
    if not _is_windows():
        raise WatchTaskError("Windows Task Scheduler is unavailable on this platform")
    if not task_registered():
        if enabled:
            raise WatchTaskError("watch startup task is not registered")
        _update_enabled(False, path)
        return
    action = "/ENABLE" if enabled else "/DISABLE"
    result = _run_schtasks(["/Change", "/TN", TASK_NAME, action])
    if result.returncode != 0:
        message = (result.stderr or result.stdout).strip()
        raise WatchTaskError(f"Task Scheduler update failed: {message}")
    _update_enabled(enabled, path)


def unregister_task(path: Path = CONFIG_FILE) -> None:
    if not _is_windows():
        raise WatchTaskError("Windows Task Scheduler is unavailable on this platform")
    if task_registered():
        result = _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"])
        if result.returncode != 0:
            message = (result.stderr or result.stdout).strip()
            raise WatchTaskError(f"Task Scheduler removal failed: {message}")
    _update_enabled(False, path)


def status(
    *,
    config_path: Path = CONFIG_FILE,
    log_path: Path = LOG_FILE,
) -> dict[str, Any]:
    config = load_config(config_path)
    supported = _is_windows()
    registered = task_registered() if supported else False
    return {
        "supported": supported,
        "configured": bool(config["watches"]),
        "enabled": bool(config["enabled"] and registered),
        "registered": registered,
        "watch_count": len(config["watches"]),
        "debounce_seconds": config["debounce_seconds"],
        "task_name": TASK_NAME,
        "log_path": str(log_path),
    }


def _rotate_log(path: Path) -> None:
    try:
        if path.stat().st_size < MAX_LOG_BYTES:
            return
    except FileNotFoundError:
        return
    except OSError as exc:
        raise WatchTaskError(f"could not inspect watch log: {exc}") from exc
    archive = path.with_suffix(path.suffix + ".1")
    try:
        os.replace(path, archive)
    except OSError as exc:
        raise WatchTaskError(f"could not rotate watch log: {exc}") from exc


class _BoundedLogWriter:
    """Text writer that keeps one active log and one bounded rollover."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._stream: Any = None
        self._bytes = 0

    def __enter__(self) -> _BoundedLogWriter:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        _rotate_log(self.path)
        try:
            self._bytes = self.path.stat().st_size
        except FileNotFoundError:
            self._bytes = 0
        self._stream = self.path.open("a", encoding="utf-8", buffering=1)
        return self

    def __exit__(self, *_args: object) -> None:
        if self._stream is not None:
            self._stream.close()

    def _rollover(self) -> None:
        self._stream.close()
        archive = self.path.with_suffix(self.path.suffix + ".1")
        os.replace(self.path, archive)
        self._stream = self.path.open("a", encoding="utf-8", buffering=1)
        self._bytes = 0

    def write(self, value: str) -> int:
        encoded = value.encode("utf-8", errors="replace")
        if len(encoded) > MAX_LOG_BYTES:
            encoded = encoded[-MAX_LOG_BYTES:]
            value = encoded.decode("utf-8", errors="replace")
        if self._bytes and self._bytes + len(encoded) > MAX_LOG_BYTES:
            self._rollover()
        written = self._stream.write(value)
        self._bytes += len(value.encode("utf-8", errors="replace"))
        return written

    def flush(self) -> None:
        self._stream.flush()


def read_log_tail(path: Path = LOG_FILE, max_lines: int = MAX_LOG_LINES) -> str:
    limit = max(1, min(int(max_lines), MAX_LOG_LINES))
    try:
        with path.open("r", encoding="utf-8", errors="replace") as stream:
            lines = stream.readlines()
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise WatchTaskError(f"could not read watch log: {exc}") from exc
    return "".join(lines[-limit:])


def run_background(
    *,
    config_path: Path = CONFIG_FILE,
    log_path: Path = LOG_FILE,
    watch_main: Callable[[list[str]], int] | None = None,
) -> int:
    config = load_config(config_path)
    if not config["enabled"] or not config["watches"]:
        return 0
    runner = watch_main
    if runner is None:
        from watch_run import main

        runner = main

    arguments = [
        "--watches", json.dumps(config["watches"], separators=(",", ":")),
        "--settle", str(config["debounce_seconds"]),
    ]
    try:
        with _BoundedLogWriter(log_path) as stream:
            with redirect_stdout(stream), redirect_stderr(stream):
                return int(runner(arguments) or 0)
    except OSError as exc:
        raise WatchTaskError(f"could not write watch log: {exc}") from exc
