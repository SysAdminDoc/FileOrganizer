using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media.Animation;
using FileOrganizer.UI.Views.Pages;

namespace FileOrganizer.UI.Views;

public sealed partial class MainWindow : Window
{
    private bool _isSelectingNavigationItem;

    private readonly List<NavSearchSuggestion> _searchSuggestions =
    [
        new("Home", "Workspace overview and quick actions", "home"),
        new("Organize", "Apply AI batch classifications to disk and undo moves", "organize"),
        new("Files", "PC file organizer — sort by extension and type", "files"),
        new("Cleanup", "Find empty, junk, broken, big, and old files", "cleanup"),
        new("Duplicates", "Hash-based duplicate detection with side-by-side compare", "duplicates"),
        new("Music", "Picard-style audio tagging — Chromaprint + AcoustID + MusicBrainz + mutagen", "music"),
        new("Video", "GuessIt filename parser, custom-format scoring, TV/Movie rename templates", "video"),
        new("Books", "EPUB/MOBI/AZW3/PDF/CBZ metadata, ISBN scan, optional online lookup", "books"),
        new("Photos", "EXIF, geotag map, AI event grouping, faces", "photos"),
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

            titleBar.BackgroundColor = Microsoft.UI.Colors.Transparent;
            titleBar.InactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
            titleBar.ButtonBackgroundColor = Microsoft.UI.Colors.Transparent;
            titleBar.ButtonInactiveBackgroundColor = Microsoft.UI.Colors.Transparent;
            titleBar.ButtonForegroundColor = Windows.UI.Color.FromArgb(0xff, 0xe8, 0xec, 0xf3);
            titleBar.ButtonInactiveForegroundColor = Windows.UI.Color.FromArgb(0xff, 0x6d, 0x7d, 0x96);
            titleBar.ButtonHoverBackgroundColor = Windows.UI.Color.FromArgb(0xff, 0x1f, 0x23, 0x38);
            titleBar.ButtonHoverForegroundColor = Windows.UI.Color.FromArgb(0xff, 0xe8, 0xec, 0xf3);
            titleBar.ButtonPressedBackgroundColor = Windows.UI.Color.FromArgb(0xff, 0x25, 0x2a, 0x38);
            titleBar.ButtonPressedForegroundColor = Windows.UI.Color.FromArgb(0xff, 0xe8, 0xec, 0xf3);
        }

        App.Register(this);
        Activated += MainWindow_Activated;
    }

    private void MainWindow_Activated(object sender, WindowActivatedEventArgs args)
    {
        Activated -= MainWindow_Activated;
        RequestNavigation("home");
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
            "organize" => typeof(OrganizePage),
            "cleanup" => typeof(CleanupPage),
            "music" => typeof(MusicPage),
            "video" => typeof(VideoPage),
            "books" => typeof(BooksPage),
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
        "files" => new PlaceholderInfo(
            "Files", "Sort PC files by type and extension",
            "\uE8A5",
            "PC File Organizer not wired yet",
            "Will sort any folder's files by extension or type using configurable per-category output paths. Wraps fileorganizer/files.py.",
            PoweredBy: "fileorganizer/files.py"),
        "duplicates" => new PlaceholderInfo(
            "Duplicates", "Progressive hash-based duplicate detection",
            "\uE8C8",
            "Duplicate Finder not wired yet",
            "Size > prefix hash > suffix hash > full SHA-256, plus perceptual image hashing for near-duplicate photos. Wraps fileorganizer/duplicates.py.",
            PoweredBy: "fileorganizer/duplicates.py"),
        "photos" => new PlaceholderInfo(
            "Photos", "EXIF, geotag map, and AI event grouping",
            "\uEB9F",
            "Photo workflows not wired yet",
            "EXIF metadata, Leaflet geotag map, AI event clustering, optional face detection, thumbnail grid. Wraps fileorganizer/photos.py.",
            PoweredBy: "fileorganizer/photos.py"),
        "watch" => new PlaceholderInfo(
            "Watch", "Auto-organize folders on change",
            "\uE7C8",
            "Watch mode not wired yet",
            "Monitor folders, auto-organize new files, system tray, watch history log. Wraps the watch worker in fileorganizer/workers.py.",
            PoweredBy: "fileorganizer/workers.py"),
        "toolbox" => new PlaceholderInfo(
            "Toolbox", "Specialized organize-pipeline utilities",
            "\uE713",
            "Toolbox tile grid not wired yet",
            "Asset DB build/lookup/export, classify_design batches, deepseek_research, fix_phantom_categories, validate, plan-and-apply, undo. Wraps the top-level *.py runners in the repo root.",
            PoweredBy: "asset_db.py · classify_design.py · organize_run.py"),
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
            // Settings window not wired yet — fall through to placeholder route.
            ContentFrame.Navigate(typeof(PlaceholderPage), new PlaceholderInfo(
                "Settings", "Preferences, themes, AI providers",
                "\uE713",
                "Settings not wired yet",
                "Theme picker, AI provider config (DeepSeek/GitHub Models/Ollama), watch folder list, protected paths."), new EntranceNavigationTransitionInfo());
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
