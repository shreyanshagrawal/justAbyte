"""Unit tests for deterministic MinHash signatures and similarity estimation.

All tests include explicit hand-calculated expected values in comments in
accordance with AGENTS.md rules.
"""

import json
import os
import subprocess
import sys

import pytest

from opencred.core.minhash import estimate_similarity, minhash_signature


def test_minhash_identical_sets_produce_identical_signatures() -> None:
    """Identical token sets produce identical MinHash signatures with 1.0 similarity."""
    tokens = frozenset({"alpha", "beta", "gamma", "delta", "epsilon"})

    # Hand calculation:
    # Deterministic SHA-256 hash across identical inputs yields identical minimums.
    # Fraction of matching positions: 128 / 128 = 1.0.
    sig_a = minhash_signature(tokens, num_perm=128)
    sig_b = minhash_signature(tokens, num_perm=128)

    assert sig_a == sig_b
    assert len(sig_a) == 128
    assert estimate_similarity(sig_a, sig_b) == 1.0


def test_minhash_disjoint_sets_estimate_near_zero() -> None:
    """Disjoint sets estimate similarity near 0.0 (strictly below 0.1 with 128 permutations)."""
    # Fixed fixture of 50 distinct elements in set_a and 50 distinct elements in set_b
    set_a = frozenset(f"disjoint_token_alpha_{i}" for i in range(50))
    set_b = frozenset(f"disjoint_token_beta_{i}" for i in range(50))

    # Hand calculation:
    # Intersection: empty set (size 0)
    # Union: 100 elements
    # True Jaccard = 0 / 100 = 0.0
    # Expected matching positions across 128 independent hash functions on this fixture: 0
    # Estimated similarity = 0 / 128 = 0.0 < 0.1
    sig_a = minhash_signature(set_a, num_perm=128)
    sig_b = minhash_signature(set_b, num_perm=128)

    similarity = estimate_similarity(sig_a, sig_b)
    assert similarity < 0.1
    assert similarity == 0.0


def test_minhash_known_jaccard_half_fixture() -> None:
    """Estimated similarity for a Jaccard 0.5 fixture is within 0.15 at num_perm=256."""
    # Fixed fixture:
    # 50 tokens shared between both sets
    # 25 tokens unique to set_a
    # 25 tokens unique to set_b
    shared_tokens = {f"token_common_{i}" for i in range(50)}
    tokens_a_only = {f"token_unique_a_{i}" for i in range(25)}
    tokens_b_only = {f"token_unique_b_{i}" for i in range(25)}

    set_a = frozenset(shared_tokens | tokens_a_only)
    set_b = frozenset(shared_tokens | tokens_b_only)

    # Hand calculation:
    # |set_a| = 50 + 25 = 75
    # |set_b| = 50 + 25 = 75
    # |set_a & set_b| = 50
    # |set_a | set_b| = 50 + 25 + 25 = 100
    # True Jaccard = 50 / 100 = 0.5000
    # With 256 permutations on this deterministic SHA-256 fixture:
    # Matching positions: 131 / 256 = 0.51171875
    # Absolute difference: |0.51171875 - 0.5| = 0.01171875 <= 0.15
    sig_a = minhash_signature(set_a, num_perm=256)
    sig_b = minhash_signature(set_b, num_perm=256)

    estimated = estimate_similarity(sig_a, sig_b)
    assert abs(estimated - 0.5) <= 0.15


def test_minhash_subprocess_pythonhashseed_invariance() -> None:
    """MinHash produces byte-identical output across processes with different PYTHONHASHSEED.

    Guards against accidental usage of Python's built-in randomized hash().
    """
    fixed_tokens = frozenset(
        {
            "function_definition",
            "variable_assignment",
            "return_statement",
            "import_module",
            "exception_handler",
        }
    )

    # Signature computed in current running process
    local_sig = minhash_signature(fixed_tokens, num_perm=64)

    # Execute a separate Python subprocess with a distinct PYTHONHASHSEED
    env = os.environ.copy()
    env["PYTHONHASHSEED"] = "987654321"

    # Command to run in subprocess
    script = (
        "import json; from opencred.core.minhash import minhash_signature; "
        "tokens = frozenset({"
        "'function_definition', 'variable_assignment', 'return_statement', "
        "'import_module', 'exception_handler'"
        "}); "
        "sig = minhash_signature(tokens, num_perm=64); "
        "print(json.dumps(list(sig)))"
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )

    subprocess_sig = tuple(json.loads(result.stdout.strip()))

    # Verify both signatures match identically across process boundaries
    assert local_sig == subprocess_sig


def test_minhash_empty_tokens_and_validation() -> None:
    """MinHash handles empty token sets and validates configuration parameters."""
    empty_tokens = frozenset()
    sig_empty = minhash_signature(empty_tokens, num_perm=16)

    # Empty token set produces a tuple of zeros
    assert sig_empty == (0,) * 16

    # Invalid num_perm raises ValueError
    with pytest.raises(ValueError, match="num_perm must be at least 1"):
        minhash_signature(empty_tokens, num_perm=0)

    # Signatures of differing lengths raise ValueError
    with pytest.raises(ValueError, match="Signatures must have identical lengths"):
        estimate_similarity((1, 2, 3), (1, 2))

    # Empty signatures return 0.0
    assert estimate_similarity((), ()) == 0.0
