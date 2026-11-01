# OpenCred

OpenCred is a Git-native, decentralized trust and campaign-detection system for open-source contributions. Repositories own their trust data as plain-text manifest files committed directly to Git, declare which peer repositories they trust, and evaluate pull requests locally.

The system is **strictly advisory**. OpenCred provides evidence-backed signals to human maintainers and must **never** automatically close, block, reject, or fail a pull request based on a contributor's score.

---

## 1. The Problem

Open-source maintainers face an increasing volume of automated, low-effort, or coordinated pull requests. Events like Hacktoberfest, cosmetic automated refactoring scripts, and coordinated badge-farming campaigns overwhelm review queues with superficially plausible diffs across hundreds of independent repositories.

At the same time, naive reputation filters create severe barriers for genuine new contributors. Centralized scoring services, proprietary reputation databases, and blacklists introduce single points of failure, opacity, and punitive biases where a newcomer with zero prior history is wrongly treated as suspicious.

OpenCred addresses this challenge by decentralizing trust. Instead of relying on a centralized platform authority, individual repositories declare their trust relationships in version-controlled Git files. OpenCred evaluates incoming contributions locally, combines cryptographic diff fingerprinting with local web-of-trust propagation, and treats newcomers fairly.

---

## 2. The Three Outputs

OpenCred produces three independent signals for every evaluated pull request. They are never collapsed or blended into a single composite score, and risk is never defined as $1 - \text{trust}$:

| Output | Range | Description |
| :--- | :--- | :--- |
| `network_trust` | $[-1.0, +1.0]$ | Corroborated web-of-trust consensus from the evaluator repository and its trusted peers. |
| `campaign_risk` | $[0.0, 1.0]$ | Likelihood that the pull request belongs to a coordinated multi-account or multi-repo campaign burst. |
| `contribution_quality_evidence` | $[0.0, 1.0]$ | Objective, positive evidence indicating that the pull request warrants human maintainer review. |

### Why They Are Kept Separate
1. **Trust is Not Competence**: A highly trusted contributor can still make poor or low-effort contributions. Conversely, an unknown newcomer can submit an exceptional, critical bug fix.
2. **Missing History is Not Negative**: A contributor without prior history has neutral `network_trust = 0.0`. Defining campaign risk as $1 - \text{trust}$ would falsely classify every newcomer as having maximum risk ($1.0$).
3. **Targeted Campaigns Exploit Reputation**: Attackers often compromise or farm accounts with moderate network trust. Merging trust and risk would obscure acute campaign anomalies behind positive historical trust.

---

## 3. How Trust Propagates

Trust is directional ($A \to B$ does not imply $B \to A$), bounded in $[0.0, 1.0]$, and decays multiplicatively over paths. OpenCred restricts propagation to a maximum depth of **two hops**.

### Propagation Rules
- **Direct Edge (1 hop)**: Direct trust declared in the evaluator's base manifest: $w(i \to j) = t(i \to j)$.
- **Two-Hop Path (2 hops)**: Transitive trust through an intermediary peer: $w(i \to k) = t(i \to j) \times t(j \to k)$.
- **Origin Deduplication**: An origin repository's assertion is counted **once**, using that origin's strongest eligible path. Multiple paths to the same origin never add together.
- **Corroboration Requirement**: A single external denouncement has bounded influence (capped at $-0.20$). Severe negative network trust ($<-0.20$) strictly requires corroborating denouncements from multiple independent origin repositories. A repository's own local denouncement is treated separately and counts fully.

### Worked Example
Suppose repository `repo/alpha` evaluates contributor `@carol`:
1. `repo/alpha` directly trusts `repo/beta` with strength $t(\text{alpha} \to \text{beta}) = 0.8$.
2. `repo/beta`'s manifest trusts `repo/gamma` with strength $t(\text{beta} \to \text{gamma}) = 0.5$.
3. The propagated path strength from `repo/alpha` to `repo/gamma` is:
   $$\text{weight} = 0.8 \times 0.5 = 0.40$$
4. In its manifest, `repo/gamma` vouches for `@carol` with strength $0.9$.
5. The discounted vouch evidence from `repo/gamma` received by `repo/alpha` is:
   $$\text{evidence} = 0.40 \times 0.9 = 0.36$$

