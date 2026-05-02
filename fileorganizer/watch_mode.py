"""FileOrganizer — Watch mode daemon for auto-classification on file arrival.

Monitors source folders for new/modified files. Auto-classifies + moves when
files stabilize (debounce window: default 30s to avoid partial-download false
positives). Integrates with organize_run.py and classify_design.py pipeline.

CLI interface:
  python watch_mode.py --source <name> --start          # Start daemon
  python watch_mode.py --source <name> --stop           # Stop daemon
  python watch_mode.py --status                         # Check status
  python watch_mode.py --source <name> --duration 60    # One-shot (60 secs)

GUI integration:
  Settings → Watch Mode tab (enable/disable, debounce slider, log viewer)
"""
import os
import sys
import time
import json
import sqlite3
import threading
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Set, Callable
from collections import defaultdict

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    HAS_WATCHDOG = True
except ImportError:
    HAS_WATCHDOG = False


# ── Configuration ─────────────────────────────────────────────────────────
_APP_DATA_DIR = os.path.join(
    os.environ.get('APPDATA', os.path.expanduser('~')),
    'FileOrganizer'
)
_WATCH_STATE_DB = os.path.join(_APP_DATA_DIR, 'watch_state.db')
_DEFAULT_DEBOUNCE_SECS = 30
_DEBOUNCE_MIN_SECS = 5
_DEBOUNCE_MAX_SECS = 120
_LOG_HISTORY_SIZE = 50


# ── Database Initialization ──────────────────────────────────────────────
def _init_watch_db():
    """Initialize watch_state.db schema if not present."""
    os.makedirs(_APP_DATA_DIR, exist_ok=True)
    db = sqlite3.connect(_WATCH_STATE_DB)
    db.execute('''
        CREATE TABLE IF NOT EXISTS watch_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at INTEGER DEFAULT (strftime('%s', 'now'))
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS watch_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_type TEXT,
            file_path TEXT,
            timestamp INTEGER DEFAULT (strftime('%s', 'now')),
            status TEXT DEFAULT 'pending'
        )
    ''')
    db.commit()
    return db


def _get_setting(db, key: str, default=None) -> Optional[str]:
    """Retrieve a setting from watch_settings."""
    cursor = db.execute(
        'SELECT value FROM watch_settings WHERE key = ?', (key,)
    )
    row = cursor.fetchone()
    return row[0] if row else default


def _set_setting(db, key: str, value: str):
    """Store a setting in watch_settings."""
    db.execute(
        'INSERT OR REPLACE INTO watch_settings (key, value) VALUES (?, ?)',
        (key, value)
    )
    db.commit()


def _log_event(db, event_type: str, file_path: str, status: str = 'pending'):
    """Log a file system event to watch_events."""
    db.execute(
        'INSERT INTO watch_events (event_type, file_path, status) VALUES (?, ?, ?)',
        (event_type, file_path, status)
    )
    # Keep only last N events
    db.execute(
        f'DELETE FROM watch_events WHERE id NOT IN '
        f'(SELECT id FROM watch_events ORDER BY id DESC LIMIT {_LOG_HISTORY_SIZE})'
    )
    db.commit()


def get_watch_log(limit: int = 50) -> list:
    """Retrieve recent watch events for GUI display."""
    try:
        db = sqlite3.connect(_WATCH_STATE_DB)
        cursor = db.execute(
            'SELECT event_type, file_path, timestamp, status FROM watch_events '
            'ORDER BY id DESC LIMIT ?',
            (limit,)
        )
        rows = cursor.fetchall()
        db.close()
        return [
            {
                'event_type': r[0],
                'file_path': r[1],
                'timestamp': r[2],
                'status': r[3]
            }
            for r in rows
        ]
    except Exception as e:
        return [{'error': str(e)}]


