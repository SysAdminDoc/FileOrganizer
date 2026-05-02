"""
Broken file detection — N-14.

Reads file headers / containers without unpacking them and reports whether
the file is corrupt, truncated, or otherwise unreadable. Integrates with:

  - asset_db.asset_files.broken (schema migration in init_db)
  - build_source_index.py --check-broken (opt-in slow scan)
  - PreflightDialog "Broken files (N)" section (planned, separate task)

Each check returns ``(is_broken: bool, reason: str)``. ``reason`` is empty
when the file is healthy. When the matching dependency isn't installed the
check returns ``(False, "")`` — never blocks a healthy file just because we
can't verify it.

The thin module surface is deliberate: extractors and the CLI go through
``is_broken(path)`` so a caller never has to remember the per-extension
dispatch.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Optional


# 20 MB cap per spec — verifying gigantic images on Windows can stall the
# UI thread and gives no useful signal beyond "container parses".
MAX_IMAGE_VERIFY_BYTES = 20 * 1024 * 1024

_HAS_PILLOW = importlib.util.find_spec("PIL") is not None
_HAS_RARFILE = importlib.util.find_spec("rarfile") is not None
_HAS_PY7ZR = importlib.util.find_spec("py7zr") is not None
_FFPROBE = shutil.which("ffprobe")


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tiff", ".tif",
               ".webp", ".heic", ".avif"}
_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mxf",
               ".flv", ".wmv"}
_ARCHIVE_EXTS = {".zip", ".rar", ".7z"}


# ── Image ────────────────────────────────────────────────────────────────


def check_image(path: Path) -> tuple[bool, str]:
    """PIL.Image.verify() without consuming the handle for later callers."""
    if not _HAS_PILLOW:
        return False, ""
    if not path or not path.exists() or not path.is_file():
        return True, "missing"
    try:
        size = path.stat().st_size
    except OSError as exc:
        return True, f"stat failed: {exc}"
    if size > MAX_IMAGE_VERIFY_BYTES:
        # Skip oversize — no useful broken-vs-OK signal at this depth.
        return False, ""
    try:
        from PIL import Image  # type: ignore
        try:
            from PIL import UnidentifiedImageError  # type: ignore
        except ImportError:
            UnidentifiedImageError = Exception  # type: ignore[assignment]
    except Exception:
        return False, ""
    try:
        with Image.open(str(path)) as im:
            # verify() consumes the file pointer so the handle MUST be
            # closed and never re-used. The context manager does that.
            im.verify()
        return False, ""
    except UnidentifiedImageError as exc:
        return True, f"unidentified image: {exc}"
    except (OSError, ValueError) as exc:
        return True, f"image verify failed: {exc}"
    except Exception as exc:
        # PIL can raise DecompressionBombError, SyntaxError, etc.
        return True, f"image verify failed: {exc.__class__.__name__}: {exc}"


# ── Video ────────────────────────────────────────────────────────────────


def check_video(path: Path) -> tuple[bool, str]:
    """ffprobe -show_error; broken iff returncode!=0 or 'error' in JSON."""
    if _FFPROBE is None:
        return False, ""
    if not path or not path.exists() or not path.is_file():
        return True, "missing"
    try:
        proc = subprocess.run(
            [
                _FFPROBE, "-v", "error",
                "-show_error",
                "-print_format", "json",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except subprocess.TimeoutExpired:
        return True, "ffprobe timeout"
    except OSError as exc:
        return False, f"ffprobe spawn failed: {exc}"
    if proc.returncode != 0:
        return True, f"ffprobe rc={proc.returncode}: {(proc.stderr or '').strip()[:200]}"
    # ffprobe sometimes returns rc=0 but writes diagnostics to stderr (truncated
    # streams, missing moov atoms, etc.). Per the N-14 rubric, treat any non-empty
    # stderr as a broken signal even when the JSON parses cleanly.
    stderr_text = (proc.stderr or "").strip()
    if stderr_text:
        return True, f"ffprobe stderr: {stderr_text[:200]}"
    if proc.stdout:
        try:
            data = json.loads(proc.stdout)
        except json.JSONDecodeError:
            data = {}
        if "error" in data:
            err = data["error"]
            if isinstance(err, dict):
                return True, str(err.get("string") or err.get("code") or err)
            return True, str(err)
    return False, ""


# ── Archive ──────────────────────────────────────────────────────────────


def check_archive(path: Path) -> tuple[bool, str]:
    """zipfile / rarfile / py7zr per-format integrity check."""
    if not path or not path.exists() or not path.is_file():
        return True, "missing"
    ext = path.suffix.lower()

    if ext == ".zip":
        try:
            with zipfile.ZipFile(str(path)) as z:
                bad = z.testzip()
                if bad is not None:
                    return True, f"zip testzip failed on entry: {bad}"
            return False, ""
        except zipfile.BadZipFile as exc:
            return True, f"bad zip: {exc}"
        except Exception as exc:
            return True, f"zip check failed: {exc.__class__.__name__}: {exc}"

    if ext == ".rar":
        if not _HAS_RARFILE:
            return False, ""
        try:
            import rarfile  # type: ignore
            with rarfile.RarFile(str(path)) as r:
                bad = r.testrar()
                if bad is not None:
                    return True, f"rar testrar failed: {bad}"
            return False, ""
        except Exception as exc:  # rarfile raises a wide hierarchy
            return True, f"rar check failed: {exc.__class__.__name__}: {exc}"

    if ext == ".7z":
        if not _HAS_PY7ZR:
            return False, ""
        try:
            import py7zr  # type: ignore
            with py7zr.SevenZipFile(str(path)) as sz:
                bad = sz.testzip()
                if bad:
                    return True, f"7z testzip failed: {bad}"
            return False, ""
        except Exception as exc:  # py7zr.exceptions.* hierarchy
            return True, f"7z check failed: {exc.__class__.__name__}: {exc}"

    return False, ""


# ── Dispatcher ───────────────────────────────────────────────────────────


def is_broken(path: Path) -> tuple[bool, str]:
    """Dispatch a path to the matching check based on its extension.

    Returns ``(False, "")`` for any extension we don't recognise — N-14 only
    flags broken files we can verify, never guesses.
    """
    if not path:
        return False, ""
    ext = path.suffix.lower()
    if ext in _IMAGE_EXTS:
        return check_image(path)
    if ext in _VIDEO_EXTS:
        return check_video(path)
    if ext in _ARCHIVE_EXTS:
        return check_archive(path)
    return False, ""


# ── CLI ──────────────────────────────────────────────────────────────────


def _cli_scan(root: Path, max_files: Optional[int] = None) -> int:
    """Walk a directory and print one BROKEN line per detected file."""
    if not root.exists():
        print(f"ERROR: {root} not found", file=sys.stderr)
        return 2
    found = 0
    checked = 0
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        ext = path.suffix.lower()
        if ext not in _IMAGE_EXTS and ext not in _VIDEO_EXTS and ext not in _ARCHIVE_EXTS:
            continue
        broken, reason = is_broken(path)
        checked += 1
        if broken:
            found += 1
            print(f"BROKEN  {path}  -- {reason}")
        if max_files and checked >= max_files:
            break
    print(f"checked={checked}  broken={found}")
    return 1 if found else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Detect corrupt images, videos, and archives in a directory.",
    )
    ap.add_argument("--scan", required=True,
                    help="Directory to walk recursively.")
    ap.add_argument("--max-files", type=int, default=0,
                    help="Stop after checking N files (default: unlimited).")
    args = ap.parse_args()
    return _cli_scan(Path(args.scan), max_files=args.max_files or None)


if __name__ == "__main__":
    sys.exit(main())
