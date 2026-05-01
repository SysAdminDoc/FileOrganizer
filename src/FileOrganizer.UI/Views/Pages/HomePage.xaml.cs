using System.Collections.ObjectModel;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace FileOrganizer.UI.Views.Pages;

public sealed partial class HomePage : Page
{
    private readonly List<HomeSearchSuggestion> _allSuggestions = [];

    public ObservableCollection<HomeActionTile> Actions { get; } = [];
    public ObservableCollection<HomeClusterTile> Clusters { get; } = [];

    public HomePage()
    {
        InitializeComponent();
        SeedDashboard();
        SeedSearch();

        ActionsGrid.ItemsSource = Actions;
        ClustersGrid.ItemsSource = Clusters;
        TaskSearchBox.ItemsSource = _allSuggestions;
    }

    private void SeedDashboard()
    {
        var blue = (Brush)Application.Current.Resources["AccentBlueBrush"];
        var cyan = (Brush)Application.Current.Resources["AccentCyanBrush"];
        var green = (Brush)Application.Current.Resources["AccentGreenBrush"];
        var orange = (Brush)Application.Current.Resources["AccentOrangeBrush"];
        var yellow = (Brush)Application.Current.Resources["AccentYellowBrush"];
        var red = (Brush)Application.Current.Resources["AccentRedBrush"];
        var violet = (Brush)Application.Current.Resources["AccentVioletBrush"];
        var blueSurface = (Brush)Application.Current.Resources["SurfaceLightBrush"];
        var greenSurface = (Brush)Application.Current.Resources["SurfaceSoftBrush"];

        Actions.Add(new HomeActionTile("Smart Sort",
            "Drop a folder, get an organized library. Auto-routes every file to the right pipeline.",
            "\uE945", cyan, greenSurface, "Featured", "Try it", "smart"));
        Actions.Add(new HomeActionTile("Organize",
            "Apply AI batch classifications to disk. Preview, plan, apply, undo.",
            "\uE8B7", cyan, greenSurface, "Ready", "Open organize", "organize"));
        Actions.Add(new HomeActionTile("Files",
            "Sort any folder by file type. Pictures/JPEGs, Music/Lossless, Documents/PDFs, etc.",
            "\uE8A5", blue, blueSurface, "Ready", "Open files", "files"));
        Actions.Add(new HomeActionTile("Cleanup",
            "Empty folders, junk, broken, big, and old files — six progressive scanners.",
            "\uE74D", orange, blueSurface, "Ready", "Open cleanup", "cleanup"));
        Actions.Add(new HomeActionTile("Duplicates",
            "Byte-identical SHA-256 + BK-tree perceptual dedup with grouped results.",
            "\uE8C8", violet, blueSurface, "Ready", "Open duplicates", "duplicates"));
        Actions.Add(new HomeActionTile("Music",
            "Picard-style tagging: Chromaprint → AcoustID → MusicBrainz → mutagen.",
            "\uE8D6", violet, blueSurface, "Ready", "Open music", "music"));
        Actions.Add(new HomeActionTile("Video",
            "GuessIt filename parser, custom-format scoring, TV/Movie rename.",
            "\uE714", red, blueSurface, "Ready", "Open video", "video"));
        Actions.Add(new HomeActionTile("Books",
            "EPUB/MOBI/AZW3/PDF/CBZ metadata + optional ISBN lookup.",
            "\uE82D", yellow, greenSurface, "Ready", "Open books", "books"));
        Actions.Add(new HomeActionTile("Fonts",
            "TTF/OTF/WOFF metadata: family, style, weight, designer.",
            "\uE185", blue, blueSurface, "Ready", "Open fonts", "fonts"));
        Actions.Add(new HomeActionTile("Source Code",
            "Detect repo roots, tag primary language, regroup into Code/{lang}/{name}.",
            "\uE943", blue, blueSurface, "Ready", "Open code", "code"));
        Actions.Add(new HomeActionTile("Subtitles",
            "Auto-fetch .srt via Subliminal. Skips MKVs that already have embedded subs.",
            "\uED1E", green, greenSurface, "Ready", "Open subtitles", "subtitles"));
        Actions.Add(new HomeActionTile("Photos",
            "Read EXIF: date, camera, lens, ISO, GPS. Optional date-based folder rename.",
            "\uEB9F", green, greenSurface, "Ready", "Open photos", "photos"));
        Actions.Add(new HomeActionTile("Watch",
            "Auto-organize new files as they appear. Each watch is a (source, destination) pair.",
            "\uE7C8", red, blueSurface, "Ready", "Open watch", "watch"));
        Actions.Add(new HomeActionTile("Toolbox",
            "Power-user CLI utilities: pipeline stats, validate, asset DB, undo, audit.",
            "\uE713", orange, greenSurface, "Ready", "Open toolbox", "toolbox"));
        Actions.Add(new HomeActionTile("Settings",
            "Pick a theme (7 to choose from), set defaults, stash your AcoustID key.",
            "\uE790", cyan, greenSurface, "Ready", "Open settings", "settings"));

        Clusters.Add(new HomeClusterTile("Classify", "AI batches",
            "Run DeepSeek/GitHub Models/Ollama batches over an org_index, write batch_NNN.json.",
            "\uE950", cyan, greenSurface, "toolbox"));
        Clusters.Add(new HomeClusterTile("Apply", "Plan-and-execute",
            "Position-based apply, robocopy long-paths, error journal, retry-errors.",
            "\uE8AB", green, blueSurface, "organize"));
        Clusters.Add(new HomeClusterTile("Audit", "Asset DB & research",
            "Build SHA-256 fingerprint DB, lookup by hash, resolve _Review IDs via DeepSeek research.",
            "\uE721", orange, greenSurface, "toolbox"));
    }

