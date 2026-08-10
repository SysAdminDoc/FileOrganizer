using System.Diagnostics;
using System.Text;
using System.Text.Json;
using Microsoft.UI.Dispatching;

namespace FileOrganizer.UI.Services;

public sealed record PythonResult(
    bool Success,
    string Stdout,
    string Stderr,
    int ExitCode,
    string? ErrorMessage);

public interface IPythonRunner
{
    /// <summary>
    /// Resolves the FileOrganizer repo root by walking up from the executable
    /// until a directory containing organize_run.py is found.
    /// </summary>
    string? LocateRepoRoot();

    /// <summary>
    /// Run a Python script in the FileOrganizer repo root and capture stdout/stderr
    /// as plain text. For sidecars that emit NDJSON, use RunScriptNdjsonAsync.
    /// </summary>
    Task<PythonResult> RunScriptAsync(
        string scriptName,
        IEnumerable<string> args,
        IProgress<string>? lineProgress = null,
        CancellationToken ct = default);

    /// <summary>
    /// Run a Python script that emits NDJSON events on stdout. The callback
    /// receives the event name and the validated JsonElement so the caller can
    /// decode any custom fields. Invalid, oversized, or unknown records are
    /// isolated as bounded protocol diagnostic log events.
    /// </summary>
    Task<PythonResult> RunScriptNdjsonAsync(
        string scriptName,
        IEnumerable<string> args,
        Action<string, JsonElement> onEvent,
        CancellationToken ct = default,
        IReadOnlyDictionary<string, string>? environmentVariables = null);
}

public sealed class PythonRunner : IPythonRunner
{
    private readonly RunLifecycleGate _runGate = new();

    public string? LocateRepoRoot()
    {
        var dir = new DirectoryInfo(AppContext.BaseDirectory);
        while (dir is not null)
        {
            if (File.Exists(Path.Combine(dir.FullName, "organize_run.py")))
                return dir.FullName;
            dir = dir.Parent;
        }
        return null;
    }

