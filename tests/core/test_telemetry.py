"""Unit tests for pull request telemetry loading, freshness validation, and fairness.

All tests include explicit hand-calculated expected values in comments in
accordance with AGENTS.md rules.
"""

import json
from datetime import UTC, datetime

import pytest

from opencred.core.models import RepoId
from opencred.core.telemetry import (
    TelemetryStatus,
    load_telemetry,
    telemetry_campaign_risk,
)

# Reference test timestamps in UTC
_NOW_VALID = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
_GEN_TIME = datetime(2026, 10, 25, 12, 0, 0, tzinfo=UTC)
_EXPIRY_FUTURE = datetime(2026, 11, 7, 12, 0, 0, tzinfo=UTC)
_EXPIRY_PAST = datetime(2026, 10, 31, 12, 0, 0, tzinfo=UTC)

_DUMMY_FINGERPRINT = "a" * 64


def _build_telemetry_json(
    *,
    schema_version: int = 1,
    repository: str = "pallets/flask",
    generated_at: str = "2026-10-25T12:00:00Z",
    expires_at: str = "2026-11-07T12:00:00Z",
    entries: list[dict] | None = None,
) -> str:
    """Helper to construct canonical test telemetry JSON strings."""
    if entries is None:
        entries = [
            {
                "pr_number": 101,
                "author": "Alice",
                "opened_at": "2026-10-26T10:00:00Z",
                "exact_fingerprint": _DUMMY_FINGERPRINT,
                "path_set": ["src/app.py", "README.md"],
                "minhash_signature": [123456, 789012],
                "description_similarity_signature": [654321, 210987],
            }
        ]
    return json.dumps(
        {
            "schema_version": schema_version,
            "repository": repository,
            "generated_at": generated_at,
            "expires_at": expires_at,
            "entries": entries,
        }
    )


def test_fresh_telemetry_loads() -> None:
    """Fresh telemetry (now < expires_at) loads successfully with all entries."""
    text = _build_telemetry_json(
        generated_at="2026-10-25T12:00:00Z",
        expires_at="2026-11-07T12:00:00Z",
    )

    # Hand calculation:
    # now = 2026-11-01T12:00:00Z < expires_at (2026-11-07T12:00:00Z).
    # Status is FRESH. All 1 entry loaded. Author 'Alice' normalized to 'alice'.
    # Path set sorted: ['README.md', 'src/app.py'].
    result = load_telemetry(text, now=_NOW_VALID)

    assert result.status == TelemetryStatus.FRESH
    assert result.repository == RepoId("pallets/flask")
    assert result.schema_version == 1
    assert len(result.entries) == 1
    assert result.errors == []
    assert result.notes == []

    entry = result.entries[0]
    assert entry.pr_number == 101
    assert entry.author == "alice"
    assert entry.path_set == ["README.md", "src/app.py"]
    assert entry.exact_fingerprint == _DUMMY_FINGERPRINT
    assert entry.minhash_signature == [123456, 789012]


def test_expired_telemetry_returns_expired_and_no_entries() -> None:
    """Expired telemetry (now >= expires_at) returns EXPIRED status and empty entries."""
    expiry_str = "2026-10-31T12:00:00Z"
    text = _build_telemetry_json(
        generated_at="2026-10-20T12:00:00Z",
        expires_at=expiry_str,
    )

    # Hand calculation:
    # now = 2026-11-01T12:00:00Z >= expires_at (2026-10-31T12:00:00Z).
    # Status is EXPIRED. Entries must be empty (0 entries) to prevent stale matching.
    # Note must record: 'limited evidence: telemetry expired at ...'.
    result = load_telemetry(text, now=_NOW_VALID)

    assert result.status == TelemetryStatus.EXPIRED
    assert result.entries == []
    assert len(result.notes) == 1
    assert "limited evidence: telemetry expired at" in result.notes[0]
    assert expiry_str.replace("Z", "+00:00") in result.notes[0] or expiry_str in result.notes[0]
    assert result.errors == []


