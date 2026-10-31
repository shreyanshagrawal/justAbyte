"""Corroboration engine for OpenCred network trust signals.

Implements AGENTS.md rule 5:
- Local denouncements count fully at LOCAL_DENOUNCE_WEIGHT without capping.
- A single external origin's denouncement has bounded influence (capped at
  EXTERNAL_SINGLE_DENOUNCE_CAP).
- Severe negative classification requires at least MIN_INDEPENDENT_ORIGINS_FOR_SEVERE
  distinct origin repositories, OR a local denouncement.
- External vouches are never capped by this rule (Rule 4).
- Explainable output strings accompany each applied cap or threshold.
"""

from typing import Any

from pydantic import AliasChoices, Field, model_validator

from opencred.core.config import (
    EXTERNAL_SINGLE_DENOUNCE_CAP,
    LOCAL_DENOUNCE_WEIGHT,
    MIN_INDEPENDENT_ORIGINS_FOR_SEVERE,
    SEVERE_THRESHOLD,
)
from opencred.core.models import Assertion, OpenCredModel, RepoId


class LocalEvidence(OpenCredModel):
    """Local evidence from the evaluating repository's own manifest."""

    has_denouncement: bool = Field(
        default=False,
        validation_alias=AliasChoices("has_denouncement", "denounced"),
        description="Whether the evaluator's own manifest denounces the subject",
    )
    has_vouch: bool = Field(
        default=False,
        validation_alias=AliasChoices("has_vouch", "vouched"),
        description="Whether the evaluator's own manifest vouches for the subject",
    )

    @property
    def denounced(self) -> bool:
        return self.has_denouncement

    @property
    def vouched(self) -> bool:
        return self.has_vouch


class ExternalSignal(OpenCredModel):
    """Aggregated external network signals prior to corroboration."""

    raw_trust: float = Field(
        default=0.0,
        ge=-1.0,
        le=1.0,
        description="Raw propagated network trust in [-1.0, +1.0]",
    )
    denouncing_origins: list[RepoId] = Field(
        default_factory=list,
        description="Origin repositories that denounced the subject (may include relayed copies)",
    )
    vouching_origins: list[RepoId] = Field(
        default_factory=list,
        description="Origin repositories that vouched for the subject",
    )

    @model_validator(mode="before")
    @classmethod
    def _normalize_assertions(cls, data: Any) -> Any:
        """Allow callers to pass 'denouncements' or 'vouches' lists of Assertion or RepoId."""
        if isinstance(data, dict):
            if "denouncements" in data and "denouncing_origins" not in data:
                raw_denounces = data.pop("denouncements")
                origins: list[Any] = []
                max_str = 0.0
                for item in raw_denounces:
                    if isinstance(item, Assertion):
                        origins.append(item.origin)
                        max_str = max(max_str, item.strength)
                    else:
                        origins.append(item)
                        max_str = 1.0
                data["denouncing_origins"] = origins
                if "raw_trust" not in data and max_str > 0:
                    data["raw_trust"] = -max_str

            if "vouches" in data and "vouching_origins" not in data:
                raw_vouches = data.pop("vouches")
                origins = []
                max_str = 0.0
                for item in raw_vouches:
                    if isinstance(item, Assertion):
                        origins.append(item.origin)
                        max_str = max(max_str, item.strength)
                    else:
                        origins.append(item)
                        max_str = 1.0
                data["vouching_origins"] = origins
                if "raw_trust" not in data and max_str > 0:
                    data["raw_trust"] = max_str
        return data


class CorroboratedSignal(OpenCredModel):
    """Corroborated network trust signal with explainability notes."""

    network_trust: float = Field(
        ge=-1.0,
        le=1.0,
        description="Final corroborated network trust score in [-1.0, +1.0]",
    )
    is_severe: bool = Field(
        description="Whether negative trust meets the severe threshold for triage",
    )
    notes: list[str] = Field(
        default_factory=list,
        description="Explainability notes detailing caps and thresholds applied",
    )
    independent_denounce_count: int = Field(
        default=0,
        ge=0,
        description="Count of distinct origin repositories denouncing the subject",
    )

    @property
    def effective_trust(self) -> float:
        return self.network_trust


