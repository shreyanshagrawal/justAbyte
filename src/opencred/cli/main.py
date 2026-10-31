"""OpenCred Command-Line Interface (Typer).

Interface layer providing user commands for trust evaluation, manifest validation,
pull request assessment, and scenario simulation.

Architecture Boundary (AGENTS.md):
- CLI is an interface layer. It depends on core domain logic.
- Core domain logic NEVER imports from cli.
- CLI handles user input, file loading, and formatting.
- Deterministic output: canonical JSON with sorted keys and trailing newline.
"""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from opencred.core.aggregate import aggregate_external
from opencred.core.assessment import Assessment, assess
from opencred.core.corroboration import LocalEvidence, apply_corroboration
from opencred.core.graph import TrustGraph
from opencred.core.manifests import parse_manifest
from opencred.core.models import (
    AssertionKind,
    ContributionEvent,
    PullRequestRecord,
    RepoId,
    to_canonical_json,
)
from opencred.core.propagation import best_path_per_origin
from opencred.core.quality import QualityConfig
from opencred.core.telemetry import (
    TelemetryLoadResult,
    load_telemetry,
)

app = typer.Typer(
    name="opencred",
    help="OpenCred: Git-native decentralized trust and campaign-detection system.",
    no_args_is_help=True,
)


def _load_manifest_file(path: Path, owner: RepoId) -> str:
    """Read a manifest file from disk, exiting with 1 on error."""
    if not path.is_file():
        typer.echo(f"Error: Manifest file not found at '{path}'", err=True)
        raise typer.Exit(code=1)
    try:
        return path.read_text(encoding="utf-8")
    except OSError as err:
        typer.echo(f"Error reading manifest file '{path}': {err}", err=True)
        raise typer.Exit(code=1) from err


def _validate_repo_id(val: str) -> RepoId:
    """Validate and construct a RepoId from a string, exiting with 1 on format error."""
    try:
        return RepoId(val)
    except (ValueError, TypeError) as err:
        typer.echo(f"Error: Invalid repository format '{val}': {err}", err=True)
        raise typer.Exit(code=1) from err


def _read_peer_manifests_dir(peers_dir: Path) -> dict[RepoId, str]:
    """Read peer manifests from a directory named <owner>__<repo>.td."""
    if not peers_dir.is_dir():
        typer.echo(f"Error: Peers directory not found at '{peers_dir}'", err=True)
        raise typer.Exit(code=1)

    peer_manifests: dict[RepoId, str] = {}
    for entry in sorted(peers_dir.iterdir()):
        if entry.is_file() and entry.name.endswith(".td"):
            stem = entry.name[:-3]
            if "__" in stem:
                owner_part, repo_part = stem.split("__", 1)
                try:
                    peer_repo = RepoId(f"{owner_part}/{repo_part}")
                    peer_manifests[peer_repo] = entry.read_text(encoding="utf-8")
                except (ValueError, OSError):
                    continue
    return peer_manifests


def _read_base_manifests_dir(base_dir: Path, evaluator: RepoId) -> dict[RepoId, str]:
    """Read base-branch manifests from a directory."""
    if not base_dir.is_dir():
        typer.echo(f"Error: Base manifests directory not found at '{base_dir}'", err=True)
        raise typer.Exit(code=1)

    manifests: dict[RepoId, str] = {}
    evaluator_stem = str(evaluator).replace("/", "__")

    for entry in sorted(base_dir.iterdir()):
        if entry.is_file() and entry.name.endswith(".td"):
            stem = entry.name[:-3]
            try:
                if stem == "evaluator" or stem == evaluator_stem:
                    manifests[evaluator] = entry.read_text(encoding="utf-8")
                elif "__" in stem:
                    owner_part, repo_part = stem.split("__", 1)
                    repo_id = RepoId(f"{owner_part}/{repo_part}")
                    manifests[repo_id] = entry.read_text(encoding="utf-8")
            except (ValueError, OSError):
                continue
    return manifests


