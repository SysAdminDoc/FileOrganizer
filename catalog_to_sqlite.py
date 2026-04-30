#!/usr/bin/env python3
r"""catalog_to_sqlite.py - Convert marketplace_title_cache.json (large
sitemap-harvested catalog, possibly multi-GB) to a compact SQLite DB
suitable for the future FileOrganizer app.

Why SQLite over JSON for the full sitemap-harvested catalog:
  - 10M+ rows: JSON load takes 15+ sec and uses 8+ GB RAM
  - SQLite: O(log n) lookup against an indexed PK, no startup cost
  - File size: ~50% of equivalent JSON
  - Works in any language without parsing the whole file

Schema:
  catalog(
      key      TEXT PRIMARY KEY,    -- '<marketplace>:<id>'
      slug     TEXT,
      title    TEXT,
      source   TEXT,
      url      TEXT,
      status   INTEGER
  )

Usage:
  python catalog_to_sqlite.py marketplace_title_cache.json catalog.db
"""
import json
import sqlite3
import sys
import time
from pathlib import Path


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    if dst.exists():
        dst.unlink()

    print(f"Loading {src} ({src.stat().st_size:,} bytes)...")
    t0 = time.time()
    with src.open(encoding="utf-8") as f:
        cache = json.load(f)
    print(f"  loaded {len(cache):,} entries in {time.time()-t0:.1f}s")

    print(f"Writing {dst}...")
    t0 = time.time()
    conn = sqlite3.connect(dst)
    conn.execute("PRAGMA journal_mode=OFF")
    conn.execute("PRAGMA synchronous=OFF")
    conn.execute("PRAGMA cache_size=-262144")  # 256 MB
    conn.execute("""
        CREATE TABLE catalog (
            key    TEXT PRIMARY KEY,
            slug   TEXT,
            title  TEXT,
            source TEXT,
            url    TEXT,
            status INTEGER
        )
    """)

    rows = []
    for k, v in cache.items():
        if not isinstance(v, dict):
            continue
        rows.append((
            k,
            v.get("slug") or "",
            v.get("title") or "",
            v.get("source") or "",
            v.get("url") or "",
            v.get("status") or 0,
        ))
        if len(rows) >= 50000:
            conn.executemany(
                "INSERT OR REPLACE INTO catalog VALUES (?,?,?,?,?,?)", rows
            )
            rows.clear()
    if rows:
        conn.executemany(
            "INSERT OR REPLACE INTO catalog VALUES (?,?,?,?,?,?)", rows
        )

    conn.commit()
    conn.execute("CREATE INDEX idx_slug ON catalog(slug)")
    conn.execute("ANALYZE")
    conn.commit()
    conn.close()

    elapsed = time.time() - t0
    size = dst.stat().st_size
    print(f"  wrote {dst} ({size:,} bytes) in {elapsed:.1f}s")
    print(f"  compression ratio: {src.stat().st_size / size:.2f}x")


if __name__ == "__main__":
    main()
