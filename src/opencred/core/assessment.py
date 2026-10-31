"""End-to-end pull request assessment pipeline.

This module provides the pure assessment function integrating:
1. Evaluator base-branch manifest parsing and TrustGraph construction.
2. Peer manifest ingestion restricted strictly to evaluator's direct trust list.
3. Local evidence extraction (evaluator's own assertions about the subject).
4. External trust signal aggregation over reachable peer repositories.
5. Corroboration and single-origin influence bounding.
6. Contribution quality evidence and newcomer fairness evaluation.
7. Campaign risk detection across trusted repository telemetry.
8. Advisory triage decision generation.

All operations strictly obey AGENTS.md rules:
- Pure function: no file I/O, no network calls, no clock reads.
- Determinism: no timestamps, no random values, all collections sorted.
- Base-Branch Trust: manifest and telemetry inputs must be base-branch data.
- Advisory only: produces maintainer recommendations, never automated enforcement.
"""

from typing import Any

from pydantic import Field

from opencred.core.aggregate import aggregate_external
from opencred.core.campaign import detect_campaigns
from opencred.core.corroboration import LocalEvidence, apply_corroboration
from opencred.core.graph import TrustGraph
from opencred.core.manifests import parse_manifest
from opencred.core.models import (
    Assertion,
    AssertionKind,
    ContributionEvent,
    OpenCredModel,
    PullRequestRecord,
    RepoId,
)
from opencred.core.newcomer import is_newcomer
from opencred.core.propagation import best_path_per_origin
from opencred.core.quality import QualityConfig, contribution_quality_evidence
from opencred.core.telemetry import (
    TelemetryEntry,
    TelemetryLoadResult,
    TelemetryStatus,
)
from opencred.core.triage import TriageOutcome, decide


class Assessment(OpenCredModel):
    """Advisory assessment result for a pull request."""

    network_trust: float = Field(
        ge=-1.0,
        le=1.0,
        description="Corroborated network trust score in [-1.0, 1.0]",
    )
    campaign_risk: float = Field(
        ge=0.0,
        le=1.0,
        description="Assessed campaign risk score in [0.0, 1.0]",
    )
    contribution_quality_evidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Contribution quality evidence score in [0.0, 1.0]",
    )
    triage: TriageOutcome = Field(
        description="Advisory triage recommendation for maintainers",
    )
    reasons: list[str] = Field(
        default_factory=list,
        description="Sorted list of explainability reason strings",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Sorted list of contributing origins with propagation hop counts",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Sorted auditability notes (limited-evidence, corroboration, exclusions)",
    )


