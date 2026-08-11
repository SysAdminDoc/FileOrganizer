using System.Text.Json;
using System.Text.Json.Serialization;

namespace FileOrganizer.UI.Services;

public sealed record ScheduleTaskEntry(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("profile_name")] string ProfileName,
    [property: JsonPropertyName("frequency")] string Frequency,
    [property: JsonPropertyName("time")] string Time,
    [property: JsonPropertyName("enabled")] bool Enabled,
    [property: JsonPropertyName("auto_apply")] bool AutoApply,
    [property: JsonPropertyName("last_status")] string? LastStatus,
    [property: JsonPropertyName("last_error")] string? LastError,
    [property: JsonPropertyName("last_run")] string? LastRun,
    [property: JsonPropertyName("log_path")] string LogPath);

public sealed record ScheduleTaskState(
    [property: JsonPropertyName("supported")] bool Supported,
    [property: JsonPropertyName("profiles")] IReadOnlyList<string> Profiles,
    [property: JsonPropertyName("schedules")] IReadOnlyList<ScheduleTaskEntry> Schedules,
    [property: JsonPropertyName("message")] string? Message,
    [property: JsonPropertyName("log")] string? Log,
    [property: JsonPropertyName("error")] string? Error);

public static class ScheduleTaskProtocol
{
    public static bool TryParseState(
        string? output,
        out ScheduleTaskState? state,
        out string error)
    {
        state = null;
        error = string.Empty;
        if (string.IsNullOrWhiteSpace(output))
        {
            error = "Schedule helper returned no status.";
            return false;
        }
        try
        {
            var line = output.Split(
                '\n', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)[^1];
            state = JsonSerializer.Deserialize<ScheduleTaskState>(line);
            if (state is null)
            {
                error = "Schedule helper returned an empty status object.";
                return false;
            }
            return true;
        }
        catch (Exception exception) when (
            exception is JsonException or IndexOutOfRangeException)
        {
            error = $"Could not read schedule status: {exception.Message}";
            return false;
        }
    }

    public static string Describe(ScheduleTaskEntry entry)
    {
        var cadence = entry.Frequency == "on_logon"
            ? "at logon"
            : $"{entry.Frequency} at {entry.Time}";
        var mode = entry.AutoApply ? "auto-apply" : "preview only";
        var status = entry.LastStatus ?? (entry.Enabled ? "enabled" : "disabled");
        return $"{entry.Name} · {entry.ProfileName} · {cadence} · {mode} · {status}";
    }
}
