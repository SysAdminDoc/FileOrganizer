using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class OrganizePage : Page
{
    private readonly IPythonRunner _python;
    private CancellationTokenSource? _cts;
    private readonly BoundedTextBuffer _liveOutput = new();

    public OrganizePage()
    {
        InitializeComponent();
        _python = App.Services.GetRequiredService<IPythonRunner>();
    }

    private string SelectedSource()
    {
        if (SourceCombo.SelectedItem is ComboBoxItem item && item.Tag is string t)
            return t;
        return "ae";
    }

    private async void Stats_Click(object sender, RoutedEventArgs e)
    {
        await RunAsync("Showing batch stats", new[] { "--stats" });
    }

    private async void Preview_Click(object sender, RoutedEventArgs e)
    {
        var source = SelectedSource();
        var args = source == "ae"
            ? new[] { "--preview", "--quiet" }
            : new[] { "--source", source, "--preview", "--quiet" };
        await RunAsync($"Preview (dry run) for source={source}", args);
    }

    private async void Validate_Click(object sender, RoutedEventArgs e)
    {
        var source = SelectedSource();
        var args = source == "ae"
            ? new[] { "--validate" }
            : new[] { "--source", source, "--validate" };
        await RunAsync($"Validating sources for source={source}", args);
    }

    private async void ProvenanceStats_Click(object sender, RoutedEventArgs e)
    {
        await RunAsync(
            "Reviewing redacted AI evaluation records",
            new[] { "--stats" },
            "provenance_run.py");
    }

    private async void ExportProvenance_Click(object sender, RoutedEventArgs e)
    {
        await RunAsync(
            "Exporting redacted AI evaluation records",
            new[] { "--export" },
            "provenance_run.py");
    }

    private void Cancel_Click(object sender, RoutedEventArgs e)
    {
        _cts?.Cancel();
        StatusText.Text = "Cancelling...";
    }

    private async Task RunAsync(
        string statusLabel,
        IEnumerable<string> args,
        string script = "organize_run.py")
    {
        if (_cts is not null)
        {
            return; // already running
        }

        _cts = new CancellationTokenSource();
        SetRunning(true);
        StatusText.Text = statusLabel + "...";
        _liveOutput.Clear();
        OutputBlock.Text = "";
        OutputSummary.Text = "running...";

        var lineProgress = new Progress<string>(line =>
        {
            // Already on UI thread because Progress<T> captures the current sync context.
            if (_liveOutput.AppendLine(line))
                RenderOutput();
        });

        try
        {
            var result = await _python.RunScriptAsync(
                script,
                args,
                lineProgress,
                _cts.Token);

            if (!string.IsNullOrEmpty(result.Stderr))
            {
                _liveOutput.AppendLine();
                _liveOutput.AppendLine("--- stderr ---");
                _liveOutput.Append(result.Stderr);
                RenderOutput();
            }

            if (result.Success)
            {
                StatusText.Text = $"Done. {statusLabel.ToLowerInvariant()} completed.";
                OutputSummary.Text = "completed · exit 0";
            }
            else if (result.ErrorMessage is not null && result.ExitCode == -1 && result.Stdout.Length == 0)
            {
                StatusText.Text = result.ErrorMessage;
                OutputSummary.Text = "failed to start";
                _liveOutput.AppendLine(result.ErrorMessage);
                RenderOutput();
            }
            else
            {
                StatusText.Text = $"Failed (exit {result.ExitCode}). See output below.";
                OutputSummary.Text = $"failed · exit {result.ExitCode}";
            }
        }
        catch (OperationCanceledException)
        {
            StatusText.Text = "Cancelled.";
            OutputSummary.Text = "cancelled";
        }
        catch (Exception ex)
        {
            StatusText.Text = $"Unexpected error: {ex.Message}";
            OutputSummary.Text = "error";
            _liveOutput.AppendLine();
            _liveOutput.AppendLine("--- exception ---");
            _liveOutput.AppendLine(ex.ToString());
            RenderOutput();
        }
        finally
        {
            RenderOutput();
            if (_liveOutput.TruncatedCharacters > 0)
                OutputSummary.Text += $" · showing latest {UiStreamLimits.MaxOutputCharacters:N0} chars";
            _cts?.Dispose();
            _cts = null;
            SetRunning(false);
        }
    }

    private void RenderOutput()
    {
        OutputBlock.Text = _liveOutput.Snapshot();
        OutputScroller.ChangeView(null, double.MaxValue, null, disableAnimation: true);
    }

    private void SetRunning(bool running)
    {
        StatsButton.IsEnabled = !running;
        PreviewButton.IsEnabled = !running;
        ValidateButton.IsEnabled = !running;
        ProvenanceStatsButton.IsEnabled = !running;
        ExportProvenanceButton.IsEnabled = !running;
        SourceCombo.IsEnabled = !running;
        CancelButton.IsEnabled = running;
    }
}
