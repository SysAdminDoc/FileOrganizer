using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Media;
using Windows.Storage;
using Windows.UI;

namespace FileOrganizer.UI.Services;

public sealed record AppTheme(
    string Id,
    string DisplayName,
    string Description,
    bool IsLight,
    Dictionary<string, Color> Colors);

public interface IThemeService
{
    IReadOnlyList<AppTheme> AvailableThemes { get; }
    AppTheme CurrentTheme { get; }
    void Apply(string themeId);
    string GetSavedThemeId();
}

public sealed class ThemeService : IThemeService
{
    private const string SettingsKey = "ThemeId";

    public IReadOnlyList<AppTheme> AvailableThemes { get; }
    public AppTheme CurrentTheme { get; private set; }

    public ThemeService()
    {
        AvailableThemes = BuildThemes();
        CurrentTheme = AvailableThemes[0];
    }

    public string GetSavedThemeId()
    {
        try
        {
            return ApplicationData.Current.LocalSettings.Values.TryGetValue(SettingsKey, out var v)
                && v is string s ? s : "steam-dark";
        }
        catch
        {
            return "steam-dark";
        }
    }

    public void Apply(string themeId)
    {
        var theme = AvailableThemes.FirstOrDefault(t => t.Id == themeId) ?? AvailableThemes[0];
        CurrentTheme = theme;

        var resources = Application.Current.Resources;
        foreach (var (key, color) in theme.Colors)
        {
            // The brushes reference these by key; updating them at runtime
            // changes Color but not the brush identity, so all bindings refresh.
            if (resources.TryGetValue(key, out var existing))
            {
                if (existing is SolidColorBrush brush)
                {
                    brush.Color = color;
                }
                else if (existing is Color)
                {
                    resources[key] = color;
                }
            }
            else
            {
                resources[key] = color;
            }
        }

        // Update gradient stops by re-creating the gradient brushes.
        UpdateGradient(resources, "HeroGradientBrush", theme,
            ("hero1", 0.0), ("hero2", 0.45), ("hero3", 1.0));
        UpdateGradient(resources, "AiGradientBrush", theme,
            ("ai1", 0.0), ("ai2", 0.55), ("ai3", 1.0));

        // Pick the right ElementTheme (Dark / Light) so WinUI built-ins follow.
        if (App.MainWindowHandleSafe?.Content is FrameworkElement root)
            root.RequestedTheme = theme.IsLight ? ElementTheme.Light : ElementTheme.Dark;

        try
        {
            ApplicationData.Current.LocalSettings.Values[SettingsKey] = themeId;
        }
        catch { }
    }

    private static void UpdateGradient(ResourceDictionary res, string brushKey,
        AppTheme theme, params (string colorKey, double offset)[] stops)
    {
        if (!res.TryGetValue(brushKey, out var existing) || existing is not LinearGradientBrush)
            return;

        var brush = (LinearGradientBrush)existing;
        brush.GradientStops.Clear();
        foreach (var (k, off) in stops)
        {
            if (theme.Colors.TryGetValue(k, out var c))
                brush.GradientStops.Add(new GradientStop { Color = c, Offset = off });
        }
    }

