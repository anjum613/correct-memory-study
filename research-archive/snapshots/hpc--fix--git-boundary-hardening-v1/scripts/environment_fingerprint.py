#!/usr/bin/env python3
"""Project-owned entry point for environment-fingerprint-v2."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.environment_fingerprint import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