---

## 4. How Campaign Detection Works

Campaign detection identifies coordinated bursts of similar pull requests submitted across multiple repositories by different accounts within a short time window:

1. **Deterministic Diff Normalization**: Trailing whitespace, line endings, comments, and empty lines are removed to expose identical code changes regardless of formatting.
2. **Multi-Signal Similarity**: OpenCred evaluates pairwise similarity between PRs using a weighted combination of:
   - Exact SHA-256 diff fingerprint match (exact equality alone links two PRs).
   - MinHash token similarity over normalized diff tokens.
   - Word shingle similarity over PR title and body.
   - Jaccard similarity of touched file path sets.
3. **Time-Window Clustering**: PRs are linked into connected components using deterministic union-find if their combined similarity meets the threshold and their timestamps fall within the campaign window (default: 6 hours).
4. **Campaign Candidate Thresholds**: A cluster is flagged as a candidate only when it spans:
   - At least 3 distinct author accounts.
   - At least 3 distinct repositories.
   - At least 5 total pull requests.
5. **Benign Pattern Exclusions**: Coordinated clusters consisting entirely of automated dependency bumps (e.g., Dependabot, Renovate) or identical single-word typo fixes are excluded from campaign classification.

---

## 5. Fairness Principles

OpenCred enforces strict mathematical fairness guarantees to protect genuine contributors and newcomers:

- **Missing Data is Neutral**: Absence of history produces `network_trust = 0.0` and `campaign_risk = 0.0`.
- **Fair First-Time Review**: A newcomer with low campaign risk and positive quality signals receives triage `NEWCOMER_FAIR_REVIEW`.
- **No Guilt Presumption**: A newcomer lacking strong quality evidence receives `UNCERTAIN`, never a negative or punitive label.
- **Explainability**: Every non-trivial outcome lists concrete evidence reasons with origin counts. Language never declares a contributor "safe" or "malicious".
- **Base-Branch Integrity**: Trust manifests are read exclusively from the base branch of the repository, preventing PR authors from submitting self-vouches.

