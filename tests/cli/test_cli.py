"""Unit and integration tests for the OpenCred Typer CLI interface.

Uses typer.testing.CliRunner to test all CLI commands, exit codes, and output formats.
"""

import re
from pathlib import Path

from typer.testing import CliRunner

from opencred.cli.main import app

runner = CliRunner()
FIXTURES_DIR = Path(__file__).parent.parent / "fixtures"
ANSI_REGEX = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _clean_output(text: str) -> str:
    """Remove ANSI escape sequences, table borders, and normalize whitespace."""
    no_ansi = ANSI_REGEX.sub("", text)
    no_borders = no_ansi.replace("│", " ").replace("╭", " ").replace("╰", " ").replace("─", " ")
    return " ".join(no_borders.split())


def test_manifest_command_on_fixture_prints_expected_json() -> None:
    """manifest command parses fixture file and prints canonical JSON with sorted keys."""
    manifest_path = FIXTURES_DIR / "manifests" / "with_directives.td"
    result = runner.invoke(
        app,
        ["manifest", str(manifest_path), "--owner", "test/repo"],
    )

    assert result.exit_code == 0
    assert result.stdout.endswith("\n")

    # Output must be valid JSON matching parse_manifest content
    output = result.stdout.strip()
    assert '"ghostty-org/ghostty"' in output
    assert '"astral-sh/uv"' in output
    assert '"alice"' in output
    assert '"spammer"' in output


def test_manifest_command_format_text() -> None:
    """manifest command with --format text produces human-readable output."""
    manifest_path = FIXTURES_DIR / "manifests" / "with_directives.td"
    result = runner.invoke(
        app,
        ["manifest", str(manifest_path), "--owner", "test/repo", "--format", "text"],
    )

    assert result.exit_code == 0
    assert "Manifest owner: test/repo" in result.stdout
    assert "Trust edges" in result.stdout
    assert "Assertions" in result.stdout


def test_trust_command_on_scenario_fixture() -> None:
    """trust command computes network trust and prints canonical JSON."""
    repo_manifest = FIXTURES_DIR / "scenarios" / "base_manifests" / "evaluator__repo.td"
    peers_dir = FIXTURES_DIR / "scenarios" / "base_manifests"

    result = runner.invoke(
        app,
        [
            "trust",
            "--repo-manifest",
            str(repo_manifest),
            "--peers-dir",
            str(peers_dir),
            "--evaluator",
            "evaluator/repo",
            "--contributor",
            "established_contributor",
        ],
    )

    assert result.exit_code == 0
    assert '"network_trust":1.0' in result.stdout
    assert '"peer/trusted (1 hop)"' in result.stdout


def test_assess_command_matches_expected_json_exactly() -> None:
    """assess command on a scenario fixture matches expected json exactly."""
    pr_file = FIXTURES_DIR / "scenarios" / "pr_newcomer.json"
    base_dir = FIXTURES_DIR / "scenarios" / "base_manifests"
    telem_dir = FIXTURES_DIR / "scenarios" / "telemetry_empty"
    history_file = FIXTURES_DIR / "scenarios" / "history_empty.json"
    expected_file = FIXTURES_DIR / "expected" / "newcomer.json"

    expected_output = expected_file.read_text(encoding="utf-8")

    result = runner.invoke(
        app,
        [
            "assess",
            "--pr",
            str(pr_file),
            "--base-manifests",
            str(base_dir),
            "--telemetry-dir",
            str(telem_dir),
            "--evaluator",
            "evaluator/repo",
            "--history",
            str(history_file),
            "--now",
            "2026-10-01T12:00:00Z",
        ],
    )

    assert result.exit_code == 0
    # Must match byte-for-byte including trailing newline
    assert result.stdout == expected_output


def test_assess_command_format_text() -> None:
    """assess command with --format text produces human-readable summary derived from same data."""
    pr_file = FIXTURES_DIR / "scenarios" / "pr_newcomer.json"
    base_dir = FIXTURES_DIR / "scenarios" / "base_manifests"
    telem_dir = FIXTURES_DIR / "scenarios" / "telemetry_empty"
    history_file = FIXTURES_DIR / "scenarios" / "history_empty.json"

    result = runner.invoke(
        app,
        [
            "assess",
            "--pr",
            str(pr_file),
            "--base-manifests",
            str(base_dir),
            "--telemetry-dir",
            str(telem_dir),
            "--evaluator",
            "evaluator/repo",
            "--history",
            str(history_file),
            "--format",
            "text",
        ],
    )

    assert result.exit_code == 0
    assert "Repository: evaluator/repo" in result.stdout
    assert "Pull Request: #1 by newbie" in result.stdout
    assert "Triage Outcome: NEWCOMER_FAIR_REVIEW" in result.stdout
    assert "Quality Evidence: 0.75" in result.stdout


def test_simulate_placeholder_exits_with_code_2() -> None:
    """simulate command is a placeholder that prints 'not implemented' and exits with 2."""
    scenario_file = FIXTURES_DIR / "scenarios" / "pr_newcomer.json"
    result = runner.invoke(
        app,
        ["simulate", "--scenario", str(scenario_file)],
    )

    assert result.exit_code == 2
    assert "not implemented" in result.stdout


def test_invalid_file_path_exits_with_code_1() -> None:
    """Invalid or nonexistent input file path exits with error code 1."""
    result = runner.invoke(
        app,
        ["manifest", "nonexistent_file_does_not_exist.td", "--owner", "test/repo"],
    )

    assert result.exit_code == 1
    assert "Error: Manifest file not found" in result.stderr or "Error" in result.stdout


def test_unknown_command_exits_with_code_2() -> None:
    """Unknown command exits with error code 2."""
    result = runner.invoke(
        app,
        ["unknown_command_that_does_not_exist"],
    )

    assert result.exit_code == 2


def test_help_output_documents_now_flag_and_clock_rules() -> None:
    """--help for assess documents that the CLI uses current time only for telemetry freshness."""
    result = runner.invoke(app, ["assess", "--help"], color=False)
    assert result.exit_code == 0
    clean_text = _clean_output(result.stdout)
    assert "--now" in clean_text
    assert "The CLI never reads the system clock except through this flag" in clean_text
    assert "telemetry freshness only" in clean_text


def test_help_output_for_all_commands() -> None:
    """Verify --help executes successfully for all commands."""
    for cmd in ["manifest", "trust", "assess", "simulate"]:
        res = runner.invoke(app, [cmd, "--help"], color=False)
        assert res.exit_code == 0
        clean_text = _clean_output(res.stdout)
        assert f"Usage: opencred {cmd}" in clean_text or cmd in clean_text
