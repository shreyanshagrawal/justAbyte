"""Unit tests for OpenCred core data models and validation."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from opencred.core.models import (
    Assertion,
    AssertionKind,
    ContributionEvent,
    ContributionEventKind,
    PullRequestRecord,
    RepoId,
    TrustEdge,
    to_canonical_json,
)


class TestRepoId:
    """Tests for RepoId validation and normalization."""

    def test_valid_repo_id(self) -> None:
        r1 = RepoId("ghostty-org/ghostty")
        assert r1 == "ghostty-org/ghostty"
        assert isinstance(r1, str)

        r2 = RepoId("Pallets/Flask")
        # Hand-calculated expectation: case normalized to lowercase
        assert r2 == "pallets/flask"

        r3 = RepoId("my_org/repo.name-1")
        assert r3 == "my_org/repo.name-1"

    @pytest.mark.parametrize(
        "invalid_input",
        [
            "",
            "just-repo-name",
            "/no-owner",
            "no-repo/",
            "owner/repo/extra",
            "owner//repo",
            "   ",
        ],
    )
    def test_invalid_repo_id(self, invalid_input: str) -> None:
        with pytest.raises(ValueError, match="Invalid RepoId format"):
            RepoId(invalid_input)


class TestTrustEdgeRangeAndConstraints:
    """Boundary and constraint tests for TrustEdge."""

    def test_weight_boundaries(self) -> None:
        # Lower boundary: 0.0 is valid
        edge_zero = TrustEdge(source=RepoId("a/b"), target=RepoId("c/d"), weight=0.0)
        assert edge_zero.weight == 0.0

        # Upper boundary: 1.0 is valid
        edge_one = TrustEdge(source=RepoId("a/b"), target=RepoId("c/d"), weight=1.0)
        assert edge_one.weight == 1.0

        # Just outside lower boundary: -0.001 is invalid
        with pytest.raises(ValidationError) as exc_info:
            TrustEdge(source=RepoId("a/b"), target=RepoId("c/d"), weight=-0.001)
        assert "greater than or equal to 0" in str(exc_info.value)

        # Just outside upper boundary: 1.001 is invalid
        with pytest.raises(ValidationError) as exc_info:
            TrustEdge(source=RepoId("a/b"), target=RepoId("c/d"), weight=1.001)
        assert "less than or equal to 1" in str(exc_info.value)

    def test_self_loop_rejection(self) -> None:
        # Same repo exact string
        with pytest.raises(ValidationError, match="Self-loop trust edges are not allowed"):
            TrustEdge(source=RepoId("ghostty/repo"), target=RepoId("ghostty/repo"), weight=0.5)

        # Same repo different casing (RepoId normalizes to lowercase)
        with pytest.raises(ValidationError, match="Self-loop trust edges are not allowed"):
            TrustEdge(source=RepoId("ghostty/repo"), target=RepoId("GHOSTTY/REPO"), weight=0.8)


class TestAssertionRangeAndConstraints:
    """Boundary and constraint tests for Assertion."""

    def test_strength_boundaries(self) -> None:
        # Lower boundary: 0.0 is valid
        a_zero = Assertion(
            origin=RepoId("a/b"),
            subject="contributor",
            kind=AssertionKind.VOUCH,
            strength=0.0,
        )
        assert a_zero.strength == 0.0

        # Upper boundary: 1.0 is valid
        a_one = Assertion(
            origin=RepoId("a/b"),
            subject="contributor",
            kind=AssertionKind.VOUCH,
            strength=1.0,
        )
        assert a_one.strength == 1.0

        # Just outside lower boundary: -0.001 is invalid
        with pytest.raises(ValidationError) as exc_info:
            Assertion(
                origin=RepoId("a/b"),
                subject="contributor",
                kind=AssertionKind.VOUCH,
                strength=-0.001,
            )
        assert "greater than or equal to 0" in str(exc_info.value)

        # Just outside upper boundary: 1.001 is invalid
        with pytest.raises(ValidationError) as exc_info:
            Assertion(
                origin=RepoId("a/b"),
                subject="contributor",
                kind=AssertionKind.VOUCH,
                strength=1.001,
            )
        assert "less than or equal to 1" in str(exc_info.value)

    def test_line_number_boundaries(self) -> None:
        # None is valid
        a_none = Assertion(
            origin=RepoId("a/b"),
            subject="contributor",
            kind=AssertionKind.VOUCH,
            strength=0.5,
            line_number=None,
        )
        assert a_none.line_number is None

        # Lower boundary: 1 is valid (1-based line number)
        a_one = Assertion(
            origin=RepoId("a/b"),
            subject="contributor",
            kind=AssertionKind.VOUCH,
            strength=0.5,
            line_number=1,
        )
        assert a_one.line_number == 1

        # Just outside lower boundary: 0 is invalid
        with pytest.raises(ValidationError) as exc_info:
            Assertion(
                origin=RepoId("a/b"),
                subject="contributor",
                kind=AssertionKind.VOUCH,
                strength=0.5,
                line_number=0,
            )
        assert "greater than or equal to 1" in str(exc_info.value)

        # Negative number: -1 is invalid
        with pytest.raises(ValidationError) as exc_info:
            Assertion(
                origin=RepoId("a/b"),
                subject="contributor",
                kind=AssertionKind.VOUCH,
                strength=0.5,
                line_number=-1,
            )
        assert "greater than or equal to 1" in str(exc_info.value)


class TestPullRequestRecordBoundaries:
    """Boundary tests for PullRequestRecord."""

    def test_pr_number_boundaries(self) -> None:
        now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)

        # Lower boundary: 1 is valid
        pr = PullRequestRecord(
            repo=RepoId("owner/repo"),
            number=1,
            author="alice",
            opened_at=now,
            title="Fix bug",
            body="Description",
            changed_files=["src/main.py"],
            normalized_diff="--- a\n+++ b",
            linked_issue_numbers=[10],
            external_links=[],
        )
        assert pr.number == 1

        # Just outside lower boundary: 0 is invalid
        with pytest.raises(ValidationError) as exc_info:
            PullRequestRecord(
                repo=RepoId("owner/repo"),
                number=0,
                author="alice",
                opened_at=now,
                title="Fix bug",
                body="Description",
                changed_files=[],
                normalized_diff="",
                linked_issue_numbers=[],
                external_links=[],
            )
        assert "greater than or equal to 1" in str(exc_info.value)


class TestLoginNormalization:
    """Tests that usernames/logins are trimmed and normalized to lowercase."""

    def test_assertion_subject_normalization(self) -> None:
        a1 = Assertion(
            origin=RepoId("a/b"),
            subject="AliceSmith",
            kind=AssertionKind.VOUCH,
            strength=1.0,
        )
        assert a1.subject == "alicesmith"

        a2 = Assertion(
            origin=RepoId("a/b"),
            subject="  @BobJones  ",
            kind=AssertionKind.DENOUNCE,
            strength=0.9,
        )
        assert a2.subject == "bobjones"

    def test_assertion_empty_subject_rejected(self) -> None:
        with pytest.raises(ValidationError, match="Contributor login cannot be empty"):
            Assertion(
                origin=RepoId("a/b"),
                subject="   @   ",
                kind=AssertionKind.VOUCH,
                strength=1.0,
            )

    def test_contribution_event_subject_normalization(self) -> None:
        now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
        ev = ContributionEvent(
            subject="  @CharlieBrown ",
            repo=RepoId("x/y"),
            kind=ContributionEventKind.MERGED,
            occurred_at=now,
        )
        assert ev.subject == "charliebrown"

    def test_pull_request_author_normalization(self) -> None:
        now = datetime(2026, 11, 1, 12, 0, 0, tzinfo=UTC)
        pr = PullRequestRecord(
            repo=RepoId("owner/repo"),
            number=42,
            author="@Dave_Developer",
            opened_at=now,
            title="Add feature",
            body="Details",
            changed_files=[],
            normalized_diff="",
            linked_issue_numbers=[],
            external_links=[],
        )
        assert pr.author == "dave_developer"


class TestCanonicalSerializationAndDeterminism:
    """Tests for canonical byte-deterministic JSON serialization."""

    def test_trust_edge_serialization_independent_of_construction_order(self) -> None:
        # Construct with args in different keyword order
        e1 = TrustEdge(source=RepoId("org/alpha"), target=RepoId("org/beta"), weight=0.75)
        e2 = TrustEdge(weight=0.75, target=RepoId("org/beta"), source=RepoId("org/alpha"))

        s1 = e1.to_canonical_json()
        s2 = e2.to_canonical_json()
        s3 = to_canonical_json(e1)

        # Hand-calculated expected string with keys sorted alphabetically
        expected = '{"source":"org/alpha","target":"org/beta","weight":0.75}'
        assert s1 == expected
        assert s2 == expected
        assert s3 == expected
        assert s1 == s2

    def test_assertion_serialization_independent_of_construction_order(self) -> None:
        a1 = Assertion(
            origin=RepoId("org/repo"),
            subject="alice",
            kind=AssertionKind.VOUCH,
            strength=0.9,
            line_number=12,
        )
        a2 = Assertion(
            strength=0.9,
            line_number=12,
            kind=AssertionKind.VOUCH,
            origin=RepoId("org/repo"),
            subject="alice",
        )

        # Hand-calculated expected string with keys sorted alphabetically:
        # kind, line_number, origin, strength, subject
        expected = (
            '{"kind":"VOUCH","line_number":12,"origin":"org/repo","strength":0.9,"subject":"alice"}'
        )
        assert a1.to_canonical_json() == expected
        assert a2.to_canonical_json() == expected
        assert a1.to_canonical_json() == a2.to_canonical_json()

    def test_frozen_immutability(self) -> None:
        edge = TrustEdge(source=RepoId("a/b"), target=RepoId("c/d"), weight=0.5)
        with pytest.raises(ValidationError):
            # Attempting to mutate a frozen model raises ValidationError
            edge.weight = 0.9  # type: ignore[misc]
