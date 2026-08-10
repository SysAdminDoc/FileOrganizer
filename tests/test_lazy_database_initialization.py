import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize(
    ("module", "database_name"),
    [
        ("fileorganizer.move_journal", "organize_moves.db"),
        ("fileorganizer.provider_cost_manager", "provider_costs.db"),
    ],
)
def test_database_modules_do_not_create_files_on_import(tmp_path, module, database_name):
    appdata = tmp_path / "appdata"
    environment = os.environ.copy()
    environment["APPDATA"] = str(appdata)
    completed = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert not (appdata / "FileOrganizer" / database_name).exists()
