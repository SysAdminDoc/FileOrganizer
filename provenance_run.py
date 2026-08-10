#!/usr/bin/env python3
"""Inspect, export, and replay classification provenance records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fileorganizer.classification_provenance import (
    default_export_path,
    export_jsonl,
    get_stats,
    replay_jsonl,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--stats", action="store_true", help="show safe aggregate counts")
    actions.add_argument(
        "--export",
        nargs="?",
        const="",
        metavar="PATH",
        help="export redacted JSONL (default: per-user exports directory)",
    )
    actions.add_argument(
        "--replay",
        metavar="JSONL",
        help="replay a redacted provenance JSONL export",
    )
    parser.add_argument(
        "--fixtures",
        metavar="JSONL",
        help="fixture decisions for --replay, keyed by input_fingerprint",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.stats:
        print(json.dumps(get_stats(), indent=2, sort_keys=True))
        return 0
    if args.export is not None:
        output = Path(args.export) if args.export else default_export_path()
        count = export_jsonl(output)
        print(f"Exported {count} redacted provenance record(s) to {output}")
        return 0
    if not args.fixtures:
        raise SystemExit("--replay requires --fixtures")
    result = replay_jsonl(args.replay, args.fixtures)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
