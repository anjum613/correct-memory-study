#!/usr/bin/env python3
"""Submit and attest exactly one Qwen3.6 model-load/request smoke job."""

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
from cmpilot.qwen36_candidate import (  # noqa: E402
    ARTIFACT_ROOT,
    FROZEN_TAG,
    FROZEN_TAG_TARGET,
    MODEL_ID,
    MODEL_REVISION,
    QWEN25_RESULT,
    QWEN25_RESULT_SHA256,
    QUALIFICATION_NAMESPACE,
    sha256_file,
    write_canonical_json,
)


JOB_NAME = "qwen36-load-smoke-v1"
TECHNICAL_RERUN_OF = "25938"
TECHNICAL_RERUN_NUMBER = 1
TECHNICAL_ROOT_SMOKE = "25933"
DEFAULT_EVIDENCE = ARTIFACT_ROOT / (
    "submissions/model-load-request-smoke-v1-technical-rerun-1-of-25938"
)


def command(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cpu-gate",
        type=Path,
        default=ARTIFACT_ROOT / "cpu-preflight-v4/cpu-preflight-result.json",
    )
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        default=ROOT / QUALIFICATION_NAMESPACE / "candidate-freeze-manifest.json",
    )
    parser.add_argument(
        "--interpreter-contract",
        type=Path,
        default=ROOT / QUALIFICATION_NAMESPACE / "smoke-interpreter-contract.json",
    )
    parser.add_argument(
        "--script",
        type=Path,
        default=ROOT / "slurm/qwen36_model_load_request_smoke.sbatch",
    )
    parser.add_argument("--evidence-directory", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--begin", default="now+2minutes")
    arguments = parser.parse_args()

    cpu_gate = arguments.cpu_gate.resolve(strict=True)
    candidate = arguments.candidate_manifest.resolve(strict=True)
    interpreter_contract = arguments.interpreter_contract.resolve(strict=True)
    batch = arguments.script.resolve(strict=True)
    cpu = json.loads(cpu_gate.read_text(encoding="utf-8"))
    candidate_sha = sha256_file(candidate)
    contract_sha = sha256_file(interpreter_contract)
    if cpu.get("overall") != "PASS" or not all(cpu.get("checks", {}).values()):
        raise RuntimeError("mandatory Qwen3.6 CPU preflight is not an all-check PASS")
    if cpu.get("candidate_freeze_manifest_sha256") != candidate_sha:
        raise RuntimeError("candidate manifest changed after CPU preflight")
    if cpu.get("smoke_interpreter_contract_sha256") != contract_sha:
        raise RuntimeError("interpreter contract changed after CPU preflight")
    if sha256_file(ROOT / QWEN25_RESULT) != QWEN25_RESULT_SHA256:
        raise RuntimeError("historical Qwen2.5 result changed")

    status = command(("git", "-C", str(ROOT), "status", "--porcelain"))
    if status.returncode != 0 or status.stdout:
        raise RuntimeError("project worktree must be clean before GPU submission")
    commit = command(("git", "-C", str(ROOT), "rev-parse", "HEAD"))
    if commit.returncode != 0:
        raise RuntimeError(commit.stderr)
    tag = command(("git", "-C", str(ROOT), "rev-list", "-n", "1", FROZEN_TAG))
    if tag.returncode != 0 or tag.stdout.strip() != FROZEN_TAG_TARGET:
        raise RuntimeError("historical Qwen2.5 harness tag moved")

    queue = command(
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
        raise RuntimeError(f"Qwen3.6 serving smoke already active: {active}")
    if arguments.evidence_directory.exists() or arguments.evidence_directory.is_symlink():
        raise FileExistsError(
            f"Qwen3.6 smoke submission evidence exists: {arguments.evidence_directory}"
        )

    result = submit_with_controller_attestation(
        batch,
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
    record = {
        "artifact_destination": str(ARTIFACT_ROOT / "smoke/jobs" / job_id),
        "candidate_freeze_manifest_sha256": candidate_sha,
        "controller_batch_script_sha256": result["attestation"][
            "controller_digest"
        ],
        "frozen_historical_tag": FROZEN_TAG,
        "frozen_historical_tag_target": FROZEN_TAG_TARGET,
        "job_purpose": "model_load_and_one_openai_compatible_request_only",
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "project_commit": commit.stdout.strip(),
        "requested_resources": {
            "cpus": 16,
            "gpu_type": "NVIDIA A100-PCIE-40GB",
            "gpus": 2,
            "host_memory": "192G",
            "nodes": 1,
            "tensor_parallel_size": 2,
        },
        "schema": "qwen36-model-load-request-smoke-submission-v1",
        "slurm_job_id": job_id,
        "source_batch_script_path": str(batch),
        "source_batch_script_sha256": sha256_file(batch),
        "smoke_interpreter_contract_sha256": contract_sha,
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "technical_rerun_number": TECHNICAL_RERUN_NUMBER,
        "technical_rerun_of": TECHNICAL_RERUN_OF,
        "technical_root_smoke": TECHNICAL_ROOT_SMOKE,
        "treatment": "no_memory",
    }
    write_canonical_json(
        arguments.evidence_directory / "submission-record.json", record
    )
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
