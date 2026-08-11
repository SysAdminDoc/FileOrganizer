"""FileOrganizer — Two-phase commit journal for GUI Apply operations.

Before any move touches disk, every planned move is written to organize_moves.db
as 'pending'.  After each successful or failed move the record is updated.
On clean completion the run is cleared.  Any remaining 'pending' rows after
restart indicate a crash mid-apply and trigger the resume prompt.

NEXT-37: Retention policy and periodic vacuum to prevent database bloat.
"""
import json
import os
import shutil
import sqlite3
import threading
from datetime import datetime, timezone, timedelta

from fileorganizer.config import _APP_DATA_DIR
from fileorganizer.path_safety import (
    PathSafetyError,
    source_signature,
    validate_move,
    validate_source_signature,
)

_JOURNAL_DB = os.path.join(_APP_DATA_DIR, 'organize_moves.db')

# 30s timeout lets the GUI thread retry instead of throwing when the worker
# thread holds the write lock briefly.
_CONN_TIMEOUT = 30.0

# NEXT-37: Retention policy (days)
_RETENTION_DAYS = 90  # configurable, default 90 days
_SCHEMA_LOCK = threading.Lock()
_INITIALIZED_DB = None



def _open_connection():
    con = sqlite3.connect(_JOURNAL_DB, timeout=_CONN_TIMEOUT)
    # WAL: enables concurrent reader (GUI) + writer (worker) without deadlock.
    # NORMAL: durable on power loss except for the last few committed txns —
    #   acceptable since plan_run is rebuilt from on-disk state on resume.
    con.execute("PRAGMA journal_mode = WAL")
    con.execute("PRAGMA synchronous = NORMAL")
    return con


