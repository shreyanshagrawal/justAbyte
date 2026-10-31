"""Newcomer detection and fairness guarantees.

Implements AGENTS.md rule 6:
- Missing data is NOT negative evidence.
- A contributor with no history and no network assertions gets network_trust = 0,
  campaign_risk = 0 (unless campaign evidence exists), and triage NEWCOMER or UNCERTAIN,
  never a negative label.
"""

from collections.abc import Sequence

from opencred.core.models import ContributionEvent, ContributionEventKind


def is_newcomer(
    subject_history: Sequence[ContributionEvent],
    network_assertions_count: int,
) -> bool:
    """Determine whether a contributor is classified as a newcomer.

    A contributor is classified as a newcomer when:
    1. They have zero merged contributions in observed history.
    2. They have zero network assertions of any kind (neither vouches nor denouncements).

    Non-merged events (such as CLOSED_UNMERGED or review interactions) do NOT
    disqualify a subject from newcomer status as long as no contributions were merged.

    Args:
        subject_history: Observed contribution interactions for the contributor.
        network_assertions_count: Total number of network assertions (vouches + denouncements).

    Returns:
        True if the contributor has no merged history and no network assertions; False otherwise.

    Raises:
        ValueError: If network_assertions_count is negative.
    """
    if network_assertions_count < 0:
        raise ValueError(
            f"network_assertions_count must be non-negative, got {network_assertions_count}"
        )

    if network_assertions_count > 0:
        return False

    has_merged = any(event.kind == ContributionEventKind.MERGED for event in subject_history)
    return not has_merged


__all__ = ["is_newcomer"]
