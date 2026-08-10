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

var review = session.AcceptLine(
    """{"event":"review","protocol_version":"1.0","sequence":2,"scan_id":"abc123","status":"running"}""");
Assert(review.Name == "review" && !review.IsDiagnostic, "Valid review metadata was rejected.");

var reviewExport = session.AcceptLine(
    """{"event":"review_exported","protocol_version":"1.0","sequence":3,"scan_id":"abc123","path":"C:\\review.json"}""");
Assert(reviewExport.Name == "review_exported" && !reviewExport.IsDiagnostic,
    "Valid review export metadata was rejected.");

var complete = session.AcceptLine(
    """{"event":"complete","protocol_version":"1.0","sequence":4,"status":"ok","total":2,"terminal":true}""");
Assert(complete.Name == "complete", "Valid terminal record was rejected.");
Assert(session.IsComplete, "Completed protocol stream was not recognized.");

var late = session.AcceptLine(
    """{"event":"log","protocol_version":"1.0","sequence":5,"level":"info","message":"late"}""");
Assert(late.Name == "log" && late.IsDiagnostic, "Post-terminal event was not isolated.");

var cancelled = SidecarProtocolSession.CreateTerminalError("cancelled", "Cancelled by user.");
Assert(cancelled.Name == "error", "Synthetic cancellation is not an error event.");
Assert(cancelled.Payload.GetProperty("terminal").GetBoolean(), "Cancellation is not terminal.");
Assert(cancelled.Payload.GetProperty("status").GetString() == "cancelled", "Cancellation status drifted.");

var crashRoot = Path.Combine(
    Path.GetTempPath(),
    $"fileorganizer-crash-contract-{Guid.NewGuid():N}");
Directory.CreateDirectory(crashRoot);
try
{
    const int maxCrashLogBytes = 900;
    const int maxCrashRecords = 2;
    const string knownSecret = "known-secret-value";
    var crashPath = Path.Combine(crashRoot, "fileorganizer_crash.log");
    File.WriteAllText(
        crashPath,
        string.Concat(Enumerable.Repeat(
            "legacy api_key=legacy-secret C:\\Users\\Alice\\Private\\legacy.txt\n---\n",
            100)));
    File.WriteAllText($"{crashPath}.3", "expired archive");
    var crashLog = new CrashLogWriter(
        crashPath,
        maxCrashLogBytes,
        maxCrashRecords,
        archiveCount: 2,
        knownSecretValues: [knownSecret]);

    for (var cycle = 0; cycle < 12; cycle++)
    {
        try
        {
            throw new InvalidOperationException(
                $"cycle={cycle} api_key=inline-secret --token command-secret "
                + $"Bearer bearer-secret {knownSecret} ghp_1234567890abcdefghijkl "
                + "at \"C:\\Users\\Alice\\Private\\report.csv\"");
        }
        catch (InvalidOperationException exception)
        {
            crashLog.Write(exception);
        }
    }

    var crashFiles = Directory.GetFiles(crashRoot, "fileorganizer_crash.log*");
    Assert(crashFiles.Length == 3, "Crash log archive retention was not bounded.");
    Assert(File.Exists($"{crashPath}.1") && File.Exists($"{crashPath}.2"),
        "Crash log rotation names were not deterministic.");
    foreach (var crashFile in crashFiles)
    {
        Assert(new FileInfo(crashFile).Length <= maxCrashLogBytes,
            "A rotated crash log exceeded its byte cap.");
        Assert(File.ReadLines(crashFile).Count(line => line == "---") <= maxCrashRecords,
            "A rotated crash log exceeded its record cap.");
    }

    var currentCrashLog = File.ReadAllText(crashPath);
    var allCrashLogs = string.Join("\n", crashFiles.Select(File.ReadAllText));
    Assert(currentCrashLog.Contains("cycle=11", StringComparison.Ordinal),
        "The newest crash context was not retained.");
    Assert(allCrashLogs.Contains(nameof(InvalidOperationException), StringComparison.Ordinal),
        "Crash exception type was lost.");
    Assert(allCrashLogs.Contains("Program.cs", StringComparison.Ordinal),
        "Actionable stack source context was lost.");
    foreach (var (label, value) in new[]
    {
        ("known", knownSecret),
        ("legacy", "legacy-secret"),
        ("labeled", "inline-secret"),
        ("argument", "command-secret"),
        ("bearer", "bearer-secret"),
        ("recognizable", "ghp_1234567890abcdefghijkl"),
        ("path", "Alice"),
    })
    {
        Assert(!allCrashLogs.Contains(value, StringComparison.OrdinalIgnoreCase),
            $"Sensitive {label} crash context was persisted.");
    }
    Assert(allCrashLogs.Contains("[REDACTED]", StringComparison.Ordinal),
        "Crash log did not mark redacted secrets.");
    Assert(allCrashLogs.Contains("[PATH]", StringComparison.Ordinal),
        "Crash log did not minimize a sensitive path.");
    Assert(!File.Exists($"{crashPath}.3"),
        "Crash log archives beyond the retention limit were not removed.");
}
finally
{
    Directory.Delete(crashRoot, recursive: true);
}

