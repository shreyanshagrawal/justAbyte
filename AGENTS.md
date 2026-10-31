# AGENTS.md — OpenCred Permanent Rules & Guidelines

## PROJECT

OpenCred is a Git-native, decentralized trust and campaign-detection system for open-source contributions. Repositories own their trust data as files in Git, choose which peer repositories they trust, and evaluate contributors locally. The system is **ADVISORY ONLY**. It must never automatically close, block, reject, or fail a pull request because of a contributor's score.

---

## STACK

- **Language & Runtime**: Python 3.12, src layout (`src/opencred`).
- **Validation & Models**: Pydantic v2 for data models and validation.
- **CLI Interface**: Typer for the CLI.
- **Testing & Quality**: pytest for tests, ruff for linting and formatting, mypy in strict mode.
- **Architecture Constraints**: No database. No always-on server. No blockchain. No peer-to-peer networking.
- **Dependency Policy**: Minimize dependencies. Before adding any dependency, state its name, its purpose, and why the standard library is insufficient.

---

## ARCHITECTURE BOUNDARY

- `src/opencred/core/` contains all domain logic: manifests, trust, campaign, telemetry, triage, assessment. It must **NOT** import `typer`, GitHub client libraries, `httpx`, `requests`, or anything from `src/opencred/cli` or `src/opencred/action`.
- `src/opencred/cli/` and `src/opencred/action/` are interface layers. They depend on core, never the reverse.
- `src/opencred/ai/` holds an optional analyzer interface. Core must function when no AI analyzer is configured.

---

## NON-NEGOTIABLE RULES

1. **Determinism**: The same inputs always produce byte-identical outputs. Never use Python's built-in `hash()` for fingerprints, because it is randomized per process. Use `hashlib` (for example SHA-256). Sort all collections before serializing. Never put wall-clock timestamps into scored results. Timestamps may appear only in inputs and telemetry metadata.
2. **Three Separate Outputs**: `network_trust` in $[-1.0, +1.0]$, `campaign_risk` in $[0.0, 1.0]$, `contribution_quality_evidence` in $[0.0, 1.0]$. Never combine them into one score. Never define risk as $1 - \text{trust}$.
3. **Propagation**: Trust strength $t(i \to j)$ is in $[0.0, 1.0]$. A path of two edges has weight $t(i \to a) \times t(a \to b)$. Maximum propagation depth is 2 hops. Trust is directional; $A$ trusting $B$ does not imply $B$ trusts $A$.
4. **Origin Deduplication**: An assertion is counted once per **ORIGIN** repository, using that origin's strongest eligible path. Relayed copies are never independent evidence. Multiple paths to one origin never add together.
5. **Corroboration**: A single external denouncement has bounded influence. Severe negative network trust requires denouncements from multiple independent origins. A repository's own local denouncement is treated separately and can count fully.
6. **Fairness**: Missing data is **NOT** negative evidence. A contributor with no history gets `network_trust = 0`, `campaign_risk = 0` unless campaign evidence exists, and triage `NEWCOMER` or `UNCERTAIN`, never a negative label.
7. **Base-Branch Trust**: Trust manifests used in an assessment are read from the base branch of the repository, never from the pull request's head. A PR author must not be able to edit their own vouches as part of the PR being assessed.
8. **Explainability**: Every non-trivial output includes reason strings that reference concrete evidence counts. No output may state that a contributor is safe or trustworthy as a verdict.
9. **Configuration & Thresholds**: Thresholds and weights live in one config module (`src/opencred/core/config.py`) as named constants with comments saying they are **STARTING VALUES** to be tuned by simulation, not validated optima.
10. **AI Boundary**: AI output is never the sole basis for a triage decision. Core logic must pass all tests with the AI analyzer absent.

---

## TESTING

- Every core module has unit tests.
- Algorithms have hand-calculated expected values written in the test as comments.
- Tests must not access the network.
- Tests that cover fairness properties are marked with `@pytest.mark.fairness`.

---

## WORKING STYLE

- Before any multi-file change, state a short plan.
- Keep each change small and focused on one phase.
- Run `ruff`, `mypy`, and `pytest` before reporting a step as complete.
- Report which tests you ran and their results.

---

## Graphify

This repo is indexed in Graphify. For questions about code structure, callers, dependencies, or the impact of a change, use Graphify's MCP tools before grep or reading files one by one: query_graph for how something works, graphify_find for where a symbol is defined, graphify_callers / graphify_callees for who calls what, graphify_impact for what a change could affect. Use grep for exact strings, such as error messages or config keys. If a Graphify tool fails or the repository isn't indexed, say so, then fall back to grep.

---

## Skills & Capabilities

- **Review Before Each Prompt**: Before tackling any prompt or task, review available skills in `.agents/skills/` (including `find-skills`) to check if an existing skill applies.
- **Skill Discovery**: When a prompt involves specialized tools, libraries, or capabilities that could benefit from an agent skill, consult `find-skills` (`npx skills find <query>` / `npx skills add <package>`) to discover and load relevant skills.
