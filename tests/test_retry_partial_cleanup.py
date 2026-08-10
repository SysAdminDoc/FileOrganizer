from __future__ import annotations

import json
import os

import pytest

import fileorganizer.config as config
import organize_run as runner


@pytest.fixture
def retry_environment(monkeypatch, tmp_path):
    source_root = tmp_path / "source"
    destination_root = tmp_path / "organized"
    source_root.mkdir()
    destination_root.mkdir()
    error_file = tmp_path / "retry-errors.json"
    monkeypatch.setattr(runner, "JOURNAL_FILE", str(tmp_path / "moves.db"))
    monkeypatch.setattr(runner, "LOG_FILE", str(tmp_path / "run.log"))
    monkeypatch.setattr(runner, "ERRORS_FILE", str(tmp_path / "legacy-errors.json"))
    monkeypatch.setattr(runner, "errors_file", lambda _mode: str(error_file))
    monkeypatch.setattr(runner, "get_dest_root", lambda: str(destination_root))
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )
    return source_root, destination_root, error_file


def _retry_record(source, destination, source_root, destination_root, **values):
    record = {
        "disk_name": os.path.basename(source),
        "src": str(source),
        "dest": str(destination),
        "category": "Flyers & Print",
        "clean_name": "Recovered Asset",
        "confidence": 95,
        "error": "copy interrupted",
        "partial_dest_exists": True,
        "partial_dest_signature": runner._partial_destination_signature(str(destination)),
        "source_root": str(source_root),
        "dest_root": str(destination_root),
        "source_signature": {},
        "is_file_item": False,
        "file_ext": "",
    }
    record.update(values)
    return record


def _write_errors(error_file, records):
    error_file.write_text(json.dumps(records), encoding="utf-8")


def test_failed_apply_records_partial_identity_and_file_shape(
    retry_environment,
    monkeypatch,
):
    source_root, _destination_root, error_file = retry_environment
    source = source_root / "source.bin"
    source.write_bytes(b"complete payload")
    plan = runner.build_move_plan(
        [(
            {
                "name": "source",
                "clean_name": "source",
                "category": "Flyers & Print",
                "confidence": 95,
            },
            {"path": str(source), "file_ext": ".bin", "is_file": True},
        )],
        source_override=str(source_root),
        source_mode="loose_files",
    )

    def fail_after_partial(item, _plan):
        os.makedirs(os.path.dirname(item["dest"]), exist_ok=True)
        with open(item["dest"], "wb") as partial:
            partial.write(b"complete")
        raise OSError("simulated interrupted copy")

    monkeypatch.setattr(runner, "_move_plan_item", fail_after_partial)

    result = runner.apply_move_plan(plan, dry_run=False, verbose=False)

    assert result["errors"] == 1
    record = json.loads(error_file.read_text(encoding="utf-8"))[0]
    assert record["partial_dest_exists"] is True
    assert record["partial_dest_signature"]["kind"] == "file"
    assert record["partial_dest_signature"]["cleanup_safe"] is True
    assert record["is_file_item"] is True
    assert record["file_ext"] == ".bin"


def test_retry_removes_verified_partial_file_and_moves_source(retry_environment):
    source_root, destination_root, error_file = retry_environment
    source = source_root / "source.bin"
    source.write_bytes(b"complete payload")
    destination = destination_root / "Flyers & Print" / "Recovered Asset.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"complete")
    record = _retry_record(
        source,
        destination,
        source_root,
        destination_root,
        is_file_item=True,
        file_ext=".bin",
    )
    _write_errors(error_file, [record])

    runner.retry_errors("loose_files")

    assert not error_file.exists()
    assert not source.exists()
    assert destination.read_bytes() == b"complete payload"


