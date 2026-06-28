import re
import xml.etree.ElementTree as ET
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CORE_VERSION = "8.5.17"
SHELL_VERSION = "0.6.0"


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _read_optional(path: str) -> str | None:
    target = REPO_ROOT / path
    return target.read_text(encoding="utf-8") if target.exists() else None


def test_release_metadata_versions_are_aligned():
    readme = _read("README.md")
    security = _read_optional("SECURITY.md")
    changelog = _read_optional("CHANGELOG.md")
    home_page = _read("src/FileOrganizer.UI/Views/Pages/HomePage.xaml")
    props_text = _read("src/Directory.Build.props")
    manifest = ET.parse(REPO_ROOT / "src/FileOrganizer.UI/app.manifest")

    props = {match.group(1): match.group(2) for match in re.finditer(r"<([^/>]+)>([^<]+)</\1>", props_text)}
    assembly_identity = manifest.getroot().find("{urn:schemas-microsoft-com:asm.v1}assemblyIdentity")

    assert f"FileOrganizer.UI%20v{SHELL_VERSION}" in readme
    assert f"Python%20v{CORE_VERSION}" in readme
    if security is not None:
        assert f"Python core v{CORE_VERSION}" in security
        assert f"FileOrganizer.UI v{SHELL_VERSION}" in security
    if changelog is not None:
        assert f"## [v{CORE_VERSION}]" in changelog
    assert f"FileOrganizer.UI v{SHELL_VERSION}" in home_page
    assert props["Version"] == SHELL_VERSION
    assert props["PackageVersion"] == SHELL_VERSION
    assert props["AssemblyVersion"] == f"{SHELL_VERSION}.0"
    assert props["FileVersion"] == f"{SHELL_VERSION}.0"
    assert props["InformationalVersion"] == f"{SHELL_VERSION}+core.{CORE_VERSION}"
    assert assembly_identity is not None
    assert assembly_identity.attrib["version"] == f"{SHELL_VERSION}.0"
