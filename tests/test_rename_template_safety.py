import json
import subprocess
import sys
from pathlib import Path

import pytest

from fileorganizer.path_safety import (
    PathSafetyError,
    resolve_rename_destination,
    unique_rename_destination,
    validate_rename_template,
)


SIDECARS = (
    ("music_run.py", {"albumartist", "year", "album", "disc", "track", "title", "ext"}),
    ("video_run.py", {"title", "year", "season", "episode", "ext"}),
    ("books_run.py", {"author", "title", "series", "series_index", "ext"}),
    ("fonts_run.py", {"family", "style", "weight", "ext"}),
    ("code_run.py", {"language", "name"}),
    ("photos_run.py", {"year", "month", "day", "name", "ext"}),
)


@pytest.mark.parametrize(
    ("template", "fields"),
    [
        ("Music/{albumartist}/{year} - {album}/{disc:02}-{track:02} {title}.{ext}", SIDECARS[0][1]),
        ("Movies/{title} ({year})/Season {season:02}/{title} - S{season:02}E{episode:02}.{ext}", SIDECARS[1][1]),
        ("Books/{author}/{series} #{series_index:g} - {title}.{ext}", SIDECARS[2][1]),
        ("Fonts/{family}/{family} - {style}.{ext}", SIDECARS[3][1]),
        ("Code/{language}/{name}", SIDECARS[4][1]),
        ("Pictures/{year}/{year}-{month:02}-{day:02}/{name}.{ext}", SIDECARS[5][1]),
    ],
)
def test_documented_templates_are_valid(template, fields):
    assert validate_rename_template(template, fields) == template


@pytest.mark.parametrize(
    "template",
    [
        "../outside/{title}",
        r"..\outside\{title}",
        r"C:\outside\{title}",
        r"\\server\share\{title}",
        "/outside/{title}",
        "safe//{title}",
        "safe/{title}/../outside",
        "{title.__class__}",
        "{title[0]}",
        "{unknown}",
        "{title!r}",
        "{title:{width}}",
        "CON/{title}",
    ],
)
def test_unsafe_templates_fail_closed(template):
    with pytest.raises(PathSafetyError):
        validate_rename_template(template, {"title"})


@pytest.mark.parametrize("relative", ["../outside.txt", r"C:\outside.txt", r"\\server\share\x.txt"])
def test_formatted_destination_cannot_escape_root(tmp_path, relative):
    root = tmp_path / "organized"
    root.mkdir()
    with pytest.raises(PathSafetyError):
        resolve_rename_destination(root, relative)


def test_collision_uses_a_unique_suffix_without_overwriting(tmp_path):
    root = tmp_path / "organized"
    source_root = tmp_path / "source"
    root.mkdir()
    source_root.mkdir()
    source = source_root / "song.mp3"
    source.write_bytes(b"source")
    candidate = root / "song.mp3"
    candidate.write_bytes(b"existing")

    selected = unique_rename_destination(candidate, source)

    assert Path(selected) == root / "song (2).mp3"
    assert candidate.read_bytes() == b"existing"


@pytest.mark.parametrize("script,fields", SIDECARS)
def test_each_specialized_sidecar_rejects_unsafe_pattern(tmp_path, script, fields):
    root = tmp_path / "source"
    root.mkdir()
    result = subprocess.run(
        [
            sys.executable,
            str(Path(__file__).parents[1] / script),
            "--root",
            str(root),
            "--rename-pattern",
            "../outside/{title}",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    events = [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    assert events and events[0]["event"] == "handshake"
    error = next(event for event in events if event["event"] == "error")
    assert error["code"] == "invalid_rename_pattern"
    assert error["terminal"] is True
    assert not (tmp_path / "outside").exists()
