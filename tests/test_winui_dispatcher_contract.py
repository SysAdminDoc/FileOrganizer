import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_raw_and_comics_pages_rely_on_the_central_dispatcher_contract():
    for relative_path in (
        "src/FileOrganizer.UI/Views/Pages/RAWPage.xaml.cs",
        "src/FileOrganizer.UI/Views/Pages/ComicsPage.xaml.cs",
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "MainWindow.Current" not in source
        assert "DispatcherQueue" not in source


def test_app_owns_the_safe_main_window_handle_used_by_pages():
    source = (REPO_ROOT / "src/FileOrganizer.UI/App.xaml.cs").read_text(encoding="utf-8")
    assert "public static Window? MainWindowHandleSafe => _mainWindow;" in source


def test_ndjson_runner_dispatches_and_propagates_callback_failures():
    source = (REPO_ROOT / "src/FileOrganizer.UI/Services/PythonRunner.cs").read_text(encoding="utf-8")
    assert "DispatcherQueue.GetForCurrentThread()" in source
    assert "await completion.Task.WaitAsync(dispatchToken)" in source
    assert "completion.TrySetException(ex)" in source
    assert "var accepted = protocol.AcceptLine(line)" in source
    assert "accepted.Payload" in source


def test_runners_drain_cancelled_readers_before_same_sidecar_restart():
    services = REPO_ROOT / "src/FileOrganizer.UI/Services"
    gate = (services / "RunLifecycleGate.cs").read_text(encoding="utf-8")
    assert "ConcurrentDictionary<string, SemaphoreSlim>" in gate
    assert "await gate.WaitAsync(cancellationToken)" in gate
    assert "Interlocked.Exchange(ref _gate, null)?.Release()" in gate

    python_runner = (services / "PythonRunner.cs").read_text(encoding="utf-8")
    assert "_runGate.EnterAsync(scriptName, ct)" in python_runner
    assert python_runner.count("await ObserveReaderTasksAsync(stdoutTask, stderrTask)") == 2
    assert "ct.ThrowIfCancellationRequested();\n                stdout.AppendLine(line);" in python_runner

    sidecar_runner = (services / "SidecarRunner.cs").read_text(encoding="utf-8")
    assert "_runGate.EnterAsync(toolName, ct)" in sidecar_runner
    assert "await ObserveReaderTasksAsync(stdoutTask, stderrTask)" in sidecar_runner
    assert "lct.ThrowIfCancellationRequested();\n                    onRawEvent?.Invoke" in sidecar_runner


def test_shell_cleanup_and_duplicates_are_explicitly_read_only_with_handoff():
    for relative_path in (
        "src/FileOrganizer.UI/Views/Pages/CleanupPage.xaml",
        "src/FileOrganizer.UI/Views/Pages/DuplicatesPage.xaml",
    ):
        source = (REPO_ROOT / relative_path).read_text(encoding="utf-8")
        assert "Read-only review" in source
        assert "no files are changed" in source.lower()
        assert "Python desktop" in source

    cleanup = (REPO_ROOT / "src/FileOrganizer.UI/Views/Pages/CleanupPage.xaml").read_text(encoding="utf-8")
    duplicates = (REPO_ROOT / "src/FileOrganizer.UI/Views/Pages/DuplicatesPage.xaml").read_text(encoding="utf-8")
    assert 'SelectionMode="None"' in cleanup
    assert 'SelectionMode="None"' in duplicates


def test_acoustid_secret_uses_credential_locker_and_never_argv():
    settings = (REPO_ROOT / "src/FileOrganizer.UI/Services/UserSettings.cs").read_text(encoding="utf-8")
    music = (REPO_ROOT / "src/FileOrganizer.UI/Views/Pages/MusicPage.xaml.cs").read_text(encoding="utf-8")
    runner = (REPO_ROOT / "src/FileOrganizer.UI/Services/PythonRunner.cs").read_text(encoding="utf-8")
    settings_page = (REPO_ROOT / "src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml.cs").read_text(encoding="utf-8")

    assert "PasswordVault" in settings
    assert "PasswordCredential" in settings
    assert 'Remove("AcoustIdApiKey")' in settings
    assert "TrySavePreferences" in settings_page
    assert "TryWriteAcoustIdSecret" in settings
    assert '"--api-key"' not in music
    assert '"ACOUSTID_API_KEY"' in music
    assert "IReadOnlyDictionary<string, string>? environmentVariables" in runner
    assert "psi.EnvironmentVariables[pair.Key] = pair.Value" in runner


def test_build_wrapper_does_not_pin_an_unavailable_visual_studio_installation():
    source = (REPO_ROOT / "src/build.ps1").read_text(encoding="utf-8")

    assert "Microsoft Visual Studio\\18\\Community" not in source
    assert "MSBUILD_EXE_PATH" in source
    assert "vswhere.exe" in source
    assert "Microsoft.DotNet.MSBuildSdkResolver.dll" in source


def test_title_bar_palette_tracks_live_theme_and_activation_changes():
    service = (REPO_ROOT / "src/FileOrganizer.UI/Services/ThemeService.cs").read_text(
        encoding="utf-8"
    )
    window = (REPO_ROOT / "src/FileOrganizer.UI/Views/MainWindow.xaml.cs").read_text(
        encoding="utf-8"
    )

    assert "event EventHandler<AppTheme>? ThemeChanged" in service
    assert "ThemeChanged?.Invoke(this, theme)" in service
    for semantic_token in (
        'theme.Colors["BrandTextPrimary"]',
        'theme.Colors["BrandTextMuted"]',
        'theme.Colors["BrandSurfaceLight"]',
        'theme.Colors["BrandBorderStrong"]',
    ):
        assert semantic_token in service

    assert "_themeService.ThemeChanged += ThemeService_ThemeChanged" in window
    assert "ApplyTitleBarPalette(_themeService.TitleBarPalette)" in window
    assert "Activated -= MainWindow_Activated" not in window
    for title_bar_state in (
        "ButtonForegroundColor",
        "ButtonInactiveForegroundColor",
        "ButtonHoverBackgroundColor",
        "ButtonHoverForegroundColor",
        "ButtonPressedBackgroundColor",
        "ButtonPressedForegroundColor",
    ):
        assert f"titleBar.{title_bar_state} = palette." in window


def test_every_title_bar_palette_has_readable_icon_contrast():
    source = (REPO_ROOT / "src/FileOrganizer.UI/Services/ThemeService.cs").read_text(
        encoding="utf-8"
    )

    def luminance(hex_color: str) -> float:
        channels = [int(hex_color[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            value / 12.92
            if value <= 0.04045
            else ((value + 0.055) / 1.055) ** 2.4
            for value in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    def contrast(first: str, second: str) -> float:
        light, dark = sorted((luminance(first), luminance(second)), reverse=True)
        return (light + 0.05) / (dark + 0.05)

    theme_blocks = source.split('new AppTheme("')[1:]
    assert len(theme_blocks) == 7
    for block in theme_blocks:
        theme_id = block.split('"', 1)[0]
        colors = dict(re.findall(r'\["([^"]+)"\] = C\("(#[0-9a-fA-F]{6})"\)', block))
        for foreground, background in (
            ("BrandTextPrimary", "BrandBackground"),
            ("BrandTextPrimary", "BrandSurfaceLight"),
            ("BrandTextPrimary", "BrandBorderStrong"),
            ("BrandTextMuted", "BrandBackground"),
        ):
            assert contrast(colors[foreground], colors[background]) >= 3.0, (
                theme_id,
                foreground,
                background,
            )


def test_winui_app_uses_the_bounded_redacting_crash_log_writer():
    app = (REPO_ROOT / "src/FileOrganizer.UI/App.xaml.cs").read_text(encoding="utf-8")
    writer = (
        REPO_ROOT / "src/FileOrganizer.UI/Services/CrashLogWriter.cs"
    ).read_text(encoding="utf-8")

    assert "CrashLog.Write(exception)" in app
    assert "File.AppendAllText" not in app
    assert "DefaultMaxFileBytes = 512 * 1024" in writer
    assert "DefaultMaxRecords = 100" in writer
    assert "DefaultArchiveCount = 2" in writer
    assert "File.Move(_logPath, ArchivePath(1), overwrite: true)" in writer
    assert "[REDACTED]" in writer


def test_settings_page_only_reports_saved_after_verified_persistence():
    settings = (REPO_ROOT / "src/FileOrganizer.UI/Services/UserSettings.cs").read_text(
        encoding="utf-8"
    )
    page = (
        REPO_ROOT / "src/FileOrganizer.UI/Views/Pages/SettingsPage.xaml.cs"
    ).read_text(encoding="utf-8")

    assert "SettingsPersistence.Save(" in settings
    assert "TrySavePreferences" in settings
    assert "var saveResult = _settings.TrySavePreferences" in page
    assert "if (!saveResult.Success)" in page
    assert "Previous settings remain active; choose Save to retry." in page
    assert "These edits are only shown here; choose Save to retry." in page
    assert page.index("if (!saveResult.Success)") < page.index(
        'SaveStatusText.Text = "Saved."'
    )


def test_every_custom_button_style_uses_system_focus_visuals():
    resources = (REPO_ROOT / "src/FileOrganizer.UI/App.xaml").read_text(
        encoding="utf-8"
    )
    expected_styles = {
        "PrimaryButtonStyle",
        "SecondaryButtonStyle",
        "GhostButtonStyle",
        "DangerButtonStyle",
        "IconButtonStyle",
    }
    button_styles = {
        match.group(1): match.group(0)
        for match in re.finditer(
            r'<Style x:Key="([^"]+ButtonStyle)".*?</Style>',
            resources,
            flags=re.DOTALL,
        )
    }

    assert expected_styles <= button_styles.keys()
    assert 'UseSystemFocusVisuals" Value="False"' not in resources
    for style_name in expected_styles:
        assert 'Property="UseSystemFocusVisuals" Value="True"' in button_styles[style_name]
