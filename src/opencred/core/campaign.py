"""Pull request campaign and burst activity detection.

This module detects coordinated multi-repository pull request campaigns using:
- Pairwise PR similarity (exact diff fingerprint, MinHash diff tokens,
  MinHash description shingles, and path-set Jaccard).
- Time-windowed clustering via deterministic Disjoint Set Union (Union-Find).
- Campaign candidate qualification thresholds (authors, repositories, PR count).
- Configurable exclusion filters for benign mass PRs (dependency bumps, typo fixes).
- Explainable signals and bounded heuristic risk assessment.

All operations strictly obey AGENTS.md rules:
- Deterministic behavior: no reliance on Python's randomized hash().
- Isolated domain logic: zero imports of CLI, networking, or GitHub client libraries.
- Advisory outputs: status is always 'AWAITING_EVIDENCE' prior to triage.
"""

import hashlib
import re
from collections.abc import Iterable
from datetime import datetime
from pathlib import Path

from pydantic import Field

from opencred.core.config import (
    CAMPAIGN_BURST_MIN_PRS,
    CAMPAIGN_EXCLUSION_DIFF_PATTERNS,
    CAMPAIGN_EXCLUSION_FILE_PATTERNS,
    CAMPAIGN_EXCLUSION_TITLE_PATTERNS,
    CAMPAIGN_MIN_AUTHORS,
    CAMPAIGN_MIN_REPOS,
    CAMPAIGN_SIMILARITY_THRESHOLD,
    CAMPAIGN_WEIGHT_DESC,
    CAMPAIGN_WEIGHT_DIFF,
    CAMPAIGN_WEIGHT_PATHS,
    CAMPAIGN_WINDOW_HOURS,
)
from opencred.core.fingerprint import (
    exact_fingerprint,
    jaccard,
    normalize_diff,
    path_set,
    shingles,
)
from opencred.core.minhash import (
    estimate_similarity,
    minhash_signature,
)
from opencred.core.models import (
    OpenCredModel,
    PullRequestRecord,
    RepoId,
)
from opencred.core.telemetry import TelemetryEntry

_EMPTY_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"


class CampaignCandidate(OpenCredModel):
    """A detected multi-repository pull request campaign candidate."""

    id: str = Field(description="Deterministic SHA-256 hash of sorted PR keys")
    affected_repos: list[RepoId] = Field(
        description="Sorted list of affected repository identifiers"
    )
    authors: list[str] = Field(description="Sorted list of contributor usernames")
    pr_keys: list[str] = Field(description="Sorted list of PR keys in repo#number format")
    signals: list[str] = Field(
        description="List of feature strings describing observed campaign evidence"
    )
    status: str = Field(
        default="AWAITING_EVIDENCE",
        description="Candidate review status; always 'AWAITING_EVIDENCE' prior to triage",
    )
    campaign_risk: float = Field(
        ge=0.0,
        le=1.0,
        description="Heuristic campaign risk in [0.0, 1.0]",
    )
    excluded_reason: str | None = Field(
        default=None,
        description="Explanation if the candidate was excluded under benign pattern rules",
    )


class CampaignDetectionResult(OpenCredModel):
    """Aggregate result of campaign detection over a set of pull requests."""

    candidates: list[CampaignCandidate] = Field(
        default_factory=list,
        description="Active campaign candidates awaiting evidence",
    )
    excluded: list[CampaignCandidate] = Field(
        default_factory=list,
        description="Candidate components excluded due to benign patterns",
    )

    def __iter__(self):  # type: ignore[no-untyped-def]
        """Iterate directly over active campaign candidates."""
        return iter(self.candidates)

    def __len__(self) -> int:
        """Return the number of active candidates."""
        return len(self.candidates)

    def __getitem__(self, index: int) -> CampaignCandidate:
        """Access active candidates by index."""
        return self.candidates[index]

    @property
    def all_components(self) -> list[CampaignCandidate]:
        """Return all detected components including excluded ones."""
        return self.candidates + self.excluded


class UnionFind:
    """Disjoint Set Union (DSU) data structure with deterministic tie-breaking.

    Roots are chosen deterministically by selecting the lexicographically
    smallest PR key when merging two sets.
    """

    def __init__(self, elements: Iterable[str]) -> None:
        self.parent: dict[str, str] = {el: el for el in elements}

    def find(self, x: str) -> str:
        """Find the representative root of element x with path compression."""
        root = x
        while self.parent[root] != root:
            root = self.parent[root]
        curr = x
        while curr != root:
            nxt = self.parent[curr]
            self.parent[curr] = root
            curr = nxt
        return root

    def union(self, x: str, y: str) -> None:
        """Merge sets containing x and y using deterministic lexicographical tie-breaking."""
        root_x = self.find(x)
        root_y = self.find(y)
        if root_x != root_y:
            # Deterministic tie-breaking: the lexicographically smaller key becomes root
            if root_x < root_y:
                self.parent[root_y] = root_x
            else:
                self.parent[root_x] = root_y


