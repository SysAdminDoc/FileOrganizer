#!/usr/bin/env python3
"""NDJSON sidecar — Smart Sort dispatcher.

The "drop a folder, get an organized destination" workflow. Walks the
source root, classifies every file by extension into a category bucket
(audio / video / image / book / pdf / font / archive / code / document
/ other), and either previews the planned move or executes it into a
canonical destination tree.

Default destination layout:
    {dest_root}/Music/...
    {dest_root}/Video/...
    {dest_root}/Pictures/...
    {dest_root}/Books/...
    {dest_root}/PDFs/...
    {dest_root}/Fonts/...
    {dest_root}/Archives/...
    {dest_root}/Code/...
    {dest_root}/Documents/...
    {dest_root}/Other/...

The dispatcher delegates the *naming* of each destination file to the
matching media-type sidecar's logic — it imports their pure-Python
helpers rather than spawning subprocesses, so a 20k-file run is one
process, not 20k. Music files reuse `music_run._read_existing_tags` plus
the beets-style `_format_path`. Video files reuse `video_run._parse_one`.
Books reuse `books_run._read_one`. Fonts reuse `fonts_run._read_font`.
Anything else is moved with its original name preserved.

NDJSON events:
    {"event":"start","root":"...","dest":"...","mode":"...","plan_only":<bool>}
    {"event":"progress","scanned":N,"planned":N,"moved":N,"stage":"<msg>"}
    {"event":"item","path":"...","category":"...","status":"planned|moved|skipped|error",
        "new_path":"...","reason":"..."?}
    {"event":"summary","by_category":{"...":N,...}}
    {"event":"complete","total":N,"planned":N,"moved":N,"skipped":N,"errors":N}
    {"event":"error","code":"...","message":"..."}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import time
import traceback
from collections import Counter

# Extension → category routing.
CATEGORY_EXTS: dict[str, tuple[str, ...]] = {
    "audio":    (".mp3", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".oga",
                 ".opus", ".wav", ".wma", ".alac", ".aiff", ".ape"),
    "video":    (".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv",
                 ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob"),
    "image":    (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp",
                 ".tiff", ".tif", ".heic", ".heif", ".raw", ".cr2",
                 ".nef", ".arw", ".dng", ".orf", ".rw2", ".psd", ".ai", ".svg"),
    "book":     (".epub", ".mobi", ".azw", ".azw3", ".kfx", ".cbz",
                 ".cbr", ".cb7", ".fb2", ".lit", ".pdb"),
    "pdf":      (".pdf",),
    "font":     (".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc"),
    "archive":  (".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz",
                 ".tgz", ".tbz2"),
    "code":     (".py", ".js", ".ts", ".tsx", ".jsx", ".rs", ".go",
                 ".java", ".kt", ".cs", ".cpp", ".c", ".h", ".rb",
                 ".php", ".swift", ".sh", ".ps1", ".sql"),
    "document": (".docx", ".doc", ".odt", ".rtf", ".txt", ".md",
                 ".xlsx", ".xls", ".ods", ".csv", ".pptx", ".ppt",
                 ".odp", ".key", ".pages"),
}

# Some extensions are ambiguous between video and audio (.mp4 hosts AAC).
# Treat container-only extensions as video unless they're inside a folder
# named "Music" or similar — done at routing time.
VIDEO_PREFER_PARENT = re.compile(r"music|songs?|albums?|tracks?", re.I)


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _safe_name(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:180]


def _classify(path: str) -> str:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".mp4":
        # Disambiguate against parent folder hint.
        if VIDEO_PREFER_PARENT.search(os.path.dirname(path)):
            return "audio"
        return "video"
    for cat, exts in CATEGORY_EXTS.items():
        if ext in exts:
            return cat
    return "other"


def _walk_files(root: str) -> list[str]:
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        # Skip hidden + VCS dirs.
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in ("__pycache__",)]
        for f in filenames:
            if f.startswith("."):
                continue
            out.append(os.path.join(dirpath, f))
    return out


def _resolve_collision(dest: str) -> str:
    """If dest exists, append (1)/(2)/... until it doesn't."""
    if not os.path.exists(dest):
        return dest
    base, ext = os.path.splitext(dest)
    i = 1
    while True:
        cand = f"{base} ({i}){ext}"
        if not os.path.exists(cand):
            return cand
        i += 1


def _plan_audio(path: str, dest_root: str) -> str | None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from music_run import _read_existing_tags, _format_path
    except Exception:
        return None
    tags = _read_existing_tags(path)
    if not (tags.get("artist") or tags.get("albumartist")):
        # No useful tags — keep original layout under Music/.
        rel = os.path.relpath(path, start=os.path.commonpath([path, dest_root])
                              if os.path.commonpath([path, dest_root]) else os.path.dirname(path))
        return os.path.join(dest_root, "Music", os.path.basename(path))
    ext = os.path.splitext(path)[1].lstrip(".") or "mp3"
    rel = _format_path(
        "Music/{albumartist}/{album}/{disc:02}-{track:02} {title}.{ext}",
        {**tags, "ext": ext})
    return os.path.join(dest_root, rel)


def _plan_video(path: str, dest_root: str) -> str | None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from video_run import _parse_one, _format_path as _video_format
    except Exception:
        return None
    info = _parse_one(path)
    ext = os.path.splitext(path)[1].lstrip(".") or "mkv"
    if info.get("type") == "episode" and info.get("title"):
        return os.path.join(
            dest_root,
            _video_format(
                "TV/{title}/Season {season:02}/{title} - S{season:02}E{episode:02}.{ext}",
                {**info, "ext": ext}))
    if info.get("title"):
        return os.path.join(
            dest_root,
            _video_format(
                "Movies/{title} ({year})/{title} ({year}).{ext}",
                {**info, "ext": ext}))
    return os.path.join(dest_root, "Video", os.path.basename(path))


