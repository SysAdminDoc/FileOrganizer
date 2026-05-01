#!/usr/bin/env python3
"""NDJSON sidecar — PC file organizer (sort by extension/type).

For users who just want to organize a messy Downloads / Desktop folder
without any AI in the loop. Files are routed by extension into category
buckets (a superset of Smart Sort's, with finer subcategories like
Documents/Spreadsheets, Pictures/RAW). Preview / apply modes.

NDJSON events:
    {"event":"start","root":"...","dest":"...","mode":"..."}
    {"event":"progress","scanned":N,"planned":N,"moved":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"planned|moved|skipped|error",
        "category":"...","new_path":"..."}
    {"event":"summary","by_category":{"...":N,...}}
    {"event":"complete","total":N,"planned":N,"moved":N,"skipped":N,"errors":N}
    {"event":"error","code":"...","message":"..."}
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
import traceback
from collections import Counter

# Finer-grained categories than Smart Sort. Keeps power-users happy who
# want Pictures/RAW separate from Pictures/JPEGs.
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("Pictures/RAW",     (".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf", ".srw")),
    ("Pictures/JPEGs",   (".jpg", ".jpeg", ".jpe")),
    ("Pictures/PNGs",    (".png",)),
    ("Pictures/HEIC",    (".heic", ".heif")),
    ("Pictures/Vectors", (".svg", ".ai", ".eps")),
    ("Pictures/Other",   (".gif", ".bmp", ".webp", ".tiff", ".tif", ".ico", ".psd")),

    ("Music/FLAC",       (".flac", ".alac")),
    ("Music/Lossless",   (".wav", ".aiff", ".ape")),
    ("Music/Lossy",      (".mp3", ".m4a", ".aac", ".ogg", ".oga", ".opus", ".wma")),

    ("Video/MP4",        (".mp4", ".m4v")),
    ("Video/MKV",        (".mkv",)),
    ("Video/Other",      (".avi", ".mov", ".wmv", ".flv", ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob", ".ogv")),

    ("Documents/PDFs",        (".pdf",)),
    ("Documents/Word",        (".doc", ".docx", ".odt", ".rtf")),
    ("Documents/Spreadsheets",(".xls", ".xlsx", ".ods", ".csv", ".tsv")),
    ("Documents/Slides",      (".ppt", ".pptx", ".odp", ".key")),
    ("Documents/Plain text",  (".txt", ".md", ".log", ".rst")),

    ("Books",            (".epub", ".mobi", ".azw", ".azw3", ".kfx", ".cbz",
                          ".cbr", ".cb7", ".fb2", ".lit", ".pdb")),

    ("Fonts",            (".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc")),

    ("Archives",         (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
                          ".tgz", ".tbz2", ".cab")),

    ("Installers",       (".msi", ".exe", ".dmg", ".pkg", ".deb", ".rpm", ".apk", ".appx", ".msix")),

    ("Code",             (".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go",
                          ".java", ".kt", ".cs", ".cpp", ".c", ".h", ".rb",
                          ".php", ".swift", ".sh", ".ps1", ".sql", ".html",
                          ".css", ".scss", ".vue", ".svelte")),

    ("Data",             (".json", ".xml", ".yaml", ".yml", ".toml", ".ini", ".cfg")),
    ("Disk Images",      (".iso", ".img", ".vhd", ".vmdk", ".dmg")),
    ("3D Models",        (".obj", ".stl", ".fbx", ".blend", ".dae", ".3ds", ".gltf", ".glb")),
    ("Torrents",         (".torrent",)),
]


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _classify(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    for category, exts in RULES:
        if ext in exts:
            return category
    return "Other"


def _resolve_collision(dest: str) -> str:
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 1
    while True:
        cand = f"{base} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


def _walk(root: str, recursive: bool) -> list[str]:
    out = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not d.startswith(".")]
            for f in filenames:
                if not f.startswith("."):
                    out.append(os.path.join(dirpath, f))
    else:
        for entry in os.scandir(root):
            if entry.is_file(follow_symlinks=False) and not entry.name.startswith("."):
                out.append(entry.path)
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON PC file organizer")
    parser.add_argument("--root", required=True)
    parser.add_argument("--dest", default="",
                        help="Destination root. Defaults to --root (sort in place).")
    parser.add_argument("--mode", choices=["preview", "apply"], default="preview")
    parser.add_argument("--recursive", action="store_true",
                        help="Walk subfolders too. Default is the immediate root.")
    parser.add_argument("--copy", action="store_true")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2

    dest_root = os.path.abspath(args.dest) if args.dest else os.path.abspath(args.root)
    files = _walk(args.root, args.recursive)
    _emit({"event": "start", "root": args.root, "dest": dest_root,
           "mode": args.mode, "files_found": len(files)})

    state = {"scanned": 0, "planned": 0, "moved": 0, "skipped": 0, "errors": 0, "last": 0.0}
    by_cat: Counter = Counter()

    for path in files:
        state["scanned"] += 1
        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress", "scanned": state["scanned"],
                   "planned": state["planned"], "moved": state["moved"],
                   "stage": os.path.basename(path)[:200]})
        try:
            cat = _classify(path)
            by_cat[cat] += 1
            target = os.path.join(dest_root, cat, os.path.basename(path))

            if os.path.abspath(target) == os.path.abspath(path):
                state["skipped"] += 1
                _emit({"event": "item", "path": path, "category": cat,
                       "status": "skipped", "new_path": target})
                continue

            if args.mode == "preview":
                state["planned"] += 1
                _emit({"event": "item", "path": path, "category": cat,
                       "status": "planned", "new_path": target})
                continue

            target_unique = _resolve_collision(target)
            os.makedirs(os.path.dirname(target_unique), exist_ok=True)
            if args.copy:
                shutil.copy2(path, target_unique)
            else:
                shutil.move(path, target_unique)
            state["moved"] += 1
            _emit({"event": "item", "path": path, "category": cat,
                   "status": "moved", "new_path": target_unique})

        except KeyboardInterrupt:
            _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
            return 130
        except Exception as exc:
            state["errors"] += 1
            _emit({"event": "item", "path": path, "category": "Other",
                   "status": "error", "new_path": "",
                   "message": f"{type(exc).__name__}: {exc}"})

    _emit({"event": "summary", "by_category": dict(by_cat)})
    _emit({"event": "complete", "total": state["scanned"],
           "planned": state["planned"], "moved": state["moved"],
           "skipped": state["skipped"], "errors": state["errors"]})
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
