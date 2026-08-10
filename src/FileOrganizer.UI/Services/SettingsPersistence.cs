namespace FileOrganizer.UI.Services;

public sealed record StoredStringResult(
    bool Success,
    bool Exists,
    string Value,
    string? Error = null)
{
    public static StoredStringResult Missing() => new(true, false, string.Empty);
    public static StoredStringResult Found(string value) => new(true, true, value);
    public static StoredStringResult Failed(string error) => new(false, false, string.Empty, error);
}

public sealed record SettingsSaveResult(
    bool Success,
    bool PreviousValuesRestored,
    string? Error = null);

public interface IStringSettingsStore
{
    StoredStringResult Read(string key);
    bool TryWrite(string key, string value, out string? error);
    bool TryRemove(string key, out string? error);
}

public static class SettingsPersistence
{
    public static SettingsSaveResult Save(
        IStringSettingsStore store,
        IReadOnlyDictionary<string, string> values)
    {
        ArgumentNullException.ThrowIfNull(store);
        ArgumentNullException.ThrowIfNull(values);

        var previous = new Dictionary<string, StoredStringResult>(StringComparer.Ordinal);
        var changedKeys = new List<string>();
        try
        {
            foreach (var key in values.Keys)
            {
                var stored = store.Read(key);
                if (!stored.Success)
                {
                    return new SettingsSaveResult(
                        false,
                        true,
                        stored.Error ?? $"Could not read {key} before saving.");
                }

                previous[key] = stored;
            }

            foreach (var (key, value) in values)
            {
                if (!store.TryWrite(key, value ?? string.Empty, out var error))
                    return RollBack(store, previous, changedKeys, error ?? $"Could not write {key}.");
                changedKeys.Add(key);
            }

            foreach (var (key, expected) in values)
            {
                var stored = store.Read(key);
                if (!stored.Success || !stored.Exists || stored.Value != (expected ?? string.Empty))
                {
                    return RollBack(
                        store,
                        previous,
                        changedKeys,
                        stored.Error ?? $"Could not verify {key} after saving.");
                }
            }

            return new SettingsSaveResult(true, true);
        }
        catch (Exception exception)
        {
            return RollBack(store, previous, changedKeys, exception.Message);
        }
    }

    private static SettingsSaveResult RollBack(
        IStringSettingsStore store,
        IReadOnlyDictionary<string, StoredStringResult> previous,
        IReadOnlyList<string> changedKeys,
        string error)
    {
        var restored = true;
        for (var index = changedKeys.Count - 1; index >= 0; index--)
        {
            var key = changedKeys[index];
            var oldValue = previous[key];
            try
            {
                var success = oldValue.Exists
                    ? store.TryWrite(key, oldValue.Value, out _)
                    : store.TryRemove(key, out _);
                restored &= success;
            }
            catch
            {
                restored = false;
            }
        }

        return new SettingsSaveResult(false, restored, error);
    }
}

public sealed record UserPreferences(
    string AcoustIdApiKey,
    string DefaultSubtitleLanguages,
    string DefaultMusicRenamePattern,
    string DefaultVideoRenamePattern,
    string DefaultBookRenamePattern);
