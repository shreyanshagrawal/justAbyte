"""External trust signal aggregation for OpenCred.

Combines assertions from trusted peer repositories using origin deduplication,
shortest/strongest eligible paths, and weighted averaging over propagation weights.
"""

from pydantic import Field

from opencred.core.graph import TrustGraph
from opencred.core.models import Assertion, AssertionKind, OpenCredModel, RepoId
from opencred.core.propagation import best_path_per_origin


class ExternalSignal(OpenCredModel):
    """Aggregated trust signal derived from reachable external peer repositories."""

    value: float = Field(
        ge=-1.0,
        le=1.0,
        description="Weighted average trust signal in [-1.0, +1.0]",
    )
    total_weight: float = Field(
        ge=0.0,
        description="Sum of path weights for contributing origins",
    )
    contributing_origins: list[RepoId] = Field(
        default_factory=list,
        description="Deterministically sorted list of origins contributing to the signal",
    )
    excluded_origins: list[tuple[RepoId, str]] = Field(
        default_factory=list,
        description="Origins that were queried or reachable but excluded, paired with reasons",
    )


def aggregate_external(
    subject: str,
    evaluator: RepoId | str,
    graph: TrustGraph,
    assertions_by_origin: dict[RepoId, list[Assertion]],
    max_hops: int = 2,
) -> ExternalSignal:
    """Aggregate external contributor assertions across the repository web of trust.

    Algorithm:
    1. Retrieve the single best path per origin for the evaluator repository.
    2. For each reachable origin with a path weight > 0:
       a. Collect that origin's own direct assertions about the subject.
          Assertions attributed to a different origin are relays and excluded.
       b. Deduplicate identical assertions by content.
       c. Compute the origin's signed value: +strength for VOUCH, -strength for DENOUNCE.
       d. Multiply by the path weight to obtain the origin's contribution.
    3. Combine the contributions as a weighted average over path weights.
    4. Record every excluded origin and the reason for auditability.

    Args:
        subject: Contributor username/login being evaluated.
        evaluator: The evaluating repository identity.
        graph: TrustGraph containing peer repository trust edges.
        assertions_by_origin: Mapping of origin RepoId to its declared assertions.
        max_hops: Maximum propagation depth (1 or 2). Defaults to 2.

    Returns:
        ExternalSignal containing the aggregated score, total weight, contributing origins,
        and excluded origins with reasons.
    """
    evaluator_repo = RepoId(evaluator) if not isinstance(evaluator, RepoId) else evaluator
    norm_subject = subject.strip().lstrip("@").lower()

    # 1. Get best_path_per_origin for evaluator (enforces origin deduplication)
    best_paths = best_path_per_origin(graph, evaluator=evaluator_repo, max_hops=max_hops)

    excluded_origins: list[tuple[RepoId, str]] = []
    # (origin, path_weight, contribution)
    contributing_data: list[tuple[RepoId, float, float]] = []

    # Consider all origins either declared in assertions or reachable in graph
    all_candidate_origins = set(assertions_by_origin.keys()) | set(best_paths.keys())

    for origin in sorted(all_candidate_origins):
        # The evaluator repository itself represents local trust, not external
        if origin == evaluator_repo:
            excluded_origins.append((origin, "evaluator is local repository, not external"))
            continue

        # Check reachability within max_hops
        if origin not in best_paths:
            msg = f"origin '{origin}' is not reachable from evaluator within {max_hops} hops"
            excluded_origins.append((origin, msg))
            continue

        path_w = best_paths[origin].weight
        if path_w <= 0.0:
            excluded_origins.append((origin, f"path weight to origin '{origin}' is 0.0"))
            continue

        raw_assertions = assertions_by_origin.get(origin, [])
        if not raw_assertions:
            excluded_origins.append((origin, f"origin '{origin}' has no assertions"))
            continue

        # Filter assertions for the specific subject
        subject_assertions = [a for a in raw_assertions if a.subject == norm_subject]
        if not subject_assertions:
            excluded_origins.append(
                (origin, f"origin '{origin}' has no assertions for subject '{norm_subject}'")
            )
            continue

        # 2a. Collect only that origin's own direct assertions; relays are excluded
        own_assertions = [a for a in subject_assertions if a.origin == origin]
        if not own_assertions:
            msg = f"all assertions from origin '{origin}' are relays attributed to other origins"
            excluded_origins.append((origin, msg))
            continue

        # 2b. Deduplicate identical assertions by content (kind, strength, subject, origin)
        unique_assertions: list[Assertion] = []
        seen_keys: set[tuple[AssertionKind, float, str, RepoId]] = set()
        for a in own_assertions:
            key = (a.kind, a.strength, a.subject, a.origin)
            if key not in seen_keys:
                seen_keys.add(key)
                unique_assertions.append(a)

        # 2c. Compute the origin's signed value: +strength for VOUCH, -strength for DENOUNCE
        signed_values = [
            a.strength if a.kind == AssertionKind.VOUCH else -a.strength for a in unique_assertions
        ]
        origin_signed_value = sum(signed_values) / len(signed_values)

        # 2d. Multiply by path weight to get the origin's contribution
        contribution = origin_signed_value * path_w
        contributing_data.append((origin, path_w, contribution))

    # 3. Combine contributions as a weighted average over path weights
    if not contributing_data:
        return ExternalSignal(
            value=0.0,
            total_weight=0.0,
            contributing_origins=[],
            excluded_origins=sorted(excluded_origins, key=lambda x: (x[0], x[1])),
        )

    total_weight = sum(w for _, w, _ in contributing_data)
    if total_weight <= 0.0:
        return ExternalSignal(
            value=0.0,
            total_weight=0.0,
            contributing_origins=[],
            excluded_origins=sorted(excluded_origins, key=lambda x: (x[0], x[1])),
        )

    # Weighted average of contributions over path weights: sum(c_i * w_i) / sum(w_i)
    numerator = sum(contrib * w for _, w, contrib in contributing_data)
    weighted_avg = round(numerator / total_weight, 6)
    weighted_avg = max(-1.0, min(1.0, weighted_avg))

    return ExternalSignal(
        value=weighted_avg,
        total_weight=round(total_weight, 6),
        contributing_origins=sorted([origin for origin, _, _ in contributing_data]),
        excluded_origins=sorted(excluded_origins, key=lambda x: (x[0], x[1])),
    )


__all__ = ["ExternalSignal", "aggregate_external"]
