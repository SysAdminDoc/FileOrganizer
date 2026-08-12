from __future__ import annotations

from fileorganizer.dedup_checkpoint import DedupCheckpointStore, checkpoint_key
from fileorganizer.duplicates import ProgressiveDuplicateDetector


def _entries(*paths):
    return [
        (str(path), path.stat().st_size, path.stat().st_mtime_ns)
        for path in paths
    ]


def test_checkpoint_key_changes_when_file_stat_changes(tmp_path):
    path = tmp_path / "item.bin"
    path.write_bytes(b"abc")
    first = checkpoint_key([(str(path), 3, 10)])
    second = checkpoint_key([(str(path), 4, 10)])
    third = checkpoint_key([(str(path), 3, 11)])

    assert first != second
    assert first != third


def test_checkpoint_store_round_trip_and_clear(tmp_path):
    store = DedupCheckpointStore(str(tmp_path / "checkpoints.db"))
    store.open()
    store.put_many("run", "prefix", {"one": "hash-one", "two": "hash-two"})

    assert store.get("run", "prefix", "one") == "hash-one"
    assert store.get("run", "prefix", "missing") is None

    store.clear("run")
    assert store.get("run", "prefix", "one") is None
    store.close()


def test_detector_resumes_saved_prefix_hashes_and_clears_on_completion(tmp_path, monkeypatch):
    payload = (b"prefix" + bytes(range(256))) * 512
    first_path = tmp_path / "first.bin"
    second_path = tmp_path / "second.bin"
    first_path.write_bytes(payload)
    second_path.write_bytes(payload)
    entries = _entries(first_path, second_path)
    checkpoint_path = tmp_path / "dedup.db"

    callback_calls = 0

    def cancel_after_one_hash():
        nonlocal callback_calls
        callback_calls += 1
        return callback_calls > 1

    interrupted = ProgressiveDuplicateDetector(
        enable_perceptual=False,
        enable_audio=False,
        checkpoint_path=str(checkpoint_path),
        checkpoint_every=1,
        cancel_cb=cancel_after_one_hash,
    )
    assert interrupted.detect(entries) == {}

    run_key = checkpoint_key(entries)
    with DedupCheckpointStore(str(checkpoint_path)) as store:
        assert store.get(run_key, "prefix", str(first_path))
        assert store.get(run_key, "prefix", str(second_path)) is None

    partial_calls = []
    real_partial = ProgressiveDuplicateDetector._hash_partial

    def recording_partial(path, offset, size):
        partial_calls.append((path, offset))
        return real_partial(path, offset, size)

    resumed = ProgressiveDuplicateDetector(
        enable_perceptual=False,
        enable_audio=False,
        checkpoint_path=str(checkpoint_path),
        checkpoint_every=1,
    )
    monkeypatch.setattr(resumed, "_hash_partial", recording_partial)
    result = resumed.detect(entries)

    assert set(result) == {str(first_path), str(second_path)}
    assert (str(first_path), 0) not in partial_calls
    with DedupCheckpointStore(str(checkpoint_path)) as store:
        assert store.get(run_key, "prefix", str(first_path)) is None

