"""OpenCred core domain logic."""

__version__ = "0.1.0"

from opencred.core.aggregate import (
    ExternalSignal,
    aggregate_external,
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
from opencred.core.propagation import (
    PathChoice,
    best_path_per_origin,
    path_weight,
)
from opencred.core.telemetry import (
    TelemetryEntry,
    TelemetryLoadResult,
    TelemetryPayload,
    TelemetryStatus,
    load_telemetry,
    telemetry_campaign_risk,
)

__all__ = [
    "__version__",
    "Assertion",
    "AssertionKind",
    "ContributionEvent",
    "ContributionEventKind",
    "ExternalSignal",
    "ManifestParseResult",
    "OpenCredModel",
    "PathChoice",
    "PullRequestRecord",
    "RepoId",
    "TelemetryEntry",
    "TelemetryLoadResult",
    "TelemetryPayload",
    "TelemetryStatus",
    "TrustEdge",
    "TrustGraph",
    "aggregate_external",
    "best_path_per_origin",
    "estimate_similarity",
    "exact_fingerprint",
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
