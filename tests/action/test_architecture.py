"""Unit tests for OpenCred architecture boundary enforcement script (scripts/check_architecture.py).

Tests architectural boundaries using fixture directories under tests/fixtures/arch/
without relying on the active repository source tree.
"""

from pathlib import Path

from scripts.check_architecture import run_checks

ARCH_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "arch"


def test_valid_architecture_fixtures_produce_no_violations() -> None:
    """Valid modules under core and cli produce 0 violations."""
    valid_root = ARCH_FIXTURES / "valid"
    violations = run_checks(valid_root)
    assert len(violations) == 0


def test_core_violations_detected() -> None:
    """Core module importing socket, typer, opencred.action, or urllib.request is flagged."""
    invalid_root = ARCH_FIXTURES / "invalid_core"
    violations = run_checks(invalid_root)
    assert len(violations) >= 4

    flagged_modules = {v.imported_module for v in violations}
    assert "socket" in flagged_modules
    assert "typer" in flagged_modules
    assert "opencred.action" in flagged_modules
    assert "urllib.request" in flagged_modules

    # Verify line numbers are correctly captured
    for v in violations:
        assert v.line_number > 0
        assert "bad_mod.py" in str(v.file_path)


def test_cli_violates_action_import() -> None:
    """CLI module importing opencred.action is flagged with line number."""
    invalid_root = ARCH_FIXTURES / "invalid_cli"
    violations = run_checks(invalid_root)
    assert len(violations) == 1
    v = violations[0]
    assert v.imported_module == "opencred.action.comment" or "opencred.action" in v.imported_module
    assert v.line_number == 2
    assert "bad_cli.py" in str(v.file_path)
