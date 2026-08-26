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
    build_run_matrix,
    load_experiment_manifest,
    write_new_canonical_json,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--expected-manifest-sha256")
    args = parser.parse_args(argv)
    try:
        manifest, manifest_sha256 = load_experiment_manifest(
            args.manifest, expected_sha256=args.expected_manifest_sha256
        )
        matrix = build_run_matrix(
            manifest, experiment_manifest_sha256=manifest_sha256
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
