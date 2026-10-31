"""Simulation evaluator and gate verification engine for OpenCred.

Evaluates synthetic ecosystem scenarios across three operational modes:
1. LOCAL_ONLY: Each repository assesses PRs using only its own base manifest
   and contributor history. No peer edges, no telemetry.
2. PROPAGATION: Incorporates 2-hop web-of-trust propagation, cluster influence capping,
   and single-origin corroboration bounding. Telemetry is absent.
3. PROPAGATION_PLUS_CAMPAIGNS: Full OpenCred pipeline adding peer telemetry ingestion,
   MinHash diff fingerprinting, and coordinated campaign detection.

Propagation Round Model:
    Simulates discrete synchronization cycles across the repository web of trust:
    - Round 0: Origin publishes an assertion (vouch or denouncement) in its base manifest.
    - Round 1: Evaluators directly declaring a trust directive (# @trust-repo origin)
      ingest origin's manifest during peer sync (distance = 1 hop).
    - Round 2: Evaluators with a 2-hop path via an intermediary peer ingest the peer's
      manifest and discover origin's assertion (distance = 2 hops).
    Per AGENTS.md rule 3, maximum propagation depth is strictly 2 hops. Propagation
    halts after round 2; unreachable or disjoint repositories remain at 0 rounds.

Gates:
    Evaluator threshold assertions loaded from an external JSON file (e.g. examples/gates.json).
    Exits with code 1 if any configured gate check fails.
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import Field

from opencred.core.assessment import assess
from opencred.core.config import CAMPAIGN_ALERT_THRESHOLD
from opencred.core.fingerprint import exact_fingerprint, normalize_diff, path_set, shingles
from opencred.core.graph import TrustGraph
from opencred.core.manifests import parse_manifest
from opencred.core.minhash import minhash_signature
from opencred.core.models import OpenCredModel, RepoId, to_canonical_json
from opencred.core.propagation import best_path_per_origin
from opencred.core.telemetry import TelemetryEntry, TelemetryLoadResult, TelemetryStatus
from opencred.core.triage import TriageOutcome
from opencred.simulation.generate import PRLabel, Scenario, generate_scenario


class EvaluationMode(StrEnum):
    """Operational modes for OpenCred evaluation pipeline."""

    LOCAL_ONLY = "LOCAL_ONLY"
    PROPAGATION = "PROPAGATION"
    PROPAGATION_PLUS_CAMPAIGNS = "PROPAGATION_PLUS_CAMPAIGNS"


class ModeMetrics(OpenCredModel):
    """Evaluation metrics computed against ground truth for an operational mode."""

    campaigns_detected: int = Field(
        ge=0,
        description="Count of distinct coordinated campaigns correctly flagged for investigation",
    )
    campaigns_missed: int = Field(
        ge=0,
        description="Count of coordinated campaigns not flagged by any pull request",
    )
    legit_prs_flagged_for_investigation: int = Field(
        ge=0,
        description="False positive count: legitimate PRs flagged with INVESTIGATE_CAMPAIGN",
    )
    trap_prs_flagged: int = Field(
        ge=0,
        description="False positive count: trap PRs (dependency bumps/typos) flagged as campaigns",
    )
    newcomer_fairness_violations: int = Field(
        ge=0,
        description="Count of newcomers with negative trust or unwarranted scrutiny",
    )
    ring_suppression: float = Field(
        ge=-1.0,
        le=1.0,
        description="Network trust score of honest targeted contributor under ring attack",
    )
    propagation_rounds: int = Field(
        ge=0,
        description="Simulated discrete sync rounds until ring denouncement reaches target repo",
    )


class EvaluationReport(OpenCredModel):
    """Comprehensive evaluation report across all three modes with gate results."""

    seed: int
    num_repos: int
    total_prs: int
    modes: dict[str, ModeMetrics]
    gates: dict[str, Any] | None = None
    gate_failures: list[str] = Field(default_factory=list)
    gates_passed: bool = True


def compute_propagation_rounds(
    evaluator: RepoId,
    target_origin: RepoId,
    manifests: dict[str, str],
) -> int:
    """Compute discrete sync rounds from target_origin to evaluator (max 2 hops).

    Uses BFS over declared # @trust-repo edges starting from the evaluator.
    Returns 1 if directly trusted, 2 if reachable in 2 hops, or 0 if unreachable.
    """
    eval_text = manifests.get(str(evaluator), "")
    eval_parse = parse_manifest(eval_text, owner=evaluator)
    direct_peers = {edge.target for edge in eval_parse.trust_edges}

    if target_origin in direct_peers:
        return 1

    graph = TrustGraph()
    for edge in eval_parse.trust_edges:
        graph.add_edge(edge)

    for peer in direct_peers:
        peer_text = manifests.get(str(peer), "")
        peer_parse = parse_manifest(peer_text, owner=peer)
        for edge in peer_parse.trust_edges:
            graph.add_edge(edge)

    best_paths = best_path_per_origin(graph, evaluator=evaluator, max_hops=2)
    if target_origin in best_paths:
        return len(best_paths[target_origin].path)

    return 0


def build_scenario_telemetry(
    scenario: Scenario,
    evaluation_time: datetime,
) -> dict[RepoId, TelemetryLoadResult]:
    """Construct deterministic fresh TelemetryLoadResult objects for all repositories."""
    telemetry_by_repo: dict[RepoId, TelemetryLoadResult] = {}

    for repo in scenario.repositories:
        repo_prs = [p for p in scenario.prs if p.repo == repo]
        entries: list[TelemetryEntry] = []
        for p in repo_prs:
            norm_diff = normalize_diff(p.normalized_diff)
            diff_fp = exact_fingerprint(p.normalized_diff)
            diff_tokens = frozenset(norm_diff.split())
            diff_sig = list(minhash_signature(diff_tokens, num_perm=128))
            desc_text = f"{p.title}\n{p.body}".strip()
            desc_shing = shingles(desc_text, k=3)
            desc_sig = list(minhash_signature(desc_shing, num_perm=128))
            paths = sorted(path_set(p.changed_files))
            entries.append(
                TelemetryEntry(
                    pr_number=p.number,
                    author=p.author,
                    opened_at=p.opened_at,
                    exact_fingerprint=diff_fp,
                    path_set=paths,
                    minhash_signature=diff_sig,
                    description_similarity_signature=desc_sig,
                )
            )
        telemetry_by_repo[repo] = TelemetryLoadResult(
            status=TelemetryStatus.FRESH,
            repository=repo,
            schema_version=1,
            generated_at=evaluation_time,
            expires_at=evaluation_time + timedelta(days=7),
            entries=entries,
        )

    return telemetry_by_repo


def evaluate_mode(
    mode: EvaluationMode,
    scenario: Scenario,
    telemetry_by_repo: dict[RepoId, TelemetryLoadResult],
    target_evaluator: RepoId,
    ring_origin: RepoId,
) -> ModeMetrics:
    """Evaluate all pull requests in the scenario under a specific operational mode."""
    peer_manifests = (
        {}
        if mode == EvaluationMode.LOCAL_ONLY
        else {RepoId(r): text for r, text in scenario.manifests.items()}
    )
    active_telemetry = (
        telemetry_by_repo if mode == EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS else {}
    )

    legit_flagged = 0
    trap_flagged = 0
    newcomer_violations = 0

    campaign_detected_set: set[str] = set()
    ring_suppression_score: float = 0.0

    for pr in scenario.prs:
        key = f"{pr.repo}#{pr.number}"
        gt_pr_label = scenario.ground_truth.prs[key]
        gt_author_label = scenario.ground_truth.contributors[pr.author]

        evaluator = pr.repo
        base_manifests = {evaluator: scenario.manifests[str(evaluator)]}
        history = scenario.contributors.get(pr.author, [])

        res = assess(
            pr=pr,
            base_manifests=base_manifests,
            evaluator=evaluator,
            peer_manifests=peer_manifests,
            telemetry=active_telemetry,
            history=history,
        )

        # 1. False positive tracking
        if gt_pr_label == PRLabel.LEGIT.value:
            if res.triage == TriageOutcome.INVESTIGATE_CAMPAIGN:
                legit_flagged += 1
        elif gt_pr_label == PRLabel.TRAP.value:
            if res.triage == TriageOutcome.INVESTIGATE_CAMPAIGN:
                trap_flagged += 1

        # 2. Newcomer fairness tracking (network_trust < 0 or unwarranted additional scrutiny)
        if gt_author_label == "NEWCOMER":
            if res.network_trust < 0.0:
                newcomer_violations += 1
            elif (
                res.triage == TriageOutcome.ADDITIONAL_SCRUTINY
                and res.campaign_risk < CAMPAIGN_ALERT_THRESHOLD
            ):
                newcomer_violations += 1

        # 3. Campaign detection tracking
        if res.triage == TriageOutcome.INVESTIGATE_CAMPAIGN:
            for c in scenario.campaigns:
                if key in c.pr_keys:
                    campaign_detected_set.add(c.campaign_id)

        # 4. Ring suppression tracking on honest target PR #1000 evaluated by target_evaluator
        if pr.number == 1000 and pr.author == "honest_target_0":
            ring_suppression_score = round(res.network_trust, 4)

    campaigns_detected = len(campaign_detected_set)
    campaigns_missed = len(scenario.campaigns) - campaigns_detected

    # 5. Propagation rounds calculation
    if mode == EvaluationMode.LOCAL_ONLY:
        propagation_rounds = 0
    else:
        propagation_rounds = compute_propagation_rounds(
            evaluator=target_evaluator,
            target_origin=ring_origin,
            manifests=scenario.manifests,
        )

    return ModeMetrics(
        campaigns_detected=campaigns_detected,
        campaigns_missed=campaigns_missed,
        legit_prs_flagged_for_investigation=legit_flagged,
        trap_prs_flagged=trap_flagged,
        newcomer_fairness_violations=newcomer_violations,
        ring_suppression=ring_suppression_score,
        propagation_rounds=propagation_rounds,
    )


def check_gates(
    report: EvaluationReport,
    gates: dict[str, Any],
) -> tuple[bool, list[str]]:
    """Validate evaluation report against threshold gates configured in gates.json."""
    failures: list[str] = []

    # newcomer_fairness_violations_max (checked across all modes)
    if "newcomer_fairness_violations_max" in gates:
        max_violations = int(gates["newcomer_fairness_violations_max"])
        for mode_name, metrics in report.modes.items():
            if metrics.newcomer_fairness_violations > max_violations:
                failures.append(
                    f"[{mode_name}] newcomer_fairness_violations "
                    f"({metrics.newcomer_fairness_violations}) "
                    f"exceeds maximum allowed threshold ({max_violations})"
                )

    # ring_suppression_floor (checked across all modes)
    if "ring_suppression_floor" in gates:
        floor_val = float(gates["ring_suppression_floor"])
        for mode_name, metrics in report.modes.items():
            if metrics.ring_suppression < floor_val:
                failures.append(
                    f"[{mode_name}] ring_suppression ({metrics.ring_suppression}) "
                    f"below configured floor ({floor_val})"
                )

    # legit_prs_flagged_for_investigation_max (checked across all modes)
    if "legit_prs_flagged_for_investigation_max" in gates:
        max_fp = int(gates["legit_prs_flagged_for_investigation_max"])
        for mode_name, metrics in report.modes.items():
            if metrics.legit_prs_flagged_for_investigation > max_fp:
                failures.append(
                    f"[{mode_name}] legit_prs_flagged_for_investigation "
                    f"({metrics.legit_prs_flagged_for_investigation}) exceeds maximum ({max_fp})"
                )

    # trap_prs_flagged_max (checked across all modes)
    if "trap_prs_flagged_max" in gates:
        max_trap_fp = int(gates["trap_prs_flagged_max"])
        for mode_name, metrics in report.modes.items():
            if metrics.trap_prs_flagged > max_trap_fp:
                failures.append(
                    f"[{mode_name}] trap_prs_flagged ({metrics.trap_prs_flagged}) "
                    f"exceeds maximum ({max_trap_fp})"
                )

    # campaigns_missed_max (checked specifically on full pipeline PROPAGATION_PLUS_CAMPAIGNS)
    if "campaigns_missed_max" in gates:
        max_missed = int(gates["campaigns_missed_max"])
        full_mode = report.modes.get(EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS.value)
        if full_mode and full_mode.campaigns_missed > max_missed:
            failures.append(
                f"[{EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS.value}] campaigns_missed "
                f"({full_mode.campaigns_missed}) exceeds maximum allowed threshold ({max_missed})"
            )

    return (len(failures) == 0, failures)


def evaluate_scenario(
    scenario: Scenario,
    seed: int,
    gates: dict[str, Any] | None = None,
) -> EvaluationReport:
    """Run full evaluation across all three operational modes on a synthetic scenario."""
    eval_time = datetime(2026, 11, 1, 0, 0, 0, tzinfo=UTC)
    telemetry_by_repo = build_scenario_telemetry(scenario, eval_time)

    # Evaluator and ring origin for ring suppression and propagation rounds tracking
    target_evaluator = scenario.repositories[8]  # honest_repos[0]
    ring_origin = scenario.denunciation_rings[0].repositories[0]  # Ring 0 origin

    modes_results: dict[str, ModeMetrics] = {}
    for mode in [
        EvaluationMode.LOCAL_ONLY,
        EvaluationMode.PROPAGATION,
        EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS,
    ]:
        modes_results[mode.value] = evaluate_mode(
            mode=mode,
            scenario=scenario,
            telemetry_by_repo=telemetry_by_repo,
            target_evaluator=target_evaluator,
            ring_origin=ring_origin,
        )

    report = EvaluationReport(
        seed=seed,
        num_repos=len(scenario.repositories),
        total_prs=len(scenario.prs),
        modes=modes_results,
        gates=gates,
    )

    if gates:
        passed, failures = check_gates(report, gates)
        report = report.model_copy(update={"gates_passed": passed, "gate_failures": failures})

    return report


def format_markdown_table(report: EvaluationReport) -> str:
    """Format evaluation report metrics as a GitHub Flavored Markdown table."""
    headers = [
        "Mode",
        "Campaigns Detected",
        "Campaigns Missed",
        "Legit Flagged",
        "Trap Flagged",
        "Newcomer Violations",
        "Ring Suppression",
        "Propagation Rounds",
    ]
    lines: list[str] = [
        f"### OpenCred Simulation Evaluation Report (Seed {report.seed})",
        "",
        f"- Repositories: {report.num_repos} | Total PRs: {report.total_prs}",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for mode_name in [
        EvaluationMode.LOCAL_ONLY.value,
        EvaluationMode.PROPAGATION.value,
        EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS.value,
    ]:
        m = report.modes[mode_name]
        row = [
            f"`{mode_name}`",
            str(m.campaigns_detected),
            str(m.campaigns_missed),
            str(m.legit_prs_flagged_for_investigation),
            str(m.trap_prs_flagged),
            str(m.newcomer_fairness_violations),
            f"{m.ring_suppression:+.2f}",
            str(m.propagation_rounds),
        ]
        lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    if report.gates:
        status = "PASSED" if report.gates_passed else "FAILED"
        lines.append(f"**Gate Status:** `{status}`")
        if report.gate_failures:
            lines.append("")
            lines.append("**Gate Failures:**")
            for f in report.gate_failures:
                lines.append(f"- ❌ {f}")
    lines.append("")
    return "\n".join(lines)


def run_evaluation(
    seeds: list[int],
    gates_path: Path | None = None,
    output_format: str = "all",
) -> tuple[int, list[EvaluationReport]]:
    """Execute evaluation across a list of seeds and print formatted outputs.

    Returns:
        tuple[int, list[EvaluationReport]]: Exit code (0 for pass, 1 for gate failure)
        and list of generated EvaluationReports.
    """
    gates: dict[str, Any] | None = None
    if gates_path and gates_path.exists():
        gates = json.loads(gates_path.read_text(encoding="utf-8"))

    reports: list[EvaluationReport] = []
    overall_exit_code = 0

    for seed in seeds:
        scenario = generate_scenario(seed=seed)
        report = evaluate_scenario(scenario=scenario, seed=seed, gates=gates)
        reports.append(report)

        if not report.gates_passed:
            overall_exit_code = 1

        if output_format in ("markdown", "all"):
            md_table = format_markdown_table(report)
            sys.stdout.write(md_table + "\n")

        if output_format in ("json", "all"):
            canonical_json = to_canonical_json(report) + "\n"
            sys.stdout.write("```json\n" + canonical_json + "```\n\n")

    return (overall_exit_code, reports)


def main() -> int:
    """CLI entry point for simulation evaluation runner."""
    parser = argparse.ArgumentParser(
        description="OpenCred Simulation Evaluator and Gate Verification Runner",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Single seed for evaluation.",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=None,
        help="Space-separated list of seeds (e.g. --seeds 1 2 3).",
    )
    parser.add_argument(
        "--gates",
        type=str,
        default="examples/gates.json",
        help="Path to gates configuration file (default: examples/gates.json).",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["all", "markdown", "json"],
        default="all",
        help="Output format: 'all' (markdown + json), 'markdown', or 'json'.",
    )

    args = parser.parse_args()

    # Determine seed list
    if args.seeds:
        seed_list = args.seeds
    elif args.seed is not None:
        seed_list = [args.seed]
    else:
        seed_list = [42]

    gates_file = Path(args.gates) if args.gates else None
    exit_code, _ = run_evaluation(
        seeds=seed_list,
        gates_path=gates_file,
        output_format=args.format,
    )
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
