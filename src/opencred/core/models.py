"""Domain data models and validation for OpenCred core.

All models adhere to the non-negotiable rules defined in AGENTS.md:
- Deterministic behavior and byte-identical canonical JSON serialization.
- Strict input range validation at construction time.
- Subject username and repository identity normalization.
"""

import json
import re
from datetime import datetime
from enum import StrEnum
from typing import Any, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    GetCoreSchemaHandler,
    field_validator,
    model_validator,
)
from pydantic_core import core_schema


class RepoId(str):
    """Repository identifier in 'owner/repo' format.

    Note:
        The OpenCred MVP uses string 'owner/repo' paths for repository identity.
        In production, repositories can be renamed or transferred, so a stable
        underlying numeric ID (such as GitHub's numeric repository ID) should
        replace or augment this identifier in future versions.
    """

    REPO_ID_REGEX = re.compile(r"^[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+$")

    def __new__(cls, value: str) -> "RepoId":
        if not isinstance(value, str):
            raise TypeError(f"RepoId must be a string, got {type(value).__name__}")
        normalized = value.strip().lower()
        if not cls.REPO_ID_REGEX.match(normalized):
            raise ValueError(
                f"Invalid RepoId format: '{value}'. Expected 'owner/repo' containing "
                "only alphanumeric characters, hyphens, underscores, or dots."
            )
        return super().__new__(cls, normalized)

    @classmethod
    def __get_pydantic_core_schema__(
        cls, _source_type: type[Any], _handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls,
            core_schema.str_schema(),
        )


def _normalize_login(v: Any) -> Any:
    """Normalize a contributor login by trimming whitespace, leading '@', and downcasing."""
    if isinstance(v, str):
        cleaned = v.strip().lstrip("@").lower()
        if not cleaned:
            raise ValueError("Contributor login cannot be empty")
        return cleaned
    return v


def to_canonical_json(model: BaseModel | Any) -> str:
    """Serialize a model or data structure to canonical byte-deterministic JSON.

    All dictionary keys at all levels are sorted alphabetically, float/number
    formats are consistent, and separators are minimal with no extraneous whitespace.
    """
    if isinstance(model, BaseModel):
        data = model.model_dump(mode="json")
    else:
        data = model
    return json.dumps(data, sort_keys=True, separators=(",", ":"))


class OpenCredModel(BaseModel):
    """Base immutable model for OpenCred data structures."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    def to_canonical_json(self) -> str:
        """Produce canonical, deterministic JSON string representation."""
        return to_canonical_json(self)


class TrustEdge(OpenCredModel):
    """A directed edge in the repository web-of-trust graph.

    Represents trust from source repository to target peer repository with
    a weight in [0.0, 1.0]. Self-loops are strictly prohibited.
    """

    source: RepoId
    target: RepoId
    weight: float = Field(ge=0.0, le=1.0, description="Trust weight in [0.0, 1.0]")

    @model_validator(mode="after")
    def _reject_self_loop(self) -> Self:
        if self.source == self.target:
            raise ValueError(
                f"Self-loop trust edges are not allowed: source and target are both '{self.source}'"
            )
        return self


class AssertionKind(StrEnum):
    """Kind of contributor trust assertion."""

    VOUCH = "VOUCH"
    DENOUNCE = "DENOUNCE"


class Assertion(OpenCredModel):
    """An explicit vouch or denouncement made by an origin repository about a subject."""

    origin: RepoId
    subject: str
    kind: AssertionKind
    strength: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence or strength of the assertion in [0.0, 1.0]",
    )
    line_number: int | None = Field(
        default=None,
        ge=1,
        description="1-based line number in origin manifest for auditability",
    )

    @field_validator("subject", mode="before")
    @classmethod
    def _validate_subject(cls, v: Any) -> Any:
        return _normalize_login(v)


class ContributionEventKind(StrEnum):
    """Types of observed contribution events."""

    MERGED = "MERGED"
    CLOSED_UNMERGED = "CLOSED_UNMERGED"
    FLAGGED_SPAM = "FLAGGED_SPAM"
    ADDRESSED_REVIEW = "ADDRESSED_REVIEW"


class ContributionEvent(OpenCredModel):
    """A factual contribution interaction recorded for a contributor."""

    subject: str
    repo: RepoId
    kind: ContributionEventKind
    occurred_at: datetime

    @field_validator("subject", mode="before")
    @classmethod
    def _validate_subject(cls, v: Any) -> Any:
        return _normalize_login(v)


class PullRequestRecord(OpenCredModel):
    """Record of a pull request under assessment."""

    repo: RepoId
    number: int = Field(ge=1, description="Pull request number (>= 1)")
    author: str
    opened_at: datetime
    title: str
    body: str
    changed_files: list[str]
    normalized_diff: str
    linked_issue_numbers: list[int]
    external_links: list[str]

    @field_validator("author", mode="before")
    @classmethod
    def _validate_author(cls, v: Any) -> Any:
        return _normalize_login(v)


__all__ = [
    "Assertion",
    "AssertionKind",
    "ContributionEvent",
    "ContributionEventKind",
    "OpenCredModel",
    "PullRequestRecord",
    "RepoId",
    "TrustEdge",
    "to_canonical_json",
]
