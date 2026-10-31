"""OpenCred core domain logic."""

__version__ = "0.1.0"

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
    ExternalSignal,
    LocalEvidence,
    apply_corroboration,
)
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
    "PullRequestRecord",
    "QualityConfig",
    "QualityEvidence",
    "RepoId",
    "TrustEdge",
    "apply_corroboration",
    "cap_group_influence",
    "contribution_quality_evidence",
    "find_mutual_groups",
    "is_newcomer",
    "parse_manifest",
    "to_canonical_json",
]
