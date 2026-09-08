#!/usr/bin/env python3
"""Submit exactly one attested synthetic four-condition Qwen3.6 GPU smoke."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.batch_script_attestation import (  # noqa: E402
    submit_with_controller_attestation,
)
from cmpilot.qwen36_candidate import sha256_file  # noqa: E402
from cmpilot.qwen36_qualification import write_canonical_json  # noqa: E402
from cmpilot.qualification_runtime_paths import runtime_path_record  # noqa: E402
from cmpilot.synthetic_memory_gpu import (  # noqa: E402
    ARTIFACT_ROOT,
    BATCH_PATH,
    GPU_FREEZE_PATH,
    MODEL_ID,
    MODEL_REVISION,
    QUALIFICATION_RESULT_SHA256,
    SOURCE_CPU_VALIDATION_SHA256,
    SOURCE_MANIFEST_SHA256,
    validate_gpu_freeze,
)
from scripts.qwen36_server_port import (  # noqa: E402
    MAX_BIND_ATTEMPTS,
    SELECTION_METHOD,
    base_url,
    candidate_schedule,
)


SQUEUE = Path("/slurm/bin/squeue")
SACCT = Path("/slurm/bin/sacct")
JOB_NAME = "qwen36-synth-memory-smoke-v1"
PREFLIGHT = ARTIFACT_ROOT / "cpu-preflight/gpu-smoke-ready-v2/preflight-result.json"
SUBMISSION = ARTIFACT_ROOT / "submissions/synthetic-four-condition-v1"


def _run(command: tuple[str, ...], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--begin", default="now+2minutes")
    args = parser.parse_args()
    freeze = validate_gpu_freeze(ROOT)
    batch = (ROOT / BATCH_PATH).resolve(strict=True)
    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    if (
        preflight.get("overall") != "PASS"
        or not all(preflight.get("checks", {}).values())
        or preflight.get("freeze_sha256") != freeze["sha256"]
        or preflight.get("batch_sha256") != sha256_file(batch)
        or preflight.get("qualification_result_sha256")
        != QUALIFICATION_RESULT_SHA256
        or preflight.get("source_manifest_sha256") != SOURCE_MANIFEST_SHA256
        or preflight.get("source_cpu_validation_sha256")
        != SOURCE_CPU_VALIDATION_SHA256
    ):
        raise RuntimeError("synthetic GPU smoke preflight is not the exact all-check PASS")
    if sha256_file(
        ROOT / "qualification/qwen36-v1/qualification-result.json"
    ) != QUALIFICATION_RESULT_SHA256:
        raise RuntimeError("authoritative Qwen3.6 qualification result changed")
    qualification = json.loads(
        (ROOT / "qualification/qwen36-v1/qualification-result.json").read_text(
            encoding="utf-8"
        )
    )
    if (
        qualification.get("final_qualification_decision") != "PASS"
        or qualification.get("competence_count", {}).get("passed") != 4
    ):
        raise RuntimeError("Qwen3.6 has not retained its 4/5 qualification PASS")
    status = _run(("git", "-C", str(ROOT), "status", "--porcelain"))
    if status.returncode or status.stdout:
        raise RuntimeError("project worktree must be clean before synthetic GPU submission")
    commit = _run(("git", "-C", str(ROOT), "rev-parse", "HEAD"))
    if commit.returncode:
        raise RuntimeError(commit.stderr)

    queue = _run((str(SQUEUE), "-h", "-u", "s224049759", "-o", "%i|%j|%T"))
    if queue.returncode:
        raise RuntimeError(f"could not inspect Slurm queue: {queue.stderr}")
    active = [
        line
        for line in queue.stdout.splitlines()
        if len(line.split("|")) >= 2 and line.split("|")[1] == JOB_NAME
    ]
    prohibited_active = [
        line
        for line in queue.stdout.splitlines()
        if any(
            marker in line.casefold()
            for marker in ("security-triplet", "memory-treatment")
        )
    ]
    history = _run(
        (
            str(SACCT),
            "-X",
            "--starttime",
            "2026-08-12",
            "--name",
            JOB_NAME,
            "--noheader",
            "--parsable2",
            "--format",
            "JobIDRaw,JobName,State",
        )
    )
    if history.returncode:
        raise RuntimeError(f"could not inspect Slurm history: {history.stderr}")
    historical = [line for line in history.stdout.splitlines() if line.strip("|")]
    jobs_root = ARTIFACT_ROOT / "jobs"
    existing_jobs = sorted(path.name for path in jobs_root.iterdir()) if jobs_root.exists() else []
    if active or historical or existing_jobs or SUBMISSION.exists() or prohibited_active:
        raise RuntimeError(
            "duplicate or out-of-scope GPU evidence exists: "
            f"active={active}, historical={historical}, artifacts={existing_jobs}, "
            f"prohibited_active={prohibited_active}"
        )

    runtime_budget = runtime_path_record(
        job_id="99999999999999999999",
        task_id="synthetic-memory-smoke-v1",
        persistent_artifact_root=jobs_root,
    )
    if not runtime_budget["pass"]:
        raise RuntimeError("synthetic GPU runtime IPC path exceeds the threshold")
    result = submit_with_controller_attestation(
        batch,
        evidence_dir=SUBMISSION,
        begin=args.begin,
    )
    if not result.get("pass") or not result.get("job_id"):
        print(json.dumps(result, sort_keys=True))
        return 1
    job_id = str(result["job_id"])
    runtime = runtime_path_record(
        job_id=job_id,
        task_id="synthetic-memory-smoke-v1",
        persistent_artifact_root=jobs_root,
    )
    if not runtime["pass"]:
        raise RuntimeError("submitted job ID unexpectedly exceeds the IPC path budget")
    ports = candidate_schedule(job_id)
    record = {
        "artifact_destination": str(jobs_root / job_id),
        "controller_batch_script_sha256": result["attestation"][
            "controller_digest"
        ],
        "freeze_sha256": freeze["sha256"],
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION},
        "preflight_path": str(PREFLIGHT),
        "preflight_sha256": sha256_file(PREFLIGHT),
        "project_commit": commit.stdout.strip(),
        "requested_resources": {
            "cpus": 16,
            "gpu_type": "NVIDIA A100-PCIE-40GB",
            "gpus": 2,
            "memory_gib": 192,
            "nodes": 1,
        },
        "runtime_directory": runtime["runtime_directory"],
        "schema": "synthetic-memory-gpu-smoke-submission-v1",
        "scientific_evidence": False,
        "server_port_policy": {
            "candidate_base_urls": [base_url(port) for port in ports],
            "candidate_ports": list(ports),
            "host": "127.0.0.1",
            "max_bind_attempts": MAX_BIND_ATTEMPTS,
            "selection_method": SELECTION_METHOD,
        },
        "slurm_job_id": job_id,
        "source_batch_script": str(batch),
        "source_batch_script_sha256": sha256_file(batch),
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "submitted_job_count": 1,
        "treatment_conditions": [
            "A_NO_MEMORY",
            "B_APPLICABLE_SOURCE_VALID",
            "C_NON_APPLICABLE_SOURCE_VALID",
            "D_ORACLE_COMPLETED",
        ],
    }
    write_canonical_json(SUBMISSION / "submission-record.json", record)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
