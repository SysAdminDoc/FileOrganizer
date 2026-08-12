from pathlib import Path

from fileorganizer.config import resolve_app_data_dir


def test_portable_marker_selects_data_directory_next_to_script(tmp_path):
    (tmp_path / "portable.flag").write_text("", encoding="utf-8")

    result = resolve_app_data_dir(tmp_path, tmp_path / "ignored-appdata")

    assert Path(result) == tmp_path / "FileOrganizerData"


def test_default_data_directory_uses_appdata_without_marker(tmp_path):
    result = resolve_app_data_dir(tmp_path, tmp_path / "appdata")

    assert Path(result) == tmp_path / "appdata" / "FileOrganizer"
