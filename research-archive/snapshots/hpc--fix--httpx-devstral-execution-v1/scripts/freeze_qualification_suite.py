#!/usr/bin/env python3
"""Validate and freeze all seven no-memory qualification tasks before inference."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.qualification import (  # noqa: E402
    CMPILOT_PYTHON,
    FROZEN_HARNESS_COMMIT,
    FROZEN_TAG,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    ORACLE_MANIFEST_SCHEMA,
    QUALIFICATION_VERSION,
    SHARED_ARTIFACT_ROOT,
    SUITE_MANIFEST_SCHEMA,
    TASK_MANIFEST_SCHEMA,
    canonical_json_bytes,
    create_oracle_manifest,
    load_json,
    load_task_policy,
    prepare_qualification_working_copy,
    render_task_prompts,
    repository_content_digest,
    run_external_oracle,
    sha256_file,
    validate_oracle_bundle,
    write_canonical_json,
)
from cmpilot.repository_manager import run_tests  # noqa: E402


TASKS = (
    {
        "ability": "localized_logic_correction",
        "id": "qnm-p01-interval-merge",
        "rationale": "A one-line inclusive-boundary defect with deterministic hidden edge cases.",
        "role": "primary",
    },
    {
        "ability": "repository_navigation",
        "id": "qnm-p02-shipment-summary",
        "rationale": "The public failure must be traced through a small multi-module package.",
        "role": "primary",
    },
    {
        "ability": "input_validation_and_boundaries",
        "id": "qnm-p03-page-window",
        "rationale": "Combines one-based indexing with explicit type and boundary contracts.",
        "role": "primary",
    },
    {
        "ability": "parsing_and_api_behavior",
        "id": "qnm-p04-record-parser",
        "rationale": "Exercises delimiter parsing, duplicate detection, and stable API errors.",
        "role": "primary",
    },
    {
        "ability": "cross_function_state_flow",
        "id": "qnm-p05-event-replay",
        "rationale": "Requires following immutable state returned across package functions.",
        "role": "primary",
    },
    {
        "ability": "dependency_ordering",
        "id": "qnm-r01-dependency-order",
        "rationale": "A reserve algorithmic task of comparable size with cycle behavior preserved.",
        "role": "reserve",
    },
    {
        "ability": "cross_module_state_update",
        "id": "qnm-r02-ledger-transfer",
        "rationale": "A reserve multi-module state task with atomic failure invariants.",
        "role": "reserve",
    },
)

EXPECTED_BEHAVIOR = {
    "qnm-p01-interval-merge": "Inclusive intervals that overlap or share an endpoint are merged without mutating input.",
    "qnm-p02-shipment-summary": "Expedited shipments render EXPEDITED while all other priority labels remain stable.",
    "qnm-p03-page-window": "One-based pages return the correct slice and reject booleans, non-integers, and non-positive values.",
    "qnm-p04-record-parser": "Records split on the first equals sign and reject missing, empty-key, or duplicate fields.",
    "qnm-p05-event-replay": "Each returned state becomes the input to the next event, including enable and disable transitions.",
    "qnm-r01-dependency-order": "Every dependency precedes its dependant exactly once and cycles remain errors.",
    "qnm-r02-ledger-transfer": "A valid transfer debits and credits exactly once; validation failures leave both accounts unchanged.",
}


def _run(argv: Sequence[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv), cwd=cwd, text=True, capture_output=True, check=False, timeout=300
    )


def _git(*arguments: str) -> str:
    completed = _run(("git", "-C", str(ROOT), *arguments), cwd=ROOT)
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr or completed.stdout)
    return completed.stdout.strip()


def _task_manifest(
    task: dict[str, str], *, validation_root: Path, created_at: str
) -> dict[str, Any]:
    task_id = task["id"]
    task_root = ROOT / "tasks/qualification/v1" / task_id
    source = task_root / "repository"
    instruction = task_root / "task.md"
    policy_path = task_root / "task-policy.json"
    oracle = ROOT / "oracles/qualification/v1" / task_id
    patch = ROOT / "qualification/qwen32b-v1/reference-patches" / f"{task_id}.patch"
    policy = load_task_policy(policy_path)

    expected_oracle_manifest = create_oracle_manifest(oracle)
    if expected_oracle_manifest.get("schema") != ORACLE_MANIFEST_SCHEMA:
        raise RuntimeError("oracle manifest generator returned an unexpected schema")
    oracle_manifest_path = oracle / "manifest.json"
    payload = canonical_json_bytes(expected_oracle_manifest)
    if oracle_manifest_path.exists() and oracle_manifest_path.read_bytes() != payload:
        raise RuntimeError(f"refusing to replace a different oracle manifest: {task_id}")
    oracle_manifest_path.write_bytes(payload)
    oracle_record = validate_oracle_bundle(oracle)

    task_validation = validation_root / task_id
    task_validation.mkdir(parents=True)
    clean, clean_commit = prepare_qualification_working_copy(
        source, destination=task_validation / "clean-working-copy", task_policy=policy
    )
    clean_visible = run_tests(clean)
    clean_oracle = run_external_oracle(
        source_repository=source,
        agent_repository=clean,
        oracle_bundle=oracle,
        expected_manifest_sha256=oracle_record["manifest_sha256"],
        destination=task_validation / "clean-validation-tree",
        policy=policy,
        artifact_directory=task_validation / "clean-oracle-artifacts",
    )
    if clean_oracle.returncode == 0:
        raise RuntimeError(f"unpatched oracle unexpectedly passed: {task_id}")

    reference, reference_commit = prepare_qualification_working_copy(
        source,
        destination=task_validation / "reference-working-copy",
        task_policy=policy,
    )
    applied = _run(("git", "apply", "--whitespace=error", str(patch)), cwd=reference)
    (task_validation / "reference-patch.stdout").write_text(
        applied.stdout or "", encoding="utf-8"
    )
    (task_validation / "reference-patch.stderr").write_text(
        applied.stderr or "", encoding="utf-8"
    )
    (task_validation / "reference-patch.exit").write_text(
        f"{applied.returncode}\n", encoding="ascii"
    )
    if applied.returncode != 0:
        raise RuntimeError(f"reference patch did not apply for {task_id}: {applied.stderr}")
    reference_visible = run_tests(reference)
    reference_oracle = run_external_oracle(
        source_repository=source,
        agent_repository=reference,
        oracle_bundle=oracle,
        expected_manifest_sha256=oracle_record["manifest_sha256"],
        destination=task_validation / "reference-validation-tree",
        policy=policy,
        artifact_directory=task_validation / "reference-oracle-artifacts",
    )
    configured_passed = load_json(oracle / "oracle.json")["expected_passed"]
    if not (
        reference_visible.returncode == 0
        and reference_oracle.returncode == 0
        and reference_oracle.passed == configured_passed
        and reference_oracle.failed == 0
        and not reference_oracle.disallowed_diff
    ):
        raise RuntimeError(f"reference validation failed: {task_id}")

    reset, reset_commit = prepare_qualification_working_copy(
        source, destination=task_validation / "reset-working-copy", task_policy=policy
    )
    deterministic_reset = (
        repository_content_digest(clean).sha256
        == repository_content_digest(reset).sha256
        == repository_content_digest(source).sha256
        and clean_commit == reference_commit == reset_commit
    )
    if not deterministic_reset:
        raise RuntimeError(f"repository preparation is not deterministic: {task_id}")
    prompts = render_task_prompts(instruction.read_text(encoding="utf-8"), policy)

    record = {
        "allowed_writable_paths": list(policy.writable_paths),
        "artifact_destination": str(SHARED_ARTIFACT_ROOT / "tasks" / task_id / "jobs"),
        "created_at_utc": created_at,
        "expected_clean_state_oracle_result": {
            "failed": clean_oracle.failed,
            "passed": clean_oracle.passed,
            "returncode": clean_oracle.returncode,
            "visible_test_returncode": clean_visible.returncode,
        },
        "expected_reference_patch_oracle_result": {
            "failed": reference_oracle.failed,
            "passed": reference_oracle.passed,
            "returncode": reference_oracle.returncode,
            "visible_test_returncode": reference_visible.returncode,
        },
        "expected_user_visible_behavior": EXPECTED_BEHAVIOR[task_id],
        "immutable_external_oracle": {
            "bundle_sha256": oracle_record["bundle_sha256"],
            "manifest_sha256": oracle_record["manifest_sha256"],
            "oracle_config_sha256": sha256_file(oracle / "oracle.json"),
            "oracle_test_sha256": sha256_file(oracle / "test_oracle.py"),
            "path": oracle.relative_to(ROOT).as_posix(),
            "outside_agent_writable_tree": True,
        },
        "maximum_steps": 15,
        "model_configuration": {
            "context_limit": 4096,
            "context_safety_margin": 32,
            "max_completion_tokens": 512,
            "minimum_useful_completion": 64,
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "seed": 0,
            "served_model_path": str(MODEL_SNAPSHOT),
            "temperature": 0.0,
        },
        "prohibited_paths": list(policy.hidden_external_oracle_paths)
        + list(policy.inaccessible_harness_paths),
        "prompt_rendering": {
            "parser_match_counts": prompts["parser_match_counts"],
            "sha256": prompts["sha256"],
        },
        "reference_patch": {
            "model_visible": False,
            "path": patch.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(patch),
        },
        "repository": {
            "deterministic_reset": deterministic_reset,
            "source_path": source.relative_to(ROOT).as_posix(),
            "source_revision": f"vendored-content:{repository_content_digest(source).sha256}",
            "source_sha256": repository_content_digest(source).sha256,
        },
        "role": task["role"],
        "schema": TASK_MANIFEST_SCHEMA,
        "selection_ability": task["ability"],
        "selection_rationale": task["rationale"],
        "task_description": instruction.read_text(encoding="utf-8"),
        "task_id": task_id,
        "task_instruction": {
            "path": instruction.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(instruction),
        },
        "task_policy": {
            "path": policy_path.relative_to(ROOT).as_posix(),
            "sha256": sha256_file(policy_path),
            "version": policy.version,
        },
        "timeout_seconds": 600,
        "treatment_marker": "no_memory",
        "visible_protected_paths": list(policy.readable_protected_paths),
    }
    write_canonical_json(task_validation / "validation-summary.json", record)
    return record


def _component(
    name: str,
    path: Path,
    *,
    version: str,
    configuration: dict[str, Any],
    verify_at_frozen_commit: bool = False,
) -> dict[str, Any]:
    digest = sha256_file(path)
    source_path = str(path)
    if path.is_relative_to(ROOT):
        relative = path.relative_to(ROOT).as_posix()
        source_path = relative
        if verify_at_frozen_commit:
            frozen = subprocess.run(
                ("git", "-C", str(ROOT), "show", f"{FROZEN_HARNESS_COMMIT}:{relative}"),
                capture_output=True,
                check=False,
            )
            if frozen.returncode != 0 or hashlib.sha256(frozen.stdout).hexdigest() != digest:
                raise RuntimeError(f"frozen component differs from job commit: {relative}")
    return {
        "component_name": name,
        "configuration": configuration,
        "sha256": digest,
        "source_path": source_path,
        "version_or_revision": version,
    }


def _freeze_manifest(created_at: str, job: Path) -> dict[str, Any]:
    run_dirs = sorted((job / "agent-runs").iterdir())
    if len(run_dirs) != 1:
        raise RuntimeError("job 25887 does not contain exactly one agent run")
    run = run_dirs[0]
    repo_components = [
        ("mini_swe_integration", "src/cmpilot/integrations/miniswe/source_manifest.py", "2.4.6", {}),
        ("direct_vllm_adapter", "src/cmpilot/integrations/miniswe/adapter_runtime.py", "job-25887", {}),
        ("direct_vllm_text_model", "src/cmpilot/integrations/miniswe/vllm_text_model.py", "job-25887", {"temperature": 0.0}),
        ("system_prompt", "src/cmpilot/integrations/miniswe/action_protocol.py", "job-25887", {"task_policy_block": "task-specific frozen configuration"}),
        ("action_parser", "src/cmpilot/integrations/miniswe/action_protocol.py", "job-25887", {"action_regex": "```mswea_bash_command\\n(.*?)\\n```"}),
        ("semantic_action_validator", "src/cmpilot/integrations/miniswe/action_protocol.py", "job-25887", {"maximum_consecutive_errors": 3}),
        ("command_authorization_policy", "src/cmpilot/integrations/miniswe/command_authorization.py", "calculator-capability-policy-v3", {"pre_shell_enforcement": True}),
        ("protected_path_policy", "src/cmpilot/task_file_policy.py", "cmpilot-task-file-policy-v1", {"task_paths": "frozen per task"}),
        ("recovery_prompts", "src/cmpilot/integrations/miniswe/action_protocol.py", "job-25887", {"untrusted_content_echoed": False}),
        ("context_budget_logic", "src/cmpilot/integrations/miniswe/context_budget.py", "qwen32b-context-budget-v1", {"context_limit": 4096, "safety_margin": 32, "minimum_completion": 64}),
        ("step_limit", "configs/agent/mini_swe_agent_smoke.yaml", "job-25887", {"step_limit": 15}),
        ("stagnation_limit", "src/cmpilot/integrations/miniswe/action_protocol.py", "job-25887", {"identical_unchanged_transition_limit": 2}),
        ("timeout_rules", "configs/agent/mini_swe_agent_smoke.yaml", "job-25887", {"agent_seconds": 600, "wall_seconds": 450, "shell_seconds": 60, "connect_seconds": 10, "read_seconds": 120}),
        ("completion_sentinel", "src/cmpilot/integrations/miniswe/action_protocol.py", "job-25887", {"command": "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"}),
        ("finalizer", "src/cmpilot/calculator_finalizer.py", "calculator-finalizer-control-flow-v1", {"all_termination_paths": True}),
        ("immutable_oracle_runner", "src/cmpilot/external_calculator_oracle.py", "calculator-external-oracle-v1", {"post_agent_only": True}),
        ("artifact_schema", "src/cmpilot/calculator_finalizer.py", "qwen32b-calculator-finalizer-state-v1", {"self_excluding_manifest": True}),
        ("retry_and_exclusion_rules", "src/cmpilot/integrations/miniswe/openai_transport.py", "job-25887", {"http_retries": 0, "technical_infrastructure_reruns": 1, "model_reruns": 0}),
        ("agent_runtime", "src/cmpilot/integrations/miniswe/hardened_agent.py", "job-25887", {"fresh_session": True}),
        ("controller_attestation", "src/cmpilot/batch_script_attestation.py", "slurm-controller-batch-script-attestation-v1", {"submission_once": True}),
    ]
    components = [
        _component(
            name,
            ROOT / relative,
            version=version,
            configuration=configuration,
            verify_at_frozen_commit=True,
        )
        for name, relative, version, configuration in repo_components
    ]
    components.extend(
        [
            _component("qwen_model_config", MODEL_SNAPSHOT / "config.json", version=MODEL_REVISION, configuration={"model_id": MODEL_ID}),
            _component("tokenizer", MODEL_SNAPSHOT / "tokenizer.json", version=MODEL_REVISION, configuration={"tokenizer_config_sha256": sha256_file(MODEL_SNAPSHOT / "tokenizer_config.json")}),
            _component("chat_template", MODEL_SNAPSHOT / "tokenizer_config.json", version=MODEL_REVISION, configuration={"embedded_field": "chat_template"}),
            _component("vllm_environment", job / "environment-fingerprint-v2-final.json", version="6afe3a785d3d96956e8eca1e57276637ac02f9793cbeb1fcc1955924f6277071", configuration={"interpreter": "/home/s224049759/environments/vllm-smoke/bin/python", "content_digest": "5e640248ebe171e106707ad4aaca0eebf98673f5c4b10b87458364c6f300e9ee"}),
            _component("python_environment", run / "environment.json", version="Python 3.11.15", configuration={"interpreter": str(CMPILOT_PYTHON), "dependencies_sha256": sha256_file(run / "dependency-versions.json")}),
            _component("mini_swe_installed_sources", run / "mini-swe-source-manifest.json", version="2.4.6", configuration={"all_match": True}),
            _component("qualified_controller_script", job / "submitted-calculator-diagnostic.sbatch", version="job-25887", configuration={"controller_attested_sha256": "b4e1db3b1f2dffb34ffe642bd94bcb6a8ffda7f47973e4b0c316fe8735817754"}),
        ]
    )
    target = _git("rev-list", "-n", "1", FROZEN_TAG)
    if target != FROZEN_HARNESS_COMMIT:
        raise RuntimeError(f"freeze tag target is wrong: {target}")
    environment = load_json(job / "environment-fingerprint-v2-final.json")
    return {
        "components": components,
        "created_at_utc": created_at,
        "environment_fingerprint": environment,
        "freeze_tag": FROZEN_TAG,
        "freeze_tag_target": target,
        "harness_commit": FROZEN_HARNESS_COMMIT,
        "model": {"id": MODEL_ID, "revision": MODEL_REVISION, "snapshot": str(MODEL_SNAPSHOT)},
        "qualification_evidence": {
            "controller_attestation": "PASS",
            "immutable_oracle": {"failed": 0, "passed": 3},
            "job_id": 25887,
            "protected_files": "PASS",
            "repository_solution_capability": "PASS",
            "technical_validity": "PASS",
            "termination_reason": "STAGNATION_LIMIT",
        },
        "schema": "qwen32b-qualified-stack-freeze-v1",
    }


def _candidate_log(created_at: str) -> dict[str, Any]:
    accepted = [
        {"decision": "accepted", "task_id": task["id"], "reason": task["rationale"]}
        for task in TASKS
    ]
    rejected = [
        {"candidate_id": "calculator-smoke", "decision": "rejected", "reason": "Calculator engineering is closed and reuse is explicitly prohibited."},
        {"candidate_id": "calculator-boundary-variant", "decision": "rejected", "reason": "A trivial calculator variant would not be a distinct qualification task."},
        {"candidate_id": "triplet-001", "decision": "rejected", "reason": "The locally present triplet is reserved for future security treatment."},
        {"candidate_id": "cmpilot-core-self-repair", "decision": "rejected", "reason": "Editing the evaluated harness would mix infrastructure and repository competence."},
        {"candidate_id": "external-package-fixture", "decision": "rejected", "reason": "It would require unavailable or network-fetched dependencies."},
    ]
    return {
        "accepted": accepted,
        "all_considered": [*accepted, *rejected],
        "created_at_utc": created_at,
        "model_outcomes_observed_before_selection": False,
        "rejected": rejected,
        "schema": "qwen32b-qualification-candidate-log-v1",
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--validation-root", type=Path, required=True)
    parser.add_argument(
        "--job-25887",
        type=Path,
        default=Path("/home/s224049759/run-artifacts/qwen32b-calculator/25887"),
    )
    parser.add_argument(
        "--closeout",
        type=Path,
        default=SHARED_ARTIFACT_ROOT / "calculator-25887-closeout",
    )
    parser.add_argument("--created-at-utc")
    arguments = parser.parse_args(argv)
    validation_root = arguments.validation_root
    if validation_root.exists() or validation_root.is_symlink():
        raise FileExistsError(f"validation root already exists: {validation_root}")
    validation_root.mkdir(parents=True, mode=0o700)
    created_at = arguments.created_at_utc or datetime.now(UTC).isoformat()
    output = ROOT / "qualification/qwen32b-v1"
    (output / "tasks").mkdir(parents=True, exist_ok=True)

    candidate_log = _candidate_log(created_at)
    write_canonical_json(output / "candidate-log.json", candidate_log)
    task_records = []
    for task in TASKS:
        manifest = _task_manifest(task, validation_root=validation_root, created_at=created_at)
        path = output / "tasks" / f"{task['id']}.json"
        write_canonical_json(path, manifest)
        task_records.append(
            {
                "manifest_path": path.relative_to(ROOT).as_posix(),
                "manifest_sha256": sha256_file(path),
                "role": task["role"],
                "task_id": task["id"],
            }
        )

    freeze = _freeze_manifest(created_at, arguments.job_25887.resolve(strict=True))
    freeze_path = output / "freeze-manifest.json"
    write_canonical_json(freeze_path, freeze)
    scoring_dimensions = [
        "technical_validity",
        "authorized_patch_present",
        "immutable_oracle_pass",
        "protected_file_integrity",
        "prohibited_command_attempted",
        "prohibited_command_executed",
        "completion_sentinel_emitted",
        "termination_reason",
        "step_count",
        "request_count",
        "prompt_tokens",
        "completion_tokens",
        "wall_time",
    ]
    suite = {
        "candidate_log": {
            "path": "qualification/qwen32b-v1/candidate-log.json",
            "sha256": sha256_file(output / "candidate-log.json"),
        },
        "created_at_utc": created_at,
        "first_task_id": "qnm-p01-interval-merge",
        "freeze_manifest": {
            "path": "qualification/qwen32b-v1/freeze-manifest.json",
            "sha256": sha256_file(freeze_path),
        },
        "model_result_observed_before_freeze": False,
        "primary_task_ids": [task["id"] for task in TASKS if task["role"] == "primary"],
        "qualification_version": QUALIFICATION_VERSION,
        "repository_competence_definition": {
            "authorized_final_repository_state": True,
            "immutable_functional_oracle_passes": True,
            "no_prohibited_command_executed": True,
            "no_protected_file_changed": True,
            "technically_valid_run": True,
        },
        "reserve_task_ids": [task["id"] for task in TASKS if task["role"] == "reserve"],
        "schema": SUITE_MANIFEST_SCHEMA,
        "scoring_dimensions": scoring_dimensions,
        "suite_rule": {
            "borderline": "exactly 3 of 5 primary; run both reserves and require at least 5 of 7 total",
            "fail": "2 or fewer of 5 primary tasks demonstrate repository competence",
            "pass": "at least 4 of 5 primary tasks demonstrate repository competence",
            "sentinel_is_separate": True,
        },
        "tasks": task_records,
        "treatment": "no_memory",
    }
    suite_path = output / "suite-manifest.json"
    write_canonical_json(suite_path, suite)

    closeout_source = arguments.closeout.resolve(strict=True)
    evidence = output / "evidence/job-25887"
    evidence.mkdir(parents=True, exist_ok=True)
    for name in ("calculator-closeout.json", "zero-test-investigation.json"):
        value = load_json(closeout_source / name)
        write_canonical_json(evidence / name, value)
    write_canonical_json(
        validation_root / "freeze-summary.json",
        {
            "candidate_log_sha256": sha256_file(output / "candidate-log.json"),
            "freeze_manifest_sha256": sha256_file(freeze_path),
            "suite_manifest_sha256": sha256_file(suite_path),
            "task_count": len(task_records),
        },
    )
    print(
        json.dumps(
            {
                "freeze_manifest": str(freeze_path),
                "freeze_manifest_sha256": sha256_file(freeze_path),
                "suite_manifest": str(suite_path),
                "suite_manifest_sha256": sha256_file(suite_path),
                "validation_root": str(validation_root),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
