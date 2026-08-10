from __future__ import annotations

import os

import pytest

import fileorganizer.config as config
from fileorganizer import move_journal
from fileorganizer.safe_move import move_duplicate_files, undo_move_action


@pytest.fixture(autouse=True)
def isolated_move_journal(monkeypatch, tmp_path):
    monkeypatch.setattr(move_journal, "_JOURNAL_DB", str(tmp_path / "moves.db"))
    monkeypatch.setattr(move_journal, "_INITIALIZED_DB", None)
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )


def test_same_name_different_content_uses_suffix_and_is_undoable(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    first = source_root / "one" / "same.bin"
    second = source_root / "two" / "same.bin"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    destination_root.mkdir()
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    outcomes = move_duplicate_files(
        [str(first), str(second)],
        str(destination_root),
        source_root=str(source_root),
        action_id="different-content",
    )

    assert [outcome.status for outcome in outcomes] == ["moved", "conflict_renamed"]
    assert (destination_root / "same.bin").read_bytes() == b"first"
    assert (destination_root / "same (1).bin").read_bytes() == b"second"
    assert not first.exists()
    assert not second.exists()

    undo = undo_move_action("different-content")

    assert [outcome.status for outcome in undo] == ["undone", "undone"]
    assert first.read_bytes() == b"first"
    assert second.read_bytes() == b"second"
    assert not (destination_root / "same.bin").exists()
    assert not (destination_root / "same (1).bin").exists()
    assert {
        record["status"] for record in move_journal.get_action_moves("different-content")
    } == {"undone"}


def test_identical_destination_skips_without_deleting_source(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    first = source_root / "one" / "same.bin"
    second = source_root / "two" / "same.bin"
    first.parent.mkdir(parents=True)
    second.parent.mkdir(parents=True)
    destination_root.mkdir()
    first.write_bytes(b"identical")
    second.write_bytes(b"identical")

    outcomes = move_duplicate_files(
        [str(first), str(second)],
        str(destination_root),
        source_root=str(source_root),
        action_id="identical-content",
    )

    assert [outcome.status for outcome in outcomes] == ["moved", "skipped_identical"]
    assert not first.exists()
    assert second.read_bytes() == b"identical"
    assert (destination_root / "same.bin").read_bytes() == b"identical"
    assert len(move_journal.get_action_moves("identical-content")) == 1

    undo_move_action("identical-content")
    assert first.read_bytes() == b"identical"
    assert second.read_bytes() == b"identical"
    assert not (destination_root / "same.bin").exists()


def test_preexisting_different_destination_is_never_replaced(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    source = source_root / "same.bin"
    existing = destination_root / "same.bin"
    source.write_bytes(b"incoming")
    existing.write_bytes(b"existing")

    outcome = move_duplicate_files(
        [str(source)],
        str(destination_root),
        source_root=str(source_root),
        action_id="existing-destination",
    )[0]

    assert outcome.status == "conflict_renamed"
    assert existing.read_bytes() == b"existing"
    assert (destination_root / "same (1).bin").read_bytes() == b"incoming"


def test_undo_refuses_changed_destination(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    source = source_root / "asset.bin"
    source.write_bytes(b"original")
    outcome = move_duplicate_files(
        [str(source)],
        str(destination_root),
        source_root=str(source_root),
        action_id="changed-destination",
    )[0]
    destination = destination_root / "asset.bin"
    destination.write_bytes(b"changed after move")

    undo = undo_move_action("changed-destination")

    assert outcome.status == "moved"
    assert undo[0].status == "error"
    assert not source.exists()
    assert destination.read_bytes() == b"changed after move"
    record = move_journal.get_action_moves("changed-destination")[0]
    assert record["status"] == "moved"
    assert record["error"]


def test_source_outside_approved_root_is_reported_per_item(tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "destination"
    source_root.mkdir()
    destination_root.mkdir()
    outside = tmp_path / "outside.bin"
    outside.write_bytes(b"outside")

    outcome = move_duplicate_files(
        [str(outside)],
        str(destination_root),
        source_root=str(source_root),
    )[0]

    assert outcome.status == "error"
    assert outside.exists()
    assert not os.path.exists(move_journal._JOURNAL_DB)
