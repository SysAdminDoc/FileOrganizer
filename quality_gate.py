"""Run reproducible static-analysis checks against a non-increasing baseline."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version as package_version
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = ROOT / "quality-baseline.json"
DEFAULT_OUTPUT_DIRECTORY = ROOT / "artifacts" / "quality"
WINDOWS_CREATION_FLAGS = (
    getattr(subprocess, "CREATE_NO_WINDOW", 0)
    | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    if sys.platform == "win32"
    else 0
)


@dataclass(frozen=True)
class FindingCounts:
    errors: int
    warnings: int = 0


@dataclass(frozen=True)
class ToolSpec:
    distribution: str
    arguments: tuple[str, ...]
    parser: Callable[[str], FindingCounts]
    report_extension: str


def parse_ruff_output(output: str) -> FindingCounts:
    payload: Any = json.loads(output)
    if not isinstance(payload, list):
        raise ValueError("Ruff JSON output must be a list")
    return FindingCounts(errors=len(payload))


def parse_mypy_output(output: str) -> FindingCounts:
    return FindingCounts(
        errors=sum(1 for line in output.splitlines() if ": error:" in line)
    )


def parse_pyright_output(output: str) -> FindingCounts:
    payload: Any = json.loads(output)
    if not isinstance(payload, dict):
        raise ValueError("pyright JSON output must be an object")
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        raise ValueError("pyright JSON output is missing its summary")
    errors = summary.get("errorCount")
    warnings = summary.get("warningCount")
    if not isinstance(errors, int) or not isinstance(warnings, int):
        raise ValueError("pyright summary contains invalid finding counts")
    return FindingCounts(errors=errors, warnings=warnings)


TOOL_SPECS: dict[str, ToolSpec] = {
    "ruff": ToolSpec(
        distribution="ruff",
        arguments=("-m", "ruff", "check", ".", "--output-format=json"),
        parser=parse_ruff_output,
        report_extension="json",
    ),
    "mypy": ToolSpec(
        distribution="mypy",
        arguments=(
            "-m",
            "mypy",
            "--python-version",
            "3.10",
            "--no-site-packages",
            "--ignore-missing-imports",
            "--no-pretty",
            "--no-color-output",
            ".",
        ),
        parser=parse_mypy_output,
        report_extension="txt",
    ),
    "pyright": ToolSpec(
        distribution="pyright",
        arguments=(
            "-m",
            "pyright",
            "--pythonversion",
            "3.10",
            "--pythonplatform",
            "Windows",
            "--outputjson",
        ),
        parser=parse_pyright_output,
        report_extension="json",
    ),
}


def compare_counts(
    tool_name: str,
    actual: FindingCounts,
    baseline: FindingCounts,
) -> list[str]:
    failures: list[str] = []
    for metric in ("errors", "warnings"):
        actual_count = getattr(actual, metric)
        baseline_count = getattr(baseline, metric)
        if actual_count > baseline_count:
            failures.append(
                f"{tool_name} {metric} increased from "
                f"{baseline_count} to {actual_count}"
            )
        elif actual_count < baseline_count:
            failures.append(
                f"{tool_name} {metric} improved from {baseline_count} to "
                f"{actual_count}; lower quality-baseline.json in the same change"
            )
    return failures


def _require_mapping(value: object, context: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError(f"{context} must be a JSON object")
    return value


def _require_integer(record: Mapping[str, object], key: str, context: str) -> int:
    value = record.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{context}.{key} must be an integer")
    return value


def load_baseline(path: Path) -> dict[str, tuple[str, FindingCounts]]:
    payload = _require_mapping(json.loads(path.read_text(encoding="utf-8")), "baseline")
    if payload.get("schema_version") != 1 or payload.get("python_version") != "3.10":
        raise ValueError("Unsupported quality baseline schema or Python version")
    tools = _require_mapping(payload.get("tools"), "baseline.tools")
    baseline: dict[str, tuple[str, FindingCounts]] = {}
    for tool_name in TOOL_SPECS:
        record = _require_mapping(tools.get(tool_name), f"baseline.tools.{tool_name}")
        expected_version = record.get("version")
        if not isinstance(expected_version, str) or not expected_version:
            raise ValueError(f"baseline.tools.{tool_name}.version must be a string")
        baseline[tool_name] = (
            expected_version,
            FindingCounts(
                errors=_require_integer(record, "errors", tool_name),
                warnings=_require_integer(record, "warnings", tool_name),
            ),
        )
    return baseline


def run_quality_gate(
    selected_tools: Sequence[str],
    baseline_path: Path,
    output_directory: Path,
) -> int:
    baseline = load_baseline(baseline_path)
    output_directory.mkdir(parents=True, exist_ok=True)
    failures: list[str] = []
    report_tools: dict[str, object] = {}

    for tool_name in selected_tools:
        spec = TOOL_SPECS[tool_name]
        expected_version, expected_counts = baseline[tool_name]
        try:
            installed_version = package_version(spec.distribution)
        except PackageNotFoundError:
            installed_version = "missing"

        command = [sys.executable, *spec.arguments]
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=WINDOWS_CREATION_FLAGS,
        )
        raw_path = output_directory / f"{tool_name}.{spec.report_extension}"
        raw_path.write_text(completed.stdout, encoding="utf-8")
        if completed.stderr:
            (output_directory / f"{tool_name}.stderr.txt").write_text(
                completed.stderr,
                encoding="utf-8",
            )

        tool_failures: list[str] = []
        if installed_version != expected_version:
            tool_failures.append(
                f"{tool_name} version is {installed_version}; expected {expected_version}"
            )
        if completed.returncode not in (0, 1):
            tool_failures.append(
                f"{tool_name} failed to run (exit {completed.returncode})"
            )

        counts: FindingCounts | None = None
        try:
            counts = spec.parser(completed.stdout)
        except (json.JSONDecodeError, ValueError) as exc:
            tool_failures.append(f"{tool_name} output could not be parsed: {exc}")
        if counts is not None:
            tool_failures.extend(
                compare_counts(tool_name, counts, expected_counts)
            )

        failures.extend(tool_failures)
        report_tools[tool_name] = {
            "version": installed_version,
            "exit_code": completed.returncode,
            "counts": (
                {"errors": counts.errors, "warnings": counts.warnings}
                if counts is not None
                else None
            ),
            "baseline": {
                "errors": expected_counts.errors,
                "warnings": expected_counts.warnings,
            },
            "failures": tool_failures,
        }

        if counts is None:
            print(f"{tool_name}: unable to read findings")
        else:
            print(
                f"{tool_name}: {counts.errors} error(s), "
                f"{counts.warnings} warning(s)"
            )

    summary = {
        "schema_version": 1,
        "success": not failures,
        "tools": report_tools,
        "failures": failures,
    }
    (output_directory / "quality-summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for failure in failures:
        print(f"QUALITY GATE: {failure}", file=sys.stderr)
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="append",
        choices=tuple(TOOL_SPECS),
        dest="checks",
        help="Run only this checker (repeatable). Defaults to every checker.",
    )
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    selected_tools: Sequence[str] = arguments.checks or tuple(TOOL_SPECS)
    return run_quality_gate(
        selected_tools,
        arguments.baseline.resolve(),
        arguments.output_dir.resolve(),
    )


if __name__ == "__main__":
    raise SystemExit(main())
