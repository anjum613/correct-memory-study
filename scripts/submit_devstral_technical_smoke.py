#!/usr/bin/env python3
"""Submit one controller-attested Devstral technical smoke after READY."""

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
from cmpilot.devstral_profile import MODEL_ID, MODEL_REVISION, SERVER_PYTHON  # noqa: E402
from cmpilot.devstral_snapshot_freeze import sha256_file  # noqa: E402
from cmpilot.devstral_technical_smoke import (  # noqa: E402
    ARTIFACT_ROOT,
    BATCH_PATH,
    SMOKE_ID,
    runtime_integrity_from_verifier,
    write_new_json,
)


DEFAULT_EVIDENCE = ARTIFACT_ROOT / "submissions/primary"


def command(
    argv: tuple[str, ...], *, timeout: int = 60
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--script", type=Path, default=ROOT / BATCH_PATH)
    parser.add_argument("--evidence-directory", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--begin", default="now+1minute")
    arguments = parser.parse_args(argv)
    batch = arguments.script.resolve(strict=True)

    status = command(("git", "status", "--porcelain"))
    if status.returncode != 0 or status.stdout:
        raise RuntimeError("project worktree must be clean before GPU submission")
    commit = command(("git", "rev-parse", "HEAD"))
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr)
    queue = command(
        ("/slurm/bin/squeue", "-h", "-u", "s224049759", "-o", "%i|%j|%T")
    )
    if queue.returncode != 0:
        raise RuntimeError(f"could not inspect Slurm queue: {queue.stderr}")
    active = [
        line
        for line in queue.stdout.splitlines()
        if len(line.split("|")) >= 2
        and line.split("|")[1] == "devstral-small-2507-smoke-v1"
    ]
    if active:
        raise RuntimeError(f"Devstral technical smoke already active: {active}")
    jobs = ARTIFACT_ROOT / "jobs"
    existing_jobs = sorted(path.name for path in jobs.iterdir()) if jobs.is_dir() else []
    if existing_jobs:
        raise RuntimeError(
            "Devstral technical smoke already has immutable job artifacts; "
            "freeze a new smoke version for a rerun"
        )
    if arguments.evidence_directory.exists() or arguments.evidence_directory.is_symlink():
        raise FileExistsError(
            f"Devstral smoke submission evidence exists: {arguments.evidence_directory}"
        )

    verification_process = command(
        (
            str(SERVER_PYTHON),
            str(ROOT / "scripts/verify_devstral_environment.py"),
        ),
        timeout=1200,
    )
    try:
        verification = json.loads(verification_process.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError("Devstral verifier did not return JSON") from error
    if verification_process.returncode != 0:
        raise RuntimeError(
            "Devstral verifier did not authorize submission: "
            f"{verification.get('status')}"
        )
    preflight = runtime_integrity_from_verifier(ROOT, verification)

    result = submit_with_controller_attestation(
        batch,
        evidence_dir=arguments.evidence_directory,
        begin=arguments.begin,
    )
    write_new_json(
        arguments.evidence_directory / "environment-verification.json",
        verification,
    )
    write_new_json(
        arguments.evidence_directory / "technical-smoke-preflight.json",
        preflight,
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
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "project_commit": commit.stdout.strip(),
        "requested_resources": preflight["resources"],
        "schema": "devstral-technical-smoke-submission-v1",
        "scientific_evidence": False,
        "slurm_job_id": job_id,
        "smoke_id": SMOKE_ID,
        "source_batch_script_path": str(batch),
        "source_batch_script_sha256": sha256_file(batch),
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "submission_once": True,
    }
    write_new_json(arguments.evidence_directory / "submission-record.json", record)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
