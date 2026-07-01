"""Async watch loop scaffold using watchfiles (NEXT-60).

Provides a cross-platform filesystem watcher foundation for NEXT-1 watch mode.
Uses `watchfiles` (Rust-backed, async iteration) when available, falls back to
polling with os.scandir.
"""
import asyncio
import importlib.util
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Set

log = logging.getLogger(__name__)

_HAS_WATCHFILES = importlib.util.find_spec("watchfiles") is not None
_MAX_QUEUE_DEPTH = 1000
_DEFAULT_DEBOUNCE_MS = 30000  # 30 seconds


@dataclass
class FileEvent:
    """A filesystem change event."""
    path: str
    change_type: str  # 'added', 'modified', 'deleted'
    timestamp: float = field(default_factory=time.monotonic)


@dataclass
class WatchConfig:
    """Configuration for the watch daemon."""
    paths: list = field(default_factory=list)
    debounce_ms: int = _DEFAULT_DEBOUNCE_MS
    max_queue: int = _MAX_QUEUE_DEPTH
    recursive: bool = True
    ignore_patterns: Set[str] = field(default_factory=lambda: {
        "__pycache__", ".git", ".DS_Store", "Thumbs.db",
        ".fileorganizer.reserve", "organize_moves.db",
    })


class WatchDaemon:
    """Filesystem watch daemon with debounce queue."""

    def __init__(self, config: WatchConfig, on_stable: Optional[Callable] = None):
        self.config = config
        self.on_stable = on_stable
        self._queue: dict = {}  # path -> FileEvent
        self._running = False

    def is_available(self) -> bool:
        """Check if watchfiles is installed."""
        return _HAS_WATCHFILES

    async def start(self):
        """Start the async watch loop."""
        self._running = True
        log.info("Watch daemon starting for %d paths", len(self.config.paths))

        if _HAS_WATCHFILES:
            await self._watch_with_watchfiles()
        else:
            await self._watch_with_polling()

    def stop(self):
        """Signal the watch loop to stop."""
        self._running = False

    def pending_count(self) -> int:
        """Number of events waiting in the debounce queue."""
        return len(self._queue)

    def get_stable_paths(self) -> list:
        """Return paths that have been stable past the debounce window."""
        now = time.monotonic()
        threshold = self.config.debounce_ms / 1000.0
        stable = []
        expired_keys = []

        for path, event in self._queue.items():
            if now - event.timestamp >= threshold:
                stable.append(event)
                expired_keys.append(path)

        for key in expired_keys:
            del self._queue[key]

        return stable

    def _should_ignore(self, path: str) -> bool:
        """Check if a path should be ignored."""
        basename = os.path.basename(path)
        return basename in self.config.ignore_patterns

    def _enqueue(self, path: str, change_type: str):
        """Add or update an event in the debounce queue."""
        if self._should_ignore(path):
            return
        if len(self._queue) >= self.config.max_queue:
            log.warning("Watch queue full (%d), dropping event", self.config.max_queue)
            return
        self._queue[path] = FileEvent(path=path, change_type=change_type)

    async def _watch_with_watchfiles(self):
        """Watch using the watchfiles library."""
        import watchfiles

        paths = [p for p in self.config.paths if os.path.isdir(p)]
        if not paths:
            log.warning("No valid paths to watch")
            return

        try:
            async for changes in watchfiles.awatch(
                *paths,
                recursive=self.config.recursive,
                step=1000,
                debounce=1000,
            ):
                if not self._running:
                    break
                for change_type, path in changes:
                    ct = {1: "added", 2: "modified", 3: "deleted"}.get(change_type, "modified")
                    self._enqueue(path, ct)

                stable = self.get_stable_paths()
                if stable and self.on_stable:
                    await self._fire_callback(stable)
        except asyncio.CancelledError:
            pass

    async def _watch_with_polling(self, interval: float = 2.0):
        """Fallback polling watcher when watchfiles is not available."""
        known: dict = {}

        for path in self.config.paths:
            if os.path.isdir(path):
                known.update(self._scan_dir(path))

        while self._running:
            await asyncio.sleep(interval)

            current: dict = {}
            for path in self.config.paths:
                if os.path.isdir(path):
                    current.update(self._scan_dir(path))

            for p, mtime in current.items():
                if p not in known:
                    self._enqueue(p, "added")
                elif known[p] != mtime:
                    self._enqueue(p, "modified")

            for p in known:
                if p not in current:
                    self._enqueue(p, "deleted")

            known = current

            stable = self.get_stable_paths()
            if stable and self.on_stable:
                await self._fire_callback(stable)

    def _scan_dir(self, path: str) -> dict:
        """Scan a directory and return {path: mtime} dict."""
        result = {}
        try:
            for entry in os.scandir(path):
                if self._should_ignore(entry.path):
                    continue
                try:
                    result[entry.path] = entry.stat().st_mtime
                except OSError:
                    pass
        except (PermissionError, OSError):
            pass
        return result

    async def _fire_callback(self, stable_events: list):
        """Fire the on_stable callback."""
        try:
            if asyncio.iscoroutinefunction(self.on_stable):
                await self.on_stable(stable_events)
            else:
                self.on_stable(stable_events)
        except Exception as e:
            log.error("Watch callback error: %s", e)
