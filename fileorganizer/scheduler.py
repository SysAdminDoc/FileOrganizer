"""Cross-platform registration and persistence for scheduled scan profiles."""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, fields
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from fileorganizer.config import _APP_DATA_DIR
from fileorganizer.path_safety import validate_storage_name


SCHEMA_VERSION = 2
TASK_PREFIX = "FileOrganizer_Schedule_"
VALID_FREQUENCIES = {"daily", "weekly", "monthly", "on_logon"}


class SchedulerError(RuntimeError):
    """Raised when a schedule is invalid or cannot be registered."""


@dataclass
class ScheduledProfile:
    """A saved scan profile and the cadence used to run it."""

    name: str
    folder_path: str
    frequency: str
    time: str
    day_of_week: Optional[int] = None
    day_of_month: Optional[int] = None
    enabled: bool = True
    created_at: Optional[str] = None
    last_run: Optional[str] = None
    profile_name: Optional[str] = None
    auto_apply: bool = False
    last_status: Optional[str] = None
    last_error: Optional[str] = None
    last_finished: Optional[str] = None

    def __post_init__(self) -> None:
        if self.created_at is None:
            self.created_at = datetime.now().isoformat(timespec="seconds")
        if self.profile_name is None:
            self.profile_name = self.name


def _atomic_json_write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = ""
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = stream.name
            json.dump(value, stream, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except OSError as exc:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError:
                pass
        raise SchedulerError(f"could not save schedules: {exc}") from exc


def _unit_slug(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-.")
    if not slug:
        raise SchedulerError("schedule name has no usable characters")
    return slug[:80]


class SchedulerManager:
    """Manage scheduled profile scans through the host's per-user scheduler."""

    def __init__(
        self,
        config_dir: Optional[str] = None,
        *,
        runner_path: Optional[Path] = None,
        python_executable: Optional[str] = None,
    ) -> None:
        base = Path(config_dir) if config_dir else Path(_APP_DATA_DIR) / "schedules"
        base.mkdir(parents=True, exist_ok=True)
        self.config_dir = base
        self.schedules_file = base / "schedules.json"
        self.platform = platform.system()
        self.runner_path = runner_path or Path(__file__).resolve().parent.parent / "schedule_task_run.py"
        self.python_executable = python_executable or sys.executable
        self.schedules: dict[str, ScheduledProfile] = self._load_schedules()
        legacy_file = Path.home() / ".fileorganizer" / "schedules" / "schedules.json"
        if not self.schedules_file.exists() and legacy_file.is_file():
            current = self.schedules_file
            self.schedules_file = legacy_file
            self.schedules = self._load_schedules()
            self.schedules_file = current
            if self.schedules:
                self._save_schedules()

    def _load_schedules(self) -> dict[str, ScheduledProfile]:
        try:
            raw = json.loads(self.schedules_file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, json.JSONDecodeError):
            return {}
        if isinstance(raw, dict) and "schedules" in raw:
            raw = raw.get("schedules")
        if not isinstance(raw, dict):
            return {}
        allowed = {item.name for item in fields(ScheduledProfile)}
        schedules: dict[str, ScheduledProfile] = {}
        for name, value in raw.items():
            if not isinstance(name, str) or not isinstance(value, dict):
                continue
            try:
                payload = {key: val for key, val in value.items() if key in allowed}
                schedules[name] = ScheduledProfile(**payload)
            except (TypeError, ValueError):
                continue
        return schedules

    def _save_schedules(self) -> None:
        # Keep the legacy top-level mapping so older installations can still read it.
        _atomic_json_write(
            self.schedules_file,
            {name: asdict(profile) for name, profile in self.schedules.items()},
        )

    @staticmethod
    def _validate_profile(profile: ScheduledProfile) -> None:
        try:
            validate_storage_name(profile.name)
            validate_storage_name(profile.profile_name or "")
        except ValueError as exc:
            raise SchedulerError(str(exc)) from exc
        if profile.frequency not in VALID_FREQUENCIES:
            raise SchedulerError(
                "frequency must be daily, weekly, monthly, or on_logon"
            )
        try:
            hour_text, minute_text = profile.time.split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except (AttributeError, TypeError, ValueError) as exc:
            raise SchedulerError("time must use 24-hour HH:MM format") from exc
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise SchedulerError("time must use 24-hour HH:MM format")
        profile.time = f"{hour:02d}:{minute:02d}"
        if profile.frequency == "weekly":
            if profile.day_of_week is None:
                profile.day_of_week = 0
            if not 0 <= profile.day_of_week <= 6:
                raise SchedulerError("day_of_week must be between 0 and 6")
        if profile.frequency == "monthly":
            if profile.day_of_month is None:
                profile.day_of_month = 1
            if not 1 <= profile.day_of_month <= 31:
                raise SchedulerError("day_of_month must be between 1 and 31")
        if not isinstance(profile.auto_apply, bool):
            raise SchedulerError("auto_apply must be true or false")

    def create_schedule(
        self,
        name: str,
        folder_path: str,
        frequency: str,
        time: str,
        day_of_week: Optional[int] = None,
        day_of_month: Optional[int] = None,
        *,
        profile_name: Optional[str] = None,
        auto_apply: bool = False,
        replace: bool = False,
    ) -> bool:
        if name in self.schedules and not replace:
            return False
        profile = ScheduledProfile(
            name=name,
            profile_name=profile_name or name,
            folder_path=folder_path,
            frequency=frequency,
            time=time,
            day_of_week=day_of_week,
            day_of_month=day_of_month,
            auto_apply=auto_apply,
        )
        try:
            self._validate_profile(profile)
        except SchedulerError:
            return False
        previous = self.schedules.get(name)
        if previous:
            profile.created_at = previous.created_at
            profile.last_run = previous.last_run
            profile.last_finished = previous.last_finished
            profile.last_status = previous.last_status
            profile.last_error = previous.last_error
        if not self._register_os_task(profile):
            return False
        self.schedules[name] = profile
        self._save_schedules()
        return True

    def delete_schedule(self, name: str) -> bool:
        profile = self.schedules.get(name)
        if profile is None:
            return False
        if not self._unregister_os_task(profile):
            return False
        del self.schedules[name]
        self._save_schedules()
        return True

    def enable_schedule(self, name: str) -> bool:
        return self._set_enabled(name, True)

    def disable_schedule(self, name: str) -> bool:
        return self._set_enabled(name, False)

    def _set_enabled(self, name: str, enabled: bool) -> bool:
        profile = self.schedules.get(name)
        if profile is None:
            return False
        succeeded = self._set_os_task_enabled(profile, enabled)
        if succeeded:
            profile.enabled = enabled
            self._save_schedules()
        return succeeded

    def list_schedules(self) -> list[ScheduledProfile]:
        return sorted(self.schedules.values(), key=lambda item: item.name.casefold())

    def get_schedule(self, name: str) -> Optional[ScheduledProfile]:
        return self.schedules.get(name)

    def note_run_started(self, name: str) -> None:
        profile = self.schedules.get(name)
        if profile is None:
            raise SchedulerError(f"unknown schedule: {name}")
        profile.last_run = datetime.now().isoformat(timespec="seconds")
        profile.last_status = "running"
        profile.last_error = None
        self._save_schedules()

    def note_run_finished(self, name: str, *, succeeded: bool, error: str = "") -> None:
        profile = self.schedules.get(name)
        if profile is None:
            raise SchedulerError(f"unknown schedule: {name}")
        profile.last_finished = datetime.now().isoformat(timespec="seconds")
        profile.last_status = "completed" if succeeded else "failed"
        profile.last_error = error[:2000] or None
        self._save_schedules()

    def _task_name(self, profile: ScheduledProfile) -> str:
        return f"{TASK_PREFIX}{_unit_slug(profile.name)}"

    def _runner_tokens(self, profile: ScheduledProfile) -> list[str]:
        if not self.runner_path.is_file():
            raise SchedulerError(f"schedule runner is missing: {self.runner_path}")
        executable = Path(self.python_executable)
        if self.platform == "Windows" and executable.name.lower() != "pythonw.exe":
            pythonw = executable.with_name("pythonw.exe")
            if not pythonw.is_file():
                raise SchedulerError(
                    "pythonw.exe was not found beside the configured Python interpreter"
                )
            executable = pythonw
        return [str(executable), str(self.runner_path), "--run", profile.name]

    @staticmethod
    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        options: dict[str, Any] = {
            "capture_output": True,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "check": False,
            **kwargs,
        }
        if os.name == "nt":
            options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        return subprocess.run(command, **options)

    def _register_os_task(self, profile: ScheduledProfile) -> bool:
        try:
            if self.platform == "Windows":
                return self._register_windows_task(profile)
            if self.platform == "Darwin":
                return self._register_macos_task(profile)
            return self._register_linux_task(profile)
        except (OSError, SchedulerError):
            return False

    def _unregister_os_task(self, profile: ScheduledProfile) -> bool:
        try:
            if self.platform == "Windows":
                return self._unregister_windows_task(profile)
            if self.platform == "Darwin":
                return self._unregister_macos_task(profile)
            return self._unregister_linux_task(profile)
        except OSError:
            return False

    def _set_os_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        try:
            if self.platform == "Windows":
                return self._set_windows_task_enabled(profile, enabled)
            if self.platform == "Darwin":
                return self._set_macos_task_enabled(profile, enabled)
            return self._set_linux_task_enabled(profile, enabled)
        except OSError:
            return False

    def _register_windows_task(self, profile: ScheduledProfile) -> bool:
        schedule = {
            "daily": "DAILY",
            "weekly": "WEEKLY",
            "monthly": "MONTHLY",
            "on_logon": "ONLOGON",
        }[profile.frequency]
        action = subprocess.list2cmdline(self._runner_tokens(profile))
        command = [
            "schtasks.exe", "/Create", "/TN", self._task_name(profile),
            "/SC", schedule, "/TR", action, "/RL", "LIMITED", "/F",
        ]
        if profile.frequency != "on_logon":
            command += ["/ST", profile.time]
        if profile.frequency == "weekly":
            days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
            command += ["/D", days[profile.day_of_week or 0]]
        elif profile.frequency == "monthly":
            command += ["/D", str(profile.day_of_month or 1)]
        return self._run(command).returncode == 0

    # Retained for callers/tests that used the old fallback method directly.
    def _register_windows_task_schtasks(self, profile: ScheduledProfile) -> bool:
        return self._register_windows_task(profile)

    def _unregister_windows_task(self, profile: ScheduledProfile) -> bool:
        result = self._run([
            "schtasks.exe", "/Delete", "/TN", self._task_name(profile), "/F",
        ])
        # Missing tasks are already unregistered.
        return result.returncode in {0, 1}

    def _set_windows_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        switch = "/ENABLE" if enabled else "/DISABLE"
        return self._run([
            "schtasks.exe", "/Change", "/TN", self._task_name(profile), switch,
        ]).returncode == 0

    def _launchd_path(self, profile: ScheduledProfile) -> Path:
        return Path.home() / "Library" / "LaunchAgents" / (
            f"com.fileorganizer.schedule.{_unit_slug(profile.name).lower()}.plist"
        )

    def _register_macos_task(self, profile: ScheduledProfile) -> bool:
        import plistlib

        path = self._launchd_path(profile)
        path.parent.mkdir(parents=True, exist_ok=True)
        hour, minute = (int(part) for part in profile.time.split(":"))
        label = path.stem
        payload: dict[str, Any] = {
            "Label": label,
            "ProgramArguments": self._runner_tokens(profile),
            "StandardOutPath": str(self.config_dir / f"{_unit_slug(profile.name)}.log"),
            "StandardErrorPath": str(self.config_dir / f"{_unit_slug(profile.name)}.log"),
        }
        if profile.frequency == "on_logon":
            payload["RunAtLoad"] = True
        else:
            payload["StartCalendarInterval"] = self._get_launchd_interval(
                profile, hour, minute
            )
        with path.open("wb") as stream:
            plistlib.dump(payload, stream)
        result = self._run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)])
        if result.returncode != 0 and "already bootstrapped" not in result.stderr.lower():
            return False
        if not profile.enabled:
            return self._set_macos_task_enabled(profile, False)
        return True

    def _get_launchd_interval(
        self, profile: ScheduledProfile, hour: int, minute: int
    ) -> list[dict[str, int]]:
        base = {"Hour": hour, "Minute": minute}
        if profile.frequency == "weekly":
            # launchd uses Sunday=1 through Saturday=7.
            weekday = ((profile.day_of_week or 0) + 1) % 7 + 1
            return [{**base, "Weekday": weekday}]
        if profile.frequency == "monthly":
            return [{**base, "Day": profile.day_of_month or 1}]
        return [base]

    def _unregister_macos_task(self, profile: ScheduledProfile) -> bool:
        path = self._launchd_path(profile)
        self._run(["launchctl", "bootout", f"gui/{os.getuid()}", str(path)])
        try:
            path.unlink(missing_ok=True)
        except OSError:
            return False
        return True

    def _set_macos_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        target = f"gui/{os.getuid()}/{self._launchd_path(profile).stem}"
        verb = "enable" if enabled else "disable"
        return self._run(["launchctl", verb, target]).returncode == 0

    def _systemd_paths(self, profile: ScheduledProfile) -> tuple[Path, Path]:
        base = Path.home() / ".config" / "systemd" / "user"
        slug = _unit_slug(profile.name).lower()
        return base / f"fileorganizer-{slug}.timer", base / f"fileorganizer-{slug}.service"

    def _register_linux_task(self, profile: ScheduledProfile) -> bool:
        if profile.frequency == "on_logon":
            return self._register_linux_systemd_timer(profile)
        if self._register_linux_systemd_timer(profile):
            return True
        return self._register_linux_cron(profile)

    def _register_linux_systemd_timer(self, profile: ScheduledProfile) -> bool:
        timer, service = self._systemd_paths(profile)
        timer.parent.mkdir(parents=True, exist_ok=True)
        command = " ".join(shlex.quote(token) for token in self._runner_tokens(profile))
        service.write_text(
            "[Unit]\n"
            f"Description=FileOrganizer scheduled scan: {profile.name}\n\n"
            "[Service]\nType=oneshot\n"
            f"ExecStart={command}\n",
            encoding="utf-8",
        )
        timer.write_text(self._get_systemd_timer_content(profile), encoding="utf-8")
        if self._run(["systemctl", "--user", "daemon-reload"]).returncode != 0:
            return False
        verb = "enable" if profile.enabled else "disable"
        return self._run([
            "systemctl", "--user", verb, "--now", timer.name,
        ]).returncode == 0

    def _get_systemd_timer_content(self, profile: ScheduledProfile) -> str:
        hour, minute = profile.time.split(":")
        if profile.frequency == "weekly":
            days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
            calendar = f"{days[profile.day_of_week or 0]} *-*-* {hour}:{minute}:00"
        elif profile.frequency == "monthly":
            calendar = f"*-*-{profile.day_of_month or 1:02d} {hour}:{minute}:00"
        elif profile.frequency == "on_logon":
            calendar = ""
        else:
            calendar = f"*-*-* {hour}:{minute}:00"
        trigger = "OnStartupSec=30\n" if not calendar else f"OnCalendar={calendar}\n"
        return (
            "[Unit]\n"
            f"Description=FileOrganizer {profile.name} Timer\n\n"
            "[Timer]\n"
            f"{trigger}Persistent=true\n\n"
            "[Install]\nWantedBy=timers.target\n"
        )

    def _register_linux_cron(self, profile: ScheduledProfile) -> bool:
        if profile.frequency == "on_logon":
            return False
        entry = self._get_cron_entry(profile)
        result = self._run(["crontab", "-l"])
        existing = result.stdout if result.returncode == 0 else ""
        lines = [line for line in existing.splitlines() if line.strip()]
        if entry not in lines:
            lines.append(entry)
        update = self._run(["crontab", "-"], input="\n".join(lines) + "\n")
        return update.returncode == 0

    def _get_cron_entry(self, profile: ScheduledProfile) -> str:
        hour, minute = profile.time.split(":")
        if profile.frequency == "weekly":
            # cron is Sunday=0; the public model is Monday=0.
            day = ((profile.day_of_week or 0) + 1) % 7
            cadence = f"{minute} {hour} * * {day}"
        elif profile.frequency == "monthly":
            cadence = f"{minute} {hour} {profile.day_of_month or 1} * *"
        else:
            cadence = f"{minute} {hour} * * *"
        command = " ".join(shlex.quote(token) for token in self._runner_tokens(profile))
        return f"{cadence} {command} # fileorganizer:{_unit_slug(profile.name)}"

    def _unregister_linux_task(self, profile: ScheduledProfile) -> bool:
        timer, service = self._systemd_paths(profile)
        self._run(["systemctl", "--user", "disable", "--now", timer.name])
        existed = timer.exists() or service.exists()
        try:
            timer.unlink(missing_ok=True)
            service.unlink(missing_ok=True)
        except OSError:
            return False
        if existed:
            self._run(["systemctl", "--user", "daemon-reload"])

        result = self._run(["crontab", "-l"])
        if result.returncode == 0:
            marker = f"# fileorganizer:{_unit_slug(profile.name)}"
            lines = [line for line in result.stdout.splitlines() if marker not in line]
            self._run(["crontab", "-"], input="\n".join(lines) + "\n")
        return True

    def _set_linux_task_enabled(self, profile: ScheduledProfile, enabled: bool) -> bool:
        timer, _service = self._systemd_paths(profile)
        verb = "enable" if enabled else "disable"
        return self._run([
            "systemctl", "--user", verb, "--now", timer.name,
        ]).returncode == 0
