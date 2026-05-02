"""FileOrganizer — Two-phase commit journal for GUI Apply operations.

Before any move touches disk, every planned move is written to organize_moves.db
as 'pending'.  After each successful or failed move the record is updated.
On clean completion the run is cleared.  Any remaining 'pending' rows after
restart indicate a crash mid-apply and trigger the resume prompt.

NEXT-37: Retention policy and periodic vacuum to prevent database bloat.
"""
import os, sqlite3
from datetime import datetime, timezone, timedelta

from fileorganizer.config import _APP_DATA_DIR

_JOURNAL_DB = os.path.join(_APP_DATA_DIR, 'organize_moves.db')

# 30s timeout lets the GUI thread retry instead of throwing when the worker
# thread holds the write lock briefly.
_CONN_TIMEOUT = 30.0

# NEXT-37: Retention policy (days)
_RETENTION_DAYS = 90  # configurable, default 90 days



def _connect():
    con = sqlite3.connect(_JOURNAL_DB, timeout=_CONN_TIMEOUT)
    # WAL: enables concurrent reader (GUI) + writer (worker) without deadlock.
    # NORMAL: durable on power loss except for the last few committed txns —
    #   acceptable since plan_run is rebuilt from on-disk state on resume.
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def _init():
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    con = _connect()
    con.execute("""
        CREATE TABLE IF NOT EXISTS moves (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id       TEXT    NOT NULL,
            ri           INTEGER NOT NULL,
            folder_name  TEXT    NOT NULL,
            src          TEXT    NOT NULL,
            dst          TEXT    NOT NULL,
            category     TEXT    NOT NULL,
            confidence   REAL    NOT NULL DEFAULT 0,
            cleaned_name TEXT    NOT NULL DEFAULT '',
            status       TEXT    NOT NULL DEFAULT 'pending',
            ts_planned   TEXT    NOT NULL,
            ts_done      TEXT
        )
    """)
    con.commit()
    con.close()


_init()


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ── Journal operations ─────────────────────────────────────────────────────────

def plan_run(run_id: str, work_items: list):
    """Write all work items as 'pending' for this run before any move starts."""
    now = _now()
    con = _connect()
    for ri, it in work_items:
        con.execute(
            """
            INSERT INTO moves
                (run_id, ri, folder_name, src, dst, category,
                 confidence, cleaned_name, status, ts_planned)
            VALUES (?,?,?,?,?,?,?,?,'pending',?)
            """,
            (
                run_id, ri,
                getattr(it, 'folder_name', ''),
                getattr(it, 'full_source_path', ''),
                getattr(it, 'full_dest_path', ''),
                getattr(it, 'category', ''),
                float(getattr(it, 'confidence', 0)),
                getattr(it, 'cleaned_name', ''),
                now,
            )
        )
    con.commit()
    con.close()


def mark_done(run_id: str, ri: int, status: str):
    """Update a single move record to 'done' or 'error'."""
    con = _connect()
    con.execute(
        "UPDATE moves SET status=?, ts_done=? WHERE run_id=? AND ri=?",
        (status, _now(), run_id, ri)
    )
    con.commit()
    con.close()


def clear_run(run_id: str):
    """Delete all journal records for this run (called on clean completion)."""
    con = _connect()
    con.execute("DELETE FROM moves WHERE run_id=?", (run_id,))
    con.commit()
    con.close()


def clear_all():
    """Discard every pending record (user chose to start fresh)."""
    con = _connect()
    con.execute("DELETE FROM moves WHERE status='pending'")
    con.commit()
    con.close()


def get_pending_summary() -> list:
    """Return [(run_id, count)] for runs that still have pending moves."""
    con = _connect()
    rows = con.execute(
        """
        SELECT run_id, COUNT(*) AS n
        FROM moves WHERE status = 'pending'
        GROUP BY run_id
        ORDER BY MIN(ts_planned)
        """
    ).fetchall()
    con.close()
    return [(r[0], r[1]) for r in rows]


def get_pending_moves(run_id: str) -> list:
    """Return all pending moves for a run as dicts (src/dst/etc.)."""
    con = _connect()
    rows = con.execute(
        """
        SELECT ri, folder_name, src, dst, category, confidence, cleaned_name
        FROM moves WHERE run_id=? AND status='pending'
        ORDER BY id
        """,
        (run_id,)
    ).fetchall()
    con.close()
    return [
        {
            'ri':          r[0],
            'folder_name': r[1],
            'src':         r[2],
            'dst':         r[3],
            'category':    r[4],
            'confidence':  r[5],
            'cleaned_name': r[6],
        }
        for r in rows
    ]


def cleanup_expired(days: int = _RETENTION_DAYS):
    """NEXT-37: Delete journal records older than retention period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')
    con = _connect()
    con.execute(
        "DELETE FROM moves WHERE status='done' AND ts_done < ?",
        (cutoff_str,)
    )
    con.commit()
    con.close()


def vacuum():
    """NEXT-37: Reclaim disk space by vacuuming the database."""
    con = _connect()
    con.execute("VACUUM")
    con.commit()
    con.close()

