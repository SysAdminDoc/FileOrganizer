using System.Collections.ObjectModel;
using System.Globalization;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class CleanupPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    private long _totalSize;

    public BoundedObservableCollection<CleanupResultItem> Results { get; } = [];

    public CleanupPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        ResultsList.ItemsSource = Results;
        UpdateScannerOptionsVisibility();
    }

    private string SelectedScannerTag()
    {
        if (ScannerCombo.SelectedItem is ComboBoxItem cbi && cbi.Tag is string tag)
            return tag;
        return "empty_folders";
    }

    private void ScannerCombo_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        UpdateScannerOptionsVisibility();
    }

    private void UpdateScannerOptionsVisibility()
    {
        if (BigFilesOptions is null) return; // running before InitializeComponent finishes
        var tag = SelectedScannerTag();
        BigFilesOptions.Visibility = tag == "big_files" ? Visibility.Visible : Visibility.Collapsed;
        OldDownloadsOptions.Visibility = tag == "old_downloads" ? Visibility.Visible : Visibility.Collapsed;
        TempFilesOptions.Visibility = tag == "temp_files" ? Visibility.Visible : Visibility.Collapsed;
        BrokenFilesOptions.Visibility = tag == "broken_files" ? Visibility.Visible : Visibility.Collapsed;
    }

    private async void Browse_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker
        {
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.Desktop,
        };
        picker.FileTypeFilter.Add("*");

        var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);

        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null)
        {
            FolderTextBox.Text = folder.Path;
        }
    }

    private async void Scan_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;

        var folder = FolderTextBox.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder))
        {
            StatusText.Text = "Pick a folder that exists before scanning.";
            return;
        }

        var scanner = SelectedScannerTag();
        var args = new List<string> { "--scanner", scanner, "--root", folder };

        switch (scanner)
        {
            case "big_files":
                args.AddRange(new[] { "--min-size-mb",
                    MinSizeMbBox.Value.ToString(CultureInfo.InvariantCulture) });
                break;
            case "old_downloads":
                args.AddRange(new[] { "--days-old",
                    ((int)DaysOldBox.Value).ToString(CultureInfo.InvariantCulture) });
                break;
            case "temp_files":
                if (IncludeLogsCheck.IsChecked == true) args.Add("--include-logs");
                if (MinAgeDaysBox.Value > 0)
                {
                    args.AddRange(new[] { "--min-age-days",
                        ((int)MinAgeDaysBox.Value).ToString(CultureInfo.InvariantCulture) });
                }
                break;
            case "broken_files":
                if (CheckArchivesCheck.IsChecked == true) args.Add("--check-archives");
                break;
        }

        _cts = new CancellationTokenSource();
        SetRunning(true);
        Results.Clear();
        _totalSize = 0;
        ScannedText.Text = "0";
        FoundText.Text = "0";
        TotalSizeText.Text = "0 B";
        StatusText.Text = $"Scanning... ({scanner})";

        try
        {
            var result = await _python.RunScriptNdjsonAsync(
                "cleanup_run.py",
                args,
                HandleEvent,
                _cts.Token);

            if (result.Success)
            {
                StatusText.Text = $"Review complete: {Results.TotalAdded:N0} item(s) found.{Results.RetentionNotice} No files changed; use the Python desktop Cleanup Tools to act.";
            }
            else if (result.ExitCode == -1 && string.IsNullOrEmpty(result.ErrorMessage) is false)
            {
                StatusText.Text = result.ErrorMessage;
            }
            else
            {
                StatusText.Text = $"Failed (exit {result.ExitCode}). {result.Stderr}".Trim();
            }
        }
        catch (OperationCanceledException)
        {
            StatusText.Text = "Cancelled.";
        }
        catch (Exception ex)
        {
            StatusText.Text = $"Unexpected error: {ex.Message}";
        }
        finally
        {
            Results.FlushPendingChanges();
            _cts?.Dispose();
            _cts = null;
            SetRunning(false);
        }
    }

    private async void Resume_Click(object sender, RoutedEventArgs e)
    {
        var scanId = ScanIdTextBox.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(scanId))
        {
            StatusText.Text = "Enter a saved review ID first.";
            return;
        }
        await RunSavedReviewAsync(
            ["--resume-scan", scanId], clearResults: true, busyText: "Revalidating saved review...");
    }

    private async void Import_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        var picker = new Windows.Storage.Pickers.FileOpenPicker
        {
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.DocumentsLibrary,
        };
        picker.FileTypeFilter.Add(".json");
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var file = await picker.PickSingleFileAsync();
        if (file is not null)
            await RunSavedReviewAsync(
                ["--import-review", file.Path], clearResults: true, busyText: "Importing review...");
    }

    private async void Export_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        var scanId = ScanIdTextBox.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(scanId))
        {
            StatusText.Text = "Enter a saved review ID first.";
            return;
        }
        var picker = new Windows.Storage.Pickers.FileSavePicker
        {
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.DocumentsLibrary,
            SuggestedFileName = $"cleanup-review-{scanId}",
        };
        picker.FileTypeChoices.Add("JSON review", new List<string> { ".json" });
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var file = await picker.PickSaveFileAsync();
        if (file is not null)
            await RunSavedReviewAsync(
                ["--export-scan", scanId, "--output", file.Path],
                clearResults: false,
                busyText: "Exporting review...");
    }

    private async Task RunSavedReviewAsync(List<string> args, bool clearResults, string busyText)
    {
        if (_cts is not null) return;
        _cts = new CancellationTokenSource();
        SetRunning(true);
        if (clearResults)
        {
            Results.Clear();
            _totalSize = 0;
            ScannedText.Text = "0";
            FoundText.Text = "0";
            TotalSizeText.Text = "0 B";
        }
        StatusText.Text = busyText;
        try
        {
            var result = await _python.RunScriptNdjsonAsync(
                "cleanup_run.py", args, HandleEvent, _cts.Token);
            if (!result.Success)
                StatusText.Text = result.ErrorMessage ?? result.Stderr;
            else if (clearResults)
                StatusText.Text = $"Saved review loaded: {Results.TotalAdded:N0} item(s). Stale or missing paths are labeled and cannot be acted on.";
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Unexpected error: {ex.Message}"; }
        finally
        {
            Results.FlushPendingChanges();
            _cts?.Dispose();
            _cts = null;
            SetRunning(false);
        }
    }

    private void HandleEvent(string eventName, System.Text.Json.JsonElement root)
    {
        switch (eventName)
        {
            case "item":
                var path = root.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                var size = root.TryGetProperty("size", out var s) && s.ValueKind == System.Text.Json.JsonValueKind.Number
                    ? s.GetInt64() : 0L;
                var reason = root.TryGetProperty("reason", out var r) ? r.GetString() ?? "" : "";
                var validationStatus = root.TryGetProperty("validation_status", out var vs)
                    ? vs.GetString() ?? "unchecked" : "unchecked";
                var validationReason = root.TryGetProperty("validation_reason", out var vr)
                    ? vr.GetString() ?? "" : "";
                _totalSize += size;
                Results.Add(new CleanupResultItem(path, size, reason, validationStatus, validationReason));
                FoundText.Text = Results.TotalAdded.ToString("N0", CultureInfo.CurrentCulture);
                TotalSizeText.Text = FormatSize(_totalSize);
                break;

            case "review":
                if (root.TryGetProperty("scan_id", out var id))
                    ScanIdTextBox.Text = id.GetString() ?? "";
                if (root.TryGetProperty("root", out var reviewRoot))
                    FolderTextBox.Text = reviewRoot.GetString() ?? FolderTextBox.Text;
                break;

            case "review_exported":
                StatusText.Text = root.TryGetProperty("path", out var exportedPath)
                    ? $"Review exported to {exportedPath.GetString()}"
                    : "Review exported.";
                break;

            case "progress":
                if (root.TryGetProperty("scanned", out var sc) && sc.ValueKind == System.Text.Json.JsonValueKind.Number)
                    ScannedText.Text = sc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("stage", out var stage))
                    StatusText.Text = $"Scanning... {stage.GetString()}";
                break;

            case "error":
                var msg = root.TryGetProperty("message", out var m) ? m.GetString() ?? "" : "";
                StatusText.Text = $"Error: {msg}";
                break;

            case "complete":
                if (root.TryGetProperty("total_count", out var tc) && tc.ValueKind == System.Text.Json.JsonValueKind.Number)
                    FoundText.Text = tc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("total_size", out var ts) && ts.ValueKind == System.Text.Json.JsonValueKind.Number)
                {
                    _totalSize = ts.GetInt64();
                    TotalSizeText.Text = FormatSize(_totalSize);
                }
                break;
        }
    }

    private void Cancel_Click(object sender, RoutedEventArgs e)
    {
        _cts?.Cancel();
        StatusText.Text = "Cancelling...";
    }

    private void SetRunning(bool running)
    {
        ScanButton.IsEnabled = !running;
        BrowseButton.IsEnabled = !running;
        ScannerCombo.IsEnabled = !running;
        FolderTextBox.IsEnabled = !running;
        ScanIdTextBox.IsEnabled = !running;
        ResumeButton.IsEnabled = !running;
        ImportButton.IsEnabled = !running;
        ExportButton.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }

    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB", "PB"];
        double size = bytes;
        int unit = 0;
        while (size >= 1024 && unit < units.Length - 1)
        {
            size /= 1024;
            unit++;
        }
        return unit == 0
            ? $"{bytes:N0} B"
            : $"{size:N1} {units[unit]}";
    }
}

public sealed class CleanupResultItem
{
    public string Path { get; }
    public long Size { get; }
    public string Reason { get; }
    public string SizeText { get; }

    public CleanupResultItem(
        string path,
        long size,
        string reason,
        string validationStatus = "unchecked",
        string validationReason = "")
    {
        Path = path;
        Size = size;
        Reason = validationStatus is "fresh" or "unchecked"
            ? reason
            : $"{validationStatus.ToUpperInvariant()}: {validationReason} · {reason}";
        SizeText = FormatSize(size);
    }

    private static string FormatSize(long bytes)
    {
        if (bytes <= 0) return "—";
        string[] units = ["B", "KB", "MB", "GB", "TB", "PB"];
        double size = bytes;
        int unit = 0;
        while (size >= 1024 && unit < units.Length - 1)
        {
            size /= 1024;
            unit++;
        }
        return unit == 0
            ? $"{bytes:N0} B"
            : $"{size:N1} {units[unit]}";
    }
}
