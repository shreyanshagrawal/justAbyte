"""Unit tests for OpenCred trust propagation and origin deduplication."""

from opencred.core.graph import TrustGraph
from opencred.core.models import RepoId, TrustEdge
from opencred.core.propagation import PathChoice, best_path_per_origin, path_weight


class TestPathWeight:
    """Tests for path_weight calculation."""

    def test_empty_path_weight(self) -> None:
        """An empty path returns 0.0 weight."""
        # Hand-calculated expectation: empty path has 0.0 weight
        assert path_weight([]) == 0.0

    def test_single_edge_path_weight(self) -> None:
        """A -> B with weight 0.9: path weight 0.9."""
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.9)

        # Hand-calculated expectation:
        # A -> B with weight 0.9: path weight 0.9
        assert path_weight([edge_ab]) == 0.9

    def test_two_edge_path_weight(self) -> None:
        """A -> B -> C with weights 0.9 and 0.7: 0.9 * 0.7 = 0.63."""
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")

        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.9)
        edge_bc = TrustEdge(source=repo_b, target=repo_c, weight=0.7)

        # Hand-calculated expectation: 0.9 * 0.7 = 0.63
        # Note for the reviewer: this is the consolidated plan's example for a single path.
        # The consolidated plan's worked example for an indirect signal also multiplies by
        # the source's signal value (+0.9 * 0.56 = +0.504). That multiplication happens in
        # Phase 6.3, not here.
        assert path_weight([edge_ab, edge_bc]) == 0.63


class TestBestPathPerOrigin:
    """Tests for best_path_per_origin deduplication and tie-breaking."""

    def test_multipath_keeps_highest_weight(self) -> None:
        """Two paths to C, one via B (0.9*0.7=0.63) and one direct (weight 0.5): keep 0.63."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")

        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.9)
        edge_bc = TrustEdge(source=repo_b, target=repo_c, weight=0.7)
        edge_ac = TrustEdge(source=repo_a, target=repo_c, weight=0.5)

        graph.add_edge(edge_ab)
        graph.add_edge(edge_bc)
        graph.add_edge(edge_ac)

        # Hand-calculated expectations:
        # For origin B:
        #   Only 1 path: [edge_ab] with weight 0.9
        # For origin C:
        #   Path 1: [edge_ab, edge_bc] with weight 0.9 * 0.7 = 0.63
        #   Path 2: [edge_ac] with weight 0.5
        #   0.63 > 0.5 -> Keep Path 1 with weight 0.63
        choices = best_path_per_origin(graph, evaluator=repo_a, max_hops=2)

        assert sorted(choices.keys()) == [repo_b, repo_c]
        assert choices[repo_b] == PathChoice(weight=0.9, path=[edge_ab])
        assert choices[repo_c] == PathChoice(weight=0.63, path=[edge_ab, edge_bc])

    def test_three_hop_path_excluded_when_max_hops_is_two(self) -> None:
        """A path of three hops is excluded when max_hops=2."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")
        repo_d = RepoId("org/repo-d")

        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.9)
        edge_bc = TrustEdge(source=repo_b, target=repo_c, weight=0.8)
        edge_cd = TrustEdge(source=repo_c, target=repo_d, weight=0.7)

        graph.add_edge(edge_ab)
        graph.add_edge(edge_bc)
        graph.add_edge(edge_cd)

        # Hand-calculated expectations:
        # D is 3 hops away from A: A -> B -> C -> D
        # With max_hops=2, only B (1 hop) and C (2 hops) are reachable. D is excluded.
        choices = best_path_per_origin(graph, evaluator=repo_a, max_hops=2)

        assert repo_d not in choices
        assert sorted(choices.keys()) == [repo_b, repo_c]
        assert choices[repo_b] == PathChoice(weight=0.9, path=[edge_ab])
        # Hand-calculated expectation: 0.9 * 0.8 = 0.72
        assert choices[repo_c] == PathChoice(weight=0.72, path=[edge_ab, edge_bc])

    def test_ties_resolved_deterministically(self) -> None:
        """Two paths with identical cumulative weight break ties lexicographically."""
        graph = TrustGraph()
        repo_a = RepoId("org/repo-a")
        repo_b = RepoId("org/repo-b")
        repo_c = RepoId("org/repo-c")
        repo_d = RepoId("org/repo-d")

        # Path 1 via B: A -> B (0.8), B -> D (0.5) -> cumulative weight 0.8 * 0.5 = 0.40
        edge_ab = TrustEdge(source=repo_a, target=repo_b, weight=0.8)
        edge_bd = TrustEdge(source=repo_b, target=repo_d, weight=0.5)

        # Path 2 via C: A -> C (0.8), C -> D (0.5) -> cumulative weight 0.8 * 0.5 = 0.40
        edge_ac = TrustEdge(source=repo_a, target=repo_c, weight=0.8)
        edge_cd = TrustEdge(source=repo_c, target=repo_d, weight=0.5)

        # Add edges in reverse alphabetical order: C first, then B
        graph.add_edge(edge_ac)
        graph.add_edge(edge_cd)
        graph.add_edge(edge_ab)
        graph.add_edge(edge_bd)

        # Hand-calculated expectations:
        # Weight(Path 1: A -> B -> D) = 0.8 * 0.5 = 0.40
        # Weight(Path 2: A -> C -> D) = 0.8 * 0.5 = 0.40
        # Lexicographical path representations:
        #   Path 1: "org/repo-a -> org/repo-b -> org/repo-d"
        #   Path 2: "org/repo-a -> org/repo-c -> org/repo-d"
        # Since "org/repo-b" < "org/repo-c", Path 1 is lexicographically smaller.
        # Tie-breaker must deterministically select Path 1 regardless of insertion order.
        choices = best_path_per_origin(graph, evaluator=repo_a, max_hops=2)

        assert choices[repo_d] == PathChoice(weight=0.40, path=[edge_ab, edge_bd])
        assert choices[repo_d].path_repr == "org/repo-a -> org/repo-b -> org/repo-d"

    def test_evaluator_with_no_outgoing_edges(self) -> None:
        """An evaluator with no trust edges returns an empty dictionary."""
        graph = TrustGraph()
        evaluator = RepoId("isolated/repo")

        # Hand-calculated expectation: empty dict {}
        assert best_path_per_origin(graph, evaluator=evaluator, max_hops=2) == {}
