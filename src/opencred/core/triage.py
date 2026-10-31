"""Advisory triage decisions for open-source pull requests.

This module combines network trust, campaign risk, contribution quality,
and newcomer status into an advisory triage recommendation for repository
maintainers.

Advisory Rules (AGENTS.md):
- Advisory only: never automatically block, close, or reject contributions.
- Explainability: every outcome includes concrete evidence reasons.
- Language constraints: no output may use 'safe', 'trusted', 'malicious', or 'block'.
- Missing data is not negative: newcomers and incomplete data yield UNCERTAIN
  or NEWCOMER_FAIR_REVIEW, never adverse labels.
"""

from enum import StrEnum
from typing import NamedTuple

from opencred.core.config import (
    CAMPAIGN_ALERT_THRESHOLD,
    CAMPAIGN_LOW_THRESHOLD,
    MIN_INDEPENDENT_ORIGINS_FOR_SEVERE,
    QUALITY_FAIR_THRESHOLD,
    TRUST_NORMAL_THRESHOLD,
)
from opencred.core.quality import QualityEvidence


class TriageOutcome(StrEnum):
    """Advisory triage recommendation outcome."""

    NORMAL_REVIEW = "NORMAL_REVIEW"
    NEWCOMER_FAIR_REVIEW = "NEWCOMER_FAIR_REVIEW"
    ADDITIONAL_SCRUTINY = "ADDITIONAL_SCRUTINY"
    REVIEW_REPUTATION_EVIDENCE = "REVIEW_REPUTATION_EVIDENCE"
    INVESTIGATE_CAMPAIGN = "INVESTIGATE_CAMPAIGN"
    UNCERTAIN = "UNCERTAIN"


class TriageDecision(NamedTuple):
    """Advisory triage decision with recommendation and explainability reasons."""

    outcome: TriageOutcome
    reasons: list[str]


