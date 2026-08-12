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
    public string FocalLength { get; set; } = "";
    public string Status { get; set; } = "";
}

public sealed partial class RAWPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    public BoundedObservableCollection<RawImageRow> Results { get; } =
        new(isImportant: item => item.Status.Equals("error", StringComparison.OrdinalIgnoreCase));

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

    private async void Convert_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;

        var sourcePicker = new Windows.Storage.Pickers.FileOpenPicker
        {
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.PicturesLibrary,
        };
        foreach (var extension in new[]
        {
            ".dng", ".cr2", ".cr3", ".crw", ".nef", ".nrw", ".arw", ".srw", ".orf",
            ".rw2", ".raf", ".pef", ".rwl", ".x3f", ".3fr", ".dcr", ".kdc", ".mrw",
            ".raw", ".iiq", ".fff", ".mef", ".mos", ".cap",
        }) sourcePicker.FileTypeFilter.Add(extension);
        WinRT.Interop.InitializeWithWindow.Initialize(sourcePicker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var source = await sourcePicker.PickSingleFileAsync();
        if (source is null) return;

        var destinationPicker = new Windows.Storage.Pickers.FolderPicker
        {
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.PicturesLibrary,
        };
        destinationPicker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(destinationPicker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var destinationFolder = await destinationPicker.PickSingleFolderAsync();
        if (destinationFolder is null) return;

        var destination = Path.Combine(
            destinationFolder.Path, Path.GetFileNameWithoutExtension(source.Name) + ".dng");
        if (File.Exists(destination) && !string.Equals(source.Path, destination, StringComparison.OrdinalIgnoreCase))
        {
            StatusText.Text = $"A DNG already exists at {destination}; no file was overwritten.";
            return;
        }

        _cts = new CancellationTokenSource();
        SetRunning(true);
        StatusText.Text = "Saving a DNG copy...";
        try
        {
            var result = await _python.RunScriptNdjsonAsync(
                "raw_run.py",
                ["--convert-dng", source.Path, "--output", destination],
                HandleEvent,
                _cts.Token);
            if (!result.Success)
                StatusText.Text = result.ErrorMessage ?? result.Stderr;
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally
        {
            Results.FlushPendingChanges();
            _cts?.Dispose();
            _cts = null;
            SetRunning(false);
        }
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
            StatusText.Text = r.Success
                ? $"Done. {Results.TotalAdded:N0} raw images.{Results.RetentionNotice}"
                : (r.ErrorMessage ?? r.Stderr);
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally { Results.FlushPendingChanges(); _cts?.Dispose(); _cts = null; SetRunning(false); }
    }

    private void HandleEvent(string ev, JsonElement root)
    {
        if (ev == "file")
        {
            var filename = GetText(root, "filename", "Unknown");
            var camera = GetText(root, "camera", "Unknown");
            var dateTaken = GetText(root, "date_taken", "Unknown");
            var iso = GetText(root, "iso", "Unknown");
            var focalLength = GetText(root, "focal_length", "Unknown");
            var status = GetText(root, "status", "OK");
            var destination = GetText(root, "destination");
            var backend = GetText(root, "backend");
            if (!string.IsNullOrWhiteSpace(destination))
            {
                var format = GetText(root, "raw_format", "RAW");
                StatusText.Text = $"{status}: {format} via {backend}; saved to {destination}";
            }
            Results.Add(new RawImageRow
            {
                Filename = filename,
                Camera = camera,
                DateTaken = dateTaken,
                Iso = iso,
                FocalLength = focalLength,
                Status = status,
            });
        }
        else if (ev == "progress")
        {
            if (root.TryGetProperty("scanned", out var scanned)) ScannedText.Text = scanned.GetInt32().ToString("N0");
            if (root.TryGetProperty("exif_read", out var exif)) ExifText.Text = exif.GetInt32().ToString("N0");
            if (root.TryGetProperty("organized", out var organized)) OrganizedText.Text = organized.GetInt32().ToString("N0");
            if (root.TryGetProperty("status", out var status)) StatusText.Text = status.GetString() ?? "";
        }
        else if (ev == "plan")
        {
            var path = root.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
            var items = root.TryGetProperty("items", out var i) ? i.GetInt32() : 0;
            var dryRun = root.TryGetProperty("dry_run", out var d) && d.GetBoolean();
            StatusText.Text = dryRun
                ? $"Dry-run plan written for {items:N0} RAW files: {path}"
                : $"Moved {items:N0} RAW files. Plan: {path}";
        }
    }

    private static string GetText(JsonElement root, string property, string fallback = "") =>
        root.TryGetProperty(property, out var value) && value.ValueKind == JsonValueKind.String
            ? value.GetString() ?? fallback
            : fallback;

    private void SetRunning(bool running)
    {
        FolderTextBox.IsEnabled = !running;
        BrowseButton.IsEnabled = !running;
        ConvertButton.IsEnabled = !running;
        ModeCombo.IsEnabled = !running;
        ScanButton.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }

    private void Cancel_Click(object sender, RoutedEventArgs e)
    {
        _cts?.Cancel();
    }
}
