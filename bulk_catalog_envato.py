#!/usr/bin/env python3
r"""bulk_catalog_envato.py - Build a large reference cache of Envato
marketplace item ID -> canonical title mappings, beyond what any single
user has in their library.

The marketplace_title_cache.json built from one user's archives is small
(~640 entries). For the future Python FileOrganizer app to be useful out
of the box, we want a much larger pre-populated catalog so any user
encounters cache hits on day one.

Approach: walk the public listing surfaces of every Envato marketplace
and harvest every item URL we can see. Each `/item/<slug>/<id>` URL is
a fact: that ID's canonical slug is `<slug>`, no further request needed.

  marketplace      base url
  ---------------- ----------------------
  videohive        https://videohive.net
  themeforest      https://themeforest.net
  audiojungle      https://audiojungle.net
  graphicriver     https://graphicriver.net
  photodune        https://photodune.net
  3docean          https://3docean.net
  codecanyon       https://codecanyon.net

For each marketplace we paginate `/search?q=&sort=<order>&page=N` (works
on every Envato site, unlike /category/all) across multiple sort orders.

Output: extends marketplace_title_cache.json with new entries keyed by
"<marketplace>:<id>", value is {title, slug, source: "catalog-listing"}.

Usage:
    python bulk_catalog_envato.py --scan                   # report only
    python bulk_catalog_envato.py --apply                  # write to cache
    python bulk_catalog_envato.py --apply --site videohive # one site only
    python bulk_catalog_envato.py --apply --max-pages 30   # smaller pass
    python bulk_catalog_envato.py --apply --parallel       # 7 sites concurrent
"""
import argparse
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO = Path(__file__).parent
CACHE_FILE = REPO / "marketplace_title_cache.json"
CACHE_LOCK = threading.Lock()

MARKETPLACES = [
    ("videohive",   "https://videohive.net"),
    ("themeforest", "https://themeforest.net"),
    ("audiojungle", "https://audiojungle.net"),
    ("graphicriver","https://graphicriver.net"),
    ("photodune",   "https://photodune.net"),
    ("3docean",     "https://3docean.net"),
    ("codecanyon",  "https://codecanyon.net"),
]

# Sort orders that exist on Envato (different sorts surface different items).
# `sales` and `rating` typically yield best item diversity; date variants
# capture newer uploads.
SORT_ORDERS = ["sales", "rating", "date", "trending", "recent"]

# Subcategories are discovered dynamically by scraping each marketplace's
# homepage for `/category/<slug>` links — Envato's category slugs change
# (e.g. videohive uses `after-effects-project-files`, not the older
# `after-effects-templates`). See discover_subcategories().
CATEGORY_LINK_RX = re.compile(
    r'href="(/category/[a-z0-9][a-z0-9/_-]+)(?:[?#"][^"]*)?"',
    re.IGNORECASE,
)

# Author portfolio pagination: /user/<name>/portfolio?page=N
# Top authors have 100s-1000s of items, opening a separate pagination
# window from /search and /category. See discover_authors() and
# harvest_author().
USER_LINK_RX = re.compile(
    r'href="/user/([a-z0-9_-]+?)(?:/[a-z]+)?(?:[?#"])',
    re.IGNORECASE,
)

# Regex for /item/slug/id - works on every Envato site.
ITEM_RX = re.compile(r"/item/([a-z0-9_-]+)/(\d+)(?:[/\"\s?])", re.IGNORECASE)

HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
}

# Bail-out tuning
PAGES_NO_NEW_BAIL = 3      # stop a sort after N consecutive pages with 0 new IDs
SORT_FIRSTPASS_BAIL = 5    # if first sort yields 0 new in first N pages, marketplace is dead


