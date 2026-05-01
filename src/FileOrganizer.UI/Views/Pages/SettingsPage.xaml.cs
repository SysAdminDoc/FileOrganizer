using System.Collections.ObjectModel;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI;
using FileOrganizer.UI.Services;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class SettingsPage : Page
{
    private readonly IThemeService _theme;
    private readonly IUserSettings _settings;
    public ObservableCollection<ThemeTile> Themes { get; } = [];

    public SettingsPage()
    {
        InitializeComponent();
        _theme = App.Services.GetRequiredService<IThemeService>();
        _settings = App.Services.GetRequiredService<IUserSettings>();

        LoadThemes();
        ThemeRepeater.ItemsSource = Themes;

        ApiKeyBox.Password = _settings.AcoustIdApiKey;
        MusicPatternBox.Text = _settings.DefaultMusicRenamePattern;
        VideoPatternBox.Text = _settings.DefaultVideoRenamePattern;
        BookPatternBox.Text = _settings.DefaultBookRenamePattern;
        LangsBox.Text = _settings.DefaultSubtitleLanguages;
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
        _settings.AcoustIdApiKey = ApiKeyBox.Password ?? "";
        _settings.DefaultMusicRenamePattern = MusicPatternBox.Text ?? "";
        _settings.DefaultVideoRenamePattern = VideoPatternBox.Text ?? "";
        _settings.DefaultBookRenamePattern = BookPatternBox.Text ?? "";
        _settings.DefaultSubtitleLanguages = string.IsNullOrWhiteSpace(LangsBox.Text) ? "en" : LangsBox.Text;
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
        SaveStatusText.Text = "Defaults restored.";
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
