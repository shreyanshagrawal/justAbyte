"""Unit tests for GitHub workflow security validation script (scripts/check_workflows.py).

Verifies enforcement of security rules against fixture workflow files:
1. Every job has explicit timeout-minutes.
2. A workflow or job has explicit permissions block.
3. No step uses continue-on-error: true.
4. No workflow uses pull_request_target.
5. Any checkout step has persist-credentials: false (or explains credentials in comment).
"""

from pathlib import Path

from scripts.check_workflows import check_workflow_file

WORKFLOW_FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "workflows"


def test_valid_workflow_passes_cleanly() -> None:
    """Valid workflow fixture produces 0 violations."""
    fixture = WORKFLOW_FIXTURES / "valid_workflow.yml"
    violations = check_workflow_file(fixture)
    assert len(violations) == 0


def test_missing_timeout_flagged() -> None:
    """Job lacking timeout-minutes is detected and flagged."""
    fixture = WORKFLOW_FIXTURES / "missing_timeout.yml"
    violations = check_workflow_file(fixture)
    assert any(v.rule == "missing-timeout-minutes" for v in violations)


def test_missing_permissions_flagged() -> None:
    """Workflow lacking top-level and job-level permissions is flagged."""
    fixture = WORKFLOW_FIXTURES / "missing_permissions.yml"
    violations = check_workflow_file(fixture)
    assert any(v.rule == "missing-permissions" for v in violations)


def test_continue_on_error_flagged() -> None:
    """Step with continue-on-error: true is flagged."""
    fixture = WORKFLOW_FIXTURES / "continue_on_error.yml"
    violations = check_workflow_file(fixture)
    assert any(v.rule == "continue-on-error-forbidden" for v in violations)


def test_pull_request_target_flagged() -> None:
    """Workflow using pull_request_target trigger is flagged."""
    fixture = WORKFLOW_FIXTURES / "pull_request_target.yml"
    violations = check_workflow_file(fixture)
    assert any(v.rule == "pull-request-target-forbidden" for v in violations)


def test_insecure_checkout_lacking_persist_credentials_flagged() -> None:
    """actions/checkout lacking persist-credentials: false is flagged."""
    fixture = WORKFLOW_FIXTURES / "insecure_checkout.yml"
    violations = check_workflow_file(fixture)
    assert any(v.rule == "unsecured-checkout-credentials" for v in violations)


def test_checkout_without_persist_credentials_allowed_with_comment() -> None:
    """actions/checkout is allowed if file has a comment explaining why credentials are required."""
    fixture = WORKFLOW_FIXTURES / "checkout_with_comment.yml"
    violations = check_workflow_file(fixture)
    assert not any(v.rule == "unsecured-checkout-credentials" for v in violations)
