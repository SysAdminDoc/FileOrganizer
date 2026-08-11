#!/usr/bin/env python3
"""NDJSON sidecar for local Chroma-backed CLIP image/text search."""

from __future__ import annotations

import argparse
import os
import traceback

from fileorganizer.capabilities import get_capability
from fileorganizer.chroma_index import (
    ChromaIndex,
    ChromaIndexUnavailable,
    ChromaRecord,
    document_for_path,
    record_id,
)
from fileorganizer.clip_index import ClipEmbedder, ClipIndexUnavailable, iter_image_paths
from fileorganizer.sidecar_protocol import SidecarEmitter


_PROTOCOL = SidecarEmitter("chroma_index")


def _emit(event: dict) -> None:
    _PROTOCOL.emit(event)


def main(argv: list[str] | None = None) -> int:
    _PROTOCOL.reset()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", help="Image root to index")
    query = parser.add_mutually_exclusive_group()
    query.add_argument("--query-image", help="Image path to search for")
    query.add_argument("--query-text", help="Text prompt to search against image names")
    parser.add_argument("--db", required=True, help="Persistent Chroma directory")
    parser.add_argument("--collection", default="fileorganizer_clip")
    parser.add_argument("--model", default="ViT-L-14")
    parser.add_argument("--pretrained", default="datacomp_xl_s13b_b90k")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"], default="auto")
    parser.add_argument("--batch-size", type=int, default=16)
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=0.0)
    parser.add_argument("--rebuild", action="store_true")
    args = parser.parse_args(argv)

    operations = [bool(args.root), bool(args.query_image), bool(args.query_text)]
    if sum(operations) != 1:
        parser.error("provide exactly one of --root, --query-image, or --query-text")
    if args.root and not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2
    if args.query_image and not os.path.isfile(args.query_image):
        _emit({"event": "error", "code": "query_not_found",
               "message": f"Query image not found: {args.query_image}"})
        return 2

    capability = get_capability("chroma_index", "cross_modal_search")
    if capability["status"] == "unavailable":
        _PROTOCOL.emit_capability_error(
            "cross_modal_search",
            "Install chromadb, open_clip_torch, and torch before running Chroma search.",
        )
        return 3

    try:
        embedder = ClipEmbedder(
            model_name=args.model,
            pretrained=args.pretrained,
            device=args.device,
            batch_size=args.batch_size,
        )
        with ChromaIndex(args.db, collection=args.collection) as index:
            if args.root:
                paths = list(iter_image_paths(args.root))
                _emit({"event": "start", "mode": "index", "root": os.path.abspath(args.root),
                       "db": os.path.abspath(args.db), "files_found": len(paths),
                       "plan_only": True})
                if args.rebuild:
                    # Chroma's collection delete is intentionally avoided here;
                    # upserts plus stale cleanup preserve the collection identity.
                    existing = index.collection.get()
                    ids = existing.get("ids", [])
                    if ids:
                        index.collection.delete(ids=[str(value) for value in ids])
                indexed = 0
                failed = 0
                live_paths = {os.path.normcase(os.path.abspath(path)) for path in paths}
                for start in range(0, len(paths), embedder.batch_size):
                    encoded, failures = embedder.encode_paths(paths[start:start + embedder.batch_size])
                    records = [ChromaRecord(
                        record_id=record_id(item.path),
                        path=item.path,
                        embedding=item.embedding,
                        document=document_for_path(item.path),
                        metadata={"kind": "image"},
                    ) for item in encoded]
                    indexed += index.upsert(records)
                    failed += len(failures)
                    for item in encoded:
                        _emit({"event": "item", "path": item.path, "status": "indexed"})
                    _emit({"event": "progress", "scanned": min(start + embedder.batch_size, len(paths)),
                           "indexed": indexed, "stage": "CLIP embedding"})
                removed = index.remove_missing_under(args.root, live_paths)
                _emit({"event": "summary", "indexed": indexed, "failed": failed,
                       "removed": removed, "total_indexed": index.count()})
                _emit({"event": "complete", "total": len(paths), "indexed": indexed,
                       "failed": failed, "removed": removed})
                return 0

            query_path = args.query_image or ""
            if args.query_image:
                encoded, failures = embedder.encode_paths([args.query_image])
                if not encoded:
                    detail = failures[0].reason if failures else "query image could not be encoded"
                    _emit({"event": "error", "code": "query_encode_failed", "message": detail})
                    return 4
                query_embedding = encoded[0].embedding
                query_label = query_path
            else:
                query_embedding = embedder.encode_texts([args.query_text or ""])[0]
                query_label = args.query_text
            _emit({"event": "start", "mode": "query", "query": query_label,
                   "db": os.path.abspath(args.db), "plan_only": True})
            results = index.query(
                query_embedding,
                limit=args.limit,
                minimum_similarity=args.threshold,
            )
            for result in results:
                _emit({"event": "item", "path": result["path"], "status": "match",
                       "similarity": result["similarity"], "document": result["document"]})
            _emit({"event": "complete", "total": len(results), "matches": len(results)})
            return 0
    except (ChromaIndexUnavailable, ClipIndexUnavailable) as exc:
        _emit({"event": "error", "code": "embedding_unavailable", "message": str(exc)})
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
