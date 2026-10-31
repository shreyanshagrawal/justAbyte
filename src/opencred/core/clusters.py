"""Mutual trust cluster detection and influence bounding.

Detects cycles and strongly connected components (SCCs) in the repository web-of-trust
graph so that mutual-trust clusters cannot multiply their influence collusively.
"""

from collections.abc import Iterable, Mapping, Sequence

from opencred.core.models import RepoId, TrustEdge

# ==============================================================================
# WHY STRONGLY CONNECTED COMPONENTS (SCCS) ARE USED:
#
# In decentralized trust networks, collusive or tightly-coupled repositories
# frequently form mutual-trust subgraphs (e.g., A -> B and B -> A, or larger
# trust rings A -> B -> C -> A). If each repository in such a ring were counted
# as an independent origin, an N-repository mutual cartel could artificially
# amplify its collective influence (denouncements or vouches) by a factor of N.
#
# Strongly connected components (SCCs) mathematically identify maximal subgraphs
# where every repository is mutually reachable from every other repository along
# directed trust edges. Using Tarjan's linear-time O(V + E) algorithm, OpenCred
# partitions the repository graph into disjoint SCCs:
# 1. Non-cyclic structures (such as one-way chains A -> B -> C) decompose into
#    independent singleton components ({A}, {B}, {C}).
# 2. Mutually-trusting rings and cliques collapse into multi-node origin groups.
#
# Influence bounding then caps the total external influence of any mutual cluster
# to that of its single strongest member, preventing Sybil amplification while
# preserving legitimate independent signals.
# ==============================================================================


def find_mutual_groups(
    graph: (
        Sequence[TrustEdge] | Mapping[RepoId, Iterable[RepoId]] | Iterable[tuple[RepoId, RepoId]]
    ),
) -> list[set[RepoId]]:
    """Find strongly connected mutual trust groups in the repository trust graph.

    Args:
        graph: A sequence of TrustEdge objects, a mapping of RepoId to target
            iterables, or an iterable of (source, target) tuples.

    Returns:
        A list of sets of RepoId representing the strongly connected components,
        sorted deterministically by their member names.
    """
    adj: dict[RepoId, set[RepoId]] = {}
    all_nodes: set[RepoId] = set()

    if isinstance(graph, Mapping):
        for src, targets in graph.items():
            src_repo = RepoId(src) if not isinstance(src, RepoId) else src
            all_nodes.add(src_repo)
            adj.setdefault(src_repo, set())
            for dst in targets:
                dst_repo = RepoId(dst) if not isinstance(dst, RepoId) else dst
                all_nodes.add(dst_repo)
                adj[src_repo].add(dst_repo)
                adj.setdefault(dst_repo, set())
    else:
        for item in graph:
            if isinstance(item, TrustEdge):
                src_repo = item.source
                dst_repo = item.target
            elif isinstance(item, tuple) and len(item) == 2:
                src_repo = RepoId(item[0]) if not isinstance(item[0], RepoId) else item[0]
                dst_repo = RepoId(item[1]) if not isinstance(item[1], RepoId) else item[1]
            else:
                raise TypeError(f"Unsupported graph element: {type(item).__name__}")
            all_nodes.add(src_repo)
            all_nodes.add(dst_repo)
            adj.setdefault(src_repo, set()).add(dst_repo)
            adj.setdefault(dst_repo, set())

    # Tarjan's strongly connected components algorithm
    index = 0
    indices: dict[RepoId, int] = {}
    lowlinks: dict[RepoId, int] = {}
    stack: list[RepoId] = []
    on_stack: set[RepoId] = set()
    sccs: list[set[RepoId]] = []

    def strongconnect(v: RepoId) -> None:
        nonlocal index
        indices[v] = index
        lowlinks[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        # Sort neighbors for deterministic traversal across environments
        for w in sorted(adj.get(v, set())):
            if w not in indices:
                strongconnect(w)
                lowlinks[v] = min(lowlinks[v], lowlinks[w])
            elif w in on_stack:
                lowlinks[v] = min(lowlinks[v], indices[w])

        if lowlinks[v] == indices[v]:
            scc: set[RepoId] = set()
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.add(w)
                if w == v:
                    break
            sccs.append(scc)

    # Sort vertices to guarantee byte-deterministic traversal order
    for node in sorted(all_nodes):
        if node not in indices:
            strongconnect(node)

    # Sort components deterministically by their sorted members
    sccs.sort(key=lambda scc: sorted(scc))
    return sccs


def cap_group_influence(
    group: Iterable[RepoId] | Mapping[RepoId, float],
    member_influences: Mapping[RepoId, float] | None = None,
) -> float:
    """Calculate the combined influence of a mutual group, capped to its strongest member.

    Args:
        group: A collection of RepoId members, or a mapping of RepoId to influence float.
        member_influences: Optional mapping of RepoId to influence float if group is an iterable.

    Returns:
        The maximum influence among all members present in the group (float in [0.0, 1.0]).
        If no members have influence, returns 0.0.
    """
    if member_influences is None:
        if isinstance(group, Mapping):
            values = [float(v) for v in group.values()]
            return max(values, default=0.0)
        raise ValueError("member_influences must be provided when group is not a Mapping")

    influences: list[float] = []
    for member in group:
        if member in member_influences:
            influences.append(float(member_influences[member]))

    return max(influences, default=0.0)


__all__ = [
    "cap_group_influence",
    "find_mutual_groups",
]
