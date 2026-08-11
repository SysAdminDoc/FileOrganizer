using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Animation;
using FileOrganizer.UI.Services;
using FileOrganizer.UI.Views.Pages;

namespace FileOrganizer.UI.Views;

public sealed partial class MainWindow : Window
{
    private bool _isSelectingNavigationItem;
    private bool _initialNavigationCompleted;
    private readonly AppWindow _appWindow;
    private readonly IThemeService _themeService;
    private readonly IPythonRunner _pythonRunner;
    private readonly ICapabilityHealthService _capabilityHealth;

    private readonly List<NavSearchSuggestion> _searchSuggestions =
    [
        new("Home", "Workspace overview and quick actions", "home"),
        new("Smart Sort", "Choose folders, route every file to the right pipeline", "smart"),
        new("Organize", "Apply AI batch classifications to disk and undo moves", "organize"),
        new("Files", "PC file organizer — sort by extension and type", "files"),
        new("Cleanup", "Find empty, junk, broken, big, and old files", "cleanup"),
        new("Duplicates", "Byte-identical SHA-256 + BK-tree perceptual-image dedup", "duplicates"),
        new("Music", "Picard-style audio tagging — Chromaprint + AcoustID + MusicBrainz + mutagen", "music"),
        new("Video", "GuessIt filename parser, custom-format scoring, TV/Movie rename templates", "video"),
        new("Books", "EPUB/MOBI/AZW3/PDF/CBZ metadata, ISBN scan, optional online lookup", "books"),
        new("Fonts", "TTF/OTF/WOFF metadata: family, style, weight, designer", "fonts"),
        new("Source Code", "Detect repo roots by marker files, tag primary language", "code"),
        new("Subtitles", "Subliminal: auto-fetch .srt for video files, skip embedded", "subtitles"),
        new("Photos", "EXIF, geotag map, AI event grouping, faces", "photos"),
        new("Raw Photos", "DNG/CR2/NEF/ARW/ORF/RW2 metadata, EXIF, organize by camera and date", "raw"),
        new("Comics", "CBZ/CBR/CB7/CBT archive metadata, series detection, organize by publisher and series", "comics"),
        new("Watch", "Auto-organize folders on change with tray integration", "watch"),
        new("Toolbox", "Asset DB, classifier, research, plan-and-apply utilities", "toolbox"),
    ];

    public MainWindow()
    {
        InitializeComponent();
        NavSearchBox.ItemsSource = _searchSuggestions;

        var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(this);
        var windowId = Microsoft.UI.Win32Interop.GetWindowIdFromWindow(hwnd);
        var appWindow = Microsoft.UI.Windowing.AppWindow.GetFromWindowId(windowId);
        _appWindow = appWindow;
        _themeService = App.Services.GetRequiredService<IThemeService>();
        _pythonRunner = App.Services.GetRequiredService<IPythonRunner>();
        _capabilityHealth = App.Services.GetRequiredService<ICapabilityHealthService>();
        _capabilityHealth.Changed += CapabilityHealth_Changed;
        appWindow.Resize(new Windows.Graphics.SizeInt32(1280, 820));

        var displayArea = Microsoft.UI.Windowing.DisplayArea.GetFromWindowId(windowId,
            Microsoft.UI.Windowing.DisplayAreaFallback.Primary);
        var centerX = (displayArea.WorkArea.Width - 1280) / 2;
        var centerY = (displayArea.WorkArea.Height - 820) / 2;
        appWindow.Move(new Windows.Graphics.PointInt32(centerX, centerY));

        if (appWindow.TitleBar is not null)
        {
            var titleBar = appWindow.TitleBar;
            titleBar.ExtendsContentIntoTitleBar = true;
            titleBar.PreferredHeightOption = Microsoft.UI.Windowing.TitleBarHeightOption.Tall;
        }

        ApplyTitleBarPalette(_themeService.TitleBarPalette);
        _themeService.ThemeChanged += ThemeService_ThemeChanged;
        App.Register(this);
        Activated += MainWindow_Activated;
        Closed += (_, _) =>
        {
            _themeService.ThemeChanged -= ThemeService_ThemeChanged;
            _capabilityHealth.Changed -= CapabilityHealth_Changed;
        };
    }

    private void MainWindow_Activated(object sender, WindowActivatedEventArgs args)
    {
        ApplyTitleBarPalette(_themeService.TitleBarPalette);
        if (_initialNavigationCompleted)
            return;

        _initialNavigationCompleted = true;
        RequestNavigation("home");
        _ = LoadCapabilityHealthAsync();
    }

    private async Task LoadCapabilityHealthAsync()
    {
        CapabilityExpander.Visibility = Visibility.Visible;
        var result = await _pythonRunner.RunScriptNdjsonAsync(
            "capabilities_run.py",
            ["--workflow", "all"],
            (_, _) => { });
        if (!result.Success)
            CapabilityStatusText.Text = $"Capability check unavailable — {result.ErrorMessage ?? result.Stderr}";
    }

    private void CapabilityHealth_Changed(object? sender, CapabilityHealthSnapshot snapshot)
    {
        if (!DispatcherQueue.HasThreadAccess)
        {
            DispatcherQueue.TryEnqueue(() => RenderCapabilityHealth(snapshot));
            return;
        }
        RenderCapabilityHealth(snapshot);
    }

    private void RenderCapabilityHealth(CapabilityHealthSnapshot snapshot)
    {
        CapabilityRowsList.ItemsSource = snapshot.Rows;
        CapabilityStatusText.Text =
            $"Workflow capabilities — {snapshot.Available} available · "
            + $"{snapshot.Unavailable} unavailable · {snapshot.NotChecked} online not checked";
        CapabilityExpander.Visibility = Visibility.Visible;
    }

