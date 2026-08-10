using System.Text;
using System.Text.Json;

namespace FileOrganizer.UI.Services;

public sealed record SidecarProtocolEvent(
    string Name,
    JsonElement Payload,
    bool IsDiagnostic = false);

/// <summary>
/// Stateful validator for FileOrganizer's versioned NDJSON sidecar stream.
/// Invalid records become bounded diagnostic log events and never escape as
/// parser exceptions or reach page-specific event handlers as trusted data.
/// </summary>
public sealed class SidecarProtocolSession
{
    public const string SupportedVersion = "1.0";
    public const int MaxRecordBytes = 1_048_576;

    private static readonly HashSet<string> AllowedEvents = new(StringComparer.Ordinal)
    {
        "handshake", "start", "progress", "item", "group", "summary",
        "file", "comic", "plan", "log", "complete", "error", "watching",
        "detected", "heartbeat",
        "review", "review_exported",
    };

    private readonly string _sidecarName;
    private int _lastSequence = -1;

    public SidecarProtocolSession(string sidecarName)
    {
        _sidecarName = sidecarName;
    }

    public bool HandshakeReceived { get; private set; }
    public bool TerminalReceived { get; private set; }
    public int ViolationCount { get; private set; }
    public bool IsComplete => HandshakeReceived && TerminalReceived;

    public SidecarProtocolEvent AcceptLine(string line)
    {
        if (Encoding.UTF8.GetByteCount(line) > MaxRecordBytes)
            return Diagnostic("record_too_large", "Sidecar record exceeded the byte limit.");

        try
        {
            using var document = JsonDocument.Parse(line, new JsonDocumentOptions
            {
                MaxDepth = 16,
                CommentHandling = JsonCommentHandling.Disallow,
                AllowTrailingCommas = false,
            });
            var root = document.RootElement;
            if (root.ValueKind != JsonValueKind.Object)
                return Diagnostic("invalid_record", "Sidecar record must be a JSON object.");

            if (!TryString(root, "event", out var eventName))
                return Diagnostic("missing_event", "Sidecar record has no string event name.");
            if (!AllowedEvents.Contains(eventName))
                return Diagnostic("unknown_event", $"Ignored unknown sidecar event '{eventName}'.");
            if (!TryString(root, "protocol_version", out var version) || version != SupportedVersion)
                return Diagnostic(
                    "unsupported_protocol",
                    $"Expected sidecar protocol {SupportedVersion}; received '{(version.Length == 0 ? "missing" : version)}'.");
            if (!root.TryGetProperty("sequence", out var sequenceValue)
                || sequenceValue.ValueKind != JsonValueKind.Number
                || !sequenceValue.TryGetInt32(out var sequence)
                || sequence < 0)
            {
                return Diagnostic("invalid_sequence", "Sidecar sequence must be a nonnegative integer.");
            }

            if (eventName == "handshake")
            {
                if (HandshakeReceived || sequence != 0 || _lastSequence >= 0)
                    return Diagnostic("duplicate_handshake", "Handshake must be the first record.");
                if (!TryString(root, "sidecar", out _)
                    || !root.TryGetProperty("capabilities", out var capabilities)
                    || capabilities.ValueKind != JsonValueKind.Object)
                {
                    return Diagnostic(
                        "invalid_handshake",
                        "Handshake requires sidecar and capabilities fields.");
                }

                HandshakeReceived = true;
                _lastSequence = 0;
                return new SidecarProtocolEvent(eventName, root.Clone());
            }

            if (!HandshakeReceived)
                return Diagnostic("missing_handshake", "Ignored event received before the handshake.");
            if (sequence <= _lastSequence)
                return Diagnostic("invalid_sequence", "Sidecar sequence did not increase.");
            if (TerminalReceived)
                return Diagnostic("event_after_terminal", "Ignored event received after terminal state.");

            var fieldError = ValidateFields(eventName, root);
            if (fieldError is not null)
                return Diagnostic("invalid_fields", fieldError);

            _lastSequence = sequence;
            if (eventName == "complete"
                || (eventName == "error"
                    && root.GetProperty("terminal").ValueKind == JsonValueKind.True))
            {
                TerminalReceived = true;
            }

            return new SidecarProtocolEvent(eventName, root.Clone());
        }
        catch (JsonException ex)
        {
            return Diagnostic("invalid_json", $"Ignored malformed sidecar JSON: {ex.Message}");
        }
    }

