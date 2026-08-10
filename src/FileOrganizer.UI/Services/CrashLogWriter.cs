using System.Text;
using System.Text.RegularExpressions;

namespace FileOrganizer.UI.Services;

public sealed class CrashLogWriter
{
    public const int DefaultMaxFileBytes = 512 * 1024;
    public const int DefaultMaxRecords = 100;
    public const int DefaultArchiveCount = 2;

    private static readonly object WriteLock = new();
    private static readonly UTF8Encoding Utf8 = new(encoderShouldEmitUTF8Identifier: false);
    private static readonly Regex LabeledSecretPattern = new(
        """(?ix)\b(api[_-]?key|access[_-]?key|token|secret|password|credential)\s*[:=]\s*(?:"[^"]*"|'[^']*'|[^\s,;]+)""",
        RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(100));
    private static readonly Regex SecretArgumentPattern = new(
        """(?ix)(--(?:api[_-]?key|access[_-]?key|token|secret|password|credential))(?:=|\s+)(?:"[^"]*"|'[^']*'|[^\s]+)""",
        RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(100));
    private static readonly Regex BearerPattern = new(
        @"(?i)\b(Bearer\s+)[A-Za-z0-9._~+/=-]+",
        RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(100));
    private static readonly Regex RecognizableTokenPattern = new(
        @"(?i)\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{12,})\b",
        RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(100));
    private static readonly Regex QuotedWindowsPathPattern = new(
        """(?i)(?:"(?:[A-Z]:\\|\\\\)[^"\r\n]+"|'(?:[A-Z]:\\|\\\\)[^'\r\n]+')""",
        RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(100));
    private static readonly Regex WindowsPathPattern = new(
        """(?i)(?:[A-Z]:\\|\\\\[^\\\s]+\\[^\\\s]+\\)(?:[^\\/:*?"<>|\s]+\\)*([^\\/:*?"<>|\s]+)""",
        RegexOptions.CultureInvariant,
        TimeSpan.FromMilliseconds(100));

    private readonly string _logPath;
    private readonly int _maxFileBytes;
    private readonly int _maxRecords;
    private readonly int _archiveCount;
    private readonly IReadOnlyList<string> _knownSecretValues;

    public CrashLogWriter(
        string logPath,
        int maxFileBytes = DefaultMaxFileBytes,
        int maxRecords = DefaultMaxRecords,
        int archiveCount = DefaultArchiveCount,
        IEnumerable<string>? knownSecretValues = null)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(logPath);
        if (maxFileBytes < 256)
            throw new ArgumentOutOfRangeException(nameof(maxFileBytes));
        if (maxRecords < 1)
            throw new ArgumentOutOfRangeException(nameof(maxRecords));
        if (archiveCount < 0)
            throw new ArgumentOutOfRangeException(nameof(archiveCount));

