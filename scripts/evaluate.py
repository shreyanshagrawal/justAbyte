#!/usr/bin/env python3
"""OpenCred Simulation Evaluation CLI Script.

Runs simulation evaluation across seeds and verifies gates.

Usage:
    python scripts/evaluate.py --seeds 1 2 3 --gates examples/gates.json
"""

import sys

from opencred.simulation.evaluate import main

if __name__ == "__main__":
    sys.exit(main())
