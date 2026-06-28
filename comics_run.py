#!/usr/bin/env python3
"""Comic archive metadata extractor and dry-run organizer sidecar."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tarfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fileorganizer.safe_archive import UnsafeArchiveEntryError, safe_extract_path


COMIC_EXTENSIONS = {'.cbz', '.cbr', '.cb7', '.cbt'}
IMAGE_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'}
PLAN_SCHEMA_VERSION = 1
_SAFE_CHECK_ROOT = os.path.join(os.getcwd(), "__comic_archive_safety_root__")


def emit(event: str, data: dict[str, Any]) -> None:
    """Emit a structured NDJSON event for the WinUI shell."""
    obj = {"event": event} | data
    print(json.dumps(obj, ensure_ascii=False), flush=True)


def _load_pillow_image():
    try:
        from PIL import Image  # type: ignore
        return Image
    except ImportError:
        return None


def _load_rarfile():
    try:
        import rarfile  # type: ignore
        return rarfile
    except ImportError:
        return None


def _load_py7zr():
    try:
        import py7zr  # type: ignore
        return py7zr
    except ImportError:
        return None


def _safe_segment(value: str, fallback: str) -> str:
    text = re.sub(r'[<>:"/\\|?*]+', "_", (value or "").strip())
    text = re.sub(r"\s+", "_", text).strip("._ ")
    return text[:100] or fallback


def parse_comic_filename(filename: str) -> dict[str, str]:
    """
    Parse common comic filename patterns:
    - Series Name #012 (Publisher) (2024).cbz
    - (Series Name) #012 (Publisher) (2024).cbz
    - Series_Name_v01c01.cbz
    """
    basename = Path(filename).stem.strip()

    match = re.match(
        r'^\((?P<series>[^)]+)\)\s+#?(?P<issue>\d+)'
        r'(?:.*?\((?P<publisher>[^)0-9][^)]+)\))?'
        r'(?:.*?\((?P<year>\d{4})\))?',
        basename,
    )
    if match:
        groups = match.groupdict()
        return {
            "series": (groups.get("series") or "Unknown").strip(),
            "volume": f"#{groups.get('issue') or 'Unknown'}",
            "publisher": (groups.get("publisher") or "Unknown").strip(),
            "year": groups.get("year") or "Unknown",
        }

    match = re.match(
        r'^(?P<series>.+?)\s+#(?P<issue>\d+)'
        r'(?:\s+\((?P<publisher>[^)0-9][^)]+)\))?'
        r'(?:\s+\((?P<year>\d{4})\))?',
        basename,
    )
    if match:
        groups = match.groupdict()
        return {
            "series": (groups.get("series") or "Unknown").strip(),
            "volume": f"#{groups.get('issue') or 'Unknown'}",
            "publisher": (groups.get("publisher") or "Unknown").strip(),
            "year": groups.get("year") or "Unknown",
        }

    match = re.match(r'^(?P<series>.+?)[\s_.-]+v(?P<volume>\d+)(?:c(?P<issue>\d+))?', basename, re.I)
    if match:
        groups = match.groupdict()
        issue = groups.get("issue")
        return {
            "series": (groups.get("series") or "Unknown").replace("_", " ").strip(),
            "volume": f"v{groups.get('volume')}" + (f"c{issue}" if issue else ""),
            "publisher": "Unknown",
            "year": "Unknown",
        }

    return {
        "series": basename or "Unknown",
        "volume": "Unknown",
        "publisher": "Unknown",
        "year": "Unknown",
    }


def _validate_entry_name(name: str) -> None:
    safe_extract_path(_SAFE_CHECK_ROOT, name)


def _verify_image_stream(stream, image_module) -> bool:
    try:
        with image_module.open(stream) as img:
            img.verify()
        return True
    except Exception:
        return False


def _inspect_zip(path: Path, image_module) -> dict[str, Any]:
    try:
        with zipfile.ZipFile(path, "r") as zf:
            bad = zf.testzip()
            if bad:
                return {"ok": False, "status": f"Corrupt member: {bad}", "pages": 0, "first_page": ""}
            pages = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                _validate_entry_name(info.filename)
                if Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS:
                    pages.append(info.filename)
            if not pages:
                return {"ok": False, "status": "No image pages found", "pages": 0, "first_page": ""}
            first = sorted(pages)[0]
            with zf.open(first) as stream:
                if not _verify_image_stream(stream, image_module):
                    return {"ok": False, "status": f"Unreadable first page: {first}", "pages": len(pages), "first_page": first}
            return {"ok": True, "status": "OK", "pages": len(pages), "first_page": first}
    except UnsafeArchiveEntryError as e:
        return {"ok": False, "status": f"Unsafe archive entry: {e}", "pages": 0, "first_page": ""}
    except Exception as e:
        return {"ok": False, "status": f"Corrupt archive: {type(e).__name__}", "pages": 0, "first_page": ""}


def _inspect_tar(path: Path, image_module) -> dict[str, Any]:
    try:
        with tarfile.open(path, "r:*") as tf:
            pages = []
            members = tf.getmembers()
            for member in members:
                if member.isdir():
                    continue
                if not member.isfile():
                    return {"ok": False, "status": f"Unsafe non-file member: {member.name}", "pages": 0, "first_page": ""}
                _validate_entry_name(member.name)
                if Path(member.name).suffix.lower() in IMAGE_EXTENSIONS:
                    pages.append(member)
            if not pages:
                return {"ok": False, "status": "No image pages found", "pages": 0, "first_page": ""}
            first = sorted(pages, key=lambda m: m.name)[0]
            stream = tf.extractfile(first)
            if stream is None or not _verify_image_stream(stream, image_module):
                return {"ok": False, "status": f"Unreadable first page: {first.name}", "pages": len(pages), "first_page": first.name}
            return {"ok": True, "status": "OK", "pages": len(pages), "first_page": first.name}
    except UnsafeArchiveEntryError as e:
        return {"ok": False, "status": f"Unsafe archive entry: {e}", "pages": 0, "first_page": ""}
    except Exception as e:
        return {"ok": False, "status": f"Corrupt archive: {type(e).__name__}", "pages": 0, "first_page": ""}


def _inspect_rar(path: Path, image_module) -> dict[str, Any]:
    rarfile = _load_rarfile()
    if rarfile is None:
        return {"ok": False, "status": "Missing dependency: rarfile", "pages": 0, "first_page": ""}
    try:
        with rarfile.RarFile(str(path)) as rf:
            pages = []
            for info in rf.infolist():
                is_dir = info.isdir() if hasattr(info, "isdir") else str(info.filename).endswith("/")
                if is_dir:
                    continue
                _validate_entry_name(info.filename)
                if Path(info.filename).suffix.lower() in IMAGE_EXTENSIONS:
                    pages.append(info)
            if not pages:
                return {"ok": False, "status": "No image pages found", "pages": 0, "first_page": ""}
            first = sorted(pages, key=lambda i: i.filename)[0]
            with rf.open(first) as stream:
                if not _verify_image_stream(stream, image_module):
                    return {"ok": False, "status": f"Unreadable first page: {first.filename}", "pages": len(pages), "first_page": first.filename}
            return {"ok": True, "status": "OK", "pages": len(pages), "first_page": first.filename}
    except UnsafeArchiveEntryError as e:
        return {"ok": False, "status": f"Unsafe archive entry: {e}", "pages": 0, "first_page": ""}
    except Exception as e:
        return {"ok": False, "status": f"Corrupt archive: {type(e).__name__}", "pages": 0, "first_page": ""}


def _inspect_7z(path: Path) -> dict[str, Any]:
    py7zr = _load_py7zr()
    if py7zr is None:
        return {"ok": False, "status": "Missing dependency: py7zr", "pages": 0, "first_page": ""}
    try:
        with py7zr.SevenZipFile(str(path), "r") as archive:
            names = archive.getnames()
            pages = []
            for name in names:
                if name.endswith("/"):
                    continue
                _validate_entry_name(name)
                if Path(name).suffix.lower() in IMAGE_EXTENSIONS:
                    pages.append(name)
            bad = archive.testzip() if hasattr(archive, "testzip") else None
            if bad:
                return {"ok": False, "status": f"Corrupt member: {bad}", "pages": len(pages), "first_page": ""}
            tested = archive.test() if hasattr(archive, "test") else True
            if tested is False:
                return {"ok": False, "status": "Corrupt archive: integrity test failed", "pages": len(pages), "first_page": ""}
            if not pages:
                return {"ok": False, "status": "No image pages found", "pages": 0, "first_page": ""}
            first = sorted(pages)[0]
            return {"ok": True, "status": "OK", "pages": len(pages), "first_page": first}
    except UnsafeArchiveEntryError as e:
        return {"ok": False, "status": f"Unsafe archive entry: {e}", "pages": 0, "first_page": ""}
    except Exception as e:
        return {"ok": False, "status": f"Corrupt archive: {type(e).__name__}", "pages": 0, "first_page": ""}


def inspect_comic_archive(archive_path: str, image_module=None) -> dict[str, Any]:
    image_module = image_module or _load_pillow_image()
    if image_module is None:
        return {"ok": False, "status": "Missing dependency: Pillow", "pages": 0, "first_page": ""}

    path = Path(archive_path)
    ext = path.suffix.lower()
    if ext == ".cbz":
        return _inspect_zip(path, image_module)
    if ext == ".cbt":
        return _inspect_tar(path, image_module)
    if ext == ".cbr":
        return _inspect_rar(path, image_module)
    if ext == ".cb7":
        return _inspect_7z(path)
    return {"ok": False, "status": f"Unsupported comic archive: {ext}", "pages": 0, "first_page": ""}


def planned_destination(comic_file: Path, metadata: dict[str, str], dest_root: Path) -> Path:
    publisher = _safe_segment(metadata.get("publisher", ""), "Unknown")
    series = _safe_segment(metadata.get("series", ""), "Unknown")
    return dest_root / "Comics" / publisher / series / comic_file.name


def write_plan(plan: dict[str, Any], path: str = "") -> str:
    out = Path(path) if path else Path(plan["root"]) / "comic_organize_plan.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(out)


def _move_file(src: Path, dest: Path) -> str:
    if dest.exists():
        return "blocked: destination exists"
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.rename(src, dest)
    except OSError:
        shutil.move(str(src), str(dest))
    return "moved"


def scan_folder(
    root: str,
    mode: str,
    dest_root: str = "",
    plan_out: str = "",
    apply: bool = False,
    image_module=None,
) -> int:
    """Scan folder for comic archives, emit events, and optionally apply a plan."""
    root_path = Path(root)
    if not root_path.is_dir():
        emit("error", {"code": "invalid_root", "message": f"Not a folder: {root}"})
        return 2

    image_module = image_module or _load_pillow_image()
    if image_module is None:
        emit("error", {"code": "missing_dependency", "message": "Pillow is required for comic page validation; install with: pip install pillow"})
        return 2

    destination_root = Path(dest_root) if dest_root else root_path
    scanned = 0
    extracted = 0
    series_names = set()
    organized = 0
    plan_items: list[dict[str, Any]] = []

    comic_files = []
    for ext in COMIC_EXTENSIONS:
        comic_files.extend(root_path.rglob(f"*{ext}"))
        comic_files.extend(root_path.rglob(f"*{ext.upper()}"))

    for comic_file in sorted(set(comic_files)):
        scanned += 1
        if scanned % 10 == 0:
            emit("progress", {
                "scanned": scanned,
                "extracted": extracted,
                "series_count": len(series_names),
                "organized": organized,
                "status": f"Scanned {scanned} archives...",
            })

        metadata = parse_comic_filename(comic_file.name)
        inspection = inspect_comic_archive(str(comic_file), image_module=image_module)
        if inspection["ok"]:
            extracted += 1

        series_names.add(metadata["series"])
        dest = planned_destination(comic_file, metadata, destination_root)
        item_status = inspection["status"]

        if mode == "organize":
            if inspection["ok"]:
                item_status = _move_file(comic_file, dest) if apply else "planned"
                organized += 1 if item_status in {"planned", "moved"} else 0
            else:
                item_status = f"blocked: {inspection['status']}"
            plan_items.append({
                "source": str(comic_file),
                "destination": str(dest),
                "series": metadata["series"],
                "volume": metadata["volume"],
                "publisher": metadata["publisher"],
                "year": metadata["year"],
                "pages": inspection["pages"],
                "first_page": inspection["first_page"],
                "status": item_status,
            })

        emit("comic", {
            "filename": comic_file.name,
            "path": str(comic_file),
            "series": metadata["series"],
            "volume": metadata["volume"],
            "publisher": metadata["publisher"],
            "year": metadata["year"],
            "pages": inspection["pages"],
            "first_page": inspection["first_page"],
            "destination": str(dest) if mode == "organize" else "",
            "status": item_status,
        })

    if mode == "organize":
        plan = {
            "schema_version": PLAN_SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "root": str(root_path),
            "dest_root": str(destination_root),
            "dry_run": not apply,
            "item_count": len(plan_items),
            "items": plan_items,
        }
        plan_path = write_plan(plan, plan_out)
        emit("plan", {"path": plan_path, "items": len(plan_items), "dry_run": not apply})

    emit("progress", {
        "scanned": scanned,
        "extracted": extracted,
        "series_count": len(series_names),
        "organized": organized,
        "status": f"Done. Processed {scanned} comic archives, found {len(series_names)} series.",
    })
    emit("complete", {"total": scanned, "extracted": extracted, "series_count": len(series_names), "organized": organized})
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Comic archive metadata extractor")
    parser.add_argument("--root", required=True, help="Root folder to scan")
    parser.add_argument("--mode", default="preview", choices=["preview", "organize"],
                        help="Mode: preview (read only) or organize (write a plan)")
    parser.add_argument("--dest-root", help="Destination root for organize plans")
    parser.add_argument("--plan-out", help="Write organize plan to this JSON path")
    parser.add_argument("--apply", action="store_true", help="Apply the generated organize plan")
    args = parser.parse_args(argv)

    return scan_folder(
        args.root,
        args.mode,
        dest_root=args.dest_root or "",
        plan_out=args.plan_out or "",
        apply=args.apply,
    )


if __name__ == "__main__":
    sys.exit(main())