class _PRFeatures:
    """Precomputed deterministic features for a pull request or telemetry record."""

    __slots__ = (
        "author",
        "desc_sig",
        "diff_fp",
        "diff_sig",
        "is_benign",
        "key",
        "norm_diff",
        "opened_at",
        "paths",
        "repo",
    )

    def __init__(
        self,
        key: str,
        repo: RepoId,
        author: str,
        opened_at: datetime,
        diff_fp: str,
        diff_sig: tuple[int, ...],
        desc_sig: tuple[int, ...],
        paths: frozenset[str],
        norm_diff: str = "",
        is_benign: bool = False,
    ) -> None:
        self.key = key
        self.repo = repo
        self.author = author
        self.opened_at = opened_at
        self.diff_fp = diff_fp
        self.diff_sig = diff_sig
        self.desc_sig = desc_sig
        self.paths = paths
        self.norm_diff = norm_diff
        self.is_benign = is_benign

    @classmethod
    def from_pr(cls, pr: PullRequestRecord) -> "_PRFeatures":
        key = f"{pr.repo}#{pr.number}"
        norm_diff = normalize_diff(pr.normalized_diff)
        diff_fp = exact_fingerprint(pr.normalized_diff)
        diff_tokens = frozenset(norm_diff.split())
        diff_sig = minhash_signature(diff_tokens, num_perm=128)
        desc_text = f"{pr.title}\n{pr.body}".strip()
        desc_shing = shingles(desc_text, k=3)
        desc_sig = minhash_signature(desc_shing, num_perm=128)
        paths = path_set(pr.changed_files)
        is_benign = _check_is_benign_pr(pr, norm_diff)
        return cls(
            key=key,
            repo=pr.repo,
            author=pr.author,
            opened_at=pr.opened_at,
            diff_fp=diff_fp,
            diff_sig=diff_sig,
            desc_sig=desc_sig,
            paths=paths,
            norm_diff=norm_diff,
            is_benign=is_benign,
        )

    @classmethod
    def from_telemetry(cls, repo: RepoId, entry: TelemetryEntry) -> "_PRFeatures":
        key = f"{repo}#{entry.pr_number}"
        paths = path_set(entry.path_set)
        all_lockfiles = bool(paths) and all(
            Path(f).name.lower() in CAMPAIGN_EXCLUSION_FILE_PATTERNS
            or f.lower().endswith(CAMPAIGN_EXCLUSION_FILE_PATTERNS)
            for f in paths
        )
        return cls(
            key=key,
            repo=repo,
            author=entry.author,
            opened_at=entry.opened_at,
            diff_fp=entry.exact_fingerprint,
            diff_sig=tuple(entry.minhash_signature),
            desc_sig=tuple(entry.description_similarity_signature),
            paths=paths,
            norm_diff="",
            is_benign=all_lockfiles,
        )


def _check_is_benign_pr(pr: PullRequestRecord, norm_diff: str) -> bool:
    """Check if an individual PR matches configured benign patterns.

    A PR is benign only if its modifications strictly adhere to benign categories:
    - Pure version string bumps in diff hunk lines.
    - Lockfile-only changes (e.g. package-lock.json, cargo.lock).
    - Typo fixes on documentation files (.md, .rst, .txt).
    """
    hunk_lines = [
        line
        for line in norm_diff.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]

    diff_regexes = [re.compile(p) for p in CAMPAIGN_EXCLUSION_DIFF_PATTERNS]
    is_pure_version_diff = bool(hunk_lines) and all(
        any(rx.search(line) for rx in diff_regexes) for line in hunk_lines
    )

    if is_pure_version_diff:
        return True

    all_lockfiles = bool(pr.changed_files) and all(
        Path(f).name.lower() in CAMPAIGN_EXCLUSION_FILE_PATTERNS
        or f.lower().endswith(CAMPAIGN_EXCLUSION_FILE_PATTERNS)
        for f in pr.changed_files
    )

    title_stripped = pr.title.strip()
    title_matches_exclusion = any(
        re.search(pattern, title_stripped) for pattern in CAMPAIGN_EXCLUSION_TITLE_PATTERNS
    )

    if all_lockfiles and (title_matches_exclusion or not hunk_lines):
        return True

    if title_matches_exclusion and (all_lockfiles or is_pure_version_diff or not hunk_lines):
        return True

    # Check documentation typo fixes
    is_typo_title = bool(re.search(r"(?i)^fix(ed)?\s+typo", title_stripped)) or bool(
        re.search(r"(?i)^typo(s)?\s+fix", title_stripped)
    )
    if is_typo_title:
        doc_files = bool(pr.changed_files) and all(
            f.lower().endswith((".md", ".rst", ".txt", ".markdown")) for f in pr.changed_files
        )
        if doc_files:
            return True

    return False


