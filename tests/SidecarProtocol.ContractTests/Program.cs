using FileOrganizer.UI.Services;

static void Assert(bool condition, string message)
{
    if (!condition)
        throw new InvalidOperationException(message);
}

var session = new SidecarProtocolSession("contract-fixture");

var handshake = session.AcceptLine(
    """{"event":"handshake","protocol_version":"1.0","sequence":0,"sidecar":"fixture","capabilities":{}}""");
Assert(handshake.Name == "handshake", "Valid handshake was rejected.");
Assert(session.HandshakeReceived, "Handshake state was not recorded.");

var malformed = session.AcceptLine("{not-json");
Assert(malformed.Name == "log" && malformed.IsDiagnostic, "Malformed JSON escaped isolation.");

var unknown = session.AcceptLine(
    """{"event":"future_event","protocol_version":"1.0","sequence":1}""");
Assert(unknown.Name == "log" && unknown.IsDiagnostic, "Unknown event escaped isolation.");

var progress = session.AcceptLine(
    """{"event":"progress","protocol_version":"1.0","sequence":1,"stage":"scan","current":1,"total":2,"percent":50}""");
Assert(progress.Name == "progress" && !progress.IsDiagnostic, "Valid progress was rejected.");

var complete = session.AcceptLine(
    """{"event":"complete","protocol_version":"1.0","sequence":2,"status":"ok","total":2,"terminal":true}""");
Assert(complete.Name == "complete", "Valid terminal record was rejected.");
Assert(session.IsComplete, "Completed protocol stream was not recognized.");

var late = session.AcceptLine(
    """{"event":"log","protocol_version":"1.0","sequence":3,"level":"info","message":"late"}""");
Assert(late.Name == "log" && late.IsDiagnostic, "Post-terminal event was not isolated.");

var cancelled = SidecarProtocolSession.CreateTerminalError("cancelled", "Cancelled by user.");
Assert(cancelled.Name == "error", "Synthetic cancellation is not an error event.");
Assert(cancelled.Payload.GetProperty("terminal").GetBoolean(), "Cancellation is not terminal.");
Assert(cancelled.Payload.GetProperty("status").GetString() == "cancelled", "Cancellation status drifted.");

Console.WriteLine("Sidecar protocol contract fixtures passed.");
