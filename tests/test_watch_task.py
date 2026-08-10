from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import fileorganizer.config as config
from fileorganizer import watch_task
import watch_task_run


@pytest.fixture(autouse=True)
def disable_default_protected_paths(monkeypatch):
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )


def _watch_roots(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    return source, destination


def test_watch_task_config_is_validated_and_atomically_reloaded(tmp_path: Path):
    source, destination = _watch_roots(tmp_path)
    config_path = tmp_path / "watch-task.json"

    saved = watch_task.save_config(
        [{"src": str(source), "dest": str(destination), "copy": True}],
        45,
        enabled=True,
        path=config_path,
    )

    assert saved == watch_task.load_config(config_path)
    assert saved["schema_version"] == 1
    assert saved["enabled"] is True
    assert saved["debounce_seconds"] == 45
    assert saved["watches"][0]["copy"] is True
    assert not list(tmp_path.glob(".watch-task.json.*.tmp"))


@pytest.mark.parametrize("debounce", [0, 1, 121, "1.5", True, "NaN"])
def test_watch_task_rejects_invalid_debounce(tmp_path: Path, debounce):
    source, destination = _watch_roots(tmp_path)

    with pytest.raises(watch_task.WatchTaskError, match="debounce"):
        watch_task.save_config(
            [{"src": str(source), "dest": str(destination)}],
            debounce,
            path=tmp_path / "watch-task.json",
        )


def test_watch_task_rejects_duplicate_or_overlapping_roots(tmp_path: Path):
    source, destination = _watch_roots(tmp_path)
    config_path = tmp_path / "watch-task.json"

    with pytest.raises(watch_task.WatchTaskError, match="configured more than once"):
        watch_task.save_config([
            {"src": str(source), "dest": str(destination)},
            {"src": str(source), "dest": str(tmp_path / "other")},
        ], 30, path=config_path)

    with pytest.raises(watch_task.WatchTaskError, match="unsafe roots"):
        watch_task.save_config([
            {"src": str(source), "dest": str(source / "inside")},
        ], 30, path=config_path)


def test_registration_uses_hidden_pythonw_per_user_logon_task(tmp_path: Path, monkeypatch):
    source, destination = _watch_roots(tmp_path)
    config_path = tmp_path / "watch-task.json"
    watch_task.save_config(
        [{"src": str(source), "dest": str(destination)}],
        30,
        path=config_path,
    )
    runner = tmp_path / "watch_task_run.py"
    runner.write_text("", encoding="utf-8")
    python = tmp_path / "python.exe"
    python.write_text("", encoding="utf-8")
    pythonw = tmp_path / "pythonw.exe"
    pythonw.write_text("", encoding="utf-8")
    calls: list[list[str]] = []

    def fake_schtasks(arguments: list[str]):
        calls.append(arguments)
        return subprocess.CompletedProcess(arguments, 0, "ok", "")

    monkeypatch.setattr(watch_task, "_is_windows", lambda: True)
    monkeypatch.setattr(watch_task, "_run_schtasks", fake_schtasks)

    watch_task.register_task(
        runner,
        python_executable=str(python),
        config_path=config_path,
    )

    command = calls[0]
    assert command[:3] == ["/Create", "/TN", watch_task.TASK_NAME]
    assert ["/SC", "ONLOGON"] == command[3:5]
    assert ["/RL", "LIMITED"] == command[-3:-1]
    task_action = command[command.index("/TR") + 1]
    assert str(pythonw) in task_action
    assert str(runner) in task_action
    assert "--run" in task_action
    assert watch_task.load_config(config_path)["enabled"] is True


def test_disable_is_idempotent_when_task_is_not_registered(tmp_path: Path, monkeypatch):
    source, destination = _watch_roots(tmp_path)
    config_path = tmp_path / "watch-task.json"
    watch_task.save_config(
        [{"src": str(source), "dest": str(destination)}],
        30,
        enabled=True,
        path=config_path,
    )
    monkeypatch.setattr(watch_task, "_is_windows", lambda: True)
    monkeypatch.setattr(watch_task, "task_registered", lambda: False)

    watch_task.set_task_enabled(False, config_path)

    assert watch_task.load_config(config_path)["enabled"] is False


def test_missing_source_does_not_block_status_or_disable(tmp_path: Path, monkeypatch):
    source, destination = _watch_roots(tmp_path)
    config_path = tmp_path / "watch-task.json"
    watch_task.save_config(
        [{"src": str(source), "dest": str(destination)}],
        30,
        enabled=True,
        path=config_path,
    )
    source.rmdir()
    monkeypatch.setattr(watch_task, "_is_windows", lambda: True)
    monkeypatch.setattr(watch_task, "task_registered", lambda: False)

    assert watch_task.load_config(config_path)["watches"]
    watch_task.set_task_enabled(False, config_path)
    assert watch_task.load_config(config_path)["enabled"] is False


def test_background_runner_redirects_output_to_bounded_log(tmp_path: Path, monkeypatch):
    source, destination = _watch_roots(tmp_path)
    config_path = tmp_path / "watch-task.json"
    log_path = tmp_path / "logs" / "watch.log"
    watch_task.save_config(
        [{"src": str(source), "dest": str(destination)}],
        17,
        enabled=True,
        path=config_path,
    )
    received: list[str] = []

    def fake_watch_main(arguments: list[str]) -> int:
        received.extend(arguments)
        print("x" * 25)
        print("y" * 25)
        return 0

    monkeypatch.setattr(watch_task, "MAX_LOG_BYTES", 32)
    assert watch_task.run_background(
        config_path=config_path,
        log_path=log_path,
        watch_main=fake_watch_main,
    ) == 0

    assert received[received.index("--settle") + 1] == "17"
    payload = json.loads(received[received.index("--watches") + 1])
    assert payload[0]["src"] == str(source.resolve()).lower()
    assert "y" * 25 in watch_task.read_log_tail(log_path)
    archive = log_path.with_suffix(".log.1")
    assert archive.exists()
    assert log_path.stat().st_size <= 32
    assert archive.stat().st_size <= 32


def test_watch_task_cli_status_is_machine_readable(monkeypatch, capsys):
    monkeypatch.setattr(
        watch_task,
        "status",
        lambda: {
            "supported": True,
            "configured": True,
            "enabled": False,
            "registered": True,
            "watch_count": 2,
            "debounce_seconds": 30,
            "task_name": watch_task.TASK_NAME,
            "log_path": "watch.log",
        },
    )

    assert watch_task_run.main(["--status"]) == 0
    assert json.loads(capsys.readouterr().out)["watch_count"] == 2


def test_settings_surface_exposes_watch_startup_debounce_and_logs():
    root = Path(__file__).resolve().parents[1]
    xaml = (root / "src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml").read_text(
        encoding="utf-8"
    )
    code = (root / "src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml.cs").read_text(
        encoding="utf-8"
    )

    assert 'x:Name="WatchStartupToggle"' in xaml
    assert 'x:Name="WatchDebounceSlider"' in xaml
    assert 'x:Name="WatchLogBox"' in xaml
    assert '"--configure"' in code
    assert '"--register"' in code
    assert '"--disable"' in code
    assert '"--logs"' in code