def _read_telemetry_dir(
    telem_dir: Path,
    now: datetime,
) -> dict[RepoId, TelemetryLoadResult]:
    """Read repository telemetry files from a directory."""
    if not telem_dir.exists():
        return {}
    if not telem_dir.is_dir():
        typer.echo(f"Error: Telemetry path is not a directory '{telem_dir}'", err=True)
        raise typer.Exit(code=1)

    results: dict[RepoId, TelemetryLoadResult] = {}
    for entry in sorted(telem_dir.iterdir()):
        if entry.is_file() and entry.name.endswith(".json"):
            stem = entry.name[:-5]
            try:
                content = entry.read_text(encoding="utf-8")
                load_res = load_telemetry(content, now=now)
                if load_res.repository:
                    results[load_res.repository] = load_res
                elif "__" in stem:
                    owner_part, repo_part = stem.split("__", 1)
                    repo_id = RepoId(f"{owner_part}/{repo_part}")
                    results[repo_id] = load_res
            except (ValueError, OSError):
                continue
    return results


@app.command()
def manifest(
    path: Annotated[
        Path,
        typer.Argument(help="Path to the manifest file (.td)."),
    ],
    owner: Annotated[
        str,
        typer.Option(
            "--owner",
            help="Repository identity that owns this manifest in 'owner/repo' format.",
        ),
    ],
    format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: 'json' (canonical JSON) or 'text' (human-readable summary).",
        ),
    ] = "json",
) -> None:
    """Parse a trust manifest file and print assertions, trust edges, and errors."""
    owner_repo = _validate_repo_id(owner)
    text = _load_manifest_file(path, owner_repo)
    result = parse_manifest(text, owner=owner_repo)

    if format.lower() == "text":
        typer.echo(f"Manifest owner: {owner_repo}")
        typer.echo(f"Trust edges ({len(result.trust_edges)}):")
        for edge in result.trust_edges:
            typer.echo(f"  - target: {edge.target} (weight: {edge.weight:.2f})")
        typer.echo(f"Assertions ({len(result.assertions)}):")
        for a in result.assertions:
            typer.echo(f"  - {a.subject} ({a.kind.value}, strength: {a.strength:.2f})")
        if result.errors:
            typer.echo(f"Errors ({len(result.errors)}):")
            for line_no, msg in result.errors:
                typer.echo(f"  - Line {line_no}: {msg}")
        if result.warnings:
            typer.echo(f"Warnings ({len(result.warnings)}):")
            for line_no, msg in result.warnings:
                typer.echo(f"  - Line {line_no}: {msg}")
    else:
        typer.echo(to_canonical_json(result))


