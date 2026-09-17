#!/usr/bin/env python3
"""Run the whole suite. Equivalent to `pytest -q`, and the house entry point."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    sys.exit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=root))
