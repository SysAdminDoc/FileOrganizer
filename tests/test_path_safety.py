from __future__ import annotations

import pytest

import fileorganizer.config as config
import organize_run as runner
from fileorganizer.path_safety import PathSafetyError, validate_move, validate_tree_pair


@pytest.fixture(autouse=True)
def disable_default_protected_paths_for_temp_fixtures(monkeypatch):
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )


def test_validate_move_rejects_destination_outside_approved_root(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    source = source_root / "asset"
    source.mkdir()

    with pytest.raises(PathSafetyError, match="destination escapes"):
        validate_move(
            source,
            tmp_path / "outside" / "asset",
            source_root=source_root,
            dest_root=destination_root,
        )


def test_validate_move_rejects_symlink_components(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    source = source_root / "asset"
    source.mkdir()
    link = destination_root / "linked"
    try:
        link.symlink_to(tmp_path / "outside", target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(PathSafetyError, match="(symlink|escapes)"):
        validate_move(
            source,
            link / "asset",
            source_root=source_root,
            dest_root=destination_root,
        )


def test_tampered_plan_fails_preflight_before_first_move(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    (source_root / "one").mkdir()
    (source_root / "two").mkdir()

    old_journal = runner.JOURNAL_FILE
    old_log = runner.LOG_FILE
    old_dest = runner.get_dest_root
    runner.JOURNAL_FILE = str(tmp_path / "moves.db")
    runner.LOG_FILE = str(tmp_path / "run.log")
    runner.get_dest_root = lambda: str(destination_root)
    try:
        plan = runner.build_move_plan(
            [
                (
                    {"name": "one", "clean_name": "one", "category": "Flyers & Print", "confidence": 90},
                    {"folder": str(source_root), "name": "one"},
                ),
                (
                    {"name": "two", "clean_name": "two", "category": "Flyers & Print", "confidence": 90},
                    {"folder": str(source_root), "name": "two"},
                ),
            ],
            source_mode="design",
            plan_id="tampered",
        )
        plan.items[1]["dest"] = str(tmp_path / "outside" / "two")

        with pytest.raises(PathSafetyError, match="destination escapes"):
            runner.apply_move_plan(plan, dry_run=False, verbose=False)

        assert (source_root / "one").exists()
        assert (source_root / "two").exists()
        assert not (tmp_path / "outside").exists()
    finally:
        runner.JOURNAL_FILE = old_journal
        runner.LOG_FILE = old_log
        runner.get_dest_root = old_dest


def test_build_move_plan_blocks_traversal_category_and_clean_name(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    (source_root / "category-escape").mkdir()
    (source_root / "name-escape").mkdir()

    old_dest = runner.get_dest_root
    runner.get_dest_root = lambda: str(destination_root)
    try:
        plan = runner.build_move_plan(
            [
                (
                    {"name": "category-escape", "clean_name": "valid", "category": "../Escape", "confidence": 90},
                    {"folder": str(source_root), "name": "category-escape"},
                ),
                (
                    {"name": "name-escape", "clean_name": "..", "category": "Flyers & Print", "confidence": 90},
                    {"folder": str(source_root), "name": "name-escape"},
                ),
            ],
            source_mode="design",
            plan_id="rejected-path-values",
        )
        assert plan.item_count == 0
        assert {item["reason"] for item in plan.skipped} == {"invalid_category", "invalid_clean_name"}
        assert not (tmp_path / "Escape").exists()
    finally:
        runner.get_dest_root = old_dest


def test_hardlink_self_target_never_deletes_keeper(tmp_path):
    from fileorganizer.workers import action_hardlink

    path = tmp_path / "keeper.bin"
    path.write_bytes(b"keeper")

    ok, detail = action_hardlink(str(path), str(path))

    assert not ok
    assert "same path" in detail.lower()
    assert path.read_bytes() == b"keeper"


def test_smart_and_watch_reject_overlapping_roots(tmp_path, monkeypatch):
    import smart_run
    import watch_run

    source = tmp_path / "source"
    source.mkdir()
    nested = source / "organized"
    nested.mkdir()

    monkeypatch.setattr("sys.argv", ["smart_run.py", "--root", str(source), "--dest", str(nested), "--mode", "apply"])
    assert smart_run.main() == 5

    monkeypatch.setattr("sys.argv", ["watch_run.py", "--watches", '[{"src": "' + str(source).replace('\\', '/') + '", "dest": "' + str(nested).replace('\\', '/') + '"}]'])
    assert watch_run.main() == 2


@pytest.mark.parametrize("relationship", ["equal", "child", "parent"])
def test_validate_tree_pair_rejects_all_overlapping_relationships(tmp_path, relationship):
    source = tmp_path / "source"
    source.mkdir()
    if relationship == "equal":
        destination = source
    elif relationship == "child":
        destination = source / "organized"
        destination.mkdir()
    else:
        destination = tmp_path

    with pytest.raises(PathSafetyError, match="overlap"):
        validate_tree_pair(source, destination)


def test_validate_tree_pair_rejects_reparse_root(tmp_path):
    source = tmp_path / "source"
    real_destination = tmp_path / "destination"
    source.mkdir()
    real_destination.mkdir()
    linked_destination = tmp_path / "linked-destination"
    try:
        linked_destination.symlink_to(real_destination, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")

    with pytest.raises(PathSafetyError, match="symlink|reparse"):
        validate_tree_pair(source, linked_destination)