    public static SidecarProtocolEvent CreateTerminalError(string code, string message)
    {
        var payload = JsonSerializer.SerializeToElement(new Dictionary<string, object?>
        {
            ["event"] = "error",
            ["protocol_version"] = SupportedVersion,
            ["sequence"] = -1,
            ["sidecar"] = "host",
            ["timestamp"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
            ["code"] = code,
            ["message"] = message,
            ["status"] = code == "cancelled" ? "cancelled" : "error",
            ["terminal"] = true,
        });
        return new SidecarProtocolEvent("error", payload);
    }

    private SidecarProtocolEvent Diagnostic(string code, string message)
    {
        ViolationCount++;
        var payload = JsonSerializer.SerializeToElement(new Dictionary<string, object?>
        {
            ["event"] = "log",
            ["protocol_version"] = SupportedVersion,
            ["sequence"] = -1,
            ["sidecar"] = _sidecarName,
            ["timestamp"] = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds() / 1000.0,
            ["level"] = "warning",
            ["code"] = code,
            ["message"] = message.Length <= 4096 ? message : message[..4096],
        });
        return new SidecarProtocolEvent("log", payload, IsDiagnostic: true);
    }

    private static string? ValidateFields(string eventName, JsonElement root)
    {
        switch (eventName)
        {
            case "progress":
                if (!TryString(root, "stage", out _)
                    || !IsNumber(root, "current")
                    || !root.TryGetProperty("total", out var total)
                    || (total.ValueKind != JsonValueKind.Number
                        && total.ValueKind != JsonValueKind.Null)
                    || !IsNumber(root, "percent"))
                {
                    return "Progress requires stage, current, total, and percent fields.";
                }
                var percent = root.GetProperty("percent").GetDouble();
                if (!double.IsFinite(percent) || percent < 0 || percent > 100)
                    return "Progress percent must be finite and between 0 and 100.";
                break;

            case "item":
            case "file":
            case "comic":
            case "detected":
                if (!TryString(root, "path", out _))
                    return $"{eventName} requires a nonempty path.";
                break;

            case "review":
                if (!TryString(root, "scan_id", out _))
                    return "Review requires a nonempty scan_id.";
                break;

            case "review_exported":
                if (!TryString(root, "scan_id", out _) || !TryString(root, "path", out _))
                    return "Review export requires nonempty scan_id and path fields.";
                break;

            case "log":
                if (!TryString(root, "level", out _) || !TryString(root, "message", out _))
                    return "Log requires level and message fields.";
                break;

            case "error":
                if (!TryString(root, "code", out _)
                    || !TryString(root, "message", out _)
                    || !root.TryGetProperty("terminal", out var terminal)
                    || (terminal.ValueKind != JsonValueKind.True
                        && terminal.ValueKind != JsonValueKind.False))
                {
                    return "Error requires code, message, and terminal fields.";
                }
                break;

            case "complete":
                if (!TryString(root, "status", out _)
                    || !IsNumber(root, "total")
                    || !root.TryGetProperty("terminal", out var isTerminal)
                    || isTerminal.ValueKind != JsonValueKind.True)
                {
                    return "Complete requires status, total, and terminal=true fields.";
                }
                break;
        }

        return null;
    }

    private static bool TryString(JsonElement root, string name, out string value)
    {
        value = string.Empty;
        if (!root.TryGetProperty(name, out var property)
            || property.ValueKind != JsonValueKind.String)
        {
            return false;
        }
        value = property.GetString() ?? string.Empty;
        return !string.IsNullOrWhiteSpace(value);
    }

    private static bool IsNumber(JsonElement root, string name) =>
        root.TryGetProperty(name, out var property)
        && property.ValueKind == JsonValueKind.Number;
}
