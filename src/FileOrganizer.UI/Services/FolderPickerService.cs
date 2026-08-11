using Microsoft.Windows.Storage.Pickers;

namespace FileOrganizer.UI.Services;

/// <summary>
/// Owns the WinAppSDK folder picker entry points used by desktop pages.
/// Supplying the host WindowId keeps picker ownership correct for unpackaged
/// WinUI windows and exposes the multi-folder picker without page-specific
/// interop boilerplate.
/// </summary>
public static class FolderPickerService
{
    public static async Task<IReadOnlyList<string>> PickMultipleAsync(
        PickerLocationId startLocation,
        string title)
    {
        var picker = CreatePicker(startLocation, title);
        var results = await picker.PickMultipleFoldersAsync();
        return results
            .Select(result => result.Path)
            .Where(path => !string.IsNullOrWhiteSpace(path) && Directory.Exists(path))
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .ToArray();
    }

    public static async Task<string?> PickSingleAsync(
        PickerLocationId startLocation,
        string title)
    {
        var picker = CreatePicker(startLocation, title);
        var result = await picker.PickSingleFolderAsync();
        return result?.Path is { Length: > 0 } path && Directory.Exists(path)
            ? path
            : null;
    }

    public static Microsoft.UI.Windowing.WindowId MainWindowId()
    {
        var hwnd = WinRT.Interop.WindowNative.GetWindowHandle(App.MainWindowHandle);
        return Microsoft.UI.Win32Interop.GetWindowIdFromWindow(hwnd);
    }

    private static FolderPicker CreatePicker(PickerLocationId startLocation, string title)
    {
        var picker = new FolderPicker(MainWindowId())
        {
            SuggestedStartLocation = startLocation,
            Title = title,
        };
        return picker;
    }
}
