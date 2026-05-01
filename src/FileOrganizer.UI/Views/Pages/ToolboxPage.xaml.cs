using System.Collections.ObjectModel;
using System.Text;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class ToolboxPage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    private readonly StringBuilder _output = new();

    public ObservableCollection<ToolTile> Tools { get; } = [];

    public ToolboxPage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
        SeedTools();
        ToolsRepeater.ItemsSource = Tools;
    }

    private void SeedTools()
    {
        Tools.Add(new ToolTile("organize-stats",
            "Pipeline status",
            "Show how many AI batches are classified, applied, and pending across all four pipelines.",
            "\uE7C3", "organize_run.py", new[] { "--stats" }));
        Tools.Add(new ToolTile("validate",
            "Validate sources",
            "Walk the source paths and report trailing-space / long-path issues before any moves.",
            "\uE73E", "organize_run.py", new[] { "--validate" }));
        Tools.Add(new ToolTile("asset-db-stats",
            "Asset DB summary",
            "Print SHA-256 fingerprint database stats — how many files cataloged, total size.",
            "\uE721", "asset_db.py", new[] { "--stats" }));
        Tools.Add(new ToolTile("undo-last",
            "Undo last 10 moves",
            "Roll back the most recent 10 organize-pipeline moves from the journal.",
            "\uE7A7", "organize_run.py", new[] { "--undo-last", "10" }));
        Tools.Add(new ToolTile("audit-organized",
            "Audit organized library",
            "Walk G:\\Organized + I:\\Organized, report category-name drift, phantom folders, and orphan items.",
            "\uE9F9", "audit_organized.py", Array.Empty<string>()));
        Tools.Add(new ToolTile("phantom-categories",
            "Phantom-category scan",
            "Find non-canonical top-level destination folders that don't match the master taxonomy.",
            "\uE946", "fix_phantom_categories.py", new[] { "--scan" }));
    }

    private async void Tool_Click(object sender, RoutedEventArgs e)
    {
        if (_cts is not null) return;
        if (sender is not Button b || b.Tag is not string id) return;
        var tool = Tools.FirstOrDefault(t => t.Id == id);
        if (tool is null) return;

        _cts = new CancellationTokenSource();
        CancelButton.IsEnabled = true;
        StatusText.Text = $"Running {tool.Script} {string.Join(' ', tool.Args)}...";
        _output.Clear();
        OutputBlock.Text = "";

        var progress = new Progress<string>(line =>
        {
            _output.AppendLine(line);
            OutputBlock.Text = _output.ToString();
            OutputScroller.ChangeView(null, double.MaxValue, null, true);
        });

        try
        {
            var r = await _python.RunScriptAsync(tool.Script, tool.Args, progress, _cts.Token);
            if (!string.IsNullOrEmpty(r.Stderr))
            {
                _output.AppendLine();
                _output.AppendLine("--- stderr ---");
                _output.Append(r.Stderr);
                OutputBlock.Text = _output.ToString();
            }
            StatusText.Text = r.Success
                ? $"Done. ({tool.Title})"
                : (r.ErrorMessage ?? $"Failed (exit {r.ExitCode}).");
        }
        catch (OperationCanceledException) { StatusText.Text = "Cancelled."; }
        catch (Exception ex) { StatusText.Text = $"Error: {ex.Message}"; }
        finally { _cts?.Dispose(); _cts = null; CancelButton.IsEnabled = false; }
    }

    private void Cancel_Click(object sender, RoutedEventArgs e)
    {
        _cts?.Cancel();
        StatusText.Text = "Cancelling...";
    }
}

public sealed class ToolTile(string id, string title, string description, string glyph,
                              string script, IEnumerable<string> args)
{
    public string Id { get; } = id;
    public string Title { get; } = title;
    public string Description { get; } = description;
    public string Glyph { get; } = glyph;
    public string Script { get; } = script;
    public IEnumerable<string> Args { get; } = args;
    public string Command { get; } = $"$ python {script} {string.Join(' ', args)}";
}
