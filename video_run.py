#!/usr/bin/env python3
"""NDJSON sidecar — video filename parser + quality scoring.

Wraps GuessIt (the same parser FileBot, Sonarr, Radarr use under the hood)
to extract `{title, year, season, episode, source, codec, audio_codec,
release_group, type}` from any release name. Adds a Sonarr/Radarr-style
custom-format score so the UI can pick the "keeper" among duplicate
versions of the same media.

Modes:
    preview   — identify only, emit one item event per file.
    rename    — preview + move into a target template path.
    keepers   — group by `(type, title, year, season, episode)`, mark the
                highest-scoring file in each group as `keeper=true`, the
                rest as `keeper=false`.

NDJSON events:
    {"event":"start","root":"...","mode":"...","pattern":"..."}
    {"event":"progress","scanned":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"matched|skipped|error",
        "type":"movie|episode","title":"...","year":<int>,
        "season":<int>,"episode":<int>,"source":"WEBDL|Bluray|...",
        "video_codec":"H.264|H.265|AV1","audio_codec":"DTS|AAC|...",
        "resolution":"1080p|2160p|...","release_group":"...",
        "score":<int>,"keeper":<bool>?,"new_path":"..."?}
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
from collections import defaultdict

VIDEO_EXTS = (".mp4", ".mkv", ".avi", ".mov", ".wmv", ".m4v", ".flv",
              ".webm", ".mpg", ".mpeg", ".ts", ".m2ts", ".vob", ".ogv")


# Sonarr/Radarr-inspired scoring. Numbers are illustrative — tweak in YAML
# later if the UI grows a custom-format editor.
RESOLUTION_SCORE = {
    "2160p": 4000, "4K": 4000, "1080p": 3000,
    "720p": 2000, "576p": 1000, "480p": 800, "360p": 200,
}
SOURCE_SCORE = {
    "Remux": 2000, "Blu-ray": 1500, "BluRay": 1500,
    "WEB-DL": 1300, "WEBDL": 1300, "WEB": 1100, "WEBRip": 900,
    "HDTV": 600, "DVD": 500, "DVDRip": 400, "CAM": -1000,
    "TS": -1000, "TC": -800, "SCR": -500,
}
CODEC_SCORE = {
    "h265": 200, "x265": 200, "HEVC": 200,
    "h264": 100, "x264": 100,
    "AV1": 250, "VP9": 80, "MPEG-4": 0, "XviD": -50, "DivX": -100,
}
AUDIO_SCORE = {
    "TrueHD": 200, "DTS-HD": 180, "DTS-X": 200, "Atmos": 220,
    "DTS": 100, "EAC3": 80, "AC3": 60, "AAC": 40, "MP3": 20, "Vorbis": 20, "FLAC": 100,
}


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _safe_name(value: str) -> str:
    if not value:
        return ""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value))
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:180] or "Unknown"


def _format_path(template: str, fields: dict) -> str:
    safe = {k: _safe_name(str(v)) if isinstance(v, str) else v
            for k, v in fields.items()}
    safe.setdefault("title", "Unknown Title")
    safe.setdefault("year", "0000")
    safe.setdefault("season", 0)
    safe.setdefault("episode", 0)
    safe.setdefault("ext", "mkv")
    try:
        return template.format(**safe)
    except (KeyError, IndexError, ValueError):
        return template


def _walk_video(root: str) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(VIDEO_EXTS):
                out.append(os.path.join(dirpath, f))
    return out


def _parse_one(path: str) -> dict:
    """Run GuessIt over the file's basename and normalize the result."""
    from guessit import guessit
    info = dict(guessit(os.path.basename(path)))

    out: dict = {"path": path}
    out["type"] = info.get("type", "movie")
    out["title"] = str(info.get("title") or "")
    if info.get("year"):
        out["year"] = int(info["year"])
    if info.get("season") is not None:
        s = info["season"]
        out["season"] = int(s if not isinstance(s, list) else s[0])
    if info.get("episode") is not None:
        e = info["episode"]
        out["episode"] = int(e if not isinstance(e, list) else e[0])

    # Format / quality fields. GuessIt uses inconsistent casing.
    for src, dst in (("source", "source"),
                     ("screen_size", "resolution"),
                     ("video_codec", "video_codec"),
                     ("audio_codec", "audio_codec"),
                     ("release_group", "release_group"),
                     ("streaming_service", "streaming_service")):
        v = info.get(src)
        if v:
            out[dst] = (", ".join(map(str, v)) if isinstance(v, list)
                        else str(v))
    return out


