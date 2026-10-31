"""OpenCred simulation ecosystem package.

Provides reproducible scenario generation and evaluation tooling
independent of the core domain logic.
"""

from opencred.simulation.evaluate import (
    EvaluationMode,
    EvaluationReport,
    ModeMetrics,
    check_gates,
    evaluate_scenario,
    run_evaluation,
)
from opencred.simulation.generate import (
    CampaignScenario,
    ContributorLabel,
    DenunciationRingScenario,
    GroundTruth,
    PRLabel,
    Scenario,
    generate_scenario,
)

__all__ = [
    "CampaignScenario",
    "ContributorLabel",
    "DenunciationRingScenario",
    "EvaluationMode",
    "EvaluationReport",
    "GroundTruth",
    "ModeMetrics",
    "PRLabel",
    "Scenario",
    "check_gates",
    "evaluate_scenario",
    "generate_scenario",
    "run_evaluation",
]
