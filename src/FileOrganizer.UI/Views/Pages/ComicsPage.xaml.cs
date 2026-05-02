using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed class ComicRow
{
    public string Filename { get; set; } = "";
    public string Series { get; set; } = "";
    public string Volume { get; set; } = "";
    public string Publisher { get; set; } = "";
    public string Status { get; set; } = "";
}

public sealed partial class ComicsPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    public ObservableCollection<ComicRow> Results { get; } = [];

    public ComicsPage()
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
        { SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.DocumentsLibrary };
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
        ScannedText.Text = "0"; ExtractedText.Text = "0"; SeriesText.Text = "0"; OrganizedText.Text = "0";
        StatusText.Text = "Scanning for comic archives...";
        try
        {
            var r = await _python.RunScriptNdjsonAsync("comics_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = r.Success ? $"Done. {Results.Count:N0} comics." : (r.ErrorMessage ?? r.Stderr);
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally { _cts?.Dispose(); _cts = null; SetRunning(false); }
    }

    private void HandleEvent(string ev, JsonElement root)
    {
        MainWindow.Current?.DispatcherQueue.TryEnqueue(() =>
        {
            if (ev == "comic")
            {
                var filename = root.GetProperty("filename").GetString() ?? "Unknown";
                var series = root.GetProperty("series").GetString() ?? "Unknown";
                var volume = root.GetProperty("volume").GetString() ?? "Unknown";
                var publisher = root.GetProperty("publisher").GetString() ?? "Unknown";
                var status = root.GetProperty("status").GetString() ?? "OK";
                Results.Add(new ComicRow { Filename = filename, Series = series, Volume = volume, Publisher = publisher, Status = status });
            }
            else if (ev == "progress")
            {
                if (root.TryGetProperty("scanned", out var scanned)) ScannedText.Text = scanned.GetInt32().ToString("N0");
                if (root.TryGetProperty("extracted", out var extracted)) ExtractedText.Text = extracted.GetInt32().ToString("N0");
                if (root.TryGetProperty("series_count", out var series)) SeriesText.Text = series.GetInt32().ToString("N0");
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
