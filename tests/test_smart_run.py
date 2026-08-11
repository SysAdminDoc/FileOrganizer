import json
import sys


def _events(stdout: str) -> list[dict]:
    return [json.loads(line) for line in stdout.splitlines() if line.strip()]


def test_preview_accepts_multiple_source_roots_and_reserves_collisions(tmp_path, monkeypatch, capsys):
    import smart_run

    first = tmp_path / "first"
    second = tmp_path / "second"
    destination = tmp_path / "organized"
    first.mkdir()
    second.mkdir()
    (first / "notes.txt").write_text("one", encoding="utf-8")
    (second / "notes.txt").write_text("two", encoding="utf-8")

    smart_run._PROTOCOL.reset()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart_run.py",
            "--root",
            str(first),
            "--root",
            str(second),
            "--dest",
            str(destination),
            "--mode",
            "preview",
        ],
    )

    assert smart_run.main() == 0
    rows = _events(capsys.readouterr().out)
    start = next(row for row in rows if row["event"] == "start")
    items = [row for row in rows if row["event"] == "item"]

    assert start["root"] == [str(first), str(second)]
    assert len(items) == 2
    assert len({row["new_path"] for row in items}) == 2
    assert any(row["new_path"].endswith("notes (1).txt") for row in items)


def test_apply_rejects_overlapping_source_roots(tmp_path, monkeypatch, capsys):
    import smart_run

    parent = tmp_path / "parent"
    child = parent / "child"
    destination = tmp_path / "organized"
    child.mkdir(parents=True)
    destination.mkdir()

    smart_run._PROTOCOL.reset()
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "smart_run.py",
            "--root",
            str(parent),
            "--root",
            str(child),
            "--dest",
            str(destination),
            "--mode",
            "apply",
        ],
    )

    assert smart_run.main() == 5
    rows = _events(capsys.readouterr().out)
    error = next(row for row in rows if row["event"] == "error")
    assert error["code"] == "unsafe_roots"
