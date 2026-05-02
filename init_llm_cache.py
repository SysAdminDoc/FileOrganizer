#!/usr/bin/env python3
"""Initialize LLM cache table for NEXT-44."""
import sqlite3
import os

DB_FILE = 'organize_moves.db'

def init_llm_cache():
    """Add llm_cache table if it doesn't exist."""
    con = sqlite3.connect(DB_FILE)
    con.execute("""
        CREATE TABLE IF NOT EXISTS llm_cache (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint  TEXT NOT NULL,
            model_id     TEXT NOT NULL,
            prompt_hash  TEXT NOT NULL,
            response_json TEXT NOT NULL,
            created_at   INTEGER NOT NULL,
            accessed_at  INTEGER NOT NULL,
            UNIQUE(fingerprint, model_id, prompt_hash)
        )
    """)
    con.execute("CREATE INDEX IF NOT EXISTS idx_llm_fingerprint ON llm_cache(fingerprint)")
    con.execute("CREATE INDEX IF NOT EXISTS idx_llm_accessed ON llm_cache(accessed_at)")
    con.commit()
    con.close()
    print(f"✓ llm_cache table initialized in {DB_FILE}")

if __name__ == '__main__':
    if os.path.exists(DB_FILE):
        init_llm_cache()
    else:
        print(f"Note: {DB_FILE} does not exist yet (will be created on first use)")