    private void ThemeService_ThemeChanged(object? sender, AppTheme theme) =>
        ApplyTitleBarPalette(_themeService.TitleBarPalette);

    private void ApplyTitleBarPalette(TitleBarPalette palette)
    {
        if (_appWindow.TitleBar is not { } titleBar)
            return;

        titleBar.BackgroundColor = palette.Background;
        titleBar.InactiveBackgroundColor = palette.InactiveBackground;
        titleBar.ButtonBackgroundColor = palette.ButtonBackground;
        titleBar.ButtonInactiveBackgroundColor = palette.ButtonInactiveBackground;
        titleBar.ButtonForegroundColor = palette.ButtonForeground;
        titleBar.ButtonInactiveForegroundColor = palette.ButtonInactiveForeground;
        titleBar.ButtonHoverBackgroundColor = palette.ButtonHoverBackground;
        titleBar.ButtonHoverForegroundColor = palette.ButtonHoverForeground;
        titleBar.ButtonPressedBackgroundColor = palette.ButtonPressedBackground;
        titleBar.ButtonPressedForegroundColor = palette.ButtonPressedForeground;
    }

    public void RequestNavigation(string routeKey)
    {
        NavigateTo(routeKey);
        SelectMenuItem(routeKey);
    }

    public void NavigateTo(string routeKey)
    {
        Type pageType = routeKey switch
        {
            "home" => typeof(HomePage),
            "smart" => typeof(SmartSortPage),
            "organize" => typeof(OrganizePage),
            "files" => typeof(FilesPage),
            "cleanup" => typeof(CleanupPage),
            "duplicates" => typeof(DuplicatesPage),
            "music" => typeof(MusicPage),
            "video" => typeof(VideoPage),
            "books" => typeof(BooksPage),
            "fonts" => typeof(FontsPage),
            "code" => typeof(CodePage),
            "subtitles" => typeof(SubtitlesPage),
            "photos" => typeof(PhotosPage),
            "raw" => typeof(RAWPage),
            "comics" => typeof(ComicsPage),
            "watch" => typeof(WatchPage),
            "toolbox" => typeof(ToolboxPage),
            "settings" => typeof(SettingsPage),
            _ => typeof(PlaceholderPage),
        };

        object? parameter = pageType == typeof(PlaceholderPage)
            ? GetPlaceholderInfo(routeKey)
            : null;

        ContentFrame.Navigate(pageType, parameter, new EntranceNavigationTransitionInfo());
    }

    public void NavigateToPlaceholder(PlaceholderInfo info)
    {
        ContentFrame.Navigate(typeof(PlaceholderPage), info, new EntranceNavigationTransitionInfo());
    }

    private static PlaceholderInfo GetPlaceholderInfo(string routeKey) => routeKey switch
    {
        _ => new PlaceholderInfo(
            routeKey, "Module",
            "\uE713",
            "Module not available yet",
            "This route is registered but the page has not been wired."),
    };

    private void SelectMenuItem(string tag)
    {
        foreach (var item in MainNav.MenuItems)
        {
            if (item is NavigationViewItem nvi && (nvi.Tag as string) == tag)
            {
                if (ReferenceEquals(MainNav.SelectedItem, nvi))
                    return;

                try
                {
                    _isSelectingNavigationItem = true;
                    MainNav.SelectedItem = nvi;
                }
                finally
                {
                    _isSelectingNavigationItem = false;
                }

                return;
            }
        }
    }

    private void MainNav_SelectionChanged(NavigationView sender, NavigationViewSelectionChangedEventArgs args)
    {
        if (_isSelectingNavigationItem)
            return;

        if (args.IsSettingsSelected)
        {
            ContentFrame.Navigate(typeof(SettingsPage), null, new EntranceNavigationTransitionInfo());
            return;
        }

        if (args.SelectedItem is NavigationViewItem item && item.Tag is string tag)
        {
            NavigateTo(tag);
        }
    }

    private void NavSearchBox_TextChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args)
    {
        if (args.Reason != AutoSuggestionBoxTextChangeReason.UserInput)
            return;

        var query = sender.Text.Trim();
        sender.ItemsSource = string.IsNullOrWhiteSpace(query)
            ? _searchSuggestions
            : _searchSuggestions
                .Where(s => s.Title.Contains(query, StringComparison.OrdinalIgnoreCase)
                    || s.Subtitle.Contains(query, StringComparison.OrdinalIgnoreCase))
                .ToList();
    }

    private void NavSearchBox_SuggestionChosen(AutoSuggestBox sender, AutoSuggestBoxSuggestionChosenEventArgs args)
    {
        if (args.SelectedItem is NavSearchSuggestion suggestion)
            sender.Text = suggestion.Title;
    }

    private void NavSearchBox_QuerySubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args)
    {
        var suggestion = args.ChosenSuggestion as NavSearchSuggestion
            ?? _searchSuggestions.FirstOrDefault(s =>
                s.Title.Equals(args.QueryText, StringComparison.OrdinalIgnoreCase))
            ?? _searchSuggestions.FirstOrDefault(s =>
                s.Title.Contains(args.QueryText, StringComparison.OrdinalIgnoreCase)
                || s.Subtitle.Contains(args.QueryText, StringComparison.OrdinalIgnoreCase));

        if (suggestion is null)
            return;

        RequestNavigation(suggestion.RouteKey);
    }
}

public sealed class NavSearchSuggestion
{
    public string Title { get; set; }
    public string Subtitle { get; set; }
    public string RouteKey { get; set; }

    public NavSearchSuggestion(string title, string subtitle, string routeKey)
    {
        Title = title;
        Subtitle = subtitle;
        RouteKey = routeKey;
    }
}
