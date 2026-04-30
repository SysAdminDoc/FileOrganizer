# Marketplace Catalog Expansion Signature

How the Envato marketplace_title_cache.json was grown from 643 entries
(one user's library, videohive-only) to 43,000+ entries across all 7
Envato marketplaces, suitable for a public day-one cache that gives any
new FileOrganizer user a cache hit on most archives they encounter.

This document captures the discovery surfaces, URL contracts, retry
parameters, and bail-out tuning needed to reproduce the expansion. Pair
it with [FILENAME_NORMALIZATION_SIGNATURE.md](FILENAME_NORMALIZATION_SIGNATURE.md)
which covers per-archive title lookup.

## Cache contents (apr 2026 snapshot)

Two artifacts ship from the expansion pipeline:

**1. `marketplace_title_cache.json` (lightweight, 16 MB)** — 96,026 entries
covering the most popular items per marketplace, sourced from /search,
/category, /authors/top, and author portfolios. This is what
`normalize_archive_names.py` reads at runtime; it's small enough to load
into memory in a millisecond.
```
photodune     22,473
graphicriver  22,190
audiojungle   16,486
videohive     12,686
codecanyon     9,703
themeforest    8,018
3docean        4,470
TOTAL        96,026
```

**2. `catalog/` (sharded, 400 MB across 14 files)** — 10,645,539 entries
covering the *complete* public Envato catalog, sourced from each
marketplace's `/sitemap.xml.gz`. Shipped as gzipped JSON shards under
50 MB each so they fit git's recommended file-size budget. Use
`catalog_lookup.py` for shard-aware lazy lookups (loads only the relevant
~40 MB shard on demand).
```
photodune     3,762,723   (4 shards × ~39 MB)
videohive     3,475,605   (4 shards × ~39 MB)
audiojungle   2,413,612   (2 shards × ~30 MB)
graphicriver    834,008   (1 shard, 23 MB)
themeforest      65,478   (1 shard, 2 MB)
3docean          55,801   (1 shard, 1.6 MB)
codecanyon       38,312   (1 shard, 1.5 MB)
TOTAL        10,645,539
```

Growth: 643 -> 10.6M entries (16,500x). Original cache was videohive-only.

## The expansion model

A user's local archive set typically covers a few hundred Envato items.
A public cache wants coverage of the **most likely items any user has
ever bought**, which approximates *the most popular items in each
marketplace*. The strategy:

1. Walk each marketplace's *listing surfaces* (search, category pages,
   top-sellers, featured) where every visible `/item/<slug>/<id>` URL
   is a free, no-extra-request fact: that ID's canonical slug is `<slug>`.
2. Multiply *sort orders* (sales, rating, date, trending, recent) - each
   sort surfaces a different cross-section of the catalog.
3. Multiply *subcategories* - each subcategory has its own pagination
   window separate from the global search, so it surfaces items that
   never appear on `/search?q=&page=1..60`.
4. Run all 7 marketplaces in parallel - they're rate-limited
   independently per IP, so concurrency is a free speedup.

## URL contracts

### Per-item canonical URL (the fact extracted from listings)
```
/item/<slug>/<id>            e.g. /item/cinematic-titles/12345678
```
Regex used to extract from any HTML page:
```python
ITEM_RX = re.compile(r"/item/([a-z0-9_-]+)/(\d+)(?:[/\"\s?])", re.IGNORECASE)
```
The trailing-character class is critical; without it the regex over-matches.

### Global search (works on every Envato site)
```
/search?q=&sort=<sort>&page=<n>
```
- Pagination capped at ~60 pages on every marketplace.
- Returns 30-31 unique item URLs per page on a healthy listing.
- Beyond page 60: returns the same 30 items repeatedly (de-dupes to 0 new).

### Subcategory listings (deeper pagination window)
```
/category/<slug>?sort=<sort>&page=<n>
/category/<slug>/<sub-slug>?sort=<sort>&page=<n>
```
- Slugs vary per marketplace; *do not hardcode them* - some are obsolete
  (e.g. `videohive.net/category/after-effects-templates` redirects but
  the real slug is `after-effects-project-files`).
- Discover dynamically by fetching `<base_url>/` and extracting
  `/category/...` href links.
- Each subcategory has its own ~60-page cap, so each adds ~1500 unique
  IDs that aren't reachable from `/search`.

### Top-sellers / featured (fixed pages)
```
/top-sellers
/feature
```
- High-quality items, single page each.
- Worth scraping once per marketplace at the start of any pass.

