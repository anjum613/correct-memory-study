#!/usr/bin/env python3
"""Validate and submit one frozen Qwen3.6 no-memory qualification task."""

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
    FROZEN_TAG,
    FROZEN_TAG_TARGET,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    QWEN25_RESULT,
    QWEN25_RESULT_SHA256,
    SOURCE_SUITE,
    build_suite_reference,
    sha256_file,
)
from cmpilot.qwen36_qualification import (  # noqa: E402
    ALL_TASKS,
    ENVIRONMENT_CONTENT_DIGEST,
    ENVIRONMENT_FINGERPRINT,
    PRIMARY_TASKS,
    QUALIFICATION_FREEZE,
    QWEN36_ARTIFACT_ROOT,
    QWEN36_PYTHON,
    RESERVE_TASKS,
    SEED_SCHEDULE,
    SUITE_REFERENCE,
    validate_freeze_manifest,
    validate_seed_schedule,
    write_canonical_json,
)
from cmpilot.qualification_runtime_paths import runtime_path_record  # noqa: E402


SQUEUE = Path("/slurm/bin/squeue")
SACCT = Path("/slurm/bin/sacct")
CPU_GATE = QWEN36_ARTIFACT_ROOT / "cpu-preflight-qualification-freeze-v2"


def run(argv: tuple[str, ...], *, timeout: int = 180) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def batch_path(task_id: str) -> Path:
    return ROOT / "slurm" / f"qwen36_{task_id.replace('-', '_')}.sbatch"


