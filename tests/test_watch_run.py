import json

import pytest

import fileorganizer.config as config
import watch_run


@pytest.fixture(autouse=True)
def disable_default_protected_paths_for_temp_fixtures(monkeypatch):
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )


def _events(capsys):
    return [
        json.loads(line)
        for line in capsys.readouterr().out.splitlines()
        if line.strip()
    ]


@pytest.mark.parametrize(
    "raw",
    [
        "{}",
        "1",
        "[1]",
        "[]",
        '[{"src":"","dest":"x"}]',
        '[{"src":1,"dest":"x"}]',
        '[{"src":"x","dest":1}]',
        '[{"src":"x","dest":"y","copy":"yes"}]',
    ],
)
def test_malformed_watch_roots_and_entries_fail_once(raw, capsys):
    assert watch_run.main(["--watches", raw]) == 2

    events = _events(capsys)
    assert events[0]["event"] == "handshake"
    errors = [event for event in events if event["event"] == "error"]
    assert len(errors) == 1
    assert errors[0]["code"] == "invalid_watch_config"
    assert errors[0]["terminal"] is True


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("--interval", "nope"),
        ("--interval", "-1"),
        ("--settle", "NaN"),
        ("--heartbeat", "Infinity"),
        ("--duration", "-1"),
        ("--seen-limit", "1.5"),
        ("--seen-limit", "0"),
        ("--seen-retention", "NaN"),
    ],
)
def test_invalid_watch_timing_and_bounds_fail_closed(flag, value, capsys):
    assert watch_run.main(["--watches", "[]", flag, value]) == 2
    error = _events(capsys)[-1]
    assert error["event"] == "error"
    assert error["code"] == "invalid_watch_config"


def test_per_watch_nonfinite_settle_is_rejected(tmp_path, capsys):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    payload = json.dumps([{
        "src": str(source),
        "dest": str(destination),
        "settle": float("nan"),
    }])

    assert watch_run.main(["--watches", payload]) == 2
    assert _events(capsys)[-1]["code"] == "invalid_watch_config"


def test_valid_watch_can_finish_with_a_terminal_duration(tmp_path, capsys):
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    payload = json.dumps([{"src": str(source), "dest": str(destination)}])

    result = watch_run.main([
        "--watches", payload,
        "--interval", "0.01",
        "--heartbeat", "0.01",
        "--duration", "0.03",
    ])

    events = _events(capsys)
    assert result == 0
    assert [event["event"] for event in events[:3]] == [
        "handshake", "start", "watching",
    ]
    assert events[-1]["event"] == "complete"
    assert events[-1]["terminal"] is True


def test_seen_state_is_bounded_and_reprocesses_only_changed_files(tmp_path):
    state = watch_run.BoundedSeenState(max_entries=3, retention_seconds=10)
    files = []
    for index in range(5):
        path = tmp_path / f"asset-{index}.txt"
        path.write_text(str(index), encoding="utf-8")
        files.append(path)
        assert state.remember(str(path), now=0)

    assert len(state) == 3
    assert state.evicted == 2
    assert state.is_unchanged(str(files[-1]), now=5)

    files[-1].write_text("changed", encoding="utf-8")
    assert not state.is_unchanged(str(files[-1]), now=5)
    assert state.remember(str(files[-1]), now=5)
    assert state.is_unchanged(str(files[-1]), now=6)

    state.prune(now=16)
    assert len(state) == 0
