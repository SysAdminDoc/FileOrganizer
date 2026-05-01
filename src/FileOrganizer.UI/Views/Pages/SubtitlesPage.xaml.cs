using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class SubtitlesPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    public ObservableCollection<SubtitleResultItem> Results { get; } = [];

    public SubtitlesPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        var settings = App.Services.GetRequiredService<IUserSettings>();
        ResultsList.ItemsSource = Results;
        LanguagesBox.Text = settings.DefaultSubtitleLanguages;
    }

    private async void Browse_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker
        { SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.VideosLibrary };
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
        var langText = (LanguagesBox.SelectedItem is ComboBoxItem cbi && cbi.Content is string s)
            ? s : (LanguagesBox.Text ?? "");
        var langs = string.IsNullOrWhiteSpace(langText) ? "en" : langText.Trim();
        var minScore = ((int)MinScoreBox.Value).ToString(CultureInfo.InvariantCulture);
        var args = new List<string> {
            "--root", folder, "--languages", langs, "--min-score", minScore
        };
        _cts = new CancellationTokenSource();
        SetRunning(true);
        Results.Clear();
        ScannedText.Text = "0"; DownloadedText.Text = "0";
        StatusText.Text = "Searching...";
        try
        {
            var r = await _python.RunScriptNdjsonAsync("subtitles_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = r.Success ? $"Done. {Results.Count(x => x.Status == "downloaded"):N0} subtitles fetched." : (r.ErrorMessage ?? r.Stderr);
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
                var path = root.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                var status = root.TryGetProperty("status", out var s) ? s.GetString() ?? "" : "";
                var lang = root.TryGetProperty("language", out var l) ? l.GetString() ?? "" : "";
                var prov = root.TryGetProperty("provider", out var pr) ? pr.GetString() ?? "" : "";
                Results.Add(new SubtitleResultItem(path, lang, prov, status));
                if (status == "downloaded")
                    DownloadedText.Text = Results.Count(x => x.Status == "downloaded")
                        .ToString("N0", CultureInfo.CurrentCulture);
                break;
            case "progress":
                if (root.TryGetProperty("scanned", out var sc) && sc.ValueKind == JsonValueKind.Number)
                    ScannedText.Text = sc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("stage", out var stage))
                    StatusText.Text = $"Searching... {stage.GetString()}";
                break;
            case "error":
                StatusText.Text = $"Error: {(root.TryGetProperty("message", out var m) ? m.GetString() : "")}";
                break;
        }
    }

    private void Cancel_Click(object sender, RoutedEventArgs e) { _cts?.Cancel(); StatusText.Text = "Cancelling..."; }

    private void SetRunning(bool running)
    {
        ScanButton.IsEnabled = !running; BrowseButton.IsEnabled = !running;
        FolderTextBox.IsEnabled = !running; LanguagesBox.IsEnabled = !running;
        MinScoreBox.IsEnabled = !running; CancelButton.IsEnabled = running;
    }
}

public sealed class SubtitleResultItem
{
    public string Path { get; }
    public string FileName { get; }
    public string Language { get; }
    public string Provider { get; }
    public string Status { get; }
    public Brush StatusBrush { get; }

    public SubtitleResultItem(string path, string language, string provider, string status)
    {
        Path = path;
        FileName = System.IO.Path.GetFileName(path);
        Language = language;
        Provider = provider;
        Status = status;
        StatusBrush = status switch
        {
            "downloaded" => (Brush)Application.Current.Resources["AccentGreenBrush"],
            "embedded" => (Brush)Application.Current.Resources["AccentBlueBrush"],
            "no_match" => (Brush)Application.Current.Resources["AccentYellowBrush"],
            "error" => (Brush)Application.Current.Resources["AccentRedBrush"],
            _ => (Brush)Application.Current.Resources["TextMutedBrush"],
        };
    }
}