var originalSettings = new Dictionary<string, string>(StringComparer.Ordinal)
{
    ["music"] = "old-music",
    ["video"] = "old-video",
};
var desiredSettings = new Dictionary<string, string>(StringComparer.Ordinal)
{
    ["music"] = "new-music",
    ["video"] = "new-video",
};
var durableStore = new FakeSettingsStore(originalSettings);
var savedSettings = SettingsPersistence.Save(durableStore, desiredSettings);
Assert(savedSettings.Success, "A durable settings batch was rejected.");
var restartedStore = new FakeSettingsStore(originalSettings);
Assert(restartedStore.Read("music").Value == "new-music"
    && restartedStore.Read("video").Value == "new-video",
    "Saved settings did not survive a new store instance.");

var unavailableBacking = new Dictionary<string, string>(StringComparer.Ordinal)
{
    ["music"] = "old-music",
    ["video"] = "old-video",
};
var unavailableStore = new FakeSettingsStore(unavailableBacking)
{
    FailingWriteKey = "video",
};
var unavailableSave = SettingsPersistence.Save(unavailableStore, desiredSettings);
Assert(!unavailableSave.Success, "An unavailable settings store reported success.");
Assert(unavailableSave.PreviousValuesRestored,
    "A partial settings save did not report successful rollback.");
Assert(unavailableBacking["music"] == "old-music"
    && unavailableBacking["video"] == "old-video",
    "A partial settings save did not restore last-known-good values.");

var corruptBacking = new Dictionary<string, string>(StringComparer.Ordinal)
{
    ["music"] = "old-music",
    ["video"] = "old-video",
};
var corruptStore = new FakeSettingsStore(corruptBacking)
{
    FailingReadKey = "music",
};
var corruptSave = SettingsPersistence.Save(corruptStore, desiredSettings);
Assert(!corruptSave.Success && corruptSave.PreviousValuesRestored,
    "A corrupt stored value was not rejected before mutation.");
Assert(corruptBacking["music"] == "old-music",
    "A corrupt settings read changed the previous value.");

var rollbackBacking = new Dictionary<string, string>(StringComparer.Ordinal)
{
    ["music"] = "old-music",
    ["video"] = "old-video",
};
var rollbackStore = new FakeSettingsStore(rollbackBacking)
{
    FailingWriteKey = "video",
    FailingRollbackKey = "music",
};
var rollbackSave = SettingsPersistence.Save(rollbackStore, desiredSettings);
Assert(!rollbackSave.Success && !rollbackSave.PreviousValuesRestored,
    "A failed rollback did not expose its in-memory-only state.");

var integratedSettings = new UserSettings();
var integratedSave = integratedSettings.TrySavePreferences(new UserPreferences(
    "acoustid-fixture",
    "en,fr",
    "Music/{title}.{ext}",
    "Video/{title}.{ext}",
    "Books/{title}.{ext}"));
