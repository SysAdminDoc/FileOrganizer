from pathlib import Path
from types import SimpleNamespace
from typing import cast

from _pytest.config import Config
from _pytest.main import Session

import conftest as root_config


def test_default_basetemp_is_unique_and_workspace_owned(monkeypatch):
    config = SimpleNamespace(option=SimpleNamespace(basetemp=None))
    original_run_temp = root_config._owned_run_temp
    monkeypatch.setattr(root_config, "_owned_run_temp", original_run_temp)
    monkeypatch.setattr(
        root_config.uuid,
        "uuid4",
        lambda: SimpleNamespace(hex="a" * 32),
    )

    root_config.pytest_configure(cast(Config, config))

    expected = root_config._TEMP_ROOT / f"run-{root_config.os.getpid()}-{'a' * 32}"
    assert Path(config.option.basetemp) == expected
    assert root_config._is_owned_run_temp(expected)
    assert not root_config._is_owned_run_temp(root_config._TEMP_ROOT)
    assert not root_config._is_owned_run_temp(root_config._TEMP_ROOT.parent / "run-unsafe")
    root_config.shutil.rmtree(expected)


def test_explicit_basetemp_is_preserved(monkeypatch, tmp_path):
    explicit = tmp_path / "caller-owned"
    config = SimpleNamespace(option=SimpleNamespace(basetemp=str(explicit)))
    monkeypatch.setattr(root_config, "_owned_run_temp", None)

    root_config.pytest_configure(cast(Config, config))

    assert config.option.basetemp == str(explicit)
    assert root_config._owned_run_temp is None


def test_session_cleanup_removes_only_the_owned_run(monkeypatch):
    owned = root_config._TEMP_ROOT / "run-cleanup-fixture"
    owned.mkdir(parents=True)
    (owned / "result.txt").write_text("fixture", encoding="utf-8")
    sibling = root_config._TEMP_ROOT / "keep-this-sibling"
    sibling.mkdir(exist_ok=True)
    monkeypatch.setattr(root_config, "_owned_run_temp", owned)

    root_config.pytest_sessionfinish(cast(Session, None), 0)

    assert not owned.exists()
    assert sibling.exists()
    sibling.rmdir()
