#!/usr/bin/env python3
"""NDJSON sidecar — e-book metadata reader.

Reads metadata from EPUB/MOBI/AZW3/PDF/CBZ/CBR/FB2 and emits one item event
per file. PDF gets a best-effort ISBN scan over the first 5 pages plus a
title-from-info-dict fallback. Optional `--isbn-lookup` enriches with
title/author/publisher via isbnlib's metadata providers.

Modes:
    preview  — read metadata only.
    rename   — preview + move into a target template path.

NDJSON events:
    {"event":"start","root":"...","mode":"...","pattern":"..."}
    {"event":"progress","scanned":N,"matched":N,"stage":"<msg>"}
    {"event":"item","path":"...","status":"matched|skipped|error",
        "format":"epub|mobi|azw3|pdf|cbz|cbr|fb2",
        "title":"...","author":"...","authors":["...","..."],
        "publisher":"...","language":"...","year":<int>,
        "isbn":"...","series":"...","series_index":<float>,
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

BOOK_EXTS = (".epub", ".mobi", ".azw", ".azw3", ".kfx", ".pdf",
             ".cbz", ".cbr", ".cb7", ".fb2", ".lit", ".pdb")

# ISBN-10 / ISBN-13 detection. Allow single space or hyphen between groups.
ISBN_PATTERN = re.compile(
    r"\b(?:ISBN(?:-1[03])?:?\s*)?"
    r"(97[89][\s\-]?(?:\d[\s\-]?){9}\d|(?:\d[\s\-]?){9}[\dXx])\b"
)


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
    safe.setdefault("author", "Unknown Author")
    safe.setdefault("year", "0000")
    safe.setdefault("series", "")
    safe.setdefault("series_index", 0)
    safe.setdefault("ext", "epub")
    try:
        return template.format(**safe)
    except (KeyError, IndexError, ValueError):
        return template


def _walk_books(root: str) -> list[str]:
    out = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            if f.lower().endswith(BOOK_EXTS):
                out.append(os.path.join(dirpath, f))
    return out


def _validate_isbn(raw: str) -> str | None:
    """Strip separators, return canonical ISBN-13 if checksum-valid."""
    digits = re.sub(r"[\s\-]", "", raw).upper()
    if len(digits) == 10:
        if not (digits[:9].isdigit() and (digits[9].isdigit() or digits[9] == "X")):
            return None
        s = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(digits))
        if s % 11 != 0:
            return None
        # Convert to ISBN-13 for canonical form.
        body = "978" + digits[:9]
        check = (10 - sum((1 if i % 2 == 0 else 3) * int(c)
                          for i, c in enumerate(body)) % 10) % 10
        return body + str(check)
    if len(digits) == 13 and digits.isdigit():
        check = (10 - sum((1 if i % 2 == 0 else 3) * int(c)
                          for i, c in enumerate(digits[:12])) % 10) % 10
        return digits if check == int(digits[12]) else None
    return None


def _read_epub(path: str) -> dict:
    from ebooklib import epub
    book = epub.read_epub(path, options={"ignore_ncx": True})
    out: dict = {"format": "epub"}

    def _meta(tag: str) -> list:
        return [v for v, _ in book.get_metadata("DC", tag)]

    titles = _meta("title")
    if titles: out["title"] = titles[0]
    authors = _meta("creator")
    if authors:
        out["authors"] = authors
        out["author"] = authors[0]
    pubs = _meta("publisher")
    if pubs: out["publisher"] = pubs[0]
    langs = _meta("language")
    if langs: out["language"] = langs[0]
    dates = _meta("date")
    if dates:
        m = re.match(r"(\d{4})", str(dates[0]))
        if m:
            try: out["year"] = int(m.group(1))
            except ValueError: pass
    ids = _meta("identifier")
    for ident in ids:
        isbn = _validate_isbn(str(ident))
        if isbn:
            out["isbn"] = isbn
            break

    # Calibre series metadata lives in <meta name="calibre:series" ...>.
    try:
        for item in book.get_metadata("OPF", "meta"):
            attrs = item[1] if len(item) > 1 else {}
            name = attrs.get("name", "")
            content = attrs.get("content", "")
            if name == "calibre:series" and content:
                out["series"] = content
            elif name == "calibre:series_index" and content:
                try: out["series_index"] = float(content)
                except ValueError: pass
    except Exception:
        pass

    return out


def _read_mobi(path: str) -> dict:
    """Minimal PalmDB header reader — pulls title from offset 0."""
    out: dict = {"format": "mobi"}
    try:
        with open(path, "rb") as f:
            header = f.read(78)
        title = header[:32].split(b"\x00", 1)[0].decode("latin-1", errors="ignore").strip()
        if title:
            # Mobi titles often have underscores instead of spaces.
            out["title"] = title.replace("_", " ")
    except OSError:
        pass
    return out


def _read_pdf(path: str) -> dict:
    out: dict = {"format": "pdf"}
    try:
        import pikepdf
    except ImportError:
        return out

    try:
        with pikepdf.open(path) as pdf:
            info = pdf.docinfo
            if info.get("/Title"):
                out["title"] = str(info["/Title"])
            if info.get("/Author"):
                out["author"] = str(info["/Author"])
                out["authors"] = [out["author"]]
            if info.get("/CreationDate"):
                m = re.search(r"(\d{4})", str(info["/CreationDate"]))
                if m:
                    try: out["year"] = int(m.group(1))
                    except ValueError: pass
    except Exception:
        pass

    # ISBN scan — first 5 pages of text.
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(path, maxpages=5)
        for raw, in ISBN_PATTERN.findall(text):
            isbn = _validate_isbn(raw)
            if isbn:
                out["isbn"] = isbn
                break
    except Exception:
        pass

    return out


def _read_cbz_cbr(path: str) -> dict:
    """Comic archive — look for ComicInfo.xml at the archive root."""
    out: dict = {"format": "cbz" if path.lower().endswith(".cbz") else
                          ("cbr" if path.lower().endswith(".cbr") else "cb7")}
    try:
        import zipfile, xml.etree.ElementTree as ET
        if not zipfile.is_zipfile(path):
            return out
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                if name.lower().endswith("comicinfo.xml"):
                    with zf.open(name) as f:
                        tree = ET.parse(f)
                    root = tree.getroot()
                    def _t(tag: str) -> str | None:
                        el = root.find(tag)
                        return el.text if el is not None else None
                    if _t("Title"): out["title"] = _t("Title")
                    if _t("Series"): out["series"] = _t("Series")
                    if _t("Number"):
                        try: out["series_index"] = float(_t("Number"))
                        except (TypeError, ValueError): pass
                    if _t("Writer"):
                        out["author"] = _t("Writer")
                        out["authors"] = [s.strip() for s in (_t("Writer") or "").split(",") if s.strip()]
                    if _t("Publisher"): out["publisher"] = _t("Publisher")
                    if _t("Year"):
                        try: out["year"] = int(_t("Year"))
                        except (TypeError, ValueError): pass
                    if _t("LanguageISO"): out["language"] = _t("LanguageISO")
                    break
    except Exception:
        pass
    return out


def _enrich_isbn(isbn: str, fields: dict) -> dict:
    """Use isbnlib's default provider chain to fill missing fields."""
    try:
        import isbnlib
    except ImportError:
        return fields
    try:
        meta = isbnlib.meta(isbn) or {}
        if meta.get("Title") and not fields.get("title"):
            fields["title"] = meta["Title"]
        if meta.get("Authors") and not fields.get("author"):
            fields["authors"] = meta["Authors"]
            fields["author"] = ", ".join(meta["Authors"])
        if meta.get("Publisher") and not fields.get("publisher"):
            fields["publisher"] = meta["Publisher"]
        if meta.get("Year") and not fields.get("year"):
            try: fields["year"] = int(meta["Year"])
            except (TypeError, ValueError): pass
        if meta.get("Language") and not fields.get("language"):
            fields["language"] = meta["Language"]
    except Exception:
        pass
    return fields


