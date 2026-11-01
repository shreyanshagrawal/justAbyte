#!/usr/bin/env python3
"""Validate GitHub Actions workflows in .github/workflows/ using PyYAML.

Enforces workflow security and configuration constraints:
1. Every job must have explicit `timeout-minutes`.
2. A workflow or job must have an explicit `permissions` block.
3. No step may use `continue-on-error: true`.
4. No workflow may use `pull_request_target`.
5. Any checkout step (uses actions/checkout) must have `persist-credentials: false`,
   unless a comment in the file explains why credentials are needed.

Prints each violation with file path and description, and exits 1 if violations exist.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]


class WorkflowViolation:
    """Represents a workflow linting or security policy violation."""

    def __init__(self, file_path: Path, rule: str, details: str):
        self.file_path = file_path
        self.rule = rule
        self.details = details

    def __str__(self) -> str:
        return f"{self.file_path}: [{self.rule}] {self.details}"


def _has_persist_credentials_comment(file_content: str) -> bool:
    """Check if the workflow file contains an explanatory comment for persist-credentials."""
    lower = file_content.lower()
    return "persist-credentials" in lower and (
        "credentials needed" in lower
        or "why credentials" in lower
        or "credentials are required" in lower
        or "credential explanation" in lower
    )


def check_workflow_file(file_path: Path) -> list[WorkflowViolation]:
    """Parse and validate a single GitHub workflow file."""
    violations: list[WorkflowViolation] = []
    try:
        content = file_path.read_text(encoding="utf-8")
        data: Any = yaml.safe_load(content)
    except Exception as err:
        violations.append(WorkflowViolation(file_path, "yaml-parse-error", str(err)))
        return violations

    if not isinstance(data, dict):
        violations.append(
            WorkflowViolation(file_path, "invalid-structure", "Workflow root is not a dictionary")
        )
        return violations

    # Check 4: No workflow may use pull_request_target trigger
    on_trigger = data.get("on") or data.get(True)  # PyYAML parses unquoted 'on:' as boolean True!
    if on_trigger == "pull_request_target":
        violations.append(
            WorkflowViolation(
                file_path,
                "pull-request-target-forbidden",
                "Workflow trigger 'on' uses forbidden 'pull_request_target'",
            )
        )
    elif isinstance(on_trigger, list) and "pull_request_target" in on_trigger:
        violations.append(
            WorkflowViolation(
                file_path,
                "pull-request-target-forbidden",
                "Workflow trigger 'on' list contains forbidden 'pull_request_target'",
            )
        )
    elif isinstance(on_trigger, dict) and "pull_request_target" in on_trigger:
        violations.append(
            WorkflowViolation(
                file_path,
                "pull-request-target-forbidden",
                "Workflow trigger 'on' dictionary contains forbidden 'pull_request_target'",
            )
        )

    # Check 2: Top-level permissions or job-level permissions
    top_permissions = data.get("permissions")
    jobs = data.get("jobs", {})

    if not isinstance(jobs, dict):
        violations.append(
            WorkflowViolation(file_path, "invalid-jobs", "'jobs' field must be a dictionary")
        )
        return violations

    has_credentials_comment = _has_persist_credentials_comment(content)

    for job_id, job in jobs.items():
        if not isinstance(job, dict):
            continue

        # Check 1: Job must have explicit timeout-minutes
        timeout = job.get("timeout-minutes")
        if timeout is None or not isinstance(timeout, int | float) or timeout <= 0:
            violations.append(
                WorkflowViolation(
                    file_path,
                    "missing-timeout-minutes",
                    f"Job '{job_id}' lacks explicit positive 'timeout-minutes'",
                )
            )

        # Check 2: Job or workflow must have explicit permissions block
        job_permissions = job.get("permissions")
        if top_permissions is None and job_permissions is None:
            violations.append(
                WorkflowViolation(
                    file_path,
                    "missing-permissions",
                    f"Neither workflow nor job '{job_id}' defines an explicit 'permissions' block",
                )
            )

        # Inspect job steps
        steps = job.get("steps", [])
        if isinstance(steps, list):
            for idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue

                step_name = step.get("name", f"step-{idx + 1}")

                # Check 3: No step may use continue-on-error: true
                coe = step.get("continue-on-error")
                if coe is True or str(coe).strip().lower() == "true":
                    violations.append(
                        WorkflowViolation(
                            file_path,
                            "continue-on-error-forbidden",
                            f"Job '{job_id}' step '{step_name}' sets 'continue-on-error: true'",
                        )
                    )

                # Check 5: actions/checkout must have persist-credentials: false
                uses_str = step.get("uses", "")
                if isinstance(uses_str, str) and "actions/checkout" in uses_str:
                    step_with = step.get("with", {})
                    persist_cred = (
                        step_with.get("persist-credentials")
                        if isinstance(step_with, dict)
                        else None
                    )

                    if persist_cred is not False and str(persist_cred).strip().lower() != "false":
                        if not has_credentials_comment:
                            violations.append(
                                WorkflowViolation(
                                    file_path,
                                    "unsecured-checkout-credentials",
                                    f"Job '{job_id}' step '{step_name}' uses actions/checkout "
                                    "without 'persist-credentials: false' and lacks comment",
                                )
                            )

    return violations


def check_workflows_dir(workflows_dir: Path) -> list[WorkflowViolation]:
    """Scan and validate all YAML workflow files in the given directory."""
    violations: list[WorkflowViolation] = []
    if not workflows_dir.is_dir():
        violations.append(
            WorkflowViolation(
                workflows_dir,
                "missing-directory",
                f"Workflows directory not found at: {workflows_dir}",
            )
        )
        return violations

    yaml_files = sorted(
        [
            f
            for f in workflows_dir.iterdir()
            if f.is_file() and (f.suffix == ".yml" or f.suffix == ".yaml")
        ]
    )

    for file_path in yaml_files:
        violations.extend(check_workflow_file(file_path))

    return violations


def main() -> int:
    """CLI entry point for checking workflow files."""
    parser = argparse.ArgumentParser(
        description="Verify GitHub Actions workflows adhere to security policies.",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path(".github/workflows"),
        help="Workflows directory (default: .github/workflows).",
    )

    args = parser.parse_args()
    violations = check_workflows_dir(args.dir)

    if violations:
        sys.stderr.write(f"Found {len(violations)} workflow violation(s):\n")
        for v in violations:
            sys.stderr.write(f"  {v}\n")
        return 1

    sys.stdout.write("All GitHub Actions workflows PASSED security and structure checks.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
