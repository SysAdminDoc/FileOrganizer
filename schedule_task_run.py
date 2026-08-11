#!/usr/bin/env python3
"""Register, inspect, or run scheduled FileOrganizer scan profiles."""

from __future__ import annotations

import argparse
import json
import os
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
from pathlib import Path
from typing import TextIO

from fileorganizer.plugins import ProfileManager
from fileorganizer.profile_runner import ProfileRunError, run_profile
from fileorganizer.scheduler import SchedulerError, SchedulerManager, _unit_slug


RUNNER_PATH = Path(__file__).resolve()
MAX_LOG_BYTES = 1_048_576
MAX_LOG_LINES = 250


class _BoundedLog:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.stream: TextIO | None = None

    def __enter__(self) -> TextIO:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            if self.path.stat().st_size >= MAX_LOG_BYTES:
                os.replace(self.path, self.path.with_suffix(".log.1"))
        except FileNotFoundError:
            pass
        self.stream = self.path.open("a", encoding="utf-8", buffering=1)
        return self.stream

    def __exit__(self, *_args: object) -> None:
        if self.stream is not None:
            self.stream.close()


def _log_path(manager: SchedulerManager, name: str) -> Path:
    return manager.config_dir / f"{_unit_slug(name)}.log"


def _read_log(path: Path) -> str:
    try:
        return "".join(path.read_text(encoding="utf-8", errors="replace").splitlines(True)[-MAX_LOG_LINES:])
    except FileNotFoundError:
        return ""
    except OSError as exc:
        raise SchedulerError(f"could not read schedule log: {exc}") from exc


def _state(manager: SchedulerManager, **extra: object) -> dict[str, object]:
    schedules = []
    for profile in manager.list_schedules():
        item = asdict(profile)
        item["log_path"] = str(_log_path(manager, profile.name))
        schedules.append(item)
    return {
        "supported": manager.platform in {"Windows", "Darwin", "Linux"},
        "profiles": ProfileManager.list_profiles(),
        "schedules": schedules,
        **extra,
    }


def _print_state(manager: SchedulerManager, **extra: object) -> None:
    print(json.dumps(_state(manager, **extra), ensure_ascii=False))


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--schedule", metavar="PROFILE")
    commands.add_argument("--delete", metavar="NAME")
    commands.add_argument("--enable", metavar="NAME")
    commands.add_argument("--disable", metavar="NAME")
    commands.add_argument("--status", action="store_true")
    commands.add_argument("--profiles", action="store_true")
    commands.add_argument("--logs", metavar="NAME")
    commands.add_argument("--run", metavar="NAME")
    parser.add_argument("--name", help="Schedule name; defaults to the profile name")
    parser.add_argument(
        "--frequency",
        choices=["daily", "weekly", "monthly", "on_logon"],
        default="daily",
    )
    parser.add_argument("--time", default="09:00", help="Local time in 24-hour HH:MM format")
    parser.add_argument("--day-of-week", type=int, choices=range(7), default=0)
    parser.add_argument("--day-of-month", type=int, choices=range(1, 32), default=1)
    parser.add_argument("--auto-apply", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_argument_parser().parse_args(argv)
    manager = SchedulerManager(runner_path=RUNNER_PATH)
    try:
        if args.run:
            schedule = manager.get_schedule(args.run)
            if schedule is None:
                raise SchedulerError(f"unknown schedule: {args.run}")
            manager.note_run_started(schedule.name)
            log_path = _log_path(manager, schedule.name)
            try:
                with _BoundedLog(log_path) as stream:
                    with redirect_stdout(stream), redirect_stderr(stream):
                        code = run_profile(
                            schedule.profile_name or schedule.name,
                            auto_apply=schedule.auto_apply,
                        )
                manager.note_run_finished(
                    schedule.name,
                    succeeded=code == 0,
                    error="" if code == 0 else "profile runner reported errors",
                )
                return code
            except Exception as exc:
                manager.note_run_finished(schedule.name, succeeded=False, error=str(exc))
                try:
                    with _BoundedLog(log_path) as stream:
                        print(f"Scheduled scan failed: {exc}", file=stream)
                except OSError:
                    pass
                return 1
        if args.schedule:
            config = ProfileManager.load(args.schedule)
            source = config.get("src", "") if isinstance(config, dict) else ""
            name = args.name or args.schedule
            created = manager.create_schedule(
                name,
                source,
                args.frequency,
                args.time,
                args.day_of_week,
                args.day_of_month,
                profile_name=args.schedule,
                auto_apply=args.auto_apply,
                replace=True,
            )
            if not created:
                raise SchedulerError("the operating-system scheduler rejected the task")
            _print_state(manager, message=f"Schedule '{name}' registered.")
            return 0
        if args.delete:
            if not manager.delete_schedule(args.delete):
                raise SchedulerError(f"could not remove schedule: {args.delete}")
            _print_state(manager, message=f"Schedule '{args.delete}' removed.")
            return 0
        if args.enable:
            if not manager.enable_schedule(args.enable):
                raise SchedulerError(f"could not enable schedule: {args.enable}")
            _print_state(manager, message=f"Schedule '{args.enable}' enabled.")
            return 0
        if args.disable:
            if not manager.disable_schedule(args.disable):
                raise SchedulerError(f"could not disable schedule: {args.disable}")
            _print_state(manager, message=f"Schedule '{args.disable}' disabled.")
            return 0
        if args.logs:
            if manager.get_schedule(args.logs) is None:
                raise SchedulerError(f"unknown schedule: {args.logs}")
            _print_state(manager, log=_read_log(_log_path(manager, args.logs)))
            return 0
        _print_state(manager)
        return 0
    except (OSError, ValueError, SchedulerError, ProfileRunError) as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
