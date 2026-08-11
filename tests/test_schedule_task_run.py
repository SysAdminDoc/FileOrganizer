from pathlib import Path

import pytest

import schedule_task_run
from fileorganizer.plugins import ProfileManager
from fileorganizer.profile_runner import (
    ProfileRunError,
    run_profile,
    validate_profile_config,
)


def test_schedule_cli_contract():
    args = schedule_task_run.build_argument_parser().parse_args([
        '--schedule', 'Daily Inbox',
        '--frequency', 'weekly',
        '--time', '07:30',
        '--day-of-week', '4',
        '--auto-apply',
    ])

    assert args.schedule == 'Daily Inbox'
    assert args.frequency == 'weekly'
    assert args.day_of_week == 4
    assert args.auto_apply is True


def test_validate_profile_config_accepts_safe_file_scan(tmp_path):
    source = tmp_path / 'source'
    source.mkdir()

    config = validate_profile_config({'mode': 3, 'src': str(source), 'dst': ''})

    assert config['src'] == str(source)


def test_run_profile_completes_offscreen_preview(tmp_path, monkeypatch):
    source = tmp_path / 'empty-source'
    source.mkdir()
    monkeypatch.setattr(
        ProfileManager,
        'load',
        staticmethod(lambda _name: {
            'mode': 3,
            'src': str(source),
            'dst': '',
            'depth': 0,
            'llm': False,
            'dedup': False,
            'inc_files': True,
            'inc_folders': False,
            'type_filter': 'All Files',
        }),
    )

    assert run_profile('Empty Preview') == 0


@pytest.mark.parametrize(
    'config, message',
    [
        ({'mode': 99, 'src': 'missing'}, 'unsupported scan mode'),
        ({'mode': 3, 'src': 'missing'}, 'source folder'),
    ],
)
def test_validate_profile_config_rejects_invalid_profiles(config, message):
    with pytest.raises(ProfileRunError, match=message):
        validate_profile_config(config)


def test_settings_exposes_schedule_controls():
    root = Path(__file__).resolve().parents[1]
    xaml = (root / 'src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml').read_text(
        encoding='utf-8'
    )
    code = (root / 'src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml.cs').read_text(
        encoding='utf-8'
    )

    assert 'x:Name="ScheduleProfileBox"' in xaml
    assert 'Click="ScheduleCreate_Click"' in xaml
    assert 'schedule_task_run.py' in code
    assert 'ScheduleTaskProtocol.TryParseState' in code
