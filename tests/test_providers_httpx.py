from __future__ import annotations

import sys
import types

from fileorganizer import providers


class FakeResponse:
    def __init__(self, payload=None, exc=None):
        self.payload = payload or {
            "choices": [{"message": {"content": " OK "}}],
        }
        self.exc = exc

    def raise_for_status(self):
        if self.exc:
            raise self.exc

    def json(self):
        return self.payload


def install_fake_httpx(monkeypatch, response=None, post_exc=None):
    instances = []

    class FakeTimeout:
        def __init__(self, value):
            self.value = value

    class FakeClient:
        def __init__(self, timeout=None, http2=False):
            self.timeout = timeout
            self.http2 = http2
            self.posts = []
            instances.append(self)

        def post(self, url, headers=None, json=None, timeout=None):
            self.posts.append(
                {
                    "url": url,
                    "headers": headers,
                    "json": json,
                    "timeout": timeout,
                }
            )
            if post_exc:
                raise post_exc
            return response or FakeResponse()

    fake_httpx = types.ModuleType("httpx")
    fake_httpx.Client = FakeClient
    fake_httpx.Timeout = FakeTimeout
    monkeypatch.setitem(sys.modules, "httpx", fake_httpx)
    return instances


def test_chat_completions_provider_uses_httpx_transport(monkeypatch):
    instances = install_fake_httpx(monkeypatch)
    provider = providers._ChatCompletionsProvider(
        base_url="https://api.example.test/v1/",
        api_key="token-123",
        model="model-a",
        timeout=30,
    )

    result = provider.classify(
        "hello",
        system="system prompt",
        timeout=9,
        temperature=0.25,
        max_tokens=77,
    )

    assert result == "OK"
    assert instances[0].http2 is True
    assert instances[0].timeout.value == 30
    post = instances[0].posts[0]
    assert post["url"] == "https://api.example.test/v1/chat/completions"
    assert post["headers"]["Authorization"] == "Bearer token-123"
    assert post["headers"]["Accept"] == "application/json"
    assert post["timeout"] == 9
    assert post["json"] == {
        "model": "model-a",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "hello"},
        ],
        "temperature": 0.25,
        "max_tokens": 77,
    }


def test_chat_completions_provider_batch_builds_prompt(monkeypatch):
    instances = install_fake_httpx(monkeypatch)
    provider = providers._ChatCompletionsProvider(
        base_url="https://models.github.ai/inference",
        api_key="ghp-test",
        model="github-model",
        timeout=60,
    )
    item = types.SimpleNamespace(folder_name="Promo Pack", full_src="C:/x/promo.psd")

    result = provider.classify_batch([item], system="batch system")

    assert result == "OK"
    post = instances[0].posts[0]
    assert post["url"] == "https://models.github.ai/inference/chat/completions"
    assert post["json"]["messages"][0] == {"role": "system", "content": "batch system"}
    assert post["json"]["messages"][1]["role"] == "user"
    assert "1. Promo Pack.psd" in post["json"]["messages"][1]["content"]


def test_chat_completions_provider_returns_none_on_httpx_failure(monkeypatch):
    install_fake_httpx(monkeypatch, post_exc=RuntimeError("network down"))
    provider = providers._ChatCompletionsProvider(
        base_url="https://api.example.test",
        api_key="token",
        model="model-a",
        timeout=30,
    )

    assert provider.classify("hello") is None


def test_chat_completions_provider_test_connection_uses_httpx(monkeypatch):
    install_fake_httpx(monkeypatch)
    provider = providers._ChatCompletionsProvider(
        base_url="https://api.example.test",
        api_key="token",
        model="model-a",
        timeout=30,
    )

    ok, message = provider.test_connection()

    assert ok is True
    assert message == "Connected. Reply: 'OK'"
