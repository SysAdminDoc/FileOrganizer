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

var lifecycleGate = new RunLifecycleGate();
for (var cycle = 0; cycle < 10; cycle++)
{
    var firstStarted = new TaskCompletionSource<bool>(
        TaskCreationOptions.RunContinuationsAsynchronously);
    var firstDrained = new TaskCompletionSource<bool>(
        TaskCreationOptions.RunContinuationsAsynchronously);
    var secondStarted = new TaskCompletionSource<bool>(
        TaskCreationOptions.RunContinuationsAsynchronously);
    using var cancellation = new CancellationTokenSource();

    async Task FirstRunAsync()
    {
        using var lease = await lifecycleGate.EnterAsync(
            "restart-fixture", CancellationToken.None);
        firstStarted.SetResult(true);
        try
        {
            await Task.Delay(Timeout.InfiniteTimeSpan, cancellation.Token);
        }
        catch (OperationCanceledException)
        {
            await Task.Yield();
            firstDrained.SetResult(true);
        }
    }

    async Task SecondRunAsync()
    {
        using var lease = await lifecycleGate.EnterAsync(
            "restart-fixture", CancellationToken.None);
        Assert(firstDrained.Task.IsCompleted, "Restart began before cancelled run drained.");
        secondStarted.SetResult(true);
    }

    var firstRun = FirstRunAsync();
    await firstStarted.Task;
    var secondRun = SecondRunAsync();
    await Task.Yield();
    Assert(!secondStarted.Task.IsCompleted, "Same-sidecar restart was not serialized.");
    cancellation.Cancel();
    await Task.WhenAll(firstRun, secondRun);
    Assert(secondStarted.Task.IsCompleted, "Restart did not begin after cancellation drained.");
}

var pythonRunner = new PythonRunner();
for (var cycle = 0; cycle < 3; cycle++)
{
    using var cancellation = new CancellationTokenSource();
    var firstItem = new TaskCompletionSource<bool>(
        TaskCreationOptions.RunContinuationsAsynchronously);
    var cancelledItems = 0;
    var cancellationEvents = 0;
    var cancelledRun = pythonRunner.RunScriptNdjsonAsync(
        "tests/fixtures/runner_fixture.py",
        ["--count", "1000", "--delay", "0.005"],
        (name, payload) =>
        {
            if (name == "item")
            {
                Interlocked.Increment(ref cancelledItems);
                firstItem.TrySetResult(true);
            }
            else if (name == "error"
                && payload.TryGetProperty("code", out var code)
                && code.GetString() == "cancelled")
            {
                Interlocked.Increment(ref cancellationEvents);
            }
        },
        cancellation.Token);

    await firstItem.Task.WaitAsync(TimeSpan.FromSeconds(10));
    cancellation.Cancel();
    var cancelledResult = await cancelledRun;
    Assert(!cancelledResult.Success, "Cancelled runner unexpectedly succeeded.");
    Assert(cancelledResult.ErrorMessage == "Cancelled by user.", "Cancellation result drifted.");
    Assert(cancellationEvents == 1, "Cancellation emitted more than one terminal event.");
    var itemCountAfterCancel = Volatile.Read(ref cancelledItems);
    await Task.Delay(50);
    Assert(
        Volatile.Read(ref cancelledItems) == itemCountAfterCancel,
        "A stale item callback arrived after cancellation completed.");

    var restartItems = 0;
    var restartResult = await pythonRunner.RunScriptNdjsonAsync(
        "tests/fixtures/runner_fixture.py",
        ["--count", "2", "--delay", "0.001"],
        (name, _) =>
        {
            if (name == "item")
                Interlocked.Increment(ref restartItems);
        });
    Assert(restartResult.Success, $"Restart cycle {cycle} failed: {restartResult.ErrorMessage}");
    Assert(restartItems == 2, "Restart did not consume exactly its own events.");
}

Console.WriteLine("Sidecar protocol and lifecycle contract fixtures passed.");
