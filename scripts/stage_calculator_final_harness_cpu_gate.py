#!/usr/bin/env python3
"""Stage one immutable, structurally validated calculator-final-harness CPU gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.calculator_final_harness_cpu_job import (  # noqa: E402
    DEFAULT_ARTIFACT_ROOT,
    DEFAULT_JOB_25642,
    DEFAULT_MODEL_CACHE,
    stage_calculator_final_harness_cpu_gate,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pre-submit-directory", type=Path, required=True)
    parser.add_argument("--expected-environment-fingerprint", required=True)
    parser.add_argument("--expected-runtime-content-digest", required=True)
    parser.add_argument("--expected-model-cache-digest", required=True)
    parser.add_argument(
        "--job-25642-artifacts", type=Path, default=DEFAULT_JOB_25642
    )
    parser.add_argument("--model-cache-root", type=Path, default=DEFAULT_MODEL_CACHE)
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ARTIFACT_ROOT)
    arguments = parser.parse_args()
    bundle = stage_calculator_final_harness_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=arguments.pre_submit_directory,
        job_25642_artifacts=arguments.job_25642_artifacts,
        model_cache_root=arguments.model_cache_root,
        expected_environment_fingerprint=arguments.expected_environment_fingerprint,
        expected_runtime_content_digest=arguments.expected_runtime_content_digest,
        expected_model_cache_digest=arguments.expected_model_cache_digest,
        artifact_root=arguments.artifact_root,
    )
    print(
        json.dumps(
            {
                "driver_argument_count": len(bundle.driver_arguments),
                "driver_arguments": list(bundle.driver_arguments),
                "driver_path": str(bundle.driver.path),
                "driver_sha256": bundle.driver.sha256,
                "pre_submit_directory": str(bundle.pre_submit_directory),
                "project_manifest": str(bundle.project_manifest),
                "project_snapshot": str(bundle.project_snapshot),
                "runtime_manifest": str(bundle.runtime_manifest),
                "script_validation": bundle.script_validation,
                "submitted_script": str(bundle.submitted_script),
                "submitted_script_sha256": bundle.submitted_script_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
