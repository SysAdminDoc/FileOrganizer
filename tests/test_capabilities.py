import json
from io import StringIO

from fileorganizer import capabilities
from fileorganizer.sidecar_protocol import SidecarEmitter


REQUIRED_FIELDS = {
    "schema_version",
    "workflow",
    "capability",
    "dependency",
    "detected_version",
    "scope",
    "online_required",
    "required",
    "status",
    "detail",
    "remediation",
}


def _lines(stream: StringIO) -> list[dict]:
    return [json.loads(line) for line in stream.getvalue().splitlines() if line]


def test_full_capability_matrix_is_deterministic_and_schema_complete():
    first = capabilities.capability_matrix("all")
    second = capabilities.capability_matrix("all")
    assert first == second
    assert first == sorted(first, key=lambda row: (row["workflow"], row["capability"]))
    assert {row["workflow"] for row in first} >= {
        "organize", "smart", "files", "cleanup", "duplicates", "music",
        "video", "books", "fonts", "code", "subtitles", "photos", "raw",
        "comics", "watch",
        "toolbox",
    }
    for row in first:
        assert REQUIRED_FIELDS == set(row)
        assert row["schema_version"] == capabilities.SCHEMA_VERSION
        assert row["status"] in capabilities.VALID_STATUSES
        assert row["dependency"]
        assert row["detected_version"]
        assert row["scope"]
        assert row["remediation"]


def test_clean_environment_reports_unavailable_not_no_findings(monkeypatch):
    monkeypatch.setattr(capabilities, "_module_available", lambda _module: False)
    monkeypatch.setattr(capabilities, "_binary_path", lambda _binary: None)
    rows = capabilities.capability_matrix("all")
    optional = [row for row in rows if row["dependency"] != "Python standard library"]
    builtins = [row for row in rows if row["dependency"] == "Python standard library"]
    assert optional and builtins
    assert {row["status"] for row in optional} == {"unavailable"}
    assert {row["status"] for row in builtins} == {"available"}
    assert all("not detected" in row["detail"].lower() or row["detail"] for row in optional)


def test_online_capability_remains_not_checked_when_local_dependencies_exist(monkeypatch):
    monkeypatch.setattr(
        capabilities,
        "_probe_requirement",
        lambda requirement: (True, f"{requirement.label} test-version"),
    )
    rows = [row for row in capabilities.capability_matrix("all") if row["online_required"]]
    assert rows
    assert {row["status"] for row in rows} == {"not_checked"}
    assert all("network" in row["detail"].lower() for row in rows)


def test_sidecar_handshake_exposes_only_its_workflow_matrix():
    stream = StringIO()
    emitter = SidecarEmitter("books", stream=stream)
    emitter.emit({"event": "complete", "total_count": 0})
    rows = _lines(stream)
    matrix = rows[0]["capabilities"]["capability_matrix"]
    assert rows[0]["event"] == "handshake"
    assert matrix
    assert {row["workflow"] for row in matrix} == {"books"}
    assert all(REQUIRED_FIELDS == set(row) for row in matrix)


def test_capability_error_uses_shared_terminal_schema(monkeypatch):
    monkeypatch.setattr(capabilities, "_module_available", lambda _module: False)
    stream = StringIO()
    emitter = SidecarEmitter("fonts", stream=stream)
    emitter.emit_capability_error("font_metadata")
    error = _lines(stream)[-1]
    assert error["event"] == "error"
    assert error["code"] == "capability_unavailable"
    assert error["terminal"] is True
    assert error["capability_health"]["workflow"] == "fonts"
    assert error["capability_health"]["capability"] == "font_metadata"
    assert error["capability_health"]["status"] == "unavailable"
    assert REQUIRED_FIELDS == set(error["capability_health"])


def test_unknown_workflow_is_an_explicit_empty_matrix():
    assert capabilities.capability_matrix("does-not-exist") == []
