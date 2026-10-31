"""OpenCred core domain logic."""

__version__ = "0.1.0"

from opencred.core.aggregate import (
    ExternalSignal,
    aggregate_external,
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
from opencred.core.propagation import (
    PathChoice,
    best_path_per_origin,
    path_weight,
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
    "TrustEdge",
    "TrustGraph",
    "aggregate_external",
    "best_path_per_origin",
    "parse_manifest",
    "path_weight",
    "to_canonical_json",
]
