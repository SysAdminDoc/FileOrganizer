from __future__ import annotations

import json

import pytest

import marketplace_enrich as marketplace


@pytest.mark.parametrize(
    ("name", "platform", "item_id"),
    [
        ("freepik_57407642", "freepik", "57407642"),
        ("filtergrade-123456", "filtergrade", "123456"),
        ("ss-1213219402", "shutterstock", "1213219402"),
        ("adobe-stock-327844566", "adobe_stock", "327844566"),
        (
            "https://www.freepik.com/premium-vector/anden-condor_57407642.htm",
            "freepik",
            "premium-vector/anden-condor_57407642.htm",
        ),
        (
            "https://filtergrade.com/product/media-creator-bundle-50-luts-50-overlays/",
            "filtergrade",
            "product/media-creator-bundle-50-luts-50-overlays/",
        ),
        (
            "https://stock.adobe.com/images/homepage/327844566",
            "adobe_stock",
            "images/homepage/327844566",
        ),
    ],
)
def test_extract_id_supports_expanded_marketplaces(name, platform, item_id):
    assert marketplace.extract_id(name) == (platform, item_id)


class _Response:
    def __init__(self, text="", payload=None, url=""):
        self.status_code = 200
        self.text = text
        self.url = url
        self._payload = payload

    def json(self):
        return self._payload


def test_freepik_api_parser_uses_explicit_key(monkeypatch):
    captured = {}

    def fake_get(url, domain, extra_headers=None):
        captured.update(url=url, domain=domain, headers=extra_headers)
        return _Response(
            payload={
                "data": {
                    "id": 57407642,
                    "title": "Andean Condor",
                    "type": "vector",
                    "url": "https://www.freepik.com/free-vector/andean-condor_57407642.htm",
                }
            },
            url=url,
        )

    monkeypatch.setenv("FREEPIK_API_KEY", "freepik-test-key")
    monkeypatch.setattr(marketplace, "_throttled_get", fake_get)

    result = marketplace.fetch_freepik("57407642")

    assert result["title"] == "Andean Condor"
    assert result["category"] == "Illustrator - Vector Graphics"
    assert captured["domain"] == "api.freepik.com"
    assert captured["headers"]["x-freepik-api-key"] == "freepik-test-key"


def test_freepik_without_key_fails_closed_for_numeric_id(monkeypatch):
    monkeypatch.delenv("FREEPIK_API_KEY", raising=False)
    called = []
    monkeypatch.setattr(
        marketplace,
        "_throttled_get",
        lambda *args, **kwargs: called.append((args, kwargs)),
    )

    assert marketplace.fetch_freepik("57407642") is None
    assert called == []


def test_page_parser_handles_json_ld_and_meta_tags(monkeypatch):
    page = """
    <html><head>
      <meta property="og:title" content="Premium LUT Bundle - FilterGrade">
      <meta name="keywords" content="LUTs, color grading, cinematic">
      <script type="application/ld+json">
        {"@context":"https://schema.org","@type":"Product",
         "name":"Premium LUT Bundle","category":"LUTs"}
      </script>
    </head></html>
    """
    monkeypatch.setattr(
        marketplace,
        "_throttled_get",
        lambda url, domain, extra_headers=None: _Response(
            text=page, url=url,
        ),
    )

    result = marketplace.fetch_filtergrade("product/premium-lut-bundle")

    assert result["title"] == "Premium LUT Bundle"
    assert result["category"] == "Color Grading & LUTs"
    assert result["tags"][:2] == ["LUTs", "color grading"]
    assert result["source"] == "marketplace_page"


def test_expanded_fetchers_are_registered():
    for platform in ("freepik", "motionarray", "filtergrade", "shutterstock", "adobe_stock"):
        assert callable(marketplace._FETCHERS[platform])


def test_update_check_establishes_baseline_without_alert(tmp_path, monkeypatch):
    cache_file = tmp_path / "marketplace-cache.json"
    monkeypatch.setattr(marketplace, "CACHE_FILE", cache_file)
    monkeypatch.setitem(
        marketplace._FETCHERS,
        "shutterstock",
        lambda item_id: {
            "platform": "shutterstock",
            "item_id": item_id,
            "title": "Photo",
            "category": "Stock Photos - General",
            "version": "1",
            "updated_at": "2026-01-01T00:00:00Z",
        },
    )

    summary = marketplace.check_for_updates(
        ["ss-1213219402"], force=True, now=1_800_000_000,
    )

    assert summary["checked"] == 1
    assert summary["updates"] == []
    saved = json.loads(cache_file.read_text(encoding="utf-8"))
    assert saved["shutterstock:1213219402"]["last_update_check_at"] == 1_800_000_000


def test_update_check_reports_new_provider_version_and_throttles(tmp_path, monkeypatch):
    cache_file = tmp_path / "marketplace-cache.json"
    cache_file.write_text(json.dumps({
        "shutterstock:1213219402": {
            "platform": "shutterstock",
            "item_id": "1213219402",
            "title": "Photo",
            "category": "Stock Photos - General",
            "version": "1",
            "updated_at": "2026-01-01T00:00:00Z",
            "last_update_check_at": 0,
        },
    }), encoding="utf-8")
    monkeypatch.setattr(marketplace, "CACHE_FILE", cache_file)
    calls = []

    def fresh(item_id):
        calls.append(item_id)
        return {
            "platform": "shutterstock",
            "item_id": item_id,
            "title": "Photo",
            "category": "Stock Photos - General",
            "version": "2",
            "updated_at": "2026-02-01T00:00:00Z",
        }

    monkeypatch.setitem(marketplace._FETCHERS, "shutterstock", fresh)
    summary = marketplace.check_for_updates(
        ["ss-1213219402", "ss-1213219402"], force=True, now=1_800_000_000,
    )

    assert calls == ["1213219402"]
    assert summary["updates"][0]["previous_version"] == "1"
    assert summary["updates"][0]["current_version"] == "2"
    assert summary["updates"][0]["category"] == "Stock Photos - General"

    calls.clear()
    throttled = marketplace.check_for_updates(
        ["ss-1213219402"], now=1_800_000_100,
    )
    assert calls == []
    assert throttled["skipped"] == 1
    assert throttled["updates"][0]["current_version"] == "2"
