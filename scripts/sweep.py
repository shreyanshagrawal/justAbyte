#!/usr/bin/env python3
"""OpenCred Parameter Sensitivity Sweep Script.

Sweeps CAMPAIGN_SIMILARITY_THRESHOLD over [0.6, 0.7, 0.8] and
CAMPAIGN_MIN_AUTHORS over [2, 3, 4] using the evaluation runner.

Outputs a markdown table and canonical JSON of evaluation metrics across
all 9 parameter combinations without altering the default constants in config.py.

Usage:
    python scripts/sweep.py --seed 42
    python scripts/sweep.py --seeds 1 2 3
"""

import argparse
import contextlib
import sys
from collections.abc import Generator
from pathlib import Path

import opencred.core.campaign as campaign_module
from opencred.core.models import OpenCredModel, to_canonical_json
from opencred.simulation.evaluate import EvaluationMode, evaluate_scenario
from opencred.simulation.generate import generate_scenario

SIMILARITY_THRESHOLDS: list[float] = [0.6, 0.7, 0.8]
MIN_AUTHORS_VALUES: list[int] = [2, 3, 4]


class SweepRow(OpenCredModel):
    """Metrics recorded for a specific parameter combination in the sweep."""

    similarity_threshold: float
    min_authors: int
    campaigns_detected: int
    campaigns_missed: int
    legit_prs_flagged_for_investigation: int
    trap_prs_flagged: int
    newcomer_fairness_violations: int
    ring_suppression: float
    propagation_rounds: int


class SweepReport(OpenCredModel):
    """Full sensitivity sweep report across parameter combinations."""

    seed: int
    rows: list[SweepRow]


@contextlib.contextmanager
def override_campaign_params(
    similarity_threshold: float,
    min_authors: int,
) -> Generator[None, None, None]:
    """Temporarily override campaign thresholds in campaign module without changing config.py."""
    orig_sim = campaign_module.CAMPAIGN_SIMILARITY_THRESHOLD
    orig_auth = campaign_module.CAMPAIGN_MIN_AUTHORS
    campaign_module.CAMPAIGN_SIMILARITY_THRESHOLD = similarity_threshold
    campaign_module.CAMPAIGN_MIN_AUTHORS = min_authors
    try:
        yield
    finally:
        campaign_module.CAMPAIGN_SIMILARITY_THRESHOLD = orig_sim
        campaign_module.CAMPAIGN_MIN_AUTHORS = orig_auth


def run_sweep_for_seed(seed: int) -> SweepReport:
    """Run parameter sweep across all 9 configurations for a given seed."""
    scenario = generate_scenario(seed=seed)
    rows: list[SweepRow] = []

    for sim in SIMILARITY_THRESHOLDS:
        for auth in MIN_AUTHORS_VALUES:
            with override_campaign_params(similarity_threshold=sim, min_authors=auth):
                report = evaluate_scenario(scenario=scenario, seed=seed)
                metrics = report.modes[EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS.value]
                rows.append(
                    SweepRow(
                        similarity_threshold=sim,
                        min_authors=auth,
                        campaigns_detected=metrics.campaigns_detected,
                        campaigns_missed=metrics.campaigns_missed,
                        legit_prs_flagged_for_investigation=metrics.legit_prs_flagged_for_investigation,
                        trap_prs_flagged=metrics.trap_prs_flagged,
                        newcomer_fairness_violations=metrics.newcomer_fairness_violations,
                        ring_suppression=metrics.ring_suppression,
                        propagation_rounds=metrics.propagation_rounds,
                    )
                )

    return SweepReport(seed=seed, rows=rows)


def format_sweep_markdown_table(report: SweepReport) -> str:
    """Format sweep report as a GitHub-flavored markdown table."""
    headers = [
        "Similarity Threshold",
        "Min Authors",
        "Campaigns Detected",
        "Campaigns Missed",
        "Legit Flagged",
        "Trap Flagged",
        "Newcomer Violations",
        "Ring Suppression",
        "Propagation Rounds",
    ]
    lines: list[str] = [
        f"### Campaign Detection Parameter Sensitivity Sweep (Seed {report.seed})",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]

    for row in report.rows:
        data_row = [
            f"`{row.similarity_threshold:.1f}`",
            str(row.min_authors),
            str(row.campaigns_detected),
            str(row.campaigns_missed),
            str(row.legit_prs_flagged_for_investigation),
            str(row.trap_prs_flagged),
            str(row.newcomer_fairness_violations),
            f"{row.ring_suppression:+.2f}",
            str(row.propagation_rounds),
        ]
        lines.append("| " + " | ".join(data_row) + " |")

    lines.append("")
    return "\n".join(lines)


def main() -> int:
    """CLI entry point for sensitivity sweep."""
    parser = argparse.ArgumentParser(
        description="Sweep campaign detection parameters and evaluate sensitivity tradeoffs.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Single seed for sweep evaluation (default: 42).",
    )
    parser.add_argument(
        "--seeds",
        type=int,
        nargs="+",
        default=None,
        help="Space-separated list of seeds (e.g. --seeds 1 2 3).",
    )
    parser.add_argument(
        "--format",
        type=str,
        choices=["all", "table", "json"],
        default="all",
        help="Output format: 'all' (markdown + json), 'table', or 'json'.",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional path to write output file.",
    )

    args = parser.parse_args()

    if args.seeds:
        seed_list = args.seeds
    elif args.seed is not None:
        seed_list = [args.seed]
    else:
        seed_list = [42]

    output_buffer: list[str] = []

    for seed in seed_list:
        report = run_sweep_for_seed(seed=seed)

        if args.format in ("table", "all"):
            table_md = format_sweep_markdown_table(report)
            output_buffer.append(table_md)

        if args.format in ("json", "all"):
            json_str = to_canonical_json(report) + "\n"
            output_buffer.append("```json\n" + json_str + "```\n")

    full_output = "\n".join(output_buffer)
    sys.stdout.write(full_output)

    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(full_output, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
