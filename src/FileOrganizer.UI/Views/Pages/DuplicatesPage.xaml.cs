using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class DuplicatesPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    private long _wastedBytes;
    private long _duplicateCount;
    public BoundedObservableCollection<DupeGroup> Groups { get; } = [];

    public DuplicatesPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        GroupsList.ItemsSource = Groups;
        UpdateOptionsVisibility();
    }

    private string SelectedMode() =>
        ModeCombo.SelectedItem is ComboBoxItem c && c.Tag is string t ? t : "files";

    private void ModeCombo_SelectionChanged(object sender, SelectionChangedEventArgs e) => UpdateOptionsVisibility();

    private void Similarity_Changed(object sender, SelectionChangedEventArgs e)
    {
        // ComboBox raises SelectionChanged during XAML init (before ThresholdBox
        // has been constructed because it's declared after the combo in the
        // tree). Guard against the null until both controls exist.
        if (ThresholdBox is null) return;
        if (SimilarityCombo.SelectedItem is ComboBoxItem c && c.Tag is string s
            && double.TryParse(s, out var v))
            ThresholdBox.Value = v;
    }

    private void UpdateOptionsVisibility()
    {
        if (ImageOpts is null) return;
        var m = SelectedMode();
        ImageOpts.Visibility = m == "images" ? Visibility.Visible : Visibility.Collapsed;
        FileOpts.Visibility = m == "files" ? Visibility.Visible : Visibility.Collapsed;
    }

    private async void Browse_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker();
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null) FolderTextBox.Text = folder.Path;
    }

    private async void Run_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        var folder = FolderTextBox.Text?.Trim() ?? "";
        if (!Directory.Exists(folder)) { StatusText.Text = "Pick a folder first."; return; }
        var mode = SelectedMode();
        var args = new List<string> { "--root", folder, "--mode", mode };
        if (mode == "files")
            args.AddRange(new[] { "--min-size", ((long)MinSizeBox.Value).ToString(CultureInfo.InvariantCulture) });
        else
            args.AddRange(new[] { "--threshold", ((int)ThresholdBox.Value).ToString(CultureInfo.InvariantCulture) });

        _cts = new CancellationTokenSource();
        SetRunning(true);
        Groups.Clear();
        _wastedBytes = 0;
        _duplicateCount = 0;
        GroupsText.Text = "0"; DupesText.Text = "0"; WastedText.Text = "0 B";
        StatusText.Text = "Scanning...";
        try
        {
            var r = await _python.RunScriptNdjsonAsync("dedup_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = r.Success
                ? $"Review complete: {Groups.TotalAdded:N0} groups.{Groups.RetentionNotice} No files changed; use the Python desktop Duplicate Finder to act."
                : (r.ErrorMessage ?? r.Stderr);
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally { Groups.FlushPendingChanges(); _cts?.Dispose(); _cts = null; SetRunning(false); }
    }

    private void HandleEvent(string ev, JsonElement root)
    {
        switch (ev)
        {
            case "group":
                var key = root.TryGetProperty("key", out var k) ? k.GetString() ?? "" : "";
                var mode = root.TryGetProperty("mode", out var mm) ? mm.GetString() ?? "" : "";
                var files = new List<DupeFile>();
                var totalFiles = 0;
                long biggest = 0;
                if (root.TryGetProperty("files", out var farr) && farr.ValueKind == JsonValueKind.Array)
                {
                    foreach (var f in farr.EnumerateArray())
                    {
                        var path = f.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                        var size = f.TryGetProperty("size", out var s) && s.ValueKind == JsonValueKind.Number
                            ? s.GetInt64() : 0L;
                        int? distance = null;
                        if (f.TryGetProperty("distance", out var d) && d.ValueKind == JsonValueKind.Number)
                            distance = d.GetInt32();
                        biggest = Math.Max(biggest, size);
                        if (files.Count < UiStreamLimits.MaxFilesPerGroup)
                            files.Add(new DupeFile(path, size, distance, isKeeper: totalFiles == 0));
                        totalFiles++;
                    }
                }
                if (totalFiles >= 2)
                {
                    _wastedBytes += biggest * (totalFiles - 1);
                    _duplicateCount += totalFiles - 1;
                    Groups.Add(new DupeGroup(key, mode, files, totalFiles, biggest));
                    GroupsText.Text = Groups.TotalAdded.ToString("N0", CultureInfo.CurrentCulture);
                    DupesText.Text = _duplicateCount.ToString("N0", CultureInfo.CurrentCulture);
                    WastedText.Text = FormatSize(_wastedBytes);
                }
                break;
            case "progress":
                if (root.TryGetProperty("stage", out var st) && root.TryGetProperty("scanned", out var sc))
                    StatusText.Text = $"{st.GetString()} — {sc.GetInt64():N0}";
                break;
            case "complete":
                if (root.TryGetProperty("wasted_bytes", out var wb) && wb.ValueKind == JsonValueKind.Number)
                {
                    _wastedBytes = wb.GetInt64();
                    WastedText.Text = FormatSize(_wastedBytes);
                }
                break;
            case "error":
                StatusText.Text = $"Error: {(root.TryGetProperty("message", out var em) ? em.GetString() : "")}";
                break;
        }
    }

    private void Cancel_Click(object sender, RoutedEventArgs e) { _cts?.Cancel(); StatusText.Text = "Cancelling..."; }

    private void SetRunning(bool running)
    {
        ScanButton.IsEnabled = !running; BrowseButton.IsEnabled = !running;
        ModeCombo.IsEnabled = !running; FolderTextBox.IsEnabled = !running;
        MinSizeBox.IsEnabled = !running; ThresholdBox.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }

    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB", "PB"];
        double size = bytes;
        int u = 0;
        while (size >= 1024 && u < units.Length - 1) { size /= 1024; u++; }
        return u == 0 ? $"{bytes:N0} B" : $"{size:N1} {units[u]}";
    }
}