### Sitemap (THE complete catalog)
```
/robots.txt                           - declares Sitemap: URLs
/sitemap.xml.gz                       - root: index of nested shards OR
                                        a urlset with items inline
/sitemaps/<marketplace>/sitemap<n>.xml.gz   - nested shard
```
- robots.txt always declares the sitemap location; never hardcode the
  URL since Envato has changed it before.
- Two flavors of root sitemap exist:
  - **Index style** (videohive, photodune, audiojungle, graphicriver,
    themeforest, 3docean): a `<sitemapindex>` referencing N nested
    `<loc>...sitemap<n>.xml.gz</loc>` shards.
  - **Direct style** (codecanyon): the root itself is a `<urlset>` with
    item URLs inline.
- Each nested shard contains 30K-55K item URLs. videohive has 221 shards
  (~12M total URLs, dedupes to ~3.5M unique items).
- This is the only surface that gives the *complete* catalog. /search
  and /category cap at ~60 pages each; sitemaps don't paginate.
- Decompress with `gzip.decompress(r.content)`. Some sitemaps double-gzip
  (the request includes `Accept-Encoding: gzip`, the server transports
  the already-gzipped body un-content-encoded). Detect by sniffing the
  magic bytes `\x1f\x8b` after the request returns.

### Author portfolios (deepest single source)
```
/authors/top                        - top ~50 author usernames
/user/<name>/portfolio?page=<n>     - that author's items, paginated
```
- Top authors have 100s-1000s of items; portfolio pagination opens a
  separate window from /search and /category.
- Bail-out signal: when a portfolio request lands on `/user/<name>` (no
  `/portfolio` segment in `r.url`), pagination is exhausted - stop.
- Each page returns ~30 unique items (deduped from 36 raw matches).
- Author discovery: combine `/authors/top` + the first 3 search-sales
  pages (each item links its author).
- This surface alone added +28K entries on top of the search/category
  baseline; running deeper (80 pages × 150 authors) added another +10K.

## Sort orders (in order of catalog diversity)

```python
SORT_ORDERS = ["sales", "rating", "date", "trending", "recent"]
```
- `sales` and `rating` give the widest net of unique items.
- `date` and `trending` capture newer uploads not yet ranked highly.
- `recent` typically yields nothing not already covered by `date`; useful
  as a sanity sentinel - if `recent` returns 0 new on page 1, the
  current sort window is exhausted.

## Bail-out tuning

```python
PAGES_NO_NEW_BAIL    = 3   # stop a sort after N consecutive 0-new pages
SORT_FIRSTPASS_BAIL  = 5   # if first sort yields 0 new in first N pages,
                           # marketplace is dead/blocked - skip the rest
DEAD_SORTS_BAIL      = 2   # 2 consecutive dead sorts -> advance
```
These were tuned empirically. Earlier attempts at `PAGES_NO_NEW_BAIL=10`
got the script wedged on videohive for ~30 minutes walking duplicates;
3 is the sweet spot.

## HTTP / session params

```python
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}
THROTTLE = 0.8   # seconds between requests per session
```
- Default `urllib` User-Agent gets HTTP 403. A real browser UA bypasses.
- `requests.Session()` (per worker thread) keeps cookies stable across
  paginated requests, which Envato uses to disambiguate page numbers.
- 0.8s throttle per session × 7 parallel sessions = ~9 req/sec aggregate,
  which Envato tolerates without rate-limit responses.

## Cache schema

```json
"<marketplace>:<id>": {
  "title": "Title Cased Slug",
  "slug": "title-cased-slug",
  "source": "catalog-listing"
}
```
- `marketplace`: one of `videohive`, `themeforest`, `audiojungle`,
  `graphicriver`, `photodune`, `3docean`, `codecanyon`.
- Titles are derived from slug (`replace("-", " ").title()`) - we don't
  pay the cost of a per-item HTML fetch during catalog expansion.
- Per-archive lookups (the FILENAME_NORMALIZATION_SIGNATURE flow) DO fetch
  HTML and prefer `og:title`, but only when the user's library has the
  item in question.
- The `fix_short_titles.py` pass swaps og:title for slug-derived when the
  slug is materially more descriptive (more words AND >=30% longer).

## Reproducing the expansion