def _score(item: dict) -> int:
    score = 0
    res = item.get("resolution") or ""
    score += RESOLUTION_SCORE.get(res, 0)
    src = item.get("source") or ""
    # GuessIt sometimes returns "Web" + streaming_service "Netflix" — treat as WEBDL.
    if src.lower() in ("web", "web-dl", "webdl"):
        score += SOURCE_SCORE["WEB-DL"]
    else:
        score += max((s for k, s in SOURCE_SCORE.items()
                      if k.lower() in src.lower()), default=0)

    vc = (item.get("video_codec") or "").lower()
    score += max((s for k, s in CODEC_SCORE.items() if k.lower() in vc), default=0)
    ac = (item.get("audio_codec") or "")
    for k, s in AUDIO_SCORE.items():
        if k.lower() in ac.lower():
            score += s
            break

    # Tie-breakers: bigger file wins, longer filename wins (more metadata).
    try:
        size = os.path.getsize(item["path"])
        score += min(size // (100 * 1024 * 1024), 50)  # cap at +50 for huge files
    except OSError:
        pass
    return int(score)


def _group_key(item: dict) -> tuple:
    return (
        item.get("type", ""),
        (item.get("title") or "").strip().lower(),
        item.get("year") or 0,
        item.get("season") or 0,
        item.get("episode") or 0,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON video filename parser")
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=["preview", "rename", "keepers"],
                        default="preview")
    parser.add_argument("--rename-pattern", default="",
                        help='e.g. "Movies/{title} ({year})/{title} ({year}).{ext}" or '
                             '"TV/{title}/Season {season:02}/{title} - S{season:02}E{episode:02}.{ext}"')
    parser.add_argument("--rename-root", default="")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root directory does not exist: {args.root}"})
        return 2

    try:
        import guessit  # noqa: F401
    except ImportError:
        _emit({"event": "error", "code": "missing_dep",
               "message": "guessit not installed. Run: pip install -r requirements.txt"})
        return 3

    files = _walk_video(args.root)
    _emit({"event": "start", "root": args.root, "mode": args.mode,
           "pattern": args.rename_pattern, "files_found": len(files)})

    state = {"scanned": 0, "matched": 0, "renamed": 0, "last_progress": 0.0}
    parsed: list[dict] = []

    for path in files:
        state["scanned"] += 1
        now = time.monotonic()
        if now - state["last_progress"] >= 0.2:
            state["last_progress"] = now
            _emit({"event": "progress",
                   "scanned": state["scanned"],
                   "stage": os.path.basename(path)[:200]})
        try:
            item = _parse_one(path)
            item["score"] = _score(item)
            item["status"] = "matched"
            parsed.append(item)
        except Exception as exc:
            _emit({"event": "item", "path": path, "status": "error",
                   "message": f"{type(exc).__name__}: {exc}"})

    if args.mode == "keepers":
        groups: dict[tuple, list[dict]] = defaultdict(list)
        for item in parsed:
            groups[_group_key(item)].append(item)
        for group_items in groups.values():
            group_items.sort(key=lambda x: x.get("score", 0), reverse=True)
            for i, item in enumerate(group_items):
                item["keeper"] = (i == 0)

    for item in parsed:
        if args.mode == "rename" and args.rename_pattern:
            ext = os.path.splitext(item["path"])[1].lstrip(".") or "mkv"
            rel = _format_path(args.rename_pattern, {**item, "ext": ext})
            dest_root = args.rename_root or args.root
            new_path = os.path.normpath(os.path.join(dest_root, rel))
            if os.path.abspath(new_path) != os.path.abspath(item["path"]):
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                if not os.path.exists(new_path):
                    os.rename(item["path"], new_path)
                    state["renamed"] += 1
                    item["new_path"] = new_path
        state["matched"] += 1
        _emit({"event": "item", **item})

    _emit({"event": "complete",
           "total_count": state["scanned"],
           "matched_count": state["matched"],
           "renamed_count": state["renamed"]})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        _emit({"event": "error", "code": "cancelled", "message": "Cancelled by user."})
        raise SystemExit(130)
    except Exception as exc:
        _emit({"event": "error", "code": "crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        raise SystemExit(1)
