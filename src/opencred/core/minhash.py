"""MinHash locality-sensitive hashing for set similarity estimation.

This module provides a pure-Python, deterministic MinHash implementation
using SHA-256 derived hash families. It satisfies all AGENTS.md determinism
requirements without third-party dependencies or reliance on Python's hash().
"""

import hashlib
from collections.abc import Sequence


def minhash_signature(tokens: frozenset[str], num_perm: int = 128) -> tuple[int, ...]:
    """Compute a deterministic MinHash signature for a set of token strings.

    Args:
        tokens: A frozenset of token strings.
        num_perm: The number of permutations / hash functions (default 128).

    Returns:
        A tuple of 64-bit integers of length num_perm representing the signature.
        Returns a tuple of zeros if tokens is empty.

    Raises:
        ValueError: If num_perm is less than 1.
    """
    if num_perm < 1:
        raise ValueError(f"num_perm must be at least 1, got {num_perm}")

    if not tokens:
        return (0,) * num_perm

    sig: list[int] = []
    for i in range(num_perm):
        # Derive 64-bit hash from the first 8 bytes of SHA-256(f"{i}:{token}")
        min_val = min(
            int.from_bytes(
                hashlib.sha256(f"{i}:{token}".encode()).digest()[:8],
                byteorder="big",
                signed=False,
            )
            for token in tokens
        )
        sig.append(min_val)

    return tuple(sig)


def estimate_similarity(
    sig_a: tuple[int, ...] | Sequence[int],
    sig_b: tuple[int, ...] | Sequence[int],
) -> float:
    """Estimate Jaccard similarity between two MinHash signatures.

    Similarity is computed as the fraction of matching hash values across
    corresponding permutation indices.

    Args:
        sig_a: First MinHash signature.
        sig_b: Second MinHash signature.

    Returns:
        Estimated similarity as a float in [0.0, 1.0]. Returns 0.0 if signatures
        are empty.

    Raises:
        ValueError: If the two signatures differ in length.
    """
    if len(sig_a) != len(sig_b):
        raise ValueError(
            f"Signatures must have identical lengths, got {len(sig_a)} and {len(sig_b)}"
        )

    if not sig_a:
        return 0.0

    matching_positions = sum(1 for a, b in zip(sig_a, sig_b, strict=True) if a == b)
    return float(matching_positions / len(sig_a))


__all__ = [
    "estimate_similarity",
    "minhash_signature",
]