public sealed class DupeGroup
{
    public string Header { get; }
    public string Subheader { get; }
    public IReadOnlyList<DupeFile> Files { get; }

    public DupeGroup(
        string key,
        string mode,
        IReadOnlyList<DupeFile> files,
        int totalFiles,
        long biggest)
    {
        Files = files;
        Header = mode == "images"
            ? $"Image cluster · {totalFiles} similar"
            : $"Identical · {totalFiles} copies · key {key}";
        var wasted = biggest * (totalFiles - 1);
        Subheader = wasted > 0
            ? $"~{FormatSize(wasted)} wasted (one keeper, {totalFiles - 1} dupes)"
            : "";
        if (totalFiles > files.Count)
            Subheader += $" · showing first {files.Count:N0}";
    }

    private static string FormatSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB", "PB"];
        double size = bytes;
        int u = 0;
        while (size >= 1024 && u < units.Length - 1) { size /= 1024; u++; }
        return u == 0 ? $"{bytes:N0} B" : $"{size:N1} {units[u]}";
    }
}

public sealed class DupeFile
{
    public string Path { get; }
    public long Size { get; }
    public string SizeText { get; }
    public string DistanceText { get; }
    public Brush KeeperBrush { get; }

    public DupeFile(string path, long size, int? distance, bool isKeeper)
    {
        Path = path;
        Size = size;
        SizeText = FormatSize(size);
        DistanceText = distance is null ? (isKeeper ? "★ keeper" : "") : $"d={distance}";
        KeeperBrush = isKeeper
            ? (Brush)Application.Current.Resources["AccentGreenBrush"]
            : (Brush)Application.Current.Resources["TextPrimaryBrush"];
    }

    private static string FormatSize(long bytes)
    {
        if (bytes <= 0) return "—";
        string[] units = ["B", "KB", "MB", "GB", "TB", "PB"];
        double size = bytes;
        int u = 0;
        while (size >= 1024 && u < units.Length - 1) { size /= 1024; u++; }
        return u == 0 ? $"{bytes:N0} B" : $"{size:N1} {units[u]}";
    }
}
