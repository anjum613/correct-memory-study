#!/usr/bin/env python3
"""Create the separate treatment-blind Qwen3.6 qualification candidate records."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qwen36_candidate import (  # noqa: E402
    ARTIFACT_ROOT,
    ENVIRONMENT_PATH,
    FROZEN_TAG,
    FROZEN_TAG_TARGET,
    GPU_MEMORY_UTILIZATION,
    MODEL_ARCHITECTURE,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    NATIVE_CONTEXT_LENGTH,
    QWEN25_RESULT,
    QWEN25_RESULT_SHA256,
    QUALIFICATION_NAMESPACE,
    RELEASED_DTYPE,
    SELECTED_CONTEXT_LENGTH,
    SOURCE_SUITE,
    SOURCE_SUITE_SHA256,
    TENSOR_PARALLEL_SIZE,
    build_suite_reference,
    load_json,
    memory_feasibility,
    sha256_file,
    smoke_runtime_path_record,
    write_canonical_json,
)


PROTOCOL_COMPONENTS = (
    ("system_prompt_and_action_parser", "src/cmpilot/integrations/miniswe/action_protocol.py"),
    ("semantic_action_validator", "src/cmpilot/integrations/miniswe/hardened_agent.py"),
    ("command_authorization", "src/cmpilot/integrations/miniswe/command_authorization.py"),
    ("protected_path_policy", "src/cmpilot/task_file_policy.py"),
    ("context_budget_logic", "src/cmpilot/integrations/miniswe/context_budget.py"),
    ("direct_openai_transport", "src/cmpilot/integrations/miniswe/openai_transport.py"),
    ("direct_vllm_adapter", "src/cmpilot/integrations/miniswe/vllm_text_model.py"),
    ("mini_swe_adapter_runtime", "src/cmpilot/integrations/miniswe/adapter_runtime.py"),
    ("qualification_policy_shim", "src/cmpilot/integrations/miniswe/qualification_adapter_runtime.py"),
    ("mini_swe_source_manifest", "src/cmpilot/integrations/miniswe/source_manifest.py"),
    ("runtime_ipc_path_policy", "src/cmpilot/qualification_runtime_paths.py"),
    ("artifact_schema", "scripts/finalize_qwen36_smoke.py"),
)


def git(*arguments: str) -> str:
    completed = subprocess.run(
        ("git", "-C", str(ROOT), *arguments),
        check=True,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return completed.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--namespace", type=Path, default=ROOT / QUALIFICATION_NAMESPACE
    )
    arguments = parser.parse_args()
    namespace = arguments.namespace
    paths = {
        "candidate": namespace / "candidate-freeze-manifest.json",
        "config": namespace / "qualification-config.json",
        "suite_reference": namespace / "suite-reference.json",
    }
    for path in paths.values():
        if path.exists() or path.is_symlink():
            raise FileExistsError(f"candidate output already exists: {path}")
    environment = load_json(namespace / "environment-manifest.json")
    staging = load_json(namespace / "model-staging-manifest.json")
    metadata = load_json(namespace / "model-metadata.json")
    if staging["model"]["revision"] != MODEL_REVISION:
        raise RuntimeError("staging manifest revision mismatch")
    if metadata["revision"] != MODEL_REVISION:
        raise RuntimeError("Hub metadata revision mismatch")
    suite_reference = build_suite_reference(ROOT)
    write_canonical_json(paths["suite_reference"], suite_reference, exclusive=True)

    tag_target = git("rev-list", "-n", "1", FROZEN_TAG)
    if tag_target != FROZEN_TAG_TARGET:
        raise RuntimeError("historical Qwen2.5 harness tag moved")
    project_commit = git("rev-parse", "HEAD")
    direct_adapter_commit = git(
        "log",
        "-1",
        "--format=%H",
        "--",
        "src/cmpilot/integrations/miniswe/vllm_text_model.py",
        "src/cmpilot/integrations/miniswe/openai_transport.py",
    )
    runtime_record = smoke_runtime_path_record("99999999999999999999")
    if not runtime_record["pass"]:
        raise RuntimeError("Qwen3.6 runtime IPC path exceeds the project budget")

    qualification_config = {
        "agent_protocol": {
            "action_format_changed": False,
            "authorization_changed": False,
            "completion_sentinel_changed": False,
            "context_budget_algorithm_changed": False,
            "immutable_oracle_scoring_changed": False,
            "model_visible_prompt_changed": False,
            "parser_changed": False,
            "protected_path_rules_changed": False,
            "stagnation_logic_changed": False,
            "step_and_termination_rules_changed": False,
        },
        "artifact_root": str(ARTIFACT_ROOT),
        "candidate_not_yet_qualified": True,
        "model": {
            "architecture": MODEL_ARCHITECTURE,
            "context_length": SELECTED_CONTEXT_LENGTH,
            "custom_remote_code": False,
            "dtype": RELEASED_DTYPE,
            "gpu_memory_utilization": GPU_MEMORY_UTILIZATION,
            "id": MODEL_ID,
            "language_model_only": True,
            "max_num_sequences": 1,
            "native_context_length": NATIVE_CONTEXT_LENGTH,
            "quantization": None,
            "revision": MODEL_REVISION,
            "snapshot": str(MODEL_SNAPSHOT),
            "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
        },
        "qualification_decoding": {
            "reason": "The current task freezes only the deterministic serving smoke; stochastic qualification decoding is frozen before repository tasks.",
            "status": "not_frozen_by_serving_smoke",
        },
        "qualification_suite": {
            "reference_path": str(SOURCE_SUITE),
            "reference_sha256": SOURCE_SUITE_SHA256,
            "rule": suite_reference["suite_rule"],
            "task_components_byte_identical": suite_reference[
                "all_task_components_byte_identical"
            ],
        },
        "schema": "qwen36-qualification-candidate-config-v1",
        "smoke_generation": {
            "chat_template_thinking_mode": "model_default_enabled",
            "max_tokens": 128,
            "persistent_reasoning_state": False,
            "preserve_thinking_history": False,
            "reasoning_parser": "qwen3",
            "temperature": 0.0,
        },
        "treatment": "no_memory",
    }
    write_canonical_json(paths["config"], qualification_config, exclusive=True)

    components = []
    for name, relative in PROTOCOL_COMPONENTS:
        source = ROOT / relative
        components.append(
            {
                "component": name,
                "path": relative,
                "sha256": sha256_file(source),
            }
        )
    manifest = {
        "artifact_schema": next(
            row for row in components if row["component"] == "artifact_schema"
        ),
        "candidate_status": "qualification_candidate_not_final",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "direct_adapter": {
            "commit": direct_adapter_commit,
            "transport_sha256": sha256_file(
                ROOT / "src/cmpilot/integrations/miniswe/openai_transport.py"
            ),
            "vllm_text_model_sha256": sha256_file(
                ROOT / "src/cmpilot/integrations/miniswe/vllm_text_model.py"
            ),
        },
        "environment": {
            "content_digest": environment["content_digest"][
                "canonical_inventory_sha256"
            ],
            "fingerprint": environment["fingerprint"][
                "canonical_inventory_sha256"
            ],
            "path": str(ENVIRONMENT_PATH),
            "python_version": environment["python_version"],
            "torch_cuda_build": environment["torch_cuda_build"],
            "versions": environment["versions"],
        },
        "frozen_historical_qwen25": {
            "qualification_decision": "FAIL",
            "qualification_result_path": str(QWEN25_RESULT),
            "qualification_result_sha256": QWEN25_RESULT_SHA256,
            "tag": FROZEN_TAG,
            "tag_target": tag_target,
        },
        "memory_feasibility": memory_feasibility(),
        "mini_swe_integration": {
            "source_manifest_sha256": sha256_file(
                ROOT / "src/cmpilot/integrations/miniswe/source_manifest.py"
            ),
            "version": "2.4.6",
        },
        "model": {
            "architecture": MODEL_ARCHITECTURE,
            "chat_template_sha256": staging["model"]["chat_template_sha256"],
            "config_sha256": staging["model"]["config_sha256"],
            "context_length": SELECTED_CONTEXT_LENGTH,
            "custom_remote_code": False,
            "dtype": RELEASED_DTYPE,
            "generation_config_sha256": staging["model"][
                "generation_config_sha256"
            ],
            "id": MODEL_ID,
            "revision": MODEL_REVISION,
            "snapshot_path": str(MODEL_SNAPSHOT),
            "snapshot_sha256": staging["model"]["snapshot_sha256"],
            "tensor_parallel_size": TENSOR_PARALLEL_SIZE,
            "tokenizer_inventory_sha256": staging["model"][
                "tokenizer_inventory_sha256"
            ],
        },
        "project_infrastructure_commit": project_commit,
        "protocol_components": components,
        "qualification_config": {
            "path": str(paths["config"].relative_to(ROOT)),
            "sha256": sha256_file(paths["config"]),
        },
        "qualification_suite": {
            "reference_manifest_path": str(paths["suite_reference"].relative_to(ROOT)),
            "reference_manifest_sha256": sha256_file(paths["suite_reference"]),
            "source_manifest_path": str(SOURCE_SUITE),
            "source_manifest_sha256": SOURCE_SUITE_SHA256,
            "task_components_byte_identical": True,
        },
        "runtime_ipc_path_policy": {
            "maximum_tested_socket_path_bytes": runtime_record[
                "zmq_socket_path_bytes"
            ],
            "runtime_format": "/tmp/cmq-<SLURM_JOB_ID>",
            "safe_maximum_bytes": runtime_record["safe_maximum_bytes"],
        },
        "schema": "qwen36-qualification-candidate-freeze-v1",
        "smoke_generation": qualification_config["smoke_generation"],
        "staging_manifest": {
            "path": str((namespace / "model-staging-manifest.json").relative_to(ROOT)),
            "sha256": sha256_file(namespace / "model-staging-manifest.json"),
        },
        "treatment": "no_memory",
    }
    write_canonical_json(paths["candidate"], manifest, exclusive=True)
    print(
        json.dumps(
            {
                "candidate_manifest": str(paths["candidate"]),
                "candidate_manifest_sha256": sha256_file(paths["candidate"]),
                "status": "PASS",
                "suite_reference": str(paths["suite_reference"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
