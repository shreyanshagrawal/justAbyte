#!/usr/bin/env python3
"""Validate an OpenCred Assessment result JSON against the expected schema.

Ensures result.json conforms strictly to the expected Assessment result format:
- Supports either a direct Assessment JSON object or a wrapped result object
  containing {"assessment": <Assessment>, "pr_number": int}.
- Valid numerical bounds: network_trust [-1.0, 1.0], campaign_risk [0.0, 1.0], quality [0.0, 1.0]
- Valid TriageOutcome enum string
- Explanatory reasons, sources, and notes lists
- Non-empty output structure and required fields
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from opencred.core.assessment import Assessment


class ValidatedAssessmentResult(BaseModel):
    """Schema for validated assessment output with PR context."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    assessment: Assessment
    pr_number: int | None = Field(default=None, ge=1)


def validate_result_data(data: Any) -> ValidatedAssessmentResult:
    """Validate raw parsed JSON dictionary and return a ValidatedAssessmentResult.

    Accepts:
    1. A dictionary matching `ValidatedAssessmentResult` (with `assessment` and `pr_number`).
    2. A direct `Assessment` dictionary, optionally with top-level `pr_number`.
    """
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object, got {type(data).__name__}")

    if "assessment" in data:
        # Wrapped structure
        res = ValidatedAssessmentResult.model_validate(data)
        return res

    # Direct Assessment model
    # If "pr_number" was provided at the top level alongside assessment fields, extract it
    pr_num = data.get("pr_number")
    cleaned_data = {k: v for k, v in data.items() if k != "pr_number"}
    assessment = Assessment.model_validate(cleaned_data)
    pr_num_int = int(pr_num) if pr_num is not None else None
    return ValidatedAssessmentResult(assessment=assessment, pr_number=pr_num_int)


def validate_result_file(path: Path) -> ValidatedAssessmentResult:
    """Read and validate an Assessment JSON file using Pydantic.

    Args:
        path: Path to the JSON file containing the assessment result.

    Returns:
        The validated ValidatedAssessmentResult instance.

    Raises:
        FileNotFoundError, ValueError, or ValidationError if invalid.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Assessment result file not found at: {path}")

    raw_text = path.read_text(encoding="utf-8")
    data = json.loads(raw_text)
    return validate_result_data(data)


def main() -> int:
    """CLI entry point for assessment result validation."""
    parser = argparse.ArgumentParser(
        description="Validate OpenCred result.json against the Assessment schema.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="result.json",
        type=Path,
        help="Path to assessment result JSON file to validate (default: result.json).",
    )
    parser.add_argument(
        "--print-pr-number",
        action="store_true",
        help="If specified, print the extracted PR number to stdout.",
    )

    args = parser.parse_args()

    try:
        result = validate_result_file(args.file)
    except Exception as err:
        sys.stderr.write(f"Validation failed for '{args.file}': {err}\n")
        return 1

    if args.print_pr_number:
        if result.pr_number is None:
            sys.stderr.write(f"Error: No pr_number found in '{args.file}'\n")
            return 1
        sys.stdout.write(f"{result.pr_number}\n")
        return 0

    sys.stdout.write(
        f"Validation PASSED: {args.file} conforms to Assessment schema "
        f"(triage={result.assessment.triage}, trust={result.assessment.network_trust:.2f}, "
        f"campaign_risk={result.assessment.campaign_risk:.2f}, pr={result.pr_number})\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
