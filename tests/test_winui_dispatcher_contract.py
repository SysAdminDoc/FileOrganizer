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
    assert "TrySetAcoustIdApiKey" in settings_page
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