def _hours_between(t1: datetime, t2: datetime) -> float:
    """Calculate absolute elapsed time in hours between two datetimes."""
    if t1.tzinfo is not None and t2.tzinfo is None:
        t2 = t2.replace(tzinfo=t1.tzinfo)
    elif t1.tzinfo is None and t2.tzinfo is not None:
        t1 = t1.replace(tzinfo=t2.tzinfo)
    return abs((t1 - t2).total_seconds()) / 3600.0


def calculate_pr_similarity(pr_a: PullRequestRecord, pr_b: PullRequestRecord) -> float:
    """Compute the pairwise similarity between two pull request records.

    Rule:
        Exact normalized diff fingerprint equality alone is sufficient
        to link two PRs (returns 1.0).

        Otherwise, computes a documented weighted combination of:
        - MinHash estimate of normalized diff tokens (CAMPAIGN_WEIGHT_DIFF)
        - MinHash estimate of description shingles (CAMPAIGN_WEIGHT_DESC)
        - Jaccard similarity of changed file paths (CAMPAIGN_WEIGHT_PATHS)

    Returns:
        A float similarity score in [0.0, 1.0].
    """
    feat_a = _PRFeatures.from_pr(pr_a)
    feat_b = _PRFeatures.from_pr(pr_b)
    return _calculate_feature_similarity(feat_a, feat_b)


def _calculate_feature_similarity(feat_a: _PRFeatures, feat_b: _PRFeatures) -> float:
    """Compute similarity between two precomputed PR feature objects."""
    # Strong signal: exact normalized diff fingerprint match
    if (
        feat_a.diff_fp
        and feat_b.diff_fp
        and feat_a.diff_fp == feat_b.diff_fp
        and feat_a.diff_fp != _EMPTY_SHA256
    ):
        return 1.0

    diff_sim = estimate_similarity(feat_a.diff_sig, feat_b.diff_sig)
    desc_sim = estimate_similarity(feat_a.desc_sig, feat_b.desc_sig)
    path_sim = jaccard(feat_a.paths, feat_b.paths)

    combined = (
        CAMPAIGN_WEIGHT_DIFF * diff_sim
        + CAMPAIGN_WEIGHT_DESC * desc_sim
        + CAMPAIGN_WEIGHT_PATHS * path_sim
    )
    return max(0.0, min(1.0, float(combined)))


