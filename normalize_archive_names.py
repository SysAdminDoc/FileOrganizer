#!/usr/bin/env python3
r"""normalize_archive_names.py — Rename design-asset archives to use the
canonical product title instead of bare marketplace IDs.

Naming patterns observed in I:\After Effects (and similar inboxes):

  Pattern                                       Example                  Strategy
  --------------------------------------------- ------------------------ ----------------------------------
  Bare Videohive ID                             VH-3101891.zip           HTTP scrape videohive.net redirect
  Videohive ID + version                        VH-25234937-V1.0.rar     Strip suffix, scrape ID
  Numeric prefix + slug                         095550436-photo-slideshow.zip  Already-named — clean only
  videohive- prefix + slug                      videohive-wedding-...zip Already-named — clean only
  Marketplace prefix + ID + slug                VideoHive-Wedding-...    Already-named — clean only
  Motion Array (no public redirect)             MA-620551.zip            Leave as-is
  Other (truly opaque)                          setup.zip                Leave as-is

For online lookups (Videohive specifically): the public marketplace URL
`https://videohive.net/item/-/<id>` issues a 301/302 redirect to the
canonical URL `https://videohive.net/item/<slug>/<id>`. We extract the
<slug>, replace dashes with spaces, and apply title-case to produce the
final filename. The page also exposes `<meta property="og:title">` which
carries human-readable special characters (`&`, parens, etc.) — we prefer
that over the slug when available.

All lookups are cached in marketplace_title_cache.json so re-runs are
free and the cache becomes a portable artifact for the future Python
FileOrganizer app.

Usage:
    python normalize_archive_names.py --root "I:\After Effects" --scan
    python normalize_archive_names.py --root "I:\After Effects" --apply
    python normalize_archive_names.py --root "I:\After Effects" --apply --dry-run
    python normalize_archive_names.py --root "I:\After Effects" --apply --no-online   # skip web lookups
"""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).parent
CACHE_FILE = REPO / "marketplace_title_cache.json"
LOG_FILE = REPO / "normalize_archive_names_log.json"

# Multipart RAR detector (only operate on .part1.rar; the rest follow)
PARTIAL_RAR_RE = re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE)

# Marketplace ID extractors. Order matters: more specific first.
# Each pattern returns (platform, id, residue). residue = whatever's left
# after the pattern is stripped from the basename, used as a fallback hint.
ID_PATTERNS: list[tuple[str, re.Pattern, str]] = [
    # VH-NNNNNNN with optional version suffix: VH-25234937-V2 / VH-3101891
    ("videohive", re.compile(r"^VH[-_](\d{6,9})(?:[-_].*)?$", re.IGNORECASE), "vh-prefix"),
    # videohive-...-NNNNNNN at end (slug already present): keep slug, only ID
    ("videohive", re.compile(r"^videohive[-_].+?[-_](\d{6,9})(?:[-_.].*)?$",
                              re.IGNORECASE), "vh-text-slug"),
    # VideoHive-...-NNNNNNN
    ("videohive", re.compile(r"^VideoHive[-_].+?[-_](\d{6,9})(?:[-_.].*)?$",
                              re.IGNORECASE), "vh-text-slug"),
    # Numeric prefix + slug: 095550436-photo-slideshow / 23601845-summer-opener
    ("videohive", re.compile(r"^(\d{7,9})[-_].+$"), "numeric-prefix-slug"),
    # MotionElements: NNNN_MotionElements_slug
    ("motionelements", re.compile(r"^(\d{6,9})_MotionElements_.+$",
                                   re.IGNORECASE), "me-prefix"),
    # MA-NNNNN
    ("motionarray", re.compile(r"^MA[-_](\d{4,9})$", re.IGNORECASE), "ma-bare"),
    # Slug with trailing 6-9 digit ID: wedding-slideshow-25259629
    ("videohive", re.compile(r"^.+?[-_](\d{6,9})$"), "trailing-id"),
]

INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
JUNK_TOKENS = re.compile(
    r"(?:INTRO[-_]?HD\.?NET|AIDOWNLOAD\.?NET|aidownload\.net|ShareAE\.com|"
    r"GFXDRUG\.COM|freegfx|graphicux|softarchive|VFXDownload\.net|"
    r"vfxdownload\.net|grafixfather|share\.ae)",
    re.IGNORECASE,
)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}


def load_cache() -> dict[str, dict]:
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict[str, dict]) -> None:
    CACHE_FILE.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                          encoding="utf-8")


