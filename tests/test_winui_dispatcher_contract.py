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
    assert "await completion.Task.WaitAsync(ct)" in source
    assert "completion.TrySetException(ex)" in source
    assert "await DispatchEventAsync(evName, root.Clone())" in source


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
