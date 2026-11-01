"""Tests for OpenCred GitHub action comment rendering script (scripts/render_comment.py).

Verifies:
1. An INVESTIGATE_CAMPAIGN outcome renders the campaign evidence and warning.
2. A NEWCOMER_FAIR_REVIEW outcome renders fair-review language and no negative label.
3. Malformed input causes a non-zero exit.
4. The output always includes the advisory disclaimer.
"""

import json
import subprocess
import sys
from pathlib import Path

from opencred.core.assessment import Assessment
from opencred.core.triage import TriageOutcome
from scripts.render_comment import (
    ADVISORY_DISCLAIMER,
    COMMENT_MARKER,
    render_comment,
    render_from_file,
)


def _make_sample_assessment(
    triage: TriageOutcome,
    network_trust: float = 0.0,
    campaign_risk: float = 0.0,
    quality: float = 0.5,
    reasons: list[str] | None = None,
    sources: list[str] | None = None,
    notes: list[str] | None = None,
) -> Assessment:
    """Construct an Assessment instance for testing."""
    return Assessment(
        network_trust=network_trust,
        campaign_risk=campaign_risk,
        contribution_quality_evidence=quality,
        triage=triage,
        reasons=reasons or [],
        sources=sources or [],
        notes=notes or [],
    )


def test_investigate_campaign_renders_campaign_evidence_and_warning() -> None:
    """An INVESTIGATE_CAMPAIGN outcome renders campaign evidence and prominent warning."""
    campaign_reason = "PR matches coordinated campaign burst across 4 repositories"
    assessment = _make_sample_assessment(
        triage=TriageOutcome.INVESTIGATE_CAMPAIGN,
        network_trust=0.0,
        campaign_risk=0.85,
        quality=0.2,
        reasons=[campaign_reason],
        notes=["PR is member of detected cluster candidate-01"],
    )

    rendered = render_comment(assessment, pr_number=101)

    assert COMMENT_MARKER in rendered
    assert "INVESTIGATE_CAMPAIGN" in rendered
    assert "#101" in rendered
    assert "Elevated Campaign Risk Detected" in rendered
    assert campaign_reason in rendered
    assert "0.85" in rendered
    assert ADVISORY_DISCLAIMER in rendered


def test_newcomer_fair_review_renders_fair_language_and_no_negative_label() -> None:
    """A NEWCOMER_FAIR_REVIEW outcome renders fair-review language and no negative label."""
    fair_reason = (
        "New contributor with low campaign risk (0.00 < 0.30) and positive quality evidence "
        "(0.75 >= 0.50); recommend fair first-time review."
    )
    assessment = _make_sample_assessment(
        triage=TriageOutcome.NEWCOMER_FAIR_REVIEW,
        network_trust=0.0,
        campaign_risk=0.0,
        quality=0.75,
        reasons=[fair_reason],
    )

    rendered = render_comment(assessment, pr_number=42)

    assert COMMENT_MARKER in rendered
    assert "NEWCOMER_FAIR_REVIEW" in rendered
    assert "#42" in rendered
    assert "Welcome New Contributor" in rendered
    assert "fair, welcoming first-time review is recommended without prejudice" in rendered
    assert fair_reason in rendered

    # Strictly verify no adverse or prohibited negative labels
    assert "malicious" not in rendered.lower()
    assert "suspicious" not in rendered.lower()
    assert "blocked" not in rendered.lower()
    disclaimer_snippet = "never automatically blocks, closes, rejects"
    assert "reject" not in rendered.lower() or disclaimer_snippet in rendered
    assert ADVISORY_DISCLAIMER in rendered


def test_advisory_disclaimer_always_present_in_all_outcomes() -> None:
    """The output always includes the mandatory advisory disclaimer across all outcomes."""
    for outcome in TriageOutcome:
        assessment = _make_sample_assessment(
            triage=outcome,
            network_trust=0.2,
            campaign_risk=0.1,
            quality=0.6,
        )
        rendered = render_comment(assessment)
        assert ADVISORY_DISCLAIMER in rendered
        assert "OpenCred assessments are purely advisory decision support" in rendered
        assert "never automatically blocks, closes, rejects, or fails" in rendered


def test_malformed_input_causes_nonzero_exit(tmp_path: Path) -> None:
    """Malformed input causes a non-zero exit code when running render_comment CLI."""
    import os

    malformed_file = tmp_path / "bad_result.json"
    malformed_file.write_text('{"network_trust": "not-a-number"}', encoding="utf-8")

    script_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "render_comment.py"
    repo_root = Path(__file__).resolve().parent.parent.parent

    env = os.environ.copy()
    env["PYTHONPATH"] = str(repo_root)

    proc = subprocess.run(
        [sys.executable, str(script_path), str(malformed_file)],
        capture_output=True,
        text=True,
        check=False,
        cwd=str(repo_root),
        env=env,
    )
    assert proc.returncode != 0
    assert "Error rendering comment" in proc.stderr or "Validation failed" in proc.stderr


def test_render_from_file_with_valid_wrapped_json(tmp_path: Path) -> None:
    """render_from_file successfully parses a validated wrapped JSON structure."""
    valid_file = tmp_path / "result.json"
    data = {
        "assessment": {
            "network_trust": 0.5,
            "campaign_risk": 0.05,
            "contribution_quality_evidence": 0.8,
            "triage": "NORMAL_REVIEW",
            "reasons": ["High quality PR with linked issue"],
            "sources": ["origin/a (1 hop)"],
            "notes": ["All clear"],
        },
        "pr_number": 77,
    }
    valid_file.write_text(json.dumps(data), encoding="utf-8")

    rendered = render_from_file(valid_file)
    assert "PR #77" in rendered
    assert "NORMAL_REVIEW" in rendered
    assert "+0.50" in rendered
    assert ADVISORY_DISCLAIMER in rendered
