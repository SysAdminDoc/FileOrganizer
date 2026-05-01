#!/usr/bin/env python3
"""NDJSON sidecar — duplicate detection.

Two modes:

    files   - Czkawka-style progressive hash: bucket by size, then prefix
              SHA-256 (4 KB), then full SHA-256. Reports byte-identical
              duplicates regardless of file type.
    images  - Perceptual hashing (pHash via imagehash) indexed in a
              BK-tree for sublinear similarity search. Reports near-
              duplicates with Hamming distance up to `--threshold`.

Both modes emit one `group` event per duplicate cluster, with a list of
file paths sorted by length (shortest first = canonical keeper).

NDJSON events:
    {"event":"start","mode":"files|images","root":"..."}
    {"event":"progress","stage":"<msg>","scanned":N,"groups":N}
    {"event":"group","mode":"files|images","key":"<hash>",
        "files":[{"path":"...","size":N,"distance":N?}, ...]}
    {"event":"complete","total_files":N,"groups":N,"wasted_bytes":N}
    {"event":"error","code":"...","message":"..."}
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from collections import defaultdict

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".tiff", ".tif")


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _walk(root: str, only_images: bool) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if only_images and not f.lower().endswith(IMAGE_EXTS):
                continue
            out.append(os.path.join(dirpath, f))
    return out


def _hash_prefix(path: str, n: int = 4096) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            h.update(f.read(n))
    except OSError:
        return ""
    return h.hexdigest()


def _hash_full(path: str) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    except OSError:
        return ""
    return h.hexdigest()


def _dedup_files(root: str, min_size: int) -> tuple[list[dict], int, int, int]:
    files = _walk(root, only_images=False)
    state = {"last": 0.0}

    # Stage 1: bucket by size.
    by_size: dict[int, list[str]] = defaultdict(list)
    for i, path in enumerate(files):
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size < min_size:
            continue
        by_size[size].append(path)

        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress", "stage": "size buckets",
                   "scanned": i + 1, "groups": 0})

    # Stage 2: prefix-hash within each size bucket >= 2.
    by_prefix: dict[tuple, list[str]] = defaultdict(list)
    candidate_paths = [(s, p) for s, paths in by_size.items() if len(paths) >= 2 for p in paths]
    for i, (size, path) in enumerate(candidate_paths):
        ph = _hash_prefix(path)
        if not ph:
            continue
        by_prefix[(size, ph)].append(path)
        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress", "stage": "prefix hashes",
                   "scanned": i + 1, "groups": 0})

    # Stage 3: full hash within each prefix bucket >= 2.
    groups: list[dict] = []
    wasted = 0
    final_paths = [(k, p) for k, paths in by_prefix.items() if len(paths) >= 2 for p in paths]
    by_full: dict[tuple, list[str]] = defaultdict(list)
    for i, (key, path) in enumerate(final_paths):
        fh = _hash_full(path)
        if not fh:
            continue
        try:
            sz = os.path.getsize(path)
        except OSError:
            continue
        by_full[(sz, fh)].append(path)
        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress", "stage": "full hashes",
                   "scanned": i + 1, "groups": len(groups)})

    for (size, full_hash), paths in by_full.items():
        if len(paths) < 2:
            continue
        paths_sorted = sorted(paths, key=len)  # shortest path = canonical keeper
        wasted += size * (len(paths_sorted) - 1)
        groups.append({"key": full_hash[:16],
                       "files": [{"path": p, "size": size} for p in paths_sorted]})

    return groups, len(files), wasted, len(by_full)


def _dedup_images(root: str, threshold: int) -> tuple[list[dict], int, int]:
    try:
        from PIL import Image
        import imagehash
        import pybktree
    except ImportError as exc:
        raise RuntimeError(f"Missing dep: {exc}") from exc

    files = _walk(root, only_images=True)
    state = {"last": 0.0}

    hashes: list[tuple[int, str]] = []  # (int hash, path)
    for i, path in enumerate(files):
        try:
            with Image.open(path) as im:
                ph = imagehash.phash(im)
            hashes.append((int(str(ph), 16), path))
        except Exception:
            continue
        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress", "stage": "perceptual hashing",
                   "scanned": i + 1, "groups": 0})

    if not hashes:
        return [], 0, 0

    # Build BK-tree keyed on integer hashes; distance = bit popcount XOR.
    def hamming(a: tuple, b: tuple) -> int:
        return bin(a[0] ^ b[0]).count("1")

    tree = pybktree.BKTree(hamming, hashes)

    seen: set = set()
    groups: list[dict] = []
    for i, item in enumerate(hashes):
        if item[1] in seen:
            continue
        cluster = [(d, p) for d, (h, p) in
                   ((dist, x) for dist, x in tree.find(item, threshold))
                   if p not in seen]
        if len(cluster) < 2:
            continue
        cluster.sort(key=lambda dp: (dp[0], len(dp[1])))
        files_out = []
        for dist, p in cluster:
            try:
                sz = os.path.getsize(p)
            except OSError:
                sz = 0
            files_out.append({"path": p, "size": sz, "distance": dist})
            seen.add(p)
        groups.append({"key": f"phash-{i}", "files": files_out})

        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress", "stage": "BK-tree clustering",
                   "scanned": i + 1, "groups": len(groups)})

    return groups, len(files), len(groups)


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON duplicate detector")
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=["files", "images"], default="files")
    parser.add_argument("--min-size", type=int, default=1024,
                        help="Files smaller than this many bytes are ignored (file mode).")
    parser.add_argument("--threshold", type=int, default=8,
                        help="Hamming distance threshold for image mode (0=exact, 8=very similar, 16=loose).")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2

    _emit({"event": "start", "mode": args.mode, "root": args.root})

    try:
        if args.mode == "files":
            groups, total, wasted, group_count = _dedup_files(args.root, args.min_size)
        else:
            groups, total, group_count = _dedup_images(args.root, args.threshold)
            wasted = sum(f["size"] for g in groups for f in g["files"][1:])
    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
        return 130
    except Exception as exc:
        _emit({"event": "error", "code": "crashed",
               "message": f"{type(exc).__name__}: {exc}"})
        return 1

    for g in groups:
        _emit({"event": "group", "mode": args.mode, **g})

    _emit({"event": "complete",
           "total_files": total,
           "groups": group_count,
           "wasted_bytes": wasted})
    return 0


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
