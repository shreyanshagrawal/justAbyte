"""Unit tests for OpenCred manifest parsing and Trustdown compatibility."""

from pathlib import Path

from opencred.core.manifests import parse_manifest
from opencred.core.models import AssertionKind, RepoId, TrustEdge

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "manifests"


class TestPlainManifestParsing:
    """Tests for parsing plain Vouch-style manifests without directives."""

    def test_plain_valid_manifest(self) -> None:
        fixture_path = FIXTURES_DIR / "plain_valid.td"
        content = fixture_path.read_text(encoding="utf-8")
        owner = RepoId("my-org/my-repo")

        result = parse_manifest(content, owner=owner)

        # Hand-calculated expectation: 5 assertions, 0 trust edges, 0 errors, 0 warnings
        # Sorted deterministically by subject then kind
        assert len(result.errors) == 0
        assert len(result.warnings) == 0
        assert len(result.trust_edges) == 0
        assert len(result.assertions) == 5

        # Expected sorted subjects: alice, badguy, bob, charlie, spammer
        subjects = [a.subject for a in result.assertions]
        assert subjects == ["alice", "badguy", "bob", "charlie", "spammer"]

        # alice: vouched on line 4
        assert result.assertions[0].subject == "alice"
        assert result.assertions[0].kind == AssertionKind.VOUCH
        assert result.assertions[0].strength == 1.0
        assert result.assertions[0].line_number == 4
        assert result.assertions[0].origin == owner

        # badguy: denounced on line 7
        assert result.assertions[1].subject == "badguy"
        assert result.assertions[1].kind == AssertionKind.DENOUNCE
        assert result.assertions[1].strength == 1.0
        assert result.assertions[1].line_number == 7

        # bob: vouched on line 5
        assert result.assertions[2].subject == "bob"
        assert result.assertions[2].kind == AssertionKind.VOUCH
        assert result.assertions[2].line_number == 5

        # charlie: vouched with github prefix on line 6 -> maps to charlie
        assert result.assertions[3].subject == "charlie"
        assert result.assertions[3].kind == AssertionKind.VOUCH
        assert result.assertions[3].line_number == 6

        # spammer: denounced on line 8 with reason
        assert result.assertions[4].subject == "spammer"
        assert result.assertions[4].kind == AssertionKind.DENOUNCE
        assert result.assertions[4].line_number == 8


class TestTrustDirectives:
    """Tests for # @trust-repo directive variants and constraints."""

    def test_directive_variants(self) -> None:
        text = """# OpenCred manifest
# @trust-repo ghostty-org/ghostty weight=0.9
#   @trust-repo   astral-sh/uv   weight=0.8
# @trust-repo pallets/flask weight=0.0
# @trust-repo pydantic/pydantic weight=1.0
"""
        owner = RepoId("my-org/my-repo")
        result = parse_manifest(text, owner=owner)

        assert len(result.errors) == 0
        # Hand-calculated expectation: 4 edges sorted by target repo
        # astral-sh/uv, ghostty-org/ghostty, pallets/flask, pydantic/pydantic
        assert len(result.trust_edges) == 4
        assert result.trust_edges[0] == TrustEdge(
            source=owner, target=RepoId("astral-sh/uv"), weight=0.8
        )
        assert result.trust_edges[1] == TrustEdge(
            source=owner, target=RepoId("ghostty-org/ghostty"), weight=0.9
        )
        assert result.trust_edges[2] == TrustEdge(
            source=owner, target=RepoId("pallets/flask"), weight=0.0
        )
        assert result.trust_edges[3] == TrustEdge(
            source=owner, target=RepoId("pydantic/pydantic"), weight=1.0
        )

    def test_invalid_weights_reported_as_errors(self) -> None:
        text = """# Manifest with invalid weights
# @trust-repo org/repo-a weight=1.001
# @trust-repo org/repo-b weight=-0.01
# @trust-repo org/repo-c weight=not_a_number
# @trust-repo org/repo-d weight=
# @trust-repo org/repo-e wt=0.5
"""
        owner = RepoId("my-org/my-repo")
        result = parse_manifest(text, owner=owner)

        assert len(result.trust_edges) == 0
        assert len(result.errors) == 5

        error_lines = [err[0] for err in result.errors]
        # Hand-calculated expectation: errors on lines 2, 3, 4, 5, 6
        assert error_lines == [2, 3, 4, 5, 6]
        assert "out of bounds" in result.errors[0][1]
        assert "out of bounds" in result.errors[1][1]
        assert "Invalid weight" in result.errors[2][1]
        assert "Invalid weight" in result.errors[3][1]
        assert "Malformed weight parameter" in result.errors[4][1]

    def test_duplicate_directive_for_same_target_is_error(self) -> None:
        text = """# Manifest with duplicate directive
# @trust-repo peer/target weight=0.5
# @trust-repo peer/target weight=0.8
"""
        owner = RepoId("my-org/my-repo")
        result = parse_manifest(text, owner=owner)

        # Duplicate directive must produce an error and no edge
        assert len(result.errors) == 1
        assert result.errors[0][0] == 3
        assert "Duplicate @trust-repo directive" in result.errors[0][1]
        assert len(result.trust_edges) == 0


