import json
import re
import subprocess
import sys
from pathlib import Path


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
}

ALLOWED_EVENTS = {
    "start",
    "progress",
    "item",
    "group",
    "summary",
    "file",
    "comic",
    "plan",
    "complete",
    "error",
    "watching",
    "detected",
    "heartbeat",
}


def _run_sidecar(script: str, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / script), *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        timeout=20,
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
        assert all(isinstance(row.get("event"), str) for row in rows), script
        errors = [row for row in rows if row.get("event") == "error"]
        assert errors, script
        assert all(error.get("code") and error.get("message") for error in errors), script


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
