"""Pull request telemetry models, validation, and ingestion.

This module implements the telemetry loader for OpenCred (.github/PR_TELEMETRY.json).
All parsing and evaluation logic strictly follows AGENTS.md rules:
- Deterministic behavior: 'now' is injected as an explicit parameter (no datetime.now()).
- Malformed telemetry is rejected entirely; it must never partially contribute.
- Expired telemetry is discarded and produces a visible limited-evidence note.
- ABSENT telemetry is a normal, valid state.
- Missing or stale telemetry never produces negative evidence or increases campaign risk.
"""

import json
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import Field, ValidationError, field_validator, model_validator

from opencred.core.models import OpenCredModel, RepoId


def _to_utc(dt: datetime) -> datetime:
    """Normalize a datetime to timezone-aware UTC for safe comparisons."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


class TelemetryStatus(StrEnum):
    """Lifecycle status of a telemetry snapshot."""

    FRESH = "FRESH"
    EXPIRED = "EXPIRED"
    MALFORMED = "MALFORMED"
    ABSENT = "ABSENT"


class TelemetryEntry(OpenCredModel):
    """An individual pull request record within repository telemetry."""

    pr_number: int = Field(ge=1, description="Pull request number")
    author: str = Field(description="Normalized contributor username")
    opened_at: datetime = Field(description="Timestamp when the PR was opened")
    exact_fingerprint: str = Field(
        description="64-character SHA-256 hexadecimal digest of normalized diff"
    )
    path_set: list[str] = Field(description="Sorted list of relative file paths")
    minhash_signature: list[int] = Field(
        description="Fixed-length list of 64-bit MinHash signature integers"
    )
    description_similarity_signature: list[int] = Field(
        description="Fixed-length list of MinHash signature integers for title/body"
    )

    @field_validator("author", mode="before")
    @classmethod
    def _validate_author(cls, v: Any) -> Any:
        if isinstance(v, str):
            cleaned = v.strip().lstrip("@").lower()
            if not cleaned:
                raise ValueError("author cannot be empty")
            return cleaned
        return v

    @field_validator("path_set", mode="after")
    @classmethod
    def _validate_path_set(cls, v: list[str]) -> list[str]:
        # Always maintain sorted order for canonical determinism
        return sorted(v)

    @field_validator("exact_fingerprint", mode="after")
    @classmethod
    def _validate_exact_fingerprint(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if len(cleaned) != 64 or not all(c in "0123456789abcdef" for c in cleaned):
            raise ValueError(
                f"exact_fingerprint must be a 64-character hexadecimal string, got '{v}'"
            )
        return cleaned


class TelemetryPayload(OpenCredModel):
    """Top-level schema for .github/PR_TELEMETRY.json."""

    schema_version: int = Field(
        default=1,
        description="Telemetry format version, strictly 1 for this specification",
    )
    repository: RepoId = Field(description="Normalized owner/repo repository identifier")
    generated_at: datetime = Field(description="Timestamp when this snapshot was created")
    expires_at: datetime = Field(
        description="Timestamp after which this snapshot is considered expired"
    )
    entries: list[TelemetryEntry] = Field(
        default_factory=list,
        description="Pull request telemetry records",
    )

    @field_validator("schema_version")
    @classmethod
    def _validate_schema_version(cls, v: int) -> int:
        if v != 1:
            raise ValueError(f"Unsupported schema_version: expected 1, got {v}")
        return v

    @model_validator(mode="after")
    def _validate_expiry_after_generation(self) -> Self:
        gen = _to_utc(self.generated_at)
        exp = _to_utc(self.expires_at)
        if exp <= gen:
            raise ValueError(
                f"expires_at ({self.expires_at.isoformat()}) must be after "
                f"generated_at ({self.generated_at.isoformat()})"
            )
        return self


class TelemetryLoadResult(OpenCredModel):
    """Result of loading and validating repository telemetry."""

    status: TelemetryStatus
    repository: RepoId | None = None
    schema_version: int | None = None
    generated_at: datetime | None = None
    expires_at: datetime | None = None
    entries: list[TelemetryEntry] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def load_telemetry(text: str | None, now: datetime) -> TelemetryLoadResult:
    """Load, parse, validate, and check freshness of PR telemetry.

    Args:
        text: Raw JSON file contents from .github/PR_TELEMETRY.json, or None if absent.
        now: Current evaluation timestamp supplied by the caller for determinism.

    Returns:
        TelemetryLoadResult indicating FRESH, EXPIRED, MALFORMED, or ABSENT.
    """
    if text is None or not text.strip():
        return TelemetryLoadResult(
            status=TelemetryStatus.ABSENT,
            notes=["limited evidence: telemetry is absent"],
        )

    try:
        raw_data = json.loads(text)
    except json.JSONDecodeError as err:
        return TelemetryLoadResult(
            status=TelemetryStatus.MALFORMED,
            errors=[f"Malformed JSON: {err}"],
        )

    if not isinstance(raw_data, dict):
        return TelemetryLoadResult(
            status=TelemetryStatus.MALFORMED,
            errors=["Root of telemetry JSON must be an object"],
        )

    # Check top-level required fields before Pydantic parsing for crisp diagnostics
    required_fields = {"schema_version", "repository", "generated_at", "expires_at", "entries"}
    missing = [f for f in sorted(required_fields) if f not in raw_data]
    if missing:
        return TelemetryLoadResult(
            status=TelemetryStatus.MALFORMED,
            errors=[f"Missing required top-level field(s): {', '.join(missing)}"],
        )

    try:
        payload = TelemetryPayload.model_validate(raw_data)
    except ValidationError as err:
        errors = [f"{e['loc']}: {e['msg']}" for e in err.errors()]
        return TelemetryLoadResult(
            status=TelemetryStatus.MALFORMED,
            errors=errors,
            entries=[],  # Malformed telemetry must never partially contribute
        )

    # Evaluate freshness against the supplied 'now' timestamp
    now_utc = _to_utc(now)
    expires_utc = _to_utc(payload.expires_at)

    if now_utc >= expires_utc:
        expiry_iso = payload.expires_at.isoformat()
        return TelemetryLoadResult(
            status=TelemetryStatus.EXPIRED,
            repository=payload.repository,
            schema_version=payload.schema_version,
            generated_at=payload.generated_at,
            expires_at=payload.expires_at,
            entries=[],  # Expired telemetry returns no entries for matching
            notes=[f"limited evidence: telemetry expired at {expiry_iso}"],
        )

    return TelemetryLoadResult(
        status=TelemetryStatus.FRESH,
        repository=payload.repository,
        schema_version=payload.schema_version,
        generated_at=payload.generated_at,
        expires_at=payload.expires_at,
        entries=payload.entries,
    )


def telemetry_campaign_risk(load_result: TelemetryLoadResult) -> float:
    """Return the baseline campaign risk contributed by telemetry state.

    Pursuant to AGENTS.md Rule 6 (Fairness): Missing, absent, expired, or malformed
    telemetry represents lack of correlation evidence, never negative evidence.
    This baseline risk is strictly 0.0.
    """
    if load_result.status != TelemetryStatus.FRESH:
        return 0.0
    return 0.0


__all__ = [
    "TelemetryEntry",
    "TelemetryLoadResult",
    "TelemetryPayload",
    "TelemetryStatus",
    "load_telemetry",
    "telemetry_campaign_risk",
]
