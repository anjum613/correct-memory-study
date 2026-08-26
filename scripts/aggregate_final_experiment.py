#!/usr/bin/env python3
"""Aggregate frozen final-experiment outputs into objective paper-ready tables."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.final_experiment import (  # noqa: E402
    FinalExperimentError,
    aggregate_run_results,
    load_run_matrix,
    write_new_canonical_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-matrix-sha256")
    args = parser.parse_args(argv)
    try:
        matrix, matrix_sha256 = load_run_matrix(
            args.matrix, expected_sha256=args.expected_matrix_sha256
        )
        aggregation = aggregate_run_results(matrix, args.run_root)
        aggregation_sha256 = write_new_canonical_json(args.output, aggregation)
    except (OSError, FinalExperimentError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "aggregation_path": str(args.output),
                "aggregation_sha256": aggregation_sha256,
                "matrix_sha256": matrix_sha256,
                "run_count": aggregation["run_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
