using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Storage;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class WatchPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    private long _detected;
    private long _moved;
    public ObservableCollection<WatchSpec> Watches { get; } = [];
    public ObservableCollection<WatchEvent> Events { get; } = [];

    public WatchPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        WatchesList.ItemsSource = Watches;
        EventsList.ItemsSource = Events;
        Watches.CollectionChanged += (_, _) => WatchCountText.Text = $"{Watches.Count} configured";
        LoadSavedWatches();
    }

    private async void BrowseSrc_Click(object sender, RoutedEventArgs e) =>
        NewSrcBox.Text = await PickAsync(Windows.Storage.Pickers.PickerLocationId.Downloads) ?? NewSrcBox.Text;
    private async void BrowseDst_Click(object sender, RoutedEventArgs e) =>
        NewDstBox.Text = await PickAsync(Windows.Storage.Pickers.PickerLocationId.Desktop) ?? NewDstBox.Text;

    private async Task<string?> PickAsync(Windows.Storage.Pickers.PickerLocationId start)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker { SuggestedStartLocation = start };
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var f = await picker.PickSingleFolderAsync();
        return f?.Path;
    }

    private void AddWatch_Click(object sender, RoutedEventArgs e)
    {
        var src = NewSrcBox.Text?.Trim() ?? "";
        var dst = NewDstBox.Text?.Trim() ?? "";
        if (!Directory.Exists(src) || string.IsNullOrEmpty(dst))
        {
            StatusText.Text = "Source must exist; destination must be set.";
            return;
        }
        if (Watches.Any(w => w.Src.Equals(src, StringComparison.OrdinalIgnoreCase)))
        {
            StatusText.Text = "That source is already watched.";
            return;
        }
        Watches.Add(new WatchSpec(src, dst, NewCopyCheck.IsChecked == true));
        SaveWatches();
        NewSrcBox.Text = ""; NewDstBox.Text = ""; NewCopyCheck.IsChecked = false;
        StatusText.Text = "Watch added.";
    }

    private void RemoveWatch_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button b && b.Tag is string src)
        {
            var match = Watches.FirstOrDefault(w => w.Src == src);
            if (match is not null)
            {
                Watches.Remove(match);
                SaveWatches();
            }
        }
    }

    private async void Start_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        if (Watches.Count == 0) { StatusText.Text = "Add at least one watch first."; return; }

        var json = JsonSerializer.Serialize(
            Watches.Select(w => new { src = w.Src, dest = w.Dest, copy = w.Copy }));
        var args = new[] { "--watches", json };

        _cts = new CancellationTokenSource();
        StartButton.IsEnabled = false; StopButton.IsEnabled = true;
        _detected = 0; _moved = 0;
        DetectedText.Text = "0"; MovedText.Text = "0";
        Events.Clear();
        StatusText.Text = $"Watching {Watches.Count} folder(s)...";

        try
        {
            var r = await _python.RunScriptNdjsonAsync("watch_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = "Stopped.";
        }
        catch (OperationCanceledException) { StatusText.Text = "Stopped."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally { _cts?.Dispose(); _cts = null; StartButton.IsEnabled = true; StopButton.IsEnabled = false; }
    }

    private void Stop_Click(object sender, RoutedEventArgs e)
    {
        _cts?.Cancel();
        StatusText.Text = "Stopping...";
    }

    private void HandleEvent(string ev, JsonElement root)
    {
        var now = DateTime.Now.ToString("HH:mm:ss");
        switch (ev)
        {
            case "detected":
                _detected++;
                DetectedText.Text = _detected.ToString("N0", CultureInfo.CurrentCulture);
                Events.Add(new WatchEvent(now, "detected",
                    $"Detected: {Path.GetFileName(root.GetProperty("path").GetString() ?? "")}"));
                TrimEvents();
                break;
            case "item":
                var status = root.TryGetProperty("status", out var s) ? s.GetString() ?? "" : "";
                var path = root.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                var newPath = root.TryGetProperty("new_path", out var np) ? np.GetString() ?? "" : "";
                if (status == "moved" || status == "copied") _moved++;
                MovedText.Text = _moved.ToString("N0", CultureInfo.CurrentCulture);
                Events.Add(new WatchEvent(now, status,
                    $"{Path.GetFileName(path)} → {newPath}"));
                TrimEvents();
                break;
            case "heartbeat":
                if (root.TryGetProperty("checked", out var ch) && root.TryGetProperty("moved", out var mv))
                    HeartbeatText.Text = $"♥ checked {ch.GetInt64():N0} files / {mv.GetInt64():N0} routed";
                break;
            case "error":
                Events.Add(new WatchEvent(now, "error",
                    root.TryGetProperty("message", out var m) ? m.GetString() ?? "" : ""));
                TrimEvents();
                break;
        }
    }

    private void TrimEvents()
    {
        while (Events.Count > 200) Events.RemoveAt(0);
    }

    // Persistence — comma-joined "src||dest||copy" lines in a single string.
    private const string WatchesKey = "Watches.v1";

    private void LoadSavedWatches()
    {
        try
        {
            if (ApplicationData.Current.LocalSettings.Values.TryGetValue(WatchesKey, out var v) && v is string raw)
            {
                foreach (var line in raw.Split('\n', StringSplitOptions.RemoveEmptyEntries))
                {
                    var parts = line.Split("||");
                    if (parts.Length >= 2 && Directory.Exists(parts[0]))
                    {
                        bool copy = parts.Length > 2 && parts[2] == "1";
                        Watches.Add(new WatchSpec(parts[0], parts[1], copy));
                    }
                }
            }
        }
        catch { }
    }

    private void SaveWatches()
    {
        try
        {
            var raw = string.Join('\n',
                Watches.Select(w => $"{w.Src}||{w.Dest}||{(w.Copy ? "1" : "0")}"));
            ApplicationData.Current.LocalSettings.Values[WatchesKey] = raw;
        }
        catch { }
    }
}

public sealed class WatchSpec(string src, string dest, bool copy)
{
    public string Src { get; } = src;
    public string Dest { get; } = dest;
    public bool Copy { get; } = copy;
    public string DestArrow { get; } = $"→ {dest}{(copy ? " (copy)" : "")}";
}

public sealed class WatchEvent(string time, string status, string message)
{
    public string Time { get; } = time;
    public string Status { get; } = status;
    public string Message { get; } = message;
    public Brush StatusBrush { get; } = (Brush)Application.Current.Resources[status switch
    {
        "moved" or "copied" => "AccentGreenBrush",
        "detected" => "AccentBlueBrush",
        "error" => "AccentRedBrush",
        _ => "TextMutedBrush",
    }];
}
