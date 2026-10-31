# OpenCred Manifest Specification (`manifest-spec.md`)

This document defines the specification for **OpenCred Trust Manifests**, an extension of the upstream Vouch / Trustdown (`.td`) format (`VOUCHED.td` / `.github/VOUCHED.td`).

---

## 1. File Location & Base-Branch Security Rule

### 1.1 Manifest Paths
An OpenCred manifest is stored as a flat text file in Git. Repositories locate the manifest at one of the standard paths:
- `.github/VOUCHED.td` (recommended for GitHub repositories)
- `VOUCHED.td` (repository root)

### 1.2 Base-Branch Trust Rule (AGENTS.md Rule 7)
> [!IMPORTANT]
> **Base-Branch Evaluation Only**: When an assessment is performed (e.g., evaluating a pull request), the trust manifest and all peer manifests **MUST** be loaded strictly from the repository's base branch (the merge target, such as `main`), never from the pull request's head branch or untrusted working trees.

This rule guarantees that a pull request author cannot vouch for themselves, alter peer trust weights, or delete denouncements as part of the pull request under evaluation.

---

## 2. Upstream Compatibility

OpenCred is fully backward-compatible with upstream Vouch/Ghostty implementations:

- In the upstream Trustdown format, any line whose trimmed content begins with `#` is classified as `type: "comment"` and ignored during contributor trust evaluation (see [`docs/vouch-format.md`](vouch-format.md#23-comments)).
- OpenCred encodes all peer repository trust relationships inside comment lines using the prefix `# @trust-repo`.
- **Standard Vouch Parsers**: Upstream tools (e.g., `mitchellh/vouch`, Ghostty CI bots) parse these lines harmlessly as comments. They continue to process standard contributor vouches and denouncements with zero breakage.
- **OpenCred Parsers**: OpenCred inspects comment lines for the `@trust-repo` directive to construct the directional peer repository trust graph while simultaneously parsing contributor vouches and denouncements.

```
+-------------------------------------------------------------------+
| .github/VOUCHED.td                                                |
|                                                                   |
| # Standard comment                                                |
| # @trust-repo ghostty-org/ghostty weight=0.8  <-- Ignored by Vouch|
|                                               <-- Parsed by OpenCred
| alice                                         <-- Vouch in both   |
| -github:badactor spammer                      <-- Denounce in both|
+-------------------------------------------------------------------+
```

---

## 3. Peer Trust Directive (`@trust-repo`)

OpenCred establishes a decentralized web of trust by allowing repositories to declare trust in peer repositories.

### 3.1 Syntax
A peer trust directive is written on a single line with the exact format:
```text
# @trust-repo <owner>/<repo> weight=<decimal>
```

#### Grammar Details:
1. **Comment Prefix**: Must begin with `# @trust-repo` (with single or multiple whitespace characters between `#` and `@trust-repo`).
2. **Repository Target**: `<owner>/<repo>`
   - Case-normalized to lowercase.
   - Identifies the trusted peer repository forge path (e.g., `ghostty-org/ghostty`, `pallets/flask`).
3. **Weight Parameter**: `weight=<decimal>`
   - Key and value separated by `=`.
   - `<decimal>` must be a valid float/decimal representation in the closed interval `[0.0, 1.0]`.
   - Example valid weights: `0.0`, `0.5`, `0.85`, `1.0`.

### 3.2 Direction and Ownership
- The repository containing the manifest is the **trusting repository** ($A$).
- The repository specified in the directive is the **trusted peer repository** ($B$).
- The edge is strictly directional: $A \to B$ with trust strength $t(A \to B) \in [0.0, 1.0]$. Trust is not symmetric ($A \to B$ does not imply $B \to A$).
- Propagation follows AGENTS.md rules: maximum propagation depth is 2 hops, with path weight $t(A \to B) \times t(B \to C)$.

### 3.3 Semantic Rules & Constraints
- **At most one directive per repository**: A manifest may declare trust in a given peer repository at most once.
- **Duplicate directives are fatal errors**: Declaring the same peer repository multiple times (e.g., conflicting weights or repeated declarations) is a parse error. Duplicate directives must never be silently deduplicated, averaged, or summed.
- **Weight Bounds**: Any weight $< 0.0$ or $> 1.0$ is invalid and constitutes a parse error.

---

## 4. Contributor Entries (Local Assertions)

Standard Vouch lines map directly to OpenCred local assertions:

### 4.1 Vouch Entries (`LOCAL_VOUCH`)
- **Syntax**: `username` or `platform:username` (e.g., `alice`, `github:bob`).
- **OpenCred Mapping**: Maps to a local positive assertion (`AssertionType.VOUCH`).
- **Semantics**: The repository owner asserts direct positive trust in the contributor. In local scope, a local vouch provides direct positive evidence for the contributor.

### 4.2 Denounce Entries (`LOCAL_DENOUNCE`)
- **Syntax**: `-username [reason]` or `-platform:username [reason]` (e.g., `-badguy`, `-github:spammer AI-generated spam`).
- **OpenCred Mapping**: Maps to a local negative assertion (`AssertionType.DENOUNCE`).
- **Details / Reason**: The optional text following the handle is preserved as the reason/metadata string for explainability.
- **Semantics**: The repository owner explicitly denounces the contributor. Under AGENTS.md rule 5 (Corroboration), a repository's **own local denouncement** is treated separately and counts fully, unlike external denouncements which have bounded influence and require corroboration.

### 4.3 Platform Normalization
- Platforms and usernames are case-normalized to lower case (e.g., `GitHub:Alice` becomes `github:alice`).
- If no platform is specified, it defaults to the host platform of the repository (default: `github`).

---

## 5. Error Handling & Validation Policy

OpenCred enforces strict error handling to ensure determinism and security:

1. **Explicit Line-Numbered Diagnostics**:
   - Every syntax or validation error must explicitly report the file path and the **1-based line number** where the fault occurred.
2. **Fail Closed (No Silent Coercion)**:
   - A malformed or unrecognizable line **must never** silently become a vouch or a denouncement.
   - A malformed peer directive (e.g. `# @trust-repo invalid-target`, or `# @trust-repo repo weight=2.5`) must never be silently ignored as an ordinary comment. Any line starting with `# @trust-repo` that violates the directive grammar must raise a parsing error.
3. **No Silent Fallbacks**:
   - Duplicate peer repository directives raise a parse error.
   - Out-of-bounds weights ($< 0$ or $> 1$) raise a parse error.
4. **Deterministic Behavior**:
   - Given identical file content, the parser must produce the exact same structured AST or raise the exact same error every single time.

---

## 6. Manifest Example

Here is a complete example of an OpenCred manifest demonstrating upstream compatibility, peer trust directives, local vouches, and local denouncements:

```text
# ==============================================================================
# OpenCred / Vouch Trust Manifest
# ==============================================================================
#
# Peer Repositories Trusted by This Project:
# (Parsed by OpenCred; treated as comments by standard Vouch tools)
# @trust-repo ghostty-org/ghostty weight=0.9
# @trust-repo mitchellh/vouch weight=0.85
# @trust-repo astral-sh/uv weight=0.7

# ------------------------------------------------------------------------------
# Direct Contributor Vouches (Local Assertions):
# ------------------------------------------------------------------------------
aalhendi
github:alice
github:bob

# ------------------------------------------------------------------------------
# Direct Contributor Denouncements (Local Assertions):
# ------------------------------------------------------------------------------
-github:badactor Persistent AI slop PRs
-spammer
```

### Expected Parsed OpenCred Manifest Structure:
- **Peer Trust Directives**:
  - `ghostty-org/ghostty` -> `weight = 0.9`
  - `mitchellh/vouch` -> `weight = 0.85`
  - `astral-sh/uv` -> `weight = 0.7`
- **Local Vouches**:
  - `github:aalhendi`
  - `github:alice`
  - `github:bob`
- **Local Denouncements**:
  - `github:badactor` (reason: `"Persistent AI slop PRs"`)
  - `github:spammer` (reason: `null`)

