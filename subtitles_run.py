#!/usr/bin/env python3
"""NDJSON sidecar — Subliminal-based subtitle auto-fetcher.

Walks a folder for video files, skips ones with embedded subs (via
enzyme), then asks Subliminal for `.srt` matches per requested language.
Best match (by Subliminal's score) is downloaded next to the video.

NDJSON events:
    {"event":"start","root":"...","languages":["..."]}
    {"event":"progress","scanned":N,"downloaded":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"downloaded|skipped|no_match|embedded|error",
        "language":"...","provider":"...","sub_path":"..."?,"score":<int>?}
    {"event":"complete","total_count":N,"downloaded_count":N}
    {"event":"error","code":"...","message":"..."}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import traceback

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv",
              ".webm", ".mpg", ".mpeg", ".ts", ".m2ts")


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _has_embedded(path: str) -> bool:
    try:
        from enzyme import MKV
        if path.lower().endswith(".mkv"):
            with open(path, "rb") as f:
                mkv = MKV(f)
            return bool(mkv.subtitle_tracks)
    except Exception:
        pass
    # For non-MKV containers we trust the user — checking embedded subs
    # in MP4/MOV requires ffprobe, which we don't ship.
    return False


def _walk_video(root: str) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(VIDEO_EXTS):
                out.append(os.path.join(dirpath, f))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON subtitle auto-fetcher")
    parser.add_argument("--root", required=True)
    parser.add_argument("--languages", default="en",
                        help="Comma-separated ISO 639 codes, e.g. en,es,fr")
    parser.add_argument("--min-score", type=int, default=50,
                        help="Subliminal score threshold (0-100+; 50 = decent)")
    parser.add_argument("--skip-embedded", action="store_true", default=True)
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root not found: {args.root}"})
        return 2

    try:
        from babelfish import Language
        from subliminal import (Video, region, download_best_subtitles,
                                save_subtitles, scan_video)
    except ImportError as exc:
        _emit({"event": "error", "code": "missing_dep",
               "message": f"subliminal/babelfish not installed: {exc}"})
        return 3

    # Subliminal needs a cache region. Use an in-memory dogpile backend so we
    # don't pollute the user's filesystem with .dbm files.
    if not region.is_configured:
        region.configure("dogpile.cache.memory")

    def _parse_lang(code: str):
        code = code.strip()
        if not code:
            return None
        # Try IETF (en, fr, pt-BR), then 3-letter ISO 639-3 (eng, fra, por).
        try:
            return Language.fromietf(code)
        except Exception:
            pass
        try:
            return Language(code)
        except Exception:
            return None

    languages = {l for l in (_parse_lang(c) for c in args.languages.split(","))
                 if l is not None}
    if not languages:
        _emit({"event": "error", "code": "bad_languages",
               "message": "No languages specified."})
        return 4

    files = _walk_video(args.root)
    _emit({"event": "start", "root": args.root,
           "languages": sorted(str(l) for l in languages),
           "files_found": len(files)})

    state = {"scanned": 0, "downloaded": 0, "last_progress": 0.0}

    for path in files:
        state["scanned"] += 1
        now = time.monotonic()
        if now - state["last_progress"] >= 0.2:
            state["last_progress"] = now
            _emit({"event": "progress",
                   "scanned": state["scanned"],
                   "downloaded": state["downloaded"],
                   "stage": os.path.basename(path)[:200]})

        try:
            if args.skip_embedded and _has_embedded(path):
                _emit({"event": "item", "path": path, "status": "embedded"})
                continue

            try:
                video = scan_video(path)
            except Exception:
                # scan_video parses the filename; fall back to a bare Video.
                video = Video.fromname(os.path.basename(path))

            subs = download_best_subtitles({video}, languages,
                                           min_score=args.min_score) or {}
            picks = subs.get(video, [])
            if not picks:
                _emit({"event": "item", "path": path, "status": "no_match"})
                continue

            saved = save_subtitles(video, picks, single=False,
                                   directory=os.path.dirname(path))
            for s in saved:
                _emit({"event": "item", "path": path, "status": "downloaded",
                       "language": str(s.language),
                       "provider": s.provider_name,
                       "score": getattr(s, "score", None),
                       "sub_path": os.path.join(
                           os.path.dirname(path),
                           f"{os.path.splitext(os.path.basename(path))[0]}.{s.language}.srt")})
                state["downloaded"] += 1

        except KeyboardInterrupt:
            _emit({"event": "error", "code": "cancelled", "message": "Cancelled."})
            return 130
        except Exception as exc:
            _emit({"event": "item", "path": path, "status": "error",
                   "message": f"{type(exc).__name__}: {exc}"})

    _emit({"event": "complete",
           "total_count": state["scanned"],
           "downloaded_count": state["downloaded"]})
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