def assess(
    pr: PullRequestRecord,
    base_manifests: dict[RepoId, str],
    evaluator: RepoId,
    peer_manifests: dict[RepoId, str],
    telemetry: dict[RepoId, TelemetryLoadResult],
    history: list[ContributionEvent],
    config: QualityConfig | Any = None,
) -> Assessment:
    """Assess a pull request and return a deterministic, advisory Assessment result.

    Pipeline:
    1. Parse the evaluator's base manifest and construct the TrustGraph.
       Security constraint: Peer edges beyond the evaluator's own declared trust
       are NOT added automatically. Only the evaluator's direct trust list determines
       which peers it reads from.
    2. Build assertions_by_origin from parsed manifests.
    3. Compute local evidence (evaluator's own assertions about the author).
    4. Compute aggregate_external over reachable peer repositories.
    5. Apply corroboration and bounded-influence caps.
    6. Compute contribution quality evidence and newcomer status.
    7. Run campaign detection over fresh telemetry from evaluator and trusted peers.
    8. Run advisory triage decision.
    9. Return Assessment with deterministic, sorted collections and no timestamps.
    """
    evaluator_repo = RepoId(evaluator)
    notes_accumulator: list[str] = []

    # 1. Parse evaluator's base manifest and construct TrustGraph
    eval_manifest_text = base_manifests.get(evaluator_repo, "")
    eval_parse = parse_manifest(eval_manifest_text, owner=evaluator_repo)

    graph = TrustGraph()
    for edge in eval_parse.trust_edges:
        graph.add_edge(edge)

    # Documented Architecture Rule:
    # Only the evaluator's direct trust list determines which peers it reads from.
    # Peer edges beyond the evaluator's own declared trust are NOT added automatically.
    direct_trusted_peers = sorted({edge.target for edge in eval_parse.trust_edges})

    # 2. Build assertions_by_origin from parsed manifests
    assertions_by_origin: dict[RepoId, list[Assertion]] = {
        evaluator_repo: list(eval_parse.assertions),
    }

    for peer in direct_trusted_peers:
        if peer in peer_manifests:
            peer_parse = parse_manifest(peer_manifests[peer], owner=peer)
            # Add peer's trust edges to discover paths up to 2 hops
            for edge in peer_parse.trust_edges:
                graph.add_edge(edge)
            assertions_by_origin[peer] = list(peer_parse.assertions)
            for err_line, err_msg in peer_parse.errors:
                notes_accumulator.append(
                    f"manifest error in peer '{peer}' at line {err_line}: {err_msg}"
                )

    # Reachable origins within 2 hops whose manifests are provided in peer_manifests
    best_paths = best_path_per_origin(graph, evaluator=evaluator_repo, max_hops=2)
    for origin in sorted(best_paths.keys()):
        if origin not in assertions_by_origin and origin in peer_manifests:
            origin_parse = parse_manifest(peer_manifests[origin], owner=origin)
            assertions_by_origin[origin] = list(origin_parse.assertions)
            for err_line, err_msg in origin_parse.errors:
                notes_accumulator.append(
                    f"manifest error in origin '{origin}' at line {err_line}: {err_msg}"
                )

    # 3. Compute local evidence (evaluator's own assertions about the author)
    eval_subject_assertions = [a for a in eval_parse.assertions if a.subject == pr.author]
    local_denounced = any(a.kind == AssertionKind.DENOUNCE for a in eval_subject_assertions)
    local_vouched = any(a.kind == AssertionKind.VOUCH for a in eval_subject_assertions)
    local_evidence = LocalEvidence(
        has_denouncement=local_denounced,
        has_vouch=local_vouched,
    )

    # 4. Compute aggregate_external
    external_signal = aggregate_external(
        subject=pr.author,
        evaluator=evaluator_repo,
        graph=graph,
        assertions_by_origin=assertions_by_origin,
        max_hops=2,
    )
    for excluded_orig, reason in external_signal.excluded_origins:
        notes_accumulator.append(f"excluded origin '{excluded_orig}': {reason}")

    # 5. Apply corroboration
    corroborated = apply_corroboration(local=local_evidence, external=external_signal)
    notes_accumulator.extend(corroborated.notes)

    # 6. Compute contribution_quality_evidence and newcomer flag
    quality_evidence = contribution_quality_evidence(
        pr=pr,
        subject_history=history,
        config=config,
    )

    # Count total subject network assertions across local and external sources
    total_subject_assertions = (
        len(eval_subject_assertions)
        + len(external_signal.vouching_origins)
        + len(external_signal.denouncing_origins)
    )

    newcomer_flag = is_newcomer(
        subject_history=history,
        network_assertions_count=total_subject_assertions,
    )

    # 7. Run campaign detection over telemetry from trusted repos plus evaluator's telemetry
    telemetry_items: list[tuple[RepoId, TelemetryEntry]] = []
    telemetry_repos = [evaluator_repo, *direct_trusted_peers]

    if not telemetry:
        notes_accumulator.append("limited evidence: telemetry is absent")
    else:
        for r in telemetry_repos:
            if r in telemetry:
                load_res = telemetry[r]
                if load_res.status == TelemetryStatus.FRESH:
                    for entry in load_res.entries:
                        telemetry_items.append((r, entry))
                for note in load_res.notes:
                    notes_accumulator.append(note)
            else:
                notes_accumulator.append(f"limited evidence: telemetry is absent for '{r}'")

    campaign_res = detect_campaigns(
        prs=[pr],
        telemetry_entries=telemetry_items,
    )

    pr_key = f"{pr.repo}#{pr.number}"
    matched_candidate = next(
        (c for c in campaign_res.candidates if pr_key in c.pr_keys),
        None,
    )
    if matched_candidate:
        campaign_risk = matched_candidate.campaign_risk
    else:
        campaign_risk = 0.0

    for excluded_comp in campaign_res.excluded:
        if pr_key in excluded_comp.pr_keys and excluded_comp.excluded_reason:
            notes_accumulator.append(excluded_comp.excluded_reason)

    # 8. Run triage.decide
    has_vouch = local_evidence.has_vouch or len(external_signal.vouching_origins) > 0
    has_denounce = local_evidence.has_denouncement or len(external_signal.denouncing_origins) > 0
    conflicting = bool(has_vouch and has_denounce)

    outcome, triage_reasons = decide(
        network_trust=corroborated.network_trust,
        campaign_risk=campaign_risk,
        quality=quality_evidence,
        is_newcomer=newcomer_flag,
        severe=corroborated.is_severe,
        conflicting=conflicting,
        independent_origins_count=corroborated.independent_denounce_count,
    )

    # 9. Format sources with propagation hop counts
    best_paths = best_path_per_origin(graph, evaluator=evaluator_repo, max_hops=2)
    sources_set: set[str] = set()

    if local_evidence.has_vouch or local_evidence.has_denouncement:
        sources_set.add(f"{evaluator_repo} (0 hops)")

    for origin in external_signal.contributing_origins:
        if origin in best_paths:
            hops = len(best_paths[origin].path)
            hop_str = f"{hops} hop" if hops == 1 else f"{hops} hops"
            sources_set.add(f"{origin} ({hop_str})")
        else:
            sources_set.add(f"{origin} (external)")

    # Sort all collections deterministically
    sorted_sources = sorted(sources_set)
    sorted_reasons = sorted(set(triage_reasons + quality_evidence.reasons))
    sorted_notes = sorted(set(notes_accumulator))

    return Assessment(
        network_trust=corroborated.network_trust,
        campaign_risk=campaign_risk,
        contribution_quality_evidence=quality_evidence.value,
        triage=outcome,
        reasons=sorted_reasons,
        sources=sorted_sources,
        notes=sorted_notes,
    )


__all__ = [
    "Assessment",
    "assess",
]
