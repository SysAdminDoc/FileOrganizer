using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class SmartSortPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    private readonly Dictionary<string, CategoryStat> _categoryStats = new();
    private readonly Dictionary<string, (string glyph, string brushKey)> _categoryMeta = new()
    {
        ["audio"] = ("\uE8D6", "AccentVioletBrush"),
        ["video"] = ("\uE714", "AccentRedBrush"),
        ["image"] = ("\uEB9F", "AccentGreenBrush"),
        ["book"] = ("\uE82D", "AccentYellowBrush"),
        ["pdf"] = ("\uEA90", "AccentOrangeBrush"),
        ["font"] = ("\uE185", "AccentBlueBrush"),
        ["archive"] = ("\uE7B8", "AccentCyanBrush"),
        ["code"] = ("\uE943", "AccentBlueBrush"),
        ["document"] = ("\uE8A5", "AccentBlueBrush"),
        ["other"] = ("\uE713", "TextMutedBrush"),
    };

    public ObservableCollection<SmartItemRow> Results { get; } = [];
    public ObservableCollection<CategoryStat> Categories { get; } = [];

    public SmartSortPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        ResultsList.ItemsSource = Results;
        CategoryStrip.ItemsSource = Categories;
    }

    private string SelectedMode() =>
        ModeCombo.SelectedItem is ComboBoxItem c && c.Tag is string t ? t : "preview";

    private async void BrowseSource_Click(object sender, RoutedEventArgs e) =>
        SourceTextBox.Text = await PickFolderAsync(Windows.Storage.Pickers.PickerLocationId.Downloads) ?? SourceTextBox.Text;

    private async void BrowseDest_Click(object sender, RoutedEventArgs e) =>
        DestTextBox.Text = await PickFolderAsync(Windows.Storage.Pickers.PickerLocationId.Desktop) ?? DestTextBox.Text;

    private async Task<string?> PickFolderAsync(Windows.Storage.Pickers.PickerLocationId start)
    {
        var picker = new Windows.Storage.Pickers.FolderPicker { SuggestedStartLocation = start };
        picker.FileTypeFilter.Add("*");
        WinRT.Interop.InitializeWithWindow.Initialize(picker,
            WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle));
        var folder = await picker.PickSingleFolderAsync();
        return folder?.Path;
    }

    private async void Run_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        var src = SourceTextBox.Text?.Trim() ?? "";
        var dst = DestTextBox.Text?.Trim() ?? "";
        if (!Directory.Exists(src)) { StatusText.Text = "Source folder does not exist."; return; }
        if (string.IsNullOrEmpty(dst)) { StatusText.Text = "Pick a destination folder."; return; }

        var mode = SelectedMode();
        var args = new List<string> { "--root", src, "--dest", dst, "--mode", mode };
        if (CopyCheck.IsChecked == true) args.Add("--copy");

        _cts = new CancellationTokenSource();
        SetRunning(true);
        Results.Clear();
        Categories.Clear();
        _categoryStats.Clear();
        ScannedText.Text = "0"; PlannedText.Text = "0"; MovedText.Text = "0"; ErrorsText.Text = "0";
        StatusText.Text = $"Running ({mode})...";

        try
        {
            var r = await _python.RunScriptNdjsonAsync("smart_run.py", args, HandleEvent, _cts.Token);
            if (r.Success)
                StatusText.Text = $"Done. {Results.Count:N0} items processed across {Categories.Count} categories.";
            else
                StatusText.Text = r.ErrorMessage ?? r.Stderr ?? $"Failed (exit {r.ExitCode}).";
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
                var cat = root.TryGetProperty("category", out var c) ? c.GetString() ?? "other" : "other";
                var status = root.TryGetProperty("status", out var s) ? s.GetString() ?? "" : "";
                Results.Add(new SmartItemRow(src, dst, cat, status));

                if (!_categoryStats.TryGetValue(cat, out var stat))
                {
                    var (glyph, brushKey) = _categoryMeta.TryGetValue(cat, out var meta)
                        ? meta : ("\uE713", "TextMutedBrush");
                    stat = new CategoryStat(cat, glyph,
                        (Brush)Application.Current.Resources[brushKey]);
                    _categoryStats[cat] = stat;
                    Categories.Add(stat);
                }
                stat.Increment();
                break;
            case "progress":
                if (root.TryGetProperty("scanned", out var sc) && sc.ValueKind == JsonValueKind.Number)
                    ScannedText.Text = sc.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("planned", out var pl) && pl.ValueKind == JsonValueKind.Number)
                    PlannedText.Text = pl.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("moved", out var mv) && mv.ValueKind == JsonValueKind.Number)
                    MovedText.Text = mv.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("stage", out var stage))
                    StatusText.Text = $"Running... {stage.GetString()}";
                break;
            case "complete":
                if (root.TryGetProperty("planned", out var pp) && pp.ValueKind == JsonValueKind.Number)
                    PlannedText.Text = pp.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("moved", out var mm) && mm.ValueKind == JsonValueKind.Number)
                    MovedText.Text = mm.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                if (root.TryGetProperty("errors", out var er) && er.ValueKind == JsonValueKind.Number)
                    ErrorsText.Text = er.GetInt64().ToString("N0", CultureInfo.CurrentCulture);
                break;
            case "error":
                StatusText.Text = $"Error: {(root.TryGetProperty("message", out var em) ? em.GetString() : "")}";
                break;
        }
    }

    private void Cancel_Click(object sender, RoutedEventArgs e) { _cts?.Cancel(); StatusText.Text = "Cancelling..."; }

    private void SetRunning(bool running)
    {
        ScanButton.IsEnabled = !running; SourceBrowseButton.IsEnabled = !running;
        DestBrowseButton.IsEnabled = !running; ModeCombo.IsEnabled = !running;
        SourceTextBox.IsEnabled = !running; DestTextBox.IsEnabled = !running;
        CopyCheck.IsEnabled = !running; CancelButton.IsEnabled = running;
    }
}

