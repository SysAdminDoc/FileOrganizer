using Microsoft.Extensions.DependencyInjection;
using Microsoft.UI.Xaml;
using FileOrganizer.UI.Services;
using FileOrganizer.UI.Views;
using FileOrganizer.UI.Views.Pages;

namespace FileOrganizer.UI;

public partial class App : Application
{
    private static MainWindow? _mainWindow;
    private static readonly CrashLogWriter CrashLog = new(Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "FileOrganizer",
        "logs",
        "fileorganizer_crash.log"));

    public static IServiceProvider Services { get; private set; } = null!;

    public static Window MainWindowHandle => _mainWindow
        ?? throw new InvalidOperationException("Main window not registered yet.");

    public static Window? MainWindowHandleSafe => _mainWindow;

    public App()
    {
        InitializeComponent();
        ConfigureServices();
    }

    private static void ConfigureServices()
    {
        var services = new ServiceCollection();

        services.AddSingleton<IPythonRunner, PythonRunner>();
        services.AddSingleton<ICapabilityHealthService, CapabilityHealthService>();
        services.AddSingleton<ISidecarRunner, SidecarRunner>();
        services.AddSingleton<IThemeService, ThemeService>();
        services.AddSingleton<IUserSettings, UserSettings>();

        Services = services.BuildServiceProvider();
    }

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        UnhandledException += (_, e) =>
        {
            LogUnhandledException(e.Exception);
            e.Handled = false;
        };
        _mainWindow = new MainWindow();
        _mainWindow.Activate();

        // Apply the saved theme after the window's content tree exists so
        // ElementTheme propagates correctly.
        var themeSvc = Services.GetRequiredService<IThemeService>();
        themeSvc.Apply(themeSvc.GetSavedThemeId());
    }

    internal static void Register(MainWindow window) => _mainWindow = window;

    public static void RequestNavigation(string routeKey) => _mainWindow?.RequestNavigation(routeKey);

    public static void RequestPlaceholderNavigation(PlaceholderInfo info) =>
        _mainWindow?.NavigateToPlaceholder(info);

    private static void LogUnhandledException(Exception? exception)
    {
        try
        {
            CrashLog.Write(exception);
        }
        catch
        {
        }
    }
}
