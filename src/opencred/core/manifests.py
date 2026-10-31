"""Parser for OpenCred trust manifests (.td / Trustdown).

Extends the upstream Vouch file format with peer repository trust directives:
  # @trust-repo <owner>/<repo> weight=<0..1>
while preserving complete backward compatibility with standard Vouch parsers.
"""

import re

from pydantic import Field

from opencred.core.models import (
    Assertion,
    AssertionKind,
    OpenCredModel,
    RepoId,
    TrustEdge,
)

_USERNAME_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
_PLATFORM_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


class ManifestParseResult(OpenCredModel):
    """Result of parsing an OpenCred manifest."""

    assertions: list[Assertion] = Field(
        default_factory=list,
        description="Contributor assertions sorted deterministically by subject then kind",
    )
    trust_edges: list[TrustEdge] = Field(
        default_factory=list,
        description="Peer repository trust edges sorted deterministically by target repo",
    )
    errors: list[tuple[int, str]] = Field(
        default_factory=list,
        description="Fatal syntax or semantic errors with 1-based line numbers",
    )
    warnings: list[tuple[int, str]] = Field(
        default_factory=list,
        description="Non-fatal warnings (such as duplicate entries) with 1-based line numbers",
    )


def parse_manifest(text: str, owner: RepoId | str) -> ManifestParseResult:
    """Parse an OpenCred manifest text from a repository owner.

    Args:
        text: Raw file contents of VOUCHED.td.
        owner: The repository that owns this manifest (the trust origin).

    Returns:
        ManifestParseResult containing validated assertions, trust edges,
        and line-numbered errors/warnings.
    """
    owner_repo = RepoId(owner) if not isinstance(owner, RepoId) else owner

    errors: list[tuple[int, str]] = []
    warnings: list[tuple[int, str]] = []

    seen_directive_targets: dict[RepoId, int] = {}
    conflicted_targets: set[RepoId] = set()
    potential_edges: dict[RepoId, TrustEdge] = {}

    # List of (line_number, normalized_subject, kind)
    raw_contributor_entries: list[tuple[int, str, AssertionKind]] = []

    for line_no, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()

        # 1. Blank lines are ignored
        if not stripped:
            continue

        # 2. Comment lines
        if stripped.startswith("#"):
            comment_body = stripped[1:].strip()
            # Check for peer trust directive: # @trust-repo ...
            is_directive = comment_body == "@trust-repo" or comment_body.startswith(
                ("@trust-repo ", "@trust-repo\t")
            )
            if is_directive:
                _parse_trust_directive(
                    line_no=line_no,
                    raw_directive=comment_body,
                    owner=owner_repo,
                    errors=errors,
                    seen_directive_targets=seen_directive_targets,
                    conflicted_targets=conflicted_targets,
                    potential_edges=potential_edges,
                )
            # Other comment lines are ignored harmlessly per upstream spec
            continue

        # 3. Contributor entries (vouch or denounce)
        _parse_contributor_line(
            line_no=line_no,
            stripped=stripped,
            raw_entries=raw_contributor_entries,
            errors=errors,
        )

    # Remove edges for peer targets that had duplicate directive declarations
    for conflicted in conflicted_targets:
        potential_edges.pop(conflicted, None)

    # 4. Resolve duplicates and contradictions for contributor entries
    final_assertions = _resolve_contributor_entries(
        owner=owner_repo,
        raw_entries=raw_contributor_entries,
        errors=errors,
        warnings=warnings,
    )

    # 5. Deterministic sorting
    final_assertions.sort(key=lambda a: (a.subject, a.kind.value))
    final_edges = list(potential_edges.values())
    final_edges.sort(key=lambda e: e.target)
    errors.sort(key=lambda x: (x[0], x[1]))
    warnings.sort(key=lambda x: (x[0], x[1]))

    return ManifestParseResult(
        assertions=final_assertions,
        trust_edges=final_edges,
        errors=errors,
        warnings=warnings,
    )


