"""OpenCred AI Campaign Analyzer Interface and Implementations.

This package provides an optional AI-assisted analyzer interface for campaign candidates.
Per AGENTS.md rule 10 and architectural boundary requirements:
- Core modules NEVER import from opencred.ai.
- The AI analyzer is strictly optional and never required for core correctness.
- The analyzer only receives detected CampaignCandidate instances, never individual unlinked PRs.
- Analyzer output is ADVISORY ONLY: it may contribute explanatory evidence strings, but
  it must NEVER change campaign_risk or alter triage decisions on its own.
- Prompts sent to external models contain only sanitized/normalized fields
  (title, changed file paths, normalized diff excerpt, affected repos, author counts);
  raw PR bodies are strictly excluded to prevent prompt injection or data leakage.
- Network calls must have strict timeouts and must never raise exceptions to the caller.
"""

import json
import urllib.error
import urllib.request
from enum import StrEnum
from typing import Any, Protocol

from pydantic import Field

from opencred.core.campaign import CampaignCandidate
from opencred.core.models import OpenCredModel, PullRequestRecord


class AnalyzerVerdict(StrEnum):
    """Advisory verdict classifications for AI campaign analysis."""

    LIKELY_COORDINATED = "LIKELY_COORDINATED"
    UNCLEAR = "UNCLEAR"
    LIKELY_LEGITIMATE = "LIKELY_LEGITIMATE"


class AnalyzerResult(OpenCredModel):
    """Advisory result produced by an optional campaign candidate analyzer."""

    verdict_label: AnalyzerVerdict
    evidence: list[str] = Field(
        default_factory=list,
        description="List of explanatory evidence strings",
    )
    uncertainty: str = Field(
        description="Explanation of model confidence or ambiguity",
    )
    model_id: str = Field(
        description="Identifier of the model or heuristic engine",
    )


class CampaignAnalyzer(Protocol):
    """Protocol for optional campaign candidate AI analyzers."""

    def analyze(
        self,
        candidate: CampaignCandidate,
        samples: list[PullRequestRecord],
    ) -> AnalyzerResult:
        """Analyze a campaign candidate and sample PRs for coordination patterns.

        Args:
            candidate: Detected campaign candidate with affected repos, authors, and signals.
            samples: List of relevant PullRequestRecord samples for the candidate.

        Returns:
            AnalyzerResult: Advisory verdict, evidence strings, uncertainty, and model ID.
        """
        ...


class NullAnalyzer:
    """Default no-op analyzer returning UNCLEAR with explanatory evidence."""

    def analyze(
        self,
        candidate: CampaignCandidate,
        samples: list[PullRequestRecord],
    ) -> AnalyzerResult:
        """Return UNCLEAR indicating no AI analyzer is configured."""
        return AnalyzerResult(
            verdict_label=AnalyzerVerdict.UNCLEAR,
            evidence=["no analyzer configured"],
            uncertainty="no analyzer configured",
            model_id="null",
        )


class FakeAnalyzer:
    """Deterministic analyzer for unit and integration testing."""

    def __init__(
        self,
        forced_verdict: AnalyzerVerdict | str | None = None,
        model_id: str = "fake-analyzer-v1",
    ) -> None:
        self.forced_verdict = (
            AnalyzerVerdict(forced_verdict) if forced_verdict is not None else None
        )
        self.model_id = model_id

    def analyze(
        self,
        candidate: CampaignCandidate,
        samples: list[PullRequestRecord],
    ) -> AnalyzerResult:
        """Return a deterministic verdict based on candidate signals or forced override."""
        if self.forced_verdict is not None:
            verdict = self.forced_verdict
        elif candidate.campaign_risk >= 0.7:
            verdict = AnalyzerVerdict.LIKELY_COORDINATED
        elif candidate.campaign_risk < 0.3:
            verdict = AnalyzerVerdict.LIKELY_LEGITIMATE
        else:
            verdict = AnalyzerVerdict.UNCLEAR

        evidence = [
            (
                f"Candidate spans {len(candidate.affected_repos)} repos "
                f"and {len(candidate.authors)} authors"
            ),
            f"Observed signals: {', '.join(candidate.signals) if candidate.signals else 'none'}",
        ]
        return AnalyzerResult(
            verdict_label=verdict,
            evidence=evidence,
            uncertainty="deterministic rule evaluation",
            model_id=self.model_id,
        )


