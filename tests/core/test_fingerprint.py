"""Unit tests for fingerprinting, normalization, shingling, and Jaccard similarity.

All tests include explicit hand-calculated expected values in comments in
accordance with AGENTS.md rules.
"""

import pytest

from opencred.core.fingerprint import (
    exact_fingerprint,
    jaccard,
    normalize_diff,
    path_set,
    shingles,
)


def test_exact_fingerprint_whitespace_invariance() -> None:
    """Two diffs differing only in whitespace produce byte-identical SHA-256 fingerprints."""
    diff_a = """
    def calculate_total(items):
        total = 0
        for item in items:
            total += item.price

        return total
    """

    diff_b = """
    def   calculate_total(items):
      total = 0
      for  item  in  items:
        total += item.price
      return total

    """

    # Hand calculation:
    # Both diffs, after removing blank lines, stripping leading/trailing whitespace,
    # and collapsing consecutive whitespace within each line, become:
    # "def calculate_total(items):\ntotal = 0\nfor item in items:\n"
    # "total += item.price\nreturn total"
    normalized_a = normalize_diff(diff_a)
    normalized_b = normalize_diff(diff_b)
    expected = (
        "def calculate_total(items):\n"
        "total = 0\n"
        "for item in items:\n"
        "total += item.price\n"
        "return total"
    )
    assert normalized_a == expected
    assert normalized_b == expected
    assert exact_fingerprint(diff_a) == exact_fingerprint(diff_b)


def test_exact_fingerprint_token_difference() -> None:
    """Two diffs differing by a single token produce different fingerprints."""
    diff_original = "def add(x, y):\n    return x + y"
    diff_modified = "def add(x, y):\n    return x - y"

    # Diff original normalized: "def add(x, y):\nreturn x + y"
    # Diff modified normalized: "def add(x, y):\nreturn x - y"
    # Changed token: '+' vs '-'
    assert normalize_diff(diff_original) != normalize_diff(diff_modified)
    assert exact_fingerprint(diff_original) != exact_fingerprint(diff_modified)


def test_normalize_diff_comment_stripping_and_blank_lines() -> None:
    """Comment-only lines (#, //, --) and blank lines are stripped, preserving code."""
    raw_diff = """
    # Python style comment header
    // C/JS style comment header
    -- SQL/Lua style comment header

    def query_user(user_id):
        # Fetch from database
        sql = "SELECT * FROM users WHERE id = ?"
        -- SQL query note inside block
        // Return record
        return execute(sql, user_id)

    """

    # Hand-computed expected result:
    # Lines stripped:
    # - "# Python style comment header"
    # - "// C/JS style comment header"
    # - "-- SQL/Lua style comment header"
    # - blank lines
    # - "        # Fetch from database"
    # - "        -- SQL query note inside block"
    # - "        // Return record"
    # Remaining lines normalized:
    # 1. "def query_user(user_id):"
    # 2. 'sql = "SELECT * FROM users WHERE id = ?"'
    # 3. "return execute(sql, user_id)"
    expected = (
        'def query_user(user_id):\nsql = "SELECT * FROM users WHERE id = ?"\n'
        "return execute(sql, user_id)"
    )

    assert normalize_diff(raw_diff) == expected


def test_normalize_diff_diff_markers_with_comments() -> None:
    """Diff addition and deletion lines containing only comments are stripped."""
    diff_content = """
    + # Add new validation rule
    + if not valid:
    - // Legacy fallback check
    -     return False
    +     raise ValueError("invalid")
    """

    # Hand-computed expected:
    # "+ # Add new validation rule" -> stripped
    # "+ if not valid:" -> "+ if not valid:"
    # "- // Legacy fallback check" -> stripped
    # "-     return False" -> "- return False"
    # "+     raise ValueError(\"invalid\")" -> '+ raise ValueError("invalid")'
    expected = '+ if not valid:\n- return False\n+ raise ValueError("invalid")'
    assert normalize_diff(diff_content) == expected


