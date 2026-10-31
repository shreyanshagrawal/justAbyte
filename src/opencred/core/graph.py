"""Directed repository trust graph for OpenCred.

Maintains directional trust edges between repositories and discovers simple paths
up to the maximum propagation depth (2 hops) defined in AGENTS.md.
"""

from opencred.core.models import RepoId, TrustEdge


class TrustGraph:
    """A directed graph representing trust relationships between repositories.

    Attributes:
        notes: Log of actions taken when handling duplicate edges or conflicts.
    """

    def __init__(self) -> None:
        # Maps source RepoId -> target RepoId -> TrustEdge
        self._edges: dict[RepoId, dict[RepoId, TrustEdge]] = {}
        self.notes: list[str] = []

    def add_edge(self, edge: TrustEdge) -> None:
        """Add a directed trust edge to the graph.

        If an edge with the same source and target already exists, the edge with
        the higher weight is preserved, and an explicit note is recorded.
        """
        source = edge.source
        target = edge.target

        if source not in self._edges:
            self._edges[source] = {}

        if target in self._edges[source]:
            existing = self._edges[source][target]
            if edge.weight > existing.weight:
                self._edges[source][target] = edge
                note = (
                    f"Duplicate edge {source} -> {target}: replaced weight {existing.weight} "
                    f"with higher weight {edge.weight}"
                )
            else:
                note = (
                    f"Duplicate edge {source} -> {target}: kept existing weight {existing.weight} "
                    f"over incoming weight {edge.weight}"
                )
            self.notes.append(note)
        else:
            self._edges[source][target] = edge

    def outgoing(self, repo: RepoId | str) -> list[TrustEdge]:
        """Return a deterministically sorted list of outgoing edges from repo."""
        repo_id = RepoId(repo) if not isinstance(repo, RepoId) else repo
        if repo_id not in self._edges:
            return []
        edges = list(self._edges[repo_id].values())
        edges.sort(key=lambda e: e.target)
        return edges

    def reachable_within(
        self, start: RepoId | str, max_hops: int
    ) -> dict[RepoId, list[list[TrustEdge]]]:
        """Find every simple path from start to all reachable repositories within max_hops.

        Args:
            start: The root repository evaluating trust.
            max_hops: Maximum path length. For OpenCred MVP, must be 1 or 2.

        Returns:
            Dictionary mapping each reachable target RepoId to a list of simple paths,
            where each path is a list of TrustEdge instances.

        Raises:
            ValueError: If max_hops is not 1 or 2.
        """
        if max_hops not in (1, 2):
            raise ValueError(f"max_hops must be 1 or 2 for this MVP, got {max_hops}")

        start_repo = RepoId(start) if not isinstance(start, RepoId) else start
        result: dict[RepoId, list[list[TrustEdge]]] = {}

        def _dfs(current: RepoId, current_path: list[TrustEdge], visited: set[RepoId]) -> None:
            if len(current_path) >= max_hops:
                return

            for edge in self.outgoing(current):
                target = edge.target
                if target in visited:
                    continue

                new_path = [*current_path, edge]
                result.setdefault(target, []).append(new_path)
                _dfs(target, new_path, visited | {target})

        _dfs(start_repo, [], {start_repo})

        # Deterministic sorting of keys and paths
        sorted_result: dict[RepoId, list[list[TrustEdge]]] = {}
        for target in sorted(result.keys()):
            paths = result[target]
            paths.sort(key=lambda p: (len(p), [e.target for e in p]))
            sorted_result[target] = paths

        return sorted_result

    def all_edges(self) -> list[TrustEdge]:
        """Return all edges in the graph sorted deterministically by (source, target)."""
        edges: list[TrustEdge] = []
        for targets in self._edges.values():
            edges.extend(targets.values())
        edges.sort(key=lambda e: (e.source, e.target))
        return edges

    def all_nodes(self) -> set[RepoId]:
        """Return all node RepoIds in the graph (sources and targets)."""
        nodes: set[RepoId] = set()
        for source, targets in self._edges.items():
            nodes.add(source)
            nodes.update(targets.keys())
        return nodes

    def __repr__(self) -> str:
        return f"TrustGraph(nodes={len(self.all_nodes())}, edges={len(self.all_edges())})"


__all__ = ["TrustGraph"]
