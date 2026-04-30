"""FileOrganizer — Two-phase commit journal for GUI Apply operations.

Before any move touches disk, every planned move is written to organize_moves.db
as 'pending'.  After each successful or failed move the record is updated.
On clean completion the run is cleared.  Any remaining 'pending' rows after
restart indicate a crash mid-apply and trigger the resume prompt.
"""
import os, sqlite3
from datetime import datetime, timezone

from fileorganizer.config import _APP_DATA_DIR

_JOURNAL_DB = os.path.join(_APP_DATA_DIR, 'organize_moves.db')


def _init():
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    con = sqlite3.connect(_JOURNAL_DB)
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
    con = sqlite3.connect(_JOURNAL_DB)
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
    con = sqlite3.connect(_JOURNAL_DB)
    con.execute(
        "UPDATE moves SET status=?, ts_done=? WHERE run_id=? AND ri=?",
        (status, _now(), run_id, ri)
    )
    con.commit()
    con.close()


def clear_run(run_id: str):
    """Delete all journal records for this run (called on clean completion)."""
    con = sqlite3.connect(_JOURNAL_DB)
    con.execute("DELETE FROM moves WHERE run_id=?", (run_id,))
    con.commit()
    con.close()


def clear_all():
    """Discard every pending record (user chose to start fresh)."""
    con = sqlite3.connect(_JOURNAL_DB)
    con.execute("DELETE FROM moves WHERE status='pending'")
    con.commit()
    con.close()


def get_pending_summary() -> list:
    """Return [(run_id, count)] for runs that still have pending moves."""
    con = sqlite3.connect(_JOURNAL_DB)
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
    con = sqlite3.connect(_JOURNAL_DB)
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
