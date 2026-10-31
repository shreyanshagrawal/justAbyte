"""End-to-end integration tests for OpenCred assessment pipeline.

All tests utilize hand-written scenario fixtures from tests/fixtures/scenarios/
and document hand-calculated expected values in test comments in strict
compliance with AGENTS.md rules.
"""

from datetime import UTC, datetime
from pathlib import Path

from opencred.core.assessment import Assessment, assess
from opencred.core.config import (
    EXTERNAL_SINGLE_DENOUNCE_CAP,
    QUALITY_FAIR_THRESHOLD,
)
from opencred.core.models import (
    ContributionEvent,
    ContributionEventKind,
    PullRequestRecord,
    RepoId,
)
from opencred.core.quality import QualityConfig
from opencred.core.telemetry import (
    TelemetryEntry,
    TelemetryLoadResult,
    TelemetryStatus,
)
from opencred.core.triage import TriageOutcome

FIXTURES_DIR = Path(__file__).parent.parent / "fixtures" / "scenarios"


def _read_fixture(filename: str) -> str:
    """Read scenario fixture file contents."""
    path = FIXTURES_DIR / filename
    return path.read_text(encoding="utf-8")


def _make_pr(
    repo: str = "evaluator/repo",
    number: int = 1,
    author: str = "newbie",
    title: str = "Implement auth helper",
    body: str = "Resolves issue #42 by implementing auth helper routines.",
    changed_files: list[str] | None = None,
    normalized_diff: str = "+ def helper(): return True",
    linked_issue_numbers: list[int] | None = None,
) -> PullRequestRecord:
    """Helper to construct a valid PullRequestRecord."""
    return PullRequestRecord(
        repo=RepoId(repo),
        number=number,
        author=author,
        opened_at=datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC),
        title=title,
        body=body,
        changed_files=changed_files or ["src/auth.py"],
        normalized_diff=normalized_diff,
        linked_issue_numbers=linked_issue_numbers or [42],
        external_links=[],
    )


def test_newcomer_focused_pr_fair_review() -> None:
    """Newcomer with a focused PR, no history, and no campaign -> NEWCOMER_FAIR_REVIEW,
    network_trust 0.0.

    Hand-calculated expected values:
    --------------------------------
    1. Input:
       - Contributor 'newbie' has 0 merged events in history.
       - Base manifests contain 0 assertions about 'newbie'.
       - Peer manifests contain 0 assertions about 'newbie'.
       - total_network_assertions = 0 -> is_newcomer is True.
    2. Quality:
       - Issue link present (0.25).
       - Non-trivial file 'src/auth.py' (0.25).
       - Descriptive title & body (0.25).
       - History = 0 -> saturating term = 0.0.
       - Quality score = 0.75 >= QUALITY_FAIR_THRESHOLD (0.50).
    3. Network Trust:
       - Local assertions = 0, external assertions = 0 -> raw_trust = 0.0.
       - Corroborated network_trust = 0.0.
    4. Campaign Risk:
       - No active candidate -> campaign_risk = 0.0 < CAMPAIGN_LOW_THRESHOLD (0.3).
    5. Triage:
       - is_newcomer is True, campaign_risk is low, quality >= 0.50.
       - Rule 3 matches -> NEWCOMER_FAIR_REVIEW.
    """
    evaluator = RepoId("evaluator/repo")
    pr = _make_pr(repo=str(evaluator), author="newbie")
    base_manifests = {evaluator: _read_fixture("evaluator.td")}
    peer_manifests = {RepoId("peer/trusted"): _read_fixture("peer_trusted.td")}

    result: Assessment = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests=peer_manifests,
        telemetry={},
        history=[],
    )

    assert result.network_trust == 0.0
    assert result.campaign_risk == 0.0
    assert result.contribution_quality_evidence >= QUALITY_FAIR_THRESHOLD
    assert result.triage == TriageOutcome.NEWCOMER_FAIR_REVIEW
    assert any("fair first-time review" in r for r in result.reasons)
    assert any("telemetry is absent" in n for n in result.notes)