@app.command()
def trust(
    repo_manifest: Annotated[
        Path,
        typer.Option(
            "--repo-manifest",
            help="Path to the evaluator repository's manifest file.",
        ),
    ],
    peers_dir: Annotated[
        Path,
        typer.Option(
            "--peers-dir",
            help="Directory containing peer manifest files named <owner>__<repo>.td.",
        ),
    ],
    evaluator: Annotated[
        str,
        typer.Option(
            "--evaluator",
            help="Evaluator repository in 'owner/repo' format.",
        ),
    ],
    contributor: Annotated[
        str,
        typer.Option(
            "--contributor",
            help="Contributor username to evaluate.",
        ),
    ],
    format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: 'json' (canonical JSON) or 'text' (human-readable summary).",
        ),
    ] = "json",
) -> None:
    """Evaluate network trust for a contributor from peer repository manifests."""
    evaluator_repo = _validate_repo_id(evaluator)
    eval_text = _load_manifest_file(repo_manifest, evaluator_repo)
    eval_parse = parse_manifest(eval_text, owner=evaluator_repo)

    graph = TrustGraph()
    for edge in eval_parse.trust_edges:
        graph.add_edge(edge)

    direct_peers = sorted({edge.target for edge in eval_parse.trust_edges})
    peer_manifests = _read_peer_manifests_dir(peers_dir)

    assertions_by_origin: dict[RepoId, list] = {  # type: ignore[type-arg]
        evaluator_repo: list(eval_parse.assertions),
    }

    for peer in direct_peers:
        if peer in peer_manifests:
            peer_parse = parse_manifest(peer_manifests[peer], owner=peer)
            for edge in peer_parse.trust_edges:
                graph.add_edge(edge)
            assertions_by_origin[peer] = list(peer_parse.assertions)

    best_paths = best_path_per_origin(graph, evaluator=evaluator_repo, max_hops=2)
    for origin in sorted(best_paths.keys()):
        if origin not in assertions_by_origin and origin in peer_manifests:
            origin_parse = parse_manifest(peer_manifests[origin], owner=origin)
            assertions_by_origin[origin] = list(origin_parse.assertions)

    norm_contrib = contributor.strip().lstrip("@").lower()
    eval_subject_assertions = [a for a in eval_parse.assertions if a.subject == norm_contrib]
    local_evidence = LocalEvidence(
        has_denouncement=any(a.kind == AssertionKind.DENOUNCE for a in eval_subject_assertions),
        has_vouch=any(a.kind == AssertionKind.VOUCH for a in eval_subject_assertions),
    )

    external = aggregate_external(
        subject=norm_contrib,
        evaluator=evaluator_repo,
        graph=graph,
        assertions_by_origin=assertions_by_origin,
        max_hops=2,
    )

    corroborated = apply_corroboration(local_evidence, external)

    sources_set: set[str] = set()
    if local_evidence.has_vouch or local_evidence.has_denouncement:
        sources_set.add(f"{evaluator_repo} (0 hops)")

    for origin in external.contributing_origins:
        if origin in best_paths:
            hops = len(best_paths[origin].path)
            hop_str = f"{hops} hop" if hops == 1 else f"{hops} hops"
            sources_set.add(f"{origin} ({hop_str})")
        else:
            sources_set.add(f"{origin} (external)")

    output_data = {
        "network_trust": corroborated.network_trust,
        "notes": sorted(set(corroborated.notes)),
        "sources": sorted(sources_set),
    }

    if format.lower() == "text":
        typer.echo(f"Evaluator: {evaluator_repo}")
        typer.echo(f"Contributor: {norm_contrib}")
        typer.echo(f"Network Trust: {corroborated.network_trust:.2f}")
        typer.echo(f"Sources ({len(sources_set)}):")
        for s in sorted(sources_set):
            typer.echo(f"  - {s}")
        if corroborated.notes:
            typer.echo(f"Notes ({len(corroborated.notes)}):")
            for n in sorted(set(corroborated.notes)):
                typer.echo(f"  - {n}")
    else:
        typer.echo(to_canonical_json(output_data))


