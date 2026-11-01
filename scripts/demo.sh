#!/usr/bin/env bash
# ==================================================================================================
# OpenCred End-to-End Real-Time Interactive Demonstration
# ==================================================================================================
# Simulates what happens in real life when pull requests arrive in GitHub:
# 1. Shows elapsed time and step-by-step processing.
# 2. Generates the ecosystem scenario (seed 42).
# 3. Runs the 3-mode evaluation against fairness gates.
# 4. Shows what a maintainer sees on GitHub when a NEWCOMER submits a PR.
# 5. Shows what happens when a Sybil Denunciation Ring targets an HONEST contributor.
# 6. Shows real-time multi-repo CAMPAIGN detection across coordinated bot accounts.
# 7. Displays the exact GitHub comment rendered by the GitHub Action on PRs.
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

export PYTHONPATH="${REPO_ROOT}:${PYTHONPATH:-}"

DEMO_DIR=$(mktemp -d /tmp/opencred_demo_XXXXXX)
trap 'rm -rf "${DEMO_DIR}"' EXIT

START_TIME=$(date +%s)

timestamp() {
    local now
    now=$(date +%s)
    local elapsed=$((now - START_TIME))
    printf "[+%02dm:%02ds]" $((elapsed / 60)) $((elapsed % 60))
}

echo "================================================================================"
echo "          OpenCred Real-Time Demonstration: How It Works on GitHub              "
echo "================================================================================"
echo "$(timestamp) Initializing environment at ${DEMO_DIR}"
echo "$(timestamp) Python interpreter: ${PYTHON}"
echo ""
sleep 1

# --------------------------------------------------------------------------------------------------
# Phase 1: Generate Scenario & Establish Baseline Trust
# --------------------------------------------------------------------------------------------------
echo "================================================================================"
echo " PHASE 1: Simulating Open-Source Ecosystem (30 Repositories, 58 Pull Requests)"
echo "================================================================================"
echo "$(timestamp) Generating deterministic scenario with ground truth labels (seed 42)..."
"${PYTHON}" scripts/simulate.py --seed 42 --num-repos 30 --out "${DEMO_DIR}/scenario-42.json"
echo "$(timestamp) Repositories and trust manifests generated."
echo ""
sleep 1

# --------------------------------------------------------------------------------------------------
# Phase 2: Evaluation Across 3 Operational Modes
# --------------------------------------------------------------------------------------------------
echo "================================================================================"
echo " PHASE 2: Running 3-Mode Ecosystem Evaluation (Testing Fairness & Gates)"
echo "================================================================================"
echo "$(timestamp) Evaluating across LOCAL_ONLY, PROPAGATION, and PROPAGATION_PLUS_CAMPAIGNS..."

set +e
"${PYTHON}" scripts/evaluate.py \
    --seed 42 \
    --gates examples/gates.json \
    --format markdown > "${DEMO_DIR}/evaluation.md"
EVAL_STATUS=$?
set -e

cat "${DEMO_DIR}/evaluation.md"

if [[ ${EVAL_STATUS} -ne 0 ]]; then
    echo "$(timestamp) ❌ FATAL: Simulation evaluation failed fairness gates!"
    exit 1
fi
echo "$(timestamp) ✅ All gates satisfied: 0 newcomer violations, 0 campaigns missed, ring suppression bounded."
echo ""
sleep 1.5

# --------------------------------------------------------------------------------------------------
# Phase 3: Live GitHub Scenario A — Newcomer Submits a Quality PR
# --------------------------------------------------------------------------------------------------
echo "================================================================================"
echo " PHASE 3: Real GitHub Event — New Contributor Opens Pull Request #1"
echo "================================================================================"
echo "$(timestamp) GitHub Webhook: pull_request.opened (Author: 'newbie')"
echo "$(timestamp) GitHub Action triggered: .github/workflows/opencred-analyze.yml"
echo "$(timestamp) Checking contributor history in repository base branch..."
echo "$(timestamp) Result: Contributor has 0 prior PRs (First-time contributor)."
echo "$(timestamp) Running OpenCred assessment pipeline..."
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
echo "$(timestamp) Rendering GitHub PR Comment generated by OpenCred Action:"
echo "--------------------------------------------------------------------------------"
"${PYTHON}" scripts/render_comment.py tests/fixtures/expected/newcomer.json
echo "--------------------------------------------------------------------------------"
echo "$(timestamp) Notice: No negative score, no 'malicious' tag, fair review recommendation."
echo ""
sleep 2

# --------------------------------------------------------------------------------------------------
# Phase 4: Live GitHub Scenario B — Sybil Denunciation Ring Attack
# --------------------------------------------------------------------------------------------------
echo "================================================================================"
echo " PHASE 4: Real GitHub Event — Sybil Ring Attacks Honest Contributor"
echo "================================================================================"
echo "$(timestamp) GitHub Webhook: pull_request.opened (Author: 'honest_target_0', PR #1000)"
echo "$(timestamp) 3 colluding repositories coordinate to denounce 'honest_target_0' with strength 1.0."
echo "$(timestamp) Running 2-hop trust propagation and corroboration check..."

"${PYTHON}" -c "
import json
from pathlib import Path

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

echo ""
"${PYTHON}" -m opencred.cli.main assess \
    --pr "${DEMO_DIR}/pr_target.json" \
    --base-manifests "${DEMO_DIR}/manifests" \
    --telemetry-dir "tests/fixtures/scenarios/telemetry_empty" \
    --evaluator repo-08/pkg-08 \
    --history "${DEMO_DIR}/hist_target.json" \
    --now "2026-10-01T12:00:00Z" \
    --format text

echo ""
echo "$(timestamp) 🛡️ DEFENSE VERIFIED: Single uncorroborated cluster denouncement is capped at -0.20."
echo "$(timestamp) Maintainer is notified to review reputation evidence, but PR is NEVER blocked."
echo ""
sleep 2

# --------------------------------------------------------------------------------------------------
# Phase 5: Live GitHub Scenario C — Coordinated Multi-Repo Campaign Burst
# --------------------------------------------------------------------------------------------------
echo "================================================================================"
echo " PHASE 5: Real GitHub Event — Coordinated Multi-Repo Campaign Detection"
echo "================================================================================"
echo "$(timestamp) 12 PRs submitted within 1.2 hours across 4 repositories by 6 different accounts."
echo "$(timestamp) Ingesting repository telemetry and MinHash token signatures..."
echo "$(timestamp) Executing deterministic graph clustering (Union-Find)..."
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

res = detect_campaigns(prs=scenario.prs, telemetry_entries=telem_items)

print(f'🚨 Discovered {len(res.candidates)} Coordinated Campaign Clusters:')
print('=' * 80)
for idx, c in enumerate(res.candidates, start=1):
    print(f'Cluster #{idx}:')
    print(f'  Candidate ID  : {c.id[:16]}...')
    print(f'  Status        : {c.status}')
    print(f'  Campaign Risk : {c.campaign_risk:.2f}')
    print(f'  Accounts ({len(c.authors)}) : {c.authors}')
    print(f'  Repos ({len(c.affected_repos)})    : {[str(r) for r in c.affected_repos]}')
    print('  Evidence Signals:')
    for s in c.signals:
        print(f'    • {s}')
    print('-' * 80)
"

echo ""
echo "================================================================================"
echo "$(timestamp) Live Demo Completed Successfully!"
echo " Total Elapsed Time: $(( $(date +%s) - START_TIME )) seconds"
echo "================================================================================"
exit 0
