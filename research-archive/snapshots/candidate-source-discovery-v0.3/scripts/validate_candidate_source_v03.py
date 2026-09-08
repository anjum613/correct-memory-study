#!/usr/bin/env python3
"""Validate the additive candidate-source v0.3 freeze offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.candidate_source_v03 import (  # noqa: E402
    CandidateSourceV03Error,
    validate_v03_specification,
)


DEFAULT_V02 = ROOT / "benchmark-selection/discovery/prospective-v0.2"
DEFAULT_V03 = ROOT / "benchmark-selection/discovery/prospective-v0.3"
DEFAULT_AUDIT = (
    ROOT
    / "benchmark-selection/discovery/audits/"
    "source-specification-v0.2-final-preexecution-audit.json"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--v02-directory", type=Path, default=DEFAULT_V02)
    parser.add_argument("--v03-directory", type=Path, default=DEFAULT_V03)
    parser.add_argument("--audit", type=Path, default=DEFAULT_AUDIT)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        result = validate_v03_specification(
            v02_directory=arguments.v02_directory.resolve(),
            v03_directory=arguments.v03_directory.resolve(),
            audit_path=arguments.audit.resolve(),
        )
    except (OSError, CandidateSourceV03Error) as error:
        print(
            json.dumps(
                {
                    "error": str(error),
                    "error_code": getattr(error, "code", "SPECIFICATION_IO_ERROR"),
                    "pass": False,
                },
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