@app.command(name="assess")
def assess_cmd(
    pr: Annotated[
        Path,
        typer.Option(
            "--pr",
            help="Path to JSON file containing PullRequestRecord.",
        ),
    ],
    base_manifests: Annotated[
        Path,
        typer.Option(
            "--base-manifests",
            help="Directory containing repository base manifests named <owner>__<repo>.td.",
        ),
    ],
    telemetry_dir: Annotated[
        Path,
        typer.Option(
            "--telemetry-dir",
            help="Directory containing repository telemetry files named <owner>__<repo>.json.",
        ),
    ],
    evaluator: Annotated[
        str,
        typer.Option(
            "--evaluator",
            help="Evaluator repository in 'owner/repo' format.",
        ),
    ],
    history: Annotated[
        Path,
        typer.Option(
            "--history",
            help="Path to JSON file containing contributor historical events list.",
        ),
    ],
    now: Annotated[
        str | None,
        typer.Option(
            "--now",
            help=(
                "Evaluation timestamp (ISO-8601). The CLI never reads the system clock except "
                "through this flag. When --now is omitted, the CLI uses the current time "
                "for telemetry freshness only."
            ),
        ),
    ] = None,
    format: Annotated[
        str,
        typer.Option(
            "--format",
            help="Output format: 'json' (default canonical JSON) or 'text'.",
        ),
    ] = "json",
) -> None:
    """Assess a pull request through the full OpenCred advisory evaluation pipeline."""
    evaluator_repo = _validate_repo_id(evaluator)

    if not pr.is_file():
        typer.echo(f"Error: PR record file not found at '{pr}'", err=True)
        raise typer.Exit(code=1)

    if not history.is_file():
        typer.echo(f"Error: History file not found at '{history}'", err=True)
        raise typer.Exit(code=1)

    try:
        pr_data = json.loads(pr.read_text(encoding="utf-8"))
        pr_record = PullRequestRecord.model_validate(pr_data)
    except Exception as err:
        typer.echo(f"Error parsing PullRequestRecord from '{pr}': {err}", err=True)
        raise typer.Exit(code=1) from err

    try:
        hist_data = json.loads(history.read_text(encoding="utf-8"))
        if not isinstance(hist_data, list):
            raise ValueError("History JSON must be a list of contribution events")
        hist_events = [ContributionEvent.model_validate(e) for e in hist_data]
    except Exception as err:
        typer.echo(f"Error parsing history events from '{history}': {err}", err=True)
        raise typer.Exit(code=1) from err

    # Telemetry timestamp: explicit --now or fallback to current time for freshness only
    if now:
        try:
            now_dt = datetime.fromisoformat(now)
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=UTC)
        except ValueError as err:
            typer.echo(f"Error: Invalid ISO-8601 timestamp for --now '{now}': {err}", err=True)
            raise typer.Exit(code=1) from err
    else:
        now_dt = datetime.now(UTC)

    all_manifests = _read_base_manifests_dir(base_manifests, evaluator_repo)
    base_dict = {evaluator_repo: all_manifests.get(evaluator_repo, "")}
    peer_dict = {k: v for k, v in all_manifests.items() if k != evaluator_repo}

    telemetry_data = _read_telemetry_dir(telemetry_dir, now=now_dt)

    result: Assessment = assess(
        pr=pr_record,
        base_manifests=base_dict,
        evaluator=evaluator_repo,
        peer_manifests=peer_dict,
        telemetry=telemetry_data,
        history=hist_events,
        config=QualityConfig(),
    )

    if format.lower() == "text":
        typer.echo(f"Repository: {evaluator_repo}")
        typer.echo(f"Pull Request: #{pr_record.number} by {pr_record.author}")
        typer.echo(f"Triage Outcome: {result.triage.value}")
        typer.echo(f"Network Trust: {result.network_trust:.2f}")
        typer.echo(f"Campaign Risk: {result.campaign_risk:.2f}")
        typer.echo(f"Quality Evidence: {result.contribution_quality_evidence:.2f}")
        typer.echo(f"Reasons ({len(result.reasons)}):")
        for r in result.reasons:
            typer.echo(f"  - {r}")
        typer.echo(f"Sources ({len(result.sources)}):")
        for s in result.sources:
            typer.echo(f"  - {s}")
        if result.notes:
            typer.echo(f"Notes ({len(result.notes)}):")
            for n in result.notes:
                typer.echo(f"  - {n}")
    else:
        typer.echo(to_canonical_json(result))


@app.command()
def simulate(
    scenario: Annotated[
        Path,
        typer.Option(
            "--scenario",
            help="Path to scenario JSON file.",
        ),
    ],
) -> None:
    """Run an ecosystem simulation scenario (Placeholder for Phase 14)."""
    typer.echo("not implemented")
    raise typer.Exit(code=2)


if __name__ == "__main__":
    app()
