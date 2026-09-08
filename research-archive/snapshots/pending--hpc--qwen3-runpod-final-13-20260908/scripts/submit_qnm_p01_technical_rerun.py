#!/usr/bin/env python3
"""Submit the one permitted technical rerun of qualification job 25908."""

from __future__ import annotations

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
    MODEL_REVISION,
    SHARED_ARTIFACT_ROOT,
    load_json,
    load_suite_manifest,
    repository_content_digest,
    sha256_file,
    task_paths,
    validate_oracle_bundle,
    write_canonical_json,
)
from cmpilot.qualification_runtime_paths import (  # noqa: E402
    ZMQ_UNIX_PATH_SAFE_MAX_BYTES,
    runtime_path_record,
)


TASK_ID = "qnm-p01-interval-merge"
TECHNICAL_RERUN_OF = "25908"
TECHNICAL_RERUN_NUMBER = 1
JOB_NAMES = frozenset({"qwen32b-qnm-p01", "qwen32b-qnm-p01-r1"})
EXPECTED_FREEZE_SHA256 = (
    "d828512fb206e157eb99ac0a1929b5633f3a2a1b1a30693a4a4d2f193deea0c1"
)
EXPECTED_SUITE_SHA256 = (
    "67a97e7ec0452907d80da681b128021d65a9205664ce7ff6be90944e92ba9c48"
)
EXPECTED_TASK_SHA256 = (
    "267afbd8a18337cb1841d45ea53984ec537f75483dcffe8167e6ee42ba1ac092"
)
CPU_GATE = SHARED_ARTIFACT_ROOT / "cpu-preflight-ipc-fix-25908"
EVIDENCE = (
    SHARED_ARTIFACT_ROOT
    / "submissions/qnm-p01-interval-merge-technical-rerun-1"
)
FAILED_JOB = (
    SHARED_ARTIFACT_ROOT
    / "tasks/qnm-p01-interval-merge/jobs"
    / TECHNICAL_RERUN_OF
)
SUITE_PATH = ROOT / "qualification/qwen32b-v1/suite-manifest.json"
BATCH_SCRIPT = ROOT / "slurm/qwen32b_qualification_task.sbatch"


def _command(argv: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        timeout=60,
    )


