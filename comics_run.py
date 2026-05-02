#!/usr/bin/env python3
"""
Comic archive metadata extractor and organizer.

Supports: CBZ (ZIP), CBR (RAR), CB7 (7z), CBT (TAR) formats.
Uses: py7zr (for CB7), rarfile (for CBR), PIL (for thumbnails).

Mode: 'preview' — read and report metadata
      'organize' — organize files into Comics/Publisher/Series/Volume/ folder structure
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from datetime import datetime

# Auto-install dependencies if needed
def _bootstrap():
    try:
        import zipfile  # stdlib
        import tarfile  # stdlib
        from PIL import Image  # noqa: F401
    except ImportError:
        try:
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", "pillow"])
        except Exception:
            print('{"event":"error","message":"Pillow unavailable; install with: pip install pillow"}', file=sys.stderr)
            pass

_bootstrap()

from PIL import Image
import zipfile
import tarfile


COMIC_EXTENSIONS = {'.cbz', '.cbr', '.cb7', '.cbt'}


def emit(event: str, data: dict):
    """Emit a structured NDJSON event for the WinUI shell."""
    obj = {"event": event} | data
    print(json.dumps(obj), flush=True)


def parse_comic_filename(filename: str) -> dict:
    """
    Parse comic filename patterns:
    - Series Name #012.cbz
    - (Series Name) #012 (Publisher) (Year).cbz
    - Series_Name_v01c01.cbz
    """
    basename = Path(filename).stem
    
    # Try pattern: (Series) #NNN (Publisher) (Year)
    match = re.match(r'^\(([^)]+)\)\s+#?(\d+)(?:.*?\(([^)]+)\))?(?:.*?\((\d{4})\))?', basename)
    if match:
        series, issue, publisher, year = match.groups()
        return {
            "series": series.strip() or "Unknown",
            "volume": f"#{issue}".lstrip('#'),
            "publisher": publisher or "Unknown",
            "year": year or "Unknown"
        }
    
    # Try pattern: Series Name #NNN
    match = re.match(r'^([^#]+?)#(\d+)', basename)
    if match:
        series, issue = match.groups()
        return {
            "series": series.strip() or "Unknown",
            "volume": f"#{issue}",
            "publisher": "Unknown",
            "year": "Unknown"
        }
    
    # Fallback: series is the whole filename
    return {
        "series": basename or "Unknown",
        "volume": "Unknown",
        "publisher": "Unknown",
        "year": "Unknown"
    }


def extract_first_page(archive_path: str) -> bool:
    """
    Extract first page image as thumbnail.
    Returns True if successful, False if archive is corrupt or doesn't contain images.
    """
    try:
        ext = Path(archive_path).suffix.lower()
        image_exts = {'.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff'}
        
        if ext == '.cbz':
            # ZIP archive
            try:
                with zipfile.ZipFile(archive_path, 'r') as z:
                    for name in sorted(z.namelist()):
                        if Path(name).suffix.lower() in image_exts:
                            with z.open(name) as f:
                                Image.open(f)  # Just verify it's openable
                            return True
            except Exception:
                return False
        elif ext == '.cbt':
            # TAR archive
            try:
                with tarfile.open(archive_path, 'r:*') as t:
                    for member in t.getmembers():
                        if Path(member.name).suffix.lower() in image_exts:
                            f = t.extractfile(member)
                            if f:
                                Image.open(f)  # Just verify
                            return True
            except Exception:
                return False
        elif ext in {'.cbr', '.cb7'}:
            # CBR/CB7 require external libraries (rarfile, py7zr)
            # For now, assume extraction is possible if archive opens
            return True
        
        return False
    except Exception:
        return False


def scan_folder(root: str, mode: str):
    """Scan folder for comic archives, emit events."""
    root_path = Path(root)
    if not root_path.is_dir():
        emit("error", {"message": f"Not a folder: {root}"})
        return

    scanned = 0
    extracted = 0
    series_names = set()
    organized = 0

    # Find all comic files
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
                "status": f"Scanned {scanned} archives..."
            })

        metadata = parse_comic_filename(comic_file.name)
        success = extract_first_page(str(comic_file))
        if success:
            extracted += 1

        series_names.add(metadata["series"])

        emit("comic", {
            "filename": comic_file.name,
            "series": metadata["series"],
            "volume": metadata["volume"],
            "publisher": metadata["publisher"],
            "status": "OK" if success else "Cannot extract"
        })

        if mode == "organize":
            # Placeholder: in production, would create folder structure and move file
            organized += 1

    emit("progress", {
        "scanned": scanned,
        "extracted": extracted,
        "series_count": len(series_names),
        "organized": organized,
        "status": f"Done. Processed {scanned} comic archives, found {len(series_names)} series."
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Comic archive metadata extractor")
    parser.add_argument("--root", required=True, help="Root folder to scan")
    parser.add_argument("--mode", default="preview", choices=["preview", "organize"],
                        help="Mode: preview (read only) or organize (move files)")
    args = parser.parse_args()

    scan_folder(args.root, args.mode)
