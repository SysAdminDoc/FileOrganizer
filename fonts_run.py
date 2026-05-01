#!/usr/bin/env python3
"""NDJSON sidecar — font metadata reader (TTF/OTF/WOFF/WOFF2).

Uses fonttools to read the OS/2 + name tables. Reports family name,
subfamily (style), foundry, designer, version, weight class, and
italic/monospace flags. Optional rename mode reorganizes into
`Fonts/{family}/{family} - {style}.{ext}`.

NDJSON events:
    {"event":"start","root":"..."}
    {"event":"progress","scanned":N,"matched":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"matched|skipped|error",
        "family":"...","style":"...","weight":N,"italic":<bool>,
        "monospace":<bool>,"version":"...","designer":"...",
        "foundry":"...","format":"ttf|otf|woff|woff2|ttc",
        "new_path":"..."?}
    {"event":"complete","total_count":N,"matched_count":N,"renamed_count":N}
    {"event":"error","code":"...","message":"..."}
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback

FONT_EXTS = (".ttf", ".otf", ".woff", ".woff2", ".ttc", ".otc")

# Name table IDs (per the OpenType spec).
NID_COPYRIGHT = 0
NID_FAMILY = 1
NID_SUBFAMILY = 2
NID_FULL = 4
NID_VERSION = 5
NID_DESIGNER = 9
NID_VENDOR_URL = 11
NID_DESIGNER_URL = 12
NID_FOUNDRY = 8
NID_PREFERRED_FAMILY = 16
NID_PREFERRED_SUBFAMILY = 17


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _safe_name(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:180]


def _walk_fonts(root: str) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(FONT_EXTS):
                out.append(os.path.join(dirpath, f))
    return out


def _read_name(name_table, nid: int) -> str:
    """Pick the best string for a given name ID (prefer Mac/Eng, then Win/Eng)."""
    record = (name_table.getName(nid, 3, 1, 0x409)  # Windows / Unicode BMP / English-US
              or name_table.getName(nid, 1, 0, 0)   # Mac Roman / English
              or name_table.getName(nid, 0, 0, 0))  # Unicode 1.0
    if record is None:
        return ""
    try:
        return str(record).strip()
    except Exception:
        return ""


def _read_font(path: str) -> dict:
    from fontTools.ttLib import TTFont, TTLibError

    out: dict = {"format": os.path.splitext(path)[1].lstrip(".").lower()}
    try:
        # fontNumber=0 covers TTC/OTC by reading just the first face.
        font = TTFont(path, lazy=True, fontNumber=0,
                      ignoreDecompileErrors=True, recalcBBoxes=False,
                      recalcTimestamp=False)
    except TTLibError as exc:
        raise RuntimeError(f"fontTools cannot open: {exc}") from exc

    try:
        name = font["name"]
        out["family"] = (_read_name(name, NID_PREFERRED_FAMILY)
                         or _read_name(name, NID_FAMILY))
        out["style"] = (_read_name(name, NID_PREFERRED_SUBFAMILY)
                        or _read_name(name, NID_SUBFAMILY)
                        or "Regular")
        full = _read_name(name, NID_FULL)
        if full and not out["family"]:
            out["family"] = full
        out["version"] = _read_name(name, NID_VERSION)
        out["designer"] = _read_name(name, NID_DESIGNER)
        out["foundry"] = _read_name(name, NID_FOUNDRY)

        if "OS/2" in font:
            os2 = font["OS/2"]
            out["weight"] = getattr(os2, "usWeightClass", 400)
            # fsSelection bit 0 = italic, 5 = bold; isFixedPitch (post.isFixedPitch) = monospace
            try:
                out["italic"] = bool(getattr(os2, "fsSelection", 0) & 0x01)
            except Exception:
                out["italic"] = False
        if "post" in font:
            try:
                out["monospace"] = bool(getattr(font["post"], "isFixedPitch", 0))
            except Exception:
                pass
    finally:
        font.close()

    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON font metadata reader")
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=["preview", "rename"], default="preview")
    parser.add_argument("--rename-pattern",
                        default="Fonts/{family}/{family} - {style}.{ext}")
    parser.add_argument("--rename-root", default="")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2

    try:
        from fontTools.ttLib import TTFont  # noqa: F401
    except ImportError:
        _emit({"event": "error", "code": "missing_dep",
               "message": "fonttools not installed. Run: pip install -r requirements.txt"})
        return 3

    files = _walk_fonts(args.root)
    _emit({"event": "start", "root": args.root, "files_found": len(files)})

    state = {"scanned": 0, "matched": 0, "renamed": 0, "last_progress": 0.0}

    for path in files:
        state["scanned"] += 1
        now = time.monotonic()
        if now - state["last_progress"] >= 0.2:
            state["last_progress"] = now
            _emit({"event": "progress",
                   "scanned": state["scanned"],
                   "matched": state["matched"],
                   "stage": os.path.basename(path)[:200]})
        try:
            info = _read_font(path)
            info["path"] = path

            if not info.get("family"):
                info["status"] = "skipped"
                _emit({"event": "item", **info})
                continue

            new_path = None
            if args.mode == "rename":
                ext = info.get("format") or "ttf"
                rel = args.rename_pattern.format(
                    family=_safe_name(info.get("family", "Unknown")) or "Unknown",
                    style=_safe_name(info.get("style", "Regular")) or "Regular",
                    weight=info.get("weight", 400),
                    ext=ext)
                dest_root = args.rename_root or args.root
                new_path = os.path.normpath(os.path.join(dest_root, rel))
                if os.path.abspath(new_path) != os.path.abspath(path):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    if not os.path.exists(new_path):
                        os.rename(path, new_path)
                        state["renamed"] += 1
                        info["new_path"] = new_path

            info["status"] = "matched"
            state["matched"] += 1
            _emit({"event": "item", **info})

        except KeyboardInterrupt:
            _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
            return 130
        except Exception as exc:
            _emit({"event": "item", "path": path, "status": "error",
                   "message": f"{type(exc).__name__}: {exc}"})

    _emit({"event": "complete",
           "total_count": state["scanned"],
           "matched_count": state["matched"],
           "renamed_count": state["renamed"]})
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
