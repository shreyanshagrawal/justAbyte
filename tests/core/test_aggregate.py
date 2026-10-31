"""Unit tests for external trust signal aggregation and origin deduplication."""

import pytest

from opencred.core.aggregate import ExternalSignal, aggregate_external
from opencred.core.graph import TrustGraph
from opencred.core.models import Assertion, AssertionKind, RepoId, TrustEdge


class TestAggregateExternal:
    """Tests for aggregate_external with hand-calculated expected values."""

    def test_single_origin_contribution_and_weighted_average(self) -> None:
        """Single origin B, path A->B weight 0.9, VOUCH strength 0.8:

        contribution is 0.8 * 0.9 = 0.72. Weighted average equals 0.72.
        """
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")

        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.9))

        assertion_b = Assertion(
            origin=repo_b,
            subject="alice",
            kind=AssertionKind.VOUCH,
            strength=0.8,
            line_number=5,
        )

        assertions_by_origin = {
            repo_b: [assertion_b],
        }

        # Hand-calculated expectation:
        # Origin B:
        #   Path weight w_B = 0.9
        #   VOUCH strength = 0.8 -> signed value = +0.8
        #   Contribution c_B = 0.8 * 0.9 = 0.72
        #   Numerator component = c_B * w_B = 0.72 * 0.9 = 0.648
        # Weighted average = 0.648 / 0.9 = 0.72
        # Total weight = 0.9
        signal = aggregate_external(
            subject="alice",
            evaluator=repo_a,
            graph=graph,
            assertions_by_origin=assertions_by_origin,
            max_hops=2,
        )

        assert signal.value == 0.72
        assert signal.total_weight == 0.9
        assert signal.contributing_origins == [repo_b]
        assert len(signal.excluded_origins) == 0

    def test_indirect_origin_contribution_via_intermediate_hop(self) -> None:
        """Indirect origin C via B with weights 0.9 and 0.7, VOUCH strength 0.9:

        path weight 0.63, contribution 0.9 * 0.63 = 0.567.
        """
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")

        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.9))
        graph.add_edge(TrustEdge(source=repo_b, target=repo_c, weight=0.7))

        assertion_c = Assertion(
            origin=repo_c,
            subject="alice",
            kind=AssertionKind.VOUCH,
            strength=0.9,
            line_number=10,
        )

        assertions_by_origin = {
            repo_c: [assertion_c],
        }

        # Hand-calculated expectation:
        # Path A -> B -> C: weight = 0.9 * 0.7 = 0.63
        # Origin C:
        #   Path weight w_C = 0.63
        #   VOUCH strength = 0.9 -> signed value = +0.9
        #   Contribution c_C = 0.9 * 0.63 = 0.567
        #   Numerator component = c_C * w_C = 0.567 * 0.63 = 0.35721
        # Weighted average = 0.35721 / 0.63 = 0.567
        # Total weight = 0.63
        signal = aggregate_external(
            subject="alice",
            evaluator=repo_a,
            graph=graph,
            assertions_by_origin=assertions_by_origin,
            max_hops=2,
        )

        assert signal.value == 0.567
        assert signal.total_weight == 0.63
        assert signal.contributing_origins == [repo_c]

    def test_two_origins_weighted_average(self) -> None:
        """Two origins: B contributes 0.72 (weight 0.9) and C contributes 0.567 (weight 0.63)."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")

        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.9))
        graph.add_edge(TrustEdge(source=repo_b, target=repo_c, weight=0.7))

        assertion_b = Assertion(
            origin=repo_b,
            subject="alice",
            kind=AssertionKind.VOUCH,
            strength=0.8,
            line_number=3,
        )
        assertion_c = Assertion(
            origin=repo_c,
            subject="alice",
            kind=AssertionKind.VOUCH,
            strength=0.9,
            line_number=8,
        )

        assertions_by_origin = {
            repo_b: [assertion_b],
            repo_c: [assertion_c],
        }

        # Hand-calculated expectation:
        # Origin B:
        #   Path weight w_B = 0.9
        #   Signed value s_B = +0.8
        #   Contribution c_B = 0.8 * 0.9 = 0.72
        #   Numerator component = c_B * w_B = 0.72 * 0.9 = 0.648
        # Origin C:
        #   Path weight w_C = 0.9 * 0.7 = 0.63
        #   Signed value s_C = +0.9
        #   Contribution c_C = 0.9 * 0.63 = 0.567
        #   Numerator component = c_C * w_C = 0.567 * 0.63 = 0.35721
        # Total numerator = 0.648 + 0.35721 = 1.00521
        # Total denominator (total weight) = 0.9 + 0.63 = 1.53
        # Weighted average = 1.00521 / 1.53 = 0.657 (exact terminating decimal)
        signal = aggregate_external(
            subject="alice",
            evaluator=repo_a,
            graph=graph,
            assertions_by_origin=assertions_by_origin,
            max_hops=2,
        )

        assert signal.value == 0.657
        assert signal.total_weight == 1.53
        assert signal.contributing_origins == [repo_b, repo_c]

    def test_relayed_assertions_do_not_duplicate_or_alter_signal(self) -> None:
        """The same assertion arriving through two relays does not change the result."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_relay1 = RepoId("org/repo-relay1")
        repo_relay2 = RepoId("org/repo-relay2")

        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.9))
        graph.add_edge(TrustEdge(source=repo_a, target=repo_relay1, weight=0.8))
        graph.add_edge(TrustEdge(source=repo_a, target=repo_relay2, weight=0.7))

        # Origin B's direct assertion
        direct_assertion_b = Assertion(
            origin=repo_b,
            subject="alice",
            kind=AssertionKind.VOUCH,
            strength=0.8,
            line_number=2,
        )

        # Relayed copies of B's assertion present in relay1 and relay2 manifests
        relay_assertion = Assertion(
            origin=repo_b,  # Attributed to B, not to relay1 or relay2!
            subject="alice",
            kind=AssertionKind.VOUCH,
            strength=0.8,
            line_number=14,
        )

        assertions_by_origin = {
            repo_b: [direct_assertion_b],
            repo_relay1: [relay_assertion],
            repo_relay2: [relay_assertion],
        }

        # Hand-calculated expectation:
        # - repo_b: own assertion is counted (contribution 0.8 * 0.9 = 0.72, weight 0.9)
        # - repo_relay1: only relayed assertion from repo_b -> excluded as relay!
        # - repo_relay2: only relayed assertion from repo_b -> excluded as relay!
        # Total contributing origins: ONLY repo_b.
        # Signal value must be exactly 0.72, unchanged by relays.
        signal = aggregate_external(
            subject="alice",
            evaluator=repo_a,
            graph=graph,
            assertions_by_origin=assertions_by_origin,
            max_hops=2,
        )

        assert signal.value == 0.72
        assert signal.total_weight == 0.9
        assert signal.contributing_origins == [repo_b]

        excluded_map = dict(signal.excluded_origins)
        assert repo_relay1 in excluded_map
        assert "relay" in excluded_map[repo_relay1].lower()
        assert repo_relay2 in excluded_map
        assert "relay" in excluded_map[repo_relay2].lower()

    @pytest.mark.fairness
    def test_no_eligible_origins_returns_neutral_zero(self) -> None:
        """No eligible origins: value 0.0, total_weight 0.0, no division error.

        Fairness property: missing data is not negative evidence (AGENTS.md Rule 6).
        """
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_isolated = RepoId("org/repo-isolated")

        # repo_isolated has assertions but is not reachable from repo_a
        assertions_by_origin = {
            repo_isolated: [
                Assertion(
                    origin=repo_isolated,
                    subject="newcomer_dev",
                    kind=AssertionKind.VOUCH,
                    strength=1.0,
                )
            ]
        }

        # Hand-calculated expectation:
        # repo_isolated is unreachable (no path from repo_a).
        # Contributing origins: empty.
        # value: 0.0 (neutral), total_weight: 0.0, zero division avoided.
        signal = aggregate_external(
            subject="newcomer_dev",
            evaluator=repo_a,
            graph=graph,
            assertions_by_origin=assertions_by_origin,
            max_hops=2,
        )

        assert isinstance(signal, ExternalSignal)
        assert signal.value == 0.0
        assert signal.total_weight == 0.0
        assert signal.contributing_origins == []
        assert len(signal.excluded_origins) == 1
        assert signal.excluded_origins[0][0] == repo_isolated

    def test_denounce_produces_negative_contribution(self) -> None:
        """Denouncement produces negative signed value and negative weighted average."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")

        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.8))

        denounce_b = Assertion(
            origin=repo_b,
            subject="spammer",
            kind=AssertionKind.DENOUNCE,
            strength=0.9,
            line_number=1,
        )

        assertions_by_origin = {repo_b: [denounce_b]}

        # Hand-calculated expectation:
        # Origin B:
        #   Path weight = 0.8
        #   Signed value = -0.9
        #   Contribution = -0.9 * 0.8 = -0.72
        #   Numerator = -0.72 * 0.8 = -0.576
        # Weighted average = -0.576 / 0.8 = -0.72
        # Total weight = 0.8
        signal = aggregate_external(
            subject="spammer",
            evaluator=repo_a,
            graph=graph,
            assertions_by_origin=assertions_by_origin,
            max_hops=2,
        )

        assert signal.value == -0.72
        assert signal.total_weight == 0.8
        assert signal.contributing_origins == [repo_b]