class TestMalformedLines:
    """Tests that malformed lines are rejected with line numbers and never become assertions."""

    def test_malformed_fixture_reporting(self) -> None:
        fixture_path = FIXTURES_DIR / "malformed_lines.td"
        content = fixture_path.read_text(encoding="utf-8")
        owner = RepoId("my-org/my-repo")

        result = parse_manifest(content, owner=owner)

        # Verify only the valid user at line 12 produced an assertion
        assert len(result.assertions) == 1
        assert result.assertions[0].subject == "valid_user"
        assert result.assertions[0].line_number == 12

        # Hand-calculated expectation: 9 errors on lines 3, 4, 5, 6, 7, 8, 9, 10, 11
        error_lines = [err[0] for err in result.errors]
        assert error_lines == [3, 4, 5, 6, 7, 8, 9, 10, 11]

        # Verify specific error messages
        err_dict = dict(result.errors)
        assert "Invalid target repository" in err_dict[3]
        assert "Weight out of bounds" in err_dict[4]
        assert "Self-loop trust directive not allowed" in err_dict[5]
        assert "Malformed @trust-repo directive" in err_dict[6]
        assert "Invalid weight" in err_dict[7]
        assert "handles must not contain '@'" in err_dict[8]
        assert "username cannot be empty" in err_dict[9]
        assert "platform prefix cannot be empty" in err_dict[10]
        assert "missing handle after '-'" in err_dict[11]


class TestContradictoryAndDuplicateEntries:
    """Tests for contradictory assertions and duplicate collapsing."""

    def test_contradictory_fixture_handling(self) -> None:
        fixture_path = FIXTURES_DIR / "contradictory.td"
        content = fixture_path.read_text(encoding="utf-8")
        owner = RepoId("my-org/my-repo")

        result = parse_manifest(content, owner=owner)

        # Contradictory subjects:
        # bob: vouched on line 4, denounced on line 5
        # charlie: denounced on line 7, vouched on line 8
        # Neither bob nor charlie should have ANY assertion produced!
        subjects_with_assertions = {a.subject for a in result.assertions}
        assert "bob" not in subjects_with_assertions
        assert "charlie" not in subjects_with_assertions

        # Valid assertions:
        # alice: vouched on line 3 and line 6 -> collapsed to 1 assertion (line 3)
        # dave: vouched on line 9 -> 1 assertion
        assert len(result.assertions) == 2
        assert result.assertions[0].subject == "alice"
        assert result.assertions[0].line_number == 3
        assert result.assertions[1].subject == "dave"
        assert result.assertions[1].line_number == 9

        # Warning for duplicate alice declaration on line 6
        assert len(result.warnings) == 1
        assert result.warnings[0][0] == 6
        assert "Duplicate vouch for subject 'alice'" in result.warnings[0][1]

        # Errors for contradictory lines: 4, 5 (for bob) and 7, 8 (for charlie)
        contradictory_error_lines = [err[0] for err in result.errors]
        assert contradictory_error_lines == [4, 5, 7, 8]
        for _, msg in result.errors:
            assert "both vouched and denounced" in msg


class TestCompatibilityWithUpstreamVouch:
    """Compatibility test: OpenCred manifest with directives produces identical

    contributor assertions as the same file with directives removed.
    """

    def test_compatibility_with_and_without_directives(self) -> None:
        with_directives_content = (FIXTURES_DIR / "with_directives.td").read_text(encoding="utf-8")
        upstream_plain_content = (FIXTURES_DIR / "upstream_equivalent.td").read_text(
            encoding="utf-8"
        )
        owner = RepoId("my-org/my-repo")

        res_with = parse_manifest(with_directives_content, owner=owner)
        res_plain = parse_manifest(upstream_plain_content, owner=owner)

        # Ensure no parse errors in either fixture
        assert len(res_with.errors) == 0
        assert len(res_plain.errors) == 0

        # With directives: contains 2 peer trust edges
        assert len(res_with.trust_edges) == 2
        assert len(res_plain.trust_edges) == 0

        # Contributor assertions must match exactly in subject, kind, strength, and origin
        assert len(res_with.assertions) == len(res_plain.assertions)
        for a_with, a_plain in zip(res_with.assertions, res_plain.assertions, strict=True):
            assert a_with.subject == a_plain.subject
            assert a_with.kind == a_plain.kind
            assert a_with.strength == a_plain.strength
            assert a_with.origin == a_plain.origin

    def test_output_ordering_is_stable_across_repeated_calls(self) -> None:
        content = (FIXTURES_DIR / "with_directives.td").read_text(encoding="utf-8")
        owner = RepoId("my-org/my-repo")

        run1 = parse_manifest(content, owner=owner)
        run2 = parse_manifest(content, owner=owner)

        assert run1.to_canonical_json() == run2.to_canonical_json()
        assert run1.assertions == run2.assertions
        assert run1.trust_edges == run2.trust_edges
        assert run1.errors == run2.errors
        assert run1.warnings == run2.warnings

