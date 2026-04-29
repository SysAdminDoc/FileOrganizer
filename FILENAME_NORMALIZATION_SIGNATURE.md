# Filename Normalization Signature

> A compact, transferable algorithm for turning raw marketplace-asset
> filenames into clean, human-readable titles. Distilled from a 33 TB
> design-asset library reorganization. Designed to drop straight into
> the future Python `FileOrganizer` app's classification pipeline.

## Why this matters

Raw filenames in the wild look like:

```
VH-3101891.zip
095550436-photo-slideshow.zip
videohive-wedding-valentine-card-19343478.zip
VideoHive_Space_Interstellar_Titles_19182507.rar
11457809_MotionElements_11-flat-sale-label-v2-aep.zip
VH-25234937-V1.0.part1.rar
elements-bounce-responsive-one-page-vcard-template-MWFKLJ-RuBsP6N8-05-19.zip
VH-25148454.zip
0000-2.zip                  # opaque numeric bucket
setup.zip                   # truly opaque
```

After normalization:

```
Wedding & Honeymoon.zip
Photo Slideshow.zip
Wedding Valentine Card.zip
Space Interstellar Titles.rar
11 Flat Sale Label V2.zip
[multipart kept as-is, base renamed: My Project.part1.rar / part2 / part3]
Bounce Responsive One Page vCard Template.zip
[item gone — kept as VH-25148454.zip]
0000-2.zip                  # left alone (no informative signal)
setup.zip                   # left alone
```

## The algorithm in five steps

### 1. Detect the marketplace ID and naming pattern

Eight regex patterns evaluated in order — first match wins. The pattern
identity is more important than the captured ID; it determines whether
we can clean locally or need an online lookup.

| Hint                  | Pattern                                                                  | Example                                              | Strategy        |
|-----------------------|--------------------------------------------------------------------------|------------------------------------------------------|-----------------|
| `vh-prefix`           | `^VH[-_](\d{6,9})(?:[-_].*)?$`                                           | `VH-3101891`, `VH-25234937-V2`                       | **online lookup** |
| `vh-text-slug`        | `^videohive[-_].+?[-_](\d{6,9})(?:[-_.].*)?$` (also `^VideoHive[-_]…`)   | `videohive-wedding-…-19343478`                       | local cleanup   |
| `numeric-prefix-slug` | `^(\d{7,9})[-_].+$`                                                      | `095550436-photo-slideshow`                          | local cleanup   |
| `me-prefix`           | `^(\d{6,9})_MotionElements_.+$`                                          | `11457809_MotionElements_…`                          | local cleanup   |
| `ma-bare`             | `^MA[-_](\d{4,9})$`                                                      | `MA-620551`                                          | skip (no public lookup) |
| `trailing-id`         | `^.+?[-_](\d{6,9})$`                                                     | `wedding-slideshow-25259629`                         | local cleanup   |
| (no match)            | —                                                                         | `Parallax_Corporate_Promo`                           | local cleanup (slug-only) |
| (no match, opaque)    | —                                                                         | `setup`, `0000-2`                                    | leave alone     |

### 2. Local cleanup (no network)

For everything except `vh-prefix`, the title is recoverable from the filename
itself. Apply this regex pipeline in order:

```python
s = JUNK_TOKENS.sub("", s)                                    # strip piracy/distribution domain markers
s = re.sub(r"^(?:videohive[-_\s]+|VideoHive[-_\s]+|VH[-_])", "", s, flags=re.I)
s = re.sub(r"^(?:elements[-_\s]+|envato[-_\s]+)", "", s, flags=re.I)
s = re.sub(r"^(?:[0-9]{6,}_MotionElements_)", "", s)
s = re.sub(r"^(?:[0-9]{7,9})[-_\s]+", "", s)                  # leading numeric ID
s = re.sub(r"[\s_\-]+\d{6,9}\s*$", "", s)                     # trailing numeric ID
s = re.sub(r"\s*\((?:CS|CC)\s*\d+(?:\.\d+)?\)\s*$", "", s, flags=re.I)
s = re.sub(r"[_\-\s]+(?:CS|CC)\s*\d+(?:\.\d+)?\s*$", "", s, flags=re.I)
s = re.sub(r"[\s_\-]+[A-Z0-9]{4,8}-[A-Za-z0-9]{8,}-\d{2}-\d{2,4}\s*$", "", s)  # Envato slug-suffix codes
s = re.sub(r"[\-_]+[Vv]\d+(\.\d+)?\s*$", "", s)              # version markers (-V2, -v1.0)
s = re.sub(r"[_\-\.]+", " ", s)                              # separators -> spaces
s = re.sub(r"\s+", " ", s).strip()                           # collapse whitespace
if s == s.lower() or s == s.upper():
    s = s.title()                                             # title-case if mono-case
```

