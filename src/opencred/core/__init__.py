"""OpenCred core domain logic."""

__version__ = "0.1.0"

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

__all__ = [
    "__version__",
    "Assertion",
    "AssertionKind",
    "ContributionEvent",
    "ContributionEventKind",
    "ManifestParseResult",
    "OpenCredModel",
    "PullRequestRecord",
    "RepoId",
    "TrustEdge",
    "parse_manifest",
    "to_canonical_json",
]
