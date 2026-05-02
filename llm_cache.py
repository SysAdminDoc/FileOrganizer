#!/usr/bin/env python3
"""
llm_cache.py — LLM response caching for NEXT-44.

Caches LLM classification responses by (fingerprint, model_id, prompt_hash)
to eliminate >90% of API calls on re-runs of stable asset libraries.
"""
import sqlite3
import hashlib
import json
import time
import os
from pathlib import Path
from typing import Optional

# Use organize_moves.db as the persistent cache
DB_FILE = Path(__file__).parent / 'organize_moves.db'
DEFAULT_TTL = 30 * 86400  # 30 days in seconds


def get_cache_db() -> sqlite3.Connection:
    """Open the cache database."""
    con = sqlite3.connect(str(DB_FILE))
    con.row_factory = sqlite3.Row
    return con


def prompt_hash(prompt_text: str) -> str:
    """Compute SHA-256 hash of prompt text for cache validation."""
    return hashlib.sha256(prompt_text.encode()).hexdigest()[:16]


def folder_fingerprint(folder_path: str) -> Optional[str]:
    """
    Compute folder fingerprint (SHA-256 of sorted file paths + hashes).
    Returns None if folder is empty or inaccessible.
    
    Note: For NEXT-15 integration, this should call asset_db.folder_fingerprint()
    to ensure consistency with the fingerprint DB.
    """
    try:
        from asset_db import folder_fingerprint as _fp
        fp, _ = _fp(folder_path)
        return fp
    except Exception:
        # Fallback: simplified fingerprint
        try:
            files = sorted(Path(folder_path).rglob('*'))
            if not files:
                return None
            hashes = hashlib.sha256()
            for f in files:
                if f.is_file():
                    hashes.update(f.relative_to(folder_path).as_posix().encode())
            return hashes.hexdigest()[:16]
        except Exception:
            return None


def lookup_cached(folder_path: str, model_id: str, prompt_text: str) -> Optional[dict]:
    """
    Lookup LLM cache by (fingerprint, model_id, prompt_hash).
    
    Returns the cached response (dict) if found and not expired, or None.
    Updates accessed_at on cache hit.
    """
    fp = folder_fingerprint(folder_path)
    if not fp:
        return None
    
    p_hash = prompt_hash(prompt_text)
    con = get_cache_db()
    try:
        row = con.execute(
            "SELECT response_json, accessed_at FROM llm_cache "
            "WHERE fingerprint = ? AND model_id = ? AND prompt_hash = ?",
            (fp, model_id, p_hash)
        ).fetchone()
        
        if not row:
            return None
        
        # Check TTL (only if accessed_at + TTL < now)
        now = int(time.time())
        if now - row['accessed_at'] > DEFAULT_TTL:
            # Expired; delete and return None
            con.execute(
                "DELETE FROM llm_cache "
                "WHERE fingerprint = ? AND model_id = ? AND prompt_hash = ?",
                (fp, model_id, p_hash)
            )
            con.commit()
            return None
        
        # Cache hit; update accessed_at and return response
        con.execute(
            "UPDATE llm_cache SET accessed_at = ? "
            "WHERE fingerprint = ? AND model_id = ? AND prompt_hash = ?",
            (now, fp, model_id, p_hash)
        )
        con.commit()
        
        try:
            return json.loads(row['response_json'])
        except json.JSONDecodeError:
            return None
    finally:
        con.close()


def store_cached(folder_path: str, model_id: str, prompt_text: str, response: dict) -> bool:
    """
    Store LLM response in cache by (fingerprint, model_id, prompt_hash).
    
    Returns True on success, False if the folder fingerprint cannot be computed.
    """
    fp = folder_fingerprint(folder_path)
    if not fp:
        return False
    
    p_hash = prompt_hash(prompt_text)
    now = int(time.time())
    
    con = get_cache_db()
    try:
        con.execute(
            "INSERT OR REPLACE INTO llm_cache "
            "(fingerprint, model_id, prompt_hash, response_json, created_at, accessed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (fp, model_id, p_hash, json.dumps(response), now, now)
        )
        con.commit()
        return True
    except Exception:
        return False
    finally:
        con.close()


def cleanup_expired(max_age_days: int = 30) -> int:
    """
    Remove cache entries older than max_age_days.
    Called on startup.
    
    Returns number of rows deleted.
    """
    con = get_cache_db()
    try:
        now = int(time.time())
        cutoff = now - (max_age_days * 86400)
        cur = con.execute(
            "DELETE FROM llm_cache WHERE accessed_at < ?",
            (cutoff,)
        )
        con.commit()
        return cur.rowcount
    finally:
        con.close()


def get_cache_stats() -> dict:
    """Return cache statistics (hit rate, size, etc.)."""
    con = get_cache_db()
    try:
        total = con.execute("SELECT COUNT(*) as cnt FROM llm_cache").fetchone()['cnt']
        size_bytes = con.execute(
            "SELECT SUM(LENGTH(response_json)) as sz FROM llm_cache"
        ).fetchone()['sz'] or 0
        
        # Count by model
        by_model = {}
        for row in con.execute(
            "SELECT model_id, COUNT(*) as cnt FROM llm_cache GROUP BY model_id"
        ):
            by_model[row['model_id']] = row['cnt']
        
        return {
            'total_entries': total,
            'size_bytes': size_bytes,
            'by_model': by_model,
        }
    finally:
        con.close()
