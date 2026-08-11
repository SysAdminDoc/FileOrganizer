from __future__ import annotations

import json
import urllib.request

import pytest

import fileorganizer.metrics as metrics


def test_metrics_settings_are_opt_in_and_port_bounded(tmp_path, monkeypatch):
    path = tmp_path / "metrics.json"
    monkeypatch.setattr(metrics, "_SETTINGS_FILE", path)

    assert metrics.load_metrics_settings() == {"enabled": False, "port": 9999}
    saved = metrics.save_metrics_settings({"enabled": 1, "port": 80})

    assert saved == {"enabled": True, "port": 9999}
    assert json.loads(path.read_text(encoding="utf-8")) == saved


def test_metrics_disabled_by_default_and_loopback_only():
    exporter = metrics.MetricsExporter()
    ok, detail = exporter.start(enabled=False)

    assert not ok
    assert detail == "disabled"
    assert metrics.LOOPBACK_HOST == "127.0.0.1"
    exporter.record_files_moved(4)
    exporter.observe_classification(0.25, confidence=92, cache_hit=True)


def test_metrics_endpoint_exposes_required_series():
    pytest.importorskip("prometheus_client")
    exporter = metrics.MetricsExporter()
    ok, detail = exporter.start(enabled=True, port=19991)
    if not ok:
        pytest.fail(detail)
    try:
        exporter.record_files_moved(3)
        exporter.observe_classification(0.25, confidence=92, cache_hit=True)
        with urllib.request.urlopen(exporter.url, timeout=3) as response:
            payload = response.read().decode("utf-8")
        assert "fileorganizer_files_moved_total 3.0" in payload
        assert "fileorganizer_classify_duration_seconds_bucket" in payload
        assert "fileorganizer_classification_confidence_bucket" in payload
        assert "fileorganizer_cache_hit_ratio 1.0" in payload
    finally:
        exporter.stop()
