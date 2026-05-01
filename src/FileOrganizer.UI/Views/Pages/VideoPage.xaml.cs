using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class VideoPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;

    public ObservableCollection<VideoResultItem> Results { get; } = [];

    public VideoPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        var settings = App.Services.GetRequiredService<IUserSettings>();
        ResultsList.ItemsSource = Results;
        PatternBox.Text = settings.DefaultVideoRenamePattern;
    }

    private void MoviesPreset_Click(object sender, RoutedEventArgs e) =>
        PatternBox.Text = "Movies/{title} ({year})/{title} ({year}).{ext}";
    private void TvPreset_Click(object sender, RoutedEventArgs e) =>
        PatternBox.Text = "TV/{title}/Season {season:02}/{title} - S{season:02}E{episode:02}.{ext}";

    private string SelectedMode()
    {
        if (ModeCombo.SelectedItem is ComboBoxItem cbi && cbi.Tag is string tag) return tag;
        return "preview";
    }

    private async void Browse_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker
        {
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.VideosLibrary,
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
            StatusText.Text = "Pick a video folder first.";
            return;
        }

        var mode = SelectedMode();
        var args = new List<string> { "--root", folder, "--mode", mode };
        var pattern = PatternBox.Text?.Trim() ?? "";
        if (!string.IsNullOrEmpty(pattern))
            args.AddRange(new[] { "--rename-pattern", pattern });

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
                "video_run.py", args, HandleEvent, _cts.Token);

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
                var title = root.TryGetProperty("title", out var t) ? t.GetString() ?? "" : "";
                var year = root.TryGetProperty("year", out var y) && y.ValueKind == JsonValueKind.Number
                    ? y.GetInt32().ToString(CultureInfo.InvariantCulture) : "";
                var season = root.TryGetProperty("season", out var s) && s.ValueKind == JsonValueKind.Number
                    ? s.GetInt32() : (int?)null;
                var episode = root.TryGetProperty("episode", out var ep) && ep.ValueKind == JsonValueKind.Number
                    ? ep.GetInt32() : (int?)null;
                var se = (season is null) ? "" : (episode is null ? $"S{season:D2}" : $"S{season:D2}E{episode:D2}");
                var resolution = root.TryGetProperty("resolution", out var rs) ? rs.GetString() ?? "" : "";
                var source = root.TryGetProperty("source", out var sc) ? sc.GetString() ?? "" : "";
                var codec = root.TryGetProperty("video_codec", out var vc) ? vc.GetString() ?? "" : "";
                var score = root.TryGetProperty("score", out var sk) && sk.ValueKind == JsonValueKind.Number
                    ? sk.GetInt64().ToString("N0", CultureInfo.CurrentCulture) : "";
                bool? keeper = null;
                if (root.TryGetProperty("keeper", out var kp))
                {
                    keeper = kp.ValueKind == JsonValueKind.True ? true
                          : kp.ValueKind == JsonValueKind.False ? false : (bool?)null;
                }
                if (string.IsNullOrEmpty(title)) title = Path.GetFileName(path);
                Results.Add(new VideoResultItem(path, title, year, se, resolution, source, codec, score, keeper, status));
                if (status == "matched")
                    MatchedText.Text = Results.Count.ToString("N0", CultureInfo.CurrentCulture);
                break;

            case "progress":
                if (root.TryGetProperty("scanned", out var pSc) && pSc.ValueKind == JsonValueKind.Number)
                    ScannedText.Text = pSc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
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
        CancelButton.IsEnabled = running;
    }
}

public sealed class VideoResultItem
{
    public string Path { get; }
    public string Title { get; }
    public string Year { get; }
    public string SE { get; }
    public string Resolution { get; }
    public string Source { get; }
    public string Codec { get; }
    public string Score { get; }
    public string KeeperBadge { get; }
    public Brush KeeperBrush { get; }

    public VideoResultItem(string path, string title, string year, string se,
        string resolution, string source, string codec, string score, bool? keeper, string status)
    {
        Path = path;
        Title = title;
        Year = year;
        SE = se;
        Resolution = resolution;
        Source = source;
        Codec = codec;
        Score = score;
        KeeperBadge = keeper switch
        {
            true => "★",
            false => "—",
            _ => "",
        };
        KeeperBrush = keeper switch
        {
            true => (Brush)Application.Current.Resources["AccentGreenBrush"],
            false => (Brush)Application.Current.Resources["TextSubtleBrush"],
            _ => (Brush)Application.Current.Resources["TextMutedBrush"],
        };
    }
}