def detect_campaigns(
    prs: list[PullRequestRecord],
    total_repos_in_scenario: int | None = None,
    telemetry_entries: list[tuple[RepoId, TelemetryEntry]] | None = None,
) -> CampaignDetectionResult:
    """Detect coordinated multi-repository pull request campaigns.

    Args:
        prs: List of pull request records to evaluate.
        total_repos_in_scenario: Total count of distinct repositories in the evaluation
            scenario (defaults to total distinct repositories across all items, min 1).
        telemetry_entries: Optional list of (RepoId, TelemetryEntry) tuples from telemetry.

    Returns:
        CampaignDetectionResult containing active candidates and excluded candidate components.
    """
    features: list[_PRFeatures] = []
    if prs:
        sorted_prs = sorted(prs, key=lambda pr: (str(pr.repo), pr.number))
        features.extend(_PRFeatures.from_pr(pr) for pr in sorted_prs)

    if telemetry_entries:
        sorted_telem = sorted(telemetry_entries, key=lambda t: (str(t[0]), t[1].pr_number))
        features.extend(_PRFeatures.from_telemetry(repo, entry) for repo, entry in sorted_telem)

    if not features:
        return CampaignDetectionResult()

    # Sort all features deterministically by key
    features.sort(key=lambda f: f.key)

    # Determine scenario baseline repository count
    input_repo_count = len({f.repo for f in features})
    scenario_repos = (
        max(1, total_repos_in_scenario)
        if total_repos_in_scenario is not None
        else max(1, input_repo_count)
    )

    # 2. Build connected components using Disjoint Set Union
    dsu = UnionFind(f.key for f in features)
    n = len(features)

    for i in range(n):
        for j in range(i + 1, n):
            feat_i = features[i]
            feat_j = features[j]

            # Link only if opened within the configured time window
            hours = _hours_between(feat_i.opened_at, feat_j.opened_at)
            if hours > CAMPAIGN_WINDOW_HOURS:
                continue

            sim = _calculate_feature_similarity(feat_i, feat_j)
            if sim >= CAMPAIGN_SIMILARITY_THRESHOLD:
                dsu.union(feat_i.key, feat_j.key)

    # 3. Group PRs by their deterministic component root
    components_by_root: dict[str, list[_PRFeatures]] = {}
    for feat in features:
        root = dsu.find(feat.key)
        components_by_root.setdefault(root, []).append(feat)

    active_candidates: list[CampaignCandidate] = []
    excluded_candidates: list[CampaignCandidate] = []

    # Sort components deterministically by root key
    sorted_roots = sorted(components_by_root.keys())

    for root in sorted_roots:
        comp_feats = components_by_root[root]

        # 4. Campaign Candidate qualification checks:
        #    - At least CAMPAIGN_MIN_AUTHORS distinct authors
        #    - At least CAMPAIGN_MIN_REPOS distinct repositories
        #    - At least CAMPAIGN_BURST_MIN_PRS PRs
        distinct_authors = sorted({f.author for f in comp_feats})
        distinct_repos = sorted({f.repo for f in comp_feats})
        pr_keys = sorted([f.key for f in comp_feats])
        num_prs = len(comp_feats)

        if (
            len(distinct_authors) < CAMPAIGN_MIN_AUTHORS
            or len(distinct_repos) < CAMPAIGN_MIN_REPOS
            or num_prs < CAMPAIGN_BURST_MIN_PRS
        ):
            continue

        # 5. Check exclusion rule:
        # Components whose PRs are ALL dependency bumps or typo fixes are excluded.
        all_benign = all(f.is_benign for f in comp_feats)
        excluded_reason: str | None = None
        if all_benign:
            excluded_reason = (
                f"Component excluded: all {num_prs} pull requests match benign patterns "
                "(dependency bump, typo fix, lockfile-only, or version string update)"
            )

        # 6. Mean pairwise similarity across all distinct pairs in the component
        m = len(comp_feats)
        total_pair_sim = 0.0
        num_pairs = (m * (m - 1)) // 2

        all_identical_diffs = True
        first_fp = comp_feats[0].diff_fp
        for f in comp_feats:
            if not f.diff_fp or f.diff_fp == _EMPTY_SHA256 or f.diff_fp != first_fp:
                all_identical_diffs = False
                break

        for i in range(m):
            for j in range(i + 1, m):
                total_pair_sim += _calculate_feature_similarity(comp_feats[i], comp_feats[j])

        mean_pairwise_similarity = total_pair_sim / num_pairs if num_pairs > 0 else 1.0

        # Heuristic campaign risk calculation:
        # campaign_risk = clamp(0.5 * (distinct_repos / total_repos) + 0.5 * mean_sim, 0, 1)
        # Note: STARTING VALUE heuristic to be tuned by simulation (AGENTS.md rule 9).
        repo_ratio = len(distinct_repos) / scenario_repos
        raw_risk = 0.5 * repo_ratio + 0.5 * mean_pairwise_similarity
        campaign_risk = max(0.0, min(1.0, float(raw_risk)))

        # Deterministic component ID: SHA-256 of sorted comma-separated PR keys
        candidate_id = hashlib.sha256(",".join(pr_keys).encode("utf-8")).hexdigest()[:16]

        # Explainable signals
        min_opened = min(f.opened_at for f in comp_feats)
        max_opened = max(f.opened_at for f in comp_feats)
        span_hours = _hours_between(min_opened, max_opened)

        signals: list[str] = [
            f"burst: {num_prs} PRs in {span_hours:.1f}h",
            f"mean pairwise similarity: {mean_pairwise_similarity:.2f}",
            f"coordinated across {len(distinct_repos)} repos and {len(distinct_authors)} authors",
        ]
        if all_identical_diffs:
            signals.append("identical diff fingerprints across all PRs")

        candidate = CampaignCandidate(
            id=candidate_id,
            affected_repos=distinct_repos,
            authors=distinct_authors,
            pr_keys=pr_keys,
            signals=signals,
            status="AWAITING_EVIDENCE",
            campaign_risk=campaign_risk,
            excluded_reason=excluded_reason,
        )

        if all_benign:
            excluded_candidates.append(candidate)
        else:
            active_candidates.append(candidate)

    return CampaignDetectionResult(
        candidates=active_candidates,
        excluded=excluded_candidates,
    )


__all__ = [
    "CampaignCandidate",
    "CampaignDetectionResult",
    "UnionFind",
    "calculate_pr_similarity",
    "detect_campaigns",
]
