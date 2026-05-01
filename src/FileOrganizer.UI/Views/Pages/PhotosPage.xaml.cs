using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class PhotosPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    public ObservableCollection<PhotoRow> Results { get; } = [];

    public PhotosPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        ResultsList.ItemsSource = Results;
    }

    private string SelectedMode() =>
        ModeCombo.SelectedItem is ComboBoxItem c && c.Tag is string t ? t : "preview";

    private async void Browse_Click(object sender, RoutedEventArgs e)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker
        { SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.PicturesLibrary };
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var f = await picker.PickSingleFolderAsync();
        if (f is not null) FolderTextBox.Text = f.Path;
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
        ScannedText.Text = "0"; ExifText.Text = "0"; RenamedText.Text = "0";
        StatusText.Text = "Reading EXIF...";
        try
        {
            var r = await _python.RunScriptNdjsonAsync("photos_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = r.Success ? $"Done. {Results.Count:N0} photos." : (r.ErrorMessage ?? r.Stderr);
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
                var date = root.TryGetProperty("date", out var d) ? d.GetString() ?? "" : "";
                var camera = root.TryGetProperty("camera", out var c) ? c.GetString() ?? "" : "";
                var iso = root.TryGetProperty("iso", out var i) && i.ValueKind == JsonValueKind.Number
                    ? i.GetInt32().ToString(CultureInfo.InvariantCulture) : "";
                var aperture = root.TryGetProperty("aperture", out var a) ? a.GetString() ?? "" : "";
                var shutter = root.TryGetProperty("shutter", out var s) ? s.GetString() ?? "" : "";
                var gps = "";
                if (root.TryGetProperty("lat", out var lat) && root.TryGetProperty("lon", out var lon))
                    gps = $"{lat.GetDouble():F2}, {lon.GetDouble():F2}";
                Results.Add(new PhotoRow(path, date, camera, iso, aperture, shutter, gps));
                if (!string.IsNullOrEmpty(date))
                    ExifText.Text = Results.Count(x => !string.IsNullOrEmpty(x.Date))
                        .ToString("N0", CultureInfo.CurrentCulture);
                break;
            case "progress":
                if (root.TryGetProperty("scanned", out var sc) && sc.ValueKind == JsonValueKind.Number)
                    ScannedText.Text = sc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("stage", out var stage))
                    StatusText.Text = $"Reading EXIF... {stage.GetString()}";
                break;
            case "complete":
                if (root.TryGetProperty("renamed", out var rn) && rn.ValueKind == JsonValueKind.Number)
                    RenamedText.Text = rn.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
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
        ModeCombo.IsEnabled = !running; FolderTextBox.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }
}

public sealed class PhotoRow(string path, string date, string camera, string iso, string aperture, string shutter, string gps)
{
    public string Path { get; } = path;
    public string FileName { get; } = System.IO.Path.GetFileName(path);
    public string Date { get; } = date;
    public string Camera { get; } = camera;
    public string Iso { get; } = iso;
    public string Aperture { get; } = aperture;
    public string Shutter { get; } = shutter;
    public string Gps { get; } = string.IsNullOrEmpty(gps) ? "" : "📍 " + gps;
}
