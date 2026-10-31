"""Unit tests for TrustGraph and path discovery."""

import pytest

from opencred.core.graph import TrustGraph
from opencred.core.models import RepoId, TrustEdge


class TestTrustGraphEdgeManagement:
    """Tests for edge insertion, conflict resolution, notes, and outgoing queries."""

    def test_add_edge_and_outgoing_sorting(self) -> None:
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")
        repo_d = RepoId("org/repo-d")

        # Insert edges in non-alphabetical target order: C, D, B
        e1 = TrustEdge(source=repo_a, target=repo_c, weight=0.6)
        e2 = TrustEdge(source=repo_a, target=repo_d, weight=0.4)
        e3 = TrustEdge(source=repo_a, target=repo_b, weight=0.9)

        graph.add_edge(e1)
        graph.add_edge(e2)
        graph.add_edge(e3)

        # Hand-calculated expectation: outgoing sorted deterministically by target RepoId
        # [repo-b (0.9), repo-c (0.6), repo-d (0.4)]
        outgoing = graph.outgoing(repo_a)
        assert len(outgoing) == 3
        assert [e.target for e in outgoing] == [repo_b, repo_c, repo_d]
        assert [e.weight for e in outgoing] == [0.9, 0.6, 0.4]

        # Querying a repository with no outgoing edges returns an empty list
        assert graph.outgoing(repo_b) == []

    def test_add_duplicate_edge_keeps_higher_weight_and_records_note(self) -> None:
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")

        # Initial edge with weight 0.5
        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.5))
        assert len(graph.outgoing(repo_a)) == 1
        assert graph.outgoing(repo_a)[0].weight == 0.5
        assert len(graph.notes) == 0

        # Duplicate edge with lower weight 0.3: existing higher weight 0.5 is kept
        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.3))
        # Hand-calculated expectation: weight remains 0.5, note recorded
        assert graph.outgoing(repo_a)[0].weight == 0.5
        assert len(graph.notes) == 1
        assert "kept existing weight 0.5 over incoming weight 0.3" in graph.notes[0]

        # Duplicate edge with higher weight 0.85: replaced with 0.85, note recorded
        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.85))
        # Hand-calculated expectation: weight updated to 0.85, second note recorded
        assert graph.outgoing(repo_a)[0].weight == 0.85
        assert len(graph.notes) == 2
        assert "replaced weight 0.5 with higher weight 0.85" in graph.notes[1]


class TestTrustGraphReachableWithin:
    """Tests for reachable_within path discovery, hop limits, cycle handling, and directionality."""

    def test_direction_is_respected(self) -> None:
        """A -> B does not produce B -> A."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")

        graph.add_edge(TrustEdge(source=repo_a, target=repo_b, weight=0.8))

        # Hand-calculated expectation:
        # From A: reachable is {B: [[A -> B]]}
        # From B: reachable is empty {}
        paths_from_a = graph.reachable_within(repo_a, max_hops=1)
        assert list(paths_from_a.keys()) == [repo_b]
        assert len(paths_from_a[repo_b]) == 1
        assert paths_from_a[repo_b][0] == [TrustEdge(source=repo_a, target=repo_b, weight=0.8)]

        paths_from_b = graph.reachable_within(repo_b, max_hops=1)
        assert paths_from_b == {}

    def test_cycle_terminates_and_excludes_start_node(self) -> None:
        """A two-edge cycle A -> B -> A terminates and does not return A as a target."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")

        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.9)
        edge_ba = TrustEdge(source=repo_b, target=repo_a, weight=0.7)

        graph.add_edge(edge_ab)
        graph.add_edge(edge_ba)

        # Hand-calculated expectation:
        # With max_hops=2:
        # 1-hop from A: [A -> B] (target B)
        # 2-hop from A: [A -> B, B -> A] is a cycle returning to start; excluded!
        # Target A must NEVER appear in the result dictionary.
        # Result must contain only B: [[A -> B]]
        paths_from_a = graph.reachable_within(repo_a, max_hops=2)
        assert repo_a not in paths_from_a
        assert list(paths_from_a.keys()) == [repo_b]
        assert len(paths_from_a[repo_b]) == 1
        assert paths_from_a[repo_b][0] == [edge_ab]

        # Symmetrically from B:
        paths_from_b = graph.reachable_within(repo_b, max_hops=2)
        assert repo_b not in paths_from_b
        assert list(paths_from_b.keys()) == [repo_a]
        assert paths_from_b[repo_a][0] == [edge_ba]

    def test_path_longer_than_max_hops_is_excluded(self) -> None:
        """Chain A -> B -> C. When max_hops=1, C is excluded. When max_hops=2, C is included."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")

        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.8)
        edge_bc = TrustEdge(source=repo_b, target=repo_c, weight=0.7)
        graph.add_edge(edge_ab)
        graph.add_edge(edge_bc)

        # Hand-calculated expectation with max_hops=1:
        # Only 1-hop path to B is returned. C (2 hops away) is excluded.
        paths_hop_1 = graph.reachable_within(repo_a, max_hops=1)
        assert repo_c not in paths_hop_1
        assert list(paths_hop_1.keys()) == [repo_b]
        assert paths_hop_1[repo_b] == [[edge_ab]]

        # Hand-calculated expectation with max_hops=2:
        # Both B (1 hop) and C (2 hops: [A->B, B->C]) are returned.
        paths_hop_2 = graph.reachable_within(repo_a, max_hops=2)
        assert sorted(paths_hop_2.keys()) == [repo_b, repo_c]
        assert paths_hop_2[repo_b] == [[edge_ab]]
        assert paths_hop_2[repo_c] == [[edge_ab, edge_bc]]

    def test_two_different_paths_to_same_repository_both_returned(self) -> None:
        """Diamond/multi-path: A -> B (direct 1-hop) and A -> C -> B (indirect 2-hop)."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")

        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.9)
        edge_ac = TrustEdge(source=repo_a, target=repo_c, weight=0.6)
        edge_cb = TrustEdge(source=repo_c, target=repo_b, weight=0.8)

        graph.add_edge(edge_ab)
        graph.add_edge(edge_ac)
        graph.add_edge(edge_cb)

        # Hand-calculated expectation for reachable_within(A, max_hops=2):
        # Target B has two simple paths:
        # Path 1 (length 1): [edge_ab]
        # Path 2 (length 2): [edge_ac, edge_cb]
        # Target C has one path:
        # Path 1 (length 1): [edge_ac]
        paths = graph.reachable_within(repo_a, max_hops=2)
        assert sorted(paths.keys()) == [repo_b, repo_c]

        assert len(paths[repo_b]) == 2
        assert paths[repo_b][0] == [edge_ab]
        assert paths[repo_b][1] == [edge_ac, edge_cb]

        assert len(paths[repo_c]) == 1
        assert paths[repo_c][0] == [edge_ac]

    @pytest.mark.parametrize("invalid_hops", [-1, 0, 3, 4, 10])
    def test_max_hops_validation_rejects_values_other_than_one_or_two(
        self, invalid_hops: int
    ) -> None:
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")

        with pytest.raises(ValueError, match="max_hops must be 1 or 2"):
            graph.reachable_within(repo_a, max_hops=invalid_hops)
