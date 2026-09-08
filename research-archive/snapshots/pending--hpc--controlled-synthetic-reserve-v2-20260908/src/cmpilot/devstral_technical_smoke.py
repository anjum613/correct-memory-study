"""Bounded, non-confirmatory Devstral technical-smoke evidence."""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .calculator_finalizer import (
    initialize_finalizer_state,
    run_total_finalization,
    validate_total_finalization_artifacts,
)
from .devstral_profile import (
    ENVIRONMENT_CONTENT_DIGEST_SHA256,
    ENVIRONMENT_FINGERPRINT_SHA256,
    MODEL_ID,
    MODEL_REVISION,
    PROFILE_ID,
    build_devstral_server_argv,
    validate_devstral_server_argv,
)
from .devstral_snapshot_freeze import SNAPSHOT_FREEZE, sha256_file
from .integrations.miniswe.command_authorization import (
    POLICY_VERSION,
    authorize_command,
)
from .qwen32b_final_smoke import (
    EXPECTED_INPUT_HASHES,
    FREEZE_PATH,
    FROZEN_TAG,
    FROZEN_TAG_TARGET,
    QUALIFICATION_RESULT_PATH,
    RUNNER_PATH,
    SUITE_PATH,
    TASK_ID,
    TASK_PATH,
)


SCHEMA = "devstral-technical-smoke-v2"
SMOKE_ID = "devstral-small-2507-technical-smoke-v2"
PORT = 49827
BATCH_PATH = Path("slurm/devstral_small_2507_technical_smoke.sbatch")
ARTIFACT_ROOT = Path(
    "/home/s224049759/final-experiment-artifacts/"
    "devstral-small-2507-technical-smoke/v2"
)
EXPECTED_SNAPSHOT_FREEZE_SHA256 = (
    "2486602a374814152283f8a48fb6a0108bc5c96eeabf17a6e911cf8107e4a011"
)
EXPECTED_SNAPSHOT_IDENTITY_SHA256 = (
    "e90b3af5301c42112c1711c919851aefd4c366bfc237c022c641add7ab7c8eaf"
)


class DevstralTechnicalSmokeError(RuntimeError):
    """A technical-smoke prerequisite or result is invalid."""


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DevstralTechnicalSmokeError(f"expected JSON object: {path}")
    return value


def write_new_json(
    path: Path, value: Mapping[str, Any] | Sequence[Any]
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, sort_keys=True)
        stream.write("\n")


def validate_batch_contract(project: Path) -> dict[str, bool]:
    text = (project / BATCH_PATH).read_text(encoding="utf-8")
    return {
        "agent_config_explicit": "--agent-config-source \"$AGENT_CONFIG\"" in text,
        "bf16_profile_only": "--dtype" not in text,
        "canonical_argv_executed": 'setsid "${SERVER_COMMAND[@]}"' in text,
        "context_not_duplicated": "--max-model-len" not in text,
        "direct_vllm_command_not_copied": (
            "vllm.entrypoints.openai.api_server" not in text
        ),
        "devstral_command_extractor": (
            "extract_devstral_server_command.py" in text
            and "extract_server_command.py" not in text
        ),
        "fixture_nonconfirmatory": 'printf \'%s\\n\' false > "$ARTIFACT_DIR/confirmatory.txt"' in text,
        "health": '"$BASE_URL/health"' in text,
        "models": '"$BASE_URL/v1/models"' in text,
        "no_quantization_override": "--quantization" not in text,
        "no_requeue": "#SBATCH --no-requeue" in text,
        "one_node": "#SBATCH --nodes=1" in text,
        "one_hour_bound": "#SBATCH --time=01:00:00" in text,
        "technical_runner": "run_devstral_calculator_smoke.py" in text,
        "two_a100": "#SBATCH --gres=gpu:a100:2" in text,
    }