The full sequence run on a fresh cache:
```bash
# Pass 1 - global /search across all 7 sites in parallel, 60 pages × 5 sorts
python bulk_catalog_envato.py --apply --parallel --max-pages 60 --throttle 0.8

# Pass 2 - deep paging for sites that hit the page-60 cap
python bulk_catalog_envato.py --apply --parallel --start-page 60 --max-pages 200 --throttle 0.6

# Pass 3 - subcategory sweep (dynamic discovery)
python bulk_catalog_envato.py --apply --parallel --subcategories --max-pages 12 --throttle 0.5

# Pass 4 - author portfolio sweep (top 80 authors per site, 40 pages each)
python bulk_catalog_envato.py --apply --parallel --authors \
    --max-authors 80 --author-pages 40 --throttle 0.5

# Pass 5 - author deepening (150 authors, 80 pages, catches authors who
# hit the 40-page cap in pass 4)
python bulk_catalog_envato.py --apply --parallel --authors \
    --max-authors 150 --author-pages 80 --throttle 0.5

# Pass 6 - subcategory deepening (page 12 onward, lifts the 12-page cap
# from pass 3)
python bulk_catalog_envato.py --apply --parallel --subcategories \
    --start-page 12 --max-pages 40 --throttle 0.5

# Pass 7 - SITEMAP HARVEST (the complete public catalog, ~10M entries)
python bulk_catalog_envato.py --apply --parallel --sitemaps --throttle 0.4

# Post-process: shard the resulting 2 GB JSON into git-safe gzipped pieces
mv marketplace_title_cache.json marketplace_title_cache.full.json
git checkout HEAD -- marketplace_title_cache.json   # restore the 96K subset
python catalog_shard.py marketplace_title_cache.full.json catalog/
```
Total wall time for passes 1-6: ~70 minutes. Pass 7 (sitemaps) adds another
20-30 minutes and ~2 GB of intermediate disk.

Each pass is incremental and idempotent - re-running yields 0 new entries
once a surface is saturated. Run pass 5 + 6 + 7 monthly to capture new
uploads on Envato without re-walking already-covered ground.

## Storage strategy

The full sitemap-harvested catalog is too big for a single JSON file in
git (2 GB raw, 400 MB gzipped). Split into per-marketplace + per-id-modulo
shards under 50 MB each. Layout:
```
catalog/
  videohive_0.json.gz    videohive_1.json.gz    videohive_2.json.gz    videohive_3.json.gz
  photodune_0.json.gz    photodune_1.json.gz    photodune_2.json.gz    photodune_3.json.gz
  audiojungle_0.json.gz  audiojungle_1.json.gz
  graphicriver_0.json.gz themeforest_0.json.gz  3docean_0.json.gz      codecanyon_0.json.gz
```
Shard count per marketplace lives in `catalog_shard.py:NUM_SHARDS` and
`catalog_lookup.py:NUM_SHARDS` — keep these in sync. Lookup:
```python
from catalog_lookup import CatalogLookup
cl = CatalogLookup()
entry = cl.get("videohive", "12345678")    # loads only videohive_2.json.gz
```
The helper LRU-caches loaded shards in memory, so resolving a few
thousand IDs across one session touches 4-7 shards (~300 MB peak) vs the
8 GB+ a full-load would need.

## Failure modes encountered

1. **`urllib` returns 403** - fixed by browser User-Agent.
2. **Single sort gets 0 new on re-run, script bails marketplace** - the
   first 60 pages are already cached; `--start-page 60` skips ahead.
3. **Hardcoded subcategory slugs are obsolete** - replaced with dynamic
   homepage scrape via `discover_subcategories(base_url)`.
4. **Windows file-rename race during cache save** - parallel threads +
   external readers (json inspectors) intermittently lock the dest. Fix:
   retry `Path.replace()` 8 times with exponential back-off.
5. **First-run videohive page-stall** - earlier `consecutive_no_new`
   logic required *both* added==0 AND empty-response, so duplicate-only
   pages never tripped the bail. Fixed by counting any 0-new page.

## Known coverage gaps

- **Motion Array** archives (filename pattern `MA-NNNNN`) have no
  public-listing surface - their catalog requires login. No way to
  auto-populate; the FileOrganizer app should fall back to keeping the
  bare `MA-NNNNN` ID as the title.
- **Pond5 / iStock / Shutterstock** items - different ecosystem, not
  attempted here. Each would need its own listing-walker + URL contract.
- Items beyond page 60 of every sort *and* not in any subcategory leaf -
  unrecoverable from public listings. This is a small fraction of the
  Envato catalog (deep tail of low-sales items).

## Future work

1. Cron a monthly re-run of pass 3 (subcategory sweep) to capture new
   items posted since the last harvest.
2. Add Pond5 and Motion Array lookup paths (Pond5 has public listings;
   Motion Array does not, and would require an authenticated cookie).
3. Consider extending to AudioBlocks/Storyblocks if any user library
   has those in scope.
4. Ship the cache as a release asset (gzip'd ~2 MB) so the future
   FileOrganizer Python app can hydrate it from a URL on first run.
