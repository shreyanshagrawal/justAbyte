# OpenCred Pull Request Telemetry Specification (`docs/telemetry-spec.md`)

This document defines the specification for **OpenCred Pull Request Telemetry** stored in Git at `.github/PR_TELEMETRY.json`.

---

## 1. Overview and Purpose

OpenCred detects distributed spam campaigns, coordinated PR swarms, and cross-repository code plagiarism without relying on central databases, always-on servers, or peer-to-peer networking.

Repositories optionally publish compact, privacy-preserving summaries of recently evaluated pull requests as flat JSON files in Git. Peer repositories consuming this telemetry can detect when identical or near-duplicate contributions are submitted across multiple projects simultaneously.

---

## 2. File Location & Base-Branch Security Rule

### 2.1 File Location
Telemetry must be committed at the canonical path:
```text
.github/PR_TELEMETRY.json
```

### 2.2 Base-Branch Trust Rule (AGENTS.md Rule 7)
> [!IMPORTANT]
> **Base-Branch Telemetry Ingestion Only**: Telemetry files from the evaluating repository and all peer repositories **MUST** be read strictly from their respective base branches (e.g., `main` or `master`), never from a pull request's untrusted head branch or merge commit.
>
> A contributor submitting a pull request must never be able to alter historical telemetry or inject false telemetry records into the evaluation.

---

## 3. Schema Specification: `.github/PR_TELEMETRY.json`

The telemetry file is a single JSON document conforming to the following structure:

```json
{
  "schema_version": 1,
  "repository": "owner/repo",
  "generated_at": "2026-10-31T12:00:00Z",
  "expires_at": "2026-11-07T12:00:00Z",
  "entries": [
    {
      "pr_number": 142,
      "author": "octocat",
      "opened_at": "2026-10-30T15:24:00Z",
      "exact_fingerprint": "a35f2c79b88e1042d38fbc910245a90184b4231ecda82103f1917b12046b9a84",
      "path_set": [
        "docs/README.md",
        "src/utils.py"
      ],
      "minhash_signature": [
        1827391827461928,
        9281749102837461
      ],
      "description_similarity_signature": [
        4829104829182741,
        7192837461029384
      ]
    }
  ]
}
```

### 3.1 Top-Level Fields

| Field | Type | Description |
|---|---|---|
| `schema_version` | integer | Must be strictly `1`. Incremented only on breaking format changes. |
| `repository` | string | Normalized `owner/repo` identifier (e.g. `"pallets/flask"`). |
| `generated_at` | string (ISO-8601) | UTC timestamp indicating when this snapshot was created. |
| `expires_at` | string (ISO-8601) | UTC timestamp after which this snapshot is considered expired/stale. |
| `entries` | array of objects | Chronological or reverse-chronological list of PR telemetry entries. |

### 3.2 Entry Fields

| Field | Type | Description |
|---|---|---|
| `pr_number` | integer ($\ge 1$) | Pull request number in the repository. |
| `author` | string | Contributor username (lowercase, trimmed, without leading `@`). |
| `opened_at` | string (ISO-8601) | Timestamp when the PR was originally opened. |
| `exact_fingerprint` | string (hex, 64 chars) | SHA-256 digest of the normalized diff (via `core.fingerprint.exact_fingerprint`). |
| `path_set` | array of strings | Sorted list of normalized POSIX relative file paths touched by the PR. |
| `minhash_signature` | array of integers | 64-bit unsigned integers from diff token MinHash (default length 128). |
| `description_similarity_signature` | array of integers | 64-bit unsigned integers from PR title + description shingles MinHash. |

---

## 4. Explicit Exclusions

To safeguard repository privacy and maintain minimal payload sizes, the following data is **STRICTLY EXCLUDED** from telemetry:

- **Full diffs / patches**: Excluded. Raw code additions and deletions are never published.
- **Full PR descriptions / bodies**: Excluded. Unsanitized user text is never published.
- **Commit messages & author emails**: Excluded.
- **Review comments and CI logs**: Excluded.
- **Internal contributor identifiers or local secrets**: Excluded.

Only irreversible, one-way hashes and fixed-width locality-sensitive signatures necessary for campaign matching are included.

---

## 5. Privacy Tradeoff & Threat Model

### 5.1 Privacy Considerations
- **Author Logins**: Contributor usernames are publicly visible on GitHub pull requests and commit logs. Including the normalized author login in telemetry does not reveal private identity data beyond what is already public.
- **Minimizing Fields**: By omitting full diffs and description bodies, repositories avoid leaking:
  1. Proprietary source code changes before merge.
  2. Unintended credentials, API tokens, or secrets inadvertently committed in draft pull requests.
  3. Sensitive communications or vulnerability descriptions.
- **Irreversibility**: SHA-256 diff fingerprints and MinHash signatures cannot be reversed to reconstruct the source code or PR text.

---

## 6. Freshness, Expiration, and Fairness

### 6.1 Lifecycle States
When OpenCred ingests `.github/PR_TELEMETRY.json`, it evaluates it against the current evaluation time (`now`):

1. **`FRESH`**: Telemetry is valid JSON, conforms to schema version 1, and `now < expires_at`. All entries are available for campaign matching.
2. **`EXPIRED`**: Telemetry is syntactically valid but `now >= expires_at`. All entries are ignored (`entries = []`). OpenCred records a visible note:
   ```text
   limited evidence: telemetry expired at <expires_at>
   ```
3. **`MALFORMED`**: Telemetry contains invalid JSON, missing required fields, extraneous fields, or invalid types. **The entire file is rejected** (`entries = []`). It must never partially contribute. Specific line or schema errors are reported.
4. **`ABSENT`**: Telemetry file does not exist or is empty. This is a **normal, expected state** in open source repositories. OpenCred records a visible note:
   ```text
   limited evidence: telemetry is absent
   ```

### 6.2 Fairness Property (AGENTS.md Rule 6)
> [!NOTE]
> **Missing or Stale Telemetry Is Never Negative Evidence**:
> A contributor evaluated when telemetry is `ABSENT`, `EXPIRED`, or `MALFORMED` must never receive an increased campaign risk score or a penalty. Missing telemetry simply indicates lack of cross-repository correlation evidence; the contributor's baseline campaign risk remains `0.0`.