### Test Verifications
Fairness properties are verified under `@pytest.mark.fairness`:
- [Neutrality on Missing History](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/tests/core/test_newcomer.py#L24-L50): Verifies newcomer status with zero assertions and empty history.
- [Unclosed PR Non-Penalization](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/tests/core/test_quality.py#L38-L65): Verifies unmerged closed PRs do not penalize contribution quality.
- [Bounded External Influence](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/tests/core/test_corroboration.py#L20-L55): Verifies a single external denouncement cannot drive network trust below $-0.20$.
- [Origin Deduplication](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/tests/core/test_aggregate.py#L219-L245): Verifies multiple relay paths to an origin never inflate evidence counts.
- [Cluster Influence Capping](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/tests/core/test_clusters.py#L46-L75): Verifies sybil rings of colluding peer repositories have bounded voting influence.

---

## 6. Manifest Format

Repositories declare trust assertions and peer trust relationships in `.td` (Trust Declaration) files:

```text
# @trust-repo peer/repo-a 0.8
# @trust-repo peer/repo-b 0.5

@alice vouch 0.9
@bob denounce 1.0
```

- `# @trust-repo <owner/repo> <weight>`: Declares a directed trust edge with a weight in $[0.0, 1.0]$.
- `@<username> vouch <strength>`: Declares an explicit vouch assertion.
- `@<username> denounce <strength>`: Declares an explicit denouncement.

For full grammar, comment parsing, and directive specifications, see [docs/manifest-spec.md](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/docs/manifest-spec.md).

---

## 7. Architecture & Boundaries

The codebase follows a strict layered architecture:

```
src/opencred/
├── core/         # Pure domain logic (graph, manifests, campaign, assessment, triage)
├── cli/          # Command-line interface layer (Typer)
├── action/       # GitHub Action interface layer
├── ai/           # Optional advisory LLM campaign analyzer interface
└── simulation/   # Scenario generation, evaluation runner, sensitivity sweep
```

### Architectural Boundary Rules
- **Pure Core**: `src/opencred/core` contains pure domain logic. It must **NOT** import `typer`, `httpx`, `requests`, `urllib.request`, `socket`, or any modules from `cli`, `action`, `ai`, or `simulation`.
- **Interface Layer**: `cli` and `action` depend on `core`, never the reverse.
- **Optional AI**: `ai` is advisory only. Core operations execute deterministically without any AI model installed.
- **Enforcement**: Architecture boundaries are verified via AST analysis in [`scripts/check_architecture.py`](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/scripts/check_architecture.py).

---

## 8. Running Locally

### Installation
```bash
git clone https://github.com/shreyanshagrawal/justAbyte.git
cd justAbyte
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Quality & Verification Checks
```bash
make check
```
Runs `ruff check .`, `ruff format --check .`, `mypy src`, and `pytest`.

### CLI Usage
```bash
# Parse and inspect a trust manifest file
opencred manifest tests/fixtures/manifests/plain_valid.td --owner evaluator/repo

# Query network trust for a contributor across peer manifests
opencred trust \
  --repo-manifest tests/fixtures/scenarios/evaluator.td \
  --peers-dir tests/fixtures/scenarios \
  --evaluator evaluator/repo \
  --contributor alice

# Run the complete end-to-end advisory assessment pipeline
opencred assess \
  --pr tests/fixtures/scenarios/pr_newcomer.json \
  --base-manifests tests/fixtures/scenarios/base_manifests \
  --telemetry-dir tests/fixtures/scenarios \
  --evaluator evaluator/repo \
  --history tests/fixtures/scenarios/history_empty.json
```

### Running Simulations
```bash
# Generate deterministic scenario (seed 42)
python scripts/simulate.py --seed 42 --out examples/scenario-42.json

# Evaluate scenario against strict quality and fairness gates
python scripts/evaluate.py --seed 42 --gates examples/gates.json
```

---

## 9. GitHub Actions & Fork Security

OpenCred splits pull request assessment into two distinct GitHub Actions workflows to guarantee fork safety:

```
[Untrusted PR Event]
        │
        ▼
.github/workflows/opencred-analyze.yml
(Trigger: pull_request | Permissions: contents: read | Base Branch Checkout)
        │
        ▼ Produces result.json artifact
.github/workflows/opencred-comment.yml
(Trigger: workflow_run on default branch | Permissions: pull-requests: write)
        │
        ▼
Updates advisory PR comment via GitHub REST API
```

### Why This Design is Fork-Safe
1. **No `pull_request_target`**: `opencred-analyze.yml` runs under standard `pull_request` triggers with `contents: read` permissions. It has zero access to repository secrets or write tokens.
2. **Base Branch Execution**: Manifest parsing, configuration, and analysis code are checked out strictly from `github.event.pull_request.base.sha`. PR code is checked out into a separate `pr/` directory and treated purely as passive data for diff extraction.
3. **Privileged Separation**: The commenting workflow (`opencred-comment.yml`) runs via `workflow_run` exclusively in the context of the repository's default branch. It downloads the validated `opencred-result` artifact and updates the PR comment without executing any contributor-controlled code.

---

## 10. Known Limitations

- **Repository Names Instead of Immutable IDs**: Repositories and authors are tracked by strings (`owner/repo` and usernames). Repository renames, account transfers, or deletion can disrupt historical continuity.
- **Telemetry Freshness is Asynchronous**: Peer telemetry logs are distributed via Git and committed periodically. Telemetry is not an instant, real-time message bus.
- **Sybil Resistance is Bounded, Not Solved**: While OpenCred limits multi-hop propagation depth to 2 hops, bounds single-origin influence, and caps clustered peer weights, determined adversaries creating extensive networks of independent repositories can still exert influence.
- **Starting Value Thresholds**: Constants configured in [`src/opencred/core/config.py`](file:///Users/shreyansh/Documents/Coding/hackathon/hacktober/src/opencred/core/config.py) are baseline starting values designed for empirical sensitivity tuning, not mathematically proven global optima.
- **AI Analyzer is Strictly Advisory**: The optional LLM campaign analyzer provides qualitative summaries but cannot alter numerical scores or triage outcomes. Core OpenCred correctness is independent of AI availability. 

testing
