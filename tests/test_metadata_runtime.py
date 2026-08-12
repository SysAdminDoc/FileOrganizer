"""Runtime smoke tests for optional metadata paths."""

from __future__ import annotations

import json
from zipfile import ZipFile

from fileorganizer import metadata


def test_metadata_capabilities_does_not_raise():
    capabilities = metadata.MetadataExtractor.capabilities()

    assert set(capabilities) == {
        "images", "audio", "video", "pdf", "docx", "xlsx", "ocr", "ocr_pdf",
    }


def test_archive_peeker_reads_zip_contents(tmp_path):
    archive = tmp_path / "assets.zip"
    with ZipFile(archive, "w") as handle:
        handle.writestr("preview.png", b"png")
        handle.writestr("notes.txt", b"notes")

    result = metadata.ArchivePeeker.peek(str(archive))

    assert result["file_count"] == 2
    assert result["total_size"] == len(b"png") + len(b"notes")
    assert result["extensions"][".png"] == 1
    assert result["extensions"][".txt"] == 1


def test_video_extractor_reads_ffprobe_output(monkeypatch):
    monkeypatch.setattr(metadata.winrt_metadata, "extract", lambda _path: {})
    monkeypatch.setattr(metadata.shutil, "which", lambda _name: "ffprobe")

    class Result:
        returncode = 0
        stdout = json.dumps(
            {
                "format": {"duration": "12.5"},
                "streams": [
                    {
                        "codec_type": "video",
                        "codec_name": "h264",
                        "width": 1920,
                        "height": 1080,
                        "r_frame_rate": "30000/1001",
                    }
                ],
            }
        )

    monkeypatch.setattr(metadata.subprocess, "run", lambda *args, **kwargs: Result())

    result = metadata.MetadataExtractor._extract_video("sample.mp4")

    assert result["duration"] == 12.5
    assert result["width"] == 1920
    assert result["height"] == 1080
    assert result["codec"] == "h264"
