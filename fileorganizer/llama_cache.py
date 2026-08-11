"""Loopback llama-server client with bounded prompt-prefix cache state."""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


MAX_CACHE_KEY_LENGTH = 128
MAX_CONTEXT_REVISION_LENGTH = 256
MAX_RESPONSE_LENGTH = 64_000
DEFAULT_SLOT = 0


class LlamaServerUnavailable(RuntimeError):
    """Raised when the optional local llama-server cannot answer."""


@dataclass(frozen=True)
class PromptCacheState:
    """Observable state for one llama-server prompt slot."""

    signature: str
    slot: int
    generation: int
    reused: bool


class PromptCache:
    """Track a reusable prompt prefix and invalidate it safely when context changes."""

    def __init__(self, slot: int = DEFAULT_SLOT) -> None:
        if not 0 <= int(slot) <= 64:
            raise ValueError("llama-server slot must be between 0 and 64")
        self.slot = int(slot)
        self._lock = threading.RLock()
        self._signature: str | None = None
        self._generation = 0
        self._hits = 0
        self._misses = 0

    def prepare(
        self,
        model: str,
        system_prefix: str,
        *,
        context_revision: str = "",
    ) -> PromptCacheState:
        """Return the slot state, invalidating after a relevant context change."""
        material = "\0".join((str(model), str(system_prefix), str(context_revision)))
        signature = hashlib.sha256(material.encode("utf-8", "replace")).hexdigest()
        with self._lock:
            reused = self._signature == signature
            if reused:
                self._hits += 1
            else:
                self._misses += 1
                self._generation += 1
                self._signature = signature
            return PromptCacheState(signature, self.slot, self._generation, reused)

    def invalidate(self) -> None:
        """Drop the reusable prefix after a user or taxonomy context change."""
        with self._lock:
            self._signature = None
            self._generation += 1

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {
                "generation": self._generation,
                "hits": self._hits,
                "misses": self._misses,
                "slot": self.slot,
            }


_CACHE_LOCK = threading.RLock()
_CACHES: dict[tuple[str, str], PromptCache] = {}


def get_prompt_cache(endpoint: str, model: str) -> PromptCache:
    """Return a process-local cache shared by sequential batches."""
    key = (endpoint.rstrip("/"), str(model)[:MAX_CACHE_KEY_LENGTH])
    with _CACHE_LOCK:
        cache = _CACHES.get(key)
        if cache is None:
            cache = PromptCache()
            _CACHES[key] = cache
        return cache


def invalidate_prompt_cache(endpoint: str | None = None, model: str | None = None) -> None:
    """Invalidate one cache or every local llama-server cache."""
    with _CACHE_LOCK:
        for (cache_endpoint, cache_model), cache in _CACHES.items():
            if endpoint and cache_endpoint != endpoint.rstrip("/"):
                continue
            if model and cache_model != model[:MAX_CACHE_KEY_LENGTH]:
                continue
            cache.invalidate()


def _validate_loopback_endpoint(endpoint: str) -> str:
    parsed = urllib.parse.urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "localhost", "127.0.0.1", "::1",
    }:
        raise LlamaServerUnavailable(
            "llama-server cache endpoint must be a local loopback HTTP URL"
        )
    return endpoint.rstrip("/")


def complete(
    endpoint: str,
    *,
    model: str,
    messages: list[dict[str, str]],
    cache: PromptCache,
    context_revision: str = "",
    temperature: float = 0.1,
    max_tokens: int = 4096,
    timeout: float = 180.0,
) -> tuple[str, PromptCacheState]:
    """Complete one request through llama-server's OpenAI-compatible endpoint."""
    base = _validate_loopback_endpoint(endpoint)
    if not messages or not isinstance(messages[0], dict):
        raise ValueError("llama-server requires at least one message")
    if not 1 <= int(max_tokens) <= 65_536:
        raise ValueError("max_tokens is outside the supported range")
    if not 0.1 <= float(timeout) <= 3_600:
        raise ValueError("timeout is outside the supported range")
    prefix = str(messages[0].get("content", ""))[:64_000]
    state = cache.prepare(
        model,
        prefix,
        context_revision=str(context_revision)[:MAX_CONTEXT_REVISION_LENGTH],
    )
    payload = {
        "model": str(model)[:MAX_CACHE_KEY_LENGTH],
        "messages": messages,
        "temperature": float(temperature),
        "max_tokens": int(max_tokens),
        "stream": False,
        "cache_prompt": True,
        "id_slot": state.slot,
    }
    request = urllib.request.Request(
        f"{base}/v1/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(timeout)) as response:
            data = json.loads(response.read(MAX_RESPONSE_LENGTH + 1).decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise LlamaServerUnavailable(f"llama-server request failed: {exc}") from exc
    choices = data.get("choices") if isinstance(data, dict) else None
    first = choices[0] if isinstance(choices, list) and choices else {}
    message = first.get("message") if isinstance(first, dict) else {}
    content = message.get("content") if isinstance(message, dict) else ""
    if not isinstance(content, str) or not content.strip():
        raise LlamaServerUnavailable("llama-server returned no completion content")
    return content[:MAX_RESPONSE_LENGTH], state
