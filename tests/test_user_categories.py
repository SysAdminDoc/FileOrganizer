from pathlib import Path

import pytest

import classify_design
from fileorganizer import categories
from fileorganizer import user_categories as uc
from fileorganizer.classifier import categorize_folder


def _make_examples(tmp_path: Path, count: int = uc.MIN_EXAMPLES) -> list[str]:
    examples = []
    for idx in range(count):
        folder = tmp_path / f"sermon graphics pack {idx}"
        folder.mkdir()
        (folder / f"sermon lower third {idx}.psd").write_text("sample", encoding="utf-8")
        examples.append(str(folder))
    return examples


def test_validate_examples_requires_eight(tmp_path: Path):
    examples = [tmp_path / f"example-{idx}" for idx in range(7)]
    with pytest.raises(uc.UserCategoryError):
        uc.validate_examples(examples, require_exists=False)


def test_teach_category_saves_keyword_only_when_setfit_fails(tmp_path: Path, monkeypatch):
    store = tmp_path / "user_categories.json"
    examples = _make_examples(tmp_path)

    def fail_train(record, **_kwargs):
        raise RuntimeError("setfit unavailable")

    monkeypatch.setattr(uc, "_train_setfit_model", fail_train)
    record = uc.teach_category(
        "Sermon Graphics",
        examples,
        keywords=["church media"],
        path=store,
    )

    assert record["name"] == "Sermon Graphics"
    assert record["status"] == "keyword_only"
    assert "setfit unavailable" in record["training"]["error"]
    assert ("Sermon Graphics", record["keywords"]) in uc.load_user_categories(store)
    assert "church media" in record["keywords"]
    assert "sermon" in record["keywords"]


def test_teach_category_records_trained_model_dir(tmp_path: Path, monkeypatch):
    store = tmp_path / "user_categories.json"
    examples = _make_examples(tmp_path)
    model_root = tmp_path / "models"

    def fake_train(record, **kwargs):
        model_dir = Path(kwargs["output_root"]) / "sermon-graphics"
        model_dir.mkdir(parents=True)
        trained = dict(record)
        trained["status"] = "trained"
        trained["training"] = dict(record["training"])
        trained["training"].update({
            "model_dir": str(model_dir),
            "trained_at": "2026-06-27T00:00:00Z",
            "error": "",
        })
        return trained

    monkeypatch.setattr(uc, "_train_setfit_model", fake_train)
    record = uc.teach_category(
        "Sermon Graphics",
        examples,
        path=store,
        output_root=model_root,
    )

    assert record["status"] == "trained"
    assert Path(record["training"]["model_dir"]).is_dir()
    assert uc.load_user_category_records(store)[0]["status"] == "trained"


def test_user_categories_precede_builtin_keyword_matches(monkeypatch):
    monkeypatch.setattr(
        categories,
        "load_user_categories",
        lambda: [("Local Wedding Visuals", ["wedding"])],
    )
    categories._CategoryIndex.invalidate()
    try:
        cat, conf, _cleaned = categorize_folder("wedding")
        assert cat == "Local Wedding Visuals"
        assert conf == 100
    finally:
        categories._CategoryIndex.invalidate()


def test_classify_user_category_uses_scan_text():
    records = [{
        "name": "Sermon Graphics",
        "keywords": ["sermon lower third"],
        "examples": [],
        "status": "keyword_only",
        "training": {},
    }]
    hit = uc.classify_user_category(
        "generic pack",
        scan={"all_filenames_clean": ["sermon lower third psd"]},
        records=records,
    )
    assert hit is not None
    assert hit["category"] == "Sermon Graphics"
    assert hit["method"] == "user_category"


def test_classify_design_runtime_categories_include_user_categories(monkeypatch):
    monkeypatch.setattr(
        uc,
        "load_user_categories",
        lambda: [("Sermon Graphics", ["sermon"])],
    )
    runtime = classify_design.get_runtime_categories()
    assert runtime[0] == "Sermon Graphics"
    assert "After Effects - Other" in runtime
    assert len(runtime) == len(set(runtime))
