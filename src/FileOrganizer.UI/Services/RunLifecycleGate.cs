using System.Collections.Concurrent;

namespace FileOrganizer.UI.Services;

/// <summary>
/// Serializes runs with the same logical key. A lease is released only after
/// the prior run has drained its process streams and completed cancellation.
/// Different sidecars remain independent.
/// </summary>
public sealed class RunLifecycleGate
{
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _gates =
        new(StringComparer.OrdinalIgnoreCase);

    public async ValueTask<IDisposable> EnterAsync(
        string key,
        CancellationToken cancellationToken)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(key);
        var gate = _gates.GetOrAdd(key, static _ => new SemaphoreSlim(1, 1));
        await gate.WaitAsync(cancellationToken).ConfigureAwait(false);
        return new Lease(gate);
    }

    private sealed class Lease(SemaphoreSlim gate) : IDisposable
    {
        private SemaphoreSlim? _gate = gate;

        public void Dispose()
        {
            Interlocked.Exchange(ref _gate, null)?.Release();
        }
    }
}
