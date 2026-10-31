"""Diff normalization, content fingerprinting, and similarity metrics.

This module implements deterministic diff normalization, exact SHA-256 content
fingerprinting, path normalization, word-level shingling, and Jaccard similarity
computation for pull request campaign and plagiarism detection.

All operations strictly obey AGENTS.md determinism rules:
- No reliance on Python's randomized hash() function.
- All fingerprints use cryptographic SHA-256 via hashlib.
"""

import hashlib
import string
from collections.abc import Collection, Set
from typing import Any

# Comment prefixes for common programming and query languages:
# '#' (Python, Shell, Ruby, YAML, Dockerfile, etc.)
# '//' (C, C++, Java, JavaScript, TypeScript, Rust, Go, C#, Swift, PHP, etc.)
# '--' (SQL, Lua, Haskell, Ada, etc.)
_COMMENT_PREFIXES: tuple[str, ...] = ("#", "//", "--")


def _is_comment_line(stripped: str) -> bool:
    """Determine whether a trimmed diff line is a comment-only line."""
    # Direct comment line in source code
    if stripped.startswith(_COMMENT_PREFIXES):
        # Exclude unified diff file headers such as '--- a/file' or '--- /dev/null'
        if stripped.startswith("---") and (len(stripped) == 3 or stripped[3] in (" ", "\t")):
            return False
        return True

    # Diff hunk addition or deletion ('+' or '-') followed by a comment
    if stripped.startswith(("+", "-")) and not stripped.startswith(("+++", "---")):
        inner = stripped[1:].lstrip()
        if inner.startswith(_COMMENT_PREFIXES):
            return True

    return False


def normalize_diff(diff: str) -> str:
    """Normalize a diff string to eliminate superficial formatting differences.

    Exact normalization rules:
    1. Line splitting: The input diff is split into lines respecting all
       standard line boundaries (LF, CRLF, CR), preserving the original sequence.
    2. Whitespace trimming: Leading and trailing whitespace is stripped from
       each line.
    3. Blank line removal: Empty lines or lines containing exclusively whitespace
       are discarded.
    4. Comment stripping: Comment-only lines for common languages are stripped:
       - Lines whose trimmed content starts with '#', '//', or '--' (excluding
         unified diff old-file headers starting with '--- ').
       - Hunk addition/deletion lines (beginning with '+' or '-' but not '+++'/'---')
         whose remaining content begins with '#', '//', or '--'.
    5. Whitespace collapsing: Internal whitespace sequences within each retained
       line are collapsed to a single space character (' ').
    6. Joining: Retained lines are joined using standard newline ('\\n').
    """
    normalized_lines: list[str] = []

    for raw_line in diff.splitlines():
        stripped = raw_line.strip()
        if not stripped:
            continue
        if _is_comment_line(stripped):
            continue
        # Collapse internal whitespace sequences to a single space
        collapsed = " ".join(stripped.split())
        normalized_lines.append(collapsed)

    return "\n".join(normalized_lines)


def exact_fingerprint(diff: str) -> str:
    """Compute the SHA-256 hexadecimal digest of the normalized diff.

    Uses hashlib.sha256 to ensure determinism across processes and environments.
    """
    normalized = normalize_diff(diff)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def path_set(files: list[str]) -> frozenset[str]:
    """Normalize file path separators, preserve case, and return a deduplicated set.

    All directory separators ('\\\\') are converted to POSIX forward slashes ('/').
    Character casing is preserved unchanged ('lowercase nothing').
    """
    return frozenset(f.replace("\\", "/") for f in files)


def shingles(text: str, k: int = 3) -> frozenset[str]:
    """Extract lowercase word k-grams from text after stripping punctuation.

    Args:
        text: Input string to shingle.
        k: Shingle size (number of words per k-gram), defaults to 3.

    Returns:
        A frozenset of space-joined lowercase k-word strings. Returns an empty
        frozenset if the word count is less than k.

    Raises:
        ValueError: If k is less than 1.
    """
    if k < 1:
        raise ValueError(f"k must be at least 1, got {k}")

    # Strip punctuation using string.punctuation
    punctuation_remover = str.maketrans("", "", string.punctuation)
    cleaned = text.translate(punctuation_remover)
    words = cleaned.lower().split()

    if len(words) < k:
        return frozenset()

    return frozenset(" ".join(words[i : i + k]) for i in range(len(words) - k + 1))


def jaccard(
    a: Set[Any] | frozenset[Any] | set[Any] | Collection[Any],
    b: Set[Any] | frozenset[Any] | set[Any] | Collection[Any],
) -> float:
    """Calculate the Jaccard similarity coefficient between two sets: |A & B| / |A | B|.

    Returns 0.0 when both sets are empty.
    """
    set_a = a if isinstance(a, (set, frozenset)) else set(a)
    set_b = b if isinstance(b, (set, frozenset)) else set(b)

    union_len = len(set_a | set_b)
    if union_len == 0:
        return 0.0

    intersection_len = len(set_a & set_b)
    return float(intersection_len / union_len)


__all__ = [
    "exact_fingerprint",
    "jaccard",
    "normalize_diff",
    "path_set",
    "shingles",
]
