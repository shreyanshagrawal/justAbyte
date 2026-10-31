# Vouch File Format (Trustdown `.td`) Specification Research

This document provides a factual specification of the upstream **Vouch** / **Trustdown** (`.td`) file format used by projects such as Ghostty and Mitchell Hashimoto's `vouch` tool, which OpenCred intends to maintain compatibility with.

---

## 1. Upstream Sources & References

All claims and grammar rules documented below are derived directly from the official upstream repositories and source files:

1. **Mitchell Hashimoto's Vouch Repository**:
   - Repository: [https://github.com/mitchellh/vouch](https://github.com/mitchellh/vouch)
   - Readme & Format Overview: [`README.md`](https://raw.githubusercontent.com/mitchellh/vouch/main/README.md)
   - Canonical Example File: [`VOUCHED.example.td`](https://raw.githubusercontent.com/mitchellh/vouch/main/VOUCHED.example.td)
   - Core File Parser (`from td` / `to td`): [`vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)
   - Trust Logic & Query Engine (`check-user`, `add-user`, etc.): [`vouch/lib.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/lib.nu)
   - Parser Test Suite: [`tests/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/tests/file.nu)
   - Trust Logic Test Suite: [`tests/lib.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/tests/lib.nu)

2. **Ghostty Project Repository**:
   - Repository: [https://github.com/ghostty-org/ghostty](https://github.com/ghostty-org/ghostty)
   - Contributing Guide: [`CONTRIBUTING.md`](https://raw.githubusercontent.com/ghostty-org/ghostty/main/CONTRIBUTING.md)
   - Live Production Manifest: [`.github/VOUCHED.td`](https://raw.githubusercontent.com/ghostty-org/ghostty/main/.github/VOUCHED.td)

---

## 2. Grammar in Plain Language

The `.td` (Trustdown) file is a line-oriented, UTF-8 plain-text document designed to be trivially readable and parseable without complex parsing libraries.

### 2.1 File Location
- Upstream tools search by default for either `VOUCHED.td` in the repository root or `.github/VOUCHED.td` ([Source: `default-path` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)).

### 2.2 Line Processing & Whitespace
- The file is processed line-by-line in sequential order.
- Each line is trimmed of leading and trailing whitespace ([Source: `parse-line` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)).
- **Blank lines**: Any line that is empty or contains only whitespace is treated as a `blank` entry (`type: "blank"`). Blank lines do not represent contributors or trust assertions, but are preserved when re-serializing.

### 2.3 Comments
- **Full-line comments**: A line whose trimmed content starts with `#` is treated as a comment line (`type: "comment"`). The full verbatim line (including the `#`) is captured as the comment detail ([Source: `parse-line` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)).
- **Inline comments**: There is **no** inline comment syntax. Characters such as `#` appearing after a handle are treated as text in the reason/details field.

### 2.4 Handles & Platform Prefixes
- Handles must not contain the `@` symbol ([Source: `VOUCHED.example.td`](https://raw.githubusercontent.com/mitchellh/vouch/main/VOUCHED.example.td)).
- **Platform Prefix**: A handle may be written either as `username` or as `platform:username` (e.g., `github:mitchellh`).
  - The handle is split on the first colon `:` into at most 2 parts ([Source: `parse-handle` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)).
  - If a colon is present: the first component is `platform`, the second is `username`.
  - If no colon is present: `platform` is `null` (unspecified), and the full token is `username`.
- **Case Normalization**: In the upstream reference implementation, the platform and username are downcased using `str downcase` during parsing ([Source: `parse-handle` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu) and [`tests/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/tests/file.nu)). Comparisons are case-insensitive.
- **Platform Resolution**: When matching against a platform query with a default platform (e.g., `github`), an entry with an unspecified (`null`) platform matches if the default platform matches, or if either side is unspecified ([Source: `check-user` in `vouch/lib.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/lib.nu)).

### 2.5 Vouched Entries
- A line specifying a trusted entity begins directly with the handle (e.g., `alice` or `github:alice`).
- `type` is evaluated as `"vouch"` ([Source: `parse-line` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)).

### 2.6 Denounced Entries
- A line specifying a blocked/denounced entity begins with a leading minus sign `-` (e.g., `-badactor` or `-github:badactor`).
- The minus sign is stripped before parsing the handle and reason.
- `type` is evaluated as `"denounce"` ([Source: `parse-line` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)).

### 2.7 Details and Reason Text
- Following the handle, an entry may optionally contain freeform text after a space separator.
- The entry is split on the first space ` ` into at most 2 parts ([Source: `parse-line` in `vouch/file.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/file.nu)).
- The second part, if present, is captured as `details`. If absent, `details` is `null`.
- While reasons are primarily utilized for denouncements (explaining why a contributor was denounced), the grammar and parser allow details on vouched entries as well.

### 2.8 Duplicate Handling & Ordering
- **Ordering**: The file is conventionally kept alphabetically sorted by username (`sort-by -i username`), with header comments and blank lines retained at the top ([Source: `sort-table` in `vouch/lib.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/lib.nu)).
- **Parsing behavior (`from td`)**: The parser does not fail on duplicate lines; it produces a sequential list of records containing all entries.
- **Query behavior (`check-user`)**: The reference query engine iterates sequentially from top to bottom. The **first** matching record encountered for a given user (vouch or denounce) dictates the result (`"vouched"` or `"denounced"`). Subsequent conflicting or duplicate entries are shadowed ([Source: `check-user` in `vouch/lib.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/lib.nu)).
- **Mutation behavior (`add-user` / `denounce-user`)**: When adding or denouncing via the upstream tool, all existing matching entries for that user are removed first (`remove-user`), and the single updated entry is appended and sorted ([Source: `add-user` and `denounce-user` in `vouch/lib.nu`](https://raw.githubusercontent.com/mitchellh/vouch/main/vouch/lib.nu)).

---

## 3. Example Files and Expected Parse Results

The parsed representation below corresponds to the record schema produced by the upstream reference parser (`vouch/file.nu`):
```json
{
  "type": "vouch" | "denounce" | "comment" | "blank",
  "platform": string | null,
  "username": string | null,
  "details": string | null
}
```

### Example 1: Standard File with Comments, Vouches, and Denouncements

**Input file (`VOUCHED.td`):**
```text
# Vouched contributors for the repository
# Maintained via vouch

alice
bob
github:charlie
-github:badguy
-github:spammer Sent automated AI slop
```

**Expected Parse Result:**
```json
[
  {
    "type": "comment",
    "platform": null,
    "username": null,
    "details": "# Vouched contributors for the repository"
  },
  {
    "type": "comment",
    "platform": null,
    "username": null,
    "details": "# Maintained via vouch"
  },
  {
    "type": "blank",
    "platform": null,
    "username": null,
    "details": null
  },
  {
    "type": "vouch",
    "platform": null,
    "username": "alice",
    "details": null
  },
  {
    "type": "vouch",
    "platform": null,
    "username": "bob",
    "details": null
  },
  {
    "type": "vouch",
    "platform": "github",
    "username": "charlie",
    "details": null
  },
  {
    "type": "denounce",
    "platform": "github",
    "username": "badguy",
    "details": null
  },
  {
    "type": "denounce",
    "platform": "github",
    "username": "spammer",
    "details": "Sent automated AI slop"
  }
]
```

---

### Example 2: Platform Prefixes, Case Normalization, and Vouch Details

**Input file (`VOUCHED.td`):**
```text
# Mixed platforms and notes
gitlab:DevOne
GitHub:MitchellH Core Maintainer
-sourcehut:abuser Harassment
```

**Expected Parse Result:**
```json
[
  {
    "type": "comment",
    "platform": null,
    "username": null,
    "details": "# Mixed platforms and notes"
  },
  {
    "type": "vouch",
    "platform": "gitlab",
    "username": "devone",
    "details": null
  },
  {
    "type": "vouch",
    "platform": "github",
    "username": "mitchellh",
    "details": "Core Maintainer"
  },
  {
    "type": "denounce",
    "platform": "sourcehut",
    "username": "abuser",
    "details": "Harassment"
  }
]
```

---

### Example 3: Edge Cases (Duplicate Entries, Non-Comment Hash, Whitespace)

**Input file (`VOUCHED.td`):**
```text
  # Leading whitespace in comment line  

github:alice
-github:alice Conflicting duplicate entry
github:bob # Note: inline hash is not a comment syntax
```

**Expected Parse Result:**
```json
[
  {
    "type": "blank",
    "platform": null,
    "username": null,
    "details": null
  },
  {
    "type": "comment",
    "platform": null,
    "username": null,
    "details": "  # Leading whitespace in comment line  "
  },
  {
    "type": "blank",
    "platform": null,
    "username": null,
    "details": null
  },
  {
    "type": "vouch",
    "platform": "github",
    "username": "alice",
    "details": null
  },
  {
    "type": "denounce",
    "platform": "github",
    "username": "alice",
    "details": "Conflicting duplicate entry"
  },
  {
    "type": "vouch",
    "platform": "github",
    "username": "bob",
    "details": "# Note: inline hash is not a comment syntax"
  }
]
```
*(Note for `alice`: At the parse stage, both lines are parsed as distinct records. When queried with upstream `check-user "github:alice"`, the first matching record in line order takes precedence, yielding status `"vouched"`).*

---

## 4. Unverified

The following items could not be confirmed from an authoritative formal specification, standard, or upstream documentation:

1. **Formal Grammar / RFC**: Mitchell Hashimoto stated explicitly in `README.md` that he is not ready to publish a formal specification for Trustdown until usage stabilizes. Consequently, the grammar is defined entirely by the behavior of the Nushell reference implementation rather than a formal specification.
2. **Valid Username / Platform Character Sets**: Upstream code does not validate characters in `username` or `platform` (e.g. against GitHub's username regex `^[a-zA-Z0-9](?:[a-zA-Z0-9]|-(?=[a-zA-Z0-9])){0,38}$`). It simply performs string splits on `:` and lowercases the tokens. Whether non-alphanumeric characters, spaces, or Unicode in handles should trigger syntax errors or be rejected is unverified.
3. **Canonical Platform Names**: Upstream documents and tests use `github`, but there is no verified enumeration or registry of canonical platform identifiers (e.g., `gitlab` vs `gl`, `codeberg`, `sourcehut`).
4. **Consecutive Spaces in Details**: The reference implementation uses `$rest | split row " " --number 2`. If multiple consecutive spaces exist between the handle and the details (e.g. `user   my note`), the details string retains leading whitespace (`"  my note"`). Whether this whitespace should be trimmed is unverified.
5. **Conflict Resolution Policy for Corrupted / Malicious Files**: Upstream relies on its `add-user` / `denounce-user` commands to prevent duplicates during file generation. However, if a hand-edited file contains both `alice` and `-alice`, the behavior (first match in file order wins) is an emergent artifact of the `check-user` linear loop, rather than an explicitly specified conflict resolution rule.

