using Windows.Storage;
using Windows.Security.Credentials;

namespace FileOrganizer.UI.Services;

/// <summary>
/// Persisted user-level preferences. Ordinary preferences are stored in
/// `%LOCALAPPDATA%\Packages\<package>\LocalState\settings.dat`; the AcoustID
/// secret is stored in the Windows Credential Locker and is never written to
/// LocalSettings.
/// </summary>
public interface IUserSettings
{
    string AcoustIdApiKey { get; set; }
    bool TrySetAcoustIdApiKey(string value);
    SettingsSaveResult TrySavePreferences(UserPreferences preferences);
    string DefaultSubtitleLanguages { get; set; }
    string DefaultMusicRenamePattern { get; set; }
    string DefaultVideoRenamePattern { get; set; }
    string DefaultBookRenamePattern { get; set; }
    string LastSourceFolder { get; set; }
    string LastDestFolder { get; set; }
}

public sealed class UserSettings : IUserSettings
{
    private const string AcoustIdResource = "FileOrganizer.AcoustID";
    private const string AcoustIdUser = "api-key";

    private readonly IStringSettingsStore _localSettings = new LocalSettingsStore();

    private string Get(string key, string fallback)
    {
        var stored = _localSettings.Read(key);
        return stored.Success && stored.Exists ? stored.Value : fallback;
    }

    private void Set(string key, string value)
    {
        _localSettings.TryWrite(key, value ?? "", out _);
    }

    private bool Remove(string key) => _localSettings.TryRemove(key, out _);

    private static string ReadAcoustIdSecret()
    {
        try
        {
            var vault = new PasswordVault();
            var credential = vault.Retrieve(AcoustIdResource, AcoustIdUser);
            credential.RetrievePassword();
            return credential.Password ?? "";
        }
        catch
        {
            return "";
        }
    }

    private bool TryWriteAcoustIdSecret(string value, bool removeLegacy = true)
    {
        PasswordCredential? previous = null;
        var wrote = false;
        try
        {
            var vault = new PasswordVault();
            try
            {
                previous = vault.Retrieve(AcoustIdResource, AcoustIdUser);
                previous.RetrievePassword();
                vault.Remove(previous);
            }
            catch
            {
                previous = null;
            }

            if (!string.IsNullOrEmpty(value))
            {
                vault.Add(new PasswordCredential(AcoustIdResource, AcoustIdUser, value));
                wrote = true;
            }

            if (removeLegacy && !Remove("AcoustIdApiKey"))
                throw new InvalidOperationException("Could not remove the legacy AcoustID setting.");
            return true;
        }
        catch
        {
            if (wrote)
            {
                try
                {
                    var remove = new PasswordVault();
                    var added = remove.Retrieve(AcoustIdResource, AcoustIdUser);
                    remove.Remove(added);
                }
                catch { }
            }
            if (previous is not null)
            {
                try
                {
                    var restore = new PasswordVault();
                    restore.Add(new PasswordCredential(
                        AcoustIdResource, AcoustIdUser, previous.Password));
                }
                catch { }
            }
            return false;
        }
    }

    public string AcoustIdApiKey
    {
        get
        {
            var stored = ReadAcoustIdSecret();
            if (!string.IsNullOrEmpty(stored))
            {
                Remove("AcoustIdApiKey");
                return stored;
            }

            // One-time migration from the old plaintext LocalSettings value.
            var legacy = Get("AcoustIdApiKey", "");
            if (!string.IsNullOrEmpty(legacy) && TryWriteAcoustIdSecret(legacy))
                return legacy;
            return "";
        }
        set => TrySetAcoustIdApiKey(value);
    }

    public bool TrySetAcoustIdApiKey(string value) =>
        TryWriteAcoustIdSecret(value?.Trim() ?? "");

    public SettingsSaveResult TrySavePreferences(UserPreferences preferences)
    {
        ArgumentNullException.ThrowIfNull(preferences);

        var previousSecret = ReadAcoustIdSecret();
        if (!TryWriteAcoustIdSecret(preferences.AcoustIdApiKey.Trim()))
        {
            return new SettingsSaveResult(
                false,
                false,
                "Windows Credential Locker did not accept the AcoustID key.");
        }

        var localResult = SettingsPersistence.Save(
            _localSettings,
            new Dictionary<string, string>(StringComparer.Ordinal)
            {
                ["DefaultSubtitleLanguages"] = preferences.DefaultSubtitleLanguages,
                ["DefaultMusicRenamePattern"] = preferences.DefaultMusicRenamePattern,
                ["DefaultVideoRenamePattern"] = preferences.DefaultVideoRenamePattern,
                ["DefaultBookRenamePattern"] = preferences.DefaultBookRenamePattern,
            });
        if (localResult.Success)
            return localResult;

        var secretRestored = TryWriteAcoustIdSecret(previousSecret, removeLegacy: false);
        return localResult with
        {
            PreviousValuesRestored = localResult.PreviousValuesRestored && secretRestored,
        };
    }

    public string DefaultSubtitleLanguages
    {
        get => Get("DefaultSubtitleLanguages", "en");
        set => Set("DefaultSubtitleLanguages", value);
    }

    public string DefaultMusicRenamePattern
    {
        get => Get("DefaultMusicRenamePattern",
            "Music/{albumartist}/{year} - {album}/{disc:02}-{track:02} {title}.{ext}");
        set => Set("DefaultMusicRenamePattern", value);
    }

    public string DefaultVideoRenamePattern
    {
        get => Get("DefaultVideoRenamePattern",
            "Movies/{title} ({year})/{title} ({year}).{ext}");
        set => Set("DefaultVideoRenamePattern", value);
    }

    public string DefaultBookRenamePattern
    {
        get => Get("DefaultBookRenamePattern", "Books/{author}/{title}.{ext}");
        set => Set("DefaultBookRenamePattern", value);
    }

    public string LastSourceFolder
    {
        get => Get("LastSourceFolder", "");
        set => Set("LastSourceFolder", value);
    }

    public string LastDestFolder
    {
        get => Get("LastDestFolder", "");
        set => Set("LastDestFolder", value);
    }

    private sealed class LocalSettingsStore : IStringSettingsStore
    {
        public StoredStringResult Read(string key)
        {
            try
            {
                var values = ApplicationData.Current.LocalSettings.Values;
                if (!values.TryGetValue(key, out var value))
                    return StoredStringResult.Missing();
                return value is string text
                    ? StoredStringResult.Found(text)
                    : StoredStringResult.Failed($"Stored value {key} has an invalid type.");
            }
            catch (Exception exception)
            {
                return StoredStringResult.Failed(exception.Message);
            }
        }

        public bool TryWrite(string key, string value, out string? error)
        {
            try
            {
                ApplicationData.Current.LocalSettings.Values[key] = value;
                error = null;
                return true;
            }
            catch (Exception exception)
            {
                error = exception.Message;
                return false;
            }
        }

        public bool TryRemove(string key, out string? error)
        {
            try
            {
                ApplicationData.Current.LocalSettings.Values.Remove(key);
                error = null;
                return true;
            }
            catch (Exception exception)
            {
                error = exception.Message;
                return false;
            }
        }
    }
}
