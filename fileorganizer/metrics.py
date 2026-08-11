"""Opt-in, loopback-only Prometheus metrics for local performance monitoring."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from fileorganizer.config import _APP_DATA_DIR


LOOPBACK_HOST = "127.0.0.1"
DEFAULT_PORT = 9999
_SETTINGS_FILE = Path(_APP_DATA_DIR) / "metrics_settings.json"
_DEFAULT_SETTINGS = {"enabled": False, "port": DEFAULT_PORT}
_DURATION_BUCKETS = (0.0001, 0.001, 0.01, 0.1, 1.0, 2.5, 5.0, 10.0)
_CONFIDENCE_BUCKETS = tuple(index / 10 for index in range(5, 11))


def _validate_port(value: object) -> int:
    try:
        port = int(value)
    except (TypeError, ValueError):
        return DEFAULT_PORT
    return port if 1024 <= port <= 65535 else DEFAULT_PORT


def _validate_settings(settings: object) -> dict[str, object]:
    raw = settings if isinstance(settings, dict) else {}
    return {
        "enabled": bool(raw.get("enabled", False)),
        "port": _validate_port(raw.get("port", DEFAULT_PORT)),
    }


def load_metrics_settings() -> dict[str, object]:
    """Load the explicit local-export opt-in and its bounded loopback port."""
    try:
        with _SETTINGS_FILE.open("r", encoding="utf-8") as stream:
            return _validate_settings(json.load(stream))
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_SETTINGS)


def save_metrics_settings(settings: object) -> dict[str, object]:
    """Persist validated metrics settings and return the normalized value."""
    normalized = _validate_settings(settings)
    try:
        _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _SETTINGS_FILE.open("w", encoding="utf-8") as stream:
            json.dump(normalized, stream, indent=2)
    except OSError:
        pass
    return normalized


class MetricsExporter:
    """Own one registry and one loopback HTTP server for the process."""

    def __init__(self) -> None:
        self.registry: Any = None
        self.classify_duration: Any = None
        self.files_moved: Any = None
        self.classification_confidence: Any = None
        self.cache_hit_ratio: Any = None
        self.gpu_vram_used: Any = None
        self._server: Any = None
        self._thread: Any = None
        self._enabled = False
        self._port: int | None = None
        self._cache_lookups = 0
        self._cache_hits = 0
        self._lock = threading.RLock()
        try:
            from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram
        except ImportError:
            return

        self.registry = CollectorRegistry()
        self.classify_duration = Histogram(
            "fileorganizer_classify_duration_seconds",
            "Classification operation duration in seconds.",
            buckets=_DURATION_BUCKETS,
            registry=self.registry,
        )
        self.files_moved = Counter(
            "fileorganizer_files_moved_total",
            "Files and folders moved by FileOrganizer.",
            registry=self.registry,
        )
        self.classification_confidence = Histogram(
            "fileorganizer_classification_confidence",
            "Classification confidence normalized to 0..1.",
            buckets=_CONFIDENCE_BUCKETS,
            registry=self.registry,
        )
        self.cache_hit_ratio = Gauge(
            "fileorganizer_cache_hit_ratio",
            "Observed classification cache hit ratio.",
            registry=self.registry,
        )
        self.gpu_vram_used = Gauge(
            "fileorganizer_gpu_vram_used_bytes",
            "Allocated GPU VRAM in bytes when a supported accelerator is active.",
            registry=self.registry,
        )

    @property
    def available(self) -> bool:
        return self.registry is not None

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def port(self) -> int | None:
        return self._port

    def start(self, *, enabled: bool = True, port: object = DEFAULT_PORT) -> tuple[bool, str]:
        """Start the exporter on IPv4 loopback only when explicitly enabled."""
        with self._lock:
            if not enabled:
                self.stop()
                return False, "disabled"
            if not self.available:
                return False, "prometheus-client is not installed"
            target_port = _validate_port(port)
            if self._server is not None:
                if self._port == target_port:
                    self._enabled = True
                    return True, self.url
                self.stop()
            try:
                from prometheus_client import start_http_server

                self._server, self._thread = start_http_server(
                    target_port,
                    addr=LOOPBACK_HOST,
                    registry=self.registry,
                )
            except (OSError, RuntimeError, TypeError) as exc:
                self._server = None
                self._thread = None
                return False, f"metrics endpoint unavailable: {exc}"
            self._port = int(self._server.server_address[1])
            self._enabled = True
            return True, self.url

    @property
    def url(self) -> str:
        return f"http://{LOOPBACK_HOST}:{self._port or DEFAULT_PORT}/metrics"

    def stop(self) -> None:
        with self._lock:
            server = self._server
            thread = self._thread
            self._server = None
            self._thread = None
            self._enabled = False
            self._port = None
            if server is not None:
                try:
                    server.shutdown()
                    server.server_close()
                except OSError:
                    pass
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.0)

    def observe_classification(
        self,
        duration_seconds: object,
        *,
        confidence: object = None,
        cache_hit: object = None,
    ) -> None:
        if not self._enabled or not self.available:
            return
        try:
            self.classify_duration.observe(max(0.0, float(duration_seconds)))
        except (TypeError, ValueError):
            pass
        if confidence is not None:
            try:
                normalized = float(confidence)
                if normalized > 1:
                    normalized /= 100.0
                self.classification_confidence.observe(max(0.0, min(1.0, normalized)))
            except (TypeError, ValueError):
                pass
        if isinstance(cache_hit, bool):
            self._cache_lookups += 1
            if cache_hit:
                self._cache_hits += 1
            ratio = self._cache_hits / self._cache_lookups
            self.cache_hit_ratio.set(ratio)
        self._update_gpu_vram()

    def record_files_moved(self, count: object) -> None:
        if not self._enabled or not self.available:
            return
        try:
            amount = max(0, int(count))
        except (TypeError, ValueError):
            return
        if amount:
            self.files_moved.inc(amount)
        self._update_gpu_vram()

    def _update_gpu_vram(self) -> None:
        if not self._enabled or not self.available:
            return
        try:
            import torch

            if torch.cuda.is_available():
                self.gpu_vram_used.set(float(torch.cuda.memory_allocated()))
        except (ImportError, AttributeError, RuntimeError, TypeError):
            pass


_EXPORTER = MetricsExporter()


def start_metrics_server(
    *, enabled: bool | None = None, port: object | None = None
) -> tuple[bool, str]:
    """Start the configured exporter, or explicitly stop it when disabled."""
    settings = load_metrics_settings()
    active = settings["enabled"] if enabled is None else bool(enabled)
    target_port = settings["port"] if port is None else port
    return _EXPORTER.start(enabled=active, port=target_port)


def ensure_metrics_exporter() -> bool:
    """Apply persisted opt-in settings without making metrics a hard dependency."""
    ok, _ = start_metrics_server()
    return ok


def stop_metrics_server() -> None:
    _EXPORTER.stop()


def record_classification(
    duration_seconds: object,
    *,
    confidence: object = None,
    cache_hit: object = None,
) -> None:
    _EXPORTER.observe_classification(
        duration_seconds, confidence=confidence, cache_hit=cache_hit
    )


def record_files_moved(count: object) -> None:
    _EXPORTER.record_files_moved(count)
