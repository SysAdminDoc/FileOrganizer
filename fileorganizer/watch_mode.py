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
from typing import Optional, Dict, Set, Callable, Any
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

_CLASSIFY_SOURCE_ALIASES = {
    'ae': 'ae',
    'design': 'design_unorg',
    'design_unorg': 'design_unorg',
    'design_org': 'design_org',
    'loose_files': 'loose_files',
    'design_elements': 'design_elements',
    'i_organized_legacy': 'i_organized_legacy',
}

_ORGANIZE_SOURCE_BY_CLASSIFY_SOURCE = {
    'ae': 'ae',
    'design_unorg': 'design',
    'design_org': 'design_org',
    'loose_files': 'loose_files',
    'design_elements': 'design_elements',
    'i_organized_legacy': 'i_organized_legacy',
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_repo_root_on_path() -> None:
    root = str(_repo_root())
    if root not in sys.path:
        sys.path.insert(0, root)


# ── Database Initialization ──────────────────────────────────────────────
def _init_watch_db(db_path: Optional[str] = None):
    """Initialize watch_state.db schema if not present."""
    target = db_path or _WATCH_STATE_DB
    os.makedirs(os.path.dirname(os.path.abspath(target)), exist_ok=True)
    db = sqlite3.connect(target)
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
        self.condition = threading.Condition(self.lock)
        self.timer: Optional[threading.Timer] = None
        self.on_ready = on_ready  # Callback when debounce expires
        self.active_callbacks = 0

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
        files = []
        with self.lock:
            if self.queue:
                files = list(self.queue.keys())
                self.queue.clear()
                self.timer = None
        if files and self.on_ready:
            self._emit_ready(files)

    def flush(self):
        """Immediately emit any queued paths and cancel the pending timer."""
        files = []
        with self.lock:
            if self.timer:
                self.timer.cancel()
                self.timer = None
            if self.queue:
                files = list(self.queue.keys())
                self.queue.clear()
        if files and self.on_ready:
            self._emit_ready(files)

    def _emit_ready(self, files: list[str]):
        with self.lock:
            self.active_callbacks += 1
        try:
            if self.on_ready:
                self.on_ready(files)
        finally:
            with self.lock:
                self.active_callbacks -= 1
                self.condition.notify_all()

    def wait_idle(self, timeout: Optional[float] = None) -> bool:
        """Wait until all in-flight callbacks finish."""
        deadline = time.time() + timeout if timeout is not None else None
        with self.lock:
            while self.active_callbacks:
                if deadline is None:
                    self.condition.wait()
                    continue
                remaining = deadline - time.time()
                if remaining <= 0:
                    return False
                self.condition.wait(remaining)
        return True

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


def _safe_default_dest_root() -> str:
    _ensure_repo_root_on_path()
    import organize_run

    try:
        return str(organize_run.get_dest_root())
    except Exception:
        return str(getattr(organize_run, 'DEST_PRIMARY', r'G:\Organized'))


def _default_ae_source_path() -> str:
    index_path = _repo_root() / 'org_index.json'
    try:
        with index_path.open('r', encoding='utf-8') as f:
            rows = json.load(f)
        if rows and rows[0].get('folder'):
            return str(rows[0]['folder'])
    except Exception:
        pass
    return r'I:\After Effects'


def resolve_source_config(
    source_name: str,
    source_path: Optional[str] = None,
    dest_root: Optional[str] = None,
) -> dict[str, Any]:
    """Resolve a watch source name to classify_design and organize_run config."""
    _ensure_repo_root_on_path()
    import classify_design

    classify_source = _CLASSIFY_SOURCE_ALIASES.get(source_name, source_name)
    if classify_source == 'ae':
        return {
            'requested_source': source_name,
            'classify_source': 'ae',
            'organize_source': 'ae',
            'source_path': source_path or _default_ae_source_path(),
            'dest_root': dest_root or _safe_default_dest_root(),
            'file_mode': False,
            'has_legacy': False,
        }
    if classify_source not in classify_design.SOURCE_CONFIGS:
        known = ', '.join(sorted(_CLASSIFY_SOURCE_ALIASES))
        raise ValueError(f"Unknown watch source {source_name!r}. Expected one of: {known}")

    cfg = dict(classify_design.SOURCE_CONFIGS[classify_source])
    return {
        'requested_source': source_name,
        'classify_source': classify_source,
        'organize_source': _ORGANIZE_SOURCE_BY_CLASSIFY_SOURCE[classify_source],
        'source_path': source_path or cfg['source_dir'],
        'dest_root': dest_root or _safe_default_dest_root(),
        'file_mode': bool(cfg.get('file_mode')),
        'has_legacy': bool(cfg.get('has_legacy')),
    }


def _path_is_stable(path: str, delay: float = 0.25) -> bool:
    """Return True when size and mtime stay unchanged across a short probe."""
    try:
        before = os.stat(path)
        time.sleep(delay)
        after = os.stat(path)
    except OSError:
        return False
    return (before.st_size, before.st_mtime_ns) == (after.st_size, after.st_mtime_ns)


def _asset_path_for_event(file_path: str, source_path: str, file_mode: bool) -> Path:
    event_path = Path(file_path).resolve()
    source_root = Path(source_path).resolve()
    if file_mode:
        return event_path
    try:
        rel = event_path.relative_to(source_root)
    except ValueError:
        return event_path if event_path.is_dir() else event_path.parent
    if not rel.parts:
        return event_path
    top_level = source_root / rel.parts[0]
    if top_level == event_path and event_path.is_file():
        return event_path
    return top_level


def _legacy_category_for_asset(asset_path: Path, source_path: str, context: dict[str, Any]) -> str:
    if not context.get('has_legacy'):
        return ''
    classify_source = context.get('classify_source', '')
    if classify_source == 'design_elements':
        return asset_path.name
    source_root = Path(source_path).resolve()
    try:
        rel_parent = asset_path.parent.resolve().relative_to(source_root)
    except ValueError:
        rel_parent = None
    if rel_parent and rel_parent.parts:
        return rel_parent.parts[-1]
    if asset_path.parent.resolve() != source_root:
        return asset_path.parent.name
    return ''


def _index_entries_for_files(
    file_paths: list[str],
    context: dict[str, Any],
) -> list[dict[str, Any]]:
    source_path = context['source_path']
    file_mode = bool(context.get('file_mode'))
    assets: dict[str, Path] = {}

    for file_path in file_paths:
        if not os.path.exists(file_path):
            continue
        if os.path.isfile(file_path) and not _path_is_stable(file_path):
            continue
        asset_path = _asset_path_for_event(file_path, source_path, file_mode)
        if not asset_path.exists():
            continue
        assets[os.path.normcase(str(asset_path.resolve()))] = asset_path

    entries: list[dict[str, Any]] = []
    for asset_path in sorted(assets.values(), key=lambda p: str(p).lower()):
        if asset_path.is_file():
            entry = {
                'name': asset_path.stem,
                'path': str(asset_path),
                'file_ext': asset_path.suffix.lower(),
                'is_file': True,
            }
        else:
            entry = {
                'name': asset_path.name,
                'path': str(asset_path),
            }
            legacy = _legacy_category_for_asset(asset_path, source_path, context)
            if legacy:
                entry['legacy_category'] = legacy
        entries.append(entry)
    return entries


def _review_result(item: dict[str, Any], reason: str) -> dict[str, Any]:
    name = item.get('name', '') or Path(item.get('path', '')).stem or 'Unknown Asset'
    return {
        'name': name,
        'category': 'After Effects - Other',
        'clean_name': name,
        'confidence': 0,
        'notes': reason,
        '_source_name': name,
        '_classifier': 'watch_fallback',
    }


def _normalize_watch_result(result: Any, item: dict[str, Any], category_set: set[str]) -> dict[str, Any]:
    if not isinstance(result, dict):
        return _review_result(item, 'watch mode fallback: classifier returned no result')

    out = dict(result)
    name = item.get('name', '') or Path(item.get('path', '')).stem or 'Unknown Asset'
    category = str(out.get('category') or '').strip()
    try:
        confidence = int(out.get('confidence', 0))
    except (TypeError, ValueError):
        confidence = 0

    if category in ('', '_Review', '_Unresolved') or category not in category_set:
        out = _review_result(item, f'watch mode fallback: unresolved category {category!r}')
    else:
        out['category'] = category
        out['confidence'] = max(0, min(confidence, 100))
        out.setdefault('clean_name', name)
        out.setdefault('name', name)

    out['_source_name'] = name
    out['_watch_path'] = item.get('path', '')
    return out


def _classify_watch_entries(entries: list[dict[str, Any]], source_path: str) -> list[dict[str, Any]]:
    if not entries:
        return []

    _ensure_repo_root_on_path()
    import classify_design

    old_source_dir = getattr(classify_design, 'SOURCE_DIR', '')
    classify_design.SOURCE_DIR = source_path
    category_set = set(classify_design.get_runtime_category_set())
    resolved: dict[int, dict[str, Any]] = {}

    try:
        for stage in (
            getattr(classify_design, '_try_fingerprint_db_lookup'),
            getattr(classify_design, '_try_metadata_classify'),
            getattr(classify_design, '_try_marketplace_enrich'),
        ):
            try:
                for idx, result in stage(entries).items():
                    resolved.setdefault(idx, result)
            except Exception:
                continue

        try:
            embed = classify_design._try_embeddings_classify(entries, set(resolved))
            for idx, result in embed.items():
                resolved.setdefault(idx, result)
        except Exception:
            pass

        unresolved = [(idx, item) for idx, item in enumerate(entries) if idx not in resolved]
        if unresolved and getattr(classify_design, 'DEEPSEEK_API_KEY', ''):
            ai_items = [item for _, item in unresolved]
            try:
                ai_results = classify_design.call_deepseek_cached(
                    classify_design.build_prompt(ai_items),
                    ai_items,
                    classify_design.DEEPSEEK_MODEL,
                )
                for (idx, _item), result in zip(unresolved, ai_results):
                    resolved.setdefault(idx, result)
            except Exception:
                pass

        return [
            _normalize_watch_result(
                resolved.get(idx) or _review_result(item, 'watch mode fallback: no configured AI result'),
                item,
                category_set,
            )
            for idx, item in enumerate(entries)
        ]
    finally:
        classify_design.SOURCE_DIR = old_source_dir


def _with_organize_dest_root(dest_root: str, build):
    _ensure_repo_root_on_path()
    import organize_run

    old_get_dest_root = organize_run.get_dest_root
    organize_run.get_dest_root = lambda: dest_root
    try:
        return build(organize_run)
    finally:
        organize_run.get_dest_root = old_get_dest_root


def process_ready_files(
    file_paths: list[str],
    context: dict[str, Any],
    plan_out: str = '',
    db_path: str = '',
) -> dict[str, Any]:
    """Classify a debounced watch batch and emit a dry-run move plan."""
    db_path = db_path or _WATCH_STATE_DB
    db = _init_watch_db(db_path)
    for file_path in file_paths:
        _log_event(db, 'ready', file_path, 'stable_pending')

    entries = _index_entries_for_files(file_paths, context)
    if not entries:
        _log_event(db, 'plan_skipped', json.dumps(file_paths), 'no_stable_files')
        db.close()
        return {'items': 0, 'plan_path': '', 'result': {}}

    results = _classify_watch_entries(entries, context['source_path'])
    pairs = list(zip(results, entries))
    plan_id = f"watch-{context['organize_source']}-{int(time.time())}"

    def _build(organize_run):
        plan = organize_run.build_move_plan(
            pairs,
            source_override=context['source_path'],
            source_mode=context['organize_source'],
            plan_id=plan_id,
        )
        path = organize_run.write_move_plan(plan, plan_out or '')
        result = organize_run.apply_move_plan(plan, dry_run=True, verbose=False)
        return plan, path, result

    plan, plan_path, result = _with_organize_dest_root(context['dest_root'], _build)
    _set_setting(db, 'latest_plan_id', plan.plan_id)
    _set_setting(db, 'latest_plan_path', plan_path)
    _set_setting(db, 'latest_plan_result', json.dumps(result, sort_keys=True))
    _log_event(db, 'plan_written', plan_path, 'dry_run')
    db.close()
    return {'items': len(plan.items), 'plan_path': plan_path, 'result': result}


def build_watch_plan_callback(context: dict[str, Any], plan_out: str = '') -> Callable[[list[str]], None]:
    def _on_files_ready(files: list[str]) -> None:
        try:
            process_ready_files(files, context, plan_out=plan_out)
        except Exception as e:
            db = _init_watch_db()
            _log_event(db, 'plan_failed', json.dumps(files), str(e))
            db.close()

    return _on_files_ready


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
                queue.flush()
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
        queue.flush()
        queue.wait_idle()
        queue.clear()
        observer.stop()
        observer.join()
        db = sqlite3.connect(_WATCH_STATE_DB)
        _set_setting(db, 'watch_status', 'stopped')
        _set_setting(db, 'watch_stopped_at', str(int(time.time())))
        db.close()


# ── CLI Entry Point ───────────────────────────────────────────────────────
def main(argv: Optional[list[str]] = None):
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
        '--source-path',
        help='Override the configured source path (for local smoke tests)'
    )
    parser.add_argument(
        '--dest-root',
        help='Override the organize destination root for generated dry-run plans'
    )
    parser.add_argument(
        '--plan-out',
        help='Write the generated dry-run move plan to this JSON path'
    )
    parser.add_argument(
        '--log',
        action='store_true',
        help='Show recent watch events'
    )
    
    args = parser.parse_args(argv)
    
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
    if args.start or args.duration:
        if not args.source:
            print('Error: --start/--duration requires --source')
            sys.exit(1)

        try:
            context = resolve_source_config(
                args.source,
                source_path=args.source_path,
                dest_root=args.dest_root,
            )
            callback = build_watch_plan_callback(context, plan_out=args.plan_out or '')
            print(
                f"Starting watch daemon: {context['requested_source']} "
                f"({context['source_path']}) -> {context['dest_root']}"
            )
            watch_daemon(
                source_name=context['requested_source'],
                source_path=context['source_path'],
                dest_root=context['dest_root'],
                debounce_secs=args.debounce,
                duration_secs=args.duration,
                on_files_ready=callback,
            )
        except Exception as e:
            print(f'Error: {e}')
            sys.exit(1)
        return

    parser.print_help()


if __name__ == '__main__':
    main()