    private void SeedSearch()
    {
        _allSuggestions.AddRange([
            new("Organize", "Open the organize-pipeline runner", "organize"),
            new("Apply moves", "Plan and apply classified batches to disk", "organize"),
            new("Undo last moves", "Roll back the most recent organize moves", "organize"),
            new("Sort PC files", "Open the PC file organizer", "files"),
            new("Clean empty folders", "Open cleanup scanners", "cleanup"),
            new("Find duplicates", "Open duplicate finder", "duplicates"),
            new("EXIF map", "Open photo workflows", "photos"),
            new("Watch folder", "Open watch mode", "watch"),
            new("Classify batch", "Toolbox: classify_design.py", "toolbox"),
            new("Asset DB", "Toolbox: asset_db.py", "toolbox"),
            new("Research IDs", "Toolbox: deepseek_research.py", "toolbox"),
        ]);
    }

    private void TaskSearchBox_TextChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args)
    {
        if (args.Reason != AutoSuggestionBoxTextChangeReason.UserInput)
            return;

        var query = sender.Text.Trim();
        sender.ItemsSource = string.IsNullOrWhiteSpace(query)
            ? _allSuggestions
            : _allSuggestions
                .Where(s => s.Title.Contains(query, StringComparison.OrdinalIgnoreCase)
                    || s.Subtitle.Contains(query, StringComparison.OrdinalIgnoreCase))
                .ToList();
    }

    private void TaskSearchBox_SuggestionChosen(AutoSuggestBox sender, AutoSuggestBoxSuggestionChosenEventArgs args)
    {
        if (args.SelectedItem is HomeSearchSuggestion suggestion)
            sender.Text = suggestion.Title;
    }

    private void TaskSearchBox_QuerySubmitted(AutoSuggestBox sender, AutoSuggestBoxQuerySubmittedEventArgs args)
    {
        var suggestion = args.ChosenSuggestion as HomeSearchSuggestion
            ?? _allSuggestions.FirstOrDefault(s =>
                s.Title.Equals(args.QueryText, StringComparison.OrdinalIgnoreCase))
            ?? _allSuggestions.FirstOrDefault(s =>
                s.Title.Contains(args.QueryText, StringComparison.OrdinalIgnoreCase)
                || s.Subtitle.Contains(args.QueryText, StringComparison.OrdinalIgnoreCase));

        if (suggestion is not null)
            App.RequestNavigation(suggestion.RouteKey);
    }

    private void ActionTile_Click(object sender, ItemClickEventArgs e)
    {
        if (e.ClickedItem is HomeActionTile tile)
            App.RequestNavigation(tile.RouteKey);
    }

    private void ClusterTile_Click(object sender, ItemClickEventArgs e)
    {
        if (e.ClickedItem is HomeClusterTile tile)
            App.RequestNavigation(tile.RouteKey);
    }

    private void OpenOrganize_Click(object sender, RoutedEventArgs e) =>
        App.RequestNavigation("organize");

    private void OpenCleanup_Click(object sender, RoutedEventArgs e) =>
        App.RequestNavigation("cleanup");

    private void OpenToolbox_Click(object sender, RoutedEventArgs e) =>
        App.RequestNavigation("toolbox");
}

public sealed class HomeActionTile
{
    public string Title { get; }
    public string Description { get; }
    public string Glyph { get; }
    public Brush AccentBrush { get; }
    public Brush AccentSurfaceBrush { get; }
    public string Badge { get; }
    public string ActionText { get; }
    public string RouteKey { get; }
    public Visibility BadgeVisibility => string.IsNullOrWhiteSpace(Badge) ? Visibility.Collapsed : Visibility.Visible;

    public HomeActionTile(string title, string description, string glyph, Brush accentBrush,
        Brush accentSurfaceBrush, string badge, string actionText, string routeKey)
    {
        Title = title;
        Description = description;
        Glyph = glyph;
        AccentBrush = accentBrush;
        AccentSurfaceBrush = accentSurfaceBrush;
        Badge = badge;
        ActionText = actionText;
        RouteKey = routeKey;
    }
}

public sealed class HomeClusterTile
{
    public string Title { get; set; }
    public string Subtitle { get; set; }
    public string Description { get; set; }
    public string Glyph { get; set; }
    public Brush AccentBrush { get; set; }
    public Brush AccentSurfaceBrush { get; set; }
    public string RouteKey { get; set; }

    public HomeClusterTile(string title, string subtitle, string description, string glyph,
        Brush accentBrush, Brush accentSurfaceBrush, string routeKey)
    {
        Title = title;
        Subtitle = subtitle;
        Description = description;
        Glyph = glyph;
        AccentBrush = accentBrush;
        AccentSurfaceBrush = accentSurfaceBrush;
        RouteKey = routeKey;
    }
}

public sealed class HomeSearchSuggestion
{
    public string Title { get; set; }
    public string Subtitle { get; set; }
    public string RouteKey { get; set; }

    public HomeSearchSuggestion(string title, string subtitle, string routeKey)
    {
        Title = title;
        Subtitle = subtitle;
        RouteKey = routeKey;
    }
}