def _init():
    """Create or migrate the active journal lazily on first use."""
    global _INITIALIZED_DB
    journal_path = os.path.abspath(_JOURNAL_DB)
    if _INITIALIZED_DB == journal_path:
        return
    with _SCHEMA_LOCK:
        if _INITIALIZED_DB == journal_path:
            return
        os.makedirs(os.path.dirname(journal_path) or '.', exist_ok=True)
        con = _open_connection()
        try:
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
                    source_root  TEXT    NOT NULL DEFAULT '',
                    dest_root    TEXT    NOT NULL DEFAULT '',
                    source_signature TEXT NOT NULL DEFAULT '{}',
                    destination_signature TEXT NOT NULL DEFAULT '{}',
                    merge_manifest TEXT NOT NULL DEFAULT '[]',
                    status       TEXT    NOT NULL DEFAULT 'pending',
                    ts_planned   TEXT    NOT NULL,
                    ts_done      TEXT,
                    ts_undone    TEXT
                )
            """)
            con.execute("""
                CREATE TABLE IF NOT EXISTS action_moves (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id    TEXT    NOT NULL,
                    source       TEXT    NOT NULL,
                    destination  TEXT    NOT NULL,
                    source_root  TEXT    NOT NULL,
                    dest_root    TEXT    NOT NULL,
                    source_signature TEXT NOT NULL DEFAULT '{}',
                    destination_signature TEXT NOT NULL DEFAULT '{}',
                    status       TEXT    NOT NULL DEFAULT 'pending',
                    error        TEXT    NOT NULL DEFAULT '',
                    ts_planned   TEXT    NOT NULL,
                    ts_done      TEXT,
                    ts_undone    TEXT
                )
            """)
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_action_moves_action "
                "ON action_moves(action_id, id)"
            )
            existing = {row[1] for row in con.execute("PRAGMA table_info(moves)").fetchall()}
            for column, definition in {
                'source_root': "ALTER TABLE moves ADD COLUMN source_root TEXT NOT NULL DEFAULT ''",
                'dest_root': "ALTER TABLE moves ADD COLUMN dest_root TEXT NOT NULL DEFAULT ''",
                'source_signature': "ALTER TABLE moves ADD COLUMN source_signature TEXT NOT NULL DEFAULT '{}'",
                'destination_signature': "ALTER TABLE moves ADD COLUMN destination_signature TEXT NOT NULL DEFAULT '{}'",
                'merge_manifest': "ALTER TABLE moves ADD COLUMN merge_manifest TEXT NOT NULL DEFAULT '[]'",
                'ts_undone': "ALTER TABLE moves ADD COLUMN ts_undone TEXT",
            }.items():
                if column not in existing:
                    con.execute(definition)

            action_existing = {
                row[1] for row in con.execute("PRAGMA table_info(action_moves)").fetchall()
            }
            for column, definition in {
                'destination_signature': "ALTER TABLE action_moves ADD COLUMN destination_signature TEXT NOT NULL DEFAULT '{}'",
                'ts_undone': "ALTER TABLE action_moves ADD COLUMN ts_undone TEXT",
            }.items():
                if column not in action_existing:
                    con.execute(definition)
            con.commit()
            _INITIALIZED_DB = journal_path
        finally:
            con.close()


def _connect():
    _init()
    return _open_connection()


def _now() -> str:
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


# ── Journal operations ─────────────────────────────────────────────────────────

def plan_run(run_id: str, work_items: list):
    """Write all work items as 'pending' for this run before any move starts."""
    now = _now()
    con = _connect()
    try:
        for ri, it in work_items:
            src = getattr(it, 'full_source_path', '')
            dst = getattr(it, 'full_dest_path', '')
            source_root = getattr(it, 'source_root', '') or os.path.dirname(src)
            dest_root = getattr(it, 'dest_root', '')
            try:
                signature = source_signature(src)
            except (OSError, PathSafetyError):
                signature = {}
            con.execute(
                """
                INSERT INTO moves
                    (run_id, ri, folder_name, src, dst, category,
                     confidence, cleaned_name, source_root, dest_root,
                     source_signature, status, ts_planned)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,'pending',?)
                """,
                (
                    run_id, ri,
                    getattr(it, 'folder_name', ''),
                    src, dst,
                    getattr(it, 'category', ''),
                    float(getattr(it, 'confidence', 0)),
                    getattr(it, 'cleaned_name', ''),
                    source_root, dest_root, json.dumps(signature, sort_keys=True),
                    now,
                )
            )
        con.commit()
    finally:
        con.close()


def mark_done(
    run_id: str,
    ri: int,
    status: str,
    *,
    destination_signature: dict | None = None,
    merge_manifest: list | None = None,
):
    """Update one move and retain the identity needed for a later undo."""
    con = _connect()
    try:
        assignments = ['status=?', 'ts_done=?', 'ts_undone=NULL']
        parameters: list = [status, _now()]
        if destination_signature is not None:
            assignments.append('destination_signature=?')
            parameters.append(json.dumps(destination_signature, sort_keys=True))
        if merge_manifest is not None:
            assignments.append('merge_manifest=?')
            parameters.append(json.dumps(merge_manifest, sort_keys=True))
        parameters.extend([run_id, ri])
        con.execute(
            f"UPDATE moves SET {', '.join(assignments)} WHERE run_id=? AND ri=?",
            parameters,
        )
        con.commit()
    finally:
        con.close()


def clear_run(run_id: str):
    """Remove incomplete rows while retaining completed history for undo."""
    con = _connect()
    try:
        con.execute(
            "DELETE FROM moves WHERE run_id=? AND status NOT IN ('done', 'undone')",
            (run_id,),
        )
        con.commit()
    finally:
        con.close()


def clear_all():
    """Discard every pending record (user chose to start fresh)."""
    con = _connect()
    try:
        con.execute("DELETE FROM moves WHERE status='pending'")
        con.commit()
    finally:
        con.close()


def get_pending_summary() -> list:
    """Return [(run_id, count)] for runs that still have pending moves."""
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT run_id, COUNT(*) AS n
            FROM moves WHERE status = 'pending'
            GROUP BY run_id
            ORDER BY MIN(ts_planned)
            """
        ).fetchall()
        return [(r[0], r[1]) for r in rows]
    finally:
        con.close()