def _read_one(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    if ext == ".epub":
        return _read_epub(path)
    if ext in (".mobi", ".azw", ".azw3", ".pdb", ".lit", ".kfx"):
        return _read_mobi(path)
    if ext == ".pdf":
        return _read_pdf(path)
    if ext in (".cbz", ".cbr", ".cb7"):
        return _read_cbz_cbr(path)
    return {"format": ext.lstrip(".")}


def main() -> int:
    parser = argparse.ArgumentParser(description="NDJSON e-book metadata reader")
    parser.add_argument("--root", required=True)
    parser.add_argument("--mode", choices=["preview", "rename"], default="preview")
    parser.add_argument("--rename-pattern", default="",
                        help='e.g. "Books/{author}/{title}.{ext}" or '
                             '"Books/{author}/{series} #{series_index:g} - {title}.{ext}"')
    parser.add_argument("--rename-root", default="")
    parser.add_argument("--isbn-lookup", action="store_true",
                        help="Enrich missing fields via isbnlib (network).")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        _emit({"event": "error", "code": "root_not_found",
               "message": f"Root directory does not exist: {args.root}"})
        return 2

    try:
        import ebooklib  # noqa: F401
    except ImportError:
        _emit({"event": "error", "code": "missing_dep",
               "message": "ebooklib not installed. Run: pip install -r requirements.txt"})
        return 3

    files = _walk_books(args.root)
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
            fields = _read_one(path)
            fields["path"] = path

            if args.isbn_lookup and fields.get("isbn"):
                fields = _enrich_isbn(fields["isbn"], fields)

            if not (fields.get("title") or fields.get("author")):
                fields["status"] = "skipped"
                _emit({"event": "item", **fields})
                continue

            if args.mode == "rename" and args.rename_pattern:
                ext = os.path.splitext(path)[1].lstrip(".") or "epub"
                rel = _format_path(args.rename_pattern, {**fields, "ext": ext})
                dest_root = args.rename_root or args.root
                new_path = os.path.normpath(os.path.join(dest_root, rel))
                if os.path.abspath(new_path) != os.path.abspath(path):
                    os.makedirs(os.path.dirname(new_path), exist_ok=True)
                    if not os.path.exists(new_path):
                        os.rename(path, new_path)
                        state["renamed"] += 1
                        fields["new_path"] = new_path

            fields["status"] = "matched"
            state["matched"] += 1
            _emit({"event": "item", **fields})

        except KeyboardInterrupt:
            _emit({"event": "error", "code": "cancelled", "message": "Cancelled by user."})
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
        _emit({"event": "error", "code": "cancelled", "message": "Cancelled by user."})
        raise SystemExit(130)
    except Exception as exc:
        _emit({"event": "error", "code": "crashed",
               "message": f"{type(exc).__name__}: {exc}",
               "traceback": traceback.format_exc()})
        raise SystemExit(1)
