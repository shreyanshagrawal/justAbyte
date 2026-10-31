"""Configuration thresholds and weights for OpenCred core.

NOTE:
    All values below are STARTING VALUES to be tuned by simulation,
    not validated optima (see AGENTS.md rule 9).
"""

# Weight applied to a repository's own local denouncements.
# STARTING VALUE: Local denouncements count fully.
LOCAL_DENOUNCE_WEIGHT: float = 1.0

# Magnitude cap applied to external denouncements when only one independent
# origin repository has denounced the contributor.
# STARTING VALUE: Bounded influence of a single external origin.
EXTERNAL_SINGLE_DENOUNCE_CAP: float = 0.2

# Minimum number of distinct origin repositories required to corroborate
# a severe negative classification.
# STARTING VALUE: Requires at least 2 distinct origins.
MIN_INDEPENDENT_ORIGINS_FOR_SEVERE: int = 2

# Threshold below which network trust is considered severe (for triage).
# STARTING VALUE: Set to -0.6.
SEVERE_THRESHOLD: float = -0.6

# ==============================================================================
# Contribution Quality Evidence Parameters (AGENTS.md rule 2 & 9)
#
# Represents positive evidence that a contribution deserves fair review.
# All weights and thresholds are STARTING VALUES to be tuned by simulation.
# ==============================================================================

QUALITY_WEIGHT_ISSUE_LINK: float = 0.25
QUALITY_WEIGHT_NON_TRIVIAL_FILES: float = 0.25
QUALITY_WEIGHT_DESCRIPTIVE_CONTENT: float = 0.25
QUALITY_WEIGHT_HISTORY: float = 0.25

# Saturation constant k for historical merged PRs: 1 - exp(-merged / k)
QUALITY_HISTORY_SATURATION_K: float = 5.0

# Maximum score cap for PRs modifying solely trivial/low-value files
QUALITY_TRIVIAL_PR_CAP: float = 0.15

LOW_VALUE_FILE_PATTERNS: tuple[str, ...] = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "gemfile.lock",
    "cargo.lock",
    "composer.lock",
    ".ds_store",
)

BOILERPLATE_PHRASES: tuple[str, ...] = (
    "update readme.md",
    "update readme",
    "fix typo",
    "fixed typo",
    "update",
    "test",
    "minor fix",
    "minor changes",
    "fix",
    "changes",
    "no description",
)