def _plan_book(path: str, dest_root: str) -> str | None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from books_run import _read_one, _format_path as _book_format
    except Exception:
        return None
    fields = _read_one(path)
    if not (fields.get("title") or fields.get("author")):
        return os.path.join(dest_root, "Books", os.path.basename(path))
    ext = os.path.splitext(path)[1].lstrip(".") or "epub"
    if fields.get("series"):
        return os.path.join(
            dest_root,
            _book_format(
                "Books/{author}/{series} #{series_index:g} - {title}.{ext}",
                {**fields, "ext": ext}))
    return os.path.join(
        dest_root,
        _book_format("Books/{author}/{title}.{ext}",
                     {**fields, "ext": ext}))


def _plan_font(path: str, dest_root: str) -> str | None:
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from fonts_run import _read_font
    except Exception:
        return None
    try:
        info = _read_font(path)
    except Exception:
        return os.path.join(dest_root, "Fonts", os.path.basename(path))
    fam = _safe_name(info.get("family", "") or "Unknown") or "Unknown"
    style = _safe_name(info.get("style", "Regular")) or "Regular"
    ext = info.get("format", "ttf")
    return os.path.join(dest_root, "Fonts", fam, f"{fam} - {style}.{ext}")


def _plan_default(category: str, path: str, dest_root: str) -> str:
    """Fallback: keep filename, route to the category bucket."""
    folder_name = {
        "image": "Pictures",
        "pdf": "PDFs",
        "archive": "Archives",
        "code": "Code",
        "document": "Documents",
        "other": "Other",
    }.get(category, category.capitalize())
    return os.path.join(dest_root, folder_name, os.path.basename(path))


def _plan_one(path: str, dest_root: str) -> tuple[str, str]:
    cat = _classify(path)
    planner = {
        "audio": _plan_audio,
        "video": _plan_video,
        "book": _plan_book,
        "font": _plan_font,
    }.get(cat)
    target = planner(path, dest_root) if planner else None
    if target is None:
        target = _plan_default(cat, path, dest_root)
    return cat, os.path.normpath(target)


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON Smart Sort dispatcher")
    parser.add_argument("--root", required=True, help="Source folder to scan")
    parser.add_argument("--dest", required=True, help="Destination root for organized output")
    parser.add_argument("--mode", choices=["preview", "apply"], default="preview")
    parser.add_argument("--copy", action="store_true",
                        help="Copy instead of move (apply mode only)")
    parser.add_argument("--max-files", type=int, default=0,
                        help="Stop after N files (0 = unlimited)")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2

    if args.mode == "apply" and not args.dest:
        _emit({"event": "error", "code": "no_dest",
               "message": "--dest is required for apply mode."})
        return 4

    dest_root = os.path.abspath(args.dest) if args.dest else os.path.abspath(args.root)
    src_root = os.path.abspath(args.root)
    if args.mode == "apply" and dest_root.startswith(src_root + os.sep):
        _emit({"event": "error", "code": "dest_inside_src",
               "message": "Destination cannot be inside the source — would recurse forever."})
        return 5

    files = _walk_files(args.root)
    if args.max_files > 0:
        files = files[:args.max_files]
    _emit({"event": "start", "root": args.root, "dest": dest_root,
           "mode": args.mode, "plan_only": args.mode == "preview",
           "files_found": len(files)})

    state = {"scanned": 0, "planned": 0, "moved": 0, "skipped": 0,
             "errors": 0, "last": 0.0}
    by_cat: Counter = Counter()

    for path in files:
        state["scanned"] += 1
        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress",
                   "scanned": state["scanned"],
                   "planned": state["planned"],
                   "moved": state["moved"],
                   "stage": os.path.basename(path)[:200]})

        try:
            category, target = _plan_one(path, dest_root)
            by_cat[category] += 1

            if os.path.abspath(target) == os.path.abspath(path):
                state["skipped"] += 1
                _emit({"event": "item", "path": path, "category": category,
                       "status": "skipped", "new_path": target,
                       "reason": "already in place"})
                continue

            if args.mode == "preview":
                state["planned"] += 1
                _emit({"event": "item", "path": path, "category": category,
                       "status": "planned", "new_path": target})
                continue

            # Apply: ensure unique dest, then move/copy.
            target_unique = _resolve_collision(target)
            os.makedirs(os.path.dirname(target_unique), exist_ok=True)
            if args.copy:
                shutil.copy2(path, target_unique)
            else:
                shutil.move(path, target_unique)
            state["moved"] += 1
            _emit({"event": "item", "path": path, "category": category,
                   "status": "moved", "new_path": target_unique})

        except KeyboardInterrupt:
            _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
            return 130
        except Exception as exc:
            state["errors"] += 1
            _emit({"event": "item", "path": path, "category": "other",
                   "status": "error", "new_path": "",
                   "reason": f"{type(exc).__name__}: {exc}"})

    _emit({"event": "summary", "by_category": dict(by_cat)})
    _emit({"event": "complete",
           "total": state["scanned"],
           "planned": state["planned"],
           "moved": state["moved"],
           "skipped": state["skipped"],
           "errors": state["errors"]})
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
