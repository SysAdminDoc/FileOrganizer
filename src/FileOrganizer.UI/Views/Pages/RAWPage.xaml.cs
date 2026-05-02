using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed class RawImageRow
{
    public string Filename { get; set; } = "";
    public string Camera { get; set; } = "";
    public string DateTaken { get; set; } = "";
    public string Iso { get; set; } = "";
    public string Status { get; set; } = "";
}

public sealed partial class RAWPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    public ObservableCollection<RawImageRow> Results { get; } = [];

    public RAWPage()
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
        ScannedText.Text = "0"; ExifText.Text = "0"; OrganizedText.Text = "0";
        StatusText.Text = "Scanning for RAW files...";
        try
        {
            var r = await _python.RunScriptNdjsonAsync("raw_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = r.Success ? $"Done. {Results.Count:N0} raw images." : (r.ErrorMessage ?? r.Stderr);
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally { _cts?.Dispose(); _cts = null; SetRunning(false); }
    }

    private void HandleEvent(string ev, JsonElement root)
    {
        MainWindow.Current?.DispatcherQueue.TryEnqueue(() =>
        {
            if (ev == "file")
            {
                var filename = root.GetProperty("filename").GetString() ?? "Unknown";
                var camera = root.GetProperty("camera").GetString() ?? "Unknown";
                var dateTaken = root.GetProperty("date_taken").GetString() ?? "Unknown";
                var iso = root.GetProperty("iso").GetString() ?? "Unknown";
                var status = root.GetProperty("status").GetString() ?? "OK";
                Results.Add(new RawImageRow { Filename = filename, Camera = camera, DateTaken = dateTaken, Iso = iso, Status = status });
            }
            else if (ev == "progress")
            {
                if (root.TryGetProperty("scanned", out var scanned)) ScannedText.Text = scanned.GetInt32().ToString("N0");
                if (root.TryGetProperty("exif_read", out var exif)) ExifText.Text = exif.GetInt32().ToString("N0");
                if (root.TryGetProperty("organized", out var organized)) OrganizedText.Text = organized.GetInt32().ToString("N0");
                if (root.TryGetProperty("status", out var status)) StatusText.Text = status.GetString() ?? "";
            }
        });
    }

    private void SetRunning(bool running)
    {
        FolderTextBox.IsEnabled = !running;
        BrowseButton.IsEnabled = !running;
        ModeCombo.IsEnabled = !running;
        ScanButton.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }

    private void Cancel_Click(object sender, RoutedEventArgs e)
    {
        _cts?.Cancel();
    }
}
