"""Tests for synthetic ecosystem scenario generator.

Verifies determinism, byte-exact reproducible output, ground-truth counts,
and structural constraints (campaigns, denunciation rings, traps, and manifests).
"""

import subprocess
import sys
from pathlib import Path

from opencred.core.manifests import parse_manifest
from opencred.core.models import ContributionEventKind, to_canonical_json
from opencred.simulation.generate import (
    NUM_CAMPAIGNS,
    NUM_DENUNCIATION_RINGS,
    NUM_ESTABLISHED,
    NUM_HONEST_TARGETED,
    NUM_LEGIT_PRS,
    NUM_NEWCOMERS,
    NUM_TRAP_PRS,
    ContributorLabel,
    PRLabel,
    Scenario,
    generate_scenario,
)


def test_same_seed_gives_identical_json() -> None:
    """Same seed must produce byte-identical canonical JSON output across multiple runs."""
    scenario_a = generate_scenario(seed=42)
    scenario_b = generate_scenario(seed=42)

    json_a = to_canonical_json(scenario_a)
    json_b = to_canonical_json(scenario_b)

    assert json_a == json_b
    assert len(json_a) > 0

    # Test repeated generation for strict determinism
    for _ in range(5):
        assert to_canonical_json(generate_scenario(seed=42)) == json_a


def test_different_seeds_give_different_json() -> None:
    """Different seeds must produce different scenario outputs."""
    json_42 = to_canonical_json(generate_scenario(seed=42))
    json_99 = to_canonical_json(generate_scenario(seed=99))
    json_1337 = to_canonical_json(generate_scenario(seed=1337))

    assert json_42 != json_99
    assert json_42 != json_1337
    assert json_99 != json_1337


def test_ground_truth_counts_match_configured_numbers() -> None:
    """Ground truth annotations must exactly match the configured entity counts."""
    scenario = generate_scenario(seed=42, num_repos=30)

    # 1. Repositories and manifests
    assert len(scenario.repositories) == 30
    assert len(scenario.manifests) == 30

    # 2. Denunciation rings and campaigns
    assert len(scenario.denunciation_rings) == NUM_DENUNCIATION_RINGS
    assert len(scenario.campaigns) == NUM_CAMPAIGNS

    # 3. Contributors
    expected_total_contributors = NUM_ESTABLISHED + NUM_NEWCOMERS + NUM_HONEST_TARGETED
    assert len(scenario.contributors) == expected_total_contributors
    assert len(scenario.ground_truth.contributors) == expected_total_contributors

    # Contributor labels count
    gt_contribs = scenario.ground_truth.contributors
    established_count = sum(
        1 for v in gt_contribs.values() if v == ContributorLabel.ESTABLISHED.value
    )
    newcomer_count = sum(1 for v in gt_contribs.values() if v == ContributorLabel.NEWCOMER.value)
    targeted_count = sum(
        1 for v in gt_contribs.values() if v == ContributorLabel.HONEST_TARGETED.value
    )

    assert established_count == NUM_ESTABLISHED  # 30 (60% of ordinary)
    assert newcomer_count == NUM_NEWCOMERS  # 20 (40% of ordinary)
    assert targeted_count == NUM_HONEST_TARGETED  # 2

    # Verify contributor ratio
    assert established_count / (established_count + newcomer_count) == 0.60
    assert newcomer_count / (established_count + newcomer_count) == 0.40

    # 4. Pull Requests
    expected_campaign_prs = NUM_CAMPAIGNS * 6  # 3 * 6 = 18
    expected_total_prs = NUM_LEGIT_PRS + NUM_TRAP_PRS + expected_campaign_prs

    assert len(scenario.prs) == expected_total_prs
    assert len(scenario.ground_truth.prs) == expected_total_prs
    assert len(scenario.false_positive_traps) == NUM_TRAP_PRS

    gt_prs = scenario.ground_truth.prs
    legit_pr_count = sum(1 for v in gt_prs.values() if v == PRLabel.LEGIT.value)
    trap_pr_count = sum(1 for v in gt_prs.values() if v == PRLabel.TRAP.value)
    campaign_pr_count = sum(1 for v in gt_prs.values() if v == PRLabel.CAMPAIGN.value)

    assert legit_pr_count == NUM_LEGIT_PRS  # 30
    assert trap_pr_count == NUM_TRAP_PRS  # 10
    assert campaign_pr_count == expected_campaign_prs  # 18


