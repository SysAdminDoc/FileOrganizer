using System.Text.Json;

namespace FileOrganizer.UI.Services;

public sealed record CapabilityHealthRow(
    string Workflow,
    string Capability,
    string Dependency,
    string DetectedVersion,
    string Scope,
    bool OnlineRequired,
    bool Required,
    string Status,
    string Detail,
    string Remediation)
{
    public string OnlineText => OnlineRequired ? "Online" : "Local";
    public string RequiredText => Required ? "Required" : "Optional";
    public string DisplayStatus => Status.Replace('_', ' ').ToUpperInvariant();
}

public sealed record CapabilityHealthSnapshot(IReadOnlyList<CapabilityHealthRow> Rows)
{
    public int Available => Rows.Count(row => row.Status == "available");
    public int Unavailable => Rows.Count(row => row.Status == "unavailable");
    public int NotChecked => Rows.Count(row => row.Status == "not_checked");
}

public interface ICapabilityHealthService
{
    event EventHandler<CapabilityHealthSnapshot>? Changed;
    CapabilityHealthSnapshot Snapshot { get; }
    void UpdateFromProtocol(JsonElement payload);
}

public sealed class CapabilityHealthService : ICapabilityHealthService
{
    private const int MaxRows = 256;
    private const int MaxFieldCharacters = 2048;
    private static readonly HashSet<string> ValidStatuses = new(StringComparer.Ordinal)
    {
        "available", "unavailable", "not_checked",
    };

    private readonly object _sync = new();
    private readonly Dictionary<(string Workflow, string Capability), CapabilityHealthRow> _rows = [];

    public event EventHandler<CapabilityHealthSnapshot>? Changed;

    public CapabilityHealthSnapshot Snapshot
    {
        get
        {
            lock (_sync)
                return CreateSnapshot();
        }
    }

    public void UpdateFromProtocol(JsonElement payload)
    {
        JsonElement matrix;
        JsonElement single = default;
        if (payload.TryGetProperty("capability_health", out single)
            && single.ValueKind == JsonValueKind.Object)
        {
            matrix = default;
        }
        else if (payload.TryGetProperty("capability_matrix", out matrix))
        {
        }
        else if (payload.TryGetProperty("capabilities", out var capabilities)
            && capabilities.ValueKind == JsonValueKind.Object
            && capabilities.TryGetProperty("capability_matrix", out matrix))
        {
        }
        else
        {
            return;
        }

        var parsed = new List<CapabilityHealthRow>();
        if (single.ValueKind == JsonValueKind.Object)
        {
            if (TryParseRow(single, out var row))
                parsed.Add(row);
        }
        else
        {
            if (matrix.ValueKind != JsonValueKind.Array)
                return;
            foreach (var item in matrix.EnumerateArray().Take(MaxRows))
            {
                if (TryParseRow(item, out var row))
                    parsed.Add(row);
            }
        }
        if (parsed.Count == 0)
            return;

        CapabilityHealthSnapshot snapshot;
        lock (_sync)
        {
            foreach (var row in parsed)
            {
                var key = (row.Workflow, row.Capability);
                if (_rows.ContainsKey(key) || _rows.Count < MaxRows)
                    _rows[key] = row;
            }
            snapshot = CreateSnapshot();
        }
        Changed?.Invoke(this, snapshot);
    }

    private CapabilityHealthSnapshot CreateSnapshot() => new(
        _rows.Values
            .OrderBy(row => row.Workflow, StringComparer.Ordinal)
            .ThenBy(row => row.Capability, StringComparer.Ordinal)
            .ToList());

    private static bool TryParseRow(JsonElement item, out CapabilityHealthRow row)
    {
        row = null!;
        if (item.ValueKind != JsonValueKind.Object
            || !item.TryGetProperty("schema_version", out var schemaVersion)
            || schemaVersion.ValueKind != JsonValueKind.Number
            || !schemaVersion.TryGetInt32(out var schema)
            || schema != 1
            || !TryString(item, "workflow", out var workflow)
            || !TryString(item, "capability", out var capability)
            || !TryString(item, "dependency", out var dependency)
            || !TryString(item, "detected_version", out var detectedVersion)
            || !TryString(item, "scope", out var scope)
            || !TryString(item, "status", out var status)
            || !ValidStatuses.Contains(status)
            || !TryString(item, "detail", out var detail)
            || !TryString(item, "remediation", out var remediation)
            || !TryBoolean(item, "online_required", out var onlineRequired)
            || !TryBoolean(item, "required", out var required))
        {
            return false;
        }

        row = new CapabilityHealthRow(
            workflow, capability, dependency, detectedVersion, scope,
            onlineRequired, required, status, detail, remediation);
        return true;
    }

    private static bool TryString(JsonElement root, string name, out string value)
    {
        value = string.Empty;
        if (!root.TryGetProperty(name, out var property)
            || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }
        value = (property.GetString() ?? string.Empty).Trim();
        if (value.Length > MaxFieldCharacters)
            value = value[..MaxFieldCharacters];
        return value.Length > 0;
    }

    private static bool TryBoolean(JsonElement root, string name, out bool value)
    {
        value = false;
        if (!root.TryGetProperty(name, out var property)
            || property.ValueKind is not (JsonValueKind.True or JsonValueKind.False))
        {
            return false;
        }
        value = property.GetBoolean();
        return true;
    }
}
