using System.Diagnostics;
using System.Text;

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
    /// as plain text. For sidecars that emit NDJSON, use ISidecarRunner instead.
    /// </summary>
    Task<PythonResult> RunScriptAsync(
        string scriptName,
        IEnumerable<string> args,
        IProgress<string>? lineProgress = null,
        CancellationToken ct = default);
}

public sealed class PythonRunner : IPythonRunner
{
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
        }
        catch (OperationCanceledException)
        {
            try { if (!process.HasExited) process.Kill(entireProcessTree: true); } catch { }
            return new PythonResult(false, stdout.ToString(), stderr.ToString(), -1, "Cancelled by user.");
        }

        await Task.WhenAll(stdoutTask, stderrTask).ConfigureAwait(false);

        var success = process.ExitCode == 0;
        return new PythonResult(
            Success: success,
            Stdout: stdout.ToString(),
            Stderr: stderr.ToString(),
            ExitCode: process.ExitCode,
            ErrorMessage: success ? null : $"Python exited with code {process.ExitCode}");
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
