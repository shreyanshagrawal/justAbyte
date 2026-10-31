#!/usr/bin/env python3
"""OpenCred Simulation CLI Script.

Generates reproducible ecosystem simulation scenarios with ground-truth labels.

Usage:
    python scripts/simulate.py --seed 42 --out examples/scenario-42.json
"""

import argparse
import sys
from pathlib import Path

from opencred.core.models import to_canonical_json
from opencred.simulation.generate import generate_scenario


def main() -> int:
    """Parse CLI arguments, generate scenario, and write canonical JSON output."""
    parser = argparse.ArgumentParser(
        description="Generate deterministic OpenCred simulation scenarios with ground truth.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for reproducible scenario generation (default: 42).",
    )
    parser.add_argument(
        "--num-repos",
        type=int,
        default=30,
        help="Total number of simulated repositories (default: 30, minimum: 12).",
    )
    parser.add_argument(
        "--out",
        type=str,
        default="examples/scenario-42.json",
        help="Destination path for output scenario JSON file (default: examples/scenario-42.json).",
    )

    args = parser.parse_args()

    try:
        scenario = generate_scenario(seed=args.seed, num_repos=args.num_repos)
    except ValueError as err:
        sys.stderr.write(f"Error: {err}\n")
        return 1

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    canonical_json_output = to_canonical_json(scenario) + "\n"
    out_path.write_text(canonical_json_output, encoding="utf-8")

    summary = (
        f"Generated simulation scenario (seed={args.seed}, "
        f"repos={len(scenario.repositories)}, PRs={len(scenario.prs)}, "
        f"campaigns={len(scenario.campaigns)}, rings={len(scenario.denunciation_rings)}) "
        f"-> {out_path}\n"
    )
    sys.stdout.write(summary)
    return 0


if __name__ == "__main__":
    sys.exit(main())
