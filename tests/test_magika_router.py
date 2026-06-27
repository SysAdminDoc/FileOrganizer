from __future__ import annotations

from pathlib import Path

from fileorganizer import magika_router


def test_detect_content_type_normalizes_magika_result(tmp_path, monkeypatch):
    sample = tmp_path / "asset.bin"
    sample.write_bytes(b"placeholder")

    class Output:
        mime_type = "application/zip"
        ct_label = "zip"
        description = "Zip archive"
        score = 0.99

    class Result:
        ok = True
        output = Output()

    class FakeMagika:
        def identify_path(self, path: Path):
            assert path == sample
            return Result()

    monkeypatch.setattr(magika_router, "_get_magika", lambda: FakeMagika())
    monkeypatch.setattr(magika_router, "_get_magic", lambda: None)

    hint = magika_router.detect_content_type(sample)

    assert hint is not None
    assert hint.mime_type == "application/zip"
    assert hint.label == "zip"
    assert hint.confidence == 0.99
    assert hint.source == "magika"


def test_extension_mismatch_reports_expected_extensions(tmp_path, monkeypatch):
    sample = tmp_path / "preview.jpg"
    sample.write_bytes(b"PK\x03\x04")

    monkeypatch.setattr(
        magika_router,
        "detect_content_type",
        lambda _path: magika_router.ContentTypeHint(
            label="zip",
            mime_type="application/zip",
            description="Zip archive",
            confidence=0.99,
            source="magika",
        ),
    )

    mismatch = magika_router.detect_extension_mismatch(sample)

    assert mismatch is not None
    assert mismatch["extension_mismatch"] is True
    assert mismatch["original_ext"] == ".jpg"
    assert mismatch["detected_exts"] == [".zip"]
    assert magika_router.is_obfuscated_archive(sample) is True


def test_route_by_mime_type_uses_canonical_categories(tmp_path, monkeypatch):
    sample = tmp_path / "photo.dat"
    sample.write_bytes(b"not really a jpeg")

    monkeypatch.setattr(
        magika_router,
        "detect_content_type",
        lambda _path: magika_router.ContentTypeHint(
            label="jpg",
            mime_type="image/jpeg",
            confidence=0.97,
            source="magika",
        ),
    )

    route = magika_router.route_by_mime_type(sample)

    assert route == ("Stock Photos - General", 88)
