"""Bounded, non-confirmatory Qwen32B final-harness technical smoke."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import subprocess
from typing import Any, Mapping, Sequence

from .calculator_finalizer import validate_total_finalization_artifacts
from .experiment_models import QWEN32B_PROFILE


SCHEMA = "qwen32b-final-technical-smoke-v1"
SMOKE_ID = "qwen32b-final-smoke-v1"
TASK_ID = "qnm-p01-interval-merge"
PORT = 49788
FROZEN_TAG = "qwen32b-qualification-v1"
FROZEN_TAG_TARGET = "ba039a0eaddc358d6b7174260c3b3c36169c44c0"
ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/qwen32b-final-technical-smoke/v1"
)
SUITE_PATH = Path("qualification/qwen32b-v1/suite-manifest.json")
TASK_PATH = Path("qualification/qwen32b-v1/tasks/qnm-p01-interval-merge.json")
FREEZE_PATH = Path("qualification/qwen32b-v1/freeze-manifest.json")
QUALIFICATION_RESULT_PATH = Path("qualification/qwen32b-v1/qualification-result.json")
BATCH_PATH = Path("slurm/qwen32b_final_smoke.sbatch")
RUNNER_PATH = Path("scripts/run_qualification_task.py")
EXPECTED_INPUT_HASHES = {
    SUITE_PATH: "67a97e7ec0452907d80da681b128021d65a9205664ce7ff6be90944e92ba9c48",
    TASK_PATH: "267afbd8a18337cb1841d45ea53984ec537f75483dcffe8167e6ee42ba1ac092",
    FREEZE_PATH: "d828512fb206e157eb99ac0a1929b5633f3a2a1b1a30693a4a4d2f193deea0c1",
    QUALIFICATION_RESULT_PATH: (
        "af494119487c6a31d7e6924511c81c5bdfa0aeacf9607a28b4f5f43178ecc29a"
    ),
    RUNNER_PATH: "1b9d05b606f01279c9aadd6b2cf6033a4e5d3f8f448636675122901d063d3032",
    Path("src/cmpilot/qualification_runner.py"): (
        "209a88c5dca91bffc73fe345c36a23c5f605b0905e968468f7dcf8a86dcb9eb3"
    ),
}


class QwenFinalSmokeError(RuntimeError):
    """The frozen technical-smoke contract is not satisfied."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QwenFinalSmokeError(f"expected JSON object: {path}")
    return value


