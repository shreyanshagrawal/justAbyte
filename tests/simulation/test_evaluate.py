"""Tests for simulation evaluation runner and gate verification engine."""

import subprocess
import sys
from pathlib import Path

from opencred.core.models import to_canonical_json
from opencred.simulation.evaluate import (
    EvaluationMode,
    EvaluationReport,
    check_gates,
    evaluate_scenario,
)
from opencred.simulation.generate import generate_scenario


def test_evaluate_runner_completes_on_seed_42_and_matches_schema() -> None:
    """Evaluation runner must complete on seed 42 with valid EvaluationReport schema."""
    scenario = generate_scenario(seed=42)
    report = evaluate_scenario(scenario=scenario, seed=42)

    assert isinstance(report, EvaluationReport)
    assert report.seed == 42
    assert report.num_repos == 30
    assert report.total_prs == 58

    # All three operational modes must be present
    assert EvaluationMode.LOCAL_ONLY.value in report.modes
    assert EvaluationMode.PROPAGATION.value in report.modes
    assert EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS.value in report.modes

    # Check metric fields in each mode
    for mode_name in [
        EvaluationMode.LOCAL_ONLY.value,
        EvaluationMode.PROPAGATION.value,
        EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS.value,
    ]:
        m = report.modes[mode_name]
        assert m.campaigns_detected >= 0
        assert m.campaigns_missed >= 0
        assert m.campaigns_detected + m.campaigns_missed == 3
        assert m.legit_prs_flagged_for_investigation == 0
        assert m.trap_prs_flagged == 0
        assert m.newcomer_fairness_violations == 0
        assert -1.0 <= m.ring_suppression <= 1.0

    # Local mode has no propagation or telemetry
    local_m = report.modes[EvaluationMode.LOCAL_ONLY.value]
    assert local_m.propagation_rounds == 0
    assert local_m.campaigns_detected == 0
    assert local_m.campaigns_missed == 3

    # Full mode detects all campaigns
    full_m = report.modes[EvaluationMode.PROPAGATION_PLUS_CAMPAIGNS.value]
    assert full_m.campaigns_detected == 3
    assert full_m.campaigns_missed == 0
    assert full_m.ring_suppression >= -0.3
    assert full_m.propagation_rounds == 2

    # Verify serialization to canonical JSON and deserialization back
    json_str = to_canonical_json(report)
    deserialized = EvaluationReport.model_validate_json(json_str)
    assert deserialized.seed == 42
    assert len(deserialized.modes) == 3


def test_gate_verification_passes_when_thresholds_met() -> None:
    """check_gates must report True when all metrics satisfy configured gate thresholds."""
    scenario = generate_scenario(seed=42)
    gates = {
        "newcomer_fairness_violations_max": 0,
        "ring_suppression_floor": -0.3,
        "campaigns_missed_max": 0,
        "legit_prs_flagged_for_investigation_max": 0,
        "trap_prs_flagged_max": 0,
    }
    report = evaluate_scenario(scenario=scenario, seed=42, gates=gates)

    assert report.gates_passed is True
    assert len(report.gate_failures) == 0


def test_gate_verification_fails_and_records_failures() -> None:
    """check_gates must record failure details when any gate threshold is violated."""
    scenario = generate_scenario(seed=42)
    # Impose an impossible gate (floor > 0.0 for ring suppression)
    strict_gates = {
        "ring_suppression_floor": 0.5,
    }
    passed, failures = check_gates(evaluate_scenario(scenario=scenario, seed=42), strict_gates)

    assert passed is False
    assert len(failures) > 0
    assert any("ring_suppression" in f for f in failures)


def test_evaluate_cli_execution_with_gates() -> None:
    """CLI execution via python -m opencred.simulation.evaluate must succeed on seed 42."""
    cmd = [
        sys.executable,
        "-m",
        "opencred.simulation.evaluate",
        "--seed",
        "42",
        "--gates",
        "examples/gates.json",
        "--format",
        "markdown",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "OpenCred Simulation Evaluation Report" in proc.stdout
    assert "Gate Status:** `PASSED`" in proc.stdout


def test_evaluate_cli_fails_on_failing_gate(tmp_path: Path) -> None:
    """CLI execution must exit with status code 1 when a gate fails."""
    impossible_gate = tmp_path / "strict_gate.json"
    impossible_gate.write_text('{"ring_suppression_floor": 0.99}\n', encoding="utf-8")

    cmd = [
        sys.executable,
        "-m",
        "opencred.simulation.evaluate",
        "--seed",
        "42",
        "--gates",
        str(impossible_gate),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 1
    assert "Gate Status:** `FAILED`" in proc.stdout


def test_sweep_script_execution(tmp_path: Path) -> None:
    """scripts/sweep.py must execute across the 9 parameter combinations."""
    out_table = tmp_path / "sweep_results.md"
    cmd = [
        sys.executable,
        "scripts/sweep.py",
        "--seed",
        "42",
        "--format",
        "table",
        "--out",
        str(out_table),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert proc.returncode == 0
    assert "Campaign Detection Parameter Sensitivity Sweep" in proc.stdout
    assert out_table.exists()
    content = out_table.read_text(encoding="utf-8")
    assert "| `0.6` | 2 |" in content
    assert "| `0.8` | 4 |" in content
