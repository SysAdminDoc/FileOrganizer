"""Regression tests for provider endpoint and credential-storage boundaries."""

from __future__ import annotations

import json
import os

import pytest

from fileorganizer import metadata, providers, secret_store


def test_dpapi_secret_round_trip_has_no_plaintext_file_value(tmp_path, monkeypatch):
    if os.name != "nt":
        pytest.skip("DPAPI is Windows-only")
    secret_file = tmp_path / "secrets.json"
    monkeypatch.setattr(secret_store, "_SECRETS_FILE", str(secret_file))

    secret_store.set_secret("test-token", "token-value-123")

    assert secret_store.get_secret("test-token") == "token-value-123"
    assert "token-value-123" not in secret_file.read_text(encoding="utf-8")
    assert secret_file.read_text(encoding="utf-8").startswith("{")


def test_provider_save_keeps_credentials_out_of_provider_json(tmp_path, monkeypatch):
    settings_file = tmp_path / "provider_settings.json"
    stored_secrets = {}
    monkeypatch.setattr(providers, "_PROVIDER_SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(
        providers,
        "set_secret",
        lambda name, value: stored_secrets.__setitem__(name, value),
    )
    monkeypatch.setattr(
        providers, "get_secret", lambda name: stored_secrets.get(name, "")
    )

    providers.save_provider_settings(
        {
            "github_token": "gh-token",
            "deepseek_api_key": "ds-key",
            "github_endpoint": "https://models.github.ai/inference/",
            "deepseek_endpoint": "https://api.deepseek.com/",
        }
    )

    payload = json.loads(settings_file.read_text(encoding="utf-8"))
    assert "github_token" not in payload
    assert "deepseek_api_key" not in payload
    assert stored_secrets == {
        "github_models_token": "gh-token",
        "deepseek_api_key": "ds-key",
    }

    loaded = providers.load_provider_settings()
    assert loaded["github_token"] == "gh-token"
    assert loaded["deepseek_api_key"] == "ds-key"


def test_provider_load_migrates_legacy_plaintext_fields(tmp_path, monkeypatch):
    settings_file = tmp_path / "provider_settings.json"
    migrated = {}
    settings_file.write_text(
        json.dumps(
            {
                "github_token": "legacy-gh",
                "deepseek_api_key": "legacy-ds",
                "github_enabled": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(providers, "_PROVIDER_SETTINGS_FILE", str(settings_file))
    monkeypatch.setattr(providers, "get_secret", lambda name: "")
    monkeypatch.setattr(
        providers,
        "set_secret",
        lambda name, value: migrated.__setitem__(name, value),
    )

    loaded = providers.load_provider_settings()

    assert loaded["github_token"] == "legacy-gh"
    assert loaded["deepseek_api_key"] == "legacy-ds"
    assert migrated == {
        "github_models_token": "legacy-gh",
        "deepseek_api_key": "legacy-ds",
    }
    sanitized = json.loads(settings_file.read_text(encoding="utf-8"))
    assert "github_token" not in sanitized
    assert "deepseek_api_key" not in sanitized
    assert sanitized["github_enabled"] is True


@pytest.mark.parametrize(
    "provider, endpoint",
    [
        ("github", "http://models.github.ai/inference"),
        ("github", "https://127.0.0.1/inference"),
        ("github", "https://models.github.ai.evil.test/inference"),
        ("github", "https://user:pass@models.github.ai/inference"),
        ("github", "https://models.github.ai:8443/inference"),
        ("deepseek", "https://api.deepseek.com.evil.test"),
        ("deepseek", "https://api.deepseek.com/?next=http://127.0.0.1"),
    ],
)
def test_provider_endpoint_allowlist_rejects_unsafe_values(provider, endpoint):
    assert providers.validate_provider_endpoint(endpoint, provider) is None


def test_provider_endpoint_allowlist_accepts_canonical_defaults():
    assert providers.validate_provider_endpoint(
        "https://models.github.ai/inference/", "github"
    ) == "https://models.github.ai/inference"
    assert providers.validate_provider_endpoint(
        "https://api.deepseek.com/", "deepseek"
    ) == "https://api.deepseek.com"


def test_envato_legacy_file_is_migrated_and_removed(tmp_path, monkeypatch):
    legacy_file = tmp_path / "envato_api_key.txt"
    legacy_file.write_text("envato-token", encoding="utf-8")
    protected = {}
    monkeypatch.setattr(metadata, "_ENVATO_KEY_FILE", str(legacy_file))
    monkeypatch.setattr(
        "fileorganizer.secret_store.get_secret",
        lambda name: protected.get(name, ""),
    )
    monkeypatch.setattr(
        "fileorganizer.secret_store.set_secret",
        lambda name, value: protected.__setitem__(name, value),
    )

    assert metadata._load_envato_api_key() == "envato-token"
    assert protected["envato_api_key"] == "envato-token"
    assert not legacy_file.exists()
