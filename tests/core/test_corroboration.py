"""Unit tests for OpenCred corroboration engine and bounded influence rules."""

import pytest

from opencred.core.config import (
    EXTERNAL_SINGLE_DENOUNCE_CAP,
    LOCAL_DENOUNCE_WEIGHT,
)
from opencred.core.corroboration import (
    ExternalSignal,
    LocalEvidence,
    apply_corroboration,
)
from opencred.core.models import Assertion, AssertionKind, RepoId


class TestCorroborationRules:
    """Tests for corroboration, single-origin capping, and severe classification."""

    @pytest.mark.fairness
    def test_single_external_denouncement_capped_to_point_two(self) -> None:
        """One external denouncement at strength 1.0 from one origin is capped to 0.2 magnitude."""
        local = LocalEvidence(has_denouncement=False, has_vouch=False)
        origin_a = RepoId("peer/origin-a")
        external = ExternalSignal(raw_trust=-1.0, denouncing_origins=[origin_a])

        result = apply_corroboration(local, external)

        # Hand-calculated expectation:
        # raw_trust is -1.0, capped to -EXTERNAL_SINGLE_DENOUNCE_CAP (-0.2)
        assert result.network_trust == pytest.approx(-EXTERNAL_SINGLE_DENOUNCE_CAP)
        assert result.network_trust == pytest.approx(-0.2)
        assert result.is_severe is False
        assert result.independent_denounce_count == 1

        # Check explainability notes
        assert any("capped from -1.00 to magnitude 0.20" in note for note in result.notes)
        assert any("Severe classification not met" in note for note in result.notes)

    def test_two_independent_origins_meet_severe_requirement(self) -> None:
        """Two independent origin denouncements meet the severe requirement."""
        local = LocalEvidence(has_denouncement=False, has_vouch=False)
        origin_a = RepoId("peer/origin-a")
        origin_b = RepoId("peer/origin-b")
        # Both independent origins denounce; trust -0.85 <= SEVERE_THRESHOLD (-0.6)
        external = ExternalSignal(raw_trust=-0.85, denouncing_origins=[origin_a, origin_b])

        result = apply_corroboration(local, external)

        # Hand-calculated expectation:
        # independent_denounce_count = 2 (>= MIN_INDEPENDENT_ORIGINS_FOR_SEVERE = 2)
        # network_trust = -0.85 (<= SEVERE_THRESHOLD = -0.6) -> is_severe = True
        assert result.network_trust == pytest.approx(-0.85)
        assert result.is_severe is True
        assert result.independent_denounce_count == 2

        # Check explainability notes
        assert any("corroborated by 2 independent origins" in note for note in result.notes)
        assert any("Severe classification met" in note for note in result.notes)

    @pytest.mark.fairness
    def test_relayed_duplicate_copies_do_not_meet_severe_requirement(self) -> None:
        """Two copies of one origin's denouncement (relayed) do NOT meet the severe requirement."""
        local = LocalEvidence(has_denouncement=False, has_vouch=False)
        origin_a = RepoId("peer/origin-a")
        # Origin A relayed twice through multiple network paths
        external = ExternalSignal(
            raw_trust=-1.0,
            denouncing_origins=[origin_a, origin_a],
        )

        result = apply_corroboration(local, external)

        # Hand-calculated expectation:
        # Deduplication reduces [origin_a, origin_a] to 1 distinct origin.
        # Single-origin cap applies -> network_trust = -0.2.
        # Severe requirement requires >= 2 distinct origins -> is_severe = False.
        assert result.independent_denounce_count == 1
        assert result.network_trust == pytest.approx(-0.2)
        assert result.is_severe is False

        # Check explainability notes
        assert any(
            "Deduplicated 2 external denouncement(s) down to 1" in note for note in result.notes
        )
        assert any("Severe classification not met" in note for note in result.notes)

    @pytest.mark.fairness
    def test_single_external_vouch_is_not_capped(self) -> None:
        """A single external vouch is not capped."""
        local = LocalEvidence(has_denouncement=False, has_vouch=False)
        origin_a = RepoId("peer/trusted-org")
        # Trusted origin vouches with propagated weight 0.85
        external = ExternalSignal(raw_trust=0.85, vouching_origins=[origin_a])

        result = apply_corroboration(local, external)

        # Hand-calculated expectation:
        # Positive trust is never capped (Rule 4).
        # network_trust = 0.85, is_severe = False.
        assert result.network_trust == pytest.approx(0.85)
        assert result.is_severe is False

        # Check explainability notes
        assert any("External vouch accepted without capping" in note for note in result.notes)

    def test_local_denouncement_is_not_capped(self) -> None:
        """A local denouncement is not capped."""
        local = LocalEvidence(has_denouncement=True, has_vouch=False)
        origin_a = RepoId("peer/origin-a")
        external = ExternalSignal(raw_trust=-0.5, denouncing_origins=[origin_a])

        result = apply_corroboration(local, external)

        # Hand-calculated expectation:
        # Local denouncement counts fully at LOCAL_DENOUNCE_WEIGHT (1.0).
        # network_trust = -1.0, is_severe = True.
        assert result.network_trust == pytest.approx(-LOCAL_DENOUNCE_WEIGHT)
        assert result.network_trust == pytest.approx(-1.0)
        assert result.is_severe is True

        # Check explainability notes
        assert any(
            "Local denouncement from evaluator manifest counts fully" in note
            for note in result.notes
        )
        assert any(
            "Severe classification triggered by local denouncement" in note for note in result.notes
        )

    def test_every_applied_rule_produces_a_note_string(self) -> None:
        """Every applied rule produces a note string explaining the decision."""
        # 1. Neutral case (no evidence)
        res_neutral = apply_corroboration(
            LocalEvidence(),
            ExternalSignal(),
        )
        assert len(res_neutral.notes) >= 1
        assert any("No local or external trust assertions observed" in n for n in res_neutral.notes)

        # 2. Local vouch
        res_local_vouch = apply_corroboration(
            LocalEvidence(has_vouch=True),
            ExternalSignal(),
        )
        assert any(
            "Local vouch from evaluator manifest counts fully" in n for n in res_local_vouch.notes
        )

        # 3. Weak two-origin denouncements that do not cross severe threshold
        res_weak = apply_corroboration(
            LocalEvidence(),
            ExternalSignal(
                raw_trust=-0.3,
                denouncing_origins=[RepoId("org/a"), RepoId("org/b")],
            ),
        )
        assert any("does not reach severe threshold" in n for n in res_weak.notes)

    def test_assertion_objects_input_normalization(self) -> None:
        """ExternalSignal accepts Assertion objects directly."""
        a1 = Assertion(
            origin=RepoId("peer/a"),
            subject="badactor",
            kind=AssertionKind.DENOUNCE,
            strength=1.0,
            line_number=5,
        )
        external = ExternalSignal(denouncements=[a1])
        assert external.denouncing_origins == [RepoId("peer/a")]
        assert external.raw_trust == pytest.approx(-1.0)

        result = apply_corroboration(LocalEvidence(), external)
        assert result.network_trust == pytest.approx(-EXTERNAL_SINGLE_DENOUNCE_CAP)
