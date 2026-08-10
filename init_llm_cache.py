#!/usr/bin/env python3
"""Initialize the canonical LLM cache database for NEXT-44."""

from llm_cache import DB_FILE, get_cache_db

def init_llm_cache():
    """Create or migrate the cache schema at llm_cache.DB_FILE."""
    con = get_cache_db()
    con.close()
    print(f"✓ llm_cache table initialized in {DB_FILE}")

if __name__ == '__main__':
    init_llm_cache()
