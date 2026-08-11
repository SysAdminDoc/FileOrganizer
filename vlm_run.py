#!/usr/bin/env python3
"""NDJSON sidecar for opt-in Qwen2.5-VL/llama.cpp classification and OCR."""

from __future__ import annotations

import argparse
import os
import traceback
from pathlib import Path

from fileorganizer.capabilities import get_capability
from fileorganizer.clip_index import IMAGE_EXTENSIONS
from fileorganizer.vlm import VlmResponseError, VlmUnavailable, classify_qwen
from fileorganizer.sidecar_protocol import SidecarEmitter


_PROTOCOL = SidecarEmitter("vlm")


def _emit(event: dict) -> None:
    _PROTOCOL.emit(event)


def _input_paths(root: str | None, files: list[str]) -> list[str]:
    paths: list[str] = []
    seen: set[str] = set()
    if root:
        for directory, _, names in os.walk(root, followlinks=False):
            for name in sorted(names):
                path = os.path.abspath(os.path.join(directory, name))
                if Path(path).suffix.casefold() not in IMAGE_EXTENSIONS:
                    continue
                key = os.path.normcase(path)
                if key not in seen:
                    paths.append(path)
                    seen.add(key)
    for value in files:
        path = os.path.abspath(os.path.normpath(value))
        key = os.path.normcase(path)
        if key not in seen:
            paths.append(path)
            seen.add(key)
    return paths


def main(argv: list[str] | None = None) -> int:
    _PROTOCOL.reset()
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--root", help="Recursively classify supported images")
    source.add_argument("--file", action="append", default=[], help="Classify one image; repeatable")
    parser.add_argument("--model", required=True, help="Qwen2.5-VL GGUF model path")
    parser.add_argument("--mmproj", required=True, help="Multimodal projector GGUF path")
    parser.add_argument("--cli", help="llama-qwen2vl-cli executable; defaults to PATH/env")
    parser.add_argument("--category", action="append", default=[],
                        help="Allowed category; repeat to constrain responses")
    parser.add_argument("--initial-confidence", type=int, default=0,
                        help="Existing confidence for --file inputs")
    parser.add_argument("--trigger-below", type=int, default=70,
                        help="Only invoke the VLM below this confidence")
    parser.add_argument("--max-tokens", type=int, default=1024)
    parser.add_argument("--context-size", type=int, default=16384)
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--gpu-layers", type=int)
    parser.add_argument("--asset-db", help="Optional asset_fingerprints.db to update")
    parser.add_argument("--asset-id", type=int, help="Asset row to update; valid for one input")
    args = parser.parse_args(argv)

    if args.root and not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2
    for value in args.file:
        if not os.path.isfile(value):
            _emit({"event": "error", "code": "file_not_found",
                   "message": f"File not found: {value}"})
            return 2
    paths = _input_paths(args.root, args.file)
    if not paths:
        _emit({"event": "error", "code": "no_images",
               "message": "No supported image files were found."})
        return 2
    if args.asset_id is not None and len(paths) != 1:
        _emit({"event": "error", "code": "asset_id_requires_one_file",
               "message": "--asset-id can only be used with one image."})
        return 2
    if not 0 <= args.initial_confidence <= 100 or not 0 <= args.trigger_below <= 100:
        parser.error("confidence values must be between 0 and 100")

    capability = get_capability("vlm", "qwen2vl_cli")
    if capability["status"] == "unavailable" and not args.cli:
        _PROTOCOL.emit_capability_error(
            "qwen2vl_cli",
            "Install llama.cpp's Qwen2-VL CLI or pass its executable with --cli.",
        )
        return 3

    _emit({"event": "start", "mode": "qwen2vl", "root": os.path.abspath(args.root)
           if args.root else None, "files_found": len(paths), "model": Path(args.model).name})
    classified = skipped = errors = 0
    for path in paths:
        if args.initial_confidence >= args.trigger_below:
            skipped += 1
            _emit({"event": "item", "path": path, "status": "skipped",
                   "reason": "confidence_above_trigger"})
            continue
        try:
            result = classify_qwen(
                path,
                model_path=args.model,
                mmproj_path=args.mmproj,
                categories=args.category,
                cli_path=args.cli,
                max_tokens=args.max_tokens,
                context_size=args.context_size,
                timeout=args.timeout,
                gpu_layers=args.gpu_layers,
            )
            if args.asset_id is not None:
                import asset_db

                asset_db.update_vlm_record(
                    args.asset_id,
                    ocr_text=result.ocr_text,
                    vmodel_used=result.model,
                    category=result.category,
                    confidence=result.confidence,
                    db_path=args.asset_db or asset_db.DB_FILE,
                )
            classified += 1
            _emit({"event": "item", "path": path, "status": "classified",
                   "category": result.category, "confidence": result.confidence,
                   "description": result.description, "ocr_text": result.ocr_text,
                   "requires_ocr": result.requires_ocr,
                   "has_text_overlay": result.has_text_overlay,
                   "model": result.model})
        except (VlmUnavailable, VlmResponseError, ValueError, OSError, RuntimeError) as exc:
            errors += 1
            _emit({"event": "item", "path": path, "status": "error",
                   "reason": f"{type(exc).__name__}: {exc}"})

    _emit({"event": "summary", "classified": classified, "skipped": skipped,
           "errors": errors})
    _emit({"event": "complete", "total": len(paths), "classified": classified,
           "skipped": skipped, "errors": errors})
    return 0 if errors == 0 else 4


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
        raise SystemExit(130)
    except Exception as exc:
        _emit({"event": "error", "code": "crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        raise SystemExit(1)
