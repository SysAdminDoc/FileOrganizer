namespace FileOrganizer.UI.Services;

public static class WatchPathValidator
{
    public static bool TryValidate(
        string source,
        string destination,
        out string normalizedSource,
        out string normalizedDestination,
        out string error)
    {
        normalizedSource = string.Empty;
        normalizedDestination = string.Empty;
        error = string.Empty;

        if (string.IsNullOrWhiteSpace(source) || !Directory.Exists(source))
        {
            error = "Source must be an existing folder.";
            return false;
        }
        if (string.IsNullOrWhiteSpace(destination) || File.Exists(destination))
        {
            error = "Destination must be a folder path.";
            return false;
        }

        try
        {
            normalizedSource = NormalizeRoot(source);
            normalizedDestination = NormalizeRoot(destination);
        }
        catch (Exception ex) when (ex is ArgumentException or IOException or NotSupportedException)
        {
            error = $"Watch paths are invalid: {ex.Message}";
            return false;
        }

        if (IsWithin(normalizedDestination, normalizedSource)
            || IsWithin(normalizedSource, normalizedDestination))
        {
            error = "Source and destination folders cannot overlap.";
            return false;
        }
        if (HasReparseComponent(normalizedSource) || HasReparseComponent(normalizedDestination))
        {
            error = "Source and destination cannot contain a junction or symbolic link.";
            return false;
        }
        return true;
    }

    private static string NormalizeRoot(string path)
    {
        var full = Path.GetFullPath(path);
        var root = Path.GetPathRoot(full) ?? string.Empty;
        if (full.Length > root.Length)
            full = full.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        return full;
    }

    private static bool IsWithin(string child, string root)
    {
        var relative = Path.GetRelativePath(root, child);
        return relative == "."
            || (!relative.Equals("..", StringComparison.Ordinal)
                && !relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
                && !relative.StartsWith("../", StringComparison.Ordinal)
                && !Path.IsPathRooted(relative));
    }

    private static bool HasReparseComponent(string path)
    {
        DirectoryInfo? current = new(path);
        while (current is not null)
        {
            try
            {
                if ((current.Attributes & FileAttributes.ReparsePoint) != 0)
                    return true;
            }
            catch (FileNotFoundException)
            {
                // A new destination leaf is allowed; inspect its parents.
            }
            catch (DirectoryNotFoundException)
            {
                // A new destination leaf is allowed; inspect its parents.
            }
            catch (IOException)
            {
                return true;
            }
            catch (UnauthorizedAccessException)
            {
                return true;
            }
            current = current.Parent;
        }
        return false;
    }
}
