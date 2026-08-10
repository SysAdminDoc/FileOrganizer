using System.Text.Json;
using System.Text.Json.Serialization;

namespace FileOrganizer.UI.Services;

public sealed record WatchTaskEntry(
    [property: JsonPropertyName("src")] string Source,
    [property: JsonPropertyName("dest")] string Destination,
    [property: JsonPropertyName("copy")] bool Copy);

public sealed record WatchTaskState(
    [property: JsonPropertyName("supported")] bool Supported,
    [property: JsonPropertyName("configured")] bool Configured,
    [property: JsonPropertyName("enabled")] bool Enabled,
    [property: JsonPropertyName("registered")] bool Registered,
    [property: JsonPropertyName("watch_count")] int WatchCount,
    [property: JsonPropertyName("debounce_seconds")] int DebounceSeconds,
    [property: JsonPropertyName("task_name")] string TaskName,
    [property: JsonPropertyName("log_path")] string LogPath,
    [property: JsonPropertyName("message")] string? Message,
    [property: JsonPropertyName("log")] string? Log,
    [property: JsonPropertyName("error")] string? Error);

public static class WatchTaskProtocol
{
    public const int MinimumDebounceSeconds = 2;
    public const int MaximumDebounceSeconds = 120;

    public static int ClampDebounce(double value) => Math.Clamp(
        (int)Math.Round(value, MidpointRounding.AwayFromZero),
        MinimumDebounceSeconds,
        MaximumDebounceSeconds);

    public static bool TryParseSavedWatches(
        string? raw,
        out IReadOnlyList<WatchTaskEntry> watches,
        out string error)
    {
        var parsed = new List<WatchTaskEntry>();
        var seenSources = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        error = string.Empty;
        foreach (var line in (raw ?? string.Empty).Split(
                     '\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            var parts = line.Split("||", StringSplitOptions.None);
            if (parts.Length < 2
                || !WatchPathValidator.TryValidate(
                    parts[0], parts[1], out var source, out var destination, out error))
            {
                watches = [];
                error = string.IsNullOrWhiteSpace(error)
                    ? "A saved watch entry is malformed."
                    : error;
                return false;
            }
            if (!seenSources.Add(source))
            {
                watches = [];
                error = "A source folder is configured more than once.";
                return false;
            }
            parsed.Add(new WatchTaskEntry(
                source,
                destination,
                parts.Length > 2 && parts[2] == "1"));
        }
        watches = parsed;
        error = string.Empty;
        return true;
    }

    public static string SerializeWatches(IReadOnlyList<WatchTaskEntry> watches) =>
        JsonSerializer.Serialize(watches);

    public static bool TryParseState(
        string? output,
        out WatchTaskState? state,
        out string error)
    {
        state = null;
        error = string.Empty;
        try
        {
            var line = (output ?? string.Empty)
                .Split('\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .LastOrDefault(value => value.StartsWith('{'));
            if (line is null)
            {
                error = "Watch task returned no status.";
                return false;
            }
            using var document = JsonDocument.Parse(line);
            if (document.RootElement.TryGetProperty("error", out var errorElement)
                && errorElement.ValueKind == JsonValueKind.String
                && !string.IsNullOrWhiteSpace(errorElement.GetString()))
            {
                error = errorElement.GetString()!;
                return false;
            }
            state = JsonSerializer.Deserialize<WatchTaskState>(line);
            if (state is null)
            {
                error = "Watch task returned an empty status.";
                return false;
            }
            return true;
        }
        catch (Exception exception) when (
            exception is JsonException or InvalidOperationException)
        {
            error = $"Watch task returned invalid status: {exception.Message}";
            return false;
        }
    }
}
