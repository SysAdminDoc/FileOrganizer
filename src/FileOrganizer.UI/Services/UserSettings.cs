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

    private static ApplicationDataContainer Values
    {
        get
        {
            try { return ApplicationData.Current.LocalSettings; }
            catch { return null!; }
        }
    }

    private static string Get(string key, string fallback)
    {
        try { return Values?.Values.TryGetValue(key, out var v) == true && v is string s ? s : fallback; }
        catch { return fallback; }
    }

    private static void Set(string key, string value)
    {
        try { if (Values is not null) Values.Values[key] = value ?? ""; }
        catch { }
    }

    private static bool Remove(string key)
    {
        try
        {
            return Values is null
                || !Values.Values.ContainsKey(key)
                || Values.Values.Remove(key);
        }
        catch { return false; }
    }

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

    private static bool TryWriteAcoustIdSecret(string value)
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

            if (!Remove("AcoustIdApiKey"))
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
}