def job_name(task_id: str) -> str:
    return "qwen36-" + task_id.replace("qnm-", "")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", choices=ALL_TASKS, required=True)
    parser.add_argument("--begin", default="now+2minutes")
    parser.add_argument("--primary-decision", type=Path)
    arguments = parser.parse_args()
    task_id = arguments.task_id
    role = "primary" if task_id in PRIMARY_TASKS else "reserve"
    if task_id in RESERVE_TASKS:
        if arguments.primary_decision is None:
            raise RuntimeError("reserve submission requires the frozen 3/5 primary decision")
        decision = json.loads(arguments.primary_decision.read_text(encoding="utf-8"))
        if decision.get("primary_competence_passes") != 3 or decision.get(
            "decision"
        ) != "BORDERLINE":
            raise RuntimeError("reserves are permitted only for exactly 3/5 primary passes")

    freeze_path = (ROOT / QUALIFICATION_FREEZE).resolve(strict=True)
    freeze = validate_freeze_manifest(ROOT, freeze_path)
    schedule = validate_seed_schedule(ROOT / SEED_SCHEDULE)["seeds"]
    seed = schedule[task_id]
    cpu_path = CPU_GATE / "cpu-preflight-result.json"
    cpu = json.loads(cpu_path.read_text(encoding="utf-8"))
    if cpu.get("overall") != "PASS" or not all(cpu.get("checks", {}).values()):
        raise RuntimeError("Qwen3.6 post-freeze CPU gate is not an all-check PASS")
    if cpu.get("qualification_freeze_sha256") != freeze["sha256"]:
        raise RuntimeError("CPU gate covered a different qualification freeze")
    if cpu.get("seeds", {}).get(task_id) != seed:
        raise RuntimeError("CPU gate covered a different task seed")

    suite_reference = build_suite_reference(ROOT)
    if not suite_reference.get("all_task_components_byte_identical"):
        raise RuntimeError("frozen qualification task identities changed")
    task_identity = next(
        row for row in suite_reference["tasks"] if row["task_id"] == task_id
    )
    if sha256_file(ROOT / QWEN25_RESULT) != QWEN25_RESULT_SHA256:
        raise RuntimeError("historical Qwen2.5 result changed")
    tag = run(("git", "-C", str(ROOT), "rev-list", "-n", "1", FROZEN_TAG))
    if tag.returncode or tag.stdout.strip() != FROZEN_TAG_TARGET:
        raise RuntimeError("historical Qwen2.5 tag moved")
    status = run(("git", "-C", str(ROOT), "status", "--porcelain"))
    if status.returncode or status.stdout:
        raise RuntimeError("project worktree must be clean before GPU submission")
    commit = run(("git", "-C", str(ROOT), "rev-parse", "HEAD"))
    if commit.returncode:
        raise RuntimeError(commit.stderr)

    batch = batch_path(task_id).resolve(strict=True)
    text = batch.read_text(encoding="utf-8")
    required = (
        f"TASK_ID={task_id}",
        f"TASK_SEED={seed}",
        f"TASK_ROLE={role}",
        f"MODEL_REVISION={MODEL_REVISION}",
        f"EXPECTED_FREEZE_SHA256={freeze['sha256']}",
        "--dtype bfloat16",
        "--tensor-parallel-size 2",
        "--max-model-len 32768",
        "--gpu-memory-utilization 0.90",
        "--reasoning-parser qwen3",
        "--language-model-only",
        'RUNTIME_SCRATCH=/tmp/cmq-$SLURM_JOB_ID',
    )
    if not all(value in text for value in required):
        raise RuntimeError("batch differs from frozen Qwen3.6 configuration")
    if "memory treatment" in text.casefold() or "reference.patch" in text:
        raise RuntimeError("batch exposes a forbidden treatment or reference solution")

    name = job_name(task_id)
    queue = run((str(SQUEUE), "-h", "-u", "s224049759", "-o", "%i|%j|%T"))
    if queue.returncode:
        raise RuntimeError(f"could not inspect Slurm queue: {queue.stderr}")
    active = [
        line
        for line in queue.stdout.splitlines()
        if len(line.split("|")) >= 2 and line.split("|")[1] == name
    ]
    history = run(
        (
            str(SACCT),
            "-X",
            "--starttime",
            "2026-08-09",
            "--name",
            name,
            "--noheader",
            "--parsable2",
            "--format",
            "JobIDRaw,JobName,State",
        )
    )
    if history.returncode:
        raise RuntimeError(f"could not inspect Slurm history: {history.stderr}")
    historical = [line for line in history.stdout.splitlines() if line.strip("|")]
    artifacts = QWEN36_ARTIFACT_ROOT / "tasks" / task_id / "jobs"
    submission = QWEN36_ARTIFACT_ROOT / "submissions" / f"{task_id}-{role}"
    preflight = QWEN36_ARTIFACT_ROOT / "pre-submissions" / task_id
    existing_artifacts = sorted(path.name for path in artifacts.iterdir()) if artifacts.exists() else []
    if active or historical or existing_artifacts or submission.exists() or preflight.exists():
        raise RuntimeError(
            "duplicate Qwen3.6 qualification evidence exists: "
            f"active={active}, history={historical}, artifacts={existing_artifacts}"
        )

    preflight.mkdir(parents=True, mode=0o700)
    environment_command = run(
        (
            str(QWEN36_PYTHON),
            str(ROOT / "scripts/verify_qwen36_environment.py"),
            "--output-directory",
            str(preflight / "environment-verification"),
            "--expected-fingerprint",
            str(ROOT / "qualification/qwen36-v1/environment-fingerprint.json"),
            "--expected-content",
            str(ROOT / "qualification/qwen36-v1/environment-content-digest.json"),
        ),
        timeout=600,
    )
    (preflight / "environment.stdout").write_text(
        environment_command.stdout, encoding="utf-8"
    )
    (preflight / "environment.stderr").write_text(
        environment_command.stderr, encoding="utf-8"
    )
    if environment_command.returncode:
        raise RuntimeError("live Qwen3.6 environment verification failed")
    environment = json.loads(
        (preflight / "environment-verification/result.json").read_text(encoding="utf-8")
    )
    if (
        environment.get("pass") is not True
        or environment.get("content", {}).get("actual_content_sha256")
        != ENVIRONMENT_CONTENT_DIGEST
    ):
        raise RuntimeError("live Qwen3.6 environment identity changed")

    maximum_runtime = runtime_path_record(
        job_id="99999999999999999999",
        task_id=task_id,
        persistent_artifact_root=artifacts,
    )
    if not maximum_runtime["pass"]:
        raise RuntimeError("runtime IPC path exceeds the project threshold")
    pre_submission = {
        "active_matching_jobs": active,
        "batch_script": str(batch),
        "batch_script_sha256": sha256_file(batch),
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "environment_content_digest": ENVIRONMENT_CONTENT_DIGEST,
        "environment_fingerprint": ENVIRONMENT_FINGERPRINT,
        "freeze_manifest_sha256": freeze["sha256"],
        "historical_matching_jobs": historical,
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "snapshot": str(MODEL_SNAPSHOT)},
        "pass": True,
        "project_commit": commit.stdout.strip(),
        "role": role,
        "runtime_path_budget": maximum_runtime,
        "schema": "qwen36-qualification-pre-submission-v1",
        "seed": seed,
        "task_identity": task_identity,
        "task_id": task_id,
        "treatment": "no_memory",
    }
    write_canonical_json(preflight / "pre-submission-validation.json", pre_submission)

    result = submit_with_controller_attestation(
        batch,
        evidence_dir=submission,
        begin=arguments.begin,
    )
    if not result.get("pass") or not result.get("job_id"):
        print(json.dumps(result, sort_keys=True))
        return 1
    job_id = str(result["job_id"])
    runtime = runtime_path_record(
        job_id=job_id,
        task_id=task_id,
        persistent_artifact_root=artifacts,
    )
    if not runtime["pass"]:
        raise RuntimeError("submitted job ID unexpectedly exceeds IPC path budget")
    record = {
        "artifact_destination": str(artifacts / job_id),
        "controller_batch_script_sha256": result["attestation"]["controller_digest"],
        "cpu_preflight": str(cpu_path),
        "environment_content_digest": ENVIRONMENT_CONTENT_DIGEST,
        "environment_fingerprint": ENVIRONMENT_FINGERPRINT,
        "freeze_manifest_sha256": freeze["sha256"],
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION},
        "project_commit": commit.stdout.strip(),
        "role": role,
        "runtime_directory": runtime["runtime_directory"],
        "schema": "qwen36-qualification-submission-v1",
        "seed": seed,
        "slurm_job_id": job_id,
        "source_batch_script": str(batch),
        "source_batch_script_sha256": sha256_file(batch),
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "suite_reference_sha256": sha256_file(ROOT / SUITE_REFERENCE),
        "task_identity": task_identity,
        "task_manifest_sha256": task_identity["task_manifest_sha256"],
        "task_id": task_id,
        "treatment": "no_memory",
    }
    write_canonical_json(submission / "submission-record.json", record)
    write_canonical_json(submission / "submitted-runtime-path.json", runtime)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
