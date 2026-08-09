"""Frozen Qwen3.6 no-memory qualification identity and validation."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from .qwen36_candidate import (
    ENVIRONMENT_PATH,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    SELECTED_CONTEXT_LENGTH,
    SOURCE_SUITE,
    SOURCE_SUITE_SHA256,
    TENSOR_PARALLEL_SIZE,
    canonical_json_bytes,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_FINGERPRINT = (
    "fe63e366ca33bc2392eb173281764bdb8bd543ed3ce8d36c3b3fe6727df80bab"
)
ENVIRONMENT_CONTENT_DIGEST = (
    "b36b9c47b130dba7c2a0ae60161029d3f5b0b522e8bd0f5b0f0749bae86b3a74"
)
NAMESPACE = Path("qualification/qwen36-v1")
CANDIDATE_MANIFEST = NAMESPACE / "candidate-freeze-manifest.json"
CANDIDATE_MANIFEST_SHA256 = (
    "7da6ddf4b02f2f9be92cbaa7f81376b7392598ee4a0089273d6cae66e728e0c3"
)
SUITE_REFERENCE = NAMESPACE / "suite-reference.json"
SUITE_REFERENCE_SHA256 = (
    "2403982c3d3681e746d741b357b52a7fc4e3b8b97d7219a1b46fe26f3c9200cf"
)
AGENT_CONFIG = NAMESPACE / "qualification-agent-config.json"
SEED_SCHEDULE = NAMESPACE / "qualification-seeds.json"
ADAPTER_CONTRACT = NAMESPACE / "scientific-adapter-contract.json"
SMOKE_RESULT = NAMESPACE / "smoke-result-25940.json"
QUALIFICATION_FREEZE = NAMESPACE / "qualification-freeze-manifest.json"
SMOKE_ARTIFACT = Path(
    "/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1/smoke/jobs/25940"
)
SMOKE_ARTIFACT_MANIFEST_SHA256 = (
    "86fada9dbcfde0e5b5df464af394e79f73e2d0c74d168f7a0b47b2988f4351a2"
)
QWEN36_ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/qwen36-no-memory-qualification/v1"
)
PROJECT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
MINI_SWE_PYTHON = Path(
    "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
)
QWEN36_PYTHON = ENVIRONMENT_PATH / "bin/python"
PRECISION = "bfloat16"
GPU_MEMORY_UTILIZATION = 0.90
REASONING_PARSER = "qwen3"
THINKING_MODE = "model_default_enabled"
MAX_OUTPUT_TOKENS = 8192
PROJECT_ENVIRONMENT_FINGERPRINT = (
    "6325999d4038c8c93c1c313e10a66386a5afe803bf966a951317ff12a3d35128"
)
MODEL_CONFIG_SHA256 = (
    "69db4eb7196bc8190813231b3018ca05d8c2e3abc7b1af19d55c157af44a9d9c"
)
MODEL_SNAPSHOT_SHA256 = (
    "60175a2275493bd9dd5703501539749d621e3adabeca2272279196cb6f791f99"
)
CHAT_TEMPLATE_SHA256 = (
    "e84f32a23fdda27689f868aa4a1a5621f41133e51a48d7f3efcbea2839574259"
)
GENERATION_CONFIG_SHA256 = (
    "e70c136c1b78ddc1fb0905bac8e733a4dc448d4f852a5dd75143fffc70be550e"
)
PINNED_README_SHA256 = (
    "bb936d6da51014f1edc9aa4cf9abf28d98695b7616ad56adfeeebfa752051d3d"
)
TOKENIZER_INVENTORY_SHA256 = (
    "d985a4caf1a7c4c2d3c6b58cf3f1deab195ec0f2b44d9b686a3edc93adc2cf23"
)
TOKENIZER_JSON_SHA256 = (
    "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42"
)
TOKENIZER_CONFIG_SHA256 = (
    "5186f0defcd7f232382c7f0aebcd2252d073bb921ab240e407b7ae8745d2b29b"
)

PRIMARY_TASKS = (
    "qnm-p01-interval-merge",
    "qnm-p02-shipment-summary",
    "qnm-p03-page-window",
    "qnm-p04-record-parser",
    "qnm-p05-event-replay",
)
RESERVE_TASKS = (
    "qnm-r01-dependency-order",
    "qnm-r02-ledger-transfer",
)
ALL_TASKS = PRIMARY_TASKS + RESERVE_TASKS


class Qwen36QualificationError(RuntimeError):
    """The qualification configuration differs from its predeclared identity."""


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise Qwen36QualificationError(f"expected JSON object: {path}")
    return value


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _derived_seed(task_id: str) -> int:
    value = f"qwen36-v1|{MODEL_REVISION}|{task_id}".encode("utf-8")
    return int.from_bytes(hashlib.sha256(value).digest()[:4], "big") & 0x7FFF_FFFF


def validate_seed_schedule(path: Path) -> dict[str, Any]:
    record = load_json(path)
    seeds = record.get("seeds")
    expected = {task_id: _derived_seed(task_id) for task_id in ALL_TASKS}
    checks = {
        "model_revision": record.get("model_revision") == MODEL_REVISION,
        "schema": record.get("schema") == "qwen36-qualification-seed-schedule-v1",
        "task_membership": isinstance(seeds, dict) and set(seeds) == set(ALL_TASKS),
        "deterministic_values": seeds == expected,
        "no_memory": record.get("treatment") == "no_memory",
    }
    if not all(checks.values()):
        raise Qwen36QualificationError(f"invalid seed schedule: {checks}")
    return {"checks": checks, "pass": True, "seeds": expected}


def validate_agent_config(path: Path) -> dict[str, Any]:
    record = load_json(path)
    model = record.get("model")
    expected_model = {
        "connect_timeout_seconds": 10.0,
        "context_limit": SELECTED_CONTEXT_LENGTH,
        "context_safety_margin": 32,
        "max_tokens": MAX_OUTPUT_TOKENS,
        "min_p": 0.0,
        "minimum_useful_completion": 64,
        "presence_penalty": 0.0,
        "read_timeout_seconds": 120.0,
        "repetition_penalty": 1.0,
        "samples_per_call": 1,
        "temperature": 1.0,
        "tokenizer_config_sha256": (
            "5186f0defcd7f232382c7f0aebcd2252d073bb921ab240e407b7ae8745d2b29b"
        ),
        "tokenizer_json_sha256": (
            "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42"
        ),
        "top_k": 20,
        "top_p": 0.95,
    }
    checks = {
        "agent_limits": record.get("agent")
        == {
            "cost_limit": 0.0,
            "max_consecutive_format_errors": 3,
            "step_limit": 15,
            "wall_time_limit_seconds": 450,
        },
        "environment_timeout": record.get("environment") == {"timeout": 60},
        "model_generation": model == expected_model,
    }
    if not all(checks.values()):
        raise Qwen36QualificationError(f"invalid Qwen3.6 agent config: {checks}")
    return {"checks": checks, "model": expected_model, "pass": True}


def resolved_agent_config(project: Path, task_id: str) -> dict[str, Any]:
    if task_id not in ALL_TASKS:
        raise Qwen36QualificationError(f"unknown frozen task: {task_id}")
    config_path = project / AGENT_CONFIG
    seed_path = project / SEED_SCHEDULE
    validate_agent_config(config_path)
    schedule = validate_seed_schedule(seed_path)
    value = load_json(config_path)
    value["model"] = dict(value["model"])
    value["model"]["seed"] = schedule["seeds"][task_id]
    return value


def _component(project: Path, name: str, relative: str) -> dict[str, str]:
    path = project / relative
    return {
        "component": name,
        "path": relative,
        "sha256": sha256_file(path),
    }


def build_smoke_result(artifact: Path = SMOKE_ARTIFACT) -> dict[str, Any]:
    smoke = load_json(artifact / "smoke-client-result.json")
    models = load_json(artifact / "models-response.json")
    health = load_json(artifact / "health-response.json")
    load_memory = load_json(artifact / "gpu-memory-after-load.json")
    path_budget = load_json(artifact / "runtime-ipc-path-budget.json")
    cleanup = load_json(artifact / "runtime-scratch-cleanup.json")
    server_cleanup = load_json(artifact / "server-cleanup.json")
    env_stdout = json.loads(
        (artifact / "environment-verification.stdout").read_text(encoding="utf-8")
    )
    ranks = [load_json(artifact / f"nccl-rank-{rank}.json") for rank in (0, 1)]
    manifest_digest = (artifact / "artifact-manifest.sha256").read_text().strip()
    model_row = models.get("body", {}).get("data", [{}])[0]
    checks = {
        "artifact_manifest": manifest_digest == SMOKE_ARTIFACT_MANIFEST_SHA256,
        "bf16": all(row.get("bf16_supported") for row in ranks),
        "chat": smoke.get("status") == "PASS"
        and smoke.get("canonical_response_parsed") is True,
        "cleanup": cleanup.get("pass") is True and server_cleanup.get("pass") is True,
        "context": model_row.get("max_model_len") == SELECTED_CONTEXT_LENGTH,
        "environment": env_stdout.get("pass") is True
        and env_stdout.get("fingerprint_match") is True,
        "health": health.get("status_code") == 200,
        "model": model_row.get("id") == MODEL_ID
        and str(model_row.get("root", "")).endswith(MODEL_REVISION),
        "nccl": all(row.get("pass") for row in ranks),
        "path_budget": path_budget.get("pass") is True,
        "vram": len(load_memory) == 2
        and all(row.get("free_mib", 0) >= 3500 for row in load_memory),
    }
    if not all(checks.values()):
        raise Qwen36QualificationError(f"smoke 25940 is not a PASS: {checks}")
    return {
        "artifact_directory": str(artifact),
        "artifact_manifest_sha256": manifest_digest,
        "checks": checks,
        "classification": "PASS",
        "context_decision": "SAFE_FOR_QUALIFICATION",
        "gpu_memory_after_load": load_memory,
        "job_id": "25940",
        "kv_cache": {
            "available_gib_per_gpu": 9.84,
            "gpu_tokens": 79968,
            "maximum_concurrency_at_32768": 9.13,
        },
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION},
        "reasoning_parser_compatible": True,
        "runtime_ipc": path_budget,
        "schema": "qwen36-serving-smoke-result-v1",
        "technical_history": [
            {
                "job_id": "25933",
                "classification": "TECHNICAL_INVALID",
                "detail": "UNSUPPORTED_NVIDIA_SMI_MIG_DISPLAY_QUERY",
                "scored": False,
            },
            {
                "job_id": "25938",
                "classification": "TECHNICAL_INVALID",
                "detail": "WRONG_PYTHON_INTERPRETER_MISSING_PYDANTIC",
                "scored": False,
            },
        ],
        "technical_lineage": "25933 -> 25938 -> 25940",
        "treatment": "no_memory",
    }


def build_freeze_manifest(
    project: Path,
    *,
    qualification_infrastructure_commit: str,
    created_at_utc: str | None = None,
) -> dict[str, Any]:
    project = project.resolve(strict=True)
    if (
        len(qualification_infrastructure_commit) != 40
        or any(
            character not in "0123456789abcdef"
            for character in qualification_infrastructure_commit
        )
    ):
        raise Qwen36QualificationError("qualification infrastructure commit is invalid")
    if sha256_file(project / CANDIDATE_MANIFEST) != CANDIDATE_MANIFEST_SHA256:
        raise Qwen36QualificationError("candidate manifest changed")
    if sha256_file(project / SUITE_REFERENCE) != SUITE_REFERENCE_SHA256:
        raise Qwen36QualificationError("suite reference changed")
    if sha256_file(project / SOURCE_SUITE) != SOURCE_SUITE_SHA256:
        raise Qwen36QualificationError("source qualification suite changed")
    validate_agent_config(project / AGENT_CONFIG)
    schedule = validate_seed_schedule(project / SEED_SCHEDULE)
    smoke = load_json(project / SMOKE_RESULT)
    if smoke.get("classification") != "PASS" or smoke.get("job_id") != "25940":
        raise Qwen36QualificationError("smoke result is not the validated job 25940 PASS")
    protocol = (
        ("system_prompt_and_action_parser", "src/cmpilot/integrations/miniswe/action_protocol.py"),
        ("semantic_validator_and_stagnation", "src/cmpilot/integrations/miniswe/hardened_agent.py"),
        ("command_authorization", "src/cmpilot/integrations/miniswe/command_authorization.py"),
        ("protected_path_policy", "src/cmpilot/task_file_policy.py"),
        ("context_budget_algorithm", "src/cmpilot/integrations/miniswe/context_budget.py"),
        ("direct_openai_transport", "src/cmpilot/integrations/miniswe/openai_transport.py"),
        ("direct_vllm_text_model", "src/cmpilot/integrations/miniswe/vllm_text_model.py"),
        ("mini_swe_config_builder", "src/cmpilot/mini_swe_config.py"),
        ("mini_swe_adapter_writer", "src/cmpilot/mini_swe_adapter.py"),
        ("mini_swe_adapter_runtime", "src/cmpilot/integrations/miniswe/adapter_runtime.py"),
        ("qualification_adapter_writer", "src/cmpilot/qualification_adapter.py"),
        ("qualification_policy_shim", "src/cmpilot/integrations/miniswe/qualification_adapter_runtime.py"),
        ("qualification_task_semantics", "src/cmpilot/qualification.py"),
        ("qualification_runner", "src/cmpilot/qualification_runner.py"),
        ("repository_outcome_analyzer", "src/cmpilot/post_agent_pipeline.py"),
        ("mini_swe_source_manifest", "src/cmpilot/integrations/miniswe/source_manifest.py"),
        ("runtime_ipc_policy", "src/cmpilot/qualification_runtime_paths.py"),
        ("finalizer", "src/cmpilot/calculator_finalizer.py"),
        ("artifact_manifest", "scripts/qualification_job_manifest.py"),
    )
    agent_config = load_json(project / AGENT_CONFIG)
    return {
        "artifact_schema": {
            "job_manifest": "qwen32b-qualification-job-manifest-v1",
            "outcome_dimensions": "qwen36-qualification-outcome-dimensions-v1",
        },
        "candidate_manifest": {
            "path": CANDIDATE_MANIFEST.as_posix(),
            "sha256": CANDIDATE_MANIFEST_SHA256,
        },
        "candidate_status": "qualification_configuration_frozen_not_yet_qualified",
        "context": {
            "decision": "SAFE_FOR_QUALIFICATION",
            "gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
            "max_model_len": SELECTED_CONTEXT_LENGTH,
            "max_num_sequences": 1,
        },
        "created_at_utc": created_at_utc or datetime.now(UTC).isoformat(),
        "environment": {
            "content_digest": ENVIRONMENT_CONTENT_DIGEST,
            "fingerprint": ENVIRONMENT_FINGERPRINT,
            "mini_swe_interpreter": str(MINI_SWE_PYTHON),
            "mini_swe_version": "2.4.6",
            "project_interpreter": str(PROJECT_PYTHON),
            "project_interpreter_fingerprint": PROJECT_ENVIRONMENT_FINGERPRINT,
            "serving_interpreter": str(QWEN36_PYTHON),
            "serving_path": str(ENVIRONMENT_PATH),
            "software": {
                "cuda_build": "12.8",
                "python": "3.12.8",
                "pytorch": "2.10.0",
                "tokenizers": "0.22.2",
                "transformers": "4.57.1",
                "vllm": "0.19.0",
            },
        },
        "generation": {
            **agent_config["model"],
            "authoritative_guidance": {
                "generation_config_path": str(MODEL_SNAPSHOT / "generation_config.json"),
                "generation_config_sha256": GENERATION_CONFIG_SHA256,
                "pinned_readme_path": str(MODEL_SNAPSHOT / "README.md"),
                "pinned_readme_sha256": PINNED_README_SHA256,
                "recommendation": {
                    "min_p": 0.0,
                    "presence_penalty": 0.0,
                    "repetition_penalty": 1.0,
                    "temperature": 1.0,
                    "top_k": 20,
                    "top_p": 0.95,
                },
            },
            "max_output_tokens_rationale": (
                "fixed before repository outcomes; permits normal thinking plus one "
                "canonical action while retaining the 32-token context reserve"
            ),
            "outcome_based_retries": False,
            "reasoning_parser": REASONING_PARSER,
            "samples_per_call": 1,
            "thinking_mode": THINKING_MODE,
            "preserve_thinking": False,
            "reasoning_persisted_between_tasks": False,
            "seed_schedule_path": SEED_SCHEDULE.as_posix(),
            "seed_schedule_sha256": sha256_file(project / SEED_SCHEDULE),
            "seeds": schedule["seeds"],
        },
        "candidate_parent_commit": (
            "36aeb8d27c5ed82fe0cefdc8b1c1426242194be6"
        ),
        "model": {
            "architecture": "Qwen3_5ForConditionalGeneration",
            "chat_template_sha256": CHAT_TEMPLATE_SHA256,
            "config_sha256": MODEL_CONFIG_SHA256,
            "dtype": PRECISION,
            "generation_config_sha256": GENERATION_CONFIG_SHA256,
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "snapshot": str(MODEL_SNAPSHOT),
            "snapshot_sha256": MODEL_SNAPSHOT_SHA256,
            "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
            "tokenizer_config_sha256": TOKENIZER_CONFIG_SHA256,
            "tokenizer_inventory_sha256": TOKENIZER_INVENTORY_SHA256,
            "tokenizer_json_sha256": TOKENIZER_JSON_SHA256,
        },
        "non_model_protocol_changes": False,
        "protocol_components": [
            _component(project, name, path) for name, path in protocol
        ],
        "qualification_agent_config": {
            "path": AGENT_CONFIG.as_posix(),
            "sha256": sha256_file(project / AGENT_CONFIG),
        },
        "qualification_rule": {
            "borderline": "exactly 3 of 5 primary; run both reserves and require at least 5 of 7 total",
            "fail": "2 or fewer of 5 primary repository-competence passes",
            "pass": "at least 4 of 5 primary repository-competence passes",
            "sentinel_separate": True,
        },
        "qualification_infrastructure_commit": qualification_infrastructure_commit,
        "qualification_suite": {
            "source_manifest_path": SOURCE_SUITE.as_posix(),
            "source_manifest_sha256": SOURCE_SUITE_SHA256,
            "suite_reference_path": SUITE_REFERENCE.as_posix(),
            "suite_reference_sha256": SUITE_REFERENCE_SHA256,
            "tasks": list(ALL_TASKS),
        },
        "runtime_ipc": {
            "format": "/tmp/cmq-<SLURM_JOB_ID>",
            "safe_maximum_bytes": 90,
        },
        "schema": "qwen36-qualification-freeze-v1",
        "scientific_adapter_contract": {
            "path": ADAPTER_CONTRACT.as_posix(),
            "sha256": sha256_file(project / ADAPTER_CONTRACT),
        },
        "smoke_evidence": {
            "job_id": "25940",
            "path": SMOKE_RESULT.as_posix(),
            "sha256": sha256_file(project / SMOKE_RESULT),
        },
        "treatment": "no_memory",
    }


def validate_freeze_manifest(project: Path, path: Path) -> dict[str, Any]:
    project = project.resolve(strict=True)
    record = load_json(path)
    checks: dict[str, bool] = {
        "schema": record.get("schema") == "qwen36-qualification-freeze-v1",
        "model": record.get("model", {}).get("id") == MODEL_ID
        and record.get("model", {}).get("revision") == MODEL_REVISION,
        "context": record.get("context", {}).get("max_model_len")
        == SELECTED_CONTEXT_LENGTH,
        "environment": record.get("environment", {}).get("fingerprint")
        == ENVIRONMENT_FINGERPRINT,
        "suite": record.get("qualification_suite", {}).get(
            "source_manifest_sha256"
        )
        == SOURCE_SUITE_SHA256,
        "no_memory": record.get("treatment") == "no_memory",
        "generation": record.get("generation", {}).get("temperature") == 1.0
        and record.get("generation", {}).get("top_p") == 0.95
        and record.get("generation", {}).get("top_k") == 20
        and record.get("generation", {}).get("max_tokens") == MAX_OUTPUT_TOKENS
        and record.get("generation", {}).get("samples_per_call") == 1,
        "model_hashes": record.get("model", {}).get("config_sha256")
        == MODEL_CONFIG_SHA256
        and record.get("model", {}).get("chat_template_sha256")
        == CHAT_TEMPLATE_SHA256
        and record.get("model", {}).get("snapshot_sha256")
        == MODEL_SNAPSHOT_SHA256,
    }
    for component in record.get("protocol_components", []):
        if not isinstance(component, Mapping):
            checks["component_shape"] = False
            continue
        relative = str(component.get("path", ""))
        checks[f"component:{component.get('component')}"] = bool(relative) and sha256_file(
            project / relative
        ) == component.get("sha256")
    for name in (
        "qualification_agent_config",
        "scientific_adapter_contract",
        "smoke_evidence",
    ):
        item = record.get(name, {})
        checks[name] = sha256_file(project / str(item.get("path", ""))) == item.get(
            "sha256"
        )
    if not all(checks.values()):
        raise Qwen36QualificationError(f"qualification freeze mismatch: {checks}")
    return {"checks": checks, "pass": True, "sha256": sha256_file(path)}


__all__ = [
    "ADAPTER_CONTRACT",
    "AGENT_CONFIG",
    "ALL_TASKS",
    "MAX_OUTPUT_TOKENS",
    "MINI_SWE_PYTHON",
    "PROJECT_ENVIRONMENT_FINGERPRINT",
    "PRIMARY_TASKS",
    "PROJECT_PYTHON",
    "QUALIFICATION_FREEZE",
    "QWEN36_ARTIFACT_ROOT",
    "QWEN36_PYTHON",
    "REASONING_PARSER",
    "RESERVE_TASKS",
    "SEED_SCHEDULE",
    "SMOKE_RESULT",
    "build_freeze_manifest",
    "build_smoke_result",
    "resolved_agent_config",
    "validate_agent_config",
    "validate_freeze_manifest",
    "validate_seed_schedule",
    "write_canonical_json",
]