`JUNK_TOKENS` = `(?:INTRO[-_]?HD\.?NET|AIDOWNLOAD\.?NET|ShareAE\.com|GFXDRUG\.COM|freegfx|graphicux|softarchive|VFXDownload\.net|grafixfather|share\.ae)` — observed piracy-distribution site brand markers.

### 3. Online lookup (only for bare `VH-NNNNN`)

Envato's public marketplace pattern is the single most reliable lookup
in the entire ecosystem:

```
GET https://videohive.net/item/-/<id>
```

The server responds with a 301/302 redirect to:

```
https://videohive.net/item/<slug>/<id>
```

Where `<slug>` is the kebab-case, URL-canonical title. **Critically, even
when the page itself returns HTTP 410 (item removed), the redirect still
preserves the slug** — Envato keeps the URL-mapping permanent. Only IDs
that were never published return 404 with no redirect at all.

```python
def fetch_videohive_title(item_id):
    url = f"https://videohive.net/item/-/{item_id}"
    r = requests.get(url, headers=BROWSER_HEADERS, allow_redirects=True)
    slug_m = re.search(r"/item/([^/]+)/(\d+)", r.url)
    slug = slug_m.group(1) if slug_m else ""
    if slug == "-" or not slug:
        return None                          # item never existed
    # Prefer og:title (richer punctuation than the slug) when 200 OK
    if r.status_code == 200:
        og = re.search(
            r'<meta\s+property="og:title"\s+content="([^"]+)"', r.text, re.I)
        if og:
            return decode_html_entities(og.group(1))
    # Fall back to slug-derived title (works even for 410 Gone pages)
    return slug.replace("-", " ").title()
```

**Browser headers are required** — Envato rejects bare `urllib`
default User-Agent with HTTP 403. The minimum that works:

```python
BROWSER_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
```

