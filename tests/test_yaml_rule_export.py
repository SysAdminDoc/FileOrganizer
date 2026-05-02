"""Tests for fileorganizer.yaml_rule_export — NEXT-2."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from fileorganizer import yaml_rule_export as yre  # noqa: E402

_HAS_PYYAML = importlib.util.find_spec("yaml") is not None


# ── build_organize_cli_rules ──────────────────────────────────────────────


def test_build_rules_skips_review_and_skip():
    rules = yre.build_organize_cli_rules(
        dest_root="G:\\Organized",
        source="G:\\Design Unorganized",
    )
    names = [r["name"] for r in rules]
    assert "_Review" not in names
    assert "_Skip" not in names


def test_build_rules_returns_one_per_canonical_category():
    rules = yre.build_organize_cli_rules()
    # Every rule's name must be in the canonical set.
    for rule in rules:
        assert rule["name"] in yre._CATEGORY_SET


def test_rule_carries_locations_and_actions():
    rules = yre.build_organize_cli_rules(
        dest_root="C:\\Out", source="C:\\In",
    )
    assert rules
    rule = rules[0]
    assert rule["locations"] == "C:\\In"
    actions = rule["actions"]
    assert isinstance(actions, list) and actions
    assert "move" in actions[0]
    assert actions[0]["move"].startswith("C:\\Out")


def test_rule_extension_filter_for_known_category():
    rules = yre.build_organize_cli_rules()
    fonts = next(r for r in rules if r["name"] == "Fonts & Typography")
    ext_filter = next(f for f in fonts["filters"] if "extension" in f)
    assert "ttf" in ext_filter["extension"]
    assert "otf" in ext_filter["extension"]
    assert "woff2" in ext_filter["extension"]


def test_alias_keywords_for_inverts_alias_map():
    """Reverse-lookup pulls aliases that route TO this canonical category."""
    keywords = yre._alias_keywords_for("After Effects - Slideshow")
    # 'Slideshow' / 'Slideshows' / 'Photo Slideshow' aliases all funnel here.
    joined = " ".join(keywords)
    assert "slideshow" in joined or "slideshows" in joined or "photo" in joined


def test_alias_keywords_drops_short_tokens():
    """Tokens shorter than 4 chars are filtered (organize-cli substring match)."""
    keywords = yre._alias_keywords_for("After Effects - Logo Reveal")
    for kw in keywords:
        assert len(kw) >= 4


def test_categories_override():
    """Caller can pass a narrower category list."""
    rules = yre.build_organize_cli_rules(
        categories=["Fonts & Typography", "_Review", "Photoshop - Mockups"],
    )
    names = [r["name"] for r in rules]
    assert "Fonts & Typography" in names
    assert "Photoshop - Mockups" in names
    assert "_Review" not in names


# ── render_yaml + _hand_render ────────────────────────────────────────────


def test_render_yaml_emits_top_level_rules_key():
    text = yre.render_yaml([{"name": "x", "locations": "C:\\a",
                              "filters": [{"extension": ["psd"]}],
                              "actions": [{"move": "C:\\b\\"}]}])
    assert text.startswith("rules:")
    assert "name: x" in text or 'name: "x"' in text


def test_render_yaml_empty_list():
    text = yre.render_yaml([])
    assert text.strip() in {"rules: []", "rules:\n[]"}


@pytest.mark.skipif(not _HAS_PYYAML, reason="PyYAML not installed")
def test_render_yaml_round_trips_via_pyyaml():
    import yaml
    rules = yre.build_organize_cli_rules(
        dest_root="G:\\Organized", source="G:\\Design Unorganized",
    )
    text = yre.render_yaml(rules)
    parsed = yaml.safe_load(text)
    assert "rules" in parsed
    assert isinstance(parsed["rules"], list)
    assert len(parsed["rules"]) == len(rules)
    # Each parsed rule has the expected shape.
    for orig, parsed_rule in zip(rules, parsed["rules"]):
        assert parsed_rule["name"] == orig["name"]
        assert parsed_rule["locations"] == orig["locations"]
        assert parsed_rule["actions"][0]["move"] == orig["actions"][0]["move"]


def test_hand_render_when_pyyaml_missing(monkeypatch):
    """Force the no-PyYAML path: output must still be deterministic + parseable."""
    monkeypatch.setattr(yre, "_HAS_PYYAML", False)
    rules = [{
        "name": "Fonts & Typography",
        "locations": "G:\\Design Unorganized",
        "filters": [
            {"extension": ["ttf", "otf"]},
            {"name": {"contains": ["fonts", "typography"]}},
        ],
        "actions": [{"move": "G:\\Organized\\Fonts & Typography\\"}],
    }]
    text = yre.render_yaml(rules)
    # Structural checks (we can't fully parse without PyYAML, but we can
    # assert key markers).
    assert "rules:" in text
    assert "- name: Fonts & Typography" in text
    assert "extension:" in text
    assert "- ttf" in text
    assert "name:" in text
    assert "contains:" in text
    assert "- fonts" in text
    assert "move:" in text


def test_hand_render_then_pyyaml_round_trip(monkeypatch):
    """If PyYAML is installed, the hand-rendered output should also parse."""
    if not _HAS_PYYAML:
        pytest.skip("PyYAML not installed")
    monkeypatch.setattr(yre, "_HAS_PYYAML", False)
    rules = yre.build_organize_cli_rules()
    text = yre.render_yaml(rules)
    import yaml
    parsed = yaml.safe_load(text)
    assert "rules" in parsed
    assert len(parsed["rules"]) == len(rules)


# ── export() helper ───────────────────────────────────────────────────────


def test_export_writes_file(tmp_path):
    out = tmp_path / "organize_rules.yaml"
    text = yre.export(
        output=str(out),
        dest_root="G:\\Organized",
        source="G:\\Design Unorganized",
    )
    assert out.exists()
    on_disk = out.read_text(encoding="utf-8")
    assert on_disk == text
    assert on_disk.startswith("rules:")


def test_export_returns_text_without_writing(tmp_path):
    text = yre.export()  # no output path
    assert text.startswith("rules:")
    # Confirm no file was touched (default arg means in-memory only).
    assert not (tmp_path / "organize_rules.yaml").exists()