def detect_platform_id(stem: str) -> tuple[str, str, str] | None:
    """Return (platform, id, hint) or None."""
    for platform, rx, hint in ID_PATTERNS:
        m = rx.match(stem)
        if m:
            return platform, m.group(1), hint
    return None


_LAST_REQUEST_AT = [0.0]   # naive global throttle (single-threaded)


def fetch_videohive_title(item_id: str, cache: dict[str, dict],
                          throttle: float = 0.4) -> dict | None:
    """Scrape https://videohive.net/item/-/<id> and pull the canonical title.

    The Envato server issues a 301/302 redirect from /item/-/<id> to
    /item/<slug>/<id>, where <slug> is the human-readable URL fragment.
    Even when the page later returns HTTP 410 (Gone, item removed), the
    redirect itself preserves the slug — so we accept ANY redirect that
    gives us a non-"-" slug, regardless of final status code.

    Returns {'title': str, 'slug': str, 'url': str} or None.
    Cache key: f'videohive:{id}'. Negative cache entries are stored as
    None so we don't re-hit broken endpoints on every run.
    """
    key = f"videohive:{item_id}"
    if key in cache:
        return cache[key] or None

    try:
        import requests
    except ImportError:
        return None

    # Polite throttle so we don't trip Envato's rate-limit
    elapsed = time.monotonic() - _LAST_REQUEST_AT[0]
    if elapsed < throttle:
        time.sleep(throttle - elapsed)
    _LAST_REQUEST_AT[0] = time.monotonic()

    url = f"https://videohive.net/item/-/{item_id}"
    try:
        r = requests.get(url, headers=HTTP_HEADERS, timeout=30,
                         allow_redirects=True)
    except Exception:
        cache[key] = None
        save_cache(cache)
        return None

    final_url = r.url
    slug_m = re.search(r"/item/([^/]+)/(\d+)", final_url)
    slug = slug_m.group(1) if slug_m else ""
    if slug == "-" or not slug:
        # Server didn't redirect — item is unrecoverable.
        cache[key] = None
        save_cache(cache)
        return None

    # Try to pull a richer title from the body (200 OK only — 410 returns
    # an apology page that doesn't carry the original og:title).
    title = ""
    if r.status_code == 200:
        og_m = re.search(
            r'<meta\s+property="og:title"\s+content="([^"]+)"',
            r.text, re.I,
        )
        if og_m:
            title = og_m.group(1)
        else:
            t_m = re.search(r"<title[^>]*>([^<]+)</title>", r.text, re.I)
            t = (t_m.group(1) if t_m else "").strip()
            t = re.sub(
                r"\s*[,\|]\s*(After Effects|Premiere Pro|Final Cut|Apple Motion).*$",
                "", t, flags=re.I,
            )
            t = re.sub(r"\s*[\|,]\s*VideoHive.*$", "", t, flags=re.I)
            title = t

    # Always fall back to slug→title; preferred over a generic <title> when
    # the page is 410 Gone but the redirect URL preserves the canonical slug
    if not title:
        title = slug_to_title(slug)

    # Decode common HTML entities
    title = (title.replace("&amp;", "&").replace("&#x27;", "'")
                  .replace("&quot;", '"').replace("&apos;", "'")
                  .replace("&#39;", "'"))
    title = title.strip()

    result = {"title": title, "slug": slug, "url": final_url,
              "status": r.status_code}
    cache[key] = result
    save_cache(cache)
    return result


def slug_to_title(slug: str) -> str:
    """Convert kebab-case slug to Title Case."""
    if not slug:
        return ""
    s = slug.replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.title()