**Polite throttle** — 0.4 sec between requests avoids rate limiting.
Anything faster gets 200 OK responses with no useful body (Envato
returns a generic page when it thinks you're scraping).

### 4. Cache aggressively

Lookups are slow (network round-trip + Envato latency ≈ 0.4–1 sec each).
Cache every result, including negative results, in
`marketplace_title_cache.json`:

```json
{
  "videohive:3101891": {
    "title": "Wedding & Honeymoon",
    "slug": "wedding-honeymoon",
    "url": "https://videohive.net/item/wedding-honeymoon/3101891",
    "status": 200
  },
  "videohive:99999999": null
}
```

The cache becomes a portable artifact: a curated, growing dataset of
ID → canonical title mappings that the future Python app can ship
pre-populated. With 215 hits in our run, every subsequent organizer
benefits from those lookups for free.

### 5. Sanitize for the filesystem

Replace path-invalid characters with **a space** (not the empty string).
This preserves word boundaries:

```python
INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
title = INVALID_PATH_CHARS.sub(" ", title)
title = re.sub(r"\s+", " ", title).strip()
title = title[:180].rstrip(" .")          # FAT/NTFS practical limit + no trailing dots
```

A title like `Metal Opener / Futuristic HUD / Abstract Opening Ident`
becomes `Metal Opener Futuristic HUD Abstract Opening Ident` — readable.
Removing the slashes outright (sub with `""`) would have produced
`Metal OpenerFuturistic HUDAbstract Opening Ident` — broken word boundaries.

## Multipart RAR handling

Multipart RAR sets must be detected and renamed atomically:

```python
PARTIAL_RAR_RE = re.compile(r"\.part(\d+)\.rar$", re.IGNORECASE)
```

- Only operate on `.part1.rar` (or single non-part `.rar`).
- For `.part2.rar`, `.part3.rar`, etc., return early and let the part1
  handler process them as siblings.
- When renaming, plan ALL parts of the same set together — they share
  the new base name with the part suffix preserved verbatim:

```
VH-25234937-V1.0.part1.rar  ->  Cinema Visual Pack.part1.rar
VH-25234937-V1.0.part2.rar  ->  Cinema Visual Pack.part2.rar
VH-25234937-V1.0.part3.rar  ->  Cinema Visual Pack.part3.rar
```

## Generic AEP-stem rejection (for inside-archive lookups)

Many AE templates ship with an .aep literally named `Project.aep`, `main.aep`,
`Comp 1.aep`, or `untitled.aep`. These are *worse* than the original
filename — they describe nothing. Reject them as project-name candidates
and fall through to the next signal.

```python
GENERIC_AEP_STEMS = {
    "project", "main", "comp 1", "main comp", "preview", "render",
    "untitled", "new project", "scene", "scene 1", "ae", "after effects",
    "template", "final", "edit", "footage", "main project", "video",
    "001", "01",
}
```

Also reject `__MACOSX/` and `._*` (macOS resource fork) entries
unconditionally — they always shadow the real name with junk.

```python
if path.startswith("__MACOSX/") or "/._" in path or basename.startswith("._"):
    skip_this_entry()
```

## Numeric-only safety net

If every other heuristic fails and the resulting title is purely digits
(`14330960`), **do not rename**. A bare ID like `VH-14330960.zip` carries
the implicit hint "Videohive item" — losing the prefix to produce
`14330960.zip` is strictly worse. Skip.

```python
if re.fullmatch(r"\d+", title):
    return None    # numeric-only rejection
```

## Statistics from a real 1,645-archive run

| Outcome                                     | Count | %     |
|---------------------------------------------|-------|-------|
| Renamed via local rules                     |   975 | 59.3% |
| Renamed via online VH lookup                |    81 |  4.9% |
| Skipped (already clean / cached miss / opaque) |   589 | 35.8% |
| Errors                                      |     0 |  0.0% |
| **Online cache hits → titles recovered**    |   215 | (~33% of online attempts) |
| **Online misses (item never existed)**      |   430 |  —    |

The 33% online hit rate is structural — Envato has been operating since
2008, and a meaningful fraction of older Videohive items have been
hard-deleted (their slug→ID mappings were never preserved). The
remaining items are recoverable.

## What this signature gives the future Python app

1. **Drop-in module**: ~250 lines of pure Python + `requests`. No DeepSeek,
   no LLM API, no per-item cost.
2. **Portable cache**: `marketplace_title_cache.json` ships with the app
   pre-populated. Every install starts with hundreds of free lookups.
3. **Conservative defaults**: never destroys information. If we can't
   improve a name, we leave it alone.
4. **Resume-safe**: cache + `os.rename` semantics mean a kill mid-run
   loses no progress.
5. **Multipart-aware**: RAR sets stay coherent across renames.

## Limitations and known gaps

- **Motion Array (MA-NNNNN)**: no public ID→slug redirect. Manual lookup
  via search results would require parsing JS-heavy pages — left as
  future work.
- **MotionElements**: the prefix `NNNN_MotionElements_<slug>` always
  carries the slug, so local cleanup suffices. No online path needed.
- **Hard-deleted Envato items**: ~33% of bare VH-NNN IDs no longer
  redirect at all. Names stay as-is.
- **Locale-specific titles**: some Videohive items use non-Latin titles
  (Cyrillic, CJK). The script handles them but the Windows console may
  fail to print — use UTF-8 logs as the source of truth.

## How to use this in the next session

```bash
python normalize_archive_names.py --root "I:\After Effects" --scan        # report only
python normalize_archive_names.py --root "I:\After Effects" --apply       # do it
python normalize_archive_names.py --root "I:\After Effects" --apply --no-online  # offline only
```

The cache (`marketplace_title_cache.json`) is checked in to the repo.
Subsequent runs against any inbox immediately hit the cache for any IDs
seen previously — the "library effect" compounds over time.