        _logPath = Path.GetFullPath(logPath);
        _maxFileBytes = maxFileBytes;
        _maxRecords = maxRecords;
        _archiveCount = archiveCount;
        _knownSecretValues = (knownSecretValues ?? ReadSecretEnvironmentValues())
            .Where(value => !string.IsNullOrWhiteSpace(value) && value.Length >= 4)
            .Distinct(StringComparer.Ordinal)
            .OrderByDescending(value => value.Length)
            .ToArray();
    }

    public void Write(Exception? exception)
    {
        var exceptionType = exception?.GetType().FullName ?? "UnknownException";
        var details = exception?.ToString() ?? "No exception details were supplied.";
        var record = $"[{DateTimeOffset.UtcNow:O}] {exceptionType}\n{Redact(details)}\n---\n";
        record = BoundRecord(record);

        lock (WriteLock)
        {
            var directory = Path.GetDirectoryName(_logPath);
            if (!string.IsNullOrEmpty(directory))
                Directory.CreateDirectory(directory);

            NormalizeExistingLogs();
            var recordBytes = Utf8.GetByteCount(record);
            if (ShouldRotate(recordBytes))
                Rotate();

            File.AppendAllText(_logPath, record, Utf8);
        }
    }

    private bool ShouldRotate(int incomingBytes)
    {
        if (!File.Exists(_logPath))
            return false;

        var info = new FileInfo(_logPath);
        if (info.Length + incomingBytes > _maxFileBytes)
            return true;

        var recordCount = File.ReadLines(_logPath).Count(line => line == "---");
        return recordCount >= _maxRecords;
    }

    private void NormalizeExistingLogs()
    {
        NormalizeExistingLog(_logPath);
        for (var index = 1; index <= _archiveCount; index++)
            NormalizeExistingLog(ArchivePath(index));

        var directory = Path.GetDirectoryName(_logPath)!;
        var fileName = Path.GetFileName(_logPath);
        foreach (var candidate in Directory.EnumerateFiles(directory, $"{fileName}.*"))
        {
            var candidateName = Path.GetFileName(candidate);
            if (!candidateName.StartsWith($"{fileName}.", StringComparison.OrdinalIgnoreCase))
                continue;

            var suffix = candidateName[(fileName.Length + 1)..];
            if (int.TryParse(suffix, out var index) && index > _archiveCount)
                File.Delete(candidate);
        }
    }

    private void NormalizeExistingLog(string path)
    {
        if (!File.Exists(path))
            return;

        var content = ReadBoundedTail(path);
        content = Redact(content).ReplaceLineEndings("\n");
        var records = content.Split("\n---\n", StringSplitOptions.RemoveEmptyEntries);
        if (records.Length > _maxRecords)
            records = records[^_maxRecords..];

        content = records.Length == 0
            ? string.Empty
            : string.Join("\n---\n", records) + "\n---\n";
        content = BoundExistingContent(content);

        var temporaryPath = $"{path}.tmp-{Guid.NewGuid():N}";
        try
        {
            File.WriteAllText(temporaryPath, content, Utf8);
            File.Move(temporaryPath, path, overwrite: true);
        }
        finally
        {
            File.Delete(temporaryPath);
        }
    }

    private string ReadBoundedTail(string path)
    {
        using var stream = new FileStream(
            path,
            FileMode.Open,
            FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete);
        var bytesToRead = Math.Min(stream.Length, _maxFileBytes * 4L);
        stream.Seek(-bytesToRead, SeekOrigin.End);
        using var reader = new StreamReader(stream, Utf8, detectEncodingFromByteOrderMarks: true);
        return reader.ReadToEnd();
    }

    private string BoundExistingContent(string content)
    {
        if (Utf8.GetByteCount(content) <= _maxFileBytes)
            return content;

        const string marker = "[earlier crash log content discarded]\n";
        var budget = _maxFileBytes - Utf8.GetByteCount(marker);
        var low = 0;
        var high = content.Length;
        while (low < high)
        {
            var middle = low + (high - low) / 2;
            if (Utf8.GetByteCount(content.AsSpan(middle)) <= budget)
                high = middle;
            else
                low = middle + 1;
        }

        if (low < content.Length && char.IsLowSurrogate(content[low]))
            low++;
        return marker + content[low..];
    }

    private void Rotate()
    {
        if (_archiveCount == 0)
        {
            File.Delete(_logPath);
            return;
        }

        var oldestArchive = ArchivePath(_archiveCount);
        File.Delete(oldestArchive);

        for (var index = _archiveCount - 1; index >= 1; index--)
        {
            var source = ArchivePath(index);
            if (File.Exists(source))
                File.Move(source, ArchivePath(index + 1), overwrite: true);
        }

        // A same-volume rename makes the handoff of the complete current log
        // atomic; a crash cannot leave a partially copied archive.
        if (File.Exists(_logPath))
            File.Move(_logPath, ArchivePath(1), overwrite: true);
    }

    private string ArchivePath(int index) => $"{_logPath}.{index}";

    private string Redact(string value)
    {
        var redacted = value;
        foreach (var secret in _knownSecretValues)
        {
            redacted = Regex.Replace(
                redacted,
                Regex.Escape(secret),
                "[REDACTED]",
                RegexOptions.IgnoreCase | RegexOptions.CultureInvariant,
                TimeSpan.FromMilliseconds(100));
        }

        redacted = SecretArgumentPattern.Replace(redacted, "$1=[REDACTED]");
        redacted = LabeledSecretPattern.Replace(redacted, "$1=[REDACTED]");
        redacted = BearerPattern.Replace(redacted, "$1[REDACTED]");
        redacted = RecognizableTokenPattern.Replace(redacted, "[REDACTED]");
        redacted = ReplaceKnownFolder(redacted, Environment.SpecialFolder.LocalApplicationData, "%LOCALAPPDATA%");
        redacted = ReplaceKnownFolder(redacted, Environment.SpecialFolder.ApplicationData, "%APPDATA%");
        redacted = ReplaceKnownFolder(redacted, Environment.SpecialFolder.UserProfile, "%USERPROFILE%");
        redacted = ReplaceText(redacted, Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar), "%TEMP%");
        redacted = QuotedWindowsPathPattern.Replace(redacted, "[PATH]");
        return WindowsPathPattern.Replace(redacted, match => $"[PATH]\\{match.Groups[1].Value}");
    }

    private string BoundRecord(string record)
    {
        if (Utf8.GetByteCount(record) <= _maxFileBytes)
            return record;

        const string marker = "\n[record truncated]\n---\n";
        var budget = _maxFileBytes - Utf8.GetByteCount(marker);
        var low = 0;
        var high = record.Length;
        while (low < high)
        {
            var middle = low + (high - low + 1) / 2;
            if (Utf8.GetByteCount(record.AsSpan(0, middle)) <= budget)
                low = middle;
            else
                high = middle - 1;
        }

        return record[..low] + marker;
    }

    private static string ReplaceKnownFolder(
        string value,
        Environment.SpecialFolder folder,
        string replacement) =>
        ReplaceText(value, Environment.GetFolderPath(folder), replacement);

    private static string ReplaceText(string value, string target, string replacement)
    {
        if (string.IsNullOrWhiteSpace(target))
            return value;

        return Regex.Replace(
            value,
            Regex.Escape(target),
            replacement.Replace("$", "$$"),
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant,
            TimeSpan.FromMilliseconds(100));
    }

    private static IEnumerable<string> ReadSecretEnvironmentValues()
    {
        foreach (System.Collections.DictionaryEntry entry in Environment.GetEnvironmentVariables())
        {
            var name = entry.Key?.ToString() ?? string.Empty;
            if (name.Contains("KEY", StringComparison.OrdinalIgnoreCase)
                || name.Contains("TOKEN", StringComparison.OrdinalIgnoreCase)
                || name.Contains("SECRET", StringComparison.OrdinalIgnoreCase)
                || name.Contains("PASSWORD", StringComparison.OrdinalIgnoreCase)
                || name.Contains("CREDENTIAL", StringComparison.OrdinalIgnoreCase))
            {
                yield return entry.Value?.ToString() ?? string.Empty;
            }
        }
    }
}
