from __future__ import annotations

import json

import pytest

from fileorganizer import workers


class FakeResponse:
    def __init__(
        self,
        body: bytes,
        *,
        content_type: str = "application/json",
        content_length: int | None = None,
        url: str = "https://github.com/SysAdminDoc/FileOrganizer/releases/download/v1/asset_fingerprints.json",
    ) -> None:
        self.body = body
        self.offset = 0
        self.read_sizes: list[int] = []
        self.url = url
        self.headers = {"Content-Type": content_type}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self) -> str:
        return self.url

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            size = len(self.body) - self.offset
        chunk = self.body[self.offset:self.offset + size]
        self.offset += len(chunk)
        return chunk


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/SysAdminDoc/FileOrganizer/releases/download/v1/asset_fingerprints.json",
        "https://example.com/SysAdminDoc/FileOrganizer/releases/download/v1/asset_fingerprints.json",
        "https://github.com/other/FileOrganizer/releases/download/v1/asset_fingerprints.json",
        "https://github.com/SysAdminDoc/FileOrganizer/releases/download/v1/other.json",
        "https://github.com/SysAdminDoc/FileOrganizer/releases/download/v1%2Fevil/asset_fingerprints.json",
        "https://github.com/SysAdminDoc/FileOrganizer/releases/download/v1/asset_fingerprints.json?raw=1",
    ],
)
def test_catalog_download_url_rejects_unapproved_targets(url):
    with pytest.raises(workers.CatalogSyncError) as error:
        workers._validate_catalog_download_url(url)

    assert error.value.code == "invalid_url"


def test_catalog_download_url_accepts_owned_release_asset():
    url = (
        "https://github.com/SysAdminDoc/FileOrganizer/releases/download/"
        "v8.5.20/asset_fingerprints.json"
    )
    assert workers._validate_catalog_download_url(url) == url


def test_declared_oversized_response_is_rejected_before_reading():
    response = FakeResponse(b"{}", content_length=9)

    with pytest.raises(workers.CatalogSyncError) as error:
        workers._read_bounded_http_body(
            response,
            max_bytes=8,
            media_types=workers._CATALOG_JSON_TYPES,
        )

    assert error.value.code == "response_too_large"
    assert response.read_sizes == []


def test_chunked_oversized_response_retains_only_the_byte_budget():
    response = FakeResponse(b"123456789")

    with pytest.raises(workers.CatalogSyncError) as error:
        workers._read_bounded_http_body(
            response,
            max_bytes=8,
            media_types=workers._CATALOG_JSON_TYPES,
        )

    assert error.value.code == "response_too_large"
    assert response.read_sizes == [8, 1]


def test_wrong_content_type_is_rejected_before_reading():
    response = FakeResponse(b"<html>nope</html>", content_type="text/html")

    with pytest.raises(workers.CatalogSyncError) as error:
        workers._read_bounded_http_body(
            response,
            max_bytes=100,
            media_types=workers._CATALOG_JSON_TYPES,
        )

    assert error.value.code == "invalid_content_type"
    assert response.read_sizes == []


def test_catalog_read_observes_cancellation_before_body_read():
    response = FakeResponse(b"{}")

    with pytest.raises(workers.CatalogSyncCancelled):
        workers._read_bounded_http_body(
            response,
            max_bytes=100,
            media_types=workers._CATALOG_JSON_TYPES,
            cancel_cb=lambda: True,
        )

    assert response.read_sizes == []


def test_invalid_json_and_schema_are_controlled():
    with pytest.raises(workers.CatalogSyncError, match="malformed asset payload"):
        workers._decode_catalog_json(b"{", "asset payload")

    with pytest.raises(workers.CatalogSyncError) as error:
        workers._validate_catalog_payload({"schema_version": 2, "assets": [1]})
    assert error.value.code == "invalid_schema"


def test_normal_catalog_worker_downloads_validates_and_imports(monkeypatch, tmp_path):
    download_url = (
        "https://github.com/SysAdminDoc/FileOrganizer/releases/download/"
        "v8.5.20/asset_fingerprints.json"
    )
    release = {
        "published_at": "2026-08-10T12:00:00Z",
        "tag_name": "v8.5.20",
        "assets": [{
            "name": workers._CATALOG_ASSET_NAME,
            "browser_download_url": download_url,
        }],
    }
    catalog = {
        "schema_version": 2,
        "assets": [{
            "folder_fingerprint": "a" * 64,
            "files": [],
        }],
    }
    responses = [
        FakeResponse(
            json.dumps(release).encode(),
            content_length=len(json.dumps(release).encode()),
            url=workers._CATALOG_GITHUB_API,
        ),
        FakeResponse(
            json.dumps(catalog).encode(),
            content_type="application/octet-stream",
            url="https://release-assets.githubusercontent.com/release-asset/catalog",
        ),
    ]
    requested: list[tuple[str, int]] = []

    def fake_urlopen(request, timeout):
        requested.append((request.full_url, timeout))
        return responses.pop(0)

    imported: list[dict] = []
    persisted: list[tuple] = []
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr(workers, "_CATALOG_SYNC_FILE", str(tmp_path / "missing.json"))
    monkeypatch.setattr(
        workers.CatalogSyncWorker,
        "_import_catalog",
        staticmethod(lambda payload: (imported.append(payload) or (1, 0))),
    )
    monkeypatch.setattr(
        workers.CatalogSyncWorker,
        "_persist_sync_state",
        staticmethod(lambda *values: persisted.append(values)),
    )

    results: list[tuple[bool, str]] = []
    worker = workers.CatalogSyncWorker()
    worker.finished.connect(lambda success, message: results.append((success, message)))
    worker.run()

    assert requested == [(workers._CATALOG_GITHUB_API, 10), (download_url, 30)]
    assert imported == [catalog]
    assert persisted
    assert results == [(True, "Catalog updated from v8.5.20: +1 new assets, 0 already known")]
