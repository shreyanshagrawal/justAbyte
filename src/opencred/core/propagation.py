"""Trust propagation algorithms for OpenCred.

Calculates cumulative path weights across the repository web of trust and performs
origin deduplication by selecting the single strongest path per reachable origin
repository within the maximum propagation depth (2 hops).
"""

from pydantic import Field

from opencred.core.graph import TrustGraph
from opencred.core.models import OpenCredModel, RepoId, TrustEdge


class PathChoice(OpenCredModel):
    """The chosen path and its cumulative weight to a reachable origin repository."""

    weight: float = Field(ge=0.0, le=1.0, description="Cumulative path weight in [0.0, 1.0]")
    path: list[TrustEdge] = Field(description="Sequence of trust edges forming the simple path")

    @property
    def path_repr(self) -> str:
        """Deterministic string representation of the path for auditability and tie-breaking."""
        if not self.path:
            return ""
        nodes = [str(self.path[0].source)] + [str(e.target) for e in self.path]
        return " -> ".join(nodes)


def path_weight(path: list[TrustEdge]) -> float:
    """Calculate cumulative trust weight of a path as the product of edge weights.

    Args:
        path: List of TrustEdge instances representing a simple path.

    Returns:
        Product of edge weights, rounded to 6 decimal places for byte-determinism.
        Returns 0.0 for an empty path.
    """
    if not path:
        return 0.0

    accumulated = 1.0
    for edge in path:
        accumulated *= edge.weight

    return round(accumulated, 6)


def _path_representation(path: list[TrustEdge]) -> str:
    """Return a deterministic string representation for tie-breaking."""
    if not path:
        return ""
    nodes = [str(path[0].source)] + [str(e.target) for e in path]
    return " -> ".join(nodes)


def best_path_per_origin(
    graph: TrustGraph, evaluator: RepoId | str, max_hops: int = 2
) -> dict[RepoId, PathChoice]:
    """Find the single strongest path from evaluator to each reachable origin repository.

    For each reachable repository, keeps ONLY the path with the highest cumulative weight.
    Ties in path weight are broken by the lexicographically smallest path representation,
    guaranteeing strict determinism per AGENTS.md Rule 1.

    Args:
        graph: TrustGraph containing peer repository trust edges.
        evaluator: The evaluating repository identity.
        max_hops: Maximum path depth (1 or 2). Defaults to 2.

    Returns:
        Deterministic dictionary mapping reachable origin RepoId to its best PathChoice,
        sorted by RepoId.
    """
    evaluator_repo = RepoId(evaluator) if not isinstance(evaluator, RepoId) else evaluator
    reachable = graph.reachable_within(start=evaluator_repo, max_hops=max_hops)

    best_paths: dict[RepoId, PathChoice] = {}

    for origin in sorted(reachable.keys()):
        candidate_paths = reachable[origin]
        if not candidate_paths:
            continue

        # Sort paths by:
        # 1. Highest path_weight (descending -> -weight)
        # 2. Lexicographically smallest path representation (ascending)
        sorted_candidates = sorted(
            candidate_paths,
            key=lambda p: (-path_weight(p), _path_representation(p)),
        )

        chosen_path = sorted_candidates[0]
        best_paths[origin] = PathChoice(
            weight=path_weight(chosen_path),
            path=chosen_path,
        )

    return best_paths


__all__ = ["PathChoice", "best_path_per_origin", "path_weight"]