def test_malformed_json_returns_malformed() -> None:
    """Invalid JSON syntax returns MALFORMED status, empty entries, and reports errors."""
    bad_json = "{\ninvalid json payload\n"

    # Hand calculation:
    # JSONDecodeError caught -> Status MALFORMED, entries empty, 1 error recorded.
    result = load_telemetry(bad_json, now=_NOW_VALID)

    assert result.status == TelemetryStatus.MALFORMED
    assert result.entries == []
    assert len(result.errors) >= 1
    assert "Malformed JSON" in result.errors[0]


def test_missing_required_entry_field_rejected_entirely() -> None:
    """A fixture with one entry missing a field is rejected entirely (no partial entries)."""
    # Two entries: first is valid, second is missing 'exact_fingerprint'
    entries = [
        {
            "pr_number": 1,
            "author": "bob",
            "opened_at": "2026-10-26T10:00:00Z",
            "exact_fingerprint": _DUMMY_FINGERPRINT,
            "path_set": ["file.txt"],
            "minhash_signature": [1, 2],
            "description_similarity_signature": [3, 4],
        },
        {
            "pr_number": 2,
            "author": "charlie",
            "opened_at": "2026-10-26T11:00:00Z",
            # missing 'exact_fingerprint'
            "path_set": ["file2.txt"],
            "minhash_signature": [5, 6],
            "description_similarity_signature": [7, 8],
        },
    ]
    text = _build_telemetry_json(entries=entries)

    # Hand calculation:
    # Partial contribution prohibited: entries must be 0, status must be MALFORMED,
    # and error must report validation failure for missing field.
    result = load_telemetry(text, now=_NOW_VALID)

    assert result.status == TelemetryStatus.MALFORMED
    assert result.entries == []
    assert len(result.errors) >= 1
    assert any("exact_fingerprint" in err for err in result.errors)


def test_extraneous_field_rejected() -> None:
    """Extraneous fields like 'full_diff' or 'body' are forbidden and cause MALFORMED status."""
    entries = [
        {
            "pr_number": 1,
            "author": "bob",
            "opened_at": "2026-10-26T10:00:00Z",
            "exact_fingerprint": _DUMMY_FINGERPRINT,
            "path_set": ["file.txt"],
            "minhash_signature": [1, 2],
            "description_similarity_signature": [3, 4],
            "full_diff": "+ forbidden code here",  # strictly excluded field
        }
    ]
    text = _build_telemetry_json(entries=entries)

    result = load_telemetry(text, now=_NOW_VALID)

    assert result.status == TelemetryStatus.MALFORMED
    assert result.entries == []
    assert len(result.errors) >= 1


def test_absent_telemetry_produces_note_and_no_error() -> None:
    """Absent telemetry (None or empty string) is a normal state producing a note and no error."""
    # Hand calculation:
    # ABSENT is normal. Status ABSENT, errors empty,
    # 1 note: 'limited evidence: telemetry is absent'.
    for empty_input in (None, "", "   \n\t  "):
        result = load_telemetry(empty_input, now=_NOW_VALID)
        assert result.status == TelemetryStatus.ABSENT
        assert result.entries == []
        assert result.errors == []
        assert len(result.notes) == 1
        assert "limited evidence: telemetry is absent" in result.notes[0]


@pytest.mark.fairness
def test_missing_or_stale_telemetry_never_produces_negative_campaign_score() -> None:
    """Fairness Rule 6: Missing, stale, or malformed telemetry never penalizes a contributor."""
    # Test all non-fresh telemetry states
    absent_result = load_telemetry(None, now=_NOW_VALID)
    expired_result = load_telemetry(
        _build_telemetry_json(expires_at="2026-10-01T00:00:00Z"), now=_NOW_VALID
    )
    malformed_result = load_telemetry("{bad json", now=_NOW_VALID)

    # Hand calculation:
    # Under fairness rules, absent or stale telemetry represents absence of evidence.
    # The campaign risk contribution must be exactly 0.0 (neutral), never positive penalty.
    assert telemetry_campaign_risk(absent_result) == 0.0
    assert telemetry_campaign_risk(expired_result) == 0.0
    assert telemetry_campaign_risk(malformed_result) == 0.0