def get_pending_moves(run_id: str) -> list:
    """Return all pending moves for a run as dicts (src/dst/etc.)."""
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT ri, folder_name, src, dst, category, confidence, cleaned_name,
                   source_root, dest_root, source_signature
            FROM moves WHERE run_id=? AND status='pending'
            ORDER BY id
            """,
            (run_id,)
        ).fetchall()
        return [
            {
                'ri':          r[0],
                'folder_name': r[1],
                'src':         r[2],
                'dst':         r[3],
                'category':    r[4],
                'confidence':  r[5],
                'cleaned_name': r[6],
                'source_root': r[7],
                'dest_root': r[8],
                'source_signature': json.loads(r[9] or '{}'),
            }
            for r in rows
        ]
    finally:
        con.close()


def plan_action_move(
    action_id: str,
    source: str,
    destination: str,
    source_root: str,
    dest_root: str,
    source_signature: dict,
) -> int:
    """Persist one standalone move before the filesystem is changed."""
    con = _connect()
    try:
        cursor = con.execute(
            """
            INSERT INTO action_moves
                (action_id, source, destination, source_root, dest_root,
                 source_signature, status, ts_planned)
            VALUES (?,?,?,?,?,?,'pending',?)
            """,
            (
                action_id,
                source,
                destination,
                source_root,
                dest_root,
                json.dumps(source_signature, sort_keys=True),
                _now(),
            ),
        )
        con.commit()
        if cursor.lastrowid is None:
            raise RuntimeError("action move journal did not return an id")
        return int(cursor.lastrowid)
    finally:
        con.close()


def _decode_json(value, default):
    """Decode a journal payload without allowing a corrupt row to break history."""
    try:
        decoded = json.loads(value or '')
    except (TypeError, ValueError):
        return default
    return decoded if isinstance(decoded, type(default)) else default


def get_move_history(limit: int = 1000) -> list[dict]:
    """Return completed organize and standalone moves newest first.

    The returned shape is intentionally UI-neutral so the history dialog and
    future non-Qt clients can share the same persisted-operation view.
    """
    if not isinstance(limit, int) or limit <= 0:
        raise ValueError('history limit must be a positive integer')

    history: list[dict] = []
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT id, run_id, folder_name, src, dst, category, confidence,
                   source_root, dest_root, source_signature,
                   destination_signature, merge_manifest, status,
                   ts_planned, ts_done, ts_undone
            FROM moves
            WHERE status IN ('done', 'undone')
            """
        ).fetchall()
        for row in rows:
            timestamp = row[15] or row[14] or row[13] or ''
            history.append({
                'kind': 'run',
                'id': row[0],
                'run_id': row[1],
                'action_id': '',
                'folder_name': row[2],
                'source': row[3],
                'destination': row[4],
                'src': row[3],
                'dst': row[4],
                'category': row[5],
                'confidence': float(row[6] or 0),
                'source_root': row[7],
                'dest_root': row[8],
                'source_signature': _decode_json(row[9], {}),
                'destination_signature': _decode_json(row[10], {}),
                'merge_manifest': _decode_json(row[11], []),
                'status': row[12],
                'timestamp': timestamp,
                'ts_planned': row[13],
                'ts_done': row[14],
                'ts_undone': row[15],
                'can_undo': row[12] == 'done',
            })

        rows = con.execute(
            """
            SELECT id, action_id, source, destination, source_root, dest_root,
                   source_signature, destination_signature, status, error,
                   ts_planned, ts_done, ts_undone
            FROM action_moves
            WHERE status IN ('moved', 'undone')
            """
        ).fetchall()
        for row in rows:
            timestamp = row[12] or row[11] or row[10] or ''
            history.append({
                'kind': 'action',
                'id': row[0],
                'run_id': '',
                'action_id': row[1],
                'folder_name': os.path.basename(row[2]),
                'source': row[2],
                'destination': row[3],
                'src': row[2],
                'dst': row[3],
                'category': '',
                'confidence': 0.0,
                'source_root': row[4],
                'dest_root': row[5],
                'source_signature': _decode_json(row[6], {}),
                'destination_signature': _decode_json(row[7], {}),
                'merge_manifest': [],
                'status': row[8],
                'error': row[9],
                'timestamp': timestamp,
                'ts_planned': row[10],
                'ts_done': row[11],
                'ts_undone': row[12],
                'can_undo': row[8] == 'moved',
            })
    finally:
        con.close()

    history.sort(key=lambda entry: entry.get('timestamp', ''), reverse=True)
    return history[:limit]


