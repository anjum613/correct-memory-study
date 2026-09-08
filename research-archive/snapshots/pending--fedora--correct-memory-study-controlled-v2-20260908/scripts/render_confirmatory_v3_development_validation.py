#!/usr/bin/env python3
"""Render the development-only confirmatory V3 validation artifact as YAML."""

from pathlib import Path

from cmpilot.development_validation_v3 import (
    build_development_validation_record,
    render_yaml,
)


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    print(render_yaml(build_development_validation_record(ROOT)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
