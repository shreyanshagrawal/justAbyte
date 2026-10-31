"""OpenCred core domain logic."""

__version__ = "0.1.0"

from opencred.core.aggregate import (
    ExternalSignal,
    aggregate_external,
)
from opencred.core.campaign import (
    CampaignCandidate,
    CampaignDetectionResult,
    UnionFind,
    calculate_pr_similarity,
    detect_campaigns,
)
from opencred.core.clusters import (
    cap_group_influence,
    find_mutual_groups,
)
from opencred.core.config import (
    CAMPAIGN_ALERT_THRESHOLD,
    CAMPAIGN_BURST_MIN_PRS,
    CAMPAIGN_LOW_THRESHOLD,
    CAMPAIGN_MIN_AUTHORS,
    CAMPAIGN_MIN_REPOS,
    CAMPAIGN_SIMILARITY_THRESHOLD,
    CAMPAIGN_WINDOW_HOURS,
    EXTERNAL_SINGLE_DENOUNCE_CAP,
    LOCAL_DENOUNCE_WEIGHT,
    MIN_INDEPENDENT_ORIGINS_FOR_SEVERE,
    QUALITY_FAIR_THRESHOLD,
    SEVERE_THRESHOLD,
    TRUST_NORMAL_THRESHOLD,
)
from opencred.core.corroboration import (
    CorroboratedSignal,
    LocalEvidence,
    apply_corroboration,
)
from opencred.core.fingerprint import (
    exact_fingerprint,
    jaccard,
    normalize_diff,
    path_set,
    shingles,
)
from opencred.core.graph import TrustGraph
from opencred.core.manifests import (
    ManifestParseResult,
    parse_manifest,
)
from opencred.core.minhash import (
    estimate_similarity,
    minhash_signature,
)
from opencred.core.models import (
    Assertion,
    AssertionKind,
    ContributionEvent,
    ContributionEventKind,
    OpenCredModel,
    PullRequestRecord,
    RepoId,
    TrustEdge,
    to_canonical_json,
)
from opencred.core.newcomer import is_newcomer
from opencred.core.propagation import (
    PathChoice,
    best_path_per_origin,
    path_weight,
)
from opencred.core.quality import (
    QualityConfig,
    QualityEvidence,
    contribution_quality_evidence,
)
from opencred.core.telemetry import (
    TelemetryEntry,
    TelemetryLoadResult,
    TelemetryPayload,
    TelemetryStatus,
    load_telemetry,
    telemetry_campaign_risk,
)
from opencred.core.triage import (
    TriageDecision,
    TriageOutcome,
    decide,
)

__all__ = [
    "CAMPAIGN_ALERT_THRESHOLD",
    "CAMPAIGN_BURST_MIN_PRS",
    "CAMPAIGN_LOW_THRESHOLD",
    "CAMPAIGN_MIN_AUTHORS",
    "CAMPAIGN_MIN_REPOS",
    "CAMPAIGN_SIMILARITY_THRESHOLD",
    "CAMPAIGN_WINDOW_HOURS",
    "EXTERNAL_SINGLE_DENOUNCE_CAP",
    "LOCAL_DENOUNCE_WEIGHT",
    "MIN_INDEPENDENT_ORIGINS_FOR_SEVERE",
    "QUALITY_FAIR_THRESHOLD",
    "SEVERE_THRESHOLD",
    "TRUST_NORMAL_THRESHOLD",
    "__version__",
    "Assertion",
    "AssertionKind",
    "CampaignCandidate",
    "CampaignDetectionResult",
    "ContributionEvent",
    "ContributionEventKind",
    "CorroboratedSignal",
    "ExternalSignal",
    "LocalEvidence",
    "ManifestParseResult",
    "OpenCredModel",
    "PathChoice",
    "PullRequestRecord",
    "QualityConfig",
    "QualityEvidence",
    "RepoId",
    "TelemetryEntry",
    "TelemetryLoadResult",
    "TelemetryPayload",
    "TelemetryStatus",
    "TriageDecision",
    "TriageOutcome",
    "TrustEdge",
    "TrustGraph",
    "UnionFind",
    "aggregate_external",
    "apply_corroboration",
    "best_path_per_origin",
    "calculate_pr_similarity",
    "cap_group_influence",
    "contribution_quality_evidence",
    "decide",
    "detect_campaigns",
    "estimate_similarity",
    "exact_fingerprint",
    "find_mutual_groups",
    "is_newcomer",
    "jaccard",
    "load_telemetry",
    "minhash_signature",
    "normalize_diff",
    "parse_manifest",
    "path_set",
    "path_weight",
    "shingles",
    "telemetry_campaign_risk",
    "to_canonical_json",
]