def test_established_contributor_vouched_by_direct_trusted_repo() -> None:
    """Established contributor vouched by a direct trusted repo -> NORMAL_REVIEW.

    Hand-calculated expected values:
    --------------------------------
    1. Graph & Propagation:
       - Evaluator -> peer/trusted with weight 1.0 (1 hop).
       - peer/trusted has '@vouch established_contributor strength=1.0'.
       - Path weight = 1.0 * 1.0 = 1.0.
       - External signal value = +1.0.
       - Corroborated network_trust = 1.0.
    2. Quality:
       - 3 merged history events boost quality evidence.
    3. Campaign Risk:
       - 0.0.
    4. Triage:
       - network_trust = 1.0 >= TRUST_NORMAL_THRESHOLD (0.3), campaign_risk low.
       - Rule 6 matches -> NORMAL_REVIEW.
    5. Sources:
       - 'peer/trusted (1 hop)'.
    """
    evaluator = RepoId("evaluator/repo")
    pr = _make_pr(repo=str(evaluator), author="established_contributor")
    base_manifests = {evaluator: _read_fixture("evaluator.td")}
    peer_manifests = {RepoId("peer/trusted"): _read_fixture("peer_trusted.td")}

    history = [
        ContributionEvent(
            subject="established_contributor",
            repo=evaluator,
            kind=ContributionEventKind.MERGED,
            occurred_at=datetime(2026, 9, 1, 10, 0, 0, tzinfo=UTC),
        )
        for _ in range(3)
    ]

    result: Assessment = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests=peer_manifests,
        telemetry={},
        history=history,
    )

    assert result.network_trust == 1.0
    assert result.campaign_risk == 0.0
    assert result.triage == TriageOutcome.NORMAL_REVIEW
    assert "peer/trusted (1 hop)" in result.sources


def test_contributor_denounced_by_one_external_repo_capped_not_severe() -> None:
    """Contributor denounced by one external repo only -> capped, not SEVERE.

    Hand-calculated expected values:
    --------------------------------
    1. Input:
       - Evaluator trusts peer/denounce_a at weight 1.0.
       - peer/denounce_a declares '@denounce bad_actor strength=1.0'.
       - Single independent origin ('peer/denounce_a').
    2. Corroboration:
       - Raw trust = -1.0.
       - Single external denouncement capped at EXTERNAL_SINGLE_DENOUNCE_CAP (0.2).
       - Corroborated network_trust = -0.2.
       - is_severe = False (requires >= 2 independent origins).
    3. Triage:
       - network_trust = -0.2 < 0.0, is_severe = False, campaign_risk = 0.0.
       - Rule 7 matches -> REVIEW_REPUTATION_EVIDENCE (not severe).
    """
    evaluator = RepoId("evaluator/repo")
    pr = _make_pr(repo=str(evaluator), author="bad_actor")
    base_manifests = {evaluator: _read_fixture("evaluator.td")}
    peer_manifests = {
        RepoId("peer/denounce_a"): _read_fixture("peer_denounce_single.td"),
    }

    result: Assessment = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests=peer_manifests,
        telemetry={},
        history=[],
    )

    assert result.network_trust == -EXTERNAL_SINGLE_DENOUNCE_CAP
    assert result.triage == TriageOutcome.REVIEW_REPUTATION_EVIDENCE
    # Verify reason is non-severe (does not claim severe consensus)
    assert not any("Severe" in r for r in result.reasons)
    assert any("Single-origin cap" in n or "capped" in n for n in result.notes)


def test_contributor_denounced_by_two_independent_repos_severe() -> None:
    """Contributor denounced by two independent repos -> severe, REVIEW_REPUTATION_EVIDENCE.

    Hand-calculated expected values:
    --------------------------------
    1. Input:
       - Evaluator trusts peer/denounce_a (1.0) and peer/denounce_b (1.0).
       - peer/denounce_a denounces bad_actor (origin: peer/denounce_a).
       - peer/denounce_b denounces bad_actor (origin: peer/denounce_b).
       - Independent origins = 2 >= MIN_INDEPENDENT_ORIGINS_FOR_SEVERE (2).
    2. Corroboration:
       - Raw trust = -1.0.
       - Single origin cap does NOT apply.
       - network_trust = -1.0 <= -0.6 (SEVERE_THRESHOLD).
       - is_severe = True.
    3. Triage:
       - Rule 5 matches -> REVIEW_REPUTATION_EVIDENCE with independent origin count (2).
    """
    evaluator = RepoId("evaluator/repo")
    pr = _make_pr(repo=str(evaluator), author="bad_actor")
    base_manifests = {evaluator: _read_fixture("evaluator.td")}
    peer_manifests = {
        RepoId("peer/denounce_a"): _read_fixture("peer_denounce_two_a.td"),
        RepoId("peer/denounce_b"): _read_fixture("peer_denounce_two_b.td"),
    }

    result: Assessment = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests=peer_manifests,
        telemetry={},
        history=[],
    )

    assert result.network_trust == -1.0
    assert result.triage == TriageOutcome.REVIEW_REPUTATION_EVIDENCE
    assert any(
        "Severe negative network consensus corroborated across 2" in r for r in result.reasons
    )


