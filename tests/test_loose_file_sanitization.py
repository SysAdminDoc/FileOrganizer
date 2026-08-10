from __future__ import annotations

import os
import sqlite3

import fileorganizer.config as config
import organize_run as runner


def _configure_runner(monkeypatch, tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    monkeypatch.setattr(runner, "JOURNAL_FILE", str(tmp_path / "moves.db"))
    monkeypatch.setattr(runner, "LOG_FILE", str(tmp_path / "run.log"))
    monkeypatch.setattr(runner, "get_dest_root", lambda: str(destination_root))
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )
    return source_root, destination_root


def test_nested_trailing_components_are_renamed_in_path_order(monkeypatch, tmp_path):
    source_root = str(tmp_path / "source")
    source = os.path.join(source_root, "Folder ", "asset.txt ")
    renames: list[tuple[str, str]] = []
    monkeypatch.setattr(runner, "_exact_path_exists", lambda _path: False)
    monkeypatch.setattr(
        runner,
        "_rename_exact_path",
        lambda old, new: renames.append((old, new)),
    )

    sanitized, recorded = runner.sanitize_file_source_path(source, source_root)

    clean_folder = os.path.join(source_root, "Folder")
    assert sanitized == os.path.join(clean_folder, "asset.txt")
    assert recorded == renames == [
        (os.path.join(source_root, "Folder "), clean_folder),
        (os.path.join(clean_folder, "asset.txt "), os.path.join(clean_folder, "asset.txt")),
    ]


def test_trailing_name_collision_uses_existing_suffix_policy(monkeypatch, tmp_path):
    source_root = str(tmp_path / "source")
    source = os.path.join(source_root, "asset.txt ")
    occupied = {"asset.txt", "asset (1).txt"}
    monkeypatch.setattr(
        runner,
        "_exact_path_exists",
        lambda path: os.path.basename(path) in occupied,
    )
    renames: list[tuple[str, str]] = []
    monkeypatch.setattr(
        runner,
        "_rename_exact_path",
        lambda old, new: renames.append((old, new)),
    )

    sanitized, _ = runner.sanitize_file_source_path(source, source_root)

    assert sanitized == os.path.join(source_root, "asset (2).txt")
    assert renames == [(source, sanitized)]


def test_planning_and_journal_use_the_sanitized_loose_file_path(
    monkeypatch,
    tmp_path,
):
    source_root, _destination_root = _configure_runner(monkeypatch, tmp_path)
    original = source_root / "asset-raw.txt"
    sanitized = source_root / "asset.txt"
    original.write_bytes(b"payload")

    real_sanitizer = runner.sanitize_file_source_path

    def fake_sanitizer(path, root):
        if path == str(original):
            original.rename(sanitized)
            return str(sanitized), [(str(original), str(sanitized))]
        return real_sanitizer(path, root)

    monkeypatch.setattr(runner, "sanitize_file_source_path", fake_sanitizer)
    plan = runner.build_move_plan(
        [(
            {
                "name": "asset-raw",
                "clean_name": "asset-raw",
                "category": "Flyers & Print",
                "confidence": 95,
            },
            {
                "path": str(original),
                "file_ext": ".txt",
                "is_file": True,
            },
        )],
        source_override=str(source_root),
        source_mode="loose_files",
        plan_id="sanitized-loose-file",
    )

    assert plan.item_count == 1
    item = plan.items[0]
    assert item["src"] == str(sanitized)
    assert item["disk_name"] == "asset.txt"
    assert item["file_ext"] == ".txt"
    assert item["dest"].endswith("asset.txt")

    result = runner.apply_move_plan(plan, dry_run=False, verbose=False)

    assert result["moved"] == 1
    assert result["errors"] == 0
    connection = sqlite3.connect(runner.JOURNAL_FILE)
    row = connection.execute(
        "SELECT src, disk_name, status, COUNT(*) FROM moves"
    ).fetchone()
    connection.close()
    assert row == (str(sanitized), "asset.txt", "done", 1)
    assert os.path.exists(item["dest"])


def test_ordinary_loose_file_path_is_unchanged(monkeypatch, tmp_path):
    source_root, _destination_root = _configure_runner(monkeypatch, tmp_path)
    source = source_root / "ordinary.txt"
    source.write_bytes(b"ordinary")

    plan = runner.build_move_plan(
        [(
            {
                "name": "ordinary",
                "clean_name": "ordinary",
                "category": "Flyers & Print",
                "confidence": 95,
            },
            {"path": str(source), "file_ext": ".txt", "is_file": True},
        )],
        source_override=str(source_root),
        source_mode="loose_files",
    )

    assert plan.items[0]["src"] == str(source)
    assert source.exists()
