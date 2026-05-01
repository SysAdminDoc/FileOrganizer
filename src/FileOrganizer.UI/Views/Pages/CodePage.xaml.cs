using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class CodePage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    public ObservableCollection<CodeResultItem> Results { get; } = [];

    public CodePage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        ResultsList.ItemsSource = Results;
    }

    private string SelectedMode() =>
        ModeCombo.SelectedItem is ComboBoxItem c && c.Tag is string t ? t : "preview";

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
        var args = new List<string> { "--root", folder, "--mode", SelectedMode() };
        _cts = new CancellationTokenSource();
        SetRunning(true);
        Results.Clear();
        ScannedText.Text = "0"; MatchedText.Text = "0"; RenamedText.Text = "0";
        StatusText.Text = "Scanning...";
        try
        {
            var r = await _python.RunScriptNdjsonAsync("code_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = r.Success ? $"Done. {Results.Count:N0} projects." : (r.ErrorMessage ?? r.Stderr);
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally { _cts?.Dispose(); _cts = null; SetRunning(false); }
    }

    private void HandleEvent(string ev, JsonElement root)
    {
        switch (ev)
        {
            case "item":
                var status = root.TryGetProperty("status", out var st) ? st.GetString() ?? "" : "";
                if (status != "matched") break;
                var path = root.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                var name = root.TryGetProperty("name", out var n) ? n.GetString() ?? "" : "";
                var lang = root.TryGetProperty("language", out var l) ? l.GetString() ?? "" : "";
                var fc = root.TryGetProperty("file_count", out var f) && f.ValueKind == JsonValueKind.Number
                    ? f.GetInt64().ToString("N0", CultureInfo.CurrentCulture) : "";
                var markers = "";
                if (root.TryGetProperty("markers", out var m) && m.ValueKind == JsonValueKind.Array)
                    markers = string.Join(", ", m.EnumerateArray().Select(x => x.GetString()).Where(x => x != null));
                Results.Add(new CodeResultItem(path, name, lang, fc, markers));
                MatchedText.Text = Results.Count.ToString("N0", CultureInfo.CurrentCulture);
                break;
            case "progress":
                if (root.TryGetProperty("scanned", out var sc) && sc.ValueKind == JsonValueKind.Number)
                    ScannedText.Text = sc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("stage", out var stage))
                    StatusText.Text = $"Scanning... {stage.GetString()}";
                break;
            case "complete":
                if (root.TryGetProperty("renamed_count", out var rc) && rc.ValueKind == JsonValueKind.Number)
                    RenamedText.Text = rc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
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
        CancelButton.IsEnabled = running;
    }
}

public sealed class CodeResultItem(string path, string name, string language, string fileCount, string markers)
{
    public string Path { get; } = path;
    public string Name { get; } = name;
    public string Language { get; } = language;
    public string FileCount { get; } = fileCount;
    public string Markers { get; } = markers;
}