def main() -> int:
    cpu_result_path = CPU_GATE / "cpu-preflight-result.json"
    cpu = load_json(cpu_result_path.resolve(strict=True))
    if cpu.get("overall") != "PASS" or not all(cpu.get("checks", {}).values()):
        raise RuntimeError("updated CPU preflight is not an all-check PASS")
    budget = cpu.get("runtime_ipc_path_budget", {})
    if (
        not budget.get("pass")
        or budget.get("maximum_zmq_socket_path_bytes")
        > ZMQ_UNIX_PATH_SAFE_MAX_BYTES
    ):
        raise RuntimeError("CPU preflight runtime IPC path budget is not safe")

    suite_path = SUITE_PATH.resolve(strict=True)
    if sha256_file(suite_path) != EXPECTED_SUITE_SHA256:
        raise RuntimeError("frozen suite manifest hash changed")
    suite = load_suite_manifest(suite_path)
    task_record = next(
        record for record in suite["tasks"] if record["task_id"] == TASK_ID
    )
    task_manifest = (ROOT / task_record["manifest_path"]).resolve(strict=True)
    if sha256_file(task_manifest) != EXPECTED_TASK_SHA256:
        raise RuntimeError("frozen qnm-p01 task manifest hash changed")
    task = load_json(task_manifest)
    freeze = (ROOT / suite["freeze_manifest"]["path"]).resolve(strict=True)
    if sha256_file(freeze) != EXPECTED_FREEZE_SHA256:
        raise RuntimeError("qualified stack freeze manifest hash changed")
    if task["model_configuration"]["revision"] != MODEL_REVISION:
        raise RuntimeError("frozen model revision changed")

    paths = task_paths(ROOT, task)
    oracle = validate_oracle_bundle(
        paths["oracle"],
        expected_manifest_sha256=task["immutable_external_oracle"][
            "manifest_sha256"
        ],
    )
    immutable_inputs = {
        "freeze_manifest": sha256_file(freeze),
        "oracle_bundle": oracle["bundle_sha256"],
        "oracle_manifest": oracle["manifest_sha256"],
        "reference_patch": sha256_file(paths["reference_patch"]),
        "repository_source": repository_content_digest(paths["repository"]).sha256,
        "suite_manifest": sha256_file(suite_path),
        "task_manifest": sha256_file(task_manifest),
    }
    expected_inputs = {
        "freeze_manifest": EXPECTED_FREEZE_SHA256,
        "oracle_bundle": task["immutable_external_oracle"]["bundle_sha256"],
        "oracle_manifest": task["immutable_external_oracle"]["manifest_sha256"],
        "reference_patch": task["reference_patch"]["sha256"],
        "repository_source": task["repository"]["source_sha256"],
        "suite_manifest": EXPECTED_SUITE_SHA256,
        "task_manifest": EXPECTED_TASK_SHA256,
    }
    if immutable_inputs != expected_inputs:
        raise RuntimeError("one or more frozen qualification inputs changed")

    failed_runtime = load_json(FAILED_JOB / "runtime-integrity.json")
    if (
        not failed_runtime.get("pass")
        or failed_runtime["environment_fingerprint"].get("actual_sha256")
        != "6afe3a785d3d96956e8eca1e57276637ac02f9793cbeb1fcc1955924f6277071"
        or (FAILED_JOB / "server-ready.txt").read_text(encoding="ascii").strip()
        != "0"
        or (FAILED_JOB / "run").exists()
    ):
        raise RuntimeError("job 25908 is not the recorded pre-agent technical invalidity")

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

    batch_text = BATCH_SCRIPT.read_text(encoding="utf-8")
    required_batch_text = (
        f"TECHNICAL_RERUN_OF={TECHNICAL_RERUN_OF}",
        f"TECHNICAL_RERUN_NUMBER={TECHNICAL_RERUN_NUMBER}",
        f"snapshots/{MODEL_REVISION}",
        'RUNTIME_SCRATCH="/tmp/cmq-$SLURM_JOB_ID"',
        'export VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"',
    )
    if not all(item in batch_text for item in required_batch_text):
        raise RuntimeError("technical-rerun batch script identity is incomplete")

    maximum_budget = runtime_path_record(
        job_id="99999999999999999999",
        task_id=TASK_ID,
        persistent_artifact_root=Path(task["artifact_destination"]),
    )
    if not maximum_budget["pass"]:
        raise RuntimeError("maximum representative Slurm job ID exceeds path budget")

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
        if len(line.split("|")) >= 2 and line.split("|")[1] in JOB_NAMES
    ]
    if active:
        raise RuntimeError(f"qnm-p01 qualification job already active: {active}")
    if EVIDENCE.exists() or EVIDENCE.is_symlink():
        raise FileExistsError(f"technical-rerun evidence already exists: {EVIDENCE}")

    pre_submission = {
        "active_matching_jobs": active,
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "cpu_preflight": str(cpu_result_path),
        "environment_fingerprint": failed_runtime["environment_fingerprint"],
        "immutable_inputs": immutable_inputs,
        "maximum_runtime_path_budget": maximum_budget,
        "model_revision": MODEL_REVISION,
        "pass": True,
        "queue_exit_code": queue.returncode,
        "queue_output": queue.stdout,
        "schema": "qwen32b-qnm-p01-technical-rerun-pre-submission-v1",
        "technical_rerun_number": TECHNICAL_RERUN_NUMBER,
        "technical_rerun_of": TECHNICAL_RERUN_OF,
    }
    result = submit_with_controller_attestation(
        BATCH_SCRIPT.resolve(strict=True),
        evidence_dir=EVIDENCE,
        begin="now+2minutes",
    )
    write_canonical_json(EVIDENCE / "pre-submission-validation.json", pre_submission)
    if not result["pass"] or not result.get("job_id"):
        print(json.dumps(result, sort_keys=True))
        return 1

    job_id = str(result["job_id"])
    actual_runtime = runtime_path_record(
        job_id=job_id,
        task_id=TASK_ID,
        persistent_artifact_root=Path(task["artifact_destination"]),
    )
    if not actual_runtime["pass"]:
        raise RuntimeError("submitted job ID unexpectedly exceeds path budget")
    write_canonical_json(EVIDENCE / "submitted-runtime-path.json", actual_runtime)
    record = {
        "artifact_destination": str(Path(task["artifact_destination"]) / job_id),
        "controller_copy_sha256": result["attestation"]["controller_digest"],
        "cpu_preflight_result": str(cpu_result_path),
        "freeze_manifest_sha256": sha256_file(freeze),
        "freeze_tag": FROZEN_TAG,
        "freeze_tag_target": FROZEN_HARNESS_COMMIT,
        "project_commit": project_commit.stdout.strip(),
        "runtime_directory": actual_runtime["runtime_directory"],
        "schema": "qwen32b-qnm-p01-technical-rerun-submission-v1",
        "slurm_job_id": job_id,
        "source_script_path": str(BATCH_SCRIPT.resolve(strict=True)),
        "source_script_sha256": sha256_file(BATCH_SCRIPT),
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "task_id": TASK_ID,
        "task_manifest_sha256": sha256_file(task_manifest),
        "technical_rerun_number": TECHNICAL_RERUN_NUMBER,
        "technical_rerun_of": TECHNICAL_RERUN_OF,
    }
    write_canonical_json(EVIDENCE / "submission-record.json", record)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