# ── Debounce Queue ───────────────────────────────────────────────────────
class DebounceQueue:
    """Debounce file events: reset timer on new events, emit batch on timeout."""

    def __init__(self, debounce_secs: int = _DEFAULT_DEBOUNCE_SECS, on_ready: Optional[Callable] = None):
        self.debounce_secs = max(_DEBOUNCE_MIN_SECS, min(debounce_secs, _DEBOUNCE_MAX_SECS))
        self.queue: Dict[str, float] = {}  # path -> arrival_time
        self.lock = threading.Lock()
        self.timer: Optional[threading.Timer] = None
        self.on_ready = on_ready  # Callback when debounce expires

    def add(self, file_path: str):
        """Add/reset file to queue."""
        with self.lock:
            self.queue[file_path] = time.time()
            # Cancel existing timer
            if self.timer:
                self.timer.cancel()
            # Start new timer
            self.timer = threading.Timer(
                self.debounce_secs,
                self._on_timeout
            )
            self.timer.daemon = True
            self.timer.start()

    def _on_timeout(self):
        """Called when debounce period expires."""
        with self.lock:
            if self.queue and self.on_ready:
                files = list(self.queue.keys())
                self.queue.clear()
                self.on_ready(files)

    def clear(self):
        """Clear queue and cancel timer."""
        with self.lock:
            self.queue.clear()
            if self.timer:
                self.timer.cancel()
                self.timer = None

    def size(self) -> int:
        """Return current queue size."""
        with self.lock:
            return len(self.queue)


# ── File System Event Handler ──────────────────────────────────────────────
class WatchEventHandler(FileSystemEventHandler):
    """Handles file system events (create, modify) for watch mode."""

    def __init__(self, debounce_queue: DebounceQueue, db_path: str, skip_patterns: Set[str]):
        super().__init__()
        self.queue = debounce_queue
        self.db_path = db_path
        self.skip_patterns = skip_patterns or {'.tmp', '.partial', '~', '.bak'}

    def on_created(self, event):
        """Called when a file is created."""
        if event.is_directory:
            return
        file_path = event.src_path
        if self._should_ignore(file_path):
            return
        # Reconnect to DB in this thread (watchdog events come from observer thread)
        db = sqlite3.connect(self.db_path)
        _log_event(db, 'created', file_path)
        db.close()
        self.queue.add(file_path)

    def on_modified(self, event):
        """Called when a file is modified."""
        if event.is_directory:
            return
        file_path = event.src_path
        if self._should_ignore(file_path):
            return
        # Reconnect to DB in this thread (watchdog events come from observer thread)
        db = sqlite3.connect(self.db_path)
        _log_event(db, 'modified', file_path)
        db.close()
        self.queue.add(file_path)

    def _should_ignore(self, file_path: str) -> bool:
        """Return True if file matches ignore patterns."""
        basename = os.path.basename(file_path).lower()
        for pattern in self.skip_patterns:
            if pattern in basename:
                return True
        return False


# ── Watch Daemon ──────────────────────────────────────────────────────────
def watch_daemon(
    source_name: str,
    source_path: str,
    dest_root: str,
    debounce_secs: int = _DEFAULT_DEBOUNCE_SECS,
    duration_secs: Optional[int] = None,
    on_files_ready: Optional[Callable] = None
):
    """
    Monitor source_path for files. When debounce expires, call on_files_ready(files).
    
    Args:
        source_name: Name of the source (e.g., 'ae', 'design')
        source_path: Folder to monitor
        dest_root: Destination root for moves
        debounce_secs: Debounce window (default 30s)
        duration_secs: If set, run for N seconds then stop (one-shot mode)
        on_files_ready: Callback(file_list) when debounce expires
    """
    if not HAS_WATCHDOG:
        raise ImportError("watchdog not installed. Run: pip install watchdog")
    
    source_path = str(Path(source_path).resolve())
    if not os.path.isdir(source_path):
        raise ValueError(f"Source path does not exist: {source_path}")
    
    db = _init_watch_db()
    _set_setting(db, 'watch_source', source_name)
    _set_setting(db, 'watch_source_path', source_path)
    _set_setting(db, 'watch_dest_root', dest_root)
    _set_setting(db, 'watch_status', 'running')
    _set_setting(db, 'watch_started_at', str(int(time.time())))
    db.close()
    
    # Set up debounce queue
    queue = DebounceQueue(debounce_secs, on_ready=on_files_ready)
    
    # Set up file system watcher
    event_handler = WatchEventHandler(queue, _WATCH_STATE_DB, skip_patterns={'.tmp', '.partial'})
    observer = Observer()
    observer.schedule(event_handler, source_path, recursive=True)
    observer.start()
    
    db = sqlite3.connect(_WATCH_STATE_DB)
    _log_event(db, 'watch_started', f'{source_name}:{source_path}', 'success')
    db.close()
    
    try:
        start_time = time.time()
        while True:
            time.sleep(1)
            
            # Check for one-shot duration limit
            if duration_secs and (time.time() - start_time) >= duration_secs:
                db = sqlite3.connect(_WATCH_STATE_DB)
                _log_event(db, 'watch_timeout', source_path, 'completed')
                db.close()
                break
            
            # Check for stop signal
            db = sqlite3.connect(_WATCH_STATE_DB)
            status = _get_setting(db, 'watch_status')
            db.close()
            
            if status != 'running':
                db = sqlite3.connect(_WATCH_STATE_DB)
                _log_event(db, 'watch_stopped', source_path, 'user_initiated')
                db.close()
                break
    
    except KeyboardInterrupt:
        db = sqlite3.connect(_WATCH_STATE_DB)
        _log_event(db, 'watch_interrupted', source_path, 'interrupted')
        db.close()
    
    finally:
        queue.clear()
        observer.stop()
        observer.join()
        db = sqlite3.connect(_WATCH_STATE_DB)
        _set_setting(db, 'watch_status', 'stopped')
        _set_setting(db, 'watch_stopped_at', str(int(time.time())))
        db.close()