def runtime_integrity_from_verifier(
    project: Path, verification: Mapping[str, Any]
) -> dict[str, Any]:
    checks = verification.get("checks")
    freeze = verification.get("snapshot_freeze")
    if not isinstance(checks, dict) or not isinstance(freeze, dict):
        raise DevstralTechnicalSmokeError("Devstral verifier output is incomplete")
    expected_inputs = {
        path.as_posix(): sha256_file(project / path)
        for path in EXPECTED_INPUT_HASHES
    }
    batch_checks = validate_batch_contract(project)
    readiness = {
        "all_existing_verifier_checks": bool(checks) and all(checks.values()),
        "batch_contract": all(batch_checks.values()),
        "environment_content": (
            verification.get("environment_content_digest", {}).get(
                "canonical_inventory_sha256"
            )
            == ENVIRONMENT_CONTENT_DIGEST_SHA256
        ),
        "environment_fingerprint": (
            verification.get("environment_fingerprint", {}).get(
                "canonical_inventory_sha256"
            )
            == ENVIRONMENT_FINGERPRINT_SHA256
        ),
        "fixture_inputs": all(
            expected_inputs[path.as_posix()] == expected
            for path, expected in EXPECTED_INPUT_HASHES.items()
        ),
        "production_ready": verification.get("production_ready") is True,
        "snapshot_freeze": (
            freeze.get("valid") is True
            and freeze.get("status") == "READY"
            and freeze.get("freeze_sha256")
            == EXPECTED_SNAPSHOT_FREEZE_SHA256
            and freeze.get("snapshot_identity_sha256")
            == EXPECTED_SNAPSHOT_IDENTITY_SHA256
            and sha256_file(project / SNAPSHOT_FREEZE)
            == EXPECTED_SNAPSHOT_FREEZE_SHA256
        ),
        "status_ready": verification.get("status") == "READY",
    }
    if not all(readiness.values()):
        raise DevstralTechnicalSmokeError(
            f"Devstral technical preflight failed: {readiness}"
        )
    command = validate_devstral_server_argv(
        build_devstral_server_argv(port=PORT)
    )
    return {
        "batch_checks": batch_checks,
        "checks": readiness,
        "confirmatory": False,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "fixture": {
            "prior_qwen_use_is_provenance_only": True,
            "task_id": TASK_ID,
            "task_manifest": str(TASK_PATH),
            "task_manifest_sha256": EXPECTED_INPUT_HASHES[TASK_PATH],
        },
        "fixture_input_sha256": expected_inputs,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "pass": True,
        "profile_id": PROFILE_ID,
        "resources": {
            "cpus": 8,
            "dtype": "bfloat16",
            "gpus": 2,
            "gpu_type": "a100",
            "host_memory": "128G",
            "max_model_length": 4096,
            "nodes": 1,
            "quantization": None,
            "tensor_parallel_size": 2,
            "walltime": "01:00:00",
        },
        "schema": "devstral-technical-smoke-runtime-integrity-v1",
        "scientific_evidence": False,
        "server_argv": list(command),
        "smoke_id": SMOKE_ID,
        "snapshot_freeze": {
            "path": str(SNAPSHOT_FREEZE),
            "sha256": EXPECTED_SNAPSHOT_FREEZE_SHA256,
            "snapshot_identity_sha256": EXPECTED_SNAPSHOT_IDENTITY_SHA256,
        },
        "status": "READY",
        "production_ready": True,
    }


def authorization_probe() -> dict[str, Any]:
    allowed = authorize_command("pytest -q")
    prohibited = authorize_command("curl https://example.invalid")
    checks = {
        "allowed_repository_command": allowed.authorized is True,
        "policy_version": (
            allowed.policy_version == prohibited.policy_version == POLICY_VERSION
        ),
        "prohibited_command_blocked": (
            prohibited.authorized is False
            and prohibited.category == "prohibited_network_access"
            and prohibited.reason == "NETWORK_ACCESS_PROHIBITED"
        ),
    }
    return {
        "allowed": allowed.as_dict(),
        "checks": checks,
        "pass": all(checks.values()),
        "prohibited": prohibited.as_dict(),
        "schema": "devstral-technical-smoke-authorization-probe-v1",
    }


def _first_jsonl(path: Path, *, classification: str | None = None) -> dict[str, Any]:
    for line in path.read_text(encoding="utf-8").splitlines():
        value = json.loads(line)
        if isinstance(value, dict) and (
            classification is None or value.get("classification") == classification
        ):
            return value
    return {}


def _peak_gpu_memory(path: Path) -> dict[str, int]:
    peaks: dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = [field.strip() for field in line.split(",")]
        if len(fields) != 3 or not fields[0].isdigit() or not fields[2].isdigit():
            continue
        peaks[fields[0]] = max(peaks.get(fields[0], 0), int(fields[2]))
    return peaks


