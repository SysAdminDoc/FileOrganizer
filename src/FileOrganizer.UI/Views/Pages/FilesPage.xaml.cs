using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class FilesPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    public ObservableCollection<FilesRow> Results { get; } = [];

    public FilesPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        ResultsList.ItemsSource = Results;
    }

    private string SelectedMode() =>
        ModeCombo.SelectedItem is ComboBoxItem c && c.Tag is string t ? t : "preview";

    private async void BrowseSource_Click(object sender, RoutedEventArgs e) =>
        SourceTextBox.Text = await PickAsync(Windows.Storage.Pickers.PickerLocationId.Downloads) ?? SourceTextBox.Text;
    private async void BrowseDest_Click(object sender, RoutedEventArgs e) =>
        DestTextBox.Text = await PickAsync(Windows.Storage.Pickers.PickerLocationId.Desktop) ?? DestTextBox.Text;

    private async Task<string?> PickAsync(Windows.Storage.Pickers.PickerLocationId start)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker { SuggestedStartLocation = start };
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var f = await picker.PickSingleFolderAsync();
        return f?.Path;
    }

    private async void Run_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        var src = SourceTextBox.Text?.Trim() ?? "";
        if (!Directory.Exists(src)) { StatusText.Text = "Source folder doesn't exist."; return; }

        var args = new List<string> { "--root", src, "--mode", SelectedMode() };
        var dst = DestTextBox.Text?.Trim() ?? "";
        if (!string.IsNullOrEmpty(dst)) args.AddRange(new[] { "--dest", dst });
        if (RecursiveCheck.IsChecked == true) args.Add("--recursive");

        _cts = new CancellationTokenSource();
        SetRunning(true);
        Results.Clear();
        ScannedText.Text = "0"; MovedText.Text = "0"; ErrorsText.Text = "0";
        StatusText.Text = $"Running ({SelectedMode()})...";
        try
        {
            var r = await _python.RunScriptNdjsonAsync("files_run.py", args, HandleEvent, _cts.Token);
            StatusText.Text = r.Success ? $"Done. {Results.Count:N0} items." : (r.ErrorMessage ?? r.Stderr);
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
                var src = root.TryGetProperty("path", out var p) ? p.GetString() ?? "" : "";
                var dst = root.TryGetProperty("new_path", out var d) ? d.GetString() ?? "" : "";
                var cat = root.TryGetProperty("category", out var c) ? c.GetString() ?? "Other" : "Other";
                Results.Add(new FilesRow(src, cat, dst));
                MovedText.Text = Results.Count.ToString("N0", CultureInfo.CurrentCulture);
                break;
            case "progress":
                if (root.TryGetProperty("scanned", out var sc) && sc.ValueKind == JsonValueKind.Number)
                    ScannedText.Text = sc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("stage", out var stage))
                    StatusText.Text = $"Running... {stage.GetString()}";
                break;
            case "complete":
                if (root.TryGetProperty("errors", out var er) && er.ValueKind == JsonValueKind.Number)
                    ErrorsText.Text = er.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                break;
            case "error":
                StatusText.Text = $"Error: {(root.TryGetProperty("message", out var m) ? m.GetString() : "")}";
                break;
        }
    }

    private void Cancel_Click(object sender, RoutedEventArgs e) { _cts?.Cancel(); StatusText.Text = "Cancelling..."; }

    private void SetRunning(bool running)
    {
        ScanButton.IsEnabled = !running; SourceBrowseButton.IsEnabled = !running;
        DestBrowseButton.IsEnabled = !running; ModeCombo.IsEnabled = !running;
        SourceTextBox.IsEnabled = !running; DestTextBox.IsEnabled = !running;
        RecursiveCheck.IsEnabled = !running; CancelButton.IsEnabled = running;
    }
}

public sealed class FilesRow(string source, string category, string dest)
{
    public string Source { get; } = source;
    public string Category { get; } = category;
    public string Dest { get; } = dest;
}
