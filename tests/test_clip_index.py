import json

import pytest

from fileorganizer.clip_index import (
    EMBEDDING_DIMENSION,
    ClipEmbedder,
    cosine_similarity,
    iter_image_paths,
    normalize_embedding,
    stable_model_id,
)


def test_normalize_embedding_enforces_dimension_and_unit_length():
    values = normalize_embedding([3.0] + [0.0] * (EMBEDDING_DIMENSION - 1))
    assert values[0] == pytest.approx(1.0)
    assert math_sum(values) == pytest.approx(1.0)
    assert cosine_similarity(values, values) == pytest.approx(1.0)


def math_sum(values):
    return sum(value * value for value in values)


@pytest.mark.parametrize(
    "values",
    [
        [0.0] * EMBEDDING_DIMENSION,
        [1.0] * (EMBEDDING_DIMENSION - 1),
        [float("nan")] + [0.0] * (EMBEDDING_DIMENSION - 1),
    ],
)
def test_normalize_embedding_rejects_invalid_vectors(values):
    with pytest.raises(ValueError):
        normalize_embedding(values)


def test_iter_image_paths_is_deterministic_and_skips_hidden_directories(tmp_path):
    root = tmp_path / "images"
    (root / "nested").mkdir(parents=True)
    (root / ".hidden").mkdir()
    (root / "b.png").write_bytes(b"b")
    (root / "a.jpg").write_bytes(b"a")
    (root / "nested" / "c.webp").write_bytes(b"c")
    (root / ".hidden" / "secret.jpg").write_bytes(b"secret")
    (root / "notes.txt").write_text("not an image", encoding="utf-8")

    paths = list(iter_image_paths(root))
    assert [path.rsplit("\\", 1)[-1] for path in paths] == ["a.jpg", "b.png", "c.webp"]


def test_clip_embedder_bounds_device_and_batch_size():
    with pytest.raises(ValueError):
        ClipEmbedder(device="metal")
    with pytest.raises(ValueError):
        ClipEmbedder(batch_size=0)


def test_model_id_is_stable_and_distinguishes_weights():
    first = stable_model_id("ViT-L-14", "weights-a")
    assert first == stable_model_id("ViT-L-14", "weights-a")
    assert first != stable_model_id("ViT-L-14", "weights-b")
    assert len(first) == 16


def test_clip_runner_reports_missing_optional_capability(tmp_path, monkeypatch, capsys):
    import clip_index_run

    monkeypatch.setattr(
        clip_index_run,
        "get_capability",
        lambda *_args: {"status": "unavailable"},
    )
    root = tmp_path / "images"
    root.mkdir()
    clip_index_run._PROTOCOL.reset()
    assert clip_index_run.main(["--root", str(root), "--db", str(tmp_path / "clip.db")]) == 3
    rows = [json.loads(line) for line in capsys.readouterr().out.splitlines() if line]
    assert rows[-1]["event"] == "error"
    assert rows[-1]["code"] == "capability_unavailable"
