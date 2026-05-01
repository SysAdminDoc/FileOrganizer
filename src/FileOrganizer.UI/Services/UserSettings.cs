using Windows.Storage;

namespace FileOrganizer.UI.Services;

/// <summary>
/// Persisted user-level preferences. Stored in
/// `%LOCALAPPDATA%\Packages\<package>\LocalState\settings.dat` via the
/// WinRT ApplicationData APIs — no DLL dependency, survives upgrades.
/// </summary>
public interface IUserSettings
{
    string AcoustIdApiKey { get; set; }
    string DefaultSubtitleLanguages { get; set; }
    string DefaultMusicRenamePattern { get; set; }
    string DefaultVideoRenamePattern { get; set; }
    string DefaultBookRenamePattern { get; set; }
    string LastSourceFolder { get; set; }
    string LastDestFolder { get; set; }
}

public sealed class UserSettings : IUserSettings
{
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

    public string AcoustIdApiKey
    {
        get => Get("AcoustIdApiKey", "");
        set => Set("AcoustIdApiKey", value);
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
}
