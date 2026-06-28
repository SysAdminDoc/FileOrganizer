import json
from pathlib import Path

import raw_run


class FakeRaw:
    camera_model = "Fallback Model"

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeRawPy:
    @staticmethod
    def imread(_path):
        return FakeRaw()


def _events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_main_missing_rawpy_reports_deterministic_error(tmp_path, capsys):
    rc = raw_run.main(["--root", str(tmp_path)], rawpy_module_marker=None)

    events = _events(capsys)
    assert rc == 2
    assert events == [
        {
            "event": "error",
            "code": "missing_dependency",
            "message": "rawpy is required for RAW validation; install with: pip install rawpy",
        }
    ]


def test_extract_exif_uses_real_metadata_sources(monkeypatch, tmp_path):
    raw_file = tmp_path / "sample.dng"
    raw_file.write_bytes(b"raw")

    monkeypatch.setattr(raw_run, "_metadata_from_exifread", lambda _p: {
        "make": "Canon",
        "model": "EOS R5",
        "date_taken": "2025:12:31 23:59:58",
        "iso": "800",
        "focal_length": "85mm",
    })
    monkeypatch.setattr(raw_run, "_metadata_from_exiftool", lambda _p: {})

    meta = raw_run.extract_exif(str(raw_file), rawpy_module=FakeRawPy)

    assert meta["camera"] == "Canon EOS R5"
    assert meta["date_taken"] == "2025-12-31 23:59:58"
    assert meta["iso"] == "800"
    assert meta["focal_length"] == "85mm"
    assert meta["status"] == "OK"


def test_preview_emits_focal_length_without_placeholders(monkeypatch, tmp_path, capsys):
    raw_file = tmp_path / "sample.NEF"
    raw_file.write_bytes(b"raw")
    monkeypatch.setattr(raw_run, "extract_exif", lambda _p, rawpy_module=None: {
        "camera": "Nikon Z8",
        "make": "Nikon",
        "model": "Z8",
        "date_taken": "2026-02-03 04:05:06",
        "iso": "640",
        "focal_length": "35mm",
        "status": "OK",
    })

    rc = raw_run.scan_folder(str(tmp_path), "preview", rawpy_module=FakeRawPy)

    events = _events(capsys)
    file_event = next(e for e in events if e["event"] == "file")
    assert rc == 0
    assert file_event["filename"] == "sample.NEF"
    assert file_event["camera"] == "Nikon Z8"
    assert file_event["iso"] == "640"
    assert file_event["focal_length"] == "35mm"
    assert file_event["date_taken"] == "2026-02-03 04:05:06"


def test_organize_writes_dry_run_plan_without_moving(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source"
    dest_root = tmp_path / "organized"
    plan_path = tmp_path / "raw-plan.json"
    source.mkdir()
    raw_file = source / "portrait.cr2"
    raw_file.write_bytes(b"raw")
    monkeypatch.setattr(raw_run, "extract_exif", lambda _p, rawpy_module=None: {
        "camera": "Sony A7R V",
        "make": "Sony",
        "model": "A7R V",
        "date_taken": "2024-06-15 12:30:00",
        "iso": "100",
        "focal_length": "50mm",
        "status": "OK",
    })

    rc = raw_run.scan_folder(
        str(source),
        "organize",
        rawpy_module=FakeRawPy,
        dest_root=str(dest_root),
        plan_out=str(plan_path),
    )

    events = _events(capsys)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    item = plan["items"][0]
    assert rc == 0
    assert raw_file.exists()
    assert plan["dry_run"] is True
    assert item["source"] == str(raw_file)
    assert item["destination"].endswith(str(Path("2024") / "2024-06-15" / "Sony_A7R_V" / "portrait.cr2"))
    assert item["status"] == "planned"
    assert next(e for e in events if e["event"] == "plan")["path"] == str(plan_path)


def test_organize_apply_moves_file_after_plan(monkeypatch, tmp_path):
    source = tmp_path / "source"
    dest_root = tmp_path / "organized"
    source.mkdir()
    raw_file = source / "frame.dng"
    raw_file.write_bytes(b"raw")
    monkeypatch.setattr(raw_run, "extract_exif", lambda _p, rawpy_module=None: {
        "camera": "Fuji X-T5",
        "date_taken": "2023-01-02 03:04:05",
        "iso": "200",
        "focal_length": "23mm",
        "status": "OK",
    })

    rc = raw_run.scan_folder(
        str(source),
        "organize",
        rawpy_module=FakeRawPy,
        dest_root=str(dest_root),
        apply=True,
    )

    moved = dest_root / "2023" / "2023-01-02" / "Fuji_X-T5" / "frame.dng"
    assert rc == 0
    assert moved.exists()
    assert not raw_file.exists()


def test_organize_blocks_files_that_rawpy_cannot_validate(monkeypatch, tmp_path, capsys):
    source = tmp_path / "source"
    plan_path = tmp_path / "raw-plan.json"
    source.mkdir()
    raw_file = source / "broken.nef"
    raw_file.write_bytes(b"not raw")
    monkeypatch.setattr(raw_run, "extract_exif", lambda _p, rawpy_module=None: {
        "camera": "Unknown",
        "date_taken": "Unknown",
        "iso": "Unknown",
        "focal_length": "Unknown",
        "status": "Error: LibRawFileUnsupportedError",
    })

    rc = raw_run.scan_folder(
        str(source),
        "organize",
        rawpy_module=FakeRawPy,
        plan_out=str(plan_path),
    )

    events = _events(capsys)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert raw_file.exists()
    assert plan["items"][0]["status"] == "blocked: Error: LibRawFileUnsupportedError"
    final_progress = [e for e in events if e["event"] == "progress"][-1]
    assert final_progress["organized"] == 0
