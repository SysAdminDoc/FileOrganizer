from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

import quality_gate


def test_machine_readable_checker_outputs_are_counted() -> None:
    assert quality_gate.parse_ruff_output('[{"code": "F821"}, {"code": "E501"}]') == (
        quality_gate.FindingCounts(errors=2)
    )
    assert quality_gate.parse_mypy_output(
        "module.py:1: error: broken [assignment]\nmodule.py:1: note: context\n"
    ) == quality_gate.FindingCounts(errors=1)
    assert quality_gate.parse_pyright_output(
        json.dumps({"summary": {"errorCount": 3, "warningCount": 2}})
    ) == quality_gate.FindingCounts(errors=3, warnings=2)


@pytest.mark.parametrize(
    ("actual", "expected_fragment"),
    [
        (quality_gate.FindingCounts(11, 2), "errors increased"),
        (quality_gate.FindingCounts(9, 2), "lower quality-baseline.json"),
        (quality_gate.FindingCounts(10, 3), "warnings increased"),
    ],
)
def test_ratchet_rejects_regressions_and_stale_higher_baselines(
    actual: quality_gate.FindingCounts,
    expected_fragment: str,
) -> None:
    failures = quality_gate.compare_counts(
        "fixture",
        actual,
        quality_gate.FindingCounts(10, 2),
    )
    assert any(expected_fragment in failure for failure in failures)


def test_ratchet_accepts_an_exact_baseline() -> None:
    counts = quality_gate.FindingCounts(10, 2)
    assert quality_gate.compare_counts("fixture", counts, counts) == []


def test_checked_in_baseline_covers_every_tool() -> None:
    baseline = quality_gate.load_baseline(
        Path(__file__).resolve().parents[1] / "quality-baseline.json"
    )
    assert set(baseline) == set(quality_gate.TOOL_SPECS)


def test_ci_workflow_runs_all_release_gates() -> None:
    workflow_path = (
        Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"
    )
    workflow = workflow_path.read_text(encoding="utf-8")
    assert isinstance(yaml.safe_load(workflow), dict)
    for required in (
        "windows-2025-vs2026",
        "python -m pytest",
        "python quality_gate.py",
        "SidecarProtocol.ContractTests.csproj",
        "src/build.ps1 -Configuration Release",
        "actions/upload-artifact@v7",
    ):
        assert required in workflow
