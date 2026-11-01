#!/usr/bin/env python3
"""Run OpenCred assess pipeline over a scenario file deterministically.

Extracts all pull requests, base manifests, peer manifests, telemetry,
and history from the scenario JSON, assesses each pull request, and
prints the byte-for-byte canonical JSON array of assessment results.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from opencred.core.assessment import assess
from opencred.core.models import RepoId, to_canonical_json
from opencred.simulation.evaluate import build_scenario_telemetry
from opencred.simulation.generate import Scenario


def assess_scenario(scenario: Scenario) -> list[dict[str, Any]]:
    """Run assess pipeline over all PRs in the scenario and return raw assessment dicts."""
    fixed_time = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    telemetry = build_scenario_telemetry(scenario, fixed_time)
    peer_manifests = {RepoId(r): text for r, text in scenario.manifests.items()}

    results: list[dict[str, Any]] = []
    # Sort PRs by repo and number to guarantee deterministic processing order
    sorted_prs = sorted(scenario.prs, key=lambda p: (str(p.repo), p.number))

    for pr in sorted_prs:
        res = assess(
            pr=pr,
            base_manifests={pr.repo: scenario.manifests[str(pr.repo)]},
            evaluator=pr.repo,
            peer_manifests=peer_manifests,
            telemetry=telemetry,
            history=scenario.contributors.get(pr.author, []),
        )
        results.append(
            {
                "pr_number": pr.number,
                "repo": str(pr.repo),
                "author": pr.author,
                "assessment": res.model_dump(),
            }
        )

    return results


def main() -> int:
    """CLI entry point to assess scenario and write formatted JSON."""
    parser = argparse.ArgumentParser(
        description="Run OpenCred assess pipeline over a scenario JSON file.",
    )
    parser.add_argument(
        "--scenario",
        type=Path,
        required=True,
        help="Path to scenario JSON file.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Optional output destination file. Defaults to stdout.",
    )

    args = parser.parse_args()

    if not args.scenario.is_file():
        sys.stderr.write(f"Error: Scenario file not found: {args.scenario}\n")
        return 1

    scenario = Scenario.model_validate_json(args.scenario.read_text(encoding="utf-8"))
    results = assess_scenario(scenario)
    canonical_output = to_canonical_json(results) + "\n"

    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(canonical_output, encoding="utf-8")
    else:
        sys.stdout.write(canonical_output)

    return 0


if __name__ == "__main__":
    sys.exit(main())
