#!/usr/bin/env python3
"""Emit a validated Qwen32B server argv as NUL-delimited UTF-8."""

from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.server_command import extract_command_cli  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(extract_command_cli())
