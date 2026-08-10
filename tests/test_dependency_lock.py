from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def test_dependency_lock_is_hashed_and_targets_the_documented_baseline():
    lock = (REPO_ROOT / "requirements.lock").read_text(encoding="utf-8")

    assert "--python-version 3.10" in lock.splitlines()[1]
    assert "--python-platform x86_64-pc-windows-msvc" in lock.splitlines()[1]
    assert "--hash=sha256:" in lock
    assert "pillow==" in lock.lower()
    assert "py7zr==" in lock.lower()
    assert "fonttools==" in lock.lower()


def test_dependency_verifier_exposes_freshness_validation_and_audit_checks():
    source = (REPO_ROOT / "verify_dependencies.py").read_text(encoding="utf-8")

    assert '"--generate-hashes"' in source
    assert '"--require-hashes"' in source
    assert '"pip-audit"' in source
    assert "requirements.lock" in source
