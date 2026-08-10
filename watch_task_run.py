#!/usr/bin/env python3
"""Manage or run the per-user FileOrganizer watch-mode logon task."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fileorganizer import watch_task


RUNNER_PATH = Path(__file__).resolve()


def _print_status(**extra: object) -> None:
    print(json.dumps({**watch_task.status(), **extra}, ensure_ascii=False))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--configure", action="store_true")
    commands.add_argument("--register", action="store_true")
    commands.add_argument("--enable", action="store_true")
    commands.add_argument("--disable", action="store_true")
    commands.add_argument("--unregister", action="store_true")
    commands.add_argument("--status", action="store_true")
    commands.add_argument("--logs", action="store_true")
    commands.add_argument("--run", action="store_true")
    parser.add_argument("--watches", help="JSON watch array for --configure")
    parser.add_argument("--debounce", default="30")
    args = parser.parse_args(argv)

    try:
        if args.run:
            return watch_task.run_background()
        if args.configure:
            if args.watches is None:
                raise watch_task.WatchTaskError("--configure requires --watches")
            try:
                watches = json.loads(args.watches)
            except json.JSONDecodeError as exc:
                raise watch_task.WatchTaskError(f"invalid --watches JSON: {exc}") from exc
            watch_task.save_config(watches, args.debounce)
            _print_status(message="Watch settings saved.")
            return 0
        if args.register:
            watch_task.register_task(RUNNER_PATH)
            _print_status(message="Watch startup enabled for user logon.")
            return 0
        if args.enable:
            watch_task.set_task_enabled(True)
            _print_status(message="Watch startup enabled.")
            return 0
        if args.disable:
            watch_task.set_task_enabled(False)
            _print_status(message="Watch startup disabled.")
            return 0
        if args.unregister:
            watch_task.unregister_task()
            _print_status(message="Watch startup task removed.")
            return 0
        if args.logs:
            _print_status(log=watch_task.read_log_tail())
            return 0
        _print_status()
        return 0
    except watch_task.WatchTaskError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