def _run_directory(artifact: Path) -> Path | None:
    runs = artifact / "runs"
    candidates = sorted(path for path in runs.glob("smoke-*") if path.is_dir())
    if len(candidates) > 1:
        raise DevstralTechnicalSmokeError(
            "technical smoke created more than one evaluated-agent run"
        )
    return candidates[0] if candidates else None


def finalize_job(artifact: Path, *, runner_exit_code: int) -> dict[str, Any]:
    """Apply the existing total finalizer to every outer smoke outcome."""
    destination = artifact / "finalization"
    completed = destination / "authoritative-result.txt"
    if completed.is_file():
        return load_json(destination / "result.json")
    destination.mkdir(mode=0o700)
    state_path = destination / "finalizer-state.json"
    initialize_finalizer_state(state_path, run_id=artifact.name)
    run_directory = _run_directory(artifact)
    run = load_json(run_directory / "run.json") if run_directory else {}
    classification = (
        load_json(run_directory / "classification.json") if run_directory else {}
    )
    runtime = (
        load_json(artifact / "runtime-integrity.json")
        if (artifact / "runtime-integrity.json").is_file()
        else {"pass": False}
    )
    cleanup = (
        load_json(artifact / "server-cleanup.json")
        if (artifact / "server-cleanup.json").is_file()
        else {"pass": False}
    )

    def final_repository_capture() -> dict[str, Any]:
        return {
            "complete": run_directory is not None,
            "pass": run_directory is not None,
            "run_directory": str(run_directory) if run_directory else None,
        }

    def patch_generation() -> dict[str, Any]:
        path = run_directory / "final.patch" if run_directory else None
        return {
            "complete": path is not None and path.is_file(),
            "pass": path is not None and path.is_file(),
            "sha256": sha256_file(path) if path is not None and path.is_file() else None,
        }

    def immutable_oracle() -> dict[str, Any]:
        return {
            "complete": run.get("external_oracle_result") in {"pass", "fail"},
            "functional_pass": run.get("external_oracle_result") == "pass",
            "pass": run.get("external_oracle_result") in {"pass", "fail"},
        }

    def source_integrity() -> dict[str, Any]:
        checks = classification.get("success_checks", {})
        return {
            "pass": checks.get("source_template_unchanged") is True,
            "source_template_unchanged": checks.get("source_template_unchanged"),
        }

    def project_environment_cache_integrity() -> dict[str, Any]:
        return {"pass": runtime.get("pass") is True, "runtime": runtime}

    def shutdown() -> dict[str, Any]:
        return {"pass": cleanup.get("pass") is True, "server_cleanup": cleanup}

    def scratch_cleanup() -> dict[str, Any]:
        return {
            "complete": run.get("cleanup_complete") is True,
            "pass": run.get("cleanup_complete") is True,
        }

    def performance_summary() -> dict[str, Any]:
        return {
            "agent_wall_time_seconds": run.get("agent_wall_time_seconds"),
            "pass": True,
            "request_count": run.get("model_request_count"),
            "token_usage": run.get("usage_total"),
        }

    technical = bool(
        run_directory is not None
        and run.get("technical_validity") == "pass"
        and run.get("model_protocol_technical_validity") == "PASS"
    )
    outcome = run_total_finalization(
        state_path=state_path,
        artifact_directory=destination,
        termination_reason=str(run.get("termination_reason") or "MODEL_SERVER_FAILURE"),
        callbacks={
            "final_repository_capture": final_repository_capture,
            "patch_generation": patch_generation,
            "immutable_oracle": immutable_oracle,
            "source_integrity": source_integrity,
            "project_environment_cache_integrity": project_environment_cache_integrity,
            "shutdown": shutdown,
            "scratch_cleanup": scratch_cleanup,
            "performance_summary": performance_summary,
        },
        success_label="DEVSTRAL_TECHNICAL_SMOKE_VALID",
        technical_failure_label="DEVSTRAL_TECHNICAL_SMOKE_FAILURE",
        requested_exit_code=runner_exit_code,
        initial_technical_validity=technical,
        base_result={
            "confirmatory": False,
            "model_id": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "runner_exit_code": runner_exit_code,
            "scientific_evidence": False,
            "smoke_id": SMOKE_ID,
            "task_id": "calculator-engineering-smoke",
        },
        classification_dimensions={
            "functional_result": run.get("external_oracle_result"),
            "model_protocol_technical_validity": run.get(
                "model_protocol_technical_validity"
            ),
            "technical_validity": run.get("technical_validity"),
        },
    )
    return outcome.result