def _parse_trust_directive(
    line_no: int,
    raw_directive: str,
    owner: RepoId,
    errors: list[tuple[int, str]],
    seen_directive_targets: dict[RepoId, int],
    conflicted_targets: set[RepoId],
    potential_edges: dict[RepoId, TrustEdge],
) -> None:
    """Parse and validate a '# @trust-repo <owner>/<repo> weight=<0..1>' line."""
    tokens = raw_directive.split()
    if len(tokens) < 3:
        msg = (
            "Malformed @trust-repo directive: expected "
            f"'# @trust-repo <owner>/<repo> weight=<0..1>', got '# {raw_directive}'"
        )
        errors.append((line_no, msg))
        return

    if len(tokens) > 3:
        msg = f"Malformed @trust-repo directive: unexpected extra arguments in '# {raw_directive}'"
        errors.append((line_no, msg))
        return

    target_str = tokens[1]
    weight_str = tokens[2]

    # Validate target repository format
    try:
        target_repo = RepoId(target_str)
    except (ValueError, TypeError):
        errors.append(
            (
                line_no,
                f"Invalid target repository '{target_str}': must be in 'owner/repo' format",
            )
        )
        return

    # Self-loops prohibited
    if target_repo == owner:
        msg = (
            f"Self-loop trust directive not allowed: target repository '{target_repo}' "
            "matches manifest owner"
        )
        errors.append((line_no, msg))
        return

    # Validate weight parameter
    if not weight_str.startswith("weight="):
        errors.append(
            (
                line_no,
                f"Malformed weight parameter: expected 'weight=<decimal>', got '{weight_str}'",
            )
        )
        return

    raw_weight = weight_str[len("weight=") :]
    try:
        weight_val = float(raw_weight)
    except ValueError:
        errors.append(
            (
                line_no,
                f"Invalid weight '{raw_weight}': must be a decimal in [0.0, 1.0]",
            )
        )
        return

    if not (0.0 <= weight_val <= 1.0):
        errors.append(
            (
                line_no,
                f"Weight out of bounds: {weight_val} must be in [0.0, 1.0]",
            )
        )
        return

    # Duplicate directive check
    if target_repo in seen_directive_targets:
        prev_line = seen_directive_targets[target_repo]
        msg = (
            f"Duplicate @trust-repo directive for repository '{target_repo}' "
            f"(previously declared on line {prev_line})"
        )
        errors.append((line_no, msg))
        conflicted_targets.add(target_repo)
        return

    seen_directive_targets[target_repo] = line_no
    potential_edges[target_repo] = TrustEdge(source=owner, target=target_repo, weight=weight_val)


def _parse_contributor_line(
    line_no: int,
    stripped: str,
    raw_entries: list[tuple[int, str, AssertionKind]],
    errors: list[tuple[int, str]],
) -> None:
    """Parse a single contributor vouch or denounce line."""
    if stripped.startswith("-"):
        is_denounce = True
        rest = stripped[1:].strip()
        if not rest:
            errors.append(
                (line_no, "Malformed entry: missing handle after '-' denouncement prefix")
            )
            return
    else:
        is_denounce = False
        rest = stripped

    # Handle is separated from optional reason/details by whitespace
    parts = rest.split(None, 1)
    handle = parts[0]

    if "@" in handle:
        errors.append((line_no, f"Malformed handle '{handle}': handles must not contain '@'"))
        return

    colon_count = handle.count(":")
    if colon_count > 1:
        errors.append(
            (
                line_no,
                f"Malformed handle '{handle}': expected at most one ':' for platform prefix",
            )
        )
        return

    if colon_count == 1:
        platform_part, username_part = handle.split(":", 1)
        if not platform_part:
            errors.append(
                (line_no, f"Malformed handle '{handle}': platform prefix cannot be empty")
            )
            return
        if not username_part:
            errors.append((line_no, f"Malformed handle '{handle}': username cannot be empty"))
            return
    else:
        platform_part = None
        username_part = handle

    username_norm = username_part.lower()
    if not _USERNAME_PATTERN.match(username_norm):
        errors.append(
            (
                line_no,
                f"Malformed username '{username_part}': contains invalid characters",
            )
        )
        return

    if platform_part is not None:
        platform_norm = platform_part.lower()
        if not _PLATFORM_PATTERN.match(platform_norm):
            errors.append(
                (
                    line_no,
                    f"Malformed platform prefix '{platform_part}': contains invalid characters",
                )
            )
            return
    else:
        platform_norm = "github"

    # Normalize subject: if github, use username directly; otherwise keep platform:username
    subject = username_norm if platform_norm == "github" else f"{platform_norm}:{username_norm}"
    kind = AssertionKind.DENOUNCE if is_denounce else AssertionKind.VOUCH
    raw_entries.append((line_no, subject, kind))


def _resolve_contributor_entries(
    owner: RepoId,
    raw_entries: list[tuple[int, str, AssertionKind]],
    errors: list[tuple[int, str]],
    warnings: list[tuple[int, str]],
) -> list[Assertion]:
    """Group entries by subject, reporting contradictions and collapsing duplicates."""
    by_subject: dict[str, list[tuple[int, AssertionKind]]] = {}
    for line_no, subject, kind in raw_entries:
        by_subject.setdefault(subject, []).append((line_no, kind))

    final_assertions: list[Assertion] = []

    for subject, entries in by_subject.items():
        kinds_present = {kind for _, kind in entries}
        # Contradiction: same subject both vouched and denounced
        if len(kinds_present) > 1:
            for line_no, _kind in entries:
                msg = (
                    f"Contradictory entry on line {line_no}: subject '{subject}' "
                    "is both vouched and denounced in the same manifest"
                )
                errors.append((line_no, msg))
            continue

        # Non-contradictory: create one assertion from the first declaration line
        first_line, single_kind = entries[0]
        final_assertions.append(
            Assertion(
                origin=owner,
                subject=subject,
                kind=single_kind,
                strength=1.0,
                line_number=first_line,
            )
        )

        # Emit warning-level notes for subsequent duplicate declarations
        if len(entries) > 1:
            for dup_line, _ in entries[1:]:
                msg = (
                    f"Duplicate {single_kind.value.lower()} for subject '{subject}' on line "
                    f"{dup_line} (previously declared on line {first_line})"
                )
                warnings.append((dup_line, msg))

    return final_assertions


__all__ = ["ManifestParseResult", "parse_manifest"]
