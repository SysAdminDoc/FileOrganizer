from pathlib import Path
from types import SimpleNamespace

from fileorganizer import capabilities
from fileorganizer import xmp_sidecar as xmp


def test_confidence_rating_uses_one_to_five_stars():
    assert [xmp.confidence_rating(value) for value in (-1, 0, 1, 20, 21, 40, 60, 80, 81, 100, 101)] == [
        1, 1, 1, 1, 2, 2, 3, 4, 5, 5, 5
    ]


def test_build_xmp_tags_contains_requested_ai_and_compatibility_fields():
    tags = xmp.build_xmp_tags(
        category="Photos - Events",
        confidence=86,
        prompt_information="category=Photos - Events; evidence=filename",
        prompt_writer_name="operator",
        subjects=["holiday", "holiday", "family"],
    )

    assert tags[xmp.AI_SYSTEM_TAG] == "FileOrganizer v8.x"
    assert tags[xmp.AI_PROMPT_TAG].startswith("category=Photos")
    assert tags[xmp.AI_WRITER_TAG] == "operator"
    assert tags[xmp.SUBJECT_TAG] == ["Photos - Events", "holiday", "family"]
    assert tags[xmp.RATING_TAG] == 5
    assert tags[xmp.CATEGORY_TAG] == "Photos - Events"


def test_sidecar_writer_is_fail_closed_when_exiftool_is_unavailable(tmp_path, monkeypatch):
    asset = tmp_path / "photo.jpg"
    asset.write_bytes(b"original")
    monkeypatch.setattr(
        xmp,
        "probe_exiftool",
        lambda *args, **kwargs: {
            "available": False,
            "path": "",
            "version": "",
            "reason": "test tool unavailable",
        },
    )

    result = xmp.write_xmp_sidecar(
        asset,
        category="Photos",
        confidence=75,
        prompt_information="test",
    )

    assert result.status == "unavailable"
    assert result.sidecar_path == str(asset.with_suffix(".xmp"))
    assert not Path(result.sidecar_path).exists()
    assert asset.read_bytes() == b"original"


def test_sidecar_writer_creates_then_updates_only_the_xmp_file(tmp_path, monkeypatch):
    asset = tmp_path / "photo.jpg"
    asset.write_bytes(b"original")
    calls = []

    class FakeExifTool:
        def __init__(self, *, executable):
            self.executable = executable

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def execute(self, *args):
            calls.append(args)
            if "-o" in args:
                output = Path(args[args.index("-o") + 1])
            else:
                output = Path(args[-1])
            output.write_text("xmp", encoding="utf-8")
            return "1 image files updated"

    fake_module = SimpleNamespace(ExifTool=FakeExifTool)
    monkeypatch.setattr(
        xmp,
        "probe_exiftool",
        lambda *args, **kwargs: {
            "available": True,
            "path": "exiftool.exe",
            "version": "12.76",
            "reason": "available",
        },
    )

    first = xmp.write_xmp_sidecar(
        asset,
        category="Photos",
        confidence=63,
        prompt_information="reason",
        subjects=["event"],
        exiftool_module=fake_module,
    )
    second = xmp.write_xmp_sidecar(
        asset,
        category="Photos",
        confidence=91,
        prompt_information="updated reason",
        exiftool_module=fake_module,
    )

    assert first.ok and second.ok
    assert len(calls) == 2
    assert "-o" in calls[0]
    assert "-o" not in calls[1]
    assert "-XMP-iptcExt:AISystemUsed=FileOrganizer v8.x" in calls[0]
    assert "-XMP-iptcExt:AIPromptInformation=reason" in calls[0]
    assert "-XMP-dc:Subject+=Photos" in calls[0]
    assert "-XMP-dc:Subject+=event" in calls[0]
    assert "-XMP-xmp:Rating=4" in calls[0]
    assert "-photoshop:Category=Photos" in calls[0]
    assert asset.read_bytes() == b"original"
    assert Path(first.sidecar_path).read_text(encoding="utf-8") == "xmp"


def test_metadata_capability_declares_wrapper_and_binary_requirement():
    row = capabilities.get_capability("metadata", "xmp_sidecar_write")
    assert "PyExifTool" in row["dependency"]
    assert "ExifTool" in row["dependency"]
    assert "12.15" in row["remediation"]