def validate_completion(
    artifact: Path, *, runner_exit_code: int
) -> dict[str, Any]:
    run_path = _run_directory(artifact)
    if run_path is None:
        raise DevstralTechnicalSmokeError("evaluated-agent run artifact is missing")
    run = load_json(run_path / "run.json")
    classification = load_json(run_path / "classification.json")
    runtime = load_json(artifact / "runtime-integrity.json")
    authorization = load_json(artifact / "authorization-probe.json")
    cleanup = load_json(artifact / "server-cleanup.json")
    models = load_json(artifact / "models-response.json")
    model_ids = [
        row.get("id")
        for row in models.get("data", [])
        if isinstance(row, dict)
    ]
    transport = _first_jsonl(
        run_path / "model-transport.jsonl", classification="success"
    )
    budget = _first_jsonl(run_path / "request-budgets.jsonl")
    tokenizer = budget.get("tokenizer", {})
    finalization = validate_total_finalization_artifacts(artifact / "finalization")
    health = (artifact / "health-http-status.txt").read_text().strip()
    peaks = _peak_gpu_memory(artifact / "gpu-memory-samples.csv")
    checks = {
        "action_executed": int(run.get("executed_action_count", 0)) >= 1,
        "authorization_boundary": (
            authorization.get("pass") is True
            and run.get("policy_version") == POLICY_VERSION
            and run.get("prohibited_command_executed") is False
        ),
        "finalization_complete": finalization.get("pass") is True,
        "functionality_evaluator": (
            run.get("external_oracle_result") == "pass"
            and run.get("after_test_exit_code") == 0
            and classification.get("classification") == "secure_functional_success"
        ),
        "health_200": health == "200",
        "live_generation": (
            transport.get("classification") == "success"
            and transport.get("status_code") == 200
        ),
        "mistral_serialization": (
            tokenizer.get("schema")
            == "devstral-mistral-chat-tokenizer-identity-v1"
            and tokenizer.get("response_conversion") is None
        ),
        "model_request": int(run.get("model_request_count", 0)) >= 1,
        "model_revision": runtime.get("model_revision") == MODEL_REVISION,
        "model_served": MODEL_ID in model_ids,
        "parser_accepted_action": int(run.get("command_count", 0)) >= 1,
        "peak_memory_captured": len(peaks) == 2 and all(peaks.values()),
        "runner_exit": runner_exit_code == 0,
        "runtime_integrity": runtime.get("pass") is True,
        "scientific_evidence_false": (
            load_json(artifact / "finalization/result.json").get(
                "scientific_evidence"
            )
            is False
        ),
        "server_cleanup": cleanup.get("pass") is True,
        "task_identity": run.get("task_name") == "smoke_test",
    }
    return {
        "checks": checks,
        "confirmatory": False,
        "finalization": finalization,
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "first_successful_generation": {
            "request_sha256": transport.get("request_sha256"),
            "response_sha256": transport.get("response_sha256"),
            "status_code": transport.get("status_code"),
        },
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "pass": all(checks.values()),
        "peak_gpu_memory_mib": peaks,
        "runner_exit_code": runner_exit_code,
        "schema": SCHEMA,
        "scientific_evidence": False,
        "serialization": tokenizer,
        "smoke_id": SMOKE_ID,
        "task_id": TASK_ID,
    }


__all__ = [
    "ARTIFACT_ROOT",
    "BATCH_PATH",
    "DevstralTechnicalSmokeError",
    "FROZEN_TAG",
    "FROZEN_TAG_TARGET",
    "FREEZE_PATH",
    "PORT",
    "QUALIFICATION_RESULT_PATH",
    "RUNNER_PATH",
    "SCHEMA",
    "SMOKE_ID",
    "SUITE_PATH",
    "TASK_ID",
    "TASK_PATH",
    "authorization_probe",
    "finalize_job",
    "load_json",
    "runtime_integrity_from_verifier",
    "validate_batch_contract",
    "validate_completion",
    "write_new_json",
]
