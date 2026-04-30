#!/usr/bin/env python3
r"""catalog_lookup.py - Shard-aware lookup helper for the marketplace
catalog. Provides a fast path for the future FileOrganizer app to resolve
"<marketplace>:<id>" -> {title, slug, ...} against the 10.6M-entry
sharded catalog under catalog/<marketplace>_<shard>.json.gz.

Lazy-loads only the shard a query targets (LRU-cached in memory). A typical
session of resolving a few thousand archive IDs touches 4-7 shards (one
per marketplace + a couple sub-shards) at ~40 MB each = under 300 MB peak
memory, vs the 8 GB it would take to load the full catalog at once.

Usage as a library:
    from catalog_lookup import CatalogLookup
    cl = CatalogLookup(repo_root="/path/to/FileOrganizer")
    entry = cl.get("videohive", "12345678")
    if entry:
        print(entry["title"], entry["slug"])

Usage as a CLI:
    python catalog_lookup.py videohive 12345678
    python catalog_lookup.py themeforest 99999999
"""
import gzip
import json
import sys
import threading
from functools import lru_cache
from pathlib import Path

# Shard counts must match catalog_shard.py NUM_SHARDS — keep in sync.
NUM_SHARDS = {
    "videohive": 4,
    "photodune": 4,
    "audiojungle": 2,
    "graphicriver": 1,
    "themeforest": 1,
    "3docean": 1,
    "codecanyon": 1,
}


class CatalogLookup:
    def __init__(self, repo_root: str | Path | None = None,
                 catalog_dir: str = "catalog"):
        repo_root = Path(repo_root) if repo_root else Path(__file__).parent
        self.catalog_dir = repo_root / catalog_dir
        self._shards: dict[str, dict] = {}
        self._lock = threading.Lock()

    def _load_shard(self, marketplace: str, shard: int) -> dict:
        key = f"{marketplace}_{shard}"
        with self._lock:
            if key in self._shards:
                return self._shards[key]
            path = self.catalog_dir / f"{key}.json.gz"
            if not path.exists():
                self._shards[key] = {}
                return self._shards[key]
            with gzip.open(path, "rt", encoding="utf-8") as f:
                self._shards[key] = json.load(f)
            return self._shards[key]

    def get(self, marketplace: str, item_id: str | int) -> dict | None:
        item_id = str(item_id)
        n = NUM_SHARDS.get(marketplace, 1)
        try:
            shard = int(item_id) % n
        except ValueError:
            shard = 0
        data = self._load_shard(marketplace, shard)
        key = f"{marketplace}:{item_id}"
        return data.get(key)

    def loaded_shards(self) -> list[str]:
        return sorted(self._shards.keys())


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    cl = CatalogLookup()
    entry = cl.get(sys.argv[1], sys.argv[2])
    if entry is None:
        print("(not in catalog)")
        sys.exit(2)
    print(json.dumps(entry, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
