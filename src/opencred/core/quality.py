"""Contribution quality evidence evaluator.

This module evaluates POSITIVE EVIDENCE that a contribution deserves fair review.
It does NOT measure the contributor's character or trustworthiness (see AGENTS.md rule 2 & 6).
All heuristics and weights are transparent, documented in config.py, and explainable.
"""

import math
from collections.abc import Sequence
from pathlib import Path

from pydantic import Field

from opencred.core.config import (
    BOILERPLATE_PHRASES,
    LOW_VALUE_FILE_PATTERNS,
    QUALITY_HISTORY_SATURATION_K,
    QUALITY_TRIVIAL_PR_CAP,
    QUALITY_WEIGHT_DESCRIPTIVE_CONTENT,
    QUALITY_WEIGHT_HISTORY,
    QUALITY_WEIGHT_ISSUE_LINK,
    QUALITY_WEIGHT_NON_TRIVIAL_FILES,
)
from opencred.core.models import (
    ContributionEvent,
    ContributionEventKind,
    OpenCredModel,
    PullRequestRecord,
)


class QualityEvidence(OpenCredModel):
    """Positive evidence indicating that a contribution deserves human review."""

    value: float = Field(
        ge=0.0,
        le=1.0,
        description="Quality evidence score in [0.0, 1.0]",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Explainability strings detailing concrete evidence for each component",
    )


class QualityConfig(OpenCredModel):
    """Configurable weights and thresholds for contribution quality heuristics."""

    weight_issue_link: float = QUALITY_WEIGHT_ISSUE_LINK
    weight_non_trivial_files: float = QUALITY_WEIGHT_NON_TRIVIAL_FILES
    weight_descriptive_content: float = QUALITY_WEIGHT_DESCRIPTIVE_CONTENT
    weight_history: float = QUALITY_WEIGHT_HISTORY
    history_saturation_k: float = QUALITY_HISTORY_SATURATION_K
    trivial_pr_cap: float = QUALITY_TRIVIAL_PR_CAP
    low_value_patterns: tuple[str, ...] = LOW_VALUE_FILE_PATTERNS
    boilerplate_phrases: tuple[str, ...] = BOILERPLATE_PHRASES


def _is_low_value_file(filepath: str, low_value_patterns: tuple[str, ...]) -> bool:
    """Check if a file path matches configured trivial or low-value patterns."""
    clean = filepath.strip().lower()
    basename = Path(clean).name
    return basename in low_value_patterns or clean in low_value_patterns


def contribution_quality_evidence(
    pr: PullRequestRecord,
    subject_history: Sequence[ContributionEvent] | None = None,
    config: QualityConfig | None = None,
) -> QualityEvidence:
    """Calculate positive contribution quality evidence for a pull request.

    Heuristics:
    1. Issue linking: PR links to at least one issue.
    2. Non-trivial file changes: Changed files are not solely in low-value patterns.
    3. Content descriptiveness: Title and body are non-empty and non-boilerplate.
    4. Historical merges: Merged PRs add saturating positive evidence: 1 - exp(-merged / k).
    5. Trivial-PR cap: PRs modifying solely low-value files are capped at trivial_pr_cap.

    Fairness rules:
    - Missing history yields 0.0 history contribution, never a negative penalty.
    - CLOSED_UNMERGED events do not penalize the score.

    Args:
        pr: The pull request record under assessment.
        subject_history: Optional history of observed events for the contributor.
        config: Optional configuration overriding starting weights.

    Returns:
        QualityEvidence with value in [0.0, 1.0] and detailed reason strings.
    """
    cfg = config if config is not None else QualityConfig()
    history = subject_history if subject_history is not None else []
    reasons: list[str] = []

    total_score = 0.0

    # 1. Issue link heuristic
    linked_issues = pr.linked_issue_numbers
    if linked_issues:
        total_score += cfg.weight_issue_link
        reasons.append(
            f"PR links to {len(linked_issues)} issue(s): {linked_issues} "
            f"(+{cfg.weight_issue_link:.2f})"
        )
    else:
        reasons.append("PR does not link to any tracked issues (+0.00)")

    # 2. File changes heuristic
    changed_files = pr.changed_files
    is_diff_pure_whitespace = len(pr.normalized_diff.strip()) == 0

    if not changed_files:
        reasons.append("PR has no changed files listed (+0.00)")
    else:
        is_solely_low_value = all(
            _is_low_value_file(f, cfg.low_value_patterns) for f in changed_files
        )
        if is_solely_low_value or is_diff_pure_whitespace:
            reasons.append(
                f"PR changed files ({changed_files}) match low-value patterns or diff is empty "
                "(+0.00)"
            )
        else:
            total_score += cfg.weight_non_trivial_files
            reasons.append(
                f"PR modifies {len(changed_files)} non-trivial file(s) "
                f"(+{cfg.weight_non_trivial_files:.2f})"
            )

    # 3. Descriptive title and body heuristic
    title_norm = pr.title.strip().lower()
    body_norm = pr.body.strip().lower()

    title_is_boilerplate = (not title_norm) or (title_norm in cfg.boilerplate_phrases)
    body_is_boilerplate = (not body_norm) or (body_norm in cfg.boilerplate_phrases)

    if not title_is_boilerplate and not body_is_boilerplate:
        total_score += cfg.weight_descriptive_content
        reasons.append(
            f"PR includes descriptive title and non-boilerplate description "
            f"(+{cfg.weight_descriptive_content:.2f})"
        )
    else:
        reasons.append("PR title or description is empty or boilerplate (+0.00)")

    # 4. Historical evidence heuristic (saturating function on merged events)
    # Plain CLOSED_UNMERGED events are explicitly ignored and do not reduce score.
    merged_events = [ev for ev in history if ev.kind == ContributionEventKind.MERGED]
    merged_count = len(merged_events)

    if merged_count > 0:
        saturation = 1.0 - math.exp(-merged_count / cfg.history_saturation_k)
        history_contrib = cfg.weight_history * saturation
        total_score += history_contrib
        reasons.append(
            f"Contributor history contains {merged_count} merged PR(s) with saturating "
            f"factor {saturation:.4f} (+{history_contrib:.4f})"
        )
    else:
        reasons.append("No prior merged contributions in history (neutral +0.00)")

    # 5. Trivial-PR penalty: cap score if changed files are solely low-value
    if changed_files and all(_is_low_value_file(f, cfg.low_value_patterns) for f in changed_files):
        if total_score > cfg.trivial_pr_cap:
            msg = (
                f"Trivial-PR cap applied: changes are solely in low-value patterns "
                f"({changed_files}), capping evidence from {total_score:.4f} to "
                f"{cfg.trivial_pr_cap:.2f}"
            )
            reasons.append(msg)
            total_score = cfg.trivial_pr_cap

    # Clamp final score to [0.0, 1.0]
    final_value = min(1.0, max(0.0, total_score))

    return QualityEvidence(
        value=final_value,
        reasons=reasons,
    )


__all__ = [
    "QualityConfig",
    "QualityEvidence",
    "contribution_quality_evidence",
]
