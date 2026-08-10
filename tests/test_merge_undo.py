from fileorganizer import config
from fileorganizer.workers import restore_merge_manifest, safe_merge_move


def test_merge_preserves_conflict_and_undo_restores_only_incoming_files(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )
    source_root = tmp_path / "incoming"
    destination_root = tmp_path / "organized"
    source = source_root / "asset"
    destination = destination_root / "asset"
    source.mkdir(parents=True)
    destination.mkdir(parents=True)
    (source / "scene.txt").write_bytes(b"incoming")
    (destination / "scene.txt").write_bytes(b"existing")
    (destination / "unrelated.txt").write_bytes(b"keep")

    manifest = []
    merged, skipped = safe_merge_move(
        source,
        destination,
        check_hashes=False,
        manifest=manifest,
    )

    collision = destination / "scene (2).txt"
    assert merged == 1
    assert skipped == 0
    assert (destination / "scene.txt").read_bytes() == b"existing"
    assert collision.read_bytes() == b"incoming"
    assert (destination / "unrelated.txt").read_bytes() == b"keep"
    assert not source.exists()

    restored, errors = restore_merge_manifest(
        manifest,
        source_root,
        destination_root,
    )

    assert restored >= 1
    assert errors == 0
    assert (source / "scene.txt").read_bytes() == b"incoming"
    assert (destination / "scene.txt").read_bytes() == b"existing"
    assert (destination / "unrelated.txt").read_bytes() == b"keep"
    assert not collision.exists()
    assert manifest == []


def test_identical_merge_is_restored_without_removing_destination(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )
    source_root = tmp_path / "incoming"
    destination_root = tmp_path / "organized"
    source = source_root / "asset"
    destination = destination_root / "asset"
    source.mkdir(parents=True)
    destination.mkdir(parents=True)
    (source / "same.bin").write_bytes(b"same")
    (destination / "same.bin").write_bytes(b"same")

    manifest = []
    merged, skipped = safe_merge_move(
        source,
        destination,
        check_hashes=True,
        manifest=manifest,
    )

    assert merged == 0
    assert skipped == 1
    assert not source.exists()

    restored, errors = restore_merge_manifest(
        manifest,
        source_root,
        destination_root,
    )

    assert restored >= 1
    assert errors == 0
    assert (source / "same.bin").read_bytes() == b"same"
    assert (destination / "same.bin").read_bytes() == b"same"
    assert manifest == []


def test_merge_undo_refuses_modified_incoming_file(tmp_path, monkeypatch):
    monkeypatch.setattr(
        config,
        "_cached_protected_paths",
        {"system": [], "custom": [], "enabled": False},
    )
    source_root = tmp_path / "incoming"
    destination_root = tmp_path / "organized"
    source = source_root / "asset"
    destination = destination_root / "asset"
    source.mkdir(parents=True)
    destination.mkdir(parents=True)
    (source / "scene.txt").write_bytes(b"incoming")
    (destination / "scene.txt").write_bytes(b"existing")

    manifest = []
    safe_merge_move(source, destination, manifest=manifest)
    collision = destination / "scene (2).txt"
    collision.write_bytes(b"changed by user")

    restored, errors = restore_merge_manifest(
        manifest,
        source_root,
        destination_root,
    )

    assert restored >= 1
    assert errors == 1
    assert collision.read_bytes() == b"changed by user"
    assert not (source / "scene.txt").exists()
    assert any(entry.get("action") == "move" for entry in manifest)
