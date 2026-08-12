import json

from fileorganizer import keyboard_shortcuts


def test_shortcuts_load_defaults_when_file_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(keyboard_shortcuts, "SHORTCUTS_FILE", tmp_path / "shortcuts.json")

    values = keyboard_shortcuts.load_shortcuts()

    assert values == {
        key: spec["default"] for key, spec in keyboard_shortcuts.DEFAULT_SHORTCUTS.items()
    }


def test_shortcuts_round_trip_normalizes_known_values_and_ignores_unknown(tmp_path, monkeypatch):
    path = tmp_path / "keyboard_shortcuts.json"
    monkeypatch.setattr(keyboard_shortcuts, "SHORTCUTS_FILE", path)

    saved = keyboard_shortcuts.save_shortcuts({
        "open_source": " Ctrl+Shift+O ",
        "scan": "",
        "unknown": "Ctrl+Alt+X",
    })
    loaded = keyboard_shortcuts.load_shortcuts()

    assert saved["open_source"] == "Ctrl+Shift+O"
    assert saved["scan"] == ""
    assert loaded == saved
    assert "unknown" not in json.loads(path.read_text(encoding="utf-8"))
    assert not path.with_name(".keyboard_shortcuts.json.tmp").exists()


def test_shortcuts_reject_malformed_values_without_breaking_defaults(monkeypatch, tmp_path):
    path = tmp_path / "keyboard_shortcuts.json"
    path.write_text(
        '{"open_source": "Ctrl+Ctrl+O", "scan": "F99", "apply": "Ctrl+Shift+A"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(keyboard_shortcuts, "SHORTCUTS_FILE", path)

    values = keyboard_shortcuts.load_shortcuts()

    assert values["open_source"] == keyboard_shortcuts.DEFAULT_SHORTCUTS["open_source"]["default"]
    assert values["scan"] == keyboard_shortcuts.DEFAULT_SHORTCUTS["scan"]["default"]
    assert values["apply"] == "Ctrl+Shift+A"


def test_normalize_shortcut_supports_named_keys_and_empty_disable_value():
    assert keyboard_shortcuts.normalize_shortcut("Alt+PageDown") == "Alt+PageDown"
    assert keyboard_shortcuts.normalize_shortcut("F12") == "F12"
    assert keyboard_shortcuts.normalize_shortcut("") == ""
    assert keyboard_shortcuts.normalize_shortcut("Ctrl+NotAKey", "F5") == "F5"
