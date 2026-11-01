"""Tests for root action.yml composite action definition."""

from pathlib import Path

import yaml  # type: ignore[import-untyped]


def test_action_yml_exists_and_valid() -> None:
    action_path = Path(__file__).resolve().parent.parent.parent / "action.yml"
    assert action_path.exists(), "action.yml must exist at repository root"

    with action_path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    assert data["name"] == "OpenCred Assessment"
    assert "runs" in data
    assert data["runs"]["using"] == "composite"
    assert len(data["runs"]["steps"]) > 0

    # Ensure required inputs are defined
    inputs = data.get("inputs", {})
    assert "github-token" in inputs
    assert "manifest-dir" in inputs
    assert "post-comment" in inputs

    # Ensure output keys are present
    outputs = data.get("outputs", {})
    assert "triage-decision" in outputs
    assert "network-trust" in outputs
    assert "campaign-risk" in outputs
    assert "contribution-quality" in outputs
