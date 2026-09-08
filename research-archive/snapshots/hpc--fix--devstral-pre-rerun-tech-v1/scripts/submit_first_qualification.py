#!/usr/bin/env python3
"""Submit and attest exactly the first frozen no-memory qualification task."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.batch_script_attestation import (  # noqa: E402
    submit_with_controller_attestation,
)
from cmpilot.qualification import (  # noqa: E402
    FROZEN_HARNESS_COMMIT,
    FROZEN_TAG,
    SHARED_ARTIFACT_ROOT,
    load_json,
    load_suite_manifest,
    sha256_file,
    write_canonical_json,
)


JOB_NAME = "qwen32b-qnm-p01"
FIRST_TASK_ID = "qnm-p01-interval-merge"
DEFAULT_EVIDENCE = SHARED_ARTIFACT_ROOT / "submissions" / FIRST_TASK_ID


def _command(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cpu-gate",
        type=Path,
        default=SHARED_ARTIFACT_ROOT / "cpu-preflight/cpu-preflight-result.json",
    )
    parser.add_argument(
        "--suite-manifest",
        type=Path,
        default=ROOT / "qualification/qwen32b-v1/suite-manifest.json",
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=ROOT / "slurm/qwen32b_qualification_task.sbatch",
    )
    parser.add_argument("--evidence-directory", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--begin", default="now+2minutes")
    arguments = parser.parse_args()

    cpu = load_json(arguments.cpu_gate.resolve(strict=True))
    if cpu.get("overall") != "PASS" or not all(cpu.get("checks", {}).values()):
        raise RuntimeError("mandatory CPU preflight is not an all-check PASS")
    suite_path = arguments.suite_manifest.resolve(strict=True)
    suite = load_suite_manifest(suite_path)
    if suite["first_task_id"] != FIRST_TASK_ID:
        raise RuntimeError("suite first-task assignment differs from submission script")
    task_record = next(
        record for record in suite["tasks"] if record["task_id"] == FIRST_TASK_ID
    )
    task_manifest = ROOT / task_record["manifest_path"]
    if sha256_file(task_manifest) != task_record["manifest_sha256"]:
        raise RuntimeError("first task manifest changed after suite freeze")
    freeze = ROOT / suite["freeze_manifest"]["path"]
    if sha256_file(freeze) != suite["freeze_manifest"]["sha256"]:
        raise RuntimeError("stack freeze manifest changed after suite freeze")

    status = _command(("git", "-C", str(ROOT), "status", "--porcelain"))
    if status.returncode != 0 or status.stdout:
        raise RuntimeError("project worktree must be clean before GPU submission")
    project_commit = _command(("git", "-C", str(ROOT), "rev-parse", "HEAD"))
    if project_commit.returncode != 0:
        raise RuntimeError(project_commit.stderr)
    tag_target = _command(
        ("git", "-C", str(ROOT), "rev-list", "-n", "1", FROZEN_TAG)
    )
    if tag_target.stdout.strip() != FROZEN_HARNESS_COMMIT:
        raise RuntimeError("qualified stack tag target changed")

    queue = _command(
        (
            "/slurm/bin/squeue",
            "-h",
            "-u",
            "s224049759",
            "-o",
            "%i|%j|%T",
        )
    )
    if queue.returncode != 0:
        raise RuntimeError(f"could not inspect Slurm queue: {queue.stderr}")
    active = [
        line
        for line in queue.stdout.splitlines()
        if len(line.split("|")) >= 2 and line.split("|")[1] == JOB_NAME
    ]
    if active:
        raise RuntimeError(f"qualification job already active: {active}")
    if arguments.evidence_directory.exists() or arguments.evidence_directory.is_symlink():
        raise FileExistsError(
            f"first-task submission evidence already exists: {arguments.evidence_directory}"
        )

    result = submit_with_controller_attestation(
        arguments.script.resolve(strict=True),
        evidence_dir=arguments.evidence_directory,
        begin=arguments.begin,
    )
    write_canonical_json(
        arguments.evidence_directory / "pre-submission-queue.json",
        {
            "active_matching_jobs": active,
            "checked_at_utc": datetime.now(UTC).isoformat(),
            "queue_exit_code": queue.returncode,
            "queue_output": queue.stdout,
        },
    )
    if not result["pass"] or not result.get("job_id"):
        print(json.dumps(result, sort_keys=True))
        return 1
    job_id = str(result["job_id"])
    task = load_json(task_manifest)
    record = {
        "artifact_destination": str(
            Path(task["artifact_destination"]) / job_id
        ),
        "controller_copy_sha256": result["attestation"]["controller_digest"],
        "freeze_manifest_sha256": sha256_file(freeze),
        "freeze_tag": FROZEN_TAG,
        "freeze_tag_target": FROZEN_HARNESS_COMMIT,
        "project_commit": project_commit.stdout.strip(),
        "schema": "qwen32b-first-qualification-submission-v1",
        "slurm_job_id": job_id,
        "source_script_path": str(arguments.script.resolve(strict=True)),
        "source_script_sha256": sha256_file(arguments.script),
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "task_id": FIRST_TASK_ID,
        "task_manifest_sha256": sha256_file(task_manifest),
    }
    write_canonical_json(arguments.evidence_directory / "submission-record.json", record)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
