#!/usr/bin/env python3
"""Project-owned entry point for Qwen32B guided-backend gates."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.guided_backend import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
