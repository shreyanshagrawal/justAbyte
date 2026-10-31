"""Unit tests for contribution quality evidence evaluation."""

import math
from datetime import UTC, datetime

import pytest

from opencred.core.config import QUALITY_TRIVIAL_PR_CAP
from opencred.core.models import (
    ContributionEvent,
    ContributionEventKind,
    PullRequestRecord,
    RepoId,
)
from opencred.core.quality import contribution_quality_evidence


@pytest.fixture
def base_focused_pr() -> PullRequestRecord:
    """A focused PR with an issue link, non-trivial changed files, and non-boilerplate content."""
    return PullRequestRecord(
        repo=RepoId("pallets/flask"),
        number=101,
        author="alice",
        opened_at=datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC),
        title="Fix off-by-one error in routing parser",
        body="Resolves an edge case where trailing slashes produced incorrect endpoint matches.",
        changed_files=["src/flask/routing.py", "tests/test_routing.py"],
        normalized_diff="@@ -42,3 +42,3 @@\n- old_logic\n+ fixed_logic",
        linked_issue_numbers=[42],
        external_links=[],
    )


class TestContributionQualityEvidence:
    """Tests for positive contribution quality evidence heuristics."""

    @pytest.mark.fairness
    def test_case_1_focused_pr_with_issue_link_and_no_history(
        self, base_focused_pr: PullRequestRecord
    ) -> None:
        """Case 1: A focused PR with an issue link and no history.

        HAND-CALCULATED VALUE:
        -------------------------------------------------------------------------
        Component 1 (Issue link):           +0.25 (pr.linked_issue_numbers = [42])
        Component 2 (Non-trivial files):    +0.25 (files: routing.py, test_routing.py)
        Component 3 (Descriptive content):  +0.25 (non-boilerplate title and body)
        Component 4 (History):              +0.00 (empty subject_history)
        Trivial PR cap:                     Not applied (files are non-trivial)

        Expected value = 0.25 + 0.25 + 0.25 + 0.00 = 0.75
        -------------------------------------------------------------------------
        """
        result = contribution_quality_evidence(base_focused_pr, subject_history=[])

        # Hand-calculated expectation: exactly 0.75
        assert result.value == pytest.approx(0.75)

        # Check concrete explainability reasons
        assert any("PR links to 1 issue(s): [42]" in r for r in result.reasons)
        assert any("PR modifies 2 non-trivial file(s)" in r for r in result.reasons)
        assert any("descriptive title and non-boilerplate description" in r for r in result.reasons)
        assert any("neutral +0.00" in r for r in result.reasons)

    @pytest.mark.fairness
    def test_case_2_same_pr_with_three_merged_events(
        self, base_focused_pr: PullRequestRecord
    ) -> None:
        """Case 2: The same focused PR with 3 merged events.

        HAND-CALCULATED VALUE:
        -------------------------------------------------------------------------
        Base PR heuristics (Components 1, 2, 3):
            0.25 + 0.25 + 0.25 = 0.75

        Component 4 (History with 3 merged PRs, k = 5.0):
            merged_count = 3
            k = 5.0
            saturation factor = 1 - exp(-3 / 5)
                              = 1 - exp(-0.6)
                              = 1 - 0.548811636094...
                              = 0.4511883639059736
            history contribution = weight_history * saturation factor
                                 = 0.25 * 0.4511883639059736
                                 = 0.1127970909764934

        Total Expected Value = 0.75 + 0.1127970909764934
                             = 0.8627970909764934
                             ~= 0.862797
        -------------------------------------------------------------------------
        """
        now = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
        merged_history = [
            ContributionEvent(
                subject="alice",
                repo=RepoId("pallets/flask"),
                kind=ContributionEventKind.MERGED,
                occurred_at=now,
            ),
            ContributionEvent(
                subject="alice",
                repo=RepoId("pallets/werkzeug"),
                kind=ContributionEventKind.MERGED,
                occurred_at=now,
            ),
            ContributionEvent(
                subject="alice",
                repo=RepoId("pallets/click"),
                kind=ContributionEventKind.MERGED,
                occurred_at=now,
            ),
        ]

        result = contribution_quality_evidence(base_focused_pr, subject_history=merged_history)

        # Expected value hand-calculated: 0.75 + 0.25 * (1 - exp(-0.6))
        expected_saturation = 1.0 - math.exp(-3.0 / 5.0)
        expected_value = 0.75 + (0.25 * expected_saturation)

        assert result.value == pytest.approx(expected_value)
        assert result.value == pytest.approx(0.862797, abs=1e-5)

        # Higher than Case 1
        assert result.value > 0.75

        # Check explainability reasons
        assert any("contains 3 merged PR(s)" in r for r in result.reasons)

    @pytest.mark.fairness
    def test_case_3_pr_with_only_lockfile_changes_capped_at_maximum(self) -> None:
        """Case 3: A PR with only lockfile changes is capped at the configured maximum.

        HAND-CALCULATED VALUE:
        -------------------------------------------------------------------------
        Component 1 (Issue link):           +0.25 (linked_issue_numbers = [99])
        Component 2 (Files):                +0.00 (solely package-lock.json)
        Component 3 (Descriptive content):  +0.25 (descriptive title and body)
        Raw sum = 0.25 + 0.00 + 0.25 = 0.50

        Trivial-PR penalty:
            Changed files are solely low-value lockfiles.
            Score is capped at QUALITY_TRIVIAL_PR_CAP = 0.15.

        Expected value = 0.15
        -------------------------------------------------------------------------
        """
        lockfile_pr = PullRequestRecord(
            repo=RepoId("frontend/app"),
            number=202,
            author="bob",
            opened_at=datetime(2026, 11, 1, 10, 0, 0, tzinfo=UTC),
            title="Update dependencies lockfile",
            body="Bump lockfile dependencies following security advisory patch.",
            changed_files=["package-lock.json"],
            normalized_diff="@@ -10,3 +10,3 @@\n- old_dep 1.0\n+ new_dep 1.1",
            linked_issue_numbers=[99],
            external_links=[],
        )

        result = contribution_quality_evidence(lockfile_pr, subject_history=[])

        # Hand-calculated expectation: exactly QUALITY_TRIVIAL_PR_CAP (0.15)
        assert result.value == pytest.approx(QUALITY_TRIVIAL_PR_CAP)
        assert result.value == pytest.approx(0.15)

        # Check cap reason string
        assert any("Trivial-PR cap applied" in r for r in result.reasons)
        assert any("capping evidence from 0.5000 to 0.15" in r for r in result.reasons)

    @pytest.mark.fairness
    def test_closed_unmerged_event_leaves_score_unchanged(
        self, base_focused_pr: PullRequestRecord
    ) -> None:
        """A plain CLOSED_UNMERGED event does NOT reduce or alter the score."""
        res_no_history = contribution_quality_evidence(base_focused_pr, subject_history=[])

        now = datetime(2026, 10, 15, 12, 0, 0, tzinfo=UTC)
        unmerged_history = [
            ContributionEvent(
                subject="alice",
                repo=RepoId("pallets/flask"),
                kind=ContributionEventKind.CLOSED_UNMERGED,
                occurred_at=now,
            ),
            ContributionEvent(
                subject="alice",
                repo=RepoId("pallets/flask"),
                kind=ContributionEventKind.CLOSED_UNMERGED,
                occurred_at=now,
            ),
        ]

        res_with_unmerged = contribution_quality_evidence(
            base_focused_pr, subject_history=unmerged_history
        )

        # Score remains identical: CLOSED_UNMERGED does not penalize
        assert res_with_unmerged.value == pytest.approx(res_no_history.value)
        assert res_with_unmerged.value == pytest.approx(0.75)
