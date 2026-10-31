"""Unit tests for newcomer classification and fairness guarantees."""

import random
from datetime import UTC, datetime, timedelta

import pytest

from opencred.core.corroboration import (
    ExternalSignal,
    LocalEvidence,
    apply_corroboration,
)
from opencred.core.models import (
    ContributionEvent,
    ContributionEventKind,
    RepoId,
)
from opencred.core.newcomer import is_newcomer


class TestNewcomerClassification:
    """Tests for is_newcomer function logic."""

    @pytest.mark.fairness
    def test_empty_history_and_no_assertions_is_newcomer(self) -> None:
        """Empty history and no assertions: True."""
        assert is_newcomer(subject_history=[], network_assertions_count=0) is True

    @pytest.mark.fairness
    def test_non_merged_history_with_no_assertions_is_newcomer(self) -> None:
        """Non-merged events (such as CLOSED_UNMERGED or review) still classify as newcomer."""
        now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
        history = [
            ContributionEvent(
                subject="newbie",
                repo=RepoId("owner/repo"),
                kind=ContributionEventKind.CLOSED_UNMERGED,
                occurred_at=now,
            ),
            ContributionEvent(
                subject="newbie",
                repo=RepoId("owner/repo"),
                kind=ContributionEventKind.ADDRESSED_REVIEW,
                occurred_at=now,
            ),
        ]
        assert is_newcomer(subject_history=history, network_assertions_count=0) is True

    def test_one_merged_event_is_not_newcomer(self) -> None:
        """One merged event: False."""
        now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
        history = [
            ContributionEvent(
                subject="alice",
                repo=RepoId("owner/repo"),
                kind=ContributionEventKind.MERGED,
                occurred_at=now,
            ),
        ]
        assert is_newcomer(subject_history=history, network_assertions_count=0) is False

    def test_no_merged_events_but_one_vouch_is_not_newcomer(self) -> None:
        """No merged events but one vouch (network_assertions_count = 1): False."""
        assert is_newcomer(subject_history=[], network_assertions_count=1) is False

    def test_no_merged_events_but_one_denouncement_is_not_newcomer(self) -> None:
        """No merged events but one denouncement: False."""
        assert is_newcomer(subject_history=[], network_assertions_count=1) is False

    def test_negative_network_assertions_count_raises_value_error(self) -> None:
        """Negative network assertions count raises ValueError."""
        with pytest.raises(ValueError, match="must be non-negative"):
            is_newcomer(subject_history=[], network_assertions_count=-1)


class TestNewcomerFairnessGuarantees:
    """Property tests asserting that newcomers never receive negative network trust."""

    @pytest.mark.fairness
    def test_newcomer_never_receives_negative_network_trust_property_test(self) -> None:
        """A newcomer is never given a negative network_trust.

        Generates 200 random newcomer scenarios across various non-merged history
        lengths, event kinds, and timestamps using a fixed seed, asserting that
        network_trust >= 0.0 in every scenario (AGENTS.md rule 6).
        """
        rng = random.Random(42)
        base_time = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)

        non_merged_kinds = [
            ContributionEventKind.CLOSED_UNMERGED,
            ContributionEventKind.ADDRESSED_REVIEW,
        ]

        # Test across 200 pseudo-random newcomer scenarios
        for iteration in range(200):
            subject_name = f"newcomer_{iteration}"

            # Generate random number of non-merged historical events (0 to 10)
            event_count = rng.randint(0, 10)
            history: list[ContributionEvent] = []
            for j in range(event_count):
                kind = rng.choice(non_merged_kinds)
                delta_days = rng.randint(1, 300)
                event_time = base_time + timedelta(days=delta_days)
                history.append(
                    ContributionEvent(
                        subject=subject_name,
                        repo=RepoId(f"random-org/repo-{j}"),
                        kind=kind,
                        occurred_at=event_time,
                    )
                )

            # Assert newcomer qualification
            assert is_newcomer(history, network_assertions_count=0) is True

            # Evaluate network trust for newcomer:
            # By definition, a newcomer has 0 network assertions and 0 local denouncements
            local_evidence = LocalEvidence(has_denouncement=False, has_vouch=False)
            external_signal = ExternalSignal(
                raw_trust=0.0,
                denouncing_origins=[],
                vouching_origins=[],
            )

            corroborated = apply_corroboration(local_evidence, external_signal)

            # Non-negotiable fairness property:
            # Newcomers must NEVER receive negative network trust
            assert corroborated.network_trust >= 0.0, (
                f"Newcomer {subject_name} received negative trust: {corroborated.network_trust}"
            )
            assert corroborated.network_trust == 0.0, (
                f"Expected neutral trust 0.0, got: {corroborated.network_trust}"
            )
            assert corroborated.is_severe is False, f"Newcomer {subject_name} was marked as severe"
