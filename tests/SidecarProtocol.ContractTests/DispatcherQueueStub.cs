namespace Microsoft.UI.Dispatching;

public sealed class DispatcherQueue
{
    public static DispatcherQueue? GetForCurrentThread() => null;

    public bool TryEnqueue(Action callback)
    {
        callback();
        return true;
    }
}
