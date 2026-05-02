#!/usr/bin/env python3
"""
provider_cost_manager.py — Cost capping, backoff, and failover for AI providers (NEXT-34).

Features:
- Daily cost budget per provider (default $10.00/day, configurable)
- Exponential backoff on 429/5xx errors (60-min lockout max)
- Automatic failover chain: DeepSeek → GitHub Models → Ollama
- Per-provider rate-limit tracking (X-RateLimit-* headers)
"""
import os
import sqlite3
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Dict
from pathlib import Path

from fileorganizer.config import _APP_DATA_DIR

log = logging.getLogger(__name__)

_COST_DB = os.path.join(_APP_DATA_DIR, 'provider_costs.db')
_COST_BUDGET_PER_DAY = 10.00  # USD, configurable
_MAX_BACKOFF_SECONDS = 3600   # 60 minutes


def _get_db():
    """Get or create the cost tracking database."""
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(_COST_DB, timeout=30.0)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def _init_db():
    """Initialize cost tracking schema."""
    conn = _get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_costs (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            provider        TEXT    NOT NULL,
            date            TEXT    NOT NULL,
            cost_usd        REAL    NOT NULL DEFAULT 0.0,
            request_count   INTEGER NOT NULL DEFAULT 0,
            ts_updated      TEXT    NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_backoff (
            provider        TEXT PRIMARY KEY,
            locked_until    TEXT,
            retry_count     INTEGER DEFAULT 0,
            reason          TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS provider_rate_limits (
            provider        TEXT PRIMARY KEY,
            limit_count     INTEGER,
            remaining_count INTEGER,
            reset_epoch     REAL,
            ts_checked      TEXT
        )
    """)
    conn.commit()
    conn.close()


_init_db()


def _today() -> str:
    """Return today's date as YYYY-MM-DD."""
    return datetime.now(timezone.utc).strftime('%Y-%m-%d')


def _now() -> str:
    """Return current UTC timestamp."""
    return datetime.now(timezone.utc).isoformat() + 'Z'


def record_api_call(provider: str, tokens_used: int, model: str = None):
    """Record an API call cost for daily budget tracking.
    
    Estimates cost based on provider and token count:
    - DeepSeek: $0.55 per 1M input tokens, $2.19 per 1M output (avg 0.0007)
    - GitHub: $0.75 per 1M tokens
    - Ollama: $0.00 (local)
    """
    if provider == 'ollama':
        return  # No cost
    
    cost_per_token = {
        'deepseek': 0.0007,
        'github': 0.00075,
    }.get(provider, 0.001)  # conservative default
    
    cost = tokens_used * cost_per_token
    
    conn = _get_db()
    today = _today()
    
    conn.execute("""
        INSERT OR REPLACE INTO provider_costs
            (provider, date, cost_usd, request_count, ts_updated)
        SELECT
            ?, ?, 
            COALESCE((SELECT cost_usd FROM provider_costs 
                      WHERE provider=? AND date=?), 0) + ?,
            COALESCE((SELECT request_count FROM provider_costs 
                      WHERE provider=? AND date=?), 0) + 1,
            ?
        WHERE NOT EXISTS (
            SELECT 1 FROM provider_costs WHERE provider=? AND date=?
        )
    """, (provider, today, provider, today, cost, provider, today, _now(), provider, today))
    
    if conn.total_changes == 0:
        # Row already exists, update it
        conn.execute("""
            UPDATE provider_costs
            SET cost_usd = cost_usd + ?, request_count = request_count + 1, ts_updated = ?
            WHERE provider = ? AND date = ?
        """, (cost, _now(), provider, today))
    
    conn.commit()
    conn.close()


def get_daily_cost(provider: str) -> float:
    """Get today's accumulated cost for a provider."""
    conn = _get_db()
    row = conn.execute(
        "SELECT cost_usd FROM provider_costs WHERE provider=? AND date=?",
        (provider, _today())
    ).fetchone()
    conn.close()
    return row[0] if row else 0.0


def is_over_budget(provider: str, daily_budget: float = _COST_BUDGET_PER_DAY) -> bool:
    """Check if provider has exceeded daily budget."""
    return get_daily_cost(provider) >= daily_budget


def set_backoff(provider: str, seconds: int, reason: str = "Rate limit or error"):
    """Lock a provider for exponential backoff (max 60 min)."""
    lockout = min(seconds, _MAX_BACKOFF_SECONDS)
    locked_until = (datetime.now(timezone.utc) + timedelta(seconds=lockout)).isoformat() + 'Z'
    
    conn = _get_db()
    conn.execute("""
        INSERT OR REPLACE INTO provider_backoff (provider, locked_until, retry_count, reason)
        VALUES (?, ?, COALESCE((SELECT retry_count FROM provider_backoff WHERE provider=?), 0) + 1, ?)
    """, (provider, locked_until, provider, reason))
    conn.commit()
    conn.close()
    
    log.warning(f"{provider} locked for {lockout}s: {reason}")


def is_locked(provider: str) -> Tuple[bool, Optional[float]]:
    """Check if provider is in backoff. Returns (is_locked, seconds_remaining)."""
    conn = _get_db()
    row = conn.execute(
        "SELECT locked_until FROM provider_backoff WHERE provider=?",
        (provider,)
    ).fetchone()
    conn.close()
    
    if not row or not row[0]:
        return False, None
    
    locked_until = datetime.fromisoformat(row[0].replace('Z', '+00:00'))
    now = datetime.now(timezone.utc)
    
    if now >= locked_until:
        # Backoff expired
        conn = _get_db()
        conn.execute("UPDATE provider_backoff SET locked_until=NULL WHERE provider=?", (provider,))
        conn.commit()
        conn.close()
        return False, None
    
    remaining = (locked_until - now).total_seconds()
    return True, remaining


def clear_backoff(provider: str):
    """Clear backoff for a provider (for manual recovery)."""
    conn = _get_db()
    conn.execute("UPDATE provider_backoff SET locked_until=NULL, retry_count=0 WHERE provider=?", (provider,))
    conn.commit()
    conn.close()


def get_failover_chain() -> list:
    """Return ordered failover chain: [primary, secondary, tertiary]."""
    return ['deepseek', 'github', 'ollama']


def get_next_available_provider(skip: list = None) -> Optional[str]:
    """Get the next available provider from failover chain.
    
    Args:
        skip: list of provider names to skip (already tried)
    
    Returns provider name or None if all locked/over-budget.
    """
    skip = skip or []
    
    for provider in get_failover_chain():
        if provider in skip:
            continue
        
        is_locked_flag, _ = is_locked(provider)
        if is_locked_flag:
            continue
        
        if is_over_budget(provider):
            continue
        
        return provider
    
    return None


def handle_rate_limit_response(provider: str, headers: Dict[str, str]):
    """Handle 429 response by tracking rate limit and setting backoff.
    
    Args:
        provider: provider name
        headers: HTTP response headers (case-insensitive dict-like)
    """
    conn = _get_db()
    
    # Extract rate-limit info from response headers
    limit = headers.get('X-RateLimit-Limit') or headers.get('x-ratelimit-limit')
    remaining = headers.get('X-RateLimit-Remaining') or headers.get('x-ratelimit-remaining')
    reset_epoch = headers.get('X-RateLimit-Reset') or headers.get('x-ratelimit-reset')
    
    if limit or remaining or reset_epoch:
        try:
            conn.execute("""
                INSERT OR REPLACE INTO provider_rate_limits
                    (provider, limit_count, remaining_count, reset_epoch, ts_checked)
                VALUES (?, ?, ?, ?, ?)
            """, (
                provider,
                int(limit) if limit else None,
                int(remaining) if remaining else None,
                float(reset_epoch) if reset_epoch else None,
                _now()
            ))
        except (ValueError, TypeError):
            pass
    
    conn.commit()
    conn.close()
    
    # Set backoff: start with 2 seconds, exponential retry
    retry_count = _get_retry_count(provider)
    backoff_seconds = min(2 ** retry_count, _MAX_BACKOFF_SECONDS)
    set_backoff(provider, backoff_seconds, "Rate limit 429")


def _get_retry_count(provider: str) -> int:
    """Get current retry count for exponential backoff calculation."""
    conn = _get_db()
    row = conn.execute(
        "SELECT retry_count FROM provider_backoff WHERE provider=?",
        (provider,)
    ).fetchone()
    conn.close()
    return row[0] if row else 0


def get_cost_summary() -> Dict[str, Dict]:
    """Get cost summary for all providers (today)."""
    conn = _get_db()
    rows = conn.execute(
        """SELECT provider, cost_usd, request_count 
           FROM provider_costs WHERE date=?""",
        (_today(),)
    ).fetchall()
    conn.close()
    
    return {
        row[0]: {
            'cost_usd': row[1],
            'requests': row[2],
            'budget': _COST_BUDGET_PER_DAY,
            'remaining': max(0, _COST_BUDGET_PER_DAY - row[1]),
        }
        for row in rows
    }
