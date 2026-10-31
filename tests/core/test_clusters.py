"""Unit tests for mutual trust cluster detection and influence bounding."""

import pytest

from opencred.core.clusters import cap_group_influence, find_mutual_groups
from opencred.core.models import RepoId, TrustEdge


class TestClusterDetectionAndBounding:
    """Tests for Tarjan's SCC-based mutual cluster detection and influence capping."""

    def test_two_mutual_repositories_report_as_one_group(self) -> None:
        """Two repositories with mutual trust edges A->B and B->A report as one group."""
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        edges = [
            TrustEdge(source=repo_a, target=repo_b, weight=0.8),
            TrustEdge(source=repo_b, target=repo_a, weight=0.9),
        ]

        groups = find_mutual_groups(edges)

        # Hand-calculated expectation: exactly one component containing {repo_a, repo_b}
        assert len(groups) == 1
        assert groups[0] == {repo_a, repo_b}

    def test_one_way_chain_produces_singleton_groups(self) -> None:
        """A one-way chain A -> B -> C produces singleton groups because there are no cycles."""
        repo_a = RepoId("chain/a")
        repo_b = RepoId("chain/b")
        repo_c = RepoId("chain/c")
        edges = [
            TrustEdge(source=repo_a, target=repo_b, weight=0.8),
            TrustEdge(source=repo_b, target=repo_c, weight=0.7),
        ]

        groups = find_mutual_groups(edges)

        # Hand-calculated expectation:
        # 3 singleton groups, sorted deterministically: {chain/a}, {chain/b}, {chain/c}
        assert len(groups) == 3
        assert groups[0] == {repo_a}
        assert groups[1] == {repo_b}
        assert groups[2] == {repo_c}

    @pytest.mark.fairness
    def test_eight_mutually_trusting_repositories_capped_to_strongest_member(self) -> None:
        """A group of 8 mutually-trusting repositories denouncing one contributor

        contributes at most the influence of one member.

        HAND-CALCULATED EXAMPLE:
        -------------------------------------------------------------------------
        Consider 8 repositories: R1 through R8, all mutually trusting each other
        (forming an 8-node complete directed clique of mutual trust edges).
        A contributor is denounced by all 8 repositories in this mutual syndicate.

        The evaluator's network evaluation computes the path influence for each
        origin repository:
            Influence(R1) = 0.70
            Influence(R2) = 0.85  <-- SINGLE STRONGEST MEMBER
            Influence(R3) = 0.60
            Influence(R4) = 0.75
            Influence(R5) = 0.50
            Influence(R6) = 0.65
            Influence(R7) = 0.80
            Influence(R8) = 0.40

        Without cluster influence bounding:
            Unbounded sum = 0.70 + 0.85 + 0.60 + 0.75 + 0.50 + 0.65 + 0.80 + 0.40 = 5.25
            (or an artificial 8x multiplication of denouncement strength).

        With cluster influence bounding (cap_group_influence):
            The 8 repositories collapse into ONE mutual origin group: {R1..R8}.
            Capped influence = max(0.70, 0.85, 0.60, 0.75, 0.50, 0.65, 0.80, 0.40)
                             = 0.85

        Therefore, the entire cartel contributes at most 0.85 (the influence of
        its single strongest member R2).
        -------------------------------------------------------------------------
        """
        repos = [RepoId(f"cluster/repo-{i}") for i in range(1, 9)]

        # Construct complete directed mutual trust edges between all 8 repositories
        edges: list[TrustEdge] = []
        for i, src in enumerate(repos):
            for j, dst in enumerate(repos):
                if i != j:
                    edges.append(TrustEdge(source=src, target=dst, weight=0.9))

        groups = find_mutual_groups(edges)

        # All 8 repositories collapse into exactly 1 mutual group
        assert len(groups) == 1
        assert groups[0] == set(repos)

        # Distinct influences per member
        member_influences: dict[RepoId, float] = {
            repos[0]: 0.70,
            repos[1]: 0.85,  # Strongest member
            repos[2]: 0.60,
            repos[3]: 0.75,
            repos[4]: 0.50,
            repos[5]: 0.65,
            repos[6]: 0.80,
            repos[7]: 0.40,
        }

        combined_influence = cap_group_influence(groups[0], member_influences)

        # Hand-calculated expectation: exactly 0.85
        assert combined_influence == pytest.approx(0.85)

        # Even if individual member influences sum to 5.25, the group's influence cannot exceed 0.85
        raw_sum = sum(member_influences.values())
        assert raw_sum == pytest.approx(5.25)
        assert combined_influence < raw_sum
        assert combined_influence == pytest.approx(member_influences[repos[1]])

    def test_results_are_deterministic_across_repeated_runs(self) -> None:
        """Results of find_mutual_groups are byte-deterministic across repeated executions."""
        # Create a graph with mixed cycles, isolated nodes, and one-way edges
        r1, r2, r3, r4, r5 = [RepoId(f"det/repo-{i}") for i in range(1, 6)]
        edges = [
            TrustEdge(source=r1, target=r2, weight=0.5),
            TrustEdge(source=r2, target=r1, weight=0.6),  # r1 <-> r2
            TrustEdge(source=r2, target=r3, weight=0.7),
            TrustEdge(source=r3, target=r4, weight=0.8),
            TrustEdge(source=r4, target=r3, weight=0.9),  # r3 <-> r4
            TrustEdge(source=r5, target=r1, weight=0.5),  # r5 -> r1
        ]

        run1 = find_mutual_groups(edges)
        run2 = find_mutual_groups(edges)

        # Convert sets to sorted lists for exact byte comparison
        run1_sorted = [sorted(list(g)) for g in run1]
        run2_sorted = [sorted(list(g)) for g in run2]

        assert run1_sorted == run2_sorted

        # Expected components:
        # {r1, r2}, {r3, r4}, {r5}
        assert len(run1) == 3
        assert {r1, r2} in run1
        assert {r3, r4} in run1
        assert {r5} in run1
