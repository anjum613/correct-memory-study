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
    load_run_matrix,
)
from cmpilot.final_reporting import (  # noqa: E402
    build_analysis_report,
    write_analysis_outputs,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("matrix", type=Path)
    parser.add_argument("run_root", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--csv",
        type=Path,
        help="CSV output path (default: replace the JSON output suffix with .csv)",
    )
    parser.add_argument("--expected-matrix-sha256")
    parser.add_argument(
        "--require-complete",
        action="store_true",
        help="refuse to write tables unless every matrix run is terminally finalized",
    )
    args = parser.parse_args(argv)
    csv_path = args.csv if args.csv is not None else args.output.with_suffix(".csv")
    try:
        matrix, matrix_sha256 = load_run_matrix(
            args.matrix, expected_sha256=args.expected_matrix_sha256
        )
        aggregation = build_analysis_report(
            matrix,
            args.run_root,
            require_complete=args.require_complete,
        )
        aggregation["matrix_sha256"] = matrix_sha256
        digests = write_analysis_outputs(args.output, csv_path, aggregation)
    except (OSError, FinalExperimentError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "aggregation_path": str(args.output),
                "aggregation_sha256": digests["json_sha256"],
                "completed_run_count": aggregation["completed_run_count"],
                "csv_path": str(csv_path),
                "csv_sha256": digests["csv_sha256"],
                "incomplete_run_count": aggregation["incomplete_run_count"],
                "matrix_sha256": matrix_sha256,
                "run_count": aggregation["run_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
