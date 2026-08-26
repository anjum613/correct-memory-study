#!/usr/bin/env python3
"""Generate the immutable atomic-run matrix from a frozen experiment manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.final_experiment import (  # noqa: E402
    FinalExperimentError,
    PRODUCTION,
    SYNTHETIC_UNIT_TEST,
    build_run_matrix,
    load_experiment_manifest,
    write_new_canonical_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    parser.add_argument(
        "--synthetic-unit-test",
        action="store_true",
        help="diagnostic only: allow an explicitly labelled synthetic unit-test manifest",
    )
    args = parser.parse_args(argv)
    try:
        if not args.synthetic_unit_test and args.expected_manifest_sha256 is None:
            raise FinalExperimentError(
                "production generation requires --expected-manifest-sha256"
            )
        manifest, manifest_sha256 = load_experiment_manifest(
            args.manifest,
            expected_sha256=args.expected_manifest_sha256,
            allow_synthetic=args.synthetic_unit_test,
        )
        expected_purpose = SYNTHETIC_UNIT_TEST if args.synthetic_unit_test else PRODUCTION
        if manifest["purpose"] != expected_purpose:
            raise FinalExperimentError(
                f"requested {expected_purpose} generation but manifest purpose is "
                f"{manifest['purpose']}"
            )
        matrix = build_run_matrix(
            manifest,
            experiment_manifest_sha256=manifest_sha256,
            allow_synthetic=args.synthetic_unit_test,
        )
        matrix_sha256 = write_new_canonical_json(args.output, matrix)
    except (OSError, FinalExperimentError) as error:
        parser.error(str(error))
    print(
        json.dumps(
            {
                "experiment_manifest_sha256": manifest_sha256,
                "matrix_path": str(args.output),
                "matrix_sha256": matrix_sha256,
                "run_count": matrix["run_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
