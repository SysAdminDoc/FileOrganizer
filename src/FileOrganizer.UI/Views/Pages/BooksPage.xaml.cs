using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class BooksPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;

    public ObservableCollection<BookResultItem> Results { get; } = [];

    public BooksPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        ResultsList.ItemsSource = Results;
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
            SuggestedStartLocation = Windows.Storage.Pickers.PickerLocationId.DocumentsLibrary,
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
            StatusText.Text = "Pick a books folder first.";
            return;
        }

        var mode = SelectedMode();
        var args = new List<string> { "--root", folder, "--mode", mode };
        var pattern = PatternBox.Text?.Trim() ?? "";
        if (!string.IsNullOrEmpty(pattern))
            args.AddRange(new[] { "--rename-pattern", pattern });
        if (IsbnLookupCheck.IsChecked == true)
            args.Add("--isbn-lookup");

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
                "books_run.py", args, HandleEvent, _cts.Token);

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
                var author = root.TryGetProperty("author", out var a) ? a.GetString() ?? "" : "";
                var series = root.TryGetProperty("series", out var sr) ? sr.GetString() ?? "" : "";
                var year = root.TryGetProperty("year", out var y) && y.ValueKind == JsonValueKind.Number
                    ? y.GetInt32().ToString(CultureInfo.InvariantCulture) : "";
                var isbn = root.TryGetProperty("isbn", out var isb) ? isb.GetString() ?? "" : "";
                var format = root.TryGetProperty("format", out var f) ? f.GetString() ?? "" : "";
                if (string.IsNullOrEmpty(title)) title = Path.GetFileName(path);
                Results.Add(new BookResultItem(path, title, author, series, year, isbn, format, status));
                if (status == "matched")
                    MatchedText.Text = Results.Count(r => r.Status == "matched")
                        .ToString("N0", CultureInfo.CurrentCulture);
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
        IsbnLookupCheck.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }
}

public sealed class BookResultItem
{
    public string Path { get; }
    public string Title { get; }
    public string Author { get; }
    public string Series { get; }
    public string Year { get; }
    public string Isbn { get; }
    public string Format { get; }
    public string Status { get; }

    public BookResultItem(string path, string title, string author, string series,
                          string year, string isbn, string format, string status)
    {
        Path = path;
        Title = title;
        Author = author;
        Series = series;
        Year = year;
        Isbn = isbn;
        Format = format.ToUpperInvariant();
        Status = status;
    }
}
