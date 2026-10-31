"""Smoke test for OpenCred core."""

import opencred.core


def test_core_version() -> None:
    """Assert package version string is 0.1.0."""
    assert opencred.core.__version__ == "0.1.0"
