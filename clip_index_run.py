#!/usr/bin/env python3
"""NDJSON sidecar for optional CLIP image indexing and nearest-neighbor search."""

from __future__ import annotations

import argparse
import os
import traceback

from fileorganizer.capabilities import get_capability
from fileorganizer.clip_index import (
    ClipEmbedder,
    ClipIndex,
    ClipIndexUnavailable,
    MODEL_NAME,
    PRETRAINED_NAME,
    iter_image_paths,
    stable_model_id,
)
from fileorganizer.sidecar_protocol import SidecarEmitter


_PROTOCOL = SidecarEmitter("clip_index")


def _emit(event: dict) -> None:
    _PROTOCOL.emit(event)


def main(argv: list[str] | None = None) -> int:
    _PROTOCOL.reset()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Image root to index")
    parser.add_argument("--query", help="Image path to search for")
    parser.add_argument("--db", required=True, help="sqlite-vec database path")
    parser.add_argument("--model", default=MODEL_NAME)
    parser.add_argument("--pretrained", default=PRETRAINED_NAME)
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.0,
                        help="Minimum cosine similarity for query results")
    parser.add_argument("--rebuild", action="store_true",
                        help="Clear existing vectors before indexing")
    args = parser.parse_args(argv)

    if bool(args.root) == bool(args.query):
        parser.error("provide exactly one of --root or --query")
    if args.root and not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2
    if args.query and not os.path.isfile(args.query):
        _emit({"event": "error", "code": "query_not_found",
               "message": f"Query image not found: {args.query}"})
        return 2

    capability = get_capability("clip_index", "clip_visual_index")
    if capability["status"] == "unavailable":
        _PROTOCOL.emit_capability_error(
            "clip_visual_index",
            "Install open_clip_torch, torch, and sqlite-vec before running the CLIP index.",
        )
        return 3

    try:
        embedder = ClipEmbedder(
            model_name=args.model,
            pretrained=args.pretrained,
            device=args.device,
            batch_size=args.batch_size,
        )
        with ClipIndex(args.db) as index:
            model_id = stable_model_id(args.model, args.pretrained)
            if args.root:
                paths = list(iter_image_paths(args.root))
                _emit({"event": "start", "mode": "index", "root": os.path.abspath(args.root),
                       "db": os.path.abspath(args.db), "model": model_id,
                       "files_found": len(paths), "plan_only": True})
                if args.rebuild:
                    index.clear()
                index.ensure_model(model_id)
                live_paths = {os.path.normcase(os.path.abspath(path)) for path in paths}
                indexed = 0
                failed = 0
                for start in range(0, len(paths), embedder.batch_size):
                    encoded, failures = embedder.encode_paths(paths[start:start + embedder.batch_size])
                    for item in encoded:
                        index.upsert(item.path, item.embedding)
                        indexed += 1
                        _emit({"event": "item", "path": item.path, "status": "indexed",
                               "model": model_id})
                    failed += len(failures)
                    _emit({"event": "progress", "scanned": min(start + embedder.batch_size, len(paths)),
                           "indexed": indexed, "stage": "CLIP embedding"})
                removed = index.remove_missing_under(args.root, live_paths)
                _emit({"event": "summary", "indexed": indexed, "failed": failed,
                       "removed": removed, "total_indexed": index.count()})
                _emit({"event": "complete", "total": len(paths), "indexed": indexed,
                       "failed": failed, "removed": removed})
                return 0

            _emit({"event": "start", "mode": "query", "query": os.path.abspath(args.query),
                   "db": os.path.abspath(args.db), "model": model_id, "plan_only": True})
            index.ensure_model(model_id)
            encoded, failures = embedder.encode_paths([args.query])
            if not encoded:
                detail = failures[0].reason if failures else "query image could not be encoded"
                _emit({"event": "error", "code": "query_encode_failed", "message": detail})
                return 4
            results = index.search(
                encoded[0].embedding,
                limit=args.limit,
                minimum_similarity=args.threshold,
            )
            for result in results:
                _emit({"event": "item", "path": result["path"], "status": "match",
                       "similarity": result["similarity"], "size": result["size"]})
            _emit({"event": "complete", "total": len(results), "matches": len(results)})
            return 0
    except ClipIndexUnavailable as exc:
        _emit({"event": "error", "code": "clip_unavailable", "message": str(exc)})
        return 3
    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
        return 130
    except Exception as exc:
        _emit({"event": "error", "code": "crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
