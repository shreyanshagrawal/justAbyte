# OpenCred Simulation Ecosystem

This directory contains the scenario generator, simulation models, and evaluation engine for testing OpenCred's trust propagation, campaign detection, and triage pipelines under synthetic open-source ecosystem conditions.

## Architectural Boundary

Per OpenCred guidelines (`AGENTS.md`), simulation code is strictly kept **outside** `src/opencred/core/`. Core domain logic never imports from simulation.

## How to Regenerate a Scenario

Scenarios are generated deterministically using a pseudorandom seed. To generate a scenario dataset, run:

```bash
python scripts/simulate.py --seed 42 --out examples/scenario-42.json
```

### Generator CLI Options

- `--seed`: Integer seed for deterministic generation (default: `42`). Randomness is derived strictly from `random.Random(seed)`.
- `--num-repos`: Total number of simulated repositories (default: `30`, minimum: `12`).
- `--out`: Path to write the generated scenario JSON (default: `examples/scenario-42.json`).

## How to Run Simulation Evaluation

The evaluator runs the scenario across three operational modes, calculates metrics against ground truth, and checks thresholds in `examples/gates.json`:

```bash
python scripts/evaluate.py --seeds 1 2 3 --gates examples/gates.json
```

### Three Operational Modes

1. **`LOCAL_ONLY`**: Each repository assesses PRs using only its own base manifest and local contributor history. No peer edges, no telemetry.
2. **`PROPAGATION`**: Adds two-hop web-of-trust propagation, cluster influence capping, and single-origin corroboration bounding. Telemetry is absent.
3. **`PROPAGATION_PLUS_CAMPAIGNS`**: Full OpenCred pipeline adding peer telemetry ingestion, MinHash diff fingerprinting, and coordinated campaign detection.

### Propagation Round Model

Simulates discrete synchronization cycles across the repository web of trust:
- **Round 0**: Origin publishes an assertion (vouch or denouncement) in its base manifest.
- **Round 1**: Evaluators directly declaring a trust directive (`# @trust-repo origin`) ingest origin's manifest during peer sync (distance = 1 hop).
- **Round 2**: Evaluators with a 2-hop path via an intermediary peer ingest the peer's manifest and discover origin's assertion (distance = 2 hops).

Per AGENTS.md rule 3, maximum propagation depth is strictly 2 hops. Propagation halts after round 2; unreachable or disjoint repositories remain at 0 rounds.

### Metrics & Gates

Metrics computed against ground truth:
- `campaigns_detected`, `campaigns_missed`: Coordinated multi-account attacks flagged for investigation.
- `legit_prs_flagged_for_investigation`: False positives on legitimate PRs.
- `trap_prs_flagged`: False positives on benign mass PRs (e.g. dependency bumps, typo sweeps).
- `newcomer_fairness_violations`: Newcomer contributors with negative trust or unwarranted scrutiny (must be 0).
- `ring_suppression`: Honest targeted contributor's network trust under colluding ring attack (bounded above gate floor `-0.3`).
- `propagation_rounds`: Simulated sync rounds until ring denouncement reaches target repository.