def write_new_json(path: Path, value: Mapping[str, Any] | Sequence[Any]) -> None:
    """Write canonical JSON once; smoke evidence is never overwritten."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def _git(project: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ("git", "-C", str(project), *arguments),
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _prior_fixture_use(project: Path) -> dict[str, Any]:
    result = load_json(project / QUALIFICATION_RESULT_PATH)
    rows = result.get("primary_tasks")
    if not isinstance(rows, list):
        raise QwenFinalSmokeError("qualification result has no primary task records")
    matches = [row for row in rows if row.get("task_id") == TASK_ID]
    if len(matches) != 1:
        raise QwenFinalSmokeError("prior deterministic fixture use is not unique")
    row = matches[0]
    if row.get("job_id") != "25913" or row.get("technical_validity") is not True:
        raise QwenFinalSmokeError("prior qnm-p01 technical use changed")
    events = row.get("event_counts", {})
    if not isinstance(events, dict) or int(events.get("action_executed", 0)) < 1:
        raise QwenFinalSmokeError("prior qnm-p01 use did not execute an action")
    return {
        "job_id": row["job_id"],
        "model_request_count": row.get("model_request_count"),
        "prior_action_executed_count": events["action_executed"],
        "qualification_result_path": QUALIFICATION_RESULT_PATH.as_posix(),
        "qualification_result_sha256": EXPECTED_INPUT_HASHES[
            QUALIFICATION_RESULT_PATH
        ],
    }


def validate_batch_contract(project: Path) -> dict[str, bool]:
    text = (project / BATCH_PATH).read_text(encoding="utf-8")
    return {
        "agent_config_explicit": "--agent-config-source \"$AGENT_CONFIG\"" in text,
        "canonical_argv_executed": 'setsid "${SERVER_COMMAND[@]}"' in text,
        "canonical_profile_preflight": (
            "qwen32b_final_smoke.py\" preflight" in text
        ),
        "complete_validator": "qwen32b_final_smoke.py\" complete" in text,
        "context_not_duplicated": "--max-model-len" not in text,
        "direct_vllm_command_not_copied": "vllm.entrypoints.openai.api_server" not in text,
        "fixture": TASK_ID in text,
        "health": '"$BASE_URL/health"' in text,
        "models": '"$BASE_URL/v1/models"' in text,
        "no_requeue": "#SBATCH --no-requeue" in text,
        "one_node": "#SBATCH --nodes=1" in text,
        "short_walltime": "#SBATCH --time=00:30:00" in text,
        "two_a100": "#SBATCH --gres=gpu:a100:2" in text,
    }


def build_preflight(project: Path, *, port: int = PORT) -> dict[str, Any]:
    """Validate all CPU-side inputs and return the exact server argv."""
    project = project.resolve(strict=True)
    verified_profile_inputs = QWEN32B_PROFILE.verify_static_inputs(project)
    input_hashes = {
        path.as_posix(): sha256_file(project / path)
        for path in EXPECTED_INPUT_HASHES
    }
    task = load_json(project / TASK_PATH)
    suite = load_json(project / SUITE_PATH)
    freeze = load_json(project / FREEZE_PATH)
    tag = _git(project, "rev-list", "-n", "1", FROZEN_TAG)
    ancestry = _git(project, "merge-base", "--is-ancestor", FROZEN_TAG_TARGET, "HEAD")
    batch_checks = validate_batch_contract(project)
    suite_rows = suite.get("tasks", [])
    matching_suite_rows = [
        row for row in suite_rows if isinstance(row, dict) and row.get("task_id") == TASK_ID
    ]
    checks = {
        "batch_contract": all(batch_checks.values()),
        "fixture_is_no_memory": task.get("treatment_marker") == "no_memory",
        "fixture_manifest": task.get("task_id") == TASK_ID,
        "fixture_previously_used": bool(_prior_fixture_use(project)),
        "freeze_hash_bound_by_suite": (
            suite.get("freeze_manifest", {}).get("sha256")
            == EXPECTED_INPUT_HASHES[FREEZE_PATH]
        ),
        "frozen_harness_is_ancestor": ancestry.returncode == 0,
        "frozen_tag_unchanged": (
            tag.returncode == 0 and tag.stdout.strip() == FROZEN_TAG_TARGET
        ),
        "input_hashes": all(
            input_hashes[path.as_posix()] == expected
            for path, expected in EXPECTED_INPUT_HASHES.items()
        ),
        "model_id": task.get("model_configuration", {}).get("model_id")
        == QWEN32B_PROFILE.model_id,
        "model_revision": task.get("model_configuration", {}).get("revision")
        == QWEN32B_PROFILE.model_revision,
        "profile_static_inputs": bool(verified_profile_inputs),
        "qualification_freeze_schema": freeze.get("schema")
        == "qwen32b-qualified-stack-freeze-v1",
        "suite_fixture_unique": (
            len(matching_suite_rows) == 1
            and matching_suite_rows[0].get("manifest_sha256")
            == EXPECTED_INPUT_HASHES[TASK_PATH]
        ),
    }
    if not all(checks.values()):
        raise QwenFinalSmokeError(f"Qwen32B smoke preflight failed: {checks}")
    return {
        "batch_checks": batch_checks,
        "checks": checks,
        "confirmatory": False,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fixture": {
            "task_id": TASK_ID,
            "task_manifest": TASK_PATH.as_posix(),
            "task_manifest_sha256": EXPECTED_INPUT_HASHES[TASK_PATH],
            "prior_use": _prior_fixture_use(project),
        },
        "frozen_harness_commit": FROZEN_TAG_TARGET,
        "input_hashes": input_hashes,
        "model_profile": QWEN32B_PROFILE.identity_record(),
        "model_profile_sha256": QWEN32B_PROFILE.identity_sha256(),
        "pass": True,
        "protocol_version": SCHEMA,
        "resources": {
            "cpus": 8,
            "dtype": "bfloat16",
            "gpus": 2,
            "gpu_type": "a100",
            "host_memory": "128G",
            "max_model_length": 4096,
            "nodes": 1,
            "tensor_parallel_size": 2,
            "walltime": "00:30:00",
        },
        "schema": SCHEMA,
        "scientific_evidence": False,
        "server_argv": list(QWEN32B_PROFILE.server_argv(port=port)),
        "smoke_id": SMOKE_ID,
    }


def write_preflight(project: Path, output_directory: Path, *, port: int = PORT) -> dict[str, Any]:
    output_directory.mkdir(parents=True, exist_ok=True)
    record = build_preflight(project, port=port)
    write_new_json(output_directory / "server-command.json", record["server_argv"])
    write_new_json(output_directory / "technical-smoke-preflight.json", record)
    return record


def validate_runtime_integrity(
    fingerprint_path: Path, content_path: Path
) -> dict[str, Any]:
    fingerprint = load_json(fingerprint_path)
    content = load_json(content_path)
    environment = QWEN32B_PROFILE.environment
    checks = {
        "content_authoritative": content.get("authoritative") is True,
        "content_digest": content.get("canonical_inventory_sha256")
        == environment.environment_content_digest,
        "content_schema": content.get("schema") == "environment-content-digest-v1",
        "fingerprint_digest": fingerprint.get("canonical_inventory_sha256")
        == environment.environment_fingerprint,
        "fingerprint_interpreter": fingerprint.get("interpreter")
        == str(environment.server_python),
        "fingerprint_schema": fingerprint.get("schema") == "environment-fingerprint-v2",
    }
    return {
        "checks": checks,
        "environment_id": environment.environment_id,
        "pass": all(checks.values()),
        "schema": "qwen32b-final-smoke-runtime-integrity-v1",
    }


def _models(response: Mapping[str, Any]) -> tuple[str, ...]:
    rows = response.get("data")
    if not isinstance(rows, list):
        return ()
    return tuple(
        str(row["id"])
        for row in rows
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    )


def validate_completion(
    run_artifact: Path,
    *,
    health_status_path: Path,
    models_response_path: Path,
    runtime_integrity_path: Path,
    server_cleanup_path: Path,
    runner_exit_code: int,
) -> dict[str, Any]:
    """Validate action execution, total finalization, and clean shutdown."""
    finalization = validate_total_finalization_artifacts(run_artifact)
    result = load_json(run_artifact / "result.json")
    metrics = load_json(run_artifact / "trajectory-metrics.json")
    shutdown = load_json(run_artifact / "shutdown.json")
    runtime_integrity = load_json(runtime_integrity_path)
    server_cleanup = load_json(server_cleanup_path)
    models = _models(load_json(models_response_path))
    try:
        health_status = int(health_status_path.read_text(encoding="ascii").strip())
    except (OSError, ValueError) as error:
        raise QwenFinalSmokeError("health status is unreadable") from error
    checks = {
        "action_executed": int(metrics.get("executed_action_count", 0)) >= 1,
        "authorization_policy": metrics.get("policy_version")
        == QWEN32B_PROFILE.scientific_boundary.command_policy_version,
        "finalization_complete": finalization.get("pass") is True,
        "health_200": health_status == 200,
        "model_request": int(metrics.get("model_request_count", 0)) >= 1,
        "model_revision": result.get("model_revision")
        == QWEN32B_PROFILE.model_revision,
        "model_served": QWEN32B_PROFILE.served_model_name in models,
        "parser_accepted_action": int(metrics.get("command_count", 0)) >= 1,
        "production_action_boundary": metrics.get("technical_validity") == "PASS",
        "runner_exit": runner_exit_code == 0,
        "runtime_integrity": runtime_integrity.get("pass") is True,
        "server_cleanup": server_cleanup.get("pass") is True,
        "shutdown_finalizer_stage": shutdown.get("pass") is True,
        "task_identity": result.get("task_id") == TASK_ID,
        "treatment": result.get("treatment") == "no_memory",
    }
    return {
        "checks": checks,
        "confirmatory": False,
        "finalization": finalization,
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "model_revision": QWEN32B_PROFILE.model_revision,
        "pass": all(checks.values()),
        "runner_exit_code": runner_exit_code,
        "schema": "qwen32b-final-technical-smoke-result-v1",
        "scientific_evidence": False,
        "smoke_id": SMOKE_ID,
        "task_id": TASK_ID,
    }


__all__ = [
    "ARTIFACT_ROOT",
    "BATCH_PATH",
    "FROZEN_TAG",
    "FROZEN_TAG_TARGET",
    "PORT",
    "QwenFinalSmokeError",
    "SCHEMA",
    "SMOKE_ID",
    "TASK_ID",
    "build_preflight",
    "load_json",
    "sha256_file",
    "validate_batch_contract",
    "validate_completion",
    "validate_runtime_integrity",
    "write_new_json",
    "write_preflight",
]
