"""Tests for optional AI analyzer interface and implementations.

Validates that:
1. NullAnalyzer is used by default and assess output is unchanged.
2. OllamaAnalyzer returns UNCLEAR when the server is unreachable (mocked HTTP).
3. Adding a FakeAnalyzer with LIKELY_COORDINATED does not alter campaign_risk or triage.
4. Prompts contain only normalized fields and strictly exclude raw PR bodies.
"""

import json
import urllib.error
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

from opencred.ai.analyzer import (
    AnalyzerResult,
    AnalyzerVerdict,
    CampaignAnalyzer,
    FakeAnalyzer,
    NullAnalyzer,
    OllamaAnalyzer,
)
from opencred.core.assessment import assess
from opencred.core.campaign import CampaignCandidate
from opencred.core.models import PullRequestRecord, RepoId
from opencred.core.telemetry import TelemetryEntry, TelemetryLoadResult, TelemetryStatus
from opencred.core.triage import TriageOutcome


def _create_sample_candidate_and_pr() -> tuple[CampaignCandidate, PullRequestRecord]:
    """Helper creating a sample campaign candidate and PR record."""
    pr = PullRequestRecord(
        repo=RepoId("test-org/repo-a"),
        number=101,
        author="sybil_attacker_01",
        opened_at=datetime(2026, 10, 10, 12, 0, 0, tzinfo=UTC),
        title="Fix buffer overflow in parser",
        body="SECRET RAW BODY TEXT - MUST NOT BE LEAKED TO AI PROMPT",
        changed_files=["src/parser.c"],
        normalized_diff="- int buf[32];\n+ int buf[1024];\n+ // payload injection",
        linked_issue_numbers=[],
        external_links=[],
    )

    candidate = CampaignCandidate(
        id="cand_test_001",
        affected_repos=[RepoId("test-org/repo-a"), RepoId("test-org/repo-b")],
        authors=["sybil_attacker_01", "sybil_attacker_02", "sybil_attacker_03"],
        pr_keys=["test-org/repo-a#101", "test-org/repo-b#201"],
        signals=["exact normalized diff match across 3 authors"],
        status="AWAITING_EVIDENCE",
        campaign_risk=0.85,
    )
    return candidate, pr


def _setup_scenario_for_candidate(
    candidate: CampaignCandidate, pr: PullRequestRecord
) -> tuple[
    dict[RepoId, str],
    dict[RepoId, str],
    dict[RepoId, TelemetryLoadResult],
]:
    """Helper setting up base manifests, peer manifests, and telemetry."""
    base_manifests = {
        pr.repo: (
            "# Evaluator\n"
            "# @trust-repo test-org/repo-b weight=0.90\n"
            "# @trust-repo test-org/repo-c weight=0.90\n"
        )
    }
    peer_manifests = {
        RepoId("test-org/repo-b"): "# Peer B\n",
        RepoId("test-org/repo-c"): "# Peer C\n",
    }

    # Telemetry creating matching candidate in assess()
    entries_a = [
        TelemetryEntry(
            pr_number=pr.number,
            author=pr.author,
            opened_at=pr.opened_at,
            exact_fingerprint="a" * 64,
            path_set=["src/parser.c"],
            minhash_signature=[42] * 128,
            description_similarity_signature=[42] * 128,
        ),
        TelemetryEntry(
            pr_number=102,
            author="sybil_attacker_02",
            opened_at=pr.opened_at + timedelta(minutes=10),
            exact_fingerprint="a" * 64,
            path_set=["src/parser.c"],
            minhash_signature=[42] * 128,
            description_similarity_signature=[42] * 128,
        ),
    ]

    entries_b = [
        TelemetryEntry(
            pr_number=201,
            author="sybil_attacker_03",
            opened_at=pr.opened_at + timedelta(minutes=20),
            exact_fingerprint="a" * 64,
            path_set=["src/parser.c"],
            minhash_signature=[42] * 128,
            description_similarity_signature=[42] * 128,
        ),
        TelemetryEntry(
            pr_number=202,
            author="sybil_attacker_04",
            opened_at=pr.opened_at + timedelta(minutes=30),
            exact_fingerprint="a" * 64,
            path_set=["src/parser.c"],
            minhash_signature=[42] * 128,
            description_similarity_signature=[42] * 128,
        ),
    ]

    entries_c = [
        TelemetryEntry(
            pr_number=301,
            author="sybil_attacker_05",
            opened_at=pr.opened_at + timedelta(minutes=40),
            exact_fingerprint="a" * 64,
            path_set=["src/parser.c"],
            minhash_signature=[42] * 128,
            description_similarity_signature=[42] * 128,
        )
    ]

    now = pr.opened_at + timedelta(hours=1)
    telemetry = {
        pr.repo: TelemetryLoadResult(
            status=TelemetryStatus.FRESH,
            repository=pr.repo,
            schema_version=1,
            generated_at=now,
            expires_at=now + timedelta(days=7),
            entries=entries_a,
        ),
        RepoId("test-org/repo-b"): TelemetryLoadResult(
            status=TelemetryStatus.FRESH,
            repository=RepoId("test-org/repo-b"),
            schema_version=1,
            generated_at=now,
            expires_at=now + timedelta(days=7),
            entries=entries_b,
        ),
        RepoId("test-org/repo-c"): TelemetryLoadResult(
            status=TelemetryStatus.FRESH,
            repository=RepoId("test-org/repo-c"),
            schema_version=1,
            generated_at=now,
            expires_at=now + timedelta(days=7),
            entries=entries_c,
        ),
    }

    return base_manifests, peer_manifests, telemetry


