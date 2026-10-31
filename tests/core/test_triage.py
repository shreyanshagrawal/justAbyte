"""Unit tests for advisory triage decision logic.

All rules have hand-calculated expected outcomes and explicit inputs
documented in test comments in accordance with AGENTS.md rules.
"""

import pytest

from opencred.core.config import (
    CAMPAIGN_ALERT_THRESHOLD,
    CAMPAIGN_LOW_THRESHOLD,
    MIN_INDEPENDENT_ORIGINS_FOR_SEVERE,
    QUALITY_FAIR_THRESHOLD,
    TRUST_NORMAL_THRESHOLD,
)
from opencred.core.quality import QualityEvidence
from opencred.core.triage import TriageOutcome, decide

PROHIBITED_WORDS = ("safe", "trusted", "malicious", "block")


def _assert_no_prohibited_words(reasons: list[str]) -> None:
    """Verify reasons comply with AGENTS.md language neutrality constraints."""
    for reason in reasons:
        lower = reason.lower()
        for word in PROHIBITED_WORDS:
            assert word not in lower, f"Prohibited word '{word}' found in reason: '{reason}'"


def test_rule_1_high_campaign_risk_triggers_investigate() -> None:
    """Rule 1: campaign_risk >= CAMPAIGN_ALERT_THRESHOLD -> INVESTIGATE_CAMPAIGN.

    Hand-calculated evaluation:
        Inputs:
          network_trust = 0.8 (high)
          campaign_risk = 0.75 >= CAMPAIGN_ALERT_THRESHOLD (0.6)
          quality = 0.9 (high)
          is_newcomer = False
          severe = False
          conflicting = False
        Rule 1 matches immediately:
          Expected outcome = INVESTIGATE_CAMPAIGN
          Reason mentions campaign risk and alert threshold.
    """
    outcome, reasons = decide(
        network_trust=0.8,
        campaign_risk=0.75,
        quality=0.9,
        is_newcomer=False,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.INVESTIGATE_CAMPAIGN
    assert len(reasons) >= 1
    assert "0.75" in reasons[0]
    assert str(CAMPAIGN_ALERT_THRESHOLD) in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_2_conflicting_evidence_triggers_uncertain() -> None:
    """Rule 2: conflicting is True -> UNCERTAIN.

    Hand-calculated evaluation:
        Inputs:
          network_trust = 0.5
          campaign_risk = 0.1 < CAMPAIGN_ALERT_THRESHOLD
          quality = 0.8
          is_newcomer = False
          severe = False
          conflicting = True
        Rule 1 fails (0.1 < 0.6).
        Rule 2 matches:
          Expected outcome = UNCERTAIN
          Reason mentions conflicting network evidence.
    """
    outcome, reasons = decide(
        network_trust=0.5,
        campaign_risk=0.1,
        quality=0.8,
        is_newcomer=False,
        severe=False,
        conflicting=True,
    )

    assert outcome == TriageOutcome.UNCERTAIN
    assert len(reasons) >= 1
    assert "Conflicting" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_3_newcomer_with_quality_gets_fair_review() -> None:
    """Rule 3: is_newcomer and campaign_risk low and quality >= threshold -> NEWCOMER_FAIR_REVIEW.

    Hand-calculated evaluation:
        Inputs:
          network_trust = 0.0 (neutral baseline for newcomer)
          campaign_risk = 0.05 < CAMPAIGN_LOW_THRESHOLD (0.3)
          quality = 0.75 >= QUALITY_FAIR_THRESHOLD (0.5)
          is_newcomer = True
          severe = False
          conflicting = False
        Rule 1 & 2 fail.
        Rule 3 matches:
          Expected outcome = NEWCOMER_FAIR_REVIEW
          Reason mentions newcomer, low campaign risk, and quality evidence.
    """
    assert 0.05 < CAMPAIGN_LOW_THRESHOLD
    assert 0.75 >= QUALITY_FAIR_THRESHOLD
    outcome, reasons = decide(
        network_trust=0.0,
        campaign_risk=0.05,
        quality=0.75,
        is_newcomer=True,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.NEWCOMER_FAIR_REVIEW
    assert len(reasons) >= 1
    assert "fair first-time review" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_4_newcomer_without_strong_quality_uncertain_not_negative() -> None:
    """Rule 4: is_newcomer and no strong quality -> UNCERTAIN (non-punitive).

    Hand-calculated evaluation:
        Inputs:
          network_trust = 0.0
          campaign_risk = 0.1 < 0.3
          quality = 0.2 < QUALITY_FAIR_THRESHOLD (0.5)
          is_newcomer = True
          severe = False
          conflicting = False
        Rule 1, 2, 3 fail.
        Rule 4 matches:
          Expected outcome = UNCERTAIN (never negative label per AGENTS.md rule 6)
          Reason notes lack of history without adverse presumption.
    """
    outcome, reasons = decide(
        network_trust=0.0,
        campaign_risk=0.1,
        quality=0.2,
        is_newcomer=True,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.UNCERTAIN
    assert len(reasons) >= 1
    assert "no negative presumption" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_5_severe_triggers_review_reputation_evidence_with_origin_count() -> None:
    """Rule 5: severe is True -> REVIEW_REPUTATION_EVIDENCE with origin count.

    Hand-calculated evaluation:
        Inputs:
          network_trust = -0.75
          campaign_risk = 0.1
          quality = 0.4
          is_newcomer = False
          severe = True
          conflicting = False
          independent_origins_count = 3
        Rule 1 through 4 fail.
        Rule 5 matches:
          Expected outcome = REVIEW_REPUTATION_EVIDENCE
          Reason references concrete origin count (3).
    """
    outcome, reasons = decide(
        network_trust=-0.75,
        campaign_risk=0.1,
        quality=0.4,
        is_newcomer=False,
        severe=True,
        conflicting=False,
        independent_origins_count=3,
    )

    assert outcome == TriageOutcome.REVIEW_REPUTATION_EVIDENCE
    assert len(reasons) >= 1
    assert "3 independent origin repositories" in reasons[0]
    assert "-0.75" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_5_severe_default_origin_count() -> None:
    """Rule 5 without explicit origin count defaults to MIN_INDEPENDENT_ORIGINS_FOR_SEVERE."""
    outcome, reasons = decide(
        network_trust=-0.7,
        campaign_risk=0.1,
        quality=0.3,
        is_newcomer=False,
        severe=True,
        conflicting=False,
    )

    assert outcome == TriageOutcome.REVIEW_REPUTATION_EVIDENCE
    assert str(MIN_INDEPENDENT_ORIGINS_FOR_SEVERE) in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_6_normal_review_for_positive_trust_and_low_campaign() -> None:
    """Rule 6: network_trust >= TRUST_NORMAL_THRESHOLD and campaign_risk low -> NORMAL_REVIEW.

    Hand-calculated evaluation:
        Inputs:
          network_trust = 0.6 >= TRUST_NORMAL_THRESHOLD (0.3)
          campaign_risk = 0.15 < CAMPAIGN_LOW_THRESHOLD (0.3)
          quality = 0.5
          is_newcomer = False
          severe = False
          conflicting = False
        Rules 1-5 fail.
        Rule 6 matches:
          Expected outcome = NORMAL_REVIEW
          Reason cites positive network consensus and standard review recommendation.
    """
    assert 0.6 >= TRUST_NORMAL_THRESHOLD
    outcome, reasons = decide(
        network_trust=0.6,
        campaign_risk=0.15,
        quality=0.5,
        is_newcomer=False,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.NORMAL_REVIEW
    assert len(reasons) >= 1
    assert "standard review" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_7_non_severe_negative_trust_triggers_reputation_review() -> None:
    """Rule 7: network_trust < 0 and campaign_risk low -> REVIEW_REPUTATION_EVIDENCE (not severe).

    Hand-calculated evaluation:
        Inputs:
          network_trust = -0.2 < 0.0 (non-severe, e.g. single external denouncement)
          campaign_risk = 0.1 < CAMPAIGN_LOW_THRESHOLD (0.3)
          quality = 0.4
          is_newcomer = False
          severe = False
          conflicting = False
        Rules 1-6 fail.
        Rule 7 matches:
          Expected outcome = REVIEW_REPUTATION_EVIDENCE
          Reason cites negative network consensus.
    """
    outcome, reasons = decide(
        network_trust=-0.2,
        campaign_risk=0.1,
        quality=0.4,
        is_newcomer=False,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.REVIEW_REPUTATION_EVIDENCE
    assert len(reasons) >= 1
    assert "-0.20" in reasons[0]
    assert "review of reputation evidence" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_rule_8_otherwise_inconclusive_triggers_uncertain() -> None:
    """Rule 8: Inconclusive intermediate evidence -> UNCERTAIN.

    Hand-calculated evaluation:
        Inputs:
          network_trust = 0.15 (between 0.0 and TRUST_NORMAL_THRESHOLD 0.3)
          campaign_risk = 0.1 < 0.3
          quality = 0.4
          is_newcomer = False
          severe = False
          conflicting = False
        Rules 1 through 7 all evaluate to False:
          Rule 1: 0.1 < 0.6 (False)
          Rule 2: conflicting is False (False)
          Rule 3 & 4: is_newcomer is False (False)
          Rule 5: severe is False (False)
          Rule 6: 0.15 < 0.3 (False)
          Rule 7: 0.15 >= 0.0 (False)
        Rule 8 matches:
          Expected outcome = UNCERTAIN
          Reason explains intermediate evidence range.
    """
    outcome, reasons = decide(
        network_trust=0.15,
        campaign_risk=0.1,
        quality=0.4,
        is_newcomer=False,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.UNCERTAIN
    assert len(reasons) >= 1
    assert "inconclusive" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_newcomer_with_strong_quality_and_high_campaign_risk_investigates() -> None:
    """Priority test: Newcomer with strong quality and high campaign risk
    receives INVESTIGATE_CAMPAIGN.

    Rule priority:
        Rule 1 (campaign_risk >= alert) precedes Rule 3 (newcomer fair review).
        Even if is_newcomer is True and quality is high (0.95), elevated campaign
        risk (0.8) must immediately yield INVESTIGATE_CAMPAIGN, NOT NEWCOMER_FAIR_REVIEW.
    """
    outcome, reasons = decide(
        network_trust=0.0,
        campaign_risk=0.8,
        quality=0.95,
        is_newcomer=True,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.INVESTIGATE_CAMPAIGN
    assert outcome != TriageOutcome.NEWCOMER_FAIR_REVIEW
    assert len(reasons) >= 1
    assert "0.80" in reasons[0]
    _assert_no_prohibited_words(reasons)


def test_decide_accepts_quality_evidence_instance() -> None:
    """decide() transparently handles a QualityEvidence model instance."""
    qe = QualityEvidence(value=0.85, reasons=["Has issue link #12"])
    outcome, reasons = decide(
        network_trust=0.5,
        campaign_risk=0.1,
        quality=qe,
        is_newcomer=True,
        severe=False,
        conflicting=False,
    )

    assert outcome == TriageOutcome.NEWCOMER_FAIR_REVIEW
    assert len(reasons) >= 1
    _assert_no_prohibited_words(reasons)


@pytest.mark.parametrize(
    "outcome_member",
    [
        TriageOutcome.NORMAL_REVIEW,
        TriageOutcome.NEWCOMER_FAIR_REVIEW,
        TriageOutcome.ADDITIONAL_SCRUTINY,
        TriageOutcome.REVIEW_REPUTATION_EVIDENCE,
        TriageOutcome.INVESTIGATE_CAMPAIGN,
        TriageOutcome.UNCERTAIN,
    ],
)
def test_enum_members_complete(outcome_member: TriageOutcome) -> None:
    """Verify all requested TriageOutcome enum members are defined."""
    assert isinstance(outcome_member.value, str)