def _load_move_entry(move_id: int) -> dict:
    con = _connect()
    try:
        row = con.execute(
            """
            SELECT id, run_id, folder_name, src, dst, category, confidence,
                   source_root, dest_root, source_signature,
                   destination_signature, merge_manifest, status
            FROM moves WHERE id=?
            """,
            (move_id,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise KeyError(f'journal move {move_id} was not found')
    return {
        'id': row[0],
        'run_id': row[1],
        'folder_name': row[2],
        'source': row[3],
        'destination': row[4],
        'category': row[5],
        'confidence': float(row[6] or 0),
        'source_root': row[7],
        'dest_root': row[8],
        'source_signature': _decode_json(row[9], {}),
        'destination_signature': _decode_json(row[10], {}),
        'merge_manifest': _decode_json(row[11], []),
        'status': row[12],
    }


def _save_move_undo_state(move_id: int, *, status: str, merge_manifest: list) -> None:
    con = _connect()
    try:
        con.execute(
            "UPDATE moves SET status=?, merge_manifest=?, ts_undone=? WHERE id=?",
            (
                status,
                json.dumps(merge_manifest, sort_keys=True),
                _now() if status == 'undone' else None,
                move_id,
            ),
        )
        con.commit()
    finally:
        con.close()


def undo_move_entry(move_id: int) -> dict:
    """Undo one completed organize move after revalidating its destination."""
    entry = _load_move_entry(move_id)
    if entry['status'] != 'done':
        raise PathSafetyError('journal move is not currently undoable')

    source = entry['source']
    destination = entry['destination']
    source_root = entry['source_root']
    dest_root = entry['dest_root']
    if not source_root or not dest_root:
        raise PathSafetyError('undo record has no path boundaries')

    manifest = entry['merge_manifest']
    if manifest:
        # Import lazily: workers imports the journal for normal apply, while
        # the journal itself must remain importable without loading Qt workers.
        from fileorganizer.workers import restore_merge_manifest

        try:
            _restored, errors = restore_merge_manifest(
                manifest, source_root, dest_root,
            )
        except Exception:
            _save_move_undo_state(move_id, status='done', merge_manifest=manifest)
            raise
        if errors:
            _save_move_undo_state(move_id, status='done', merge_manifest=manifest)
            raise PathSafetyError(f'{errors} merged item(s) could not be restored')
        _save_move_undo_state(move_id, status='undone', merge_manifest=[])
        return {
            'id': move_id,
            'run_id': entry['run_id'],
            'source': source,
            'destination': destination,
            'status': 'undone',
        }

    validate_source_signature(destination, entry['destination_signature'])
    validate_move(
        destination,
        source,
        source_root=dest_root,
        dest_root=source_root,
    )
    os.makedirs(os.path.dirname(source) or '.', exist_ok=True)
    shutil.move(destination, source)
    _save_move_undo_state(move_id, status='undone', merge_manifest=[])
    return {
        'id': move_id,
        'run_id': entry['run_id'],
        'source': source,
        'destination': destination,
        'status': 'undone',
    }


def undo_run(run_id: str) -> dict:
    """Undo all completed moves in a run, newest item first."""
    con = _connect()
    try:
        move_ids = [
            row[0] for row in con.execute(
                "SELECT id FROM moves WHERE run_id=? AND status='done' ORDER BY id DESC",
                (run_id,),
            ).fetchall()
        ]
    finally:
        con.close()

    restored = []
    errors = []
    for move_id in move_ids:
        try:
            restored.append(undo_move_entry(move_id))
        except Exception as exc:
            errors.append({'id': move_id, 'error': str(exc)})
    return {'run_id': run_id, 'restored': restored, 'errors': errors}


def finish_action_move(
    move_id: int,
    status: str,
    *,
    destination_signature: dict | None = None,
    error: str = '',
) -> None:
    """Finalize a standalone move journal record."""
    con = _connect()
    try:
        con.execute(
            """
            UPDATE action_moves
            SET status=?, destination_signature=?, error=?, ts_done=?, ts_undone=NULL
            WHERE id=?
            """,
            (
                status,
                json.dumps(destination_signature or {}, sort_keys=True),
                error,
                _now(),
                move_id,
            ),
        )
        con.commit()
    finally:
        con.close()


def get_action_moves(action_id: str) -> list[dict]:
    """Return standalone move records in original execution order."""
    con = _connect()
    try:
        rows = con.execute(
            """
            SELECT id, action_id, source, destination, source_root, dest_root,
                   source_signature, destination_signature, status, error
            FROM action_moves WHERE action_id=? ORDER BY id
            """,
            (action_id,),
        ).fetchall()
        return [
            {
                'id': row[0],
                'action_id': row[1],
                'source': row[2],
                'destination': row[3],
                'source_root': row[4],
                'dest_root': row[5],
                'source_signature': json.loads(row[6] or '{}'),
                'destination_signature': json.loads(row[7] or '{}'),
                'status': row[8],
                'error': row[9],
            }
            for row in rows
        ]
    finally:
        con.close()


def mark_action_undone(move_id: int, *, error: str = '') -> None:
    """Mark a standalone move restored, or retain its undo error."""
    con = _connect()
    try:
        if error:
            con.execute(
                "UPDATE action_moves SET error=? WHERE id=?",
                (error, move_id),
            )
        else:
            con.execute(
                """
                UPDATE action_moves
                SET status='undone', error='', ts_undone=? WHERE id=?
                """,
                (_now(), move_id),
            )
        con.commit()
    finally:
        con.close()


def _load_action_move(move_id: int) -> dict:
    con = _connect()
    try:
        row = con.execute(
            """
            SELECT id, action_id, source, destination, source_root, dest_root,
                   source_signature, destination_signature, status, error
            FROM action_moves WHERE id=?
            """,
            (move_id,),
        ).fetchone()
    finally:
        con.close()
    if row is None:
        raise KeyError(f'journal action move {move_id} was not found')
    return {
        'id': row[0],
        'action_id': row[1],
        'source': row[2],
        'destination': row[3],
        'source_root': row[4],
        'dest_root': row[5],
        'source_signature': _decode_json(row[6], {}),
        'destination_signature': _decode_json(row[7], {}),
        'status': row[8],
        'error': row[9],
    }


def undo_action_move(move_id: int) -> dict:
    """Undo one completed standalone action move with destination binding."""
    entry = _load_action_move(move_id)
    if entry['status'] != 'moved':
        raise PathSafetyError('journal action move is not currently undoable')

    source = entry['source']
    destination = entry['destination']
    if not entry['source_root'] or not entry['dest_root']:
        raise PathSafetyError('undo record has no path boundaries')
    try:
        validate_source_signature(destination, entry['destination_signature'])
        validate_move(
            destination,
            source,
            source_root=entry['dest_root'],
            dest_root=entry['source_root'],
        )
        os.makedirs(os.path.dirname(source) or '.', exist_ok=True)
        shutil.move(destination, source)
    except Exception as exc:
        mark_action_undone(move_id, error=str(exc))
        raise

    mark_action_undone(move_id)
    return {
        'id': move_id,
        'action_id': entry['action_id'],
        'source': source,
        'destination': destination,
        'status': 'undone',
    }


def cleanup_expired(days: int = _RETENTION_DAYS):
    """NEXT-37: Delete journal records older than retention period."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    cutoff_str = cutoff.strftime('%Y-%m-%dT%H:%M:%SZ')
    con = _connect()
    try:
        con.execute(
            """
            DELETE FROM moves
            WHERE status IN ('done', 'undone')
              AND COALESCE(ts_undone, ts_done, ts_planned) < ?
            """,
            (cutoff_str,)
        )
        con.execute(
            """
            DELETE FROM action_moves
            WHERE status IN ('moved', 'undone', 'error')
              AND COALESCE(ts_undone, ts_done, ts_planned) < ?
            """,
            (cutoff_str,),
        )
        con.commit()
    finally:
        con.close()


def vacuum():
    """NEXT-37: Reclaim disk space by vacuuming the database."""
    con = _connect()
    try:
        con.execute("VACUUM")
        con.commit()
    finally:
        con.close()

