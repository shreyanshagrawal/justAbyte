# OpenCred Simulation Ecosystem

This directory contains the scenario generator and simulation models for testing OpenCred's trust propagation, campaign detection, and triage pipelines under synthetic open-source ecosystem conditions.

## Architectural Boundary

Per OpenCred guidelines (`AGENTS.md`), simulation code is strictly kept **outside** `src/opencred/core/`. Core domain logic never imports from simulation.

## How to Regenerate a Scenario

Scenarios are generated deterministically using a pseudorandom seed. To generate a scenario dataset, run:

```bash
python scripts/simulate.py --seed 42 --out examples/scenario-42.json
```

### CLI Options

- `--seed`: Integer seed for deterministic generation (default: `42`). Randomness is derived strictly from `random.Random(seed)`.
- `--num-repos`: Total number of simulated repositories (default: `30`, minimum: `12`).
- `--out`: Path to write the generated scenario JSON (default: `examples/scenario-42.json`).

## Scenario Contents & Ground Truth

Each generated scenario contains:
- `repositories`: List of repository IDs in `owner/repo` format.
- `manifests`: Trustdown manifests per repository with `# @trust-repo` peer edges and contributor vouches/denouncements.
- `contributors`: Contributor histories (`established` with merged contributions, `newcomers` with no merged history, and `honest_targeted` contributors).
- `prs`: Collection of pull request records under assessment.
- `campaigns`: 3 coordinated campaign attacks, each involving 6 new accounts submitting near-identical PRs across 4 or more repositories within a 6-hour window.
- `denunciation_rings`: 2 rings of colluding repositories that mutually trust each other and falsely denounce an honest contributor.
- `false_positive_traps`: Benign pull requests that look similar across repositories (e.g. automated dependency version bumps, typo fixes).
- `ground_truth`: Ground truth labels for every PR (`LEGIT`, `CAMPAIGN`, `TRAP`) and contributor (`ESTABLISHED`, `NEWCOMER`, `HONEST_TARGETED`).