def test_protocol_conformance() -> None:
    """All analyzer classes must conform to the CampaignAnalyzer Protocol."""
    null_an: CampaignAnalyzer = NullAnalyzer()
    fake_an: CampaignAnalyzer = FakeAnalyzer()
    ollama_an: CampaignAnalyzer = OllamaAnalyzer()

    candidate, pr = _create_sample_candidate_and_pr()
    assert isinstance(null_an.analyze(candidate, [pr]), AnalyzerResult)
    assert isinstance(fake_an.analyze(candidate, [pr]), AnalyzerResult)
    assert isinstance(ollama_an.analyze(candidate, [pr]), AnalyzerResult)


def test_null_analyzer_default_and_assess_output_unchanged() -> None:
    """NullAnalyzer is used when no analyzer is configured, and assess output is unchanged."""
    candidate, pr = _create_sample_candidate_and_pr()
    null_an = NullAnalyzer()
    res = null_an.analyze(candidate, [pr])

    assert res.verdict_label == AnalyzerVerdict.UNCLEAR
    assert res.evidence == ["no analyzer configured"]
    assert res.uncertainty == "no analyzer configured"
    assert res.model_id == "null"

    base_manifests, peer_manifests, telemetry = _setup_scenario_for_candidate(candidate, pr)

    # 1. Assess with analyzer=None
    assess_none = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=pr.repo,
        peer_manifests=peer_manifests,
        telemetry=telemetry,
        history=[],
        analyzer=None,
    )

    # 2. Assess with analyzer=NullAnalyzer()
    assess_null = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=pr.repo,
        peer_manifests=peer_manifests,
        telemetry=telemetry,
        history=[],
        analyzer=null_an,
    )

    # Core scores and triage must be byte-identical
    assert assess_none.network_trust == assess_null.network_trust
    assert assess_none.campaign_risk == assess_null.campaign_risk
    assert assess_none.contribution_quality_evidence == assess_null.contribution_quality_evidence
    assert assess_none.triage == assess_null.triage
    assert assess_none.reasons == assess_null.reasons