    public async Task<PythonResult> RunScriptAsync(
        string scriptName,
        IEnumerable<string> args,
        IProgress<string>? lineProgress = null,
        CancellationToken ct = default)
    {
        IDisposable lease;
        try
        {
            lease = await _runGate.EnterAsync(scriptName, ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            return new PythonResult(false, "", "", -1, "Cancelled by user.");
        }

        using (lease)
        {
            return await RunScriptCoreAsync(
                scriptName, args, lineProgress, ct).ConfigureAwait(false);
        }
    }

    private async Task<PythonResult> RunScriptCoreAsync(
        string scriptName,
        IEnumerable<string> args,
        IProgress<string>? lineProgress = null,
        CancellationToken ct = default)
    {
        var repoRoot = LocateRepoRoot();
        if (repoRoot is null)
        {
            return new PythonResult(
                Success: false,
                Stdout: "",
                Stderr: "",
                ExitCode: -1,
                ErrorMessage:
                    "Could not locate FileOrganizer repo root. Expected to find " +
                    "organize_run.py in a parent directory of the running executable.");
        }

        var scriptPath = Path.Combine(repoRoot, scriptName);
        if (!File.Exists(scriptPath))
        {
            return new PythonResult(
                Success: false,
                Stdout: "",
                Stderr: "",
                ExitCode: -1,
                ErrorMessage: $"Script not found: {scriptPath}");
        }

        var psi = new ProcessStartInfo
        {
            FileName = ResolvePythonExecutable(repoRoot),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = repoRoot,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        psi.ArgumentList.Add("-u");
        psi.ArgumentList.Add(scriptPath);
        foreach (var a in args) psi.ArgumentList.Add(a);

        // Force UTF-8 stdout in the child process so Unicode filenames don't crash.
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";

        using var process = new Process { StartInfo = psi };

        var stdout = new StringBuilder();
        var stderr = new StringBuilder();

        try
        {
            process.Start();
        }
        catch (Exception ex)
        {
            return new PythonResult(false, "", "", -1,
                $"Failed to start Python: {ex.Message}. " +
                $"Ensure Python is on PATH or set FILEORGANIZER_PYTHON.");
        }

        var stdoutTask = Task.Run(async () =>
        {
            while (!process.StandardOutput.EndOfStream)
            {
                ct.ThrowIfCancellationRequested();
                var line = await process.StandardOutput.ReadLineAsync(ct).ConfigureAwait(false);
                if (line is null) break;
                ct.ThrowIfCancellationRequested();
                stdout.AppendLine(line);
                lineProgress?.Report(line);
            }
        }, ct);

        var stderrTask = Task.Run(async () =>
        {
            while (!process.StandardError.EndOfStream)
            {
                ct.ThrowIfCancellationRequested();
                var line = await process.StandardError.ReadLineAsync(ct).ConfigureAwait(false);
                if (line is null) break;
                stderr.AppendLine(line);
            }
        }, ct);

        try
        {
            await process.WaitForExitAsync(ct).ConfigureAwait(false);
            await Task.WhenAll(stdoutTask, stderrTask).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            try { await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false); }
            catch { }
            await ObserveReaderTasksAsync(stdoutTask, stderrTask).ConfigureAwait(false);
            return new PythonResult(false, stdout.ToString(), stderr.ToString(), -1, "Cancelled by user.");
        }

        var success = process.ExitCode == 0;
        return new PythonResult(
            Success: success,
            Stdout: stdout.ToString(),
            Stderr: stderr.ToString(),
            ExitCode: process.ExitCode,
            ErrorMessage: success ? null : $"Python exited with code {process.ExitCode}");
    }

    public async Task<PythonResult> RunScriptNdjsonAsync(
        string scriptName,
        IEnumerable<string> args,
        Action<string, JsonElement> onEvent,
        CancellationToken ct = default,
        IReadOnlyDictionary<string, string>? environmentVariables = null)
    {
        IDisposable lease;
        try
        {
            lease = await _runGate.EnterAsync(scriptName, ct).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            var cancelled = SidecarProtocolSession.CreateTerminalError(
                "cancelled",
                "Cancelled by user.");
            onEvent(cancelled.Name, cancelled.Payload);
            return new PythonResult(false, "", "", -1, "Cancelled by user.");
        }

        using (lease)
        {
            return await RunScriptNdjsonCoreAsync(
                scriptName,
                args,
                onEvent,
                ct,
                environmentVariables).ConfigureAwait(false);
        }
    }

    private async Task<PythonResult> RunScriptNdjsonCoreAsync(
        string scriptName,
        IEnumerable<string> args,
        Action<string, JsonElement> onEvent,
        CancellationToken ct = default,
        IReadOnlyDictionary<string, string>? environmentVariables = null)
    {
        var repoRoot = LocateRepoRoot();
        if (repoRoot is null)
        {
            return new PythonResult(false, "", "", -1,
                "Could not locate FileOrganizer repo root.");
        }

        var scriptPath = Path.Combine(repoRoot, scriptName);
        if (!File.Exists(scriptPath))
        {
            return new PythonResult(false, "", "", -1,
                $"Script not found: {scriptPath}");
        }

        var psi = new ProcessStartInfo
        {
            FileName = ResolvePythonExecutable(repoRoot),
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            CreateNoWindow = true,
            WindowStyle = ProcessWindowStyle.Hidden,
            WorkingDirectory = repoRoot,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        psi.ArgumentList.Add("-u");
        psi.ArgumentList.Add(scriptPath);
        foreach (var a in args) psi.ArgumentList.Add(a);
        if (environmentVariables is not null)
        {
            foreach (var pair in environmentVariables)
                psi.EnvironmentVariables[pair.Key] = pair.Value;
        }
        psi.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8";
        psi.EnvironmentVariables["PYTHONUTF8"] = "1";

        using var process = new Process { StartInfo = psi };
        var stderr = new StringBuilder();
        var dispatcher = DispatcherQueue.GetForCurrentThread();
        var protocol = new SidecarProtocolSession(scriptName);

        async Task DispatchEventAsync(
            string eventName,
            JsonElement payload,
            CancellationToken dispatchToken)
        {
            dispatchToken.ThrowIfCancellationRequested();
            if (dispatcher is null)
            {
                onEvent(eventName, payload);
                return;
            }

            var completion = new TaskCompletionSource<bool>(
                TaskCreationOptions.RunContinuationsAsynchronously);
            if (!dispatcher.TryEnqueue(() =>
            {
                if (dispatchToken.IsCancellationRequested)
                {
                    completion.TrySetCanceled(dispatchToken);
                    return;
                }

                try
                {
                    onEvent(eventName, payload);
                    completion.TrySetResult(true);
                }
                catch (Exception ex)
                {
                    completion.TrySetException(ex);
                }
            }))
            {
                throw new InvalidOperationException("The WinUI dispatcher is unavailable.");
            }

            await completion.Task.WaitAsync(dispatchToken).ConfigureAwait(false);
        }

        try
        {
            process.Start();
        }
        catch (Exception ex)
        {
            return new PythonResult(false, "", "", -1,
                $"Failed to start Python: {ex.Message}");
        }

        var stdoutTask = Task.Run(async () =>
        {
            while (!process.StandardOutput.EndOfStream)
            {
                ct.ThrowIfCancellationRequested();
                var line = await process.StandardOutput.ReadLineAsync(ct).ConfigureAwait(false);
                if (line is null) break;
                if (string.IsNullOrWhiteSpace(line)) continue;
                var accepted = protocol.AcceptLine(line);
                await DispatchEventAsync(
                    accepted.Name,
                    accepted.Payload,
                    ct).ConfigureAwait(false);
            }
        }, ct);

        var stderrTask = Task.Run(async () =>
        {
            while (!process.StandardError.EndOfStream)
            {
                ct.ThrowIfCancellationRequested();
                var line = await process.StandardError.ReadLineAsync(ct).ConfigureAwait(false);
                if (line is null) break;
                stderr.AppendLine(line);
            }
        }, ct);

        try
        {
            await process.WaitForExitAsync(ct).ConfigureAwait(false);
            await Task.WhenAll(stdoutTask, stderrTask).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            try { await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false); }
            catch { }
            await ObserveReaderTasksAsync(stdoutTask, stderrTask).ConfigureAwait(false);
            var cancelled = SidecarProtocolSession.CreateTerminalError(
                "cancelled",
                "Cancelled by user.");
            await DispatchEventAsync(
                cancelled.Name,
                cancelled.Payload,
                CancellationToken.None).ConfigureAwait(false);
            return new PythonResult(false, "", stderr.ToString(), -1, "Cancelled by user.");
        }

        var success = process.ExitCode == 0 && protocol.IsComplete;
        string? errorMessage = null;
        if (process.ExitCode != 0)
            errorMessage = $"Python exited with code {process.ExitCode}";
        else if (!protocol.HandshakeReceived)
            errorMessage = "Sidecar did not emit a protocol handshake.";
        else if (!protocol.TerminalReceived)
            errorMessage = "Sidecar exited without a terminal protocol event.";
        return new PythonResult(
            Success: success,
            Stdout: "",
            Stderr: stderr.ToString(),
            ExitCode: process.ExitCode,
            ErrorMessage: errorMessage);
    }

    private static async Task ObserveReaderTasksAsync(params Task[] tasks)
    {
        foreach (var task in tasks)
        {
            try
            {
                await task.ConfigureAwait(false);
            }
            catch (Exception ex) when (
                ex is OperationCanceledException
                or IOException
                or ObjectDisposedException
                or InvalidOperationException)
            {
                // Expected while a cancelled child process closes redirected pipes.
            }
        }
    }

    private static string ResolvePythonExecutable(string repoRoot)
    {
        // Allow override via env var.
        var env = Environment.GetEnvironmentVariable("FILEORGANIZER_PYTHON");
        if (!string.IsNullOrWhiteSpace(env) && File.Exists(env))
            return env;

        // Project-local venv (Windows layout).
        var venvWin = Path.Combine(repoRoot, ".venv", "Scripts", "python.exe");
        if (File.Exists(venvWin)) return venvWin;

        // Project-local venv (POSIX layout, in case repo is mounted).
        var venvPosix = Path.Combine(repoRoot, ".venv", "bin", "python");
        if (File.Exists(venvPosix)) return venvPosix;

        // Windows launcher (handles multiple installed versions).
        var py = Environment.GetEnvironmentVariable("WINDIR") is { } windir
            ? Path.Combine(windir, "py.exe")
            : null;
        if (py is not null && File.Exists(py)) return py;

        // Fall back to PATH.
        return "python";
    }
}
