#!/usr/bin/env python3
"""Validate and submit one frozen remaining no-memory primary task."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


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
    VLLM_PYTHON,
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


EXPECTED_FREEZE_SHA256 = (
    "d828512fb206e157eb99ac0a1929b5633f3a2a1b1a30693a4a4d2f193deea0c1"
)
EXPECTED_SUITE_SHA256 = (
    "67a97e7ec0452907d80da681b128021d65a9205664ce7ff6be90944e92ba9c48"
)
EXPECTED_ENVIRONMENT_FINGERPRINT = (
    "6afe3a785d3d96956e8eca1e57276637ac02f9793cbeb1fcc1955924f6277071"
)
CPU_GATE = SHARED_ARTIFACT_ROOT / "cpu-preflight-ipc-fix-25908"
JOB_25887 = Path("/home/s224049759/run-artifacts/qwen32b-calculator/25887")
JOB_25913 = (
    SHARED_ARTIFACT_ROOT / "tasks/qnm-p01-interval-merge/jobs/25913"
)
SUITE_PATH = ROOT / "qualification/qwen32b-v1/suite-manifest.json"
SBATCH = Path("/slurm/bin/sbatch")
SACCT = Path("/slurm/bin/sacct")
SQUEUE = Path("/slurm/bin/squeue")

TASKS = {
    "qnm-p02-shipment-summary": {
        "job_name": "qwen32b-qnm-p02",
        "script": ROOT / "slurm/qwen32b_qnm_p02_shipment_summary.sbatch",
    },
    "qnm-p03-page-window": {
        "job_name": "qwen32b-qnm-p03",
        "script": ROOT / "slurm/qwen32b_qnm_p03_page_window.sbatch",
    },
    "qnm-p04-record-parser": {
        "job_name": "qwen32b-qnm-p04",
        "script": ROOT / "slurm/qwen32b_qnm_p04_record_parser.sbatch",
    },
    "qnm-p05-event-replay": {
        "job_name": "qwen32b-qnm-p05",
        "script": ROOT / "slurm/qwen32b_qnm_p05_event_replay.sbatch",
    },
}


def _command(argv: tuple[str, ...], *, timeout: int = 60) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        argv,
        text=True,
        capture_output=True,
        check=False,
        timeout=timeout,
    )


def _preserve_process(path: Path, completed: subprocess.CompletedProcess[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    write_canonical_json(
        path.with_suffix(".json"),
        {
            "argv": completed.args,
            "exit_code": completed.returncode,
            "schema": "qwen32b-qualification-pre-submission-process-v1",
        },
    )
    path.with_suffix(".stdout").write_text(completed.stdout, encoding="utf-8")
    path.with_suffix(".stderr").write_text(completed.stderr, encoding="utf-8")


def _require_25913_technical_validity() -> dict[str, Any]:
    result = load_json(JOB_25913 / "run/result.json")
    dimensions = result.get("dimensions", {})
    runtime = load_json(JOB_25913 / "runtime-ipc-path-budget.json")
    cleanup = load_json(JOB_25913 / "runtime-scratch-cleanup.json")
    finalizer = load_json(JOB_25913 / "run/finalizer-state.json")
    manifest = load_json(JOB_25913 / "job-manifest.json")
    checks = {
        "artifact_manifest_pass": manifest.get("pass") is True,
        "finalizer_complete": finalizer.get("post_agent_failure_count") == 0,
        "job_exit_zero": (JOB_25913 / "job-exit-code.txt").read_text().strip() == "0",
        "runtime_cleanup_pass": cleanup.get("pass") is True,
        "runtime_path_budget_pass": runtime.get("pass") is True,
        "server_started": (JOB_25913 / "server-ready.txt").read_text().strip() == "1",
        "technical_validity": dimensions.get("technical_validity") is True,
    }
    if not all(checks.values()):
        raise RuntimeError(f"job 25913 is not technically valid: {checks}")
    return checks


def _live_environment_preflight(directory: Path) -> dict[str, Any]:
    inventory = directory / "environment-inventory.json"
    observed = directory / "environment-fingerprint.json"
    classification = directory / "environment-fingerprint-classification.json"
    capture = _command(
        (
            str(VLLM_PYTHON),
            str(ROOT / "scripts/environment_fingerprint.py"),
            "capture",
            "--inventory",
            str(inventory),
            "--record",
            str(observed),
        ),
        timeout=120,
    )
    _preserve_process(directory / "environment-capture", capture)
    if capture.returncode:
        raise RuntimeError("live environment fingerprint capture failed")
    compare = _command(
        (
            str(VLLM_PYTHON),
            str(ROOT / "scripts/environment_fingerprint.py"),
            "compare",
            "--expected",
            str(JOB_25887 / "environment-fingerprint-v2-final.json"),
            "--actual",
            str(observed),
            "--classification",
            str(classification),
        ),
        timeout=120,
    )
    _preserve_process(directory / "environment-compare", compare)
    record = load_json(classification)
    if (
        compare.returncode
        or record.get("match") is not True
        or record.get("actual_sha256") != EXPECTED_ENVIRONMENT_FINGERPRINT
    ):
        raise RuntimeError("live frozen environment fingerprint mismatch")
    return record


def _validate_batch(script: Path, task_id: str, job_name: str) -> None:
    text = script.resolve(strict=True).read_text(encoding="utf-8")
    required = (
        f"#SBATCH --job-name={job_name}",
        f"tasks/{task_id}/jobs",
        f"tasks/{task_id}.json",
        f"--task-id {task_id}",
        f"snapshots/{MODEL_REVISION}",
        'RUNTIME_SCRATCH="/tmp/cmq-$SLURM_JOB_ID"',
        'export TMPDIR="$RUNTIME_SCRATCH"',
        'export VLLM_RPC_BASE_PATH="$RUNTIME_SCRATCH"',
        "--tensor-parallel-size 2",
        "--max-model-len 4096",
        "--max-num-seqs 1",
        "--gpu-memory-utilization 0.90",
        "--seed 0",
        "--agent-timeout 600",
    )
    if not all(item in text for item in required):
        raise RuntimeError(f"batch identity or frozen runtime semantics missing: {script}")
    if "TECHNICAL_RERUN" in text or "qnm-p01-interval-merge" in text:
        raise RuntimeError(f"remaining-primary batch contains rerun identity: {script}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--task-id", required=True, choices=tuple(TASKS))
    parser.add_argument("--begin", default="now+2minutes")
    arguments = parser.parse_args()
    task_id = arguments.task_id
    configuration = TASKS[task_id]
    job_name = str(configuration["job_name"])
    script = Path(configuration["script"])

    cpu_result_path = CPU_GATE / "cpu-preflight-result.json"
    cpu = load_json(cpu_result_path.resolve(strict=True))
    if cpu.get("overall") != "PASS" or not all(cpu.get("checks", {}).values()):
        raise RuntimeError("updated CPU preflight is not an all-check PASS")
    budget = cpu.get("runtime_ipc_path_budget", {})
    if (
        not budget.get("pass")
        or budget.get("maximum_zmq_socket_path_bytes", 10**9)
        > ZMQ_UNIX_PATH_SAFE_MAX_BYTES
    ):
        raise RuntimeError("CPU preflight runtime IPC path budget is not safe")

    suite_path = SUITE_PATH.resolve(strict=True)
    if sha256_file(suite_path) != EXPECTED_SUITE_SHA256:
        raise RuntimeError("frozen suite manifest hash changed")
    suite = load_suite_manifest(suite_path)
    task_record = next(record for record in suite["tasks"] if record["task_id"] == task_id)
    if task_record["role"] != "primary":
        raise RuntimeError("remaining qualification launcher accepts primary tasks only")
    task_manifest = (ROOT / task_record["manifest_path"]).resolve(strict=True)
    if sha256_file(task_manifest) != task_record["manifest_sha256"]:
        raise RuntimeError("frozen task manifest hash changed")
    task = load_json(task_manifest)
    freeze = (ROOT / suite["freeze_manifest"]["path"]).resolve(strict=True)
    if sha256_file(freeze) != EXPECTED_FREEZE_SHA256:
        raise RuntimeError("qualified stack freeze manifest hash changed")
    if task["model_configuration"]["revision"] != MODEL_REVISION:
        raise RuntimeError("frozen model revision changed")
    if task.get("treatment_marker") != "no_memory":
        raise RuntimeError("qualification task is not treatment-blind no-memory")

    paths = task_paths(ROOT, task)
    oracle = validate_oracle_bundle(
        paths["oracle"],
        expected_manifest_sha256=task["immutable_external_oracle"]["manifest_sha256"],
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
        "task_manifest": task_record["manifest_sha256"],
    }
    if immutable_inputs != expected_inputs:
        raise RuntimeError("one or more frozen qualification inputs changed")

    status = _command(("git", "-C", str(ROOT), "status", "--porcelain"))
    if status.returncode != 0 or status.stdout:
        raise RuntimeError("project worktree must be clean before GPU submission")
    project_commit = _command(("git", "-C", str(ROOT), "rev-parse", "HEAD"))
    if project_commit.returncode:
        raise RuntimeError(project_commit.stderr)
    tag_target = _command(("git", "-C", str(ROOT), "rev-list", "-n", "1", FROZEN_TAG))
    if tag_target.stdout.strip() != FROZEN_HARNESS_COMMIT:
        raise RuntimeError("qualified stack tag target changed")

    _validate_batch(script, task_id, job_name)
    maximum_budget = runtime_path_record(
        job_id="99999999999999999999",
        task_id=task_id,
        persistent_artifact_root=Path(task["artifact_destination"]),
    )
    if not maximum_budget["pass"]:
        raise RuntimeError("maximum representative Slurm job ID exceeds path budget")
    job_25913_checks = _require_25913_technical_validity()

    queue = _command((str(SQUEUE), "-h", "-u", "s224049759", "-o", "%i|%j|%T"))
    if queue.returncode:
        raise RuntimeError(f"could not inspect Slurm queue: {queue.stderr}")
    active = [
        line
        for line in queue.stdout.splitlines()
        if len(line.split("|")) >= 2 and line.split("|")[1] == job_name
    ]
    if active:
        raise RuntimeError(f"qualification task already active: {active}")
    history = _command(
        (
            str(SACCT),
            "-X",
            "--starttime",
            "2026-08-09",
            "--name",
            job_name,
            "--noheader",
            "--parsable2",
            "--format",
            "JobIDRaw,JobName,State",
        )
    )
    if history.returncode:
        raise RuntimeError(f"could not inspect Slurm history: {history.stderr}")
    historical = [line for line in history.stdout.splitlines() if line.strip("|")]
    artifact_jobs = Path(task["artifact_destination"])
    existing_artifacts = sorted(path.name for path in artifact_jobs.iterdir()) if artifact_jobs.exists() else []
    evidence = SHARED_ARTIFACT_ROOT / "submissions" / f"{task_id}-primary"
    preflight_directory = SHARED_ARTIFACT_ROOT / "pre-submissions" / task_id
    if historical or existing_artifacts or evidence.exists() or preflight_directory.exists():
        raise RuntimeError(
            "duplicate qualification evidence exists: "
            f"history={historical}, artifacts={existing_artifacts}, "
            f"submission={evidence.exists()}, preflight={preflight_directory.exists()}"
        )

    preflight_directory.mkdir(parents=True, exist_ok=False)
    environment = _live_environment_preflight(preflight_directory)
    pre_submission = {
        "active_matching_jobs": active,
        "batch_script_sha256": sha256_file(script),
        "checked_at_utc": datetime.now(UTC).isoformat(),
        "cpu_preflight": str(cpu_result_path),
        "environment_fingerprint": environment,
        "historical_matching_jobs": historical,
        "immutable_inputs": immutable_inputs,
        "job_25913_technical_validity": job_25913_checks,
        "maximum_runtime_path_budget": maximum_budget,
        "model_revision": MODEL_REVISION,
        "pass": True,
        "project_commit": project_commit.stdout.strip(),
        "queue_exit_code": queue.returncode,
        "queue_output": queue.stdout,
        "schema": "qwen32b-remaining-primary-pre-submission-v1",
        "task_id": task_id,
    }
    write_canonical_json(preflight_directory / "pre-submission-validation.json", pre_submission)

    result = submit_with_controller_attestation(
        script.resolve(strict=True),
        evidence_dir=evidence,
        begin=arguments.begin,
    )
    if not result["pass"] or not result.get("job_id"):
        print(json.dumps(result, sort_keys=True))
        return 1
    job_id = str(result["job_id"])
    actual_runtime = runtime_path_record(
        job_id=job_id,
        task_id=task_id,
        persistent_artifact_root=Path(task["artifact_destination"]),
    )
    if not actual_runtime["pass"]:
        raise RuntimeError("submitted job ID unexpectedly exceeds path budget")
    write_canonical_json(evidence / "submitted-runtime-path.json", actual_runtime)
    record = {
        "artifact_destination": str(Path(task["artifact_destination"]) / job_id),
        "controller_copy_sha256": result["attestation"]["controller_digest"],
        "cpu_preflight_result": str(cpu_result_path),
        "environment_fingerprint": environment["actual_sha256"],
        "freeze_manifest_sha256": sha256_file(freeze),
        "freeze_tag": FROZEN_TAG,
        "freeze_tag_target": FROZEN_HARNESS_COMMIT,
        "immutable_inputs": immutable_inputs,
        "project_commit": project_commit.stdout.strip(),
        "runtime_directory": actual_runtime["runtime_directory"],
        "schema": "qwen32b-remaining-primary-submission-v1",
        "slurm_job_id": job_id,
        "source_script_path": str(script.resolve(strict=True)),
        "source_script_sha256": sha256_file(script),
        "submitted_at_utc": datetime.now(UTC).isoformat(),
        "suite_manifest_sha256": sha256_file(suite_path),
        "task_id": task_id,
        "task_manifest_sha256": sha256_file(task_manifest),
    }
    write_canonical_json(evidence / "submission-record.json", record)
    print(json.dumps(record, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
