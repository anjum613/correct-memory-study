#!/usr/bin/env python3
"""Run the deterministic HTTPX URL functional oracle."""

from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.dont_write_bytecode = True

from probe_support import oracle_main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(oracle_main("functional"))
