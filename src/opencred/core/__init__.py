"""OpenCred core domain logic."""

__version__ = "0.1.0"

from opencred.core.aggregate import (
    ExternalSignal,
    aggregate_external,
)
from opencred.core.clusters import (
    cap_group_influence,
    find_mutual_groups,
)
from opencred.core.config import (
    EXTERNAL_SINGLE_DENOUNCE_CAP,
    LOCAL_DENOUNCE_WEIGHT,
    MIN_INDEPENDENT_ORIGINS_FOR_SEVERE,
    SEVERE_THRESHOLD,
)
from opencred.core.corroboration import (
    CorroboratedSignal,
    LocalEvidence,
    apply_corroboration,
)
from opencred.core.graph import TrustGraph
from opencred.core.manifests import (
    ManifestParseResult,
    parse_manifest,
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

__all__ = [
    "EXTERNAL_SINGLE_DENOUNCE_CAP",
    "LOCAL_DENOUNCE_WEIGHT",
    "MIN_INDEPENDENT_ORIGINS_FOR_SEVERE",
    "SEVERE_THRESHOLD",
    "__version__",
    "Assertion",
    "AssertionKind",
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
    "TrustEdge",
    "TrustGraph",
    "aggregate_external",
    "apply_corroboration",
    "best_path_per_origin",
    "cap_group_influence",
    "contribution_quality_evidence",
    "find_mutual_groups",
    "is_newcomer",
    "parse_manifest",
    "path_weight",
    "to_canonical_json",
]
