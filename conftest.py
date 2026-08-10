from __future__ import annotations

import os
import shutil
import time
import uuid
from pathlib import Path

import pytest


_TEMP_ROOT = (Path(__file__).resolve().parent / ".pytest-tmp").resolve()
_owned_run_temp: Path | None = None


def _is_owned_run_temp(path: Path) -> bool:
    resolved = path.resolve()
    return (
        resolved.parent == _TEMP_ROOT
        and resolved.name.startswith("run-")
        and len(resolved.name) > len("run-")
    )


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    global _owned_run_temp
    if config.option.basetemp is not None:
        return

    run_temp = _TEMP_ROOT / f"run-{os.getpid()}-{uuid.uuid4().hex}"
    run_temp.mkdir(parents=True)
    config.option.basetemp = str(run_temp)
    _owned_run_temp = run_temp


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    del session, exitstatus
    run_temp = _owned_run_temp
    if run_temp is None or not _is_owned_run_temp(run_temp):
        return

    for attempt in range(3):
        try:
            shutil.rmtree(run_temp)
            break
        except FileNotFoundError:
            break
        except OSError:
            if attempt == 2:
                return
            time.sleep(0.05 * (attempt + 1))

    try:
        _TEMP_ROOT.rmdir()
    except OSError:
        pass
