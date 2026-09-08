#!/usr/bin/env python3
"""Stage the server-command extraction CPU gate on shared storage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.server_command_cpu_job import stage_server_command_cpu_gate  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pre-submit-directory", type=Path, required=True)
    parser.add_argument("--expected-environment-fingerprint", required=True)
    parser.add_argument("--expected-content-digest", required=True)
    parser.add_argument(
        "--artifact-root",
        type=Path,
        default=Path("/home/s224049759/run-artifacts/server-command-extraction"),
    )
    parser.add_argument("--job-name", default="server-command-extraction")
    arguments = parser.parse_args()
    bundle = stage_server_command_cpu_gate(
        project_root=ROOT,
        pre_submit_directory=arguments.pre_submit_directory,
        expected_environment_fingerprint=arguments.expected_environment_fingerprint,
        expected_content_digest=arguments.expected_content_digest,
        artifact_root=arguments.artifact_root,
        job_name=arguments.job_name,
    )
    print(
        json.dumps(
            {
                "driver_path": str(bundle.driver.path),
                "driver_sha256": bundle.driver.sha256,
                "command_plan": str(bundle.command_plan),
                "command_plan_sha256": bundle.command_plan_sha256,
                "pre_submit_directory": str(bundle.pre_submit_directory),
                "runtime_manifest": str(bundle.runtime_manifest),
                "submitted_script": str(bundle.submitted_script),
                "submitted_script_sha256": bundle.submitted_script_sha256,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
