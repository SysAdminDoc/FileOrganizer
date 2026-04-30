#!/usr/bin/env python3
r"""catalog_shard.py - Split the full marketplace cache into git-safe
gzipped shards under 50MB each.

Output layout:
  catalog/<marketplace>_<shard>.json.gz

Where <shard> is `id_int % NUM_SHARDS` for that marketplace. Lookup is:
  shard = int(item_id) % NUM_SHARDS_FOR_MARKETPLACE[marketplace]
  load `catalog/<marketplace>_<shard>.json.gz`

Shard count tuned to keep each file under ~50MB compressed:
  videohive:  4 shards (~40 MB each)
  photodune:  4 shards (~40 MB each)
  audiojungle: 2 shards (~32 MB each)
  others:     1 shard

Usage:
  python catalog_shard.py marketplace_title_cache.full.json catalog/
"""
import gzip
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

NUM_SHARDS = {
    "videohive": 4,
    "photodune": 4,
    "audiojungle": 2,
    "graphicriver": 1,
    "themeforest": 1,
    "3docean": 1,
    "codecanyon": 1,
}


def main() -> None:
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)
    src = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading {src} ({src.stat().st_size:,} bytes)...")
    t0 = time.time()
    with src.open(encoding="utf-8") as f:
        cache = json.load(f)
    print(f"  loaded {len(cache):,} entries in {time.time()-t0:.1f}s")

    # Bucket by (marketplace, shard)
    buckets: dict[tuple[str, int], dict] = defaultdict(dict)
    for k, v in cache.items():
        m, _, vid = k.partition(":")
        try:
            shard = int(vid) % NUM_SHARDS.get(m, 1)
        except ValueError:
            shard = 0
        buckets[(m, shard)][k] = v

    print(f"\nWriting shards to {out_dir}/...")
    total_size = 0
    for (m, shard), data in sorted(buckets.items()):
        fname = out_dir / f"{m}_{shard}.json.gz"
        with gzip.open(fname, "wt", encoding="utf-8", compresslevel=9) as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        size = fname.stat().st_size
        total_size += size
        print(f"  {fname.name}: {len(data):,} entries, {size:,} bytes "
              f"({size/1024/1024:.1f} MB)")

    print(f"\nTOTAL: {total_size:,} bytes ({total_size/1024/1024:.1f} MB) "
          f"across {len(buckets)} shards")


if __name__ == "__main__":
    main()
