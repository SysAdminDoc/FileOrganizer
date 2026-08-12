from fileorganizer.context_menu import build_shell_command, run_headless


def test_shell_command_targets_run_entrypoint_and_expands_directory_token():
    command = build_shell_command(
        r"C:\Python\python.exe",
        r"C:\Program Files\FileOrganizer\run.py",
    )

    assert command == (
        r'"C:\Python\python.exe" "C:\Program Files\FileOrganizer\run.py" '
        '--source "%V"'
    )


def test_shell_command_can_request_offscreen_apply():
    command = build_shell_command(
        r"C:\FileOrganizer\FileOrganizer.exe",
        frozen=True,
        headless=True,
        auto_apply=True,
    )

    assert command == (
        r'"C:\FileOrganizer\FileOrganizer.exe" --source "%V" '
        "--headless --auto-apply"
    )


def test_shell_command_accepts_selected_directory_token():
    command = build_shell_command(
        r"C:\Python\python.exe",
        r"C:\FileOrganizer\run.py",
        source_token="%1",
    )

    assert command.endswith('--source "%1"')


def test_headless_runner_rejects_missing_source_without_qt(tmp_path):
    assert run_headless(str(tmp_path / "missing")) == 2
