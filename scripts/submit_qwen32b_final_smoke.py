#!/usr/bin/env python3
"""Submit and controller-attest one bounded Qwen32B final technical smoke."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.batch_script_attestation import (  # noqa: E402
    submit_with_controller_attestation,
)
from cmpilot.qwen32b_final_smoke import (  # noqa: E402
    ARTIFACT_ROOT,
    BATCH_PATH,
    FROZEN_TAG,
    FROZEN_TAG_TARGET,
    SMOKE_ID,
    build_preflight,
    sha256_file,
    write_new_json,
)


JOB_NAME = SMOKE_ID
DEFAULT_EVIDENCE = ARTIFACT_ROOT / "submissions/primary"


def command(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, default=ROOT / BATCH_PATH)
    parser.add_argument("--evidence-directory", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--begin", default="now+1minute")
    arguments = parser.parse_args(argv)

    batch = arguments.script.resolve(strict=True)
    preflight = build_preflight(ROOT)
    status = command(("git", "-C", str(ROOT), "status", "--porcelain"))
    if status.returncode != 0 or status.stdout:
        raise RuntimeError("project worktree must be clean before GPU submission")
    commit = command(("git", "-C", str(ROOT), "rev-parse", "HEAD"))
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr)
    tag = command(("git", "-C", str(ROOT), "rev-list", "-n", "1", FROZEN_TAG))
    if tag.returncode != 0 or tag.stdout.strip() != FROZEN_TAG_TARGET:
        raise RuntimeError("historical Qwen32B qualification tag moved")

    queue = command(
        ("/slurm/bin/squeue", "-h", "-u", "s224049759", "-o", "%i|%j|%T")
    )
    if queue.returncode != 0:
        raise RuntimeError(f"could not inspect Slurm queue: {queue.stderr}")
    active = [
        line
        for line in queue.stdout.splitlines()
        if len(line.split("|")) >= 2 and line.split("|")[1] == JOB_NAME
    ]
    if active:
        raise RuntimeError(f"Qwen32B final smoke already active: {active}")

    jobs = ARTIFACT_ROOT / "jobs"
    existing_jobs = sorted(path.name for path in jobs.iterdir()) if jobs.is_dir() else []
    if existing_jobs:
        raise RuntimeError(
            "Qwen32B final smoke already has immutable job artifacts; "
            "freeze a new smoke version for a rerun"
        )
    if arguments.evidence_directory.exists() or arguments.evidence_directory.is_symlink():
        raise FileExistsError(
            f"Qwen32B smoke submission evidence exists: {arguments.evidence_directory}"
        )

    result = submit_with_controller_attestation(
        batch,
        evidence_dir=arguments.evidence_directory,
        begin=arguments.begin,
    )
    write_new_json(
        arguments.evidence_directory / "pre-submission-queue.json",
        {
            "active_matching_jobs": active,
            "checked_at_utc": datetime.now(UTC).isoformat(),
            "queue_exit_code": queue.returncode,
            "queue_output": queue.stdout,
        },
    )
    write_new_json(
        arguments.evidence_directory / "technical-smoke-preflight.json", preflight
    )
    if not result.get("pass") or not result.get("job_id"):
        print(json.dumps(result, sort_keys=True))
        return 1
    job_id = str(result["job_id"])
    record = {
        "artifact_destination": str(ARTIFACT_ROOT / "jobs" / job_id),
        "confirmatory": False,
        "controller_batch_script_sha256": result["attestation"][
            "controller_digest"
        ],
        "frozen_historical_tag": FROZEN_TAG,
        "frozen_historical_tag_target": FROZEN_TAG_TARGET,
        "model_id": preflight["model_profile"]["model_id"],
        "model_revision": preflight["model_profile"]["model_revision"],
        "project_commit": commit.stdout.strip(),
        "requested_resources": preflight["resources"],
        "schema": "qwen32b-final-technical-smoke-submission-v2",
        "scientific_evidence": False,
        "slurm_job_id": job_id,
        "smoke_id": SMOKE_ID,
        "source_batch_script_path": str(batch),
        "source_batch_script_sha256": sha256_file(batch),
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "submission_once": True,
        "task_id": preflight["fixture"]["task_id"],
    }
    write_new_json(arguments.evidence_directory / "submission-record.json", record)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
