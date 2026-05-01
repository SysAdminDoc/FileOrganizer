#!/usr/bin/env python3
"""NDJSON sidecar — Picard-style audio tagger.

Pipeline (per file):
    1. Read existing tags via mutagen (cheap baseline).
    2. Text-search MusicBrainz with `artist + album + title` from existing
       tags; rank by RapidFuzz similarity. Score >= 90 takes the match.
    3. If text match fails, run Chromaprint (fpcalc) to produce a 22 s
       acoustic fingerprint, query AcoustID for `(score, mbid, ...)` tuples,
       cross-check the top hit against MusicBrainz for canonical metadata.
    4. (--mode tag) write ID3/Vorbis/MP4 tags via mutagen.
    5. (--rename pattern) move the file into a beets-style template path
       like `Music/{albumartist}/{year} - {album}/{disc:02}-{track:02} {title}.{ext}`.

NDJSON events:
    {"event":"start","root":"...","mode":"...","pattern":"..."}
    {"event":"progress","scanned":N,"matched":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"matched|skipped|untagged|error",
        "match_type":"existing|text|fingerprint","score":<float>,
        "title":"...","artist":"...","album":"...","year":<int>,
        "track":<int>,"disc":<int>,"mbid":"...","new_path":"..."?}
    {"event":"complete","total_count":N,"matched_count":N,"renamed_count":N}
    {"event":"error","code":"...","message":"..."}

Driven from FileOrganizer.UI's MusicPage via PythonRunner.RunScriptNdjsonAsync.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
import traceback
from typing import Any

AUDIO_EXTS = (".mp3", ".m4a", ".mp4", ".aac", ".flac", ".ogg", ".oga",
              ".opus", ".wav", ".wma", ".alac", ".aiff", ".ape")

USER_AGENT = ("FileOrganizer", "0.3.0", "https://github.com/SysAdminDoc/FileOrganizer")


def _emit(obj: dict) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _safe_name(value: str) -> str:
    """Strip path-illegal characters (Windows superset)."""
    if not value:
        return ""
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", value)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return cleaned[:180] or "Unknown"


def _format_path(template: str, fields: dict) -> str:
    """Expand a beets-style format string with `{field}` placeholders.

    Special cases: `{disc:02}`, `{track:02}` for zero-padded ints.
    Missing keys collapse to "Unknown".
    """
    safe = {k: _safe_name(str(v)) if isinstance(v, str) else v
            for k, v in fields.items()}
    safe.setdefault("albumartist", safe.get("artist", "Unknown Artist"))
    safe.setdefault("album", "Unknown Album")
    safe.setdefault("title", "Unknown Title")
    safe.setdefault("year", "0000")
    safe.setdefault("track", 0)
    safe.setdefault("disc", 1)
    safe.setdefault("ext", "mp3")
    try:
        return template.format(**safe)
    except (KeyError, IndexError, ValueError):
        return template


def _read_existing_tags(path: str) -> dict[str, Any]:
    try:
        from mutagen import File as MutagenFile
        from mutagen.easyid3 import EasyID3
        from mutagen.mp4 import MP4
        from mutagen.flac import FLAC
        from mutagen.oggvorbis import OggVorbis
        from mutagen.oggopus import OggOpus
    except ImportError:
        return {}

    out: dict[str, Any] = {}
    try:
        if path.lower().endswith(".mp3"):
            try:
                tags = EasyID3(path)
                out["artist"] = (tags.get("artist") or [""])[0]
                out["albumartist"] = (tags.get("albumartist") or [""])[0]
                out["album"] = (tags.get("album") or [""])[0]
                out["title"] = (tags.get("title") or [""])[0]
                out["date"] = (tags.get("date") or [""])[0]
                track = (tags.get("tracknumber") or [""])[0]
                out["track"] = int(track.split("/")[0]) if track else 0
                disc = (tags.get("discnumber") or [""])[0]
                out["disc"] = int(disc.split("/")[0]) if disc else 1
            except Exception:
                pass
        else:
            mf = MutagenFile(path, easy=True)
            if mf is not None and mf.tags is not None:
                t = mf.tags
                out["artist"] = (t.get("artist") or [""])[0] if hasattr(t, "get") else ""
                out["albumartist"] = (t.get("albumartist") or [""])[0] if hasattr(t, "get") else ""
                out["album"] = (t.get("album") or [""])[0] if hasattr(t, "get") else ""
                out["title"] = (t.get("title") or [""])[0] if hasattr(t, "get") else ""
                out["date"] = (t.get("date") or [""])[0] if hasattr(t, "get") else ""
                track = (t.get("tracknumber") or [""])[0] if hasattr(t, "get") else ""
                if track:
                    try:
                        out["track"] = int(str(track).split("/")[0])
                    except (ValueError, AttributeError):
                        out["track"] = 0
                disc = (t.get("discnumber") or [""])[0] if hasattr(t, "get") else ""
                if disc:
                    try:
                        out["disc"] = int(str(disc).split("/")[0])
                    except (ValueError, AttributeError):
                        out["disc"] = 1
    except Exception:
        return {}

    # Coerce year out of a date string if present.
    if out.get("date"):
        m = re.match(r"(\d{4})", str(out["date"]))
        if m:
            try:
                out["year"] = int(m.group(1))
            except ValueError:
                pass

    return {k: v for k, v in out.items() if v}


def _try_text_match(mb, existing: dict) -> tuple[dict | None, float]:
    """Look up MusicBrainz by `artist + album + title`. Returns (fields, score)."""
    artist = existing.get("artist") or existing.get("albumartist")
    album = existing.get("album")
    title = existing.get("title")
    if not (artist and (album or title)):
        return None, 0.0

    try:
        from rapidfuzz import fuzz
    except ImportError:
        # Without rapidfuzz, skip text-match — fall through to fingerprint.
        return None, 0.0

    try:
        query_parts = []
        if title:
            query_parts.append(f'recording:"{title}"')
        if artist:
            query_parts.append(f'artist:"{artist}"')
        if album:
            query_parts.append(f'release:"{album}"')
        result = mb.search_recordings(query=" AND ".join(query_parts), limit=5)
    except Exception:
        return None, 0.0

    best = None
    best_score = 0.0
    for rec in result.get("recording-list", []):
        rec_title = rec.get("title", "")
        rec_artist = (rec.get("artist-credit-phrase")
                      or (rec.get("artist-credit") or [{}])[0].get("name", ""))
        score_t = fuzz.ratio(rec_title.lower(), (title or "").lower()) if title else 0
        score_a = fuzz.ratio(rec_artist.lower(), artist.lower())
        score = (score_t * 0.6) + (score_a * 0.4)
        if score > best_score:
            best_score = score
            best = rec

    if best is None or best_score < 90:
        return None, best_score / 100.0

    # Pull canonical fields from the best recording's first release.
    releases = best.get("release-list") or []
    release = releases[0] if releases else {}
    fields = {
        "title": best.get("title"),
        "artist": (best.get("artist-credit-phrase")
                   or (best.get("artist-credit") or [{}])[0].get("name")),
        "albumartist": ((release.get("artist-credit") or [{}])[0].get("name")
                        if release.get("artist-credit") else None),
        "album": release.get("title"),
        "year": int(release["date"].split("-")[0]) if release.get("date", "")[:4].isdigit() else None,
        "mbid": best.get("id"),
        "score": best_score / 100.0,
    }
    fields = {k: v for k, v in fields.items() if v is not None}
    return fields, best_score / 100.0


def _try_fingerprint_match(api_key: str, path: str, mb) -> tuple[dict | None, float]:
    """Run Chromaprint -> AcoustID -> MusicBrainz."""
    try:
        import acoustid
    except ImportError:
        return None, 0.0

    try:
        results = list(acoustid.match(api_key, path))
    except acoustid.NoBackendError:
        return None, 0.0
    except acoustid.FingerprintGenerationError:
        return None, 0.0
    except acoustid.WebServiceError as e:
        # Surface as an error event upstream — but caller controls that.
        raise RuntimeError(f"AcoustID lookup failed: {e}") from e

    if not results:
        return None, 0.0

    score, recording_id, title, artist = results[0]
    if score < 0.85:
        return None, score

    # Pull a fuller picture from MusicBrainz to find the canonical release.
    try:
        rec = mb.get_recording_by_id(
            recording_id,
            includes=["releases", "artist-credits"],
        ).get("recording", {})
    except Exception:
        rec = {}

    releases = rec.get("release-list") or []
    release = releases[0] if releases else {}
    fields: dict[str, Any] = {
        "title": rec.get("title", title),
        "artist": (rec.get("artist-credit-phrase")
                   or (rec.get("artist-credit") or [{}])[0].get("name", artist)),
        "mbid": recording_id,
        "score": score,
    }
    if release:
        if release.get("title"):
            fields["album"] = release["title"]
        if release.get("date", "")[:4].isdigit():
            fields["year"] = int(release["date"].split("-")[0])
        if release.get("artist-credit"):
            fields["albumartist"] = release["artist-credit"][0].get("name")
    return fields, score


def _write_tags(path: str, fields: dict) -> None:
    """Update file tags in-place via mutagen."""
    try:
        from mutagen.easyid3 import EasyID3
        from mutagen import File as MutagenFile
    except ImportError:
        return

    ext = os.path.splitext(path)[1].lower()
    try:
        if ext == ".mp3":
            try:
                tags = EasyID3(path)
            except Exception:
                # File missing ID3 header — bootstrap one.
                from mutagen.id3 import ID3
                ID3().save(path)
                tags = EasyID3(path)
            if "title" in fields: tags["title"] = fields["title"]
            if "artist" in fields: tags["artist"] = fields["artist"]
            if "albumartist" in fields: tags["albumartist"] = fields["albumartist"]
            if "album" in fields: tags["album"] = fields["album"]
            if "year" in fields: tags["date"] = str(fields["year"])
            if "mbid" in fields: tags["musicbrainz_trackid"] = fields["mbid"]
            tags.save(v2_version=4)
        else:
            mf = MutagenFile(path, easy=True)
            if mf is None: return
            if mf.tags is None:
                mf.add_tags()
            if "title" in fields: mf["title"] = fields["title"]
            if "artist" in fields: mf["artist"] = fields["artist"]
            if "albumartist" in fields: mf["albumartist"] = fields["albumartist"]
            if "album" in fields: mf["album"] = fields["album"]
            if "year" in fields: mf["date"] = str(fields["year"])
            mf.save()
    except Exception as exc:
        raise RuntimeError(f"Tag write failed: {exc}") from exc


def _walk_audio(root: str) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(AUDIO_EXTS):
                out.append(os.path.join(dirpath, f))
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON Picard-style audio tagger")
    parser.add_argument("--root", required=True, help="Folder to scan")
    parser.add_argument("--mode", choices=["preview", "tag"], default="preview",
                        help="preview = identify only; tag = also write tags")
    parser.add_argument("--rename-pattern", default="",
                        help='Optional move template, e.g. '
                             '"Music/{albumartist}/{year} - {album}/{disc:02}-{track:02} {title}.{ext}"')
    parser.add_argument("--rename-root", default="",
                        help="Destination root for renames (defaults to --root if pattern given)")
    parser.add_argument("--api-key", default=os.environ.get("ACOUSTID_API_KEY", ""),
                        help="AcoustID API key (or set ACOUSTID_API_KEY env var). "
                             "Register free at https://acoustid.org/api-key")
    parser.add_argument("--rate-limit", type=float, default=1.0,
                        help="MusicBrainz rate limit (req/s)")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root directory does not exist: {args.root}"})
        return 2

    try:
        import musicbrainzngs as mb
    except ImportError:
        _emit({"event": "error", "code": "missing_dep",
               "message": "musicbrainzngs not installed. Run: pip install -r requirements.txt"})
        return 3

    mb.set_useragent(*USER_AGENT)
    mb.set_rate_limit(args.rate_limit)

    files = _walk_audio(args.root)
    _emit({"event": "start", "root": args.root, "mode": args.mode,
           "pattern": args.rename_pattern, "files_found": len(files)})

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
            existing = _read_existing_tags(path)

            # Try existing tags as ground truth first if they look complete.
            if (existing.get("artist") and existing.get("album")
                    and existing.get("title") and existing.get("track")):
                fields = dict(existing)
                fields["score"] = 1.0
                match_type = "existing"
            else:
                fields, score = _try_text_match(mb, existing)
                match_type = "text"
                if fields is None and args.api_key:
                    fields, score = _try_fingerprint_match(args.api_key, path, mb)
                    match_type = "fingerprint"

            if not fields:
                _emit({"event": "item", "path": path, "status": "untagged",
                       "match_type": "none", "score": 0.0,
                       **{k: v for k, v in existing.items() if k != "date"}})
                continue

            # Merge existing tag info we want to preserve (track/disc numbers,
            # which AcoustID/MB don't always return cleanly).
            for k in ("track", "disc"):
                if k in existing and k not in fields:
                    fields[k] = existing[k]

            if args.mode == "tag":
                _write_tags(path, fields)

            new_path = None
            if args.rename_pattern:
                ext = os.path.splitext(path)[1].lstrip(".") or "mp3"
                rel = _format_path(args.rename_pattern, {**fields, "ext": ext})
                dest_root = args.rename_root or args.root
                new_path = os.path.normpath(os.path.join(dest_root, rel))
                if args.mode == "tag" and os.path.abspath(new_path) != os.path.abspath(path):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    if not os.path.exists(new_path):
                        os.rename(path, new_path)
                        state["renamed"] += 1

            state["matched"] += 1
            _emit({"event": "item", "path": path, "status": "matched",
                   "match_type": match_type,
                   "score": float(fields.get("score", 0.0)),
                   "title": fields.get("title", ""),
                   "artist": fields.get("artist", ""),
                   "album": fields.get("album", ""),
                   "year": fields.get("year"),
                   "track": fields.get("track"),
                   "disc": fields.get("disc"),
                   "mbid": fields.get("mbid", ""),
                   "new_path": new_path})

        except KeyboardInterrupt:
            _emit({"event": "error", "code": "cancelled", "message": "Cancelled by user."})
            return 130
        except Exception as exc:
            _emit({"event": "item", "path": path, "status": "error",
                   "match_type": "none", "score": 0.0,
                   "message": f"{type(exc).__name__}: {exc}"})
            continue

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