Assert(integratedSave.Success, "The integrated user settings save failed.");
var restartedSettings = new UserSettings();
Assert(restartedSettings.AcoustIdApiKey == "acoustid-fixture"
    && restartedSettings.DefaultSubtitleLanguages == "en,fr"
    && restartedSettings.DefaultMusicRenamePattern == "Music/{title}.{ext}"
    && restartedSettings.DefaultVideoRenamePattern == "Video/{title}.{ext}"
    && restartedSettings.DefaultBookRenamePattern == "Books/{title}.{ext}",
    "Integrated settings did not survive a service restart.");

var collectionNotifications = 0;
var streamedRows = new BoundedObservableCollection<StreamFixture>(
    UiStreamLimits.MaxResultRows,
    item => item.IsImportant,
    UiStreamLimits.MaxImportantRows,
    UiStreamLimits.ReplacementNotificationInterval);
streamedRows.CollectionChanged += (_, _) => collectionNotifications++;
var streamTimer = System.Diagnostics.Stopwatch.StartNew();
for (var index = 0; index < 100_000; index++)
    streamedRows.Add(new StreamFixture(index, IsImportant: index % 100 == 0));
streamedRows.FlushPendingChanges();
streamTimer.Stop();
Assert(streamedRows.Count == UiStreamLimits.MaxResultRows,
    "Streamed result rows exceeded their visible cap.");
Assert(streamedRows.TotalAdded == 100_000 && streamedRows.TotalEvicted == 99_000,
    "Streamed result totals drifted after eviction.");
Assert(streamedRows.Count(item => item.IsImportant) == UiStreamLimits.MaxImportantRows,
    "Recent important rows did not retain their dedicated capacity.");
Assert(streamedRows.Any(item => item.Id == 99_900),
    "The newest important row was not retained.");
Assert(collectionNotifications < 10_000,
    "Replacement collection notifications were not coalesced.");
Assert(streamTimer.Elapsed < TimeSpan.FromSeconds(10),
    "The 100,000-event bounded collection fixture exceeded its latency budget.");

var outputBuffer = new BoundedTextBuffer();
var outputRefreshes = 0;
for (var index = 0; index < 100_000; index++)
{
    if (outputBuffer.AppendLine($"event-{index:D6} {new string('x', 48)}"))
    {
        _ = outputBuffer.Snapshot();
        outputRefreshes++;
    }
}
var boundedOutput = outputBuffer.Snapshot();
Assert(outputBuffer.Length <= UiStreamLimits.MaxOutputCharacters,
    "Streamed text exceeded its character cap.");
Assert(outputBuffer.TruncatedCharacters > 0
    && boundedOutput.StartsWith("[... earlier output truncated ...]", StringComparison.Ordinal),
    "Streamed text did not expose truncation.");
Assert(boundedOutput.Contains("event-099999", StringComparison.Ordinal),
    "Streamed text did not retain the newest output.");
Assert(outputRefreshes < 2_000,
    "Streamed text refreshes were not coalesced.");

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

Console.WriteLine("WinUI service contract fixtures passed.");

sealed class FakeSettingsStore(IDictionary<string, string> values) : IStringSettingsStore
{
    private readonly Dictionary<string, int> _writeAttempts = new(StringComparer.Ordinal);

    public string? FailingReadKey { get; init; }
    public string? FailingWriteKey { get; init; }
    public string? FailingRollbackKey { get; init; }

    public StoredStringResult Read(string key)
    {
        if (key == FailingReadKey)
            return StoredStringResult.Failed("Injected read failure.");
        return values.TryGetValue(key, out var value)
            ? StoredStringResult.Found(value)
            : StoredStringResult.Missing();
    }

    public bool TryWrite(string key, string value, out string? error)
    {
        var attempt = _writeAttempts.GetValueOrDefault(key) + 1;
        _writeAttempts[key] = attempt;
        if (key == FailingWriteKey || (key == FailingRollbackKey && attempt > 1))
        {
            error = "Injected write failure.";
            return false;
        }

        values[key] = value;
        error = null;
        return true;
    }

    public bool TryRemove(string key, out string? error)
    {
        values.Remove(key);
        error = null;
        return true;
    }
}

sealed record StreamFixture(int Id, bool IsImportant);
