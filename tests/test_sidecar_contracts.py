import json
import os
import re
import subprocess
import sys
from io import StringIO
from pathlib import Path

from fileorganizer.sidecar_protocol import (
    ALLOWED_EVENTS as PROTOCOL_EVENTS,
    MAX_RECORD_BYTES,
    MAX_STRING_LENGTH,
    PROTOCOL_VERSION,
    SidecarEmitter,
)


REPO_ROOT = Path(__file__).resolve().parents[1]

LIVE_NDJSON_SIDECARS = {
    "books_run.py": lambda missing, dest: ["--root", str(missing)],
    "cleanup_run.py": lambda missing, dest: ["--scanner", "empty_folders", "--root", str(missing)],
    "code_run.py": lambda missing, dest: ["--root", str(missing)],
    "comics_run.py": lambda missing, dest: ["--root", str(missing)],
    "dedup_run.py": lambda missing, dest: ["--root", str(missing)],
    "files_run.py": lambda missing, dest: ["--root", str(missing)],
    "fonts_run.py": lambda missing, dest: ["--root", str(missing)],
    "music_run.py": lambda missing, dest: ["--root", str(missing)],
    "photos_run.py": lambda missing, dest: ["--root", str(missing)],
    "raw_run.py": lambda missing, dest: ["--root", str(missing)],
    "smart_run.py": lambda missing, dest: ["--root", str(missing), "--dest", str(dest)],
    "subtitles_run.py": lambda missing, dest: ["--root", str(missing)],
    "video_run.py": lambda missing, dest: ["--root", str(missing)],
    "watch_run.py": lambda missing, dest: ["--watches", "not-json"],
    "clip_index_run.py": lambda missing, dest: ["--root", str(missing), "--db", str(dest / "clip.db")],
    "chroma_run.py": lambda missing, dest: ["--root", str(missing), "--db", str(dest / "chroma")],
    "vlm_run.py": lambda missing, dest: [
        "--root", str(missing), "--model", str(dest / "model.gguf"),
        "--mmproj", str(dest / "mmproj.gguf"),
    ],
}

ALLOWED_EVENTS = set(PROTOCOL_EVENTS)