class OllamaAnalyzer:
    """Optional analyzer that queries a local Ollama server over HTTP.

    Security & Privacy Note:
        Prompts constructed by this analyzer contain ONLY normalized fields:
        - Candidate affected repository IDs and author usernames.
        - Candidate observed signals.
        - PR titles, changed file paths, and normalized diff snippets.
        Raw contributor PR bodies are strictly excluded to avoid prompt injection attacks
        or unvetted data exfiltration.

    Fault Tolerance:
        All network calls have an explicit timeout (default: 5.0 seconds).
        Any HTTP error, connection error, timeout, or malformed response is caught
        and returns an advisory UNCLEAR result. It will NEVER raise an exception to the caller.
    """

    def __init__(
        self,
        model_name: str = "llama3.2",
        endpoint: str = "http://localhost:11434",
        timeout_seconds: float = 5.0,
    ) -> None:
        self.model_name = model_name
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _build_prompt(
        self,
        candidate: CampaignCandidate,
        samples: list[PullRequestRecord],
    ) -> str:
        """Construct prompt containing strictly normalized fields without raw author bodies."""
        pr_summaries: list[str] = []
        for s in samples[:3]:  # Limit to top 3 sample PRs
            diff_snippet = s.normalized_diff[:300].strip()
            pr_summaries.append(
                f"- Repo: {s.repo}, PR #{s.number}, Title: '{s.title}', Files: {s.changed_files}\n"
                f"  Diff Excerpt:\n{diff_snippet}"
            )
        sample_text = "\n".join(pr_summaries) if pr_summaries else "No samples available"

        repos_text = ", ".join(str(r) for r in candidate.affected_repos)
        authors_text = ", ".join(candidate.authors)
        signals_text = ", ".join(candidate.signals)

        return (
            "You are a security assistant assessing potential coordinated pull request campaigns.\n"
            "Analyze the following metadata and classify coordination:\n\n"
            f"Candidate ID: {candidate.id}\n"
            f"Affected Repositories ({len(candidate.affected_repos)}): {repos_text}\n"
            f"Authors ({len(candidate.authors)}): {authors_text}\n"
            f"Signals: {signals_text}\n"
            f"Sample Pull Requests (Normalized Metadata):\n{sample_text}\n\n"
            "Respond in JSON format with keys:\n"
            "- verdict: 'LIKELY_COORDINATED', 'UNCLEAR', or 'LIKELY_LEGITIMATE'\n"
            "- evidence: list of reason strings\n"
            "- uncertainty: reason for uncertainty\n"
        )

    def analyze(
        self,
        candidate: CampaignCandidate,
        samples: list[PullRequestRecord],
    ) -> AnalyzerResult:
        """Call Ollama /api/generate over HTTP with strict timeout and fallback."""
        prompt = self._build_prompt(candidate, samples)
        url = f"{self.endpoint}/api/generate"

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }

        try:
            req_data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url,
                data=req_data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as resp:
                resp_bytes = resp.read()
                data = json.loads(resp_bytes.decode("utf-8"))

            raw_response = data.get("response", "")
            parsed: dict[str, Any] = (
                json.loads(raw_response) if isinstance(raw_response, str) and raw_response else data
            )

            verdict_str = str(parsed.get("verdict", "")).strip().upper()
            if verdict_str in AnalyzerVerdict.__members__:
                verdict = AnalyzerVerdict(verdict_str)
            else:
                verdict = AnalyzerVerdict.UNCLEAR

            evidence_val = parsed.get("evidence", [])
            if isinstance(evidence_val, str):
                evidence = [evidence_val]
            elif isinstance(evidence_val, list):
                evidence = [str(e) for e in evidence_val]
            else:
                evidence = []

            uncertainty = str(parsed.get("uncertainty", "model-generated evaluation"))

            return AnalyzerResult(
                verdict_label=verdict,
                evidence=evidence,
                uncertainty=uncertainty,
                model_id=f"ollama/{self.model_name}",
            )
        except Exception as err:
            # Fault tolerance: never raise to the caller
            return AnalyzerResult(
                verdict_label=AnalyzerVerdict.UNCLEAR,
                evidence=[f"Ollama server query failed: {err}"],
                uncertainty="server unreachable or error during inference",
                model_id=f"ollama/{self.model_name}",
            )


__all__ = [
    "AnalyzerResult",
    "AnalyzerVerdict",
    "CampaignAnalyzer",
    "FakeAnalyzer",
    "NullAnalyzer",
    "OllamaAnalyzer",
]