def decide(
    network_trust: float,
    campaign_risk: float,
    quality: float | QualityEvidence,
    is_newcomer: bool,
    severe: bool,
    conflicting: bool,
    independent_origins_count: int | None = None,
) -> tuple[TriageOutcome, list[str]]:
    """Determine an advisory triage recommendation based on contributor evidence.

    Evaluation evaluates rules in strict priority order and stops at the first match:
    1. campaign_risk >= CAMPAIGN_ALERT_THRESHOLD -> INVESTIGATE_CAMPAIGN.
    2. conflicting is True -> UNCERTAIN.
    3. is_newcomer and campaign_risk low and quality >= QUALITY_FAIR_THRESHOLD
       -> NEWCOMER_FAIR_REVIEW.
    4. is_newcomer and no strong quality -> UNCERTAIN (not a negative outcome).
    5. severe is True -> REVIEW_REPUTATION_EVIDENCE (naming independent origin count).
    6. network_trust >= TRUST_NORMAL_THRESHOLD and campaign_risk low -> NORMAL_REVIEW.
    7. network_trust < 0 and campaign_risk low -> REVIEW_REPUTATION_EVIDENCE (not severe).
    8. Otherwise -> UNCERTAIN.

    Args:
        network_trust: Net network trust score in [-1.0, 1.0].
        campaign_risk: Assessed campaign risk score in [0.0, 1.0].
        quality: Contribution quality evidence score in [0.0, 1.0] or QualityEvidence.
        is_newcomer: True if contributor has no local history and no network assertions.
        severe: True if negative network consensus meets the severe threshold.
        conflicting: True if conflicting network assertions were detected.
        independent_origins_count: Optional count of distinct independent origins denouncing.

    Returns:
        A tuple of (TriageOutcome, list[str] reasons).
    """
    quality_val = quality.value if isinstance(quality, QualityEvidence) else float(quality)
    is_campaign_low = campaign_risk < CAMPAIGN_LOW_THRESHOLD

    # Rule 1: High campaign risk -> INVESTIGATE_CAMPAIGN
    if campaign_risk >= CAMPAIGN_ALERT_THRESHOLD:
        reasons = [
            f"Campaign risk ({campaign_risk:.2f}) meets or exceeds alert threshold "
            f"({CAMPAIGN_ALERT_THRESHOLD:.2f}); recommend investigating coordinated PR patterns."
        ]
        return TriageDecision(TriageOutcome.INVESTIGATE_CAMPAIGN, reasons)

    # Rule 2: Conflicting network evidence -> UNCERTAIN
    if conflicting:
        reasons = [
            "Conflicting network assertions detected across peer repositories; "
            "advisory recommendation is uncertain to avoid premature conclusions."
        ]
        return TriageDecision(TriageOutcome.UNCERTAIN, reasons)

    # Rule 3: Newcomer with low campaign risk and sufficient quality -> NEWCOMER_FAIR_REVIEW
    if is_newcomer and is_campaign_low and quality_val >= QUALITY_FAIR_THRESHOLD:
        reasons = [
            f"New contributor with low campaign risk ({campaign_risk:.2f} < "
            f"{CAMPAIGN_LOW_THRESHOLD:.2f}) and positive quality evidence "
            f"({quality_val:.2f} >= {QUALITY_FAIR_THRESHOLD:.2f}); "
            "recommend fair first-time review."
        ]
        return TriageDecision(TriageOutcome.NEWCOMER_FAIR_REVIEW, reasons)

    # Rule 4: Newcomer without strong quality evidence -> UNCERTAIN (non-punitive)
    if is_newcomer:
        reasons = [
            f"New contributor without established quality evidence "
            f"({quality_val:.2f} < {QUALITY_FAIR_THRESHOLD:.2f}); "
            "advisory recommendation is uncertain with no negative presumption."
        ]
        return TriageDecision(TriageOutcome.UNCERTAIN, reasons)

    # Rule 5: Severe negative network consensus -> REVIEW_REPUTATION_EVIDENCE
    if severe:
        count = (
            independent_origins_count
            if independent_origins_count is not None
            else MIN_INDEPENDENT_ORIGINS_FOR_SEVERE
        )
        reasons = [
            f"Severe negative network consensus corroborated across {count} "
            f"independent origin repositories (network trust: {network_trust:.2f}); "
            "recommend review of reputation evidence."
        ]
        return TriageDecision(TriageOutcome.REVIEW_REPUTATION_EVIDENCE, reasons)

    # Rule 6: Established positive network trust and low campaign risk -> NORMAL_REVIEW
    if network_trust >= TRUST_NORMAL_THRESHOLD and is_campaign_low:
        reasons = [
            f"Positive network consensus ({network_trust:.2f} >= {TRUST_NORMAL_THRESHOLD:.2f}) "
            f"with low campaign risk ({campaign_risk:.2f} < {CAMPAIGN_LOW_THRESHOLD:.2f}); "
            "recommend standard review."
        ]
        return TriageDecision(TriageOutcome.NORMAL_REVIEW, reasons)

    # Rule 7: Negative network trust (not severe) and low campaign risk
    # -> REVIEW_REPUTATION_EVIDENCE
    if network_trust < 0.0 and is_campaign_low:
        reasons = [
            f"Negative network consensus ({network_trust:.2f} < 0.0) with low campaign risk "
            f"({campaign_risk:.2f} < {CAMPAIGN_LOW_THRESHOLD:.2f}); "
            "recommend review of reputation evidence."
        ]
        return TriageDecision(TriageOutcome.REVIEW_REPUTATION_EVIDENCE, reasons)

    # Rule 8: Otherwise -> UNCERTAIN
    reasons = [
        f"Evidence is in an intermediate or inconclusive range "
        f"(network trust: {network_trust:.2f}, campaign risk: {campaign_risk:.2f}, "
        f"quality: {quality_val:.2f}); advisory outcome is uncertain."
    ]
    return TriageDecision(TriageOutcome.UNCERTAIN, reasons)


__all__ = [
    "TriageDecision",
    "TriageOutcome",
    "decide",
]