def _run_sidecar(script: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    kwargs = {
        "cwd": REPO_ROOT,
        "text": True,
        "capture_output": True,
        "timeout": 20,
    }
    if os.name == "nt":
        kwargs["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script), *args],
        **kwargs,
    )


def _json_lines(stdout: str) -> list[dict]:
    rows = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def test_live_sidecars_emit_valid_ndjson_errors_for_fatal_inputs(tmp_path):
    missing = tmp_path / "missing"
    dest = tmp_path / "dest"
    dest.mkdir()

    for script, args_factory in LIVE_NDJSON_SIDECARS.items():
        completed = _run_sidecar(script, args_factory(missing, dest))
        rows = _json_lines(completed.stdout)

        assert completed.returncode != 0, script
        assert rows, script
        assert rows[0]["event"] == "handshake", script
        assert rows[0]["protocol_version"] == PROTOCOL_VERSION, script
        assert isinstance(rows[0].get("capabilities"), dict), script
        matrix = rows[0]["capabilities"].get("capability_matrix")
        assert isinstance(matrix, list) and matrix, script
        expected_workflow = {
            "dedup_run.py": "duplicates",
            "clip_index_run.py": "clip_index",
            "chroma_run.py": "chroma_index",
            "vlm_run.py": "vlm",
        }.get(script, script.removesuffix("_run.py"))
        assert {row["workflow"] for row in matrix} == {expected_workflow}, script
        assert [row["sequence"] for row in rows] == list(range(len(rows))), script
        assert all(row.get("protocol_version") == PROTOCOL_VERSION for row in rows), script
        assert all(len(json.dumps(row).encode("utf-8")) <= MAX_RECORD_BYTES for row in rows), script
        assert all(isinstance(row.get("event"), str) for row in rows), script
        errors = [row for row in rows if row.get("event") == "error"]
        assert errors, script
        assert all(error.get("code") and error.get("message") for error in errors), script
        terminal = [row for row in rows if row.get("terminal") is True]
        assert len(terminal) == 1, script
        assert terminal[0] is rows[-1], script


def test_capability_sidecar_exposes_full_preflight_before_terminal_event():
    completed = _run_sidecar("capabilities_run.py", ["--workflow", "all"])
    rows = _json_lines(completed.stdout)
    assert completed.returncode == 0
    assert [row["event"] for row in rows] == ["handshake", "summary", "complete"]
    matrix = rows[0]["capabilities"]["capability_matrix"]
    assert matrix == rows[1]["capability_matrix"]
    assert {row["status"] for row in matrix} <= {
        "available", "unavailable", "not_checked",
    }
    assert rows[-1]["terminal"] is True


def test_live_sidecars_do_not_runtime_install_dependencies():
    forbidden = [
        "subprocess.check_call",
        "pip install -q",
        '"-m", "pip", "install"',
        "'-m', 'pip', 'install'",
    ]

    for script in LIVE_NDJSON_SIDECARS:
        text = (REPO_ROOT / script).read_text(encoding="utf-8")
        for needle in forbidden:
            assert needle not in text, f"{script} contains runtime install path {needle!r}"


def test_live_sidecars_have_graceful_cancellation_event():
    for script in LIVE_NDJSON_SIDECARS:
        text = (REPO_ROOT / script).read_text(encoding="utf-8")
        assert "KeyboardInterrupt" in text, f"{script} does not handle KeyboardInterrupt"
        assert '"cancelled"' in text, f"{script} does not emit a cancelled code"


def test_live_sidecar_event_names_stay_in_contract():
    event_re = re.compile(r'"event"\s*:\s*"([^"]+)"|emit\(\s*"([^"]+)"|_emit\(\{\s*"event"\s*:\s*"([^"]+)"')

    for script in LIVE_NDJSON_SIDECARS:
        text = (REPO_ROOT / script).read_text(encoding="utf-8")
        events = {next(group for group in match.groups() if group) for match in event_re.finditer(text)}
        assert events, script
        assert events <= ALLOWED_EVENTS, f"{script} emits non-contract events: {sorted(events - ALLOWED_EVENTS)}"


def test_protocol_normalizes_progress_and_emits_one_terminal_record():
    stream = StringIO()
    emitter = SidecarEmitter("fixture", stream=stream)

    emitter.emit({"event": "start", "files_found": 4})
    emitter.emit({"event": "progress", "scanned": 2, "stage": "Scanning"})
    emitter.emit({"event": "complete", "total_count": 4})
    emitter.emit({"event": "error", "code": "late_error", "message": "ignored"})

    rows = _json_lines(stream.getvalue())
    assert [row["event"] for row in rows] == [
        "handshake", "start", "progress", "complete",
    ]
    assert rows[2]["current"] == 2
    assert rows[2]["total"] == 4
    assert rows[2]["percent"] == 50.0
    assert rows[-1]["terminal"] is True
    assert rows[-1]["status"] == "ok"


def test_protocol_isolates_invalid_and_unknown_records_as_bounded_logs():
    stream = StringIO()
    emitter = SidecarEmitter("fixture", stream=stream)

    emitter.emit({"event": "future_event", "message": "not supported"})
    emitter.emit({"event": "item", "status": "missing path"})
    emitter.emit({"event": "log", "level": "info", "message": "x" * (MAX_STRING_LENGTH + 99)})
    emitter.emit({"event": "error", "code": "cancelled", "message": "Cancelled."})

    rows = _json_lines(stream.getvalue())
    assert [row["event"] for row in rows] == [
        "handshake", "log", "log", "log", "error",
    ]
    assert rows[1]["code"] == "invalid_event"
    assert rows[2]["code"] == "invalid_event"
    assert len(rows[3]["message"]) == MAX_STRING_LENGTH
    assert rows[3]["protocol_truncated"] is True
    assert rows[-1]["status"] == "cancelled"
    assert rows[-1]["terminal"] is True


def test_winui_runners_use_the_shared_protocol_parser():
    services = REPO_ROOT / "src" / "FileOrganizer.UI" / "Services"
    parser_source = (services / "SidecarProtocol.cs").read_text(encoding="utf-8")
    assert f'public const string SupportedVersion = "{PROTOCOL_VERSION}"' in parser_source
    assert "AcceptLine" in parser_source
    assert "MaxRecordBytes" in parser_source
    for runner in ("PythonRunner.cs", "SidecarRunner.cs"):
        source = (services / runner).read_text(encoding="utf-8")
        assert "new SidecarProtocolSession" in source
        assert ".AcceptLine(line)" in source