def apply_corroboration(local: LocalEvidence, external: ExternalSignal) -> CorroboratedSignal:
    """Apply corroboration and bounded-influence rules to local and external evidence.

    Rules:
        1. Local denouncements count fully at LOCAL_DENOUNCE_WEIGHT without capping.
        2. External denouncements are capped at EXTERNAL_SINGLE_DENOUNCE_CAP when only
           one independent origin has denounced the subject.
        3. A 'severe' classification requires at least MIN_INDEPENDENT_ORIGINS_FOR_SEVERE
           independent origins denouncing the subject, OR a local denouncement.
        4. External vouches are not capped.
        5. Output includes explainability notes for every applied rule.
    """
    notes: list[str] = []

    # Rule 1: Local denouncements from evaluator's own manifest count fully
    if local.has_denouncement:
        local_trust = -1.0 * LOCAL_DENOUNCE_WEIGHT
        notes.append(
            f"Local denouncement from evaluator manifest counts fully at weight "
            f"{LOCAL_DENOUNCE_WEIGHT:.1f} without capping."
        )
        notes.append("Severe classification triggered by local denouncement.")
        return CorroboratedSignal(
            network_trust=local_trust,
            is_severe=True,
            notes=notes,
            independent_denounce_count=0,
        )

    # Deduplicate external denouncing origins (Rule 4 of AGENTS.md: origin deduplication)
    distinct_denounce_origins = sorted(list(set(external.denouncing_origins)))
    independent_count = len(distinct_denounce_origins)
    total_denounce_copies = len(external.denouncing_origins)

    if total_denounce_copies > independent_count:
        relayed = total_denounce_copies - independent_count
        notes.append(
            f"Deduplicated {total_denounce_copies} external denouncement(s) down to "
            f"{independent_count} independent origin(s) ({relayed} relayed duplicate(s) ignored)."
        )

    raw_trust = external.raw_trust
    corroborated_trust: float

    # Evaluate negative trust (external denouncements)
    if raw_trust < 0.0 or independent_count > 0:
        if independent_count == 1:
            # Rule 2: Capped at EXTERNAL_SINGLE_DENOUNCE_CAP for a single origin
            origin_name = str(distinct_denounce_origins[0])
            cap_limit = -EXTERNAL_SINGLE_DENOUNCE_CAP
            if raw_trust < cap_limit:
                corroborated_trust = cap_limit
                notes.append(
                    f"External denouncement capped from {raw_trust:.2f} to magnitude "
                    f"{EXTERNAL_SINGLE_DENOUNCE_CAP:.2f} because only 1 independent origin "
                    f"('{origin_name}') denounced the subject."
                )
            else:
                corroborated_trust = raw_trust
                notes.append(
                    f"External denouncement magnitude {abs(raw_trust):.2f} is within "
                    f"single-origin cap {EXTERNAL_SINGLE_DENOUNCE_CAP:.2f}."
                )
        elif independent_count >= MIN_INDEPENDENT_ORIGINS_FOR_SEVERE:
            # Corroborated by multiple independent origins
            corroborated_trust = raw_trust
            origins_str = ", ".join(f"'{o}'" for o in distinct_denounce_origins)
            notes.append(
                f"External denouncements corroborated by {independent_count} independent "
                f"origins ({origins_str}); single-origin cap does not apply."
            )
        else:
            # Negative trust without specified origins: apply single-origin cap
            corroborated_trust = max(raw_trust, -EXTERNAL_SINGLE_DENOUNCE_CAP)
            notes.append(
                f"External negative trust capped to {corroborated_trust:.2f} (single-origin cap)."
            )

    # Evaluate positive trust (external vouches)
    elif raw_trust > 0.0:
        # Rule 4: External vouches are not capped
        corroborated_trust = raw_trust
        vouch_count = len(set(external.vouching_origins)) or 1
        notes.append(
            f"External vouch accepted without capping from {vouch_count} origin(s) "
            f"(trust: {corroborated_trust:.2f})."
        )

    # Neutral / no external signal
    else:
        if local.has_vouch:
            corroborated_trust = 1.0
            notes.append("Local vouch from evaluator manifest counts fully (+1.0).")
        else:
            corroborated_trust = 0.0
            notes.append(
                "No local or external trust assertions observed; default neutral score (0.0)."
            )

    # Rule 3: Severe classification check
    is_severe: bool
    origins_sufficient = independent_count >= MIN_INDEPENDENT_ORIGINS_FOR_SEVERE
    reaches_threshold = corroborated_trust <= SEVERE_THRESHOLD

    if origins_sufficient and reaches_threshold:
        is_severe = True
        notes.append(
            f"Severe classification met: {independent_count} independent origins "
            f"(>= {MIN_INDEPENDENT_ORIGINS_FOR_SEVERE}) and trust {corroborated_trust:.2f} "
            f"meets severe threshold ({SEVERE_THRESHOLD:.2f})."
        )
    elif independent_count >= MIN_INDEPENDENT_ORIGINS_FOR_SEVERE:
        is_severe = False
        notes.append(
            f"Severe classification not met: {independent_count} independent origins denounced, "
            f"but trust {corroborated_trust:.2f} does not reach severe threshold "
            f"({SEVERE_THRESHOLD:.2f})."
        )
    else:
        is_severe = False
        if independent_count > 0:
            notes.append(
                f"Severe classification not met: requires at least "
                f"{MIN_INDEPENDENT_ORIGINS_FOR_SEVERE} independent origins "
                f"(found {independent_count})."
            )

    return CorroboratedSignal(
        network_trust=corroborated_trust,
        is_severe=is_severe,
        notes=notes,
        independent_denounce_count=independent_count,
    )


__all__ = [
    "CorroboratedSignal",
    "ExternalSignal",
    "LocalEvidence",
    "apply_corroboration",
]