public sealed class SmartItemRow
{
    public string Source { get; }
    public string Dest { get; }
    public string Category { get; }
    public string Status { get; }
    public Brush CategoryBrush { get; }
    public Brush StatusBrush { get; }

    public SmartItemRow(string source, string dest, string category, string status)
    {
        Source = source;
        Dest = dest;
        Category = category;
        Status = status;
        CategoryBrush = (Brush)Application.Current.Resources[category switch
        {
            "audio" => "AccentVioletBrush",
            "video" => "AccentRedBrush",
            "image" => "AccentGreenBrush",
            "book" => "AccentYellowBrush",
            "pdf" => "AccentOrangeBrush",
            "font" => "AccentBlueBrush",
            "archive" => "AccentCyanBrush",
            "code" => "AccentBlueBrush",
            "document" => "AccentBlueBrush",
            _ => "TextMutedBrush",
        }];
        StatusBrush = (Brush)Application.Current.Resources[status switch
        {
            "moved" => "AccentGreenBrush",
            "planned" => "AccentPrimaryBrush",
            "skipped" => "TextMutedBrush",
            "error" => "AccentRedBrush",
            _ => "TextSecondaryBrush",
        }];
    }
}

public sealed class CategoryStat : System.ComponentModel.INotifyPropertyChanged
{
    public string Name { get; }
    public string Glyph { get; }
    public Brush AccentBrush { get; }
    private long _count;
    public string CountText => _count.ToString("N0", CultureInfo.CurrentCulture);

    public event System.ComponentModel.PropertyChangedEventHandler? PropertyChanged;

    public CategoryStat(string name, string glyph, Brush accent)
    {
        Name = name.Length > 0 ? char.ToUpper(name[0]) + name[1..] : name;
        Glyph = glyph;
        AccentBrush = accent;
    }

    public void Increment()
    {
        _count++;
        PropertyChanged?.Invoke(this, new System.ComponentModel.PropertyChangedEventArgs(nameof(CountText)));
    }
}
