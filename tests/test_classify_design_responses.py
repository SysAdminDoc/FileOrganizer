import json
import sys
import types

import pytest

import classify_design


def _item(name="Demo Pack"):
    return {"name": name, "path": ""}


def _valid(name="Demo Pack"):
    return {
        "name": name,
        "category": "After Effects - Other",
        "clean_name": name,
        "confidence": 85,
        "notes": "extension evidence",
    }


@pytest.mark.parametrize(
    "raw",
    [
        7,
        {"name": "Demo Pack"},
        {
            "name": "Demo Pack",
            "category": "After Effects - Other",
            "clean_name": "Demo Pack",
            "confidence": "85",
        },
        {
            "name": "Demo Pack",
            "category": "not-a-category",
            "clean_name": "Demo Pack",
            "confidence": 85,
        },
        {
            "name": "Demo Pack",
            "category": "After Effects - Other",
            "clean_name": "Demo Pack",
            "confidence": 101,
        },
    ],
)
def test_deepseek_item_schema_failures_become_retry_records(raw):
    result = classify_design._normalize_deepseek_result(
        raw,
        _item(),
        0,
        {"After Effects - Other", "_Review"},
    )

    assert result["category"] == "_Review"
    assert result["_retry_required"] is True
    assert result["_classifier"] == "deepseek_schema_guard"


def test_deepseek_item_schema_accepts_valid_result():
    raw = _valid()
    result = classify_design._normalize_deepseek_result(
        raw,
        _item(),
        0,
        {"After Effects - Other", "_Review"},
    )

    assert result == raw


class _FakeOpenAI:
    response_content = "[]"

    def __init__(self, **_kwargs):
        self.chat = types.SimpleNamespace(
            completions=types.SimpleNamespace(create=self._create)
        )

    def _create(self, **_kwargs):
        return types.SimpleNamespace(
            choices=[
                types.SimpleNamespace(
                    message=types.SimpleNamespace(content=self.response_content)
                )
            ]
        )


@pytest.mark.parametrize(
    ("content", "code"),
    [
        ('{"items": []}', "outer_type"),
        ('[{"name": "only"}]', "cardinality"),
    ],
)
def test_call_deepseek_rejects_invalid_batch_shape(monkeypatch, content, code):
    fake_openai = types.ModuleType("openai")
    fake_client = type(
        "Client",
        (_FakeOpenAI,),
        {"response_content": content},
    )
    fake_openai.OpenAI = fake_client
    monkeypatch.setitem(sys.modules, "openai", fake_openai)

    with pytest.raises(classify_design.DeepSeekResponseError) as exc_info:
        classify_design.call_deepseek("prompt", expected_count=2)

    assert exc_info.value.code == code


def test_cached_and_fresh_results_share_schema_guard(monkeypatch):
    items = [_item("good"), _item("bad")]
    monkeypatch.setattr(
        classify_design,
        "get_runtime_category_set",
        lambda: {"After Effects - Other", "_Review"},
    )
    monkeypatch.setattr(classify_design, "lookup_cached", lambda *_args: None)
    monkeypatch.setattr(
        classify_design,
        "call_deepseek",
        lambda _prompt, expected_count=None: [_valid("good"), 99],
    )
    stored = []
    monkeypatch.setattr(
        classify_design,
        "store_cached",
        lambda *args: stored.append(args) or True,
    )

    result = classify_design.call_deepseek_cached("prompt", items)

    assert result[0]["category"] == "After Effects - Other"
    assert result[1]["category"] == "_Review"
    assert result[1]["_retry_required"] is True
    assert len(stored) == 0


def test_already_done_does_not_skip_retry_markers(tmp_path, monkeypatch):
    monkeypatch.setattr(classify_design, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(classify_design, "BATCH_PREFIX", "batch_")
    path = classify_design.batch_file(1)

    path.write_text(json.dumps([{"name": "done"}]), encoding="utf-8")
    assert classify_design.already_done(1) is True

    path.write_text(
        json.dumps([{"error": "cardinality", "_retry_required": True}]),
        encoding="utf-8",
    )
    assert classify_design.already_done(1) is False


def test_atomic_result_write_leaves_no_temporary_batch_file(tmp_path):
    path = tmp_path / "batch.json"
    classify_design._atomic_write_json(path, [{"name": "done"}])

    assert json.loads(path.read_text(encoding="utf-8")) == [{"name": "done"}]
    assert list(tmp_path.glob("*.tmp")) == []


def test_cmd_run_writes_retry_marker_instead_of_invalid_partial_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(classify_design, "RESULTS_DIR", tmp_path)
    monkeypatch.setattr(classify_design, "BATCH_PREFIX", "batch_")
    monkeypatch.setattr(classify_design, "BATCH_SIZE", 1)
    monkeypatch.setattr(classify_design, "DEEPSEEK_API_KEY", "test-key")
    monkeypatch.setattr(classify_design, "cleanup_expired", lambda **_kwargs: 0)
    for name in (
        "_try_fingerprint_db_lookup",
        "_try_metadata_classify",
        "_try_marketplace_enrich",
        "_try_embeddings_classify",
    ):
        monkeypatch.setattr(
            classify_design,
            name,
            lambda *args, **kwargs: {},
        )
    monkeypatch.setattr(
        classify_design,
        "call_deepseek_cached",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            classify_design.DeepSeekResponseError("cardinality", "bad batch")
        ),
    )

    classify_design.cmd_run([_item("broken")])

    path = classify_design.batch_file(1)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload[0]["_retry_required"] is True
    assert classify_design.already_done(1) is False
    assert list(tmp_path.glob("*.tmp")) == []
