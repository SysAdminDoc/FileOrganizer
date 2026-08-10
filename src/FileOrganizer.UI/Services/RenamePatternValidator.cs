using System.Text.RegularExpressions;

namespace FileOrganizer.UI.Services;

public static class RenamePatternValidator
{
    private static readonly HashSet<string> AllowedFields = new(StringComparer.Ordinal)
    {
        "albumartist", "year", "album", "disc", "track", "title", "ext",
        "author", "series", "series_index"
    };

    private static readonly Regex Token = new(
        @"\{(?<field>[A-Za-z_][A-Za-z0-9_]*)(?::(?<format>[^{}]*))?\}",
        RegexOptions.CultureInvariant);

    private static readonly Regex FormatSpec = new(
        @"^[<>=^+\- 0#]*\d*(?:\.\d+)?[bcdeEfFgGnosxX%]*$",
        RegexOptions.CultureInvariant);

    private static readonly Regex WindowsDrive = new(
        @"^[A-Za-z]:", RegexOptions.CultureInvariant);

    public static bool TryValidate(string? pattern, out string error)
    {
        error = string.Empty;
        if (string.IsNullOrWhiteSpace(pattern))
            return true;
        if (pattern.Length > 1024)
        {
            error = "Rename pattern is too long.";
            return false;
        }
        if (pattern.Any(char.IsControl))
        {
            error = "Rename pattern contains a control character.";
            return false;
        }
        if (pattern[0] is '/' or '\\'
            || WindowsDrive.IsMatch(pattern))
        {
            error = "Rename pattern must be relative to its destination root.";
            return false;
        }

        var scrubbed = Token.Replace(pattern, match =>
        {
            var field = match.Groups["field"].Value;
            var format = match.Groups["format"].Value;
            if (!AllowedFields.Contains(field))
            {
                error = $"Rename field '{field}' is not supported.";
                return "__invalid_field__";
            }
            if (!string.IsNullOrEmpty(format) && !FormatSpec.IsMatch(format))
            {
                error = $"Rename format for '{field}' is not supported.";
                return "__invalid_format__";
            }
            return "__field__";
        });

        if (!string.IsNullOrEmpty(error))
            return false;
        if (scrubbed.Contains('{') || scrubbed.Contains('}'))
        {
            error = "Rename pattern contains an unmatched brace.";
            return false;
        }
        if (scrubbed.IndexOfAny(new[] { '<', '>', ':', '"', '|', '?', '*' }) >= 0)
        {
            error = "Rename pattern contains an invalid filename character.";
            return false;
        }

        var components = Regex.Split(scrubbed, @"[\\/]");
        if (components.Any(string.IsNullOrEmpty))
        {
            error = "Rename pattern contains an empty path component.";
            return false;
        }
        foreach (var component in components)
        {
            if (component is "." or "..")
            {
                error = "Rename pattern cannot contain '.' or '..' components.";
                return false;
            }
            if (component.Length > 0
                && (component[^1] is '.' or ' '))
            {
                error = "Rename pattern cannot end a component with a dot or space.";
                return false;
            }
            var stem = component.TrimEnd('.', ' ').Split('.')[0].ToUpperInvariant();
            if (stem is "CON" or "PRN" or "AUX" or "NUL"
                || Regex.IsMatch(stem, @"^(COM|LPT)[1-9]$", RegexOptions.CultureInvariant))
            {
                error = "Rename pattern uses a reserved Windows name.";
                return false;
            }
        }
        return true;
    }
}