def test_campaign_structure_and_window_constraints() -> None:
    """Campaigns must involve >=6 new accounts across >=4 repositories within a 6-hour window."""
    scenario = generate_scenario(seed=42)

    for campaign in scenario.campaigns:
        # At least 6 distinct authors
        assert len(campaign.authors) >= 6
        assert len(set(campaign.authors)) >= 6

        # All authors must be newcomers with empty merged history
        for author in campaign.authors:
            assert scenario.ground_truth.contributors[author] == ContributorLabel.NEWCOMER.value
            merged_events = [
                ev
                for ev in scenario.contributors[author]
                if ev.kind == ContributionEventKind.MERGED
            ]
            assert len(merged_events) == 0

        # At least 4 distinct repositories
        assert len(campaign.repositories) >= 4

        # Find the PR records for this campaign
        campaign_prs = [pr for pr in scenario.prs if f"{pr.repo}#{pr.number}" in campaign.pr_keys]
        assert len(campaign_prs) == len(campaign.pr_keys)

        # PRs must all fall within a 6-hour window (CAMPAIGN_WINDOW_HOURS)
        timestamps = [pr.opened_at for pr in campaign_prs]
        min_time = min(timestamps)
        max_time = max(timestamps)
        duration_hours = (max_time - min_time).total_seconds() / 3600.0
        assert duration_hours <= 6.0


def test_denunciation_rings_and_honest_targets() -> None:
    """Denunciation rings must mutually trust each other and falsely denounce honest targets."""
    scenario = generate_scenario(seed=42)

    assert len(scenario.denunciation_rings) == 2

    for ring in scenario.denunciation_rings:
        assert len(ring.repositories) >= 3
        target = ring.target_contributor

        # Target must be classified as HONEST_TARGETED in ground truth
        assert scenario.ground_truth.contributors[target] == ContributorLabel.HONEST_TARGETED.value

        # Target must have legitimate merged history
        target_events = scenario.contributors[target]
        merged_count = sum(1 for ev in target_events if ev.kind == ContributionEventKind.MERGED)
        assert merged_count >= 3

        # Every repository in the ring must denounce the target in its manifest
        for repo in ring.repositories:
            manifest_text = scenario.manifests[str(repo)]
            assert f"- {target}" in manifest_text

            # Repositories in the ring must trust peer repositories in the ring
            for peer in ring.repositories:
                if peer != repo:
                    assert f"# @trust-repo {peer}" in manifest_text


def test_all_generated_manifests_parse_without_errors() -> None:
    """Every generated repository manifest must parse cleanly with parse_manifest."""
    scenario = generate_scenario(seed=42, num_repos=15)

    for repo, text in scenario.manifests.items():
        result = parse_manifest(text, repo)
        assert len(result.errors) == 0, (
            f"Syntax or semantic errors found in manifest for {repo}: {result.errors}"
        )
        # Repositories must have at least one trust edge or assertion
        assert len(result.trust_edges) > 0 or len(result.assertions) > 0


def test_property_alias_and_dict_access() -> None:
    """Scenario model must support PRs/prs property and dict-style indexing."""
    scenario = generate_scenario(seed=42)

    # Attribute and property access
    assert scenario.prs == scenario.PRs
    assert scenario.ground_truth.prs == scenario.ground_truth.PRs

    # Dict-like indexing
    assert scenario["prs"] == scenario.prs
    assert scenario["PRs"] == scenario.prs
    assert scenario.ground_truth["prs"] == scenario.ground_truth.prs
    assert scenario.ground_truth["PRs"] == scenario.ground_truth.prs


def test_simulate_script_cli_execution(tmp_path: Path) -> None:
    """scripts/simulate.py must successfully write scenario JSON via CLI."""
    out_file = tmp_path / "scenario_test.json"
    cmd = [
        sys.executable,
        "scripts/simulate.py",
        "--seed",
        "42",
        "--num-repos",
        "12",
        "--out",
        str(out_file),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, check=True)
    assert proc.returncode == 0
    assert "Generated simulation scenario" in proc.stdout
    assert out_file.exists()

    # Verify output file is valid scenario JSON
    loaded_scenario = Scenario.model_validate_json(out_file.read_text(encoding="utf-8"))
    assert len(loaded_scenario.repositories) == 12
    assert len(loaded_scenario.campaigns) == 3
