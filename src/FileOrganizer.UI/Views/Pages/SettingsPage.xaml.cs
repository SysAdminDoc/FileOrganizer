using System.Collections.ObjectModel;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using Windows.Storage;
using Windows.UI;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class SettingsPage : Page
{
    private readonly IThemeService _theme;
    private readonly IUserSettings _settings;
    private readonly IPythonRunner _python;
    public ObservableCollection<ThemeTile> Themes { get; } = [];

    public SettingsPage()
    {
        InitializeComponent();
        _theme = App.Services.GetRequiredService<IThemeService>();
        _settings = App.Services.GetRequiredService<IUserSettings>();
        _python = App.Services.GetRequiredService<IPythonRunner>();

        LoadThemes();
        ThemeRepeater.ItemsSource = Themes;

        ApiKeyBox.Password = _settings.AcoustIdApiKey;
        MusicPatternBox.Text = _settings.DefaultMusicRenamePattern;
        VideoPatternBox.Text = _settings.DefaultVideoRenamePattern;
        BookPatternBox.Text = _settings.DefaultBookRenamePattern;
        LangsBox.Text = _settings.DefaultSubtitleLanguages;
        Loaded += async (_, _) => await RefreshWatchTaskAsync(includeLog: false);
    }

    private void LoadThemes()
    {
        Themes.Clear();
        var current = _theme.CurrentTheme.Id;
        foreach (var t in _theme.AvailableThemes)
            Themes.Add(new ThemeTile(t, isCurrent: t.Id == current));
    }

    private void ThemeTile_Click(object sender, RoutedEventArgs e)
    {
        if (sender is Button b && b.Tag is string id)
        {
            _theme.Apply(id);
            // Refresh tile selection markers.
            LoadThemes();
            SaveStatusText.Text = $"Theme: {_theme.CurrentTheme.DisplayName}";
        }
    }

    private void Save_Click(object sender, RoutedEventArgs e)
    {
        var patterns = new[]
        {
            MusicPatternBox.Text ?? "",
            VideoPatternBox.Text ?? "",
            BookPatternBox.Text ?? ""
        };
        foreach (var pattern in patterns)
        {
            if (!RenamePatternValidator.TryValidate(pattern, out var error))
            {
                SaveStatusText.Text = $"Rename pattern not saved: {error}";
                return;
            }
        }

        var saveResult = _settings.TrySavePreferences(new UserPreferences(
            ApiKeyBox.Password ?? "",
            string.IsNullOrWhiteSpace(LangsBox.Text) ? "en" : LangsBox.Text,
            MusicPatternBox.Text ?? "",
            VideoPatternBox.Text ?? "",
            BookPatternBox.Text ?? ""));
        if (!saveResult.Success)
        {
            SaveStatusText.Text = saveResult.PreviousValuesRestored
                ? "Settings were not saved. Previous settings remain active; choose Save to retry."
                : "Settings could not be saved. These edits are only shown here; choose Save to retry.";
            return;
        }

        SaveStatusText.Text = "Saved.";
    }

    private void Reset_Click(object sender, RoutedEventArgs e)
    {
        ApiKeyBox.Password = "";
        MusicPatternBox.Text = "Music/{albumartist}/{year} - {album}/{disc:02}-{track:02} {title}.{ext}";
        VideoPatternBox.Text = "Movies/{title} ({year})/{title} ({year}).{ext}";
        BookPatternBox.Text = "Books/{author}/{title}.{ext}";
        LangsBox.Text = "en";
        Save_Click(sender, e);
        if (SaveStatusText.Text == "Saved.")
            SaveStatusText.Text = "Defaults restored.";
    }

    private void WatchDebounce_ValueChanged(object sender, RangeBaseValueChangedEventArgs e)
    {
        if (WatchDebounceValueText is not null)
            WatchDebounceValueText.Text = $"{WatchTaskProtocol.ClampDebounce(e.NewValue)} seconds";
    }

    private static string ReadSavedWatches()
    {
        try
        {
            return ApplicationData.Current.LocalSettings.Values.TryGetValue(
                "Watches.v1", out var value) && value is string raw
                ? raw
                : string.Empty;
        }
        catch
        {
            return string.Empty;
        }
    }

    private async void WatchApply_Click(object sender, RoutedEventArgs e)
    {
        if (!WatchStartupToggle.IsOn)
        {
            await RunWatchCommandAsync(["--disable"]);
            return;
        }

        if (!WatchTaskProtocol.TryParseSavedWatches(
                ReadSavedWatches(), out var watches, out var error))
        {
            WatchTaskStatusText.Text = $"Cannot enable startup: {error}";
            return;
        }
        if (watches.Count == 0)
        {
            WatchTaskStatusText.Text =
                "Cannot enable startup: add at least one source/destination pair on the Watch page.";
            return;
        }

        var debounce = WatchTaskProtocol.ClampDebounce(WatchDebounceSlider.Value);
        var configured = await RunWatchCommandAsync([
            "--configure",
            "--watches", WatchTaskProtocol.SerializeWatches(watches),
            "--debounce", debounce.ToString(System.Globalization.CultureInfo.InvariantCulture),
        ]);
        if (configured)
            await RunWatchCommandAsync(["--register"]);
    }

    private async void WatchRemove_Click(object sender, RoutedEventArgs e) =>
        await RunWatchCommandAsync(["--unregister"]);

    private async void WatchLog_Click(object sender, RoutedEventArgs e) =>
        await RefreshWatchTaskAsync(includeLog: true);

    private async Task RefreshWatchTaskAsync(bool includeLog)
    {
        await RunWatchCommandAsync([includeLog ? "--logs" : "--status"]);
    }

    private async Task<bool> RunWatchCommandAsync(string[] arguments)
    {
        WatchTaskStatusText.Text = "Updating Watch Mode…";
        var result = await _python.RunScriptAsync("watch_task_run.py", arguments);
        if (!WatchTaskProtocol.TryParseState(result.Stdout, out var state, out var parseError)
            || state is null)
        {
            WatchTaskStatusText.Text = result.Success
                ? parseError
                : $"Watch task failed: {parseError} {result.Stderr}".Trim();
            return false;
        }
        if (!result.Success || !string.IsNullOrWhiteSpace(state.Error))
        {
            WatchTaskStatusText.Text = state.Error ?? result.ErrorMessage ?? "Watch task failed.";
            return false;
        }

        WatchStartupToggle.IsOn = state.Enabled;
        WatchDebounceSlider.Value = state.DebounceSeconds;
        WatchTaskStatusText.Text = state.Supported
            ? $"{(state.Registered ? "Registered" : "Not registered")} · "
              + $"{state.WatchCount} watch(es) · {state.DebounceSeconds}s quiet window"
              + (string.IsNullOrWhiteSpace(state.Message) ? "" : $" · {state.Message}")
            : "Task Scheduler startup is available only on Windows.";
        if (state.Log is not null)
            WatchLogBox.Text = state.Log;
        return true;
    }
}

