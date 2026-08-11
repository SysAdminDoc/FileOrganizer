from __future__ import annotations

import json

from fileorganizer import llama_cache
from fileorganizer import ollama


def test_prompt_cache_reuses_and_invalidates_context():
    cache = llama_cache.PromptCache(slot=3)

    first = cache.prepare("qwen", "system", context_revision="v1")
    second = cache.prepare("qwen", "system", context_revision="v1")
    changed = cache.prepare("qwen", "system", context_revision="v2")

    assert first.reused is False
    assert second.reused is True
    assert second.generation == first.generation
    assert changed.reused is False
    assert changed.generation > second.generation
    assert cache.stats()["hits"] == 1


def test_complete_requests_loopback_prompt_cache(monkeypatch):
    cache = llama_cache.PromptCache(slot=2)
    captured: dict[str, object] = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _limit=None):
            return json.dumps({
                "choices": [{"message": {"content": '{"ok":true}'}}],
            }).encode("utf-8")

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(llama_cache.urllib.request, "urlopen", fake_urlopen)
    content, state = llama_cache.complete(
        "http://127.0.0.1:8080",
        model="qwen",
        messages=[
            {"role": "system", "content": "stable taxonomy"},
            {"role": "user", "content": "classify this batch"},
        ],
        cache=cache,
        context_revision="categories-v1",
        max_tokens=200,
        timeout=12,
    )

    assert content == '{"ok":true}'
    assert state.slot == 2
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["payload"]["cache_prompt"] is True
    assert captured["payload"]["id_slot"] == 2
    assert captured["timeout"] == 12.0


def test_non_loopback_cache_endpoint_is_rejected():
    cache = llama_cache.PromptCache()

    try:
        llama_cache.complete(
            "https://inference.example.invalid",
            model="qwen",
            messages=[{"role": "system", "content": "x"}],
            cache=cache,
        )
    except llama_cache.LlamaServerUnavailable as exc:
        assert "loopback" in str(exc)
    else:
        raise AssertionError("remote llama-server endpoint was accepted")


def test_ollama_batch_uses_opt_in_llama_server_cache(monkeypatch):
    calls: list[dict[str, object]] = []
    monkeypatch.setenv("FILEORGANIZER_LLAMA_SERVER_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("FILEORGANIZER_LLM_CONTEXT_REVISION", "taxonomy-v1")
    monkeypatch.setattr(
        ollama,
        "load_ollama_settings",
        lambda: {
            "url": "http://127.0.0.1:11434",
            "model": "qwen",
            "timeout": 10,
            "think": False,
            "num_predict": 64,
            "temperature": 0.1,
        },
    )
    monkeypatch.setattr(ollama, "get_all_category_names", lambda: ["Flyer / Poster"])

    def fake_complete(endpoint, **kwargs):
        calls.append({"endpoint": endpoint, **kwargs})
        return (
            '{"results":[{"name":"Poster","category":"Flyer / Poster",'
            '"confidence":90,"alternatives":[]}]}',
            llama_cache.PromptCacheState("a" * 64, 0, 1, False),
        )

    monkeypatch.setattr(llama_cache, "complete", fake_complete)
    results = ollama.ollama_classify_batch([{
        "folder_name": "Poster",
        "folder_path": "C:/Poster",
        "context": "Files: poster.psd",
    }])

    assert results[0]["category"] == "Flyer / Poster"
    assert calls[0]["endpoint"] == "http://127.0.0.1:8080"
    assert calls[0]["context_revision"] == "taxonomy-v1"
