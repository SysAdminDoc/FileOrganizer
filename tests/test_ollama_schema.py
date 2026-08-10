from __future__ import annotations

import json
import urllib.request

from fileorganizer import ollama


def test_classify_result_schema_has_discriminator():
    assert ollama.HAS_PYDANTIC is True

    schema = ollama.classify_result_json_schema()

    assert "oneOf" in schema
    assert schema["discriminator"]["propertyName"] == "kind"
    assert set(schema["discriminator"]["mapping"]) == {"classification", "review"}


def test_classify_result_schema_hash_is_deterministic():
    first = ollama.classify_result_schema_hash()
    second = ollama.classify_result_schema_hash()

    assert first == second
    assert len(first) == 64


def test_ollama_generate_uses_discriminated_schema(monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_exc):
            return False

        def read(self):
            return json.dumps(
                {
                    "message": {
                        "content": '{"kind":"classification","name":"Poster","category":"Design","confidence":80}'
                    }
                }
            ).encode("utf-8")

    def fake_urlopen(req, timeout):
        captured["timeout"] = timeout
        captured["payload"] = json.loads(req.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setattr(
        ollama,
        "load_ollama_settings",
        lambda: {
            "url": "http://localhost:11434",
            "model": "model-a",
            "timeout": 120,
            "temperature": 0.1,
            "num_predict": 128,
            "think": False,
        },
    )
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    raw = ollama._ollama_generate("prompt", structured=True)

    assert "Poster" in raw
    assert captured["timeout"] == 120
    assert captured["payload"]["format"]["discriminator"]["propertyName"] == "kind"
    assert set(captured["payload"]["format"]["discriminator"]["mapping"]) == {
        "classification",
        "review",
    }


def test_ollama_classify_folder_handles_review_result(monkeypatch):
    monkeypatch.setattr(
        ollama,
        "_ollama_generate",
        lambda *_args, **_kwargs: (
            '{"kind":"review","name":"Mystery Pack","category":"_Review",'
            '"confidence":0,"reason":"insufficient evidence"}'
        ),
    )

    result = ollama.ollama_classify_folder("Mystery Pack")

    assert result["name"] == "Mystery Pack"
    assert result["category"] is None
    assert result["confidence"] == 0
    assert result["detail"] == "llm:review:insufficient evidence"


def test_ollama_classify_folder_injects_adaptive_examples(monkeypatch):
    from fileorganizer import adaptive_corrector

    class FakeCorrector:
        def apply_correction(self, _path):
            return None

        def inject_few_shot(self, _folder_name, num_examples=3):
            assert num_examples == 3
            return [{
                'name': 'Summer Flyer',
                'category': 'Print - Flyers & Posters',
            }]

    captured = {}
    monkeypatch.setattr(adaptive_corrector, 'AdaptiveCorrector', FakeCorrector)

    def fake_generate(_prompt, **kwargs):
        captured['system'] = kwargs['system']
        return (
            '{"kind":"classification","name":"Spring Flyer",'
            '"category":"After Effects - Lower Thirds","confidence":85}'
        )

    monkeypatch.setattr(ollama, '_ollama_generate', fake_generate)

    result = ollama.ollama_classify_folder('Spring Flyer')

    assert result['category'] == 'After Effects - Lower Thirds'
    assert 'Summer Flyer → Print - Flyers & Posters' in captured['system']


def test_ollama_classify_folder_applies_exact_correction_before_llm(monkeypatch):
    from fileorganizer import adaptive_corrector

    class FakeCorrector:
        def apply_correction(self, path):
            assert path == 'C:/library/Summer Flyer'
            return ('Print - Flyers & Posters', 88)

    monkeypatch.setattr(adaptive_corrector, 'AdaptiveCorrector', FakeCorrector)
    monkeypatch.setattr(
        ollama,
        '_ollama_generate',
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError('LLM should not run')
        ),
    )

    result = ollama.ollama_classify_folder(
        'Summer Flyer', 'C:/library/Summer Flyer'
    )

    assert result == {
        'name': 'Summer Flyer',
        'category': 'Print - Flyers & Posters',
        'confidence': 100,
        'method': 'adaptive_correction',
        'detail': 'adaptive correction (weight 88)',
    }
