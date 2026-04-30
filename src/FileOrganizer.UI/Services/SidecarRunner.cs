using System.Diagnostics;
using System.Text.Json;

namespace FileOrganizer.UI.Services;

public sealed record SidecarProgress(double Percent, string Stage, int? EtaSeconds);

public sealed record SidecarLog(string Level, string Message);

public sealed record SidecarResult(
    bool Success,
    string? OutputPath,
    long? SizeBytes,
    string? ErrorCode,
    string? ErrorMessage,
    int ExitCode);

public interface ISidecarRunner
{
    /// <summary>
    /// Resolve the full path to a sidecar binary. Returns null if not found.
    /// Search order: tools/&lt;name&gt;/&lt;name&gt;.exe walking up from BaseDirectory,
    /// then %LocalAppData%/FileOrganizer/tools/.
    /// </summary>
    string? Locate(string toolName);

    public static readonly TimeSpan DefaultSilenceTimeout = TimeSpan.FromMinutes(10);

    Task<SidecarResult> RunAsync(
        string toolName,
        IEnumerable<string> args,
        IProgress<SidecarProgress>? progress = null,
        IProgress<SidecarLog>? log = null,
        CancellationToken ct = default,
        Action<string, JsonElement>? onRawEvent = null,
        TimeSpan? silenceTimeout = null);
}

public sealed class SidecarRunner : ISidecarRunner
{
    public string? Locate(string toolName)
    {
        var exeName = toolName + ".exe";

        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            var candidate = Path.Combine(dir.FullName, "tools", toolName, exeName);
            if (File.Exists(candidate)) return candidate;
            dir = dir.Parent;
        }

        var localApp = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "FileOrganizer", "tools", toolName, exeName);
        if (File.Exists(localApp)) return localApp;

        return null;
    }

    public async Task<SidecarResult> RunAsync(
        string toolName,
        IEnumerable<string> args,
        IProgress<SidecarProgress>? progress = null,
        IProgress<SidecarLog>? log = null,
        CancellationToken ct = default,
        Action<string, JsonElement>? onRawEvent = null,
        TimeSpan? silenceTimeout = null)
    {
        var exe = Locate(toolName);
        if (exe is null)
        {
            return new SidecarResult(
                Success: false,
                OutputPath: null,
                SizeBytes: null,
                ErrorCode: "sidecar_not_found",
                ErrorMessage:
                    $"Could not locate '{toolName}.exe'. Build it with " +
                    $"`pwsh tools/{toolName}/build.ps1`, or drop a frozen exe at " +
                    $"%LocalAppData%/FileOrganizer/tools/{toolName}/{toolName}.exe.",
                ExitCode: -1);
        }

        var psi = new ProcessStartInfo
        {
            FileName = exe,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
        };
        foreach (var a in args) psi.ArgumentList.Add(a);

        using var process = new Process { StartInfo = psi };

        string? finalOutput = null;
        long? finalSize = null;
        string? errorCode = null;
        string? errorMessage = null;

        var effectiveTimeout = silenceTimeout ?? ISidecarRunner.DefaultSilenceTimeout;
        using var watchdogCts = new CancellationTokenSource();
        using var linkedCts = CancellationTokenSource.CreateLinkedTokenSource(ct, watchdogCts.Token);
        var lct = linkedCts.Token;
        var stuckByWatchdog = false;

        void ResetWatchdog()
        {
            try { watchdogCts.CancelAfter(effectiveTimeout); }
            catch (ObjectDisposedException) { }
        }
        ResetWatchdog();

        process.Start();

        var stdoutTask = Task.Run(async () =>
        {
            try
            {
                while (!process.StandardOutput.EndOfStream)
                {
                    lct.ThrowIfCancellationRequested();
                    var line = await process.StandardOutput.ReadLineAsync(lct).ConfigureAwait(false);
                    if (string.IsNullOrWhiteSpace(line)) continue;

                    ResetWatchdog();

                    try
                    {
                        using var doc = JsonDocument.Parse(line);
                        var root = doc.RootElement;
                        if (!root.TryGetProperty("event", out var ev)) continue;
                        var evName = ev.GetString();

                        if (onRawEvent is not null && evName is not null)
                            onRawEvent(evName, root.Clone());

                        switch (evName)
                        {
                            case "progress":
                                progress?.Report(new SidecarProgress(
                                    Percent: root.TryGetProperty("percent", out var p) && p.ValueKind == JsonValueKind.Number ? p.GetDouble() : 0,
                                    Stage: root.TryGetProperty("stage", out var s) ? s.GetString() ?? "" : "",
                                    EtaSeconds: root.TryGetProperty("eta_seconds", out var e) && e.ValueKind == JsonValueKind.Number ? e.GetInt32() : null));
                                break;

                            case "log":
                                log?.Report(new SidecarLog(
                                    Level: root.TryGetProperty("level", out var lv) ? lv.GetString() ?? "info" : "info",
                                    Message: root.TryGetProperty("message", out var m) ? m.GetString() ?? "" : ""));
                                break;

                            case "complete":
                                finalOutput = root.TryGetProperty("output", out var o) ? o.GetString() : null;
                                finalSize = root.TryGetProperty("size_bytes", out var sb) && sb.ValueKind == JsonValueKind.Number ? sb.GetInt64() : null;
                                break;

                            case "error":
                                errorCode = root.TryGetProperty("code", out var c) ? c.GetString() : "unknown";
                                errorMessage = root.TryGetProperty("message", out var em) ? em.GetString() : null;
                                break;
                        }
                    }
                    catch (JsonException)
                    {
                        log?.Report(new SidecarLog("debug", line));
                    }
                }
            }
            catch (OperationCanceledException) { }
        }, ct);

        var stderrTask = Task.Run(async () =>
        {
            try
            {
                var stderr = await process.StandardError.ReadToEndAsync().ConfigureAwait(false);
                if (!string.IsNullOrWhiteSpace(stderr))
                {
                    foreach (var ln in stderr.Split('\n'))
                        if (!string.IsNullOrWhiteSpace(ln))
                            log?.Report(new SidecarLog("stderr", ln.TrimEnd('\r')));
                }
            }
            catch { }
        }, ct);

        try
        {
            await process.WaitForExitAsync(lct).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            stuckByWatchdog = watchdogCts.IsCancellationRequested && !ct.IsCancellationRequested;
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }

            if (stuckByWatchdog)
            {
                log?.Report(new SidecarLog(
                    "warn",
                    $"{toolName} emitted no output for " +
                    $"{(int)effectiveTimeout.TotalSeconds}s — killed as stuck"));
                return new SidecarResult(
                    Success: false,
                    OutputPath: null,
                    SizeBytes: null,
                    ErrorCode: "stuck_sidecar",
                    ErrorMessage:
                        $"{toolName} produced no output for " +
                        $"{(int)effectiveTimeout.TotalSeconds}s and was terminated.",
                    ExitCode: -1);
            }

            return new SidecarResult(false, null, null, "cancelled", "Cancelled by user.", -1);
        }

        await Task.WhenAll(stdoutTask, stderrTask).ConfigureAwait(false);

        var success = process.ExitCode == 0 && errorCode is null;
        return new SidecarResult(
            Success: success,
            OutputPath: finalOutput,
            SizeBytes: finalSize,
            ErrorCode: success ? null : (errorCode ?? "exit_nonzero"),
            ErrorMessage: success ? null : (errorMessage ?? $"Sidecar exited with code {process.ExitCode}"),
            ExitCode: process.ExitCode);
    }
}
