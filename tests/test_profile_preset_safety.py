import pytest

from fileorganizer import config
import fileorganizer.plugins as plugins
from fileorganizer.path_safety import PathSafetyError


@pytest.fixture
def isolated_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )
    profiles = tmp_path / "profiles"
    presets = tmp_path / "presets"
    profiles.mkdir()
    presets.mkdir()
    monkeypatch.setattr(plugins, "_PROFILES_DIR", str(profiles))
    monkeypatch.setattr(plugins, "_PRESETS_DIR", str(presets))
    return profiles, presets


@pytest.mark.parametrize(
    "name",
    [
        "../sentinel",
        r"..\sentinel",
        "foo/bar",
        r"foo\bar",
        r"C:\outside\sentinel",
        r"\\server\share\sentinel",
        "CON",
        "NUL.txt",
        "name.",
        "name ",
        ".",
        "..",
    ],
)
@pytest.mark.parametrize("manager, payload", [(plugins.ProfileManager, {}), (plugins.CategoryPresetManager, [])])
def test_profile_and_preset_names_cannot_escape_storage(isolated_storage, manager, payload, name):
    profiles, presets = isolated_storage
    sentinel = profiles.parent / "sentinel.json"
    sentinel.write_text("sentinel", encoding="utf-8")

    with pytest.raises(PathSafetyError):
        manager.save(name, payload)
    with pytest.raises(PathSafetyError):
        manager.load(name)
    with pytest.raises(PathSafetyError):
        manager.delete(name)

    assert sentinel.read_text(encoding="utf-8") == "sentinel"
    assert list(profiles.iterdir()) == []
    assert list(presets.iterdir()) == []


def test_valid_profile_and_preset_names_round_trip_atomically(isolated_storage):
    profiles, presets = isolated_storage
    profile = {"mode": 2, "src": "C:/Assets"}
    categories = [{"name": "Images", "extensions": ["png"]}]

    plugins.ProfileManager.save("Client Assets", profile)
    plugins.CategoryPresetManager.save("Client Assets", categories)

    assert plugins.ProfileManager.load("Client Assets") == profile
    assert plugins.CategoryPresetManager.load("Client Assets") == categories
    assert plugins.ProfileManager.list_profiles() == ["Client Assets"]
    assert plugins.CategoryPresetManager.list_presets() == ["Client Assets"]
    assert not list(profiles.glob(".fileorganizer-*.tmp"))
    assert not list(presets.glob(".fileorganizer-*.tmp"))

    plugins.ProfileManager.delete("Client Assets")
    plugins.CategoryPresetManager.delete("Client Assets")
    assert not (profiles / "Client Assets.json").exists()
    assert not (presets / "Client Assets.json").exists()


def test_listing_ignores_unsafe_existing_filenames(isolated_storage):
    profiles, presets = isolated_storage
    (profiles / "valid.json").write_text("{}", encoding="utf-8")
    (profiles / "CON.json").write_text("{}", encoding="utf-8")
    (profiles / ".json").write_text("{}", encoding="utf-8")
    (presets / "valid.json").write_text("[]", encoding="utf-8")
    (presets / "AUX.txt.json").write_text("[]", encoding="utf-8")

    assert plugins.ProfileManager.list_profiles() == ["valid"]
    assert plugins.CategoryPresetManager.list_presets() == ["valid"]
