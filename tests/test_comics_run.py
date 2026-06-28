import io
import json
import tarfile
import zipfile
from pathlib import Path

from PIL import Image

import comics_run


def _png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), (20, 40, 80)).save(buf, format="PNG")
    return buf.getvalue()


def _write_cbz(path: Path, entry: str = "001.png") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(entry, _png_bytes())


def _write_cbt(path: Path, entry: str = "001.png") -> None:
    data = _png_bytes()
    info = tarfile.TarInfo(entry)
    info.size = len(data)
    with tarfile.open(path, "w") as tf:
        tf.addfile(info, io.BytesIO(data))


def _events(capsys):
    return [json.loads(line) for line in capsys.readouterr().out.splitlines() if line.strip()]


def test_parse_comic_filename_extracts_publisher_and_issue():
    meta = comics_run.parse_comic_filename("Batman #001 (DC) (2011).cbz")

    assert meta == {
        "series": "Batman",
        "volume": "#001",
        "publisher": "DC",
        "year": "2011",
    }


def test_preview_validates_cbz_and_cbt_without_extracting(tmp_path, capsys):
    _write_cbz(tmp_path / "Batman #001 (DC) (2011).cbz")
    _write_cbt(tmp_path / "Saga #002 (Image) (2012).cbt")

    rc = comics_run.scan_folder(str(tmp_path), "preview")

    events = _events(capsys)
    comic_events = [event for event in events if event["event"] == "comic"]
    assert rc == 0
    assert {event["filename"] for event in comic_events} == {
        "Batman #001 (DC) (2011).cbz",
        "Saga #002 (Image) (2012).cbt",
    }
    assert all(event["status"] == "OK" for event in comic_events)
    assert all(event["pages"] == 1 for event in comic_events)
    assert not (tmp_path / "001.png").exists()


def test_preview_surfaces_unsafe_and_corrupt_archives(tmp_path, capsys):
    _write_cbz(tmp_path / "Unsafe #001.cbz", "../001.png")
    (tmp_path / "Broken #001.cbz").write_bytes(b"not a zip")

    rc = comics_run.scan_folder(str(tmp_path), "preview")

    events = _events(capsys)
    by_name = {event["filename"]: event for event in events if event["event"] == "comic"}
    assert rc == 0
    assert by_name["Unsafe #001.cbz"]["status"].startswith("Unsafe archive entry")
    assert by_name["Broken #001.cbz"]["status"].startswith("Corrupt archive")


def test_cbr_and_cb7_missing_dependencies_are_item_errors(monkeypatch, tmp_path):
    cbr = tmp_path / "Series #001.cbr"
    cb7 = tmp_path / "Series #002.cb7"
    cbr.write_bytes(b"rar")
    cb7.write_bytes(b"7z")
    monkeypatch.setattr(comics_run, "_load_rarfile", lambda: None)
    monkeypatch.setattr(comics_run, "_load_py7zr", lambda: None)

    cbr_result = comics_run.inspect_comic_archive(str(cbr))
    cb7_result = comics_run.inspect_comic_archive(str(cb7))

    assert cbr_result["status"] == "Missing dependency: rarfile"
    assert cb7_result["status"] == "Missing dependency: py7zr"


def test_organize_writes_dry_run_plan_without_moving(tmp_path, capsys):
    source = tmp_path / "source"
    dest_root = tmp_path / "organized"
    plan_path = tmp_path / "comic-plan.json"
    source.mkdir()
    comic = source / "Batman #001 (DC) (2011).cbz"
    _write_cbz(comic)

    rc = comics_run.scan_folder(
        str(source),
        "organize",
        dest_root=str(dest_root),
        plan_out=str(plan_path),
    )

    events = _events(capsys)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    item = plan["items"][0]
    assert rc == 0
    assert comic.exists()
    assert plan["dry_run"] is True
    assert item["source"] == str(comic)
    assert item["destination"].endswith(str(Path("Comics") / "DC" / "Batman" / comic.name))
    assert item["status"] == "planned"
    assert next(event for event in events if event["event"] == "plan")["path"] == str(plan_path)


def test_organize_apply_moves_valid_archive(tmp_path):
    source = tmp_path / "source"
    dest_root = tmp_path / "organized"
    source.mkdir()
    comic = source / "Saga #002 (Image) (2012).cbz"
    _write_cbz(comic)

    rc = comics_run.scan_folder(
        str(source),
        "organize",
        dest_root=str(dest_root),
        apply=True,
    )

    moved = dest_root / "Comics" / "Image" / "Saga" / comic.name
    assert rc == 0
    assert moved.exists()
    assert not comic.exists()


def test_organize_blocks_corrupt_archives_in_plan(tmp_path, capsys):
    source = tmp_path / "source"
    plan_path = tmp_path / "comic-plan.json"
    source.mkdir()
    comic = source / "Broken #001.cbz"
    comic.write_bytes(b"not a zip")

    rc = comics_run.scan_folder(str(source), "organize", plan_out=str(plan_path))

    events = _events(capsys)
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    assert rc == 0
    assert comic.exists()
    assert plan["items"][0]["status"].startswith("blocked: Corrupt archive")
    final_progress = [event for event in events if event["event"] == "progress"][-1]
    assert final_progress["organized"] == 0