def derive_title_from_stem(stem: str) -> str:
    """Pull a title out of the existing filename when no online lookup is
    needed (slug-format names). Handles videohive- prefixes, ID suffixes,
    Envato slug-suffix codes, version markers, etc.
    """
    s = stem.strip()
    s = JUNK_TOKENS.sub("", s)
    # Strip leading marketplace prefix
    s = re.sub(r"^(?:videohive[-_\s]+|VideoHive[-_\s]+|VH[-_])", "", s,
               flags=re.IGNORECASE)
    s = re.sub(r"^(?:elements[-_\s]+|envato[-_\s]+)", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^(?:[0-9]{6,}_MotionElements_)", "", s)
    # Strip leading numeric ID prefix
    s = re.sub(r"^(?:[0-9]{7,9})[-_\s]+", "", s)
    # Strip trailing numeric ID
    s = re.sub(r"[\s_\-]+\d{6,9}\s*$", "", s)
    # Strip CC/CS version markers
    s = re.sub(r"\s*\((?:CS|CC)\s*\d+(?:\.\d+)?\)\s*$", "", s, flags=re.I)
    s = re.sub(r"[_\-\s]+(?:CS|CC)\s*\d+(?:\.\d+)?\s*$", "", s, flags=re.I)
    # Strip Envato slug-suffix codes (MWFKLJ-RuBsP6N8-05-19 pattern)
    s = re.sub(r"[\s_\-]+[A-Z0-9]{4,8}-[A-Za-z0-9]{8,}-\d{2}-\d{2,4}\s*$", "", s)
    # Strip multipart/version suffix (-V2, -v1.0, etc.)
    s = re.sub(r"[\-_]+[Vv]\d+(\.\d+)?\s*$", "", s)
    # Strip trailing punctuation
    s = re.sub(r"\s*[-_\.]+\s*$", "", s)
    # Replace separators with spaces
    s = re.sub(r"[_\-\.]+", " ", s)
    # Collapse whitespace
    s = re.sub(r"\s+", " ", s).strip()
    # Remove invalid path chars
    s = INVALID_PATH_CHARS.sub("", s)
    # Title-case if all lowercase / all uppercase
    if s and (s == s.lower() or s == s.upper()):
        s = s.title()
    return s.strip(" .")


def sanitize_for_filename(s: str) -> str:
    """Make a string safe to use as a filename component.

    Replace path-invalid characters with a space (not empty string) so
    titles like "Foo/Bar" become "Foo Bar" instead of "FooBar".
    """
    s = INVALID_PATH_CHARS.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s[:180].rstrip(" .")


def archive_group(archive: Path) -> list[Path]:
    """Return all parts that belong to this multipart archive (or just
    [archive] if it's a single file). For .part2.rar etc. returns []."""
    m = PARTIAL_RAR_RE.search(archive.name)
    if not m:
        return [archive]
    if int(m.group(1)) != 1:
        return []
    base = archive.name[: m.start()]
    return sorted(p for p in archive.parent.iterdir()
                  if PARTIAL_RAR_RE.search(p.name) and p.name.startswith(base))


def part_suffix(archive: Path) -> str:
    """Return the .partN.rar suffix if present, else ''."""
    m = PARTIAL_RAR_RE.search(archive.name)
    if m:
        return archive.name[m.start():]  # ".part1.rar"
    return ""


def plan_rename(archive: Path, cache: dict[str, dict],
                allow_online: bool = True) -> tuple[Path | None, str]:
    """Return (planned_new_path, reason). new_path is None if no rename needed."""
    stem = archive.stem
    suffix = archive.suffix
    pre_part = part_suffix(archive)
    if pre_part:
        # Strip multipart suffix from stem so we plan against the base name
        stem = archive.name[: -len(pre_part)]
        suffix = pre_part  # we'll reattach this whole .partN.rar

    detected = detect_platform_id(stem)

    title = ""
    source = ""
    if detected:
        platform, item_id, hint = detected
        if platform == "videohive":
            if hint in ("numeric-prefix-slug", "vh-text-slug", "trailing-id"):
                # Slug already in the filename — derive title locally
                title = derive_title_from_stem(stem)
                source = f"local:{hint}"
            elif allow_online and hint == "vh-prefix":
                # Bare ID, online lookup needed
                lookup = fetch_videohive_title(item_id, cache)
                if lookup and lookup.get("title"):
                    title = lookup["title"]
                    source = f"online:videohive:{item_id}"
                else:
                    # Online lookup failed — just clean the existing stem
                    title = derive_title_from_stem(stem) or stem
                    source = f"local:fallback:{hint}"
            else:
                title = derive_title_from_stem(stem) or stem
                source = f"local:{hint}"
        elif platform == "motionelements":
            title = derive_title_from_stem(stem)
            source = "local:motionelements"
        elif platform == "motionarray":
            # No reliable scrape; keep stem as-is
            title = stem
            source = "skip:motionarray"
    else:
        # Already a slug or opaque
        cleaned = derive_title_from_stem(stem)
        if cleaned and cleaned != stem and len(cleaned) > 4:
            title = cleaned
            source = "local:slug-cleanup"
        else:
            title = stem
            source = "skip:opaque"

    title = sanitize_for_filename(title)
    if not title or len(title) < 3:
        return None, f"invalid-title:{source}"

    # Reject titles that are just digits — bare VH/MA IDs without a real
    # word are worse than the original "VH-NNN" since they lose the
    # "this is a Videohive item" hint.
    if re.fullmatch(r"\d+", title):
        return None, f"reject:numeric-only:{source}"

    new_name = f"{title}{suffix}"
    if new_name == archive.name:
        return None, f"already-clean:{source}"

    new_path = archive.parent / new_name
    return new_path, source


def safe_target(p: Path) -> Path:
    """Add (1), (2)... suffix to avoid clobbering an existing target."""
    if not p.exists():
        return p
    base = p.stem
    suffix = p.suffix
    # For multipart .partN.rar, treat .partN.rar as the suffix
    pre_part = part_suffix(p)
    if pre_part:
        base = p.name[: -len(pre_part)]
        suffix = pre_part
    i = 1
    while True:
        cand = p.parent / f"{base} ({i}){suffix}"
        if not cand.exists():
            return cand
        i += 1


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--scan", action="store_true",
                    help="Report planned renames without executing")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-online", action="store_true",
                    help="Skip web lookups; rely entirely on local heuristics")
    ap.add_argument("--limit", type=int, default=0,
                    help="Stop after N renames (0 = unlimited)")
    args = ap.parse_args()

    if not (args.scan or args.apply):
        ap.print_help()
        return

    root = Path(args.root)
    if not root.exists():
        print(f"Root not found: {root}")
        sys.exit(1)

    cache = load_cache()
    log_entries: list[dict] = []
    counts = {"skipped": 0, "renamed": 0, "errors": 0,
              "local": 0, "online": 0, "online_misses": 0}

    archives = sorted(
        f for f in root.iterdir()
        if f.is_file() and f.suffix.lower() in (".zip", ".rar", ".7z")
    )
    print(f"Scanning {len(archives)} archives in {root}")

    processed = 0
    for archive in archives:
        # Multipart RAR: only operate on the first part; rename siblings together
        parts = archive_group(archive)
        if not parts:
            continue

        if args.limit and processed >= args.limit:
            break

        new_path, source = plan_rename(archive, cache, allow_online=not args.no_online)

        if source.startswith("online"):
            counts["online"] += 1
        elif source.startswith("local"):
            counts["local"] += 1

        if new_path is None:
            counts["skipped"] += 1
            log_entries.append({"archive": archive.name, "action": "skip",
                                "reason": source})
            continue

        # Resolve collision
        target_base = new_path
        target = safe_target(target_base)

        tag = "[SCAN]" if args.scan else ("[DRY]" if args.dry_run else "[RENAME]")
        # Console is cp1252 on Windows; replace unmappable chars with '?'
        a_safe = archive.name.encode("cp1252", errors="replace").decode("cp1252")
        t_safe = target.name.encode("cp1252", errors="replace").decode("cp1252")
        print(f"{tag} {a_safe}  ({source})")
        print(f"   -> {t_safe}")

        # For multipart sets, plan the new name for ALL parts
        renames: list[tuple[Path, Path]] = []
        if len(parts) > 1:
            base_target_stem = target.name[: -len(part_suffix(target))]
            for p in parts:
                ps = part_suffix(p)
                t = p.parent / f"{base_target_stem}{ps}"
                if t.exists() and t != p:
                    t = safe_target(t)
                renames.append((p, t))
        else:
            renames.append((archive, target))

        if args.scan or args.dry_run:
            counts["renamed"] += 1
            for src, dst in renames:
                log_entries.append({
                    "archive": src.name, "action": "would-rename",
                    "to": dst.name, "source": source,
                })
            processed += 1
            continue

        try:
            for src, dst in renames:
                os.rename(str(src), str(dst))
                log_entries.append({
                    "archive": src.name, "action": "renamed",
                    "to": dst.name, "source": source,
                })
            counts["renamed"] += 1
        except OSError as e:
            print(f"   ERROR: {e}")
            counts["errors"] += 1
            log_entries.append({
                "archive": archive.name, "action": "error",
                "error": str(e), "source": source,
            })

        processed += 1

        # Save log + cache periodically
        if processed % 25 == 0 and not args.scan and not args.dry_run:
            LOG_FILE.write_text(json.dumps(log_entries, indent=2,
                                          ensure_ascii=False),
                                encoding="utf-8")

    if not args.scan and not args.dry_run:
        LOG_FILE.write_text(json.dumps(log_entries, indent=2,
                                      ensure_ascii=False),
                            encoding="utf-8")

    print("\n=== Summary ===")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print(f"  cache size: {len(cache)} entries")


if __name__ == "__main__":
    main()
