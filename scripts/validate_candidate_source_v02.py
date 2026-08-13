#!/usr/bin/env python3
"""Validate the prospective v0.2 candidate-source files offline."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.candidate_source_v02 import (  # noqa: E402
    SourceProtocolError,
    validate_specification_directory,
)


DEFAULT_SPECIFICATION_DIRECTORY = (
    ROOT / "benchmark-selection/discovery/prospective-v0.2"
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--specification-directory",
        type=Path,
        default=DEFAULT_SPECIFICATION_DIRECTORY,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        result = validate_specification_directory(
            arguments.specification_directory.resolve()
        )
    except (OSError, SourceProtocolError) as error:
        code = getattr(error, "code", "SPECIFICATION_IO_ERROR")
        print(json.dumps({"error": str(error), "error_code": code, "pass": False}))
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
