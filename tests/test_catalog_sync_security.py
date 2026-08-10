from __future__ import annotations

import hashlib
import json
import sqlite3
import urllib.error
from pathlib import Path

import pytest

import asset_db
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


def test_catalog_release_asset_requires_matching_tag_size_and_digest():
    body = b'{"schema_version":2,"assets":[]}'
    release = {
        "tag_name": "v8.5.20",
        "assets": [{
            "name": workers._CATALOG_ASSET_NAME,
            "browser_download_url": (
                "https://github.com/SysAdminDoc/FileOrganizer/releases/download/"
                "v8.5.20/asset_fingerprints.json"
            ),
            "size": len(body),
            "digest": f"sha256:{hashlib.sha256(body).hexdigest()}",
        }],
    }

    url, digest = workers._select_catalog_release_asset(release)

    assert url.endswith("v8.5.20/asset_fingerprints.json")
    assert workers._verify_catalog_digest(body, digest) == hashlib.sha256(body).hexdigest()

    release["assets"][0]["digest"] = ""
    with pytest.raises(workers.CatalogSyncError) as error:
        workers._select_catalog_release_asset(release)
    assert error.value.code == "missing_digest"


def test_catalog_digest_mismatch_is_rejected_before_decode():
    with pytest.raises(workers.CatalogSyncError) as error:
        workers._verify_catalog_digest(b"tampered", "0" * 64)

    assert error.value.code == "digest_mismatch"


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


@pytest.mark.parametrize(
    "asset",
    [
        {"folder_fingerprint": "not-a-sha256", "files": []},
        {
            "folder_fingerprint": "a" * 64,
            "confidence": 101,
            "files": [],
        },
        {
            "folder_fingerprint": "a" * 64,
            "files": [{"p": "asset.bin", "s": 1, "h": "bad", "k": 0}],
        },
    ],
)
def test_catalog_schema_rejects_invalid_bounded_fields(asset):
    with pytest.raises(workers.CatalogSyncError) as error:
        workers._validate_catalog_payload({"schema_version": 2, "assets": [asset]})

    assert error.value.code == "invalid_schema"


def test_normal_catalog_worker_downloads_validates_and_imports(monkeypatch, tmp_path):
    download_url = (
        "https://github.com/SysAdminDoc/FileOrganizer/releases/download/"
        "v8.5.20/asset_fingerprints.json"
    )
    catalog = {
        "schema_version": 2,
        "assets": [{
            "folder_fingerprint": "a" * 64,
            "files": [],
        }],
    }
    catalog_raw = json.dumps(catalog).encode()
    release = {
        "published_at": "2026-08-10T12:00:00Z",
        "tag_name": "v8.5.20",
        "assets": [{
            "name": workers._CATALOG_ASSET_NAME,
            "browser_download_url": download_url,
            "size": len(catalog_raw),
            "digest": f"sha256:{hashlib.sha256(catalog_raw).hexdigest()}",
        }],
    }
    responses = [
        FakeResponse(
            json.dumps(release).encode(),
            content_length=len(json.dumps(release).encode()),
            url=workers._CATALOG_GITHUB_API,
        ),
        FakeResponse(
            catalog_raw,
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
        staticmethod(lambda *values, **options: persisted.append((values, options))),
    )

    results: list[tuple[bool, str]] = []
    worker = workers.CatalogSyncWorker()
    worker.finished.connect(lambda success, message: results.append((success, message)))
    worker.run()

    assert requested == [(workers._CATALOG_GITHUB_API, 10), (download_url, 30)]
    assert imported == [catalog]
    assert persisted
    assert persisted[0][1]["content_sha256"] == hashlib.sha256(catalog_raw).hexdigest()
    assert results == [(True, "Catalog updated from v8.5.20: +1 new assets, 0 already known")]


def test_disabled_catalog_sync_never_opens_the_network(monkeypatch, tmp_path):
    monkeypatch.setattr(workers, "_CATALOG_SYNC_FILE", str(tmp_path / "sync.json"))
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: pytest.fail("disabled sync attempted network access"),
    )
    results: list[tuple[bool, str]] = []
    worker = workers.CatalogSyncWorker(enabled=False)
    worker.finished.connect(lambda success, message: results.append((success, message)))

    worker.run()

    state = workers.load_catalog_sync_state()
    assert results == [(True, "Catalog sync disabled; using the local catalog")]
    assert state["last_status"] == "disabled"


