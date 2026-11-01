#!/usr/bin/env python3
"""Render GitHub PR comment markdown from a validated OpenCred assessment result.

Rules:
- Uses only validated fields from ValidatedAssessmentResult.
- Displays scores: Network Trust, Campaign Risk, Quality Evidence.
- Renders TriageOutcome recommendation with appropriate explanation.
- Displays explicit reasons, contributing sources, and audit notes.
- Strictly includes the advisory disclaimer: OpenCred evaluations are advisory only
  and must never block, reject, or close contributions.
- When outcome is INVESTIGATE_CAMPAIGN, prominently highlights campaign evidence.
- When outcome is NEWCOMER_FAIR_REVIEW, highlights fair first-time review language
  without negative labels.
- Hidden HTML marker <!-- opencred-assessment --> identifies the comment for deduplication.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from opencred.core.assessment import Assessment
from opencred.core.triage import TriageOutcome

# Import from scripts directory
try:
    from scripts.validate_result import ValidatedAssessmentResult, validate_result_data
except ModuleNotFoundError:
    # If running with scripts/ on sys.path or as sibling script
    from validate_result import ValidatedAssessmentResult, validate_result_data  # type: ignore[no-redef]

COMMENT_MARKER = "<!-- opencred-assessment -->"

ADVISORY_DISCLAIMER = (
    "> [!NOTE]\n"
    "> **Advisory Notice**: OpenCred assessments are purely advisory decision support "
    "for human maintainers. OpenCred never automatically blocks, closes, rejects, or fails "
    "a pull request based on trust or risk scores."
)


def render_comment(assessment: Assessment, pr_number: int | None = None) -> str:
    """Render advisory markdown comment for GitHub pull request.

    Args:
        assessment: Validated Assessment instance.
        pr_number: Optional pull request number.

    Returns:
        Formatted markdown string including hidden comment marker.
    """
    lines: list[str] = [COMMENT_MARKER, "## OpenCred Contribution Assessment", ""]

    # Header / Triage badge
    pr_label = f" for PR #{pr_number}" if pr_number else ""

    if assessment.triage == TriageOutcome.INVESTIGATE_CAMPAIGN:
        lines.append(f"### Advisory Outcome: `INVESTIGATE_CAMPAIGN`{pr_label}")
        lines.append("")
        lines.append(
            "> [!WARNING]\n"
            "> **Elevated Campaign Risk Detected**: Coordinated pull request patterns or "
            "burst similarity anomalies match known campaign criteria. Human review of "
            "diffs and recent cross-repo submission activity is advised."
        )
    elif assessment.triage == TriageOutcome.NEWCOMER_FAIR_REVIEW:
        lines.append(f"### Advisory Outcome: `NEWCOMER_FAIR_REVIEW`{pr_label}")
        lines.append("")
        lines.append(
            "> [!TIP]\n"
            "> **Welcome New Contributor**: This contributor has no prior recorded activity "
            "or network assertions. Positive quality signals were observed; fair, welcoming "
            "first-time review is recommended without prejudice."
        )
    elif assessment.triage == TriageOutcome.NORMAL_REVIEW:
        lines.append(f"### Advisory Outcome: `NORMAL_REVIEW`{pr_label}")
        lines.append("")
        lines.append("Positive network reputation and low campaign risk observed. Standard review.")
    elif assessment.triage == TriageOutcome.REVIEW_REPUTATION_EVIDENCE:
        lines.append(f"### Advisory Outcome: `REVIEW_REPUTATION_EVIDENCE`{pr_label}")
        lines.append("")
        lines.append(
            "> [!IMPORTANT]\n"
            "> Negative network reputation consensus was observed across independent origins. "
            "Maintainers should review the reputation evidence below."
        )
    elif assessment.triage == TriageOutcome.ADDITIONAL_SCRUTINY:
        lines.append(f"### Advisory Outcome: `ADDITIONAL_SCRUTINY`{pr_label}")
        lines.append("")
        lines.append("Additional scrutiny recommended based on intermediate evidence signals.")
    else:  # UNCERTAIN
        lines.append(f"### Advisory Outcome: `UNCERTAIN`{pr_label}")
        lines.append("")
        lines.append(
            "Evidence is inconclusive, conflicting, or absent. No adverse inference is drawn."
        )

    lines.append("")

    # Metrics table
    lines.append("| Metric | Score | Assessment Range |")
    lines.append("| :--- | :--- | :--- |")
    lines.append(f"| **Network Trust** | `{assessment.network_trust:+.2f}` | [-1.00, +1.00] |")
    lines.append(f"| **Campaign Risk** | `{assessment.campaign_risk:.2f}` | [0.00, 1.00] |")
    quality_score = assessment.contribution_quality_evidence
    lines.append(f"| **Quality Evidence** | `{quality_score:.2f}` | [0.00, 1.00] |")
    lines.append("")

    # Reasons section
    if assessment.reasons:
        lines.append("#### Evaluation Reasons")
        for reason in assessment.reasons:
            lines.append(f"- {reason}")
        lines.append("")

    # Contributing Sources section
    if assessment.sources:
        lines.append("#### Contributing Reputation Origins")
        for source in assessment.sources:
            lines.append(f"- {source}")
        lines.append("")

    # Notes section
    if assessment.notes:
        lines.append("#### Audit & Context Notes")
        for note in assessment.notes:
            lines.append(f"- {note}")
        lines.append("")

    # Mandatory advisory disclaimer
    lines.append(ADVISORY_DISCLAIMER)
    lines.append("")

    return "\n".join(lines)


def render_from_file(path: Path) -> str:
    """Read a validated JSON result file and return the rendered comment string.

    Args:
        path: Path to the JSON file.

    Returns:
        Rendered markdown comment string.

    Raises:
        FileNotFoundError, ValueError, or ValidationError on invalid input.
    """
    if not path.is_file():
        raise FileNotFoundError(f"Result file not found at: {path}")

    raw_text = path.read_text(encoding="utf-8")
    data: Any = json.loads(raw_text)
    validated: ValidatedAssessmentResult = validate_result_data(data)
    return render_comment(validated.assessment, pr_number=validated.pr_number)


def main() -> int:
    """CLI entry point for rendering comment markdown."""
    parser = argparse.ArgumentParser(
        description="Render GitHub PR markdown comment from an OpenCred assessment result JSON.",
    )
    parser.add_argument(
        "file",
        nargs="?",
        default="result.json",
        type=Path,
        help="Path to assessment result JSON file (default: result.json).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Destination path to write the markdown comment. If omitted, writes to stdout.",
    )

    args = parser.parse_args()

    try:
        comment_md = render_from_file(args.file)
    except Exception as err:
        sys.stderr.write(f"Error rendering comment from '{args.file}': {err}\n")
        return 1

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(comment_md, encoding="utf-8")
    else:
        sys.stdout.write(comment_md)

    return 0


if __name__ == "__main__":
    sys.exit(main())
