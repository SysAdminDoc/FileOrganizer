#!/usr/bin/env python3
"""Emit the full machine-readable shell capability matrix."""
from __future__ import annotations

import argparse

from fileorganizer.capabilities import capability_matrix
from fileorganizer.sidecar_protocol import SidecarEmitter


_PROTOCOL = SidecarEmitter("capabilities")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", default="all")
    args = parser.parse_args()
    matrix = capability_matrix(args.workflow)
    _PROTOCOL.emit({"event": "summary", "capability_matrix": matrix, "total": len(matrix)})
    _PROTOCOL.emit({"event": "complete", "total_count": len(matrix)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
