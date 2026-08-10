"""Keep user-facing shell documentation aligned with routed source state."""

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"
MAIN_WINDOW_XAML = REPO_ROOT / "src" / "FileOrganizer.UI" / "Views" / "MainWindow.xaml"
MAIN_WINDOW_CODE = MAIN_WINDOW_XAML.with_suffix(".xaml.cs")
THEME_SERVICE = REPO_ROOT / "src" / "FileOrganizer.UI" / "Services" / "ThemeService.cs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _documented_shell_pages(readme: str) -> set[str]:
    header = "| Shell page | Current role | Integration |"
    table = readme.split(header, 1)[1].split("\n\n", 1)[0]
    rows = [line for line in table.splitlines() if line.startswith("|")]
    return {row.split("|", 2)[1].strip() for row in rows[1:]}


def test_readme_feature_matrix_matches_routed_shell_pages():
    readme = _read(README_PATH)
    xaml = _read(MAIN_WINDOW_XAML)
    code = _read(MAIN_WINDOW_CODE)

    navigation_items = dict(
        re.findall(r'<NavigationViewItem Tag="([^"]+)" Content="([^"]+)"', xaml)
    )
    routed_keys = set(re.findall(r'"([^"]+)"\s*=>\s*typeof\(\w+Page\)', code))
    expected_pages = set(navigation_items.values())
    if "settings" in routed_keys:
        expected_pages.add("Settings")

    assert set(navigation_items) <= routed_keys
    assert _documented_shell_pages(readme) == expected_pages
    assert "placeholder" not in readme.lower()


def test_readme_theme_list_matches_shell_theme_service():
    readme = _read(README_PATH)
    theme_section = readme.split("### Themes", 1)[1].split("## Architecture", 1)[0]
    theme_names = set(
        re.findall(r'new AppTheme\("[^"]+", "([^"]+)"', _read(THEME_SERVICE))
    )

    assert theme_names
    assert all(f"**{name}**" in theme_section for name in theme_names)