def test_relayed_denouncements_from_one_origin_not_severe() -> None:
    """Two denouncements originating from the same origin (relayed) do NOT meet severe requirement.

    Hand-calculated expected values:
    --------------------------------
    1. Input:
       - peer/relay_a has '@denounce bad_actor origin=upstream/central'.
       - peer/relay_b has '@denounce bad_actor origin=upstream/central'.
    2. Origin Deduplication (AGENTS.md Rule 4 & 5):
       - Both assertions originate from 'upstream/central'.
       - Deduplicated down to 1 distinct origin repository ('upstream/central').
       - independent_count = 1 < MIN_INDEPENDENT_ORIGINS_FOR_SEVERE (2).
    3. Corroboration:
       - Capped at magnitude 0.2 -> network_trust = -0.2.
       - is_severe = False.
    4. Triage:
       - Rule 7 (not severe) matches -> REVIEW_REPUTATION_EVIDENCE.
    """
    evaluator = RepoId("evaluator/repo")
    pr = _make_pr(repo=str(evaluator), author="bad_actor")
    base_manifests = {evaluator: _read_fixture("evaluator.td")}
    peer_manifests = {
        RepoId("peer/relay_a"): _read_fixture("peer_relay_a.td"),
        RepoId("peer/relay_b"): _read_fixture("peer_relay_b.td"),
        RepoId("upstream/central"): _read_fixture("upstream_central.td"),
    }

    result: Assessment = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests=peer_manifests,
        telemetry={},
        history=[],
    )

    # Denouncement is capped and NOT severe
    assert result.network_trust == -EXTERNAL_SINGLE_DENOUNCE_CAP
    assert not any("Severe" in r for r in result.reasons)


def test_telemetry_missing_notes_and_zero_campaign_risk() -> None:
    """Missing telemetry produces limited-evidence note and campaign_risk 0.0.

    Fairness guarantee (AGENTS.md Rule 6):
        Missing telemetry is not negative evidence and never increases risk.
    """
    evaluator = RepoId("evaluator/repo")
    pr = _make_pr(repo=str(evaluator), author="octocat")
    base_manifests = {evaluator: _read_fixture("evaluator.td")}

    result: Assessment = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests={},
        telemetry={},
        history=[],
    )

    assert result.campaign_risk == 0.0
    assert any("limited evidence: telemetry is absent" in n for n in result.notes)


def test_assess_byte_identical_determinism() -> None:
    """Running assess twice on identical inputs produces byte-identical canonical JSON.

    AGENTS.md Rule 1:
        Determinism: The same inputs always produce byte-identical outputs.
        No timestamps, no random values, all collections sorted.
    """
    evaluator = RepoId("evaluator/repo")
    pr = _make_pr(repo=str(evaluator), author="alice")
    base_manifests = {evaluator: _read_fixture("evaluator.td")}
    peer_manifests = {RepoId("peer/trusted"): _read_fixture("peer_trusted.td")}

    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    telemetry_entry = TelemetryEntry(
        pr_number=10,
        author="alice",
        opened_at=now,
        exact_fingerprint="a" * 64,
        path_set=["src/core.py"],
        minhash_signature=[1] * 128,
        description_similarity_signature=[2] * 128,
    )
    telemetry_data = {
        evaluator: TelemetryLoadResult(
            status=TelemetryStatus.FRESH,
            repository=evaluator,
            entries=[telemetry_entry],
        )
    }

    res1 = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests=peer_manifests,
        telemetry=telemetry_data,
        history=[],
        config=QualityConfig(),
    )

    res2 = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=evaluator,
        peer_manifests=peer_manifests,
        telemetry=telemetry_data,
        history=[],
        config=QualityConfig(),
    )

    assert res1.to_canonical_json() == res2.to_canonical_json()
    assert res1.network_trust == res2.network_trust
    assert res1.campaign_risk == res2.campaign_risk
    assert res1.triage == res2.triage
    assert res1.reasons == res2.reasons
    assert res1.sources == res2.sources
    assert res1.notes == res2.notes