def test_retry_removes_verified_partial_directory_and_moves_source(retry_environment):
    source_root, destination_root, error_file = retry_environment
    source = source_root / "source-asset"
    (source / "nested").mkdir(parents=True)
    (source / "nested" / "data.bin").write_bytes(b"complete payload")
    destination = destination_root / "Flyers & Print" / "Recovered Asset"
    (destination / "nested").mkdir(parents=True)
    (destination / "nested" / "data.bin").write_bytes(b"complete")
    _write_errors(error_file, [
        _retry_record(source, destination, source_root, destination_root),
    ])

    runner.retry_errors("design")

    assert not error_file.exists()
    assert not source.exists()
    assert (destination / "nested" / "data.bin").read_bytes() == b"complete payload"


def test_retry_never_deletes_unrelated_occupied_file(retry_environment):
    source_root, destination_root, error_file = retry_environment
    source = source_root / "source.bin"
    source.write_bytes(b"source payload")
    destination = destination_root / "Flyers & Print" / "Recovered Asset.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"unrelated data")
    _write_errors(error_file, [
        _retry_record(
            source,
            destination,
            source_root,
            destination_root,
            is_file_item=True,
            file_ext=".bin",
        ),
    ])

    runner.retry_errors("loose_files")

    assert source.read_bytes() == b"source payload"
    assert destination.read_bytes() == b"unrelated data"
    remaining = json.loads(error_file.read_text(encoding="utf-8"))
    assert remaining[0]["retry_error_code"] == "partial_destination_unrelated"


def test_retry_rejects_changed_partial_identity(retry_environment):
    source_root, destination_root, error_file = retry_environment
    source = source_root / "source.bin"
    source.write_bytes(b"source payload")
    destination = destination_root / "Flyers & Print" / "Recovered Asset.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"source")
    record = _retry_record(
        source,
        destination,
        source_root,
        destination_root,
        is_file_item=True,
        file_ext=".bin",
    )
    destination.write_bytes(b"source payload changed after failure")
    _write_errors(error_file, [record])

    runner.retry_errors("loose_files")

    assert source.exists()
    assert destination.read_bytes() == b"source payload changed after failure"
    remaining = json.loads(error_file.read_text(encoding="utf-8"))
    assert remaining[0]["retry_error_code"] == "partial_destination_changed"


def test_retry_rejects_symlink_partial_destination(retry_environment):
    source_root, destination_root, error_file = retry_environment
    source = source_root / "source.bin"
    source.write_bytes(b"source payload")
    unrelated = destination_root / "unrelated.bin"
    unrelated.write_bytes(b"do not delete")
    destination = destination_root / "Flyers & Print" / "Recovered Asset.bin"
    destination.parent.mkdir(parents=True)
    try:
        destination.symlink_to(unrelated)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink unavailable: {exc}")
    _write_errors(error_file, [
        _retry_record(
            source,
            destination,
            source_root,
            destination_root,
            is_file_item=True,
            file_ext=".bin",
        ),
    ])

    runner.retry_errors("loose_files")

    assert source.exists()
    assert destination.is_symlink()
    assert unrelated.read_bytes() == b"do not delete"
    remaining = json.loads(error_file.read_text(encoding="utf-8"))
    assert remaining[0]["partial_dest_exists"] is True


def test_legacy_retry_without_partial_identity_fails_closed(retry_environment):
    source_root, destination_root, error_file = retry_environment
    source = source_root / "source.bin"
    source.write_bytes(b"source payload")
    destination = destination_root / "Flyers & Print" / "Recovered Asset.bin"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"source")
    record = _retry_record(
        source,
        destination,
        source_root,
        destination_root,
        is_file_item=True,
        file_ext=".bin",
    )
    record.pop("partial_dest_signature")
    _write_errors(error_file, [record])

    runner.retry_errors("loose_files")

    assert source.exists()
    assert destination.read_bytes() == b"source"
    remaining = json.loads(error_file.read_text(encoding="utf-8"))
    assert remaining[0]["retry_error_code"] == "partial_identity_missing"
