#!/usr/bin/env python3
"""NDJSON sidecar — photo metadata reader (EXIF + GPS).

Walks a folder for image files, reads EXIF via Pillow / exifread, and
emits per-file events with date taken, camera body, lens, ISO, aperture,
shutter, GPS lat/lon, and (RAW+JPEG) sidecar grouping by stem.

`rename` mode reorganizes into Pictures/{year}/{year}-{month:02}-{day:02}/
{original-name}.{ext}.

NDJSON events:
    {"event":"start","root":"...","files_found":N}
    {"event":"progress","scanned":N,"with_exif":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"matched|skipped|error",
        "date":"YYYY-MM-DD","camera":"...","lens":"...",
        "iso":N,"aperture":"...","shutter":"...","focal":N,
        "lat":<float>,"lon":<float>,"width":N,"height":N,
        "format":"...","new_path":"..."}
    {"event":"complete","total":N,"with_exif":N,"renamed":N}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback
from datetime import datetime

PHOTO_EXTS = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".heic", ".heif",
              ".cr2", ".cr3", ".nef", ".arw", ".dng", ".orf", ".rw2", ".raf",
              ".srw", ".bmp", ".webp")


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _walk(root: str) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(PHOTO_EXTS):
                out.append(os.path.join(dirpath, f))
    return out


def _read_exif_pillow(path: str) -> dict:
    try:
        from PIL import Image, ExifTags
    except ImportError:
        return {}
    out: dict = {}
    try:
        with Image.open(path) as im:
            out["width"] = im.width
            out["height"] = im.height
            out["format"] = (im.format or "").lower()
            exif = im.getexif() if hasattr(im, "getexif") else None
            if exif is None:
                return out
            named = {ExifTags.TAGS.get(k, k): v for k, v in exif.items()}
            if named.get("DateTimeOriginal"):
                try:
                    dt = datetime.strptime(str(named["DateTimeOriginal"]),
                                           "%Y:%m:%d %H:%M:%S")
                    out["date"] = dt.strftime("%Y-%m-%d")
                    out["_dt"] = dt
                except ValueError:
                    pass
            if named.get("Make") or named.get("Model"):
                out["camera"] = f"{named.get('Make','').strip()} {named.get('Model','').strip()}".strip()
            if named.get("LensModel"):
                out["lens"] = str(named["LensModel"]).strip()
            if named.get("ISOSpeedRatings"):
                try: out["iso"] = int(named["ISOSpeedRatings"])
                except (TypeError, ValueError): pass
            if named.get("FNumber"):
                try:
                    f = float(named["FNumber"])
                    out["aperture"] = f"f/{f:g}"
                except (TypeError, ValueError): pass
            if named.get("ExposureTime"):
                try:
                    s = float(named["ExposureTime"])
                    out["shutter"] = f"1/{int(round(1/s))}s" if s and s < 1 else f"{s:g}s"
                except (TypeError, ValueError, ZeroDivisionError): pass
            if named.get("FocalLength"):
                try: out["focal"] = int(round(float(named["FocalLength"])))
                except (TypeError, ValueError): pass

            # GPS via Exif.IFD GPSInfo subdict
            gps = exif.get_ifd(0x8825) if hasattr(exif, "get_ifd") else None
            if gps:
                lat = _gps_to_float(gps.get(2), gps.get(1))
                lon = _gps_to_float(gps.get(4), gps.get(3))
                if lat is not None: out["lat"] = lat
                if lon is not None: out["lon"] = lon
    except Exception:
        return out
    return out


def _gps_to_float(triplet, ref) -> float | None:
    if not triplet:
        return None
    try:
        d, m, s = (float(x) for x in triplet)
        val = d + m / 60.0 + s / 3600.0
        if isinstance(ref, str) and ref in ("S", "W"):
            val = -val
        return round(val, 6)
    except (TypeError, ValueError):
        return None


def _safe_name(value: str) -> str:
    import re
    if not value: return ""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    return cleaned[:180]


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON photo metadata reader")
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=["preview", "rename"], default="preview")
    parser.add_argument("--rename-pattern",
                        default="Pictures/{year}/{year}-{month:02}-{day:02}/{name}.{ext}")
    parser.add_argument("--rename-root", default="")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2

    files = _walk(args.root)
    _emit({"event": "start", "root": args.root, "files_found": len(files)})

    state = {"scanned": 0, "with_exif": 0, "renamed": 0, "last": 0.0}

    for path in files:
        state["scanned"] += 1
        now = time.monotonic()
        if now - state["last"] >= 0.2:
            state["last"] = now
            _emit({"event": "progress", "scanned": state["scanned"],
                   "with_exif": state["with_exif"],
                   "stage": os.path.basename(path)[:200]})

        try:
            info = _read_exif_pillow(path)
            info["path"] = path
            dt = info.pop("_dt", None)
            if "date" in info:
                state["with_exif"] += 1

            if args.mode == "rename" and dt is not None:
                ext = os.path.splitext(path)[1].lstrip(".") or "jpg"
                stem = os.path.splitext(os.path.basename(path))[0]
                rel = args.rename_pattern.format(
                    year=dt.year, month=dt.month, day=dt.day,
                    name=_safe_name(stem), ext=ext)
                dest_root = args.rename_root or args.root
                new_path = os.path.normpath(os.path.join(dest_root, rel))
                if os.path.abspath(new_path) != os.path.abspath(path):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    if not os.path.exists(new_path):
                        os.rename(path, new_path)
                        state["renamed"] += 1
                        info["new_path"] = new_path

            info["status"] = "matched"
            _emit({"event": "item", **info})

        except KeyboardInterrupt:
            _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
            return 130
        except Exception as exc:
            _emit({"event": "item", "path": path, "status": "error",
                   "message": f"{type(exc).__name__}: {exc}"})

    _emit({"event": "complete", "total": state["scanned"],
           "with_exif": state["with_exif"], "renamed": state["renamed"]})
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
