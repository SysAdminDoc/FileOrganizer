using System.Collections.ObjectModel;
using System.Collections.Specialized;
using System.ComponentModel;
using System.Text;

namespace FileOrganizer.UI.Services;

public static class UiStreamLimits
{
    public const int MaxResultRows = 1_000;
    public const int MaxImportantRows = 200;
    public const int MaxCategoryRows = 64;
    public const int MaxFilesPerGroup = 200;
    public const int ReplacementNotificationInterval = 32;
    public const int MaxOutputCharacters = 128 * 1024;
    public const int OutputRefreshInterval = 64;
}

public sealed class BoundedObservableCollection<T> : ObservableCollection<T>
{
    private readonly int _capacity;
    private readonly int _importantCapacity;
    private readonly int _notificationInterval;
    private readonly Func<T, bool> _isImportant;
    private int _visibleImportantCount;
    private int _pendingReplacements;

    public BoundedObservableCollection(
        int capacity = UiStreamLimits.MaxResultRows,
        Func<T, bool>? isImportant = null,
        int importantCapacity = UiStreamLimits.MaxImportantRows,
        int notificationInterval = UiStreamLimits.ReplacementNotificationInterval)
    {
        if (capacity < 1)
            throw new ArgumentOutOfRangeException(nameof(capacity));
        if (importantCapacity < 0 || importantCapacity > capacity)
            throw new ArgumentOutOfRangeException(nameof(importantCapacity));
        if (notificationInterval < 1)
            throw new ArgumentOutOfRangeException(nameof(notificationInterval));

        _capacity = capacity;
        _importantCapacity = importantCapacity;
        _notificationInterval = notificationInterval;
        _isImportant = isImportant ?? (_ => false);
    }

    public long TotalAdded { get; private set; }
    public long TotalEvicted { get; private set; }
    public long ImportantAdded { get; private set; }
    public string RetentionNotice => TotalEvicted > 0
        ? $" Showing {Count:N0} recent/important rows."
        : string.Empty;

    protected override void InsertItem(int index, T item)
    {
        var important = _isImportant(item);
        TotalAdded++;
        if (important)
            ImportantAdded++;

        var replaceImportant = important
            && _importantCapacity > 0
            && _visibleImportantCount >= _importantCapacity;
        if (Count < _capacity && !replaceImportant)
        {
            if (important)
                _visibleImportantCount++;
            base.InsertItem(index, item);
            return;
        }

        var removeIndex = replaceImportant
            ? FindOldest(important: true)
            : FindOldest(important: false);
        if (removeIndex < 0)
            removeIndex = 0;

        if (_isImportant(Items[removeIndex]))
            _visibleImportantCount--;
        Items.RemoveAt(removeIndex);
        Items.Add(item);
        if (important)
            _visibleImportantCount++;
        TotalEvicted++;

        _pendingReplacements++;
        if (important || _pendingReplacements >= _notificationInterval)
            FlushPendingChanges();
    }

    protected override void RemoveItem(int index)
    {
        FlushPendingChanges();
        if (_isImportant(Items[index]))
            _visibleImportantCount--;
        base.RemoveItem(index);
    }

    protected override void SetItem(int index, T item)
    {
        FlushPendingChanges();
        if (_isImportant(Items[index]))
            _visibleImportantCount--;
        if (_isImportant(item))
            _visibleImportantCount++;
        base.SetItem(index, item);
    }

    protected override void ClearItems()
    {
        _pendingReplacements = 0;
        _visibleImportantCount = 0;
        TotalAdded = 0;
        TotalEvicted = 0;
        ImportantAdded = 0;
        base.ClearItems();
    }

    public void FlushPendingChanges()
    {
        if (_pendingReplacements == 0)
            return;

        _pendingReplacements = 0;
        OnPropertyChanged(new PropertyChangedEventArgs("Item[]"));
        OnCollectionChanged(new NotifyCollectionChangedEventArgs(
            NotifyCollectionChangedAction.Reset));
    }

    private int FindOldest(bool important)
    {
        for (var index = 0; index < Items.Count; index++)
        {
            if (_isImportant(Items[index]) == important)
                return index;
        }

        return -1;
    }
}

public sealed class BoundedTextBuffer
{
    private const string TruncationMarker = "[... earlier output truncated ...]\n";
    private readonly StringBuilder _buffer = new();
    private readonly int _maxCharacters;
    private readonly int _refreshInterval;
    private int _pendingAppends;

    public BoundedTextBuffer(
        int maxCharacters = UiStreamLimits.MaxOutputCharacters,
        int refreshInterval = UiStreamLimits.OutputRefreshInterval)
    {
        if (maxCharacters <= TruncationMarker.Length)
            throw new ArgumentOutOfRangeException(nameof(maxCharacters));
        if (refreshInterval < 1)
            throw new ArgumentOutOfRangeException(nameof(refreshInterval));

        _maxCharacters = maxCharacters;
        _refreshInterval = refreshInterval;
    }

    public long TotalCharactersAppended { get; private set; }
    public long TruncatedCharacters { get; private set; }
    public int Length => _buffer.Length;

    public bool AppendLine(string? value = null) =>
        Append((value ?? string.Empty) + Environment.NewLine);

    public bool Append(string? value)
    {
        if (string.IsNullOrEmpty(value))
            return false;

        TotalCharactersAppended += value.Length;
        if (value.Length >= _maxCharacters)
        {
            var retainedLength = _maxCharacters - TruncationMarker.Length;
            TruncatedCharacters += _buffer.Length + value.Length - retainedLength;
            _buffer.Clear();
            _buffer.Append(TruncationMarker);
            _buffer.Append(value.AsSpan(value.Length - retainedLength));
        }
        else
        {
            _buffer.Append(value);
            TrimToLimit();
        }

        _pendingAppends++;
        return TotalCharactersAppended == value.Length
            || _pendingAppends >= _refreshInterval;
    }

    public string Snapshot()
    {
        _pendingAppends = 0;
        return _buffer.ToString();
    }

    public void Clear()
    {
        _buffer.Clear();
        _pendingAppends = 0;
        TotalCharactersAppended = 0;
        TruncatedCharacters = 0;
    }

    private void TrimToLimit()
    {
        if (_buffer.Length <= _maxCharacters)
            return;

        var retainedLength = _maxCharacters - TruncationMarker.Length;
        var removeCount = _buffer.Length - retainedLength;
        var searchLimit = Math.Min(_buffer.Length, removeCount + 1_024);
        for (var index = removeCount; index < searchLimit; index++)
        {
            if (_buffer[index] == '\n')
            {
                removeCount = index + 1;
                break;
            }
        }

        _buffer.Remove(0, removeCount);
        _buffer.Insert(0, TruncationMarker);
        TruncatedCharacters += removeCount;
    }
}