public sealed class ThemeTile
{
    public string Id { get; }
    public string DisplayName { get; }
    public string Description { get; }
    public string Indicator { get; }
    public Brush TileBackground { get; }
    public Brush TileBorder { get; }
    public Brush NameBrush { get; }
    public Brush DescriptionBrush { get; }
    public Brush IndicatorBrush { get; }
    public Brush Swatch1 { get; }
    public Brush Swatch2 { get; }
    public Brush Swatch3 { get; }
    public Brush Swatch4 { get; }

    public ThemeTile(AppTheme theme, bool isCurrent)
    {
        Id = theme.Id;
        DisplayName = theme.DisplayName;
        Description = theme.Description;
        Indicator = isCurrent ? "● ACTIVE" : "";

        TileBackground = new SolidColorBrush(theme.Colors["BrandSurface"]);
        TileBorder = isCurrent
            ? new SolidColorBrush(theme.Colors["BrandAccentPrimary"])
            : new SolidColorBrush(theme.Colors["BrandBorder"]);
        NameBrush = new SolidColorBrush(theme.Colors["BrandTextPrimary"]);
        DescriptionBrush = new SolidColorBrush(theme.Colors["BrandTextMuted"]);
        IndicatorBrush = new SolidColorBrush(theme.Colors["BrandAccentPrimary"]);
        Swatch1 = new SolidColorBrush(theme.Colors["BrandAccentPrimary"]);
        Swatch2 = new SolidColorBrush(theme.Colors["BrandAccentGreen"]);
        Swatch3 = new SolidColorBrush(theme.Colors["BrandAccentOrange"]);
        Swatch4 = new SolidColorBrush(theme.Colors["BrandAccentRed"]);
    }
}
