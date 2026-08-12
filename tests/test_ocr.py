"""Tests for the optional, bounded local OCR pipeline."""

from __future__ import annotations

from fileorganizer import ocr


def test_screenshot_detection_is_conservative():
    assert ocr.is_likely_screenshot("Screenshot 2026-08-12.png")
    assert ocr.is_likely_screenshot("invoice_scan.jpg")
    assert not ocr.is_likely_screenshot("IMG_20260812.jpg")


def test_extract_image_text_skips_non_screenshot_in_smart_mode(tmp_path, monkeypatch):
    image = tmp_path / "holiday.jpg"
    image.write_bytes(b"not a real image, but enough for the bounded path check")
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("smart mode should skip ordinary camera filenames")

    monkeypatch.setattr(ocr.subprocess, "run", fail_if_called)

    assert ocr.extract_image_text(image, image_mode="smart") == ""


def test_extract_image_text_sanitizes_and_bounds_tesseract_output(tmp_path, monkeypatch):
    image = tmp_path / "Screenshot.png"
    image.write_bytes(b"image")
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")

    class Completed:
        returncode = 0
        stdout = "  Project {name} <draft>  "

    calls = []

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Completed()

    monkeypatch.setattr(ocr.subprocess, "run", fake_run)

    result = ocr.extract_image_text(image, max_chars=50)

    assert result == "Project name draft"
    assert calls[0][0][:4] == ["tesseract", str(image), "stdout", "-l"]
    assert calls[0][1]["timeout"] == 20


def test_extract_ocr_skips_when_disabled(tmp_path, monkeypatch):
    image = tmp_path / "Screenshot.png"
    image.write_bytes(b"image")
    monkeypatch.setattr(ocr, "load_ocr_settings", lambda: {
        "enabled": False,
        "image_mode": "smart",
        "language": "eng",
        "max_chars": 4000,
        "timeout": 20,
        "max_pdf_pages": 3,
    })
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")

    assert ocr.extract_ocr(image) == ""


def test_scanned_pdf_requires_both_optional_binaries(tmp_path, monkeypatch):
    pdf = tmp_path / "scan.pdf"
    pdf.write_bytes(b"%PDF-1.4")
    monkeypatch.setattr(ocr, "find_tesseract", lambda: "tesseract")
    monkeypatch.setattr(ocr, "find_pdf_renderer", lambda: None)

    assert ocr.extract_scanned_pdf_text(pdf) == ""


def test_metadata_exposes_ocr_text_when_available(tmp_path, monkeypatch):
    image = tmp_path / "Screenshot.png"
    image.write_bytes(b"image")
    monkeypatch.setattr("fileorganizer.ocr.extract_ocr", lambda _path: "invoice total 42")

    result = __import__("fileorganizer.metadata", fromlist=["MetadataExtractor"]).MetadataExtractor._extract_image(
        str(image)
    )

    assert result["ocr_text"] == "invoice total 42"
