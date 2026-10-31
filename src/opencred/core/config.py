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

# ==============================================================================
# Campaign Detection Parameters (AGENTS.md rules 1, 9, 10)
#
# Starting values to be tuned by simulation, not validated optima.
# ==============================================================================

# Minimum combined similarity required to link two pull requests
# STARTING VALUE: Set to 0.7.
CAMPAIGN_SIMILARITY_THRESHOLD: float = 0.7

# Maximum elapsed time window in hours between two PRs to establish a link
# STARTING VALUE: Set to 6 hours.
CAMPAIGN_WINDOW_HOURS: float = 6.0

# Minimum distinct authors required for a connected component to qualify as a campaign candidate
# STARTING VALUE: Set to 3.
CAMPAIGN_MIN_AUTHORS: int = 3

# Minimum distinct repositories required for a connected component to qualify as
# a campaign candidate.
# STARTING VALUE: Set to 3.
CAMPAIGN_MIN_REPOS: int = 3

# Minimum number of pull requests required for burst candidate qualification
# STARTING VALUE: Set to 5.
CAMPAIGN_BURST_MIN_PRS: int = 5

# Weights for pairwise similarity components when diff fingerprints do not match exactly.
# Note: exact normalized diff fingerprint match alone is sufficient to link (similarity = 1.0).
# STARTING VALUES: Normalized diff tokens (0.5), description shingles (0.3), file paths (0.2).
CAMPAIGN_WEIGHT_DIFF: float = 0.5
CAMPAIGN_WEIGHT_DESC: float = 0.3
CAMPAIGN_WEIGHT_PATHS: float = 0.2

# Patterns for excluding benign mass pull requests (e.g., bot dependency bumps or typo sweeps).
# Configured as STARTING VALUES.
CAMPAIGN_EXCLUSION_TITLE_PATTERNS: tuple[str, ...] = (
    r"(?i)^bump\s+.*\s+from\s+",
    r"(?i)^bump\s+",
    r"(?i)^deps:\s*",
    r"(?i)^build\(deps\):",
    r"(?i)^chore\(deps\):",
    r"(?i)^fix(ed)?\s+typo(s)?",
    r"(?i)^typo(s)?\s+fix",
)

CAMPAIGN_EXCLUSION_FILE_PATTERNS: tuple[str, ...] = (
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "pipfile.lock",
    "gemfile.lock",
    "cargo.lock",
    "composer.lock",
)

CAMPAIGN_EXCLUSION_DIFF_PATTERNS: tuple[str, ...] = (
    r"""(?i)^[+-]\s*("version"|version|__version__)\s*[:=]\s*["\']v?\d+""",
)

# ==============================================================================
# Triage Decision Parameters (AGENTS.md rules 2, 6, 8, 9)
#
# Starting values to be tuned by simulation, not validated optima.
# ==============================================================================

# Campaign risk threshold at or above which an alert to investigate is triggered.
# STARTING VALUE: Set to 0.6.
CAMPAIGN_ALERT_THRESHOLD: float = 0.6

# Campaign risk threshold below which campaign risk is considered low.
# STARTING VALUE: Set to 0.3.
CAMPAIGN_LOW_THRESHOLD: float = 0.3

# Contribution quality evidence threshold required for newcomer fair review.
# STARTING VALUE: Set to 0.5.
QUALITY_FAIR_THRESHOLD: float = 0.5

# Network trust threshold required for normal standard review.
# STARTING VALUE: Set to 0.3.
TRUST_NORMAL_THRESHOLD: float = 0.3