    private static IReadOnlyList<AppTheme> BuildThemes()
    {
        return
        [
            new AppTheme("steam-dark", "Steam Dark",
                "Deep blue-black with cyan accents. The default.",
                IsLight: false,
                new()
                {
                    ["BrandBackground"] = C("#0f1117"),
                    ["BrandSurface"] = C("#1c1f2a"),
                    ["BrandSurfaceMuted"] = C("#15181f"),
                    ["BrandSurfaceLight"] = C("#1f2338"),
                    ["BrandSurfaceSoft"] = C("#162a20"),
                    ["BrandSurfaceWarm"] = C("#1e160a"),
                    ["BrandSurfaceDanger"] = C("#200d0d"),
                    ["BrandSurfaceInfo"] = C("#0c1629"),
                    ["BrandBorder"] = C("#252a38"),
                    ["BrandBorderStrong"] = C("#333a52"),
                    ["BrandDivider"] = C("#1a1e2b"),
                    ["BrandAccentPrimary"] = C("#22d3ee"),
                    ["BrandAccentBlue"] = C("#60a5fa"),
                    ["BrandAccentCyan"] = C("#22d3ee"),
                    ["BrandAccentGreen"] = C("#34d399"),
                    ["BrandAccentOrange"] = C("#fb923c"),
                    ["BrandAccentYellow"] = C("#fbbf24"),
                    ["BrandAccentRed"] = C("#f87171"),
                    ["BrandAccentViolet"] = C("#a78bfa"),
                    ["BrandTextPrimary"] = C("#e8ecf3"),
                    ["BrandTextSecondary"] = C("#94a3b8"),
                    ["BrandTextMuted"] = C("#6d7d96"),
                    ["BrandTextSubtle"] = C("#4a5568"),
                    ["BrandTextInverse"] = C("#0f172a"),
                    ["hero1"] = C("#0f2030"), ["hero2"] = C("#0f1520"), ["hero3"] = C("#0e201c"),
                    ["ai1"] = C("#0c1c2a"), ["ai2"] = C("#101728"), ["ai3"] = C("#131922"),
                }),

            new AppTheme("catppuccin-mocha", "Catppuccin Mocha",
                "Warm purple-blue palette, the cult favorite among devs.",
                IsLight: false,
                new()
                {
                    ["BrandBackground"] = C("#1e1e2e"),
                    ["BrandSurface"] = C("#313244"),
                    ["BrandSurfaceMuted"] = C("#181825"),
                    ["BrandSurfaceLight"] = C("#45475a"),
                    ["BrandSurfaceSoft"] = C("#1f2733"),
                    ["BrandSurfaceWarm"] = C("#332220"),
                    ["BrandSurfaceDanger"] = C("#3a1f25"),
                    ["BrandSurfaceInfo"] = C("#1f2540"),
                    ["BrandBorder"] = C("#45475a"),
                    ["BrandBorderStrong"] = C("#585b70"),
                    ["BrandDivider"] = C("#313244"),
                    ["BrandAccentPrimary"] = C("#cba6f7"),
                    ["BrandAccentBlue"] = C("#89b4fa"),
                    ["BrandAccentCyan"] = C("#94e2d5"),
                    ["BrandAccentGreen"] = C("#a6e3a1"),
                    ["BrandAccentOrange"] = C("#fab387"),
                    ["BrandAccentYellow"] = C("#f9e2af"),
                    ["BrandAccentRed"] = C("#f38ba8"),
                    ["BrandAccentViolet"] = C("#cba6f7"),
                    ["BrandTextPrimary"] = C("#cdd6f4"),
                    ["BrandTextSecondary"] = C("#bac2de"),
                    ["BrandTextMuted"] = C("#a6adc8"),
                    ["BrandTextSubtle"] = C("#7f849c"),
                    ["BrandTextInverse"] = C("#1e1e2e"),
                    ["hero1"] = C("#2a2440"), ["hero2"] = C("#1e1e2e"), ["hero3"] = C("#1f2733"),
                    ["ai1"] = C("#1f2540"), ["ai2"] = C("#1e1e2e"), ["ai3"] = C("#181825"),
                }),

            new AppTheme("oled-black", "OLED Black",
                "True black for OLED displays. Maximum contrast.",
                IsLight: false,
                new()
                {
                    ["BrandBackground"] = C("#000000"),
                    ["BrandSurface"] = C("#0a0a0a"),
                    ["BrandSurfaceMuted"] = C("#050505"),
                    ["BrandSurfaceLight"] = C("#141414"),
                    ["BrandSurfaceSoft"] = C("#0a1410"),
                    ["BrandSurfaceWarm"] = C("#140a05"),
                    ["BrandSurfaceDanger"] = C("#1a0505"),
                    ["BrandSurfaceInfo"] = C("#050a14"),
                    ["BrandBorder"] = C("#1a1a1a"),
                    ["BrandBorderStrong"] = C("#2a2a2a"),
                    ["BrandDivider"] = C("#0f0f0f"),
                    ["BrandAccentPrimary"] = C("#00d4ff"),
                    ["BrandAccentBlue"] = C("#3b82f6"),
                    ["BrandAccentCyan"] = C("#00d4ff"),
                    ["BrandAccentGreen"] = C("#00ff88"),
                    ["BrandAccentOrange"] = C("#ff8c00"),
                    ["BrandAccentYellow"] = C("#ffd700"),
                    ["BrandAccentRed"] = C("#ff3366"),
                    ["BrandAccentViolet"] = C("#b366ff"),
                    ["BrandTextPrimary"] = C("#ffffff"),
                    ["BrandTextSecondary"] = C("#bbbbbb"),
                    ["BrandTextMuted"] = C("#777777"),
                    ["BrandTextSubtle"] = C("#444444"),
                    ["BrandTextInverse"] = C("#000000"),
                    ["hero1"] = C("#001122"), ["hero2"] = C("#000000"), ["hero3"] = C("#001a14"),
                    ["ai1"] = C("#001122"), ["ai2"] = C("#000000"), ["ai3"] = C("#0a0a0a"),
                }),

            new AppTheme("github-dark", "GitHub Dark",
                "GitHub's dark mode colors — familiar to most devs.",
                IsLight: false,
                new()
                {
                    ["BrandBackground"] = C("#0d1117"),
                    ["BrandSurface"] = C("#161b22"),
                    ["BrandSurfaceMuted"] = C("#0d1117"),
                    ["BrandSurfaceLight"] = C("#21262d"),
                    ["BrandSurfaceSoft"] = C("#0e2018"),
                    ["BrandSurfaceWarm"] = C("#1f1409"),
                    ["BrandSurfaceDanger"] = C("#290e15"),
                    ["BrandSurfaceInfo"] = C("#0c1a30"),
                    ["BrandBorder"] = C("#30363d"),
                    ["BrandBorderStrong"] = C("#484f58"),
                    ["BrandDivider"] = C("#21262d"),
                    ["BrandAccentPrimary"] = C("#58a6ff"),
                    ["BrandAccentBlue"] = C("#58a6ff"),
                    ["BrandAccentCyan"] = C("#39d0d8"),
                    ["BrandAccentGreen"] = C("#3fb950"),
                    ["BrandAccentOrange"] = C("#f0883e"),
                    ["BrandAccentYellow"] = C("#d29922"),
                    ["BrandAccentRed"] = C("#f85149"),
                    ["BrandAccentViolet"] = C("#bc8cff"),
                    ["BrandTextPrimary"] = C("#f0f6fc"),
                    ["BrandTextSecondary"] = C("#c9d1d9"),
                    ["BrandTextMuted"] = C("#8b949e"),
                    ["BrandTextSubtle"] = C("#6e7681"),
                    ["BrandTextInverse"] = C("#0d1117"),
                    ["hero1"] = C("#0c2a4d"), ["hero2"] = C("#0d1117"), ["hero3"] = C("#0a1f1a"),
                    ["ai1"] = C("#0c1a30"), ["ai2"] = C("#0d1117"), ["ai3"] = C("#161b22"),
                }),

            new AppTheme("nord", "Nord",
                "Arctic blue-gray palette. Calm and easy on the eyes.",
                IsLight: false,
                new()
                {
                    ["BrandBackground"] = C("#2e3440"),
                    ["BrandSurface"] = C("#3b4252"),
                    ["BrandSurfaceMuted"] = C("#292e39"),
                    ["BrandSurfaceLight"] = C("#434c5e"),
                    ["BrandSurfaceSoft"] = C("#2e3a40"),
                    ["BrandSurfaceWarm"] = C("#3d342a"),
                    ["BrandSurfaceDanger"] = C("#3b2a30"),
                    ["BrandSurfaceInfo"] = C("#2e3a4d"),
                    ["BrandBorder"] = C("#434c5e"),
                    ["BrandBorderStrong"] = C("#4c566a"),
                    ["BrandDivider"] = C("#3b4252"),
                    ["BrandAccentPrimary"] = C("#88c0d0"),
                    ["BrandAccentBlue"] = C("#81a1c1"),
                    ["BrandAccentCyan"] = C("#8fbcbb"),
                    ["BrandAccentGreen"] = C("#a3be8c"),
                    ["BrandAccentOrange"] = C("#d08770"),
                    ["BrandAccentYellow"] = C("#ebcb8b"),
                    ["BrandAccentRed"] = C("#bf616a"),
                    ["BrandAccentViolet"] = C("#b48ead"),
                    ["BrandTextPrimary"] = C("#eceff4"),
                    ["BrandTextSecondary"] = C("#d8dee9"),
                    ["BrandTextMuted"] = C("#c0c5cf"),
                    ["BrandTextSubtle"] = C("#7b88a1"),
                    ["BrandTextInverse"] = C("#2e3440"),
                    ["hero1"] = C("#3b4a5e"), ["hero2"] = C("#2e3440"), ["hero3"] = C("#2e3a40"),
                    ["ai1"] = C("#2e3a4d"), ["ai2"] = C("#2e3440"), ["ai3"] = C("#292e39"),
                }),

            new AppTheme("dracula", "Dracula",
                "Classic purple-accented dark theme. Never goes out of style.",
                IsLight: false,
                new()
                {
                    ["BrandBackground"] = C("#282a36"),
                    ["BrandSurface"] = C("#44475a"),
                    ["BrandSurfaceMuted"] = C("#21222c"),
                    ["BrandSurfaceLight"] = C("#4d4f6c"),
                    ["BrandSurfaceSoft"] = C("#2a3a30"),
                    ["BrandSurfaceWarm"] = C("#3a2820"),
                    ["BrandSurfaceDanger"] = C("#3a1f25"),
                    ["BrandSurfaceInfo"] = C("#22324d"),
                    ["BrandBorder"] = C("#44475a"),
                    ["BrandBorderStrong"] = C("#6272a4"),
                    ["BrandDivider"] = C("#383a4a"),
                    ["BrandAccentPrimary"] = C("#bd93f9"),
                    ["BrandAccentBlue"] = C("#8be9fd"),
                    ["BrandAccentCyan"] = C("#8be9fd"),
                    ["BrandAccentGreen"] = C("#50fa7b"),
                    ["BrandAccentOrange"] = C("#ffb86c"),
                    ["BrandAccentYellow"] = C("#f1fa8c"),
                    ["BrandAccentRed"] = C("#ff5555"),
                    ["BrandAccentViolet"] = C("#ff79c6"),
                    ["BrandTextPrimary"] = C("#f8f8f2"),
                    ["BrandTextSecondary"] = C("#cfcfc2"),
                    ["BrandTextMuted"] = C("#9b9bab"),
                    ["BrandTextSubtle"] = C("#6272a4"),
                    ["BrandTextInverse"] = C("#282a36"),
                    ["hero1"] = C("#3a2c52"), ["hero2"] = C("#282a36"), ["hero3"] = C("#2a3a30"),
                    ["ai1"] = C("#22324d"), ["ai2"] = C("#282a36"), ["ai3"] = C("#21222c"),
                }),

            new AppTheme("light", "Light",
                "Clean white background. For sunny rooms and screenshots.",
                IsLight: true,
                new()
                {
                    ["BrandBackground"] = C("#f6f8fa"),
                    ["BrandSurface"] = C("#ffffff"),
                    ["BrandSurfaceMuted"] = C("#f0f3f6"),
                    ["BrandSurfaceLight"] = C("#e7ecf1"),
                    ["BrandSurfaceSoft"] = C("#e6f4ec"),
                    ["BrandSurfaceWarm"] = C("#fdf6e3"),
                    ["BrandSurfaceDanger"] = C("#fde2e6"),
                    ["BrandSurfaceInfo"] = C("#e0eefe"),
                    ["BrandBorder"] = C("#d0d7de"),
                    ["BrandBorderStrong"] = C("#afb8c1"),
                    ["BrandDivider"] = C("#eaeef2"),
                    ["BrandAccentPrimary"] = C("#0969da"),
                    ["BrandAccentBlue"] = C("#0969da"),
                    ["BrandAccentCyan"] = C("#0891b2"),
                    ["BrandAccentGreen"] = C("#1a7f37"),
                    ["BrandAccentOrange"] = C("#bc4c00"),
                    ["BrandAccentYellow"] = C("#9a6700"),
                    ["BrandAccentRed"] = C("#cf222e"),
                    ["BrandAccentViolet"] = C("#8250df"),
                    ["BrandTextPrimary"] = C("#1f2328"),
                    ["BrandTextSecondary"] = C("#424a53"),
                    ["BrandTextMuted"] = C("#656d76"),
                    ["BrandTextSubtle"] = C("#878f99"),
                    ["BrandTextInverse"] = C("#ffffff"),
                    ["hero1"] = C("#dde7f7"), ["hero2"] = C("#f0f5fb"), ["hero3"] = C("#e8f1ec"),
                    ["ai1"] = C("#e0eefe"), ["ai2"] = C("#f0f5fb"), ["ai3"] = C("#f6f8fa"),
                }),
        ];
    }

    private static Color C(string hex)
    {
        // #rrggbb -> Color (alpha = 0xFF)
        var s = hex.TrimStart('#');
        return Color.FromArgb(0xFF,
            Convert.ToByte(s[..2], 16),
            Convert.ToByte(s.Substring(2, 2), 16),
            Convert.ToByte(s.Substring(4, 2), 16));
    }
}