def test_fake_analyzer_with_likely_coordinated_does_not_change_risk_or_triage() -> None:
    """FakeAnalyzer with LIKELY_COORDINATED does not change campaign_risk or triage."""
    candidate, pr = _create_sample_candidate_and_pr()
    base_manifests, peer_manifests, telemetry = _setup_scenario_for_candidate(candidate, pr)

    # Assessment without AI analyzer
    assess_standard = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=pr.repo,
        peer_manifests=peer_manifests,
        telemetry=telemetry,
        history=[],
        analyzer=None,
    )

    # Assessment with FakeAnalyzer forced to LIKELY_COORDINATED
    fake_analyzer = FakeAnalyzer(forced_verdict=AnalyzerVerdict.LIKELY_COORDINATED)
    assess_with_ai = assess(
        pr=pr,
        base_manifests=base_manifests,
        evaluator=pr.repo,
        peer_manifests=peer_manifests,
        telemetry=telemetry,
        history=[],
        analyzer=fake_analyzer,
    )

    # Explicit assertions required by prompt:
    # Campaign risk and triage decision must NOT change
    assert assess_with_ai.campaign_risk == assess_standard.campaign_risk
    assert assess_with_ai.triage == assess_standard.triage
    assert assess_with_ai.network_trust == assess_standard.network_trust
    quality_ev_match = (
        assess_with_ai.contribution_quality_evidence
        == assess_standard.contribution_quality_evidence
    )
    assert quality_ev_match
    assert assess_with_ai.triage == TriageOutcome.INVESTIGATE_CAMPAIGN

    # Advisory notes must record the AI evidence without altering the decision
    ai_notes = [n for n in assess_with_ai.notes if "ai analyzer" in n]
    assert len(ai_notes) > 0
    assert "verdict=LIKELY_COORDINATED" in ai_notes[0]


def test_ollama_analyzer_returns_unclear_when_server_unreachable() -> None:
    """OllamaAnalyzer returns UNCLEAR when the server is unreachable without raising."""
    candidate, pr = _create_sample_candidate_and_pr()

    # Point to an unreachable local port
    analyzer = OllamaAnalyzer(
        model_name="llama3.2",
        endpoint="http://127.0.0.1:59999",
        timeout_seconds=0.5,
    )

    # Mock urllib.request.urlopen raising URLError
    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("Connection refused [Errno 61]"),
    ):
        result = analyzer.analyze(candidate, [pr])

        assert isinstance(result, AnalyzerResult)
        assert result.verdict_label == AnalyzerVerdict.UNCLEAR
        assert "Connection refused" in result.evidence[0]
        assert result.uncertainty == "server unreachable or error during inference"
        assert result.model_id == "ollama/llama3.2"


def test_ollama_analyzer_timeout_fallback() -> None:
    """OllamaAnalyzer handles TimeoutError by returning UNCLEAR without raising."""
    candidate, pr = _create_sample_candidate_and_pr()
    analyzer = OllamaAnalyzer(timeout_seconds=0.1)

    with patch(
        "urllib.request.urlopen",
        side_effect=TimeoutError("Request timed out after 0.1s"),
    ):
        result = analyzer.analyze(candidate, [pr])

        assert result.verdict_label == AnalyzerVerdict.UNCLEAR
        assert "timed out" in result.evidence[0]


def test_ollama_analyzer_successful_mocked_response() -> None:
    """OllamaAnalyzer parses valid model response into AnalyzerResult."""
    candidate, pr = _create_sample_candidate_and_pr()
    analyzer = OllamaAnalyzer(model_name="llama3.2")

    mock_ollama_body = json.dumps(
        {
            "response": json.dumps(
                {
                    "verdict": "LIKELY_COORDINATED",
                    "evidence": [
                        "Near-identical payload injected into parser buffer",
                        "Synchronized burst across multiple fresh author accounts",
                    ],
                    "uncertainty": "low ambiguity due to identical exploit snippet",
                }
            )
        }
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_ollama_body
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = analyzer.analyze(candidate, [pr])

        assert result.verdict_label == AnalyzerVerdict.LIKELY_COORDINATED
        assert len(result.evidence) == 2
        assert "Near-identical payload" in result.evidence[0]
        assert result.model_id == "ollama/llama3.2"


def test_prompt_excludes_raw_pr_body() -> None:
    """Prompts sent to Ollama must contain only normalized fields, excluding raw bodies."""
    candidate, pr = _create_sample_candidate_and_pr()
    analyzer = OllamaAnalyzer()

    prompt = analyzer._build_prompt(candidate, [pr])

    # Must contain normalized metadata
    assert "Candidate ID: cand_test_001" in prompt
    assert "Fix buffer overflow in parser" in prompt
    assert "src/parser.c" in prompt
    assert "Diff Excerpt:" in prompt

    # MUST NOT contain raw body text
    assert "SECRET RAW BODY TEXT" not in prompt
    assert "MUST NOT BE LEAKED" not in prompt
