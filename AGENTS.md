# AGENTS.md — OpenCred Project Rules & Agent Guidelines

## 1. Project Overview

**OpenCred** is a decentralized reputation and trust layer for GitHub contributors. Repositories publish signed vouch/denounce records, choose which repositories they trust, and evaluate contributors independently.

> [!IMPORTANT]
> **Advisory Only**: OpenCred is strictly advisory and **must never automatically block a PR**. All outputs serve to assist maintainers in making informed decisions.

---

## 2. Technology Stack

- **Language & Runtime**: TypeScript (strict mode enabled), Node.js LTS
- **Persistence**: PostgreSQL
- **Testing**: Vitest
- **Future Interfaces**:
  - GitHub App via [Probot](https://probot.github.io/)
  - CLI tool for offline/local inspections

---

## 3. Architecture Rules

- **Core Isolation**: The core engine lives in `packages/core` (trust graph, propagation, scoring, campaign detection, fairness) and must have **NO dependency** on GitHub, Probot, or the CLI.
- **Dependency Flow**: Interface packages (`packages/github-app`, `packages/cli`, etc.) depend on `packages/core`. **Never** introduce reverse dependencies from core to interface layers.
- **Independent Metrics**: Maintain **Reputation**, **Risk**, and **Confidence** as three distinct, orthogonal outputs:
  - **Reputation**: Range $[-1.0, +1.0]$
  - **Risk**: Range $[0.0, 1.0]$ (or designated categorical states like `"insufficient_evidence"`)
  - **Confidence**: Range $[0.0, 1.0]$
  - **Invariant**: **Never** compute risk as `1 - reputation`. A contributor can have high reputation and high risk simultaneously (e.g., compromised credentials), or neutral reputation with high risk.

---

## 4. Trust Propagation Model

_(Fixed convention — do not alter without explicit approval)_

- **Direct Trust ($t\_{ij}$)**: $t_{ij} \in [0.0, 1.0]$ represents the directed trust repository $i$ assigns to repository $j$.
  - Trust is directional: $A \to B$ does not imply $B \to A$.
- **Path Weight ($W(p)$)**: For a path $p$ with $d$ edges ($d \ge 1$):
  $$W(p) = \left(\prod_{(u, v) \in p} t_{uv}\right) \times 0.8^{d-1}$$
- **Maximum Depth**: Maximum propagation depth is strictly **3 hops** ($d \le 3$).
- **Single Count per Origin**: Each origin repository counts **ONCE** using its **strongest eligible path** ($p^* = \arg\max_p W(p)$). Never sum multiple paths to the same origin.

---

## 5. Deduplication & Provenance

- **Provenance Tracking**: Every assertion retains its original authoring repository and issuer identity.
- **Relay Invariance**: Copies, mirrors, or relays of an assertion are never treated as independent evidence.
- **Stable Content Hashing**: Identical assertions are deduplicated using a deterministic, stable content hash.

---

## 6. Fairness & Invariants

- **Default State / Cold Start**: A contributor with no history receives:
  - `reputation = 0.0`
  - `risk = "insufficient_evidence"` (or $0.0$ with zero confidence flag)
  - `confidence = low / 0.0`
- **Negative Evidence Fallacy**: Absence of data is **never** negative evidence.
- **PR Outcomes**: Rejected or closed PRs are **not** automatically classified as bad behavior.
- **AI Contributions**: AI-generated text or code is **never** by itself evidence of malice.

---

## 7. Testing Requirements

- **Unit Test Coverage**: Every core module requires unit tests using Vitest.
- **Deterministic Algorithm Tests**: Trust graph propagation and scoring algorithms must have deterministic test suites with hand-computed expected values verifying boundary conditions and path calculations.

---

## 8. Working Style & Discipline

- **Plan First**: Before making large changes, state your plan in a few clear bullet points.
- **Small Iterations**: Keep commits and modifications small, modular, and reviewable.
- **Verify Always**: Run all unit and integration tests before reporting completion.
- **Minimal Dependencies**: Do not introduce new external dependencies without explicitly listing them and justifying why they are necessary.

---

## 9. Continuous Integration (CI)

- **CI Platform**: GitHub Actions. Workflow files live in `.github/workflows/`.

### 9.1 Required Checks on Every Push

1. **Clean Installation**: Install dependencies using `npm ci` (never `npm install` in CI).
2. **Typecheck**: Full typecheck across all packages with TypeScript strict mode enabled.
3. **Lint**: Run ESLint with zero warnings allowed (`--max-warnings 0`).
4. **Formatting**: Format check with Prettier in check mode (`prettier --check .`, no in-place writes).
5. **Unit Tests**: Execute Vitest unit tests for all packages.

### 9.2 Required Checks on Pull Requests to `main` (in addition to Push checks)

6. **Fairness Test Suite**: Execute the dedicated fairness test suite in `packages/core` (tagged `"fairness"`).
7. **Simulation Gate**: Run the seed-42 simulation scenario; fail the workflow if any fairness metric is violated.
8. **Architecture Boundary Check**: Verify core engine isolation; fail if `packages/core` imports from `packages/github-app` or `packages/cli`, or imports `probot`, `octokit`, or `commander`.

### 9.3 On Merge to `main`

9. **Full Build**: Clean production build of all workspace packages.
10. **Artifact Archival**: Upload compiled build artifacts and the simulation report.

### 9.4 CI Safety & Execution Rules

- **Node.js LTS Pinning**: Pin Node.js to the LTS version used locally. Specify the version in `.nvmrc` and read it in all workflow jobs.
- **Dependency Caching**: Cache `~/.npm` keyed deterministically on the `package-lock.json` hash.
- **Job Timeouts**: Every workflow job must enforce an explicit timeout of **15 minutes** (`timeout-minutes: 15`).
- **Security & Permissions**:
  - Default permissions must be set to minimal: `permissions: { contents: read }`.
  - **Never** print or echo secrets in logs.
  - **Never** use `pull_request_target`.
  - Do not run untrusted PR code with write-permission tokens.
- **No Masked Failures**: A failing check must **never** be marked as skipped, ignored, or configured with `continue-on-error: true`.