def test_offline_catalog_sync_preserves_last_success(monkeypatch, tmp_path):
    sync_path = tmp_path / "sync.json"
    monkeypatch.setattr(workers, "_CATALOG_SYNC_FILE", str(sync_path))
    previous = {
        "schema_version": 1,
        "last_success_at": "2026-08-01T12:00:00Z",
        "last_tag": "v8.5.19",
        "content_sha256": "a" * 64,
    }
    workers._write_catalog_sync_state(previous)

    def offline(*_args, **_kwargs):
        raise urllib.error.URLError("fixture offline")

    monkeypatch.setattr("urllib.request.urlopen", offline)
    results: list[tuple[bool, str]] = []
    worker = workers.CatalogSyncWorker()
    worker.finished.connect(lambda success, message: results.append((success, message)))

    worker.run()

    state = workers.load_catalog_sync_state()
    assert results[0][0] is True
    assert "using local catalog" in results[0][1]
    assert state["last_status"] == "offline"
    assert state["last_success_at"] == previous["last_success_at"]
    assert state["content_sha256"] == previous["content_sha256"]


def _catalog_payload(fingerprint: str, name: str) -> dict:
    return {
        "schema_version": 2,
        "asset_count": 1,
        "assets": [{
            "folder_fingerprint": fingerprint,
            "clean_name": name,
            "category": "Fixtures",
            "confidence": 90,
            "file_count": 0,
            "total_bytes": 0,
            "files": [],
        }],
    }


def _asset_names(db_path: Path) -> list[str]:
    with sqlite3.connect(db_path) as connection:
        return [
            row[0]
            for row in connection.execute("SELECT clean_name FROM assets ORDER BY clean_name")
        ]


def test_atomic_catalog_import_preserves_local_rows_and_creates_backup(tmp_path):
    database = tmp_path / "catalog.db"
    asset_db.import_community_json(_catalog_payload("a" * 64, "Local"), str(database))

    result = asset_db.import_community_json_atomic(
        _catalog_payload("b" * 64, "Community"),
        str(database),
    )

    assert result == (1, 0)
    assert _asset_names(database) == ["Community", "Local"]
    backup = Path(f"{database}.community-backup")
    assert backup.exists()
    assert _asset_names(backup) == ["Local"]
    assert list(tmp_path.glob(".asset_fingerprints_*")) == []


def test_atomic_catalog_import_rolls_back_a_failed_post_swap_check(
    monkeypatch,
    tmp_path,
):
    database = tmp_path / "catalog.db"
    asset_db.import_community_json(_catalog_payload("a" * 64, "Local"), str(database))
    real_verify = asset_db._verify_community_database

    def fail_live_verification(path: str) -> None:
        if Path(path) == database:
            raise RuntimeError("injected post-swap verification failure")
        real_verify(path)

    monkeypatch.setattr(asset_db, "_verify_community_database", fail_live_verification)

    with pytest.raises(RuntimeError, match="post-swap"):
        asset_db.import_community_json_atomic(
            _catalog_payload("b" * 64, "Untrusted"),
            str(database),
        )

    assert _asset_names(database) == ["Local"]
    assert _asset_names(Path(f"{database}.community-backup")) == ["Local"]
    assert list(tmp_path.glob(".asset_fingerprints_*")) == []


def test_catalog_opt_out_and_last_success_are_visible_in_settings():
    root = Path(__file__).resolve().parents[1]
    config_source = (root / "fileorganizer" / "config.py").read_text(encoding="utf-8")
    dialog_source = (
        root / "fileorganizer" / "dialogs" / "settings.py"
    ).read_text(encoding="utf-8")
    window_source = (root / "fileorganizer" / "main_window.py").read_text(encoding="utf-8")

    for source in (config_source, dialog_source, window_source):
        assert "community_catalog_sync" in source
    assert "last_success_at" in dialog_source
