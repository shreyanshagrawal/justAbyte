# Security Exceptions Log

This document records approved security findings, vulnerability audit exceptions, and secret scan exceptions for the OpenCred project.

Per OpenCred security policy:
- No findings may be suppressed silently.
- Any finding that cannot be immediately remediated must be documented here with the reason, affected component, and an explicit review date.
- All exceptions must be reviewed on or before their scheduled review date.

---

## Active Exceptions

*No active security exceptions or suppressed findings.*

---

## Pipeline Audit Limitations & Notes

### `pip-audit` Severity Filtering Limitation
- **Tool**: `pip-audit` (v2.x)
- **Limitation**: `pip-audit` queries PyPI and OSV databases for known CVEs/vulnerabilities. It currently does not provide a native CLI flag to filter exit codes exclusively by CVSS severity score (e.g., `--severity high,critical`).
- **Policy**: Per project policy, the `dependency-audit` job fails on **any** known vulnerability finding discovered in the installed dependency set. Any required exception must be explicitly reviewed, registered with `--ignore-vuln <ID>`, and documented in this file.

---

## Audit History

| Date | Tool | Finding ID | Component | Status | Review Date | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| 2026-11-01 | pip-audit | N/A | Environment | Clean | 2026-11-08 | Initial baseline audit clean. |
| 2026-11-01 | gitleaks | N/A | Repository | Clean | 2026-11-08 | Initial secret scan baseline clean. |

