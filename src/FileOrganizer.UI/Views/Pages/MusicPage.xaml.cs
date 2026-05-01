using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class MusicPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;

    public ObservableCollection<MusicResultItem> Results { get; } = [];

    public MusicPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        var settings = App.Services.GetRequiredService<IUserSettings>();
        ResultsList.ItemsSource = Results;
        // Pre-fill from saved settings so users don't have to type templates.
        PatternBox.Text = settings.DefaultMusicRenamePattern;
        if (string.IsNullOrEmpty(ApiKeyBox.Password))
            ApiKeyBox.Password = settings.AcoustIdApiKey;
    }

    private string SelectedMode()
    {
        if (ModeCombo.SelectedItem is ComboBoxItem cbi && cbi.Tag is string tag) return tag;
        return "preview";
    }

    private async void Browse_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker
        {
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.MusicLibrary,
        };
        picker.FileTypeFilter.Add("*");
        var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, hwnd);
        var folder = await picker.PickSingleFolderAsync();
        if (folder is not null) FolderTextBox.Text = folder.Path;
    }

    private async void Run_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        var folder = FolderTextBox.Text?.Trim() ?? "";
        if (string.IsNullOrEmpty(folder) || !Directory.Exists(folder))
        {
            StatusText.Text = "Pick a music folder first.";
            return;
        }

        var mode = SelectedMode();
        var args = new List<string> { "--root", folder, "--mode", mode };
        var pattern = PatternBox.Text?.Trim() ?? "";
        if (!string.IsNullOrEmpty(pattern))
            args.AddRange(new[] { "--rename-pattern", pattern });
        var apiKey = ApiKeyBox.Password?.Trim() ?? "";
        if (!string.IsNullOrEmpty(apiKey))
            args.AddRange(new[] { "--api-key", apiKey });

        _cts = new CancellationTokenSource();
        SetRunning(true);
        Results.Clear();
        ScannedText.Text = "0";
        MatchedText.Text = "0";
        RenamedText.Text = "0";
        StatusText.Text = $"Running... ({mode})";

        try
        {
            var result = await _python.RunScriptNdjsonAsync(
                "music_run.py", args, HandleEvent, _cts.Token);

            if (result.Success)
                StatusText.Text = $"Done. {Results.Count:N0} files processed.";
            else if (result.ExitCode == -1 && !string.IsNullOrEmpty(result.ErrorMessage))
                StatusText.Text = result.ErrorMessage;
            else
                StatusText.Text = $"Failed (exit {result.ExitCode}). {result.Stderr}".Trim();
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally
        {
            _cts?.Dispose();
            _cts = null;
            SetRunning(false);
        }
    }

    private void HandleEvent(string eventName, JsonElement root)
    {
        switch (eventName)
        {
            case "item":
                var path = root.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                var status = root.TryGetProperty("status", out var st) ? st.GetString() ?? "" : "";
                var matchType = root.TryGetProperty("match_type", out var mt) ? mt.GetString() ?? "" : "";
                var title = root.TryGetProperty("title", out var t) ? t.GetString() ?? "" : "";
                var artist = root.TryGetProperty("artist", out var ar) ? ar.GetString() ?? "" : "";
                var album = root.TryGetProperty("album", out var al) ? al.GetString() ?? "" : "";
                var year = root.TryGetProperty("year", out var y) && y.ValueKind == JsonValueKind.Number
                    ? y.GetInt32().ToString(CultureInfo.InvariantCulture) : "";
                if (string.IsNullOrEmpty(title)) title = Path.GetFileName(path);
                Results.Add(new MusicResultItem(path, title, artist, album, year, matchType, status));
                if (status == "matched")
                {
                    var n = Results.Count(r => r.Status == "matched");
                    MatchedText.Text = n.ToString("N0", CultureInfo.CurrentCulture);
                }
                break;

            case "progress":
                if (root.TryGetProperty("scanned", out var sc) && sc.ValueKind == JsonValueKind.Number)
                    ScannedText.Text = sc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("stage", out var stage))
                    StatusText.Text = $"Running... {stage.GetString()}";
                break;

            case "error":
                var msg = root.TryGetProperty("message", out var m) ? m.GetString() ?? "" : "";
                StatusText.Text = $"Error: {msg}";
                break;

            case "complete":
                if (root.TryGetProperty("matched_count", out var mc) && mc.ValueKind == JsonValueKind.Number)
                    MatchedText.Text = mc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("renamed_count", out var rc) && rc.ValueKind == JsonValueKind.Number)
                    RenamedText.Text = rc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
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
        ModeCombo.IsEnabled = !running;
        FolderTextBox.IsEnabled = !running;
        PatternBox.IsEnabled = !running;
        ApiKeyBox.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }
}

public sealed class MusicResultItem
{
    public string Path { get; }
    public string Title { get; }
    public string Artist { get; }
    public string Album { get; }
    public string Year { get; }
    public string MatchType { get; }
    public string Status { get; }
    public Brush MatchColor { get; }

    public MusicResultItem(string path, string title, string artist, string album,
                           string year, string matchType, string status)
    {
        Path = path;
        Title = title;
        Artist = artist;
        Album = album;
        Year = year;
        MatchType = matchType;
        Status = status;
        MatchColor = status switch
        {
            "matched" => (Brush)Application.Current.Resources["AccentGreenBrush"],
            "untagged" => (Brush)Application.Current.Resources["AccentYellowBrush"],
            "error" => (Brush)Application.Current.Resources["AccentRedBrush"],
            _ => (Brush)Application.Current.Resources["TextMutedBrush"],
        };
    }
}