def slug_to_title(slug: str) -> str:
    if not slug:
        return ""
    s = slug.replace("-", " ").replace("_", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s.title()


def load_cache() -> dict:
    if CACHE_FILE.exists():
        return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {}


def save_cache(cache: dict) -> None:
    with CACHE_LOCK:
        tmp = CACHE_FILE.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cache, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        # Windows: tmp.replace() can fail with "Access is denied" if another
        # process briefly opens CACHE_FILE for read (e.g., a monitoring tool
        # or json inspector). Retry a few times before giving up.
        for attempt in range(8):
            try:
                tmp.replace(CACHE_FILE)
                return
            except (OSError, PermissionError):
                if attempt == 7:
                    raise
                time.sleep(0.25 * (attempt + 1))


def discover_subcategories(base_url: str, throttle: float = 0.8) -> list:
    """Scrape `<base_url>/` for /category/<slug> links. Return a list of
    slug strings (without leading /category/) — both top-level and 2-deep.
    Top-level slugs alone open a "category overview" page that has 0 items
    on most Envato sites; the 2-deep slugs are the real listing pages."""
    try:
        import requests
    except ImportError:
        return []
    sess = requests.Session()
    sess.headers.update(HTTP_HEADERS)
    time.sleep(throttle)
    try:
        r = sess.get(base_url + "/", timeout=30, allow_redirects=True)
    except Exception:
        return []
    if r.status_code != 200:
        return []
    raw = CATEGORY_LINK_RX.findall(r.text)
    slugs = sorted({m.removeprefix("/category/").strip("/") for m in raw})
    # Filter out junk (single-letter, numeric-only, or non-slug)
    return [s for s in slugs if len(s) >= 3 and re.match(r"^[a-z0-9][a-z0-9/_-]+$", s)]


def harvest_page(sess, url: str, throttle: float) -> set:
    """Return set of (slug, id) tuples found on a listing page."""
    time.sleep(throttle)
    try:
        r = sess.get(url, timeout=30, allow_redirects=True)
    except Exception:
        return set()
    if r.status_code != 200:
        return set()
    matches = ITEM_RX.findall(r.text)
    return {(slug.lower(), vid) for slug, vid in matches}


def discover_authors(base_url: str, throttle: float = 0.6,
                     extra_seed_pages: int = 3) -> list:
    """Scrape `/authors/top` and the global `/search?sort=sales` first pages
    for `/user/<name>` links. Returns a sorted list of unique usernames."""
    try:
        import requests
    except ImportError:
        return []
    sess = requests.Session()
    sess.headers.update(HTTP_HEADERS)

    seeds = [f"{base_url}/authors/top"]
    # Search pages also surface popular authors (each item links its author)
    for page in range(1, extra_seed_pages + 1):
        seeds.append(f"{base_url}/search?q=&sort=sales&page={page}")

    found = set()
    for url in seeds:
        time.sleep(throttle)
        try:
            r = sess.get(url, timeout=30, allow_redirects=True)
        except Exception:
            continue
        if r.status_code != 200:
            continue
        for m in USER_LINK_RX.findall(r.text):
            name = m.lower().strip()
            if (len(name) >= 3 and name not in {"envato", "search", "cart",
                                                 "wishlist", "settings"}
                    and re.match(r"^[a-z0-9][a-z0-9_-]+$", name)):
                found.add(name)
    return sorted(found)


def harvest_author(marketplace: str, base_url: str, username: str,
                   max_pages: int, cache: dict, throttle: float = 0.6) -> int:
    """Walk `/user/<username>/portfolio?page=N` until pagination redirects
    to bare profile (out of items). Returns NEW entries added to cache.

    Detection: when a portfolio page request lands on /user/<name> (no
    /portfolio segment) we've walked past the last page; bail.
    """
    try:
        import requests
    except ImportError:
        return 0

    sess = requests.Session()
    sess.headers.update(HTTP_HEADERS)
    new_count = 0
    consecutive_no_new = 0

    for page in range(1, max_pages + 1):
        url = f"{base_url}/user/{username}/portfolio?page={page}"
        time.sleep(throttle)
        try:
            r = sess.get(url, timeout=30, allow_redirects=True)
        except Exception:
            break
        if r.status_code != 200:
            break
        # Pagination exhausted: redirect to bare /user/<name> drops the items
        if "/portfolio" not in r.url.lower():
            break
        items = {(slug.lower(), vid) for slug, vid
                 in ITEM_RX.findall(r.text)}
        added = _ingest(cache, marketplace, items)
        new_count += added
        if added == 0:
            consecutive_no_new += 1
            if consecutive_no_new >= 2:
                break
        else:
            consecutive_no_new = 0
    return new_count


def harvest_marketplace(marketplace: str, base_url: str, max_pages: int,
                        cache: dict, throttle: float = 0.8,
                        save_every: int = 5, start_page: int = 1,
                        category: str | None = None) -> int:
    """Walk listing surfaces of one marketplace; add new entries to cache.
    Returns number of NEW entries added.

    If `category` is set, walks /category/<category>?sort=X&page=N instead
    of the global /search?q=&sort=X&page=N.
    """
    try:
        import requests
    except ImportError:
        return 0

    sess = requests.Session()
    sess.headers.update(HTTP_HEADERS)

    new_count = 0
    pages_walked = 0

    label = f"{marketplace}/{category}" if category else marketplace
    print(f"\n=== {label} ({base_url}) ===", flush=True)

    # Top-sellers / featured (single pages, high-quality items) - skip on deep re-runs
    if start_page <= 1 and not category:
        for path in ["/top-sellers", "/feature"]:
            items = harvest_page(sess, f"{base_url}{path}", throttle)
            added = _ingest(cache, marketplace, items)
            new_count += added
            print(f"  {path}: +{added} new (page hit {len(items)} item URLs)",
                  flush=True)
            if added:
                save_cache(cache)

    sort_dead_count = 0
    for sort_idx, sort_order in enumerate(SORT_ORDERS):
        consecutive_no_new = 0
        sort_added = 0
        for page in range(start_page, max_pages + 1):
            if category:
                url = (f"{base_url}/category/{category}"
                       f"?sort={sort_order}&page={page}")
            else:
                url = f"{base_url}/search?q=&sort={sort_order}&page={page}"
            items = harvest_page(sess, url, throttle)
            added = _ingest(cache, marketplace, items)
            sort_added += added
            new_count += added
            pages_walked += 1

            if added == 0:
                consecutive_no_new += 1
            else:
                consecutive_no_new = 0

            if pages_walked % save_every == 0 and added:
                save_cache(cache)

            if consecutive_no_new >= PAGES_NO_NEW_BAIL:
                break

            # First-sort cold check: if marketplace yields nothing in first
            # SORT_FIRSTPASS_BAIL pages, it's likely dead/blocked
            if sort_idx == 0 and page >= SORT_FIRSTPASS_BAIL and sort_added == 0:
                print(f"  [{marketplace}] dead site (0 items in first "
                      f"{SORT_FIRSTPASS_BAIL} pages); skipping", flush=True)
                save_cache(cache)
                return new_count

        print(f"  sort={sort_order}: +{sort_added} new "
              f"(walked {page} pages, {new_count} cumulative)", flush=True)
        save_cache(cache)

        if sort_added == 0:
            sort_dead_count += 1
            if sort_dead_count >= 2:
                print(f"  [{marketplace}] 2 consecutive dead sorts; advancing",
                      flush=True)
                break
        else:
            sort_dead_count = 0

    save_cache(cache)
    return new_count


def _ingest(cache: dict, marketplace: str, items: set) -> int:
    """Insert (slug, id) tuples into cache. Return new-entry count."""
    added = 0
    with CACHE_LOCK:
        for slug, vid in items:
            key = f"{marketplace}:{vid}"
            if key in cache and cache[key]:
                continue
            cache[key] = {
                "title": slug_to_title(slug),
                "slug": slug,
                "source": "catalog-listing",
            }
            added += 1
    return added


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true",
                    help="Probe one marketplace shallowly without writing")
    ap.add_argument("--apply", action="store_true",
                    help="Walk all marketplaces and grow the cache")
    ap.add_argument("--site", choices=[m[0] for m in MARKETPLACES],
                    help="Only harvest this marketplace")
    ap.add_argument("--max-pages", type=int, default=60,
                    help="Pages per sort order (default 60)")
    ap.add_argument("--throttle", type=float, default=0.8,
                    help="Seconds between requests (default 0.8)")
    ap.add_argument("--parallel", action="store_true",
                    help="Harvest all marketplaces concurrently")
    ap.add_argument("--start-page", type=int, default=1,
                    help="Start each sort at this page (default 1). Use for "
                         "deep re-runs that skip already-cached pages.")
    ap.add_argument("--subcategories", action="store_true",
                    help="Walk dynamically-discovered subcategory slugs per "
                         "marketplace (separate pagination window from global "
                         "/search).")
    ap.add_argument("--authors", action="store_true",
                    help="Walk /user/<name>/portfolio for top authors per "
                         "marketplace (separate pagination window from "
                         "search and category surfaces).")
    ap.add_argument("--author-pages", type=int, default=40,
                    help="Max portfolio pages per author (default 40, "
                         "covers the typical top-author tail).")
    ap.add_argument("--max-authors", type=int, default=80,
                    help="Cap authors per marketplace (default 80).")
    args = ap.parse_args()

    if not (args.scan or args.apply):
        ap.print_help()
        return

    cache = load_cache()
    print(f"Cache before: {len(cache)} entries")

    sites = [(m, u) for m, u in MARKETPLACES if not args.site or m == args.site]

    if args.scan:
        site = sites[0]
        added = harvest_marketplace(site[0], site[1], 5, cache, args.throttle)
        print(f"\nSCAN result: +{added} new entries from {site[0]} (5 pages/sort)")
        return

    total_new = 0
    # --authors mode: walk top-author portfolios per marketplace.
    # Runs separately from --subcategories so we don't tangle the unit shape.
    if args.authors:
        max_workers = min(len(sites) * 4, 12) if args.parallel else 1
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {}
            for m, u in sites:
                authors = discover_authors(u, args.throttle)[: args.max_authors]
                print(f"  {m}: discovered {len(authors)} authors", flush=True)
                for username in authors:
                    fut = ex.submit(harvest_author, m, u, username,
                                    args.author_pages, cache, args.throttle)
                    futs[fut] = (m, username)
            for fut in as_completed(futs):
                m, uname = futs[fut]
                try:
                    added = fut.result()
                    total_new += added
                    if added:
                        print(f"  [{m}/{uname}] +{added}", flush=True)
                except Exception as e:
                    print(f"  [{m}/{uname}] FAILED: {e}", flush=True)
        save_cache(cache)
        print(f"\nDONE: {total_new} new entries added")
        print(f"Cache now: {len(cache)} entries total")
        return

    # Build the (marketplace, base_url, category) work units. Without
    # --subcategories: one unit per site (category=None). With it: one unit
    # per (site, subcategory) combination, discovered dynamically from each
    # marketplace's homepage.
    units = []
    for m, u in sites:
        if args.subcategories:
            cats = discover_subcategories(u, args.throttle)
            print(f"  {m}: discovered {len(cats)} subcategories", flush=True)
            for cat in cats:
                units.append((m, u, cat))
        else:
            units.append((m, u, None))

    if args.parallel and len(units) > 1:
        # Cap concurrency so we don't blow up Envato's edge or our local TCP
        max_workers = min(len(units), 12)
        with ThreadPoolExecutor(max_workers=max_workers) as ex:
            futs = {
                ex.submit(harvest_marketplace, m, u, args.max_pages,
                          cache, args.throttle, 5, args.start_page, cat): (m, cat)
                for m, u, cat in units
            }
            for fut in as_completed(futs):
                m, cat = futs[fut]
                label = f"{m}/{cat}" if cat else m
                try:
                    added = fut.result()
                    total_new += added
                    print(f"  [{label}] DONE: +{added} new entries", flush=True)
                except Exception as e:
                    print(f"  [{label}] FAILED: {e}", flush=True)
    else:
        for m, u, cat in units:
            added = harvest_marketplace(m, u, args.max_pages, cache,
                                        args.throttle, 5, args.start_page, cat)
            total_new += added
            label = f"{m}/{cat}" if cat else m
            print(f"  {label}: +{added} new entries", flush=True)

    save_cache(cache)
    print(f"\nDONE: {total_new} new entries added")
    print(f"Cache now: {len(cache)} entries total")


if __name__ == "__main__":
    main()