def test_path_set_normalization_and_deduplication() -> None:
    """Path set normalizes backslashes to forward slashes, preserves case, and deduplicates."""
    input_paths = [
        "src\\opencred\\core\\models.py",
        "src/opencred/core/models.py",
        "README.md",
        "docs\\API.md",
        "README.md",
    ]

    # Hand calculation:
    # "src\\opencred\\core\\models.py" -> "src/opencred/core/models.py"
    # "src/opencred/core/models.py" -> "src/opencred/core/models.py" (duplicate)
    # "README.md" -> "README.md" (casing preserved: 'README.md' != 'readme.md')
    # "docs\\API.md" -> "docs/API.md"
    # "README.md" -> "README.md" (duplicate)
    # Deduplicated set elements (3 total):
    # {"src/opencred/core/models.py", "README.md", "docs/API.md"}
    result = path_set(input_paths)
    expected = frozenset({"src/opencred/core/models.py", "README.md", "docs/API.md"})
    assert result == expected


def test_shingles_short_known_sentence() -> None:
    """Shingles extracts lowercase word k-grams after stripping punctuation."""
    sentence = "The quick brown fox jumps over the lazy dog."

    # Hand calculation:
    # 1. Punctuation stripped (trailing '.' removed).
    # 2. Lowercased: "the quick brown fox jumps over the lazy dog"
    # 3. Words (9 total):
    #    ["the", "quick", "brown", "fox", "jumps", "over", "the", "lazy", "dog"]
    # 4. 3-grams (k=3): 9 - 3 + 1 = 7 shingles:
    #    - "the quick brown"
    #    - "quick brown fox"
    #    - "brown fox jumps"
    #    - "fox jumps over"
    #    - "jumps over the"
    #    - "over the lazy"
    #    - "the lazy dog"
    expected = frozenset(
        {
            "the quick brown",
            "quick brown fox",
            "brown fox jumps",
            "fox jumps over",
            "jumps over the",
            "over the lazy",
            "the lazy dog",
        }
    )

    result = shingles(sentence, k=3)
    assert result == expected


def test_shingles_short_text_and_validation() -> None:
    """Shingles returns empty set if words < k and raises on invalid k."""
    # Text with 2 words and k=3 -> empty frozenset
    assert shingles("Hello, world!", k=3) == frozenset()

    # Empty text -> empty frozenset
    assert shingles("", k=3) == frozenset()

    # Invalid k < 1 raises ValueError
    with pytest.raises(ValueError, match="k must be at least 1"):
        shingles("sample text", k=0)


def test_jaccard_hand_computed() -> None:
    """Hand-computed Jaccard similarity: jaccard({'a','b','c'}, {'b','c','d'}) = 2/4 = 0.5."""
    set_a = {"a", "b", "c"}
    set_b = {"b", "c", "d"}

    # Hand calculation:
    # Intersection: {"b", "c"} -> size = 2
    # Union: {"a", "b", "c", "d"} -> size = 4
    # Jaccard = 2 / 4 = 0.5
    result = jaccard(set_a, set_b)
    assert result == 0.5


def test_jaccard_empty_sets() -> None:
    """Jaccard returns 0.0 when both sets are empty or one set is empty."""
    # Hand calculation: Both empty -> 0.0 by specification definition
    assert jaccard(set(), set()) == 0.0
    assert jaccard(frozenset(), frozenset()) == 0.0

    # Hand calculation: One empty set, one non-empty
    # Intersection: 0, Union: 2 -> 0 / 2 = 0.0
    assert jaccard(set(), {"x", "y"}) == 0.0
    assert jaccard({"x", "y"}, frozenset()) == 0.0


def test_jaccard_identical_and_disjoint() -> None:
    """Jaccard similarity on identical sets is 1.0 and on completely disjoint sets is 0.0."""
    # Identical: Intersection = 3, Union = 3 -> 3/3 = 1.0
    assert jaccard({"a", "b", "c"}, {"a", "b", "c"}) == 1.0

    # Disjoint: Intersection = 0, Union = 4 -> 0/4 = 0.0
    assert jaccard({"a", "b"}, {"c", "d"}) == 0.0
