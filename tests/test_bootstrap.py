"""Regression tests for side-effect-free optional dependency detection."""

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP_PATH = REPO_ROOT / "fileorganizer" / "bootstrap.py"


def test_bootstrap_has_no_runtime_package_installation_path():
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }

    assert "subprocess" not in imported_modules
    assert "pip_failed.json" not in source
    assert "break-system-packages" not in source


def test_bootstrap_only_defines_optional_dependency_flags():
    source = BOOTSTRAP_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    function_names = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    assert "_bootstrap" not in function_names
    assert "_try_install" not in function_names