# ── CLI Entry Point ───────────────────────────────────────────────────────
def main():
    """Command-line interface for watch mode."""
    parser = argparse.ArgumentParser(
        description='Watch mode daemon for FileOrganizer auto-classification'
    )
    parser.add_argument(
        '--source',
        help='Source name (ae, design, design_org, etc.)'
    )
    parser.add_argument(
        '--start',
        action='store_true',
        help='Start watch daemon'
    )
    parser.add_argument(
        '--stop',
        action='store_true',
        help='Stop watch daemon'
    )
    parser.add_argument(
        '--status',
        action='store_true',
        help='Check watch status'
    )
    parser.add_argument(
        '--duration',
        type=int,
        help='Run for N seconds (one-shot mode for testing)'
    )
    parser.add_argument(
        '--debounce',
        type=int,
        default=_DEFAULT_DEBOUNCE_SECS,
        help=f'Debounce window in seconds (default {_DEFAULT_DEBOUNCE_SECS})'
    )
    parser.add_argument(
        '--log',
        action='store_true',
        help='Show recent watch events'
    )
    
    args = parser.parse_args()
    
    # Show status
    if args.status:
        db = _init_watch_db()
        status = _get_setting(db, 'watch_status', 'stopped')
        source = _get_setting(db, 'watch_source', 'none')
        source_path = _get_setting(db, 'watch_source_path', '')
        started_at = _get_setting(db, 'watch_started_at')
        
        print(f'Status: {status}')
        print(f'Source: {source}')
        print(f'Path: {source_path}')
        if started_at:
            dt = datetime.fromtimestamp(int(started_at))
            print(f'Started: {dt.strftime("%Y-%m-%d %H:%M:%S")}')
        db.close()
        return
    
    # Show log
    if args.log:
        events = get_watch_log(limit=20)
        for evt in events:
            if 'error' in evt:
                print(f'Error: {evt["error"]}')
            else:
                dt = datetime.fromtimestamp(evt['timestamp'])
                print(f'[{dt.strftime("%H:%M:%S")}] {evt["event_type"]}: {evt["file_path"]} ({evt["status"]})')
        return
    
    # Stop daemon
    if args.stop:
        db = _init_watch_db()
        _set_setting(db, 'watch_status', 'stopped')
        db.close()
        print('Watch daemon stopped.')
        return
    
    # Start daemon
    if args.start:
        if not args.source:
            print('Error: --start requires --source')
            sys.exit(1)
        
        # TODO: Load source config from classify_design.py SOURCE_CONFIGS
        # For now, raise a placeholder error
        print(f'Error: Watch mode for source "{args.source}" not yet configured.')
        print('TODO: Integrate with SOURCE_CONFIGS from classify_design.py')
        sys.exit(1)


if __name__ == '__main__':
    main()
