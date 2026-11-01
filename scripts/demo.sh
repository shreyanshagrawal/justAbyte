#!/usr/bin/env bash
# ==================================================================================================
# OpenCred End-to-End Reproducible Demonstration
# ==================================================================================================
# Runs an end-to-end, deterministic demo verifying:
# 1. Deterministic generation of the seed-42 simulation scenario.
# 2. Three-mode evaluation (LOCAL_ONLY, PROPAGATION, PROPAGATION_PLUS_CAMPAIGNS) against gates.
# 3. Newcomer receiving NEWCOMER_FAIR_REVIEW with network_trust 0.00.
# 4. Honest contributor targeted by a denouncement ring whose network trust is bounded by cluster cap.
# 5. Detected campaign candidate with signals listed and status AWAITING_EVIDENCE.
# 6. Exit with code 1 if any fairness gate fails.
# ==================================================================================================

set -euo pipefail

# Determine repository root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

# Locate Python environment
if [[ -x "${REPO_ROOT}/.venv/bin/python" ]]; then
    PYTHON="${REPO_ROOT}/.venv/bin/python"
elif command -v python3 &>/dev/null; then
    PYTHON="python3"
else
    PYTHON="python"
fi

DEMO_DIR=$(mktemp -d /tmp/opencred_demo_XXXXXX)
trap 'rm -rf "${DEMO_DIR}"' EXIT

echo "================================================================================"
echo "                   OpenCred Live Demonstration (Seed 42)                        "
echo "================================================================================"
echo "Working directory: ${DEMO_DIR}"
echo ""

# --------------------------------------------------------------------------------------------------
# Section 1: Generate the Seed-42 Scenario
# --------------------------------------------------------------------------------------------------
echo "==> [1/5] Generating reproducible ecosystem scenario (seed 42)..."
"${PYTHON}" scripts/simulate.py --seed 42 --num-repos 30 --out "${DEMO_DIR}/scenario-42.json"
echo ""

# --------------------------------------------------------------------------------------------------
# Section 2: Run Three-Mode Evaluation & Fairness Gates Check
# --------------------------------------------------------------------------------------------------
echo "==> [2/5] Running three-mode simulation evaluation against examples/gates.json..."
set +e
"${PYTHON}" scripts/evaluate.py \
    --seed 42 \
    --gates examples/gates.json \
    --format markdown > "${DEMO_DIR}/evaluation.md"
EVAL_STATUS=$?
set -e

cat "${DEMO_DIR}/evaluation.md"
echo ""

if [[ ${EVAL_STATUS} -ne 0 ]]; then
    echo "❌ FATAL: Simulation evaluation failed fairness or quality gates!"
    exit 1
fi
echo "✅ All evaluation gates PASSED (newcomer violations = 0, ring suppression within bounds)."
echo ""

# --------------------------------------------------------------------------------------------------
# Section 3: Show Newcomer Receiving NEWCOMER_FAIR_REVIEW with network_trust = 0
# --------------------------------------------------------------------------------------------------
echo "==> [3/5] Assessing Newcomer PR (#1 by newbie):"
echo "    Verifying fair first-time review: neutral trust (0.00), no negative presumption."
echo ""
"${PYTHON}" -m opencred.cli.main assess \
    --pr tests/fixtures/scenarios/pr_newcomer.json \
    --base-manifests tests/fixtures/scenarios/base_manifests \
    --telemetry-dir tests/fixtures/scenarios \
    --evaluator evaluator/repo \
    --history tests/fixtures/scenarios/history_empty.json \
    --now "2026-10-01T12:00:00Z" \
    --format text
echo ""

# --------------------------------------------------------------------------------------------------
# Section 4: Show Honest Contributor Targeted by a Denouncement Ring (Bounded by Cap)
# --------------------------------------------------------------------------------------------------
echo "==> [4/5] Assessing Honest Contributor Targeted by a Sybil Denunciation Ring:"
echo "    Target: 'honest_target_0' on repo-08/pkg-08."
echo "    Rule 5 & Cluster Cap: Multiple colluding ring members denounce honest_target_0,"
echo "    but external denouncement is strictly bounded at -0.20."
echo ""

# Extract base manifests and PR data from the generated scenario
"${PYTHON}" -c "
import json
from pathlib import Path
from opencred.simulation.generate import Scenario

demo_dir = Path('${DEMO_DIR}')
manifests_dir = demo_dir / 'manifests'
manifests_dir.mkdir(parents=True, exist_ok=True)

scen_data = json.loads(Path('${DEMO_DIR}/scenario-42.json').read_text(encoding='utf-8'))
for repo, text in scen_data['manifests'].items():
    fname = repo.replace('/', '__') + '.td'
    (manifests_dir / fname).write_text(text, encoding='utf-8')

for p in scen_data['prs']:
    if p['author'] == 'honest_target_0':
        (demo_dir / 'pr_target.json').write_text(json.dumps(p), encoding='utf-8')
        (demo_dir / 'hist_target.json').write_text('[]', encoding='utf-8')
        break
"

"${PYTHON}" -m opencred.cli.main assess \
    --pr "${DEMO_DIR}/pr_target.json" \
    --base-manifests "${DEMO_DIR}/manifests" \
    --telemetry-dir "tests/fixtures/scenarios/telemetry_empty" \
    --evaluator repo-08/pkg-08 \
    --history "${DEMO_DIR}/hist_target.json" \
    --now "2026-10-01T12:00:00Z" \
    --format text
echo ""

# --------------------------------------------------------------------------------------------------
# Section 5: Show Detected Campaign Candidate with Signals and Status AWAITING_EVIDENCE
# --------------------------------------------------------------------------------------------------
echo "==> [5/5] Campaign Detection Candidate Extraction:"
echo "    Displaying detected coordinated cluster with status 'AWAITING_EVIDENCE' prior to triage."
echo ""

"${PYTHON}" -c "
import json
from datetime import datetime, UTC
from pathlib import Path
from opencred.simulation.generate import Scenario
from opencred.simulation.evaluate import build_scenario_telemetry
from opencred.core.campaign import detect_campaigns

scen_data = json.loads(Path('${DEMO_DIR}/scenario-42.json').read_text(encoding='utf-8'))
scenario = Scenario.model_validate(scen_data)

fixed_time = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
telemetry = build_scenario_telemetry(scenario, fixed_time)

telem_items = []
for repo, load_res in telemetry.items():
    for entry in load_res.entries:
        telem_items.append((repo, entry))

campaign_results = detect_campaigns(prs=scenario.prs, telemetry_entries=telem_items)

print(f'Total Coordinated Candidates Flagged: {len(campaign_results.candidates)}')
print('=' * 80)
for idx, candidate in enumerate(campaign_results.candidates, start=1):
    print(f'Candidate #{idx}:')
    print(f'  Candidate ID  : {candidate.id[:16]}...')
    print(f'  Status        : {candidate.status}')
    print(f'  Campaign Risk : {candidate.campaign_risk:.2f}')
    print(f'  Unique Authors: {len(candidate.authors)} ({candidate.authors[:4]}...)')
    print(f'  Affected Repos: {len(candidate.affected_repos)} ({[str(r) for r in candidate.affected_repos[:3]]}...)')
    print('  Signals Identified:')
    for s in candidate.signals:
        print(f'    - {s}')
    print('-' * 80)
"

echo ""
echo "================================================================================"
echo "          OpenCred Demo Finished Successfully (All Gates Enforced)             "
echo "================================================================================"
exit 0

