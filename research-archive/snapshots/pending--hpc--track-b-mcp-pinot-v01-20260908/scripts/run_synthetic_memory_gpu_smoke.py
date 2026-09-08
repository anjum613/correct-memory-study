#!/usr/bin/env python3
"""Run four frozen synthetic treatments through fresh scientific mini-SWE agents."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.artifact_logger import write_json, write_text  # noqa: E402
from cmpilot.mini_swe_adapter import mini_swe_info  # noqa: E402
from cmpilot.post_agent_pipeline import analyze_task_repository  # noqa: E402
from cmpilot.qualification import (  # noqa: E402
    load_task_policy,
    prepare_qualification_working_copy,
    render_task_prompts,
    sha256_file,
)
from cmpilot.qualification_adapter import (  # noqa: E402
    command,
    write_qualification_adapter,
)
from cmpilot.qualification_runner import AdapterConfig  # noqa: E402
from cmpilot.qwen36_qualification import (  # noqa: E402
    AGENT_CONFIG,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    validate_agent_config,
    write_canonical_json,
)
from cmpilot.repository_manager import (  # noqa: E402
    final_patch,
    git,
    repository_preparation_record,
    run_tests,
    template_snapshot,
)
from cmpilot.smoke_runner import (  # noqa: E402
    _safe_agent_environment,
    _snapshot_artifact,
    _source_snapshot,
    _trajectory_metrics,
    execute_agent,
)
from cmpilot.synthetic_memory_gpu import (  # noqa: E402
    EXPECTED_EXECUTION_ORDER,
    GPU_FREEZE_PATH,
    POLICY_PATH,
    RESULT_SCHEMA,
    SEEDS_PATH,
    SOURCE_ROOT,
    SyntheticGPUError,
    engineering_classification,
    prompt_evidence,
    reasoning_isolation,
    run_external_check,
    technical_rerun_eligible,
    validate_gpu_freeze,
    validate_seed_schedule,
    validate_source_inventory,
    write_artifact_manifest,
    write_condition_result,
)
from cmpilot.synthetic_memory_smoke import (  # noqa: E402
    contamination_check,
    load_json,
    memory_identity,
    render_prompt,
    tree_sha256,
)
from cmpilot.task_file_policy import (  # noqa: E402
    capture_protected_path_state,
    check_protected_path_integrity,
)
from cmpilot.vllm_client import probe_models, validate_model  # noqa: E402


IGNORED_PARTS = {".git", ".pytest_cache", "__pycache__"}


def _copy_frozen_fixture(source: Path, destination: Path) -> None:
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"synthetic source snapshot exists: {destination}")
    destination.mkdir(mode=0o700)
    for source_path in sorted(source.rglob("*")):
        relative = source_path.relative_to(source)
        if any(part in IGNORED_PARTS for part in relative.parts):
            continue
        target = destination / relative
        if source_path.is_dir():
            target.mkdir(mode=0o700, parents=True, exist_ok=True)
        elif source_path.is_file() and source_path.suffix != ".pyc":
            target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            shutil.copyfile(source_path, target)
            target.chmod(0o700 if source_path.stat().st_mode & 0o111 else 0o600)
        else:
            raise SyntheticGPUError(f"unsupported synthetic fixture entry: {source_path}")


def _resolved_agent_config(project: Path, seed: int) -> dict[str, Any]:
    source = project / AGENT_CONFIG
    validate_agent_config(source)
    value = load_json(source)
    value["model"] = dict(value["model"])
    value["model"]["seed"] = seed
    return value


def _write_process_evidence(
    artifact: Path, prefix: str, result: Any
) -> None:
    write_text(artifact / f"{prefix}.stdout", result.stdout or "")
    write_text(artifact / f"{prefix}.stderr", result.stderr or "")
    write_text(artifact / f"{prefix}.exit", f"{result.returncode}\n")


def _condition_provenance(
    *,
    project: Path,
    condition: str,
    condition_root: Path,
    repository: Path,
    repository_source_sha256: str,
    seed: int,
) -> dict[str, Any]:
    identity = memory_identity(project / SOURCE_ROOT, condition)
    run_id = condition_root.name
    return {
        "condition": condition,
        "fresh_agent_process": True,
        "fresh_conversation": True,
        "initial_history": [],
        "memory_id": identity["memory_id"],
        "memory_provenance": identity["provenance"],
        "memory_sha256": identity["memory_sha256"],
        "prompt": render_prompt(project / SOURCE_ROOT, condition),
        "repository_path": str(repository),
        "repository_source_sha256": repository_source_sha256,
        "resolved_agent_config_fresh": True,
        "run_id": run_id,
        "schema": "synthetic-memory-gpu-condition-provenance-v1",
        "seed": seed,
        "session_id": "sms-gpu-"
        + hashlib.sha256(f"{run_id}:{condition}".encode("utf-8")).hexdigest()[:20],
    }


def _run_condition(
    *,
    project: Path,
    artifact_root: Path,
    condition: str,
    ordinal: int,
    base_url: str,
    mini_python: str,
    tokenizer_path: str,
    seed: int,
    agent_timeout: int,
    expected_prompts: dict[str, Any],
) -> dict[str, Any]:
    condition_root = artifact_root / "conditions" / f"{ordinal:02d}-{condition}"
    condition_root.mkdir(parents=True, mode=0o700)
    source = project / SOURCE_ROOT / "repositories/invalidated"
    source_snapshot = condition_root / "source-snapshot"
    _copy_frozen_fixture(source, source_snapshot)
    manifest_tree = load_json(project / SOURCE_ROOT / "manifest.json")["repositories"][
        "invalidated"
    ]["tree_sha256"]
    if tree_sha256(source_snapshot) != manifest_tree:
        raise SyntheticGPUError("condition source snapshot differs from frozen fixture")

    policy = load_task_policy(project / POLICY_PATH)
    working_copy, initial_commit = prepare_qualification_working_copy(
        source_snapshot,
        destination=condition_root / "working-copy",
        task_policy=policy,
    )
    preparation = repository_preparation_record(
        source_snapshot, working_copy, initial_commit
    )
    write_json(condition_root / "repository-preparation.json", preparation)
    protected_baseline = capture_protected_path_state(working_copy, policy)
    write_json(
        condition_root / "protected-path-baseline.json",
        {"paths": [row.as_dict() for row in protected_baseline]},
    )
    source_before = template_snapshot(source_snapshot)

    task_text = render_prompt(project / SOURCE_ROOT, condition)
    task_file = condition_root / "task.md"
    task_file.write_text(task_text, encoding="utf-8", newline="\n")
    rendered_prompts = render_task_prompts(task_text, policy)
    write_json(condition_root / "canonical-prompts.json", rendered_prompts)
    observed_prompt = expected_prompts["conditions"][condition]
    if rendered_prompts["sha256"]["system"] != observed_prompt["system_prompt_sha256"]:
        raise SyntheticGPUError("condition system prompt differs from GPU freeze")
    if rendered_prompts["sha256"]["task"] != observed_prompt["task_prompt_sha256"]:
        raise SyntheticGPUError("condition task prompt differs from GPU freeze")

    resolved_path = condition_root / "resolved-agent-config.json"
    write_canonical_json(resolved_path, _resolved_agent_config(project, seed))
    provenance = _condition_provenance(
        project=project,
        condition=condition,
        condition_root=condition_root,
        repository=working_copy,
        repository_source_sha256=manifest_tree,
        seed=seed,
    )
    provenance["initial_prompt_sha256"] = observed_prompt["complete_prompt_sha256"]
    write_json(condition_root / "run-provenance.json", provenance)

    visible_pre = run_tests(working_copy)
    _write_process_evidence(condition_root, "visible-tests-pre", visible_pre)
    functional_script = project / SOURCE_ROOT / "oracles/functional_oracle.py"
    security_script = project / SOURCE_ROOT / "oracles/security_witness.py"
    functional_pre = run_external_check(functional_script, working_copy)
    security_pre = run_external_check(security_script, working_copy)
    write_json(condition_root / "functional-oracle-pre.json", functional_pre)
    write_json(condition_root / "security-witness-pre.json", security_pre)

    adapter = condition_root / "mini_swe_adapter.py"
    adapter_record = write_qualification_adapter(adapter)
    write_json(condition_root / "scientific-adapter.json", adapter_record)
    adapter_config = AdapterConfig(
        model=MODEL_ID,
        tokenizer_path=tokenizer_path,
        base_url=base_url,
        agent_config_source=resolved_path,
    )
    trajectory = condition_root / "trajectory.json"
    environment = _safe_agent_environment(
        condition_root,
        working_copy,
        adapter_config,
        trajectory,
        task_file,
    )
    environment.update(
        {
            "CMPILOT_FROZEN_ADAPTER_SHA256": adapter_record[
                "frozen_adapter_sha256"
            ],
            "CMPILOT_TASK_POLICY_SHA256": sha256_file(project / POLICY_PATH),
            "CMPILOT_TASK_POLICY_SOURCE": str(project / POLICY_PATH),
        }
    )
    command_line = command(mini_python, adapter)
    write_json(condition_root / "agent-command.json", command_line)
    agent_started = time.perf_counter()
    execution = execute_agent(
        command_line, working_copy, environment, timeout=agent_timeout
    )
    agent_wall_time = time.perf_counter() - agent_started
    write_text(condition_root / "agent.stdout", execution.stdout)
    write_text(condition_root / "agent.stderr", execution.stderr)
    write_json(
        condition_root / "agent-execution.json",
        {
            "exit_code": execution.exit_code,
            "launch_error": execution.launch_error,
            "timed_out": execution.timed_out,
            "wall_time_seconds": agent_wall_time,
        },
    )

    patch = final_patch(working_copy, initial_commit)
    status = git(working_copy, "status", "--short").stdout
    write_text(condition_root / "final.patch", patch)
    write_text(condition_root / "git-status.txt", status)
    write_json(
        condition_root / "final-file-hashes.json",
        _snapshot_artifact(_source_snapshot(working_copy)),
    )
    visible_post = run_tests(working_copy)
    _write_process_evidence(condition_root, "visible-tests-post", visible_post)
    functional_post = run_external_check(functional_script, working_copy)
    security_post = run_external_check(security_script, working_copy)
    write_json(condition_root / "functional-oracle-post.json", functional_post)
    write_json(condition_root / "security-witness-post.json", security_post)

    repository_files = {str(path) for path in _source_snapshot(working_copy)}
    metrics = _trajectory_metrics(trajectory, repository_files)
    write_json(condition_root / "trajectory-metrics.json", metrics)
    prohibited_executed = bool(
        metrics.get("environment_mutation_executed")
        or metrics.get("network_access_executed")
    )
    finding = analyze_task_repository(
        source_repository=source_snapshot,
        agent_repository=working_copy,
        task_policy=policy,
        prohibited_command_executed=prohibited_executed,
    )
    protected = check_protected_path_integrity(working_copy, protected_baseline)
    source_unchanged = template_snapshot(source_snapshot) == source_before
    authorized_patch = bool(
        patch.strip()
        and finding.allowed_paths_modified
        and not finding.disallowed_paths_modified
        and not finding.protected_path_violation
    )
    reasoning = reasoning_isolation(
        trajectory_path=trajectory,
        transport_path=condition_root / "model-transport.jsonl",
        condition=condition,
    )
    write_json(condition_root / "reasoning-isolation.json", reasoning)
    technical = bool(
        not execution.timed_out
        and execution.launch_error is None
        and execution.exit_code == 0
        and trajectory.is_file()
        and finding.technical_validity == "pass"
        and protected.ok
        and source_unchanged
        and not prohibited_executed
        and reasoning["pass"]
    )
    termination = str(metrics.get("termination_reason", ""))
    classification = engineering_classification(
        technical_validity=technical,
        functional_pass=bool(functional_post["pass"]),
        security_pass=bool(security_post["pass"]),
    )
    result = {
        "agent_wall_time": agent_wall_time,
        "authorized_patch_present": authorized_patch,
        "changed_files": list(finding.allowed_paths_modified),
        "completion_sentinel_emitted": termination == "Submitted",
        "completion_tokens": metrics.get("usage_completion"),
        "engineering_classification": classification,
        "functional_oracle_post": functional_post,
        "functional_oracle_pre": functional_pre,
        "initial_prompt_sha256": observed_prompt["complete_prompt_sha256"],
        "memory_id": provenance["memory_id"],
        "memory_provenance": provenance["memory_provenance"],
        "memory_sha256": provenance["memory_sha256"],
        "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        "prompt_tokens": metrics.get("usage_prompt"),
        "prohibited_command_attempt_count": metrics.get(
            "policy_violation_count", 0
        ),
        "prohibited_command_executed": prohibited_executed,
        "protected_file_integrity": protected.ok,
        "reasoning_isolation": reasoning,
        "reasoning_tokens": None,
        "repository_source_sha256": provenance["repository_source_sha256"],
        "request_count": metrics.get("model_request_count"),
        "schema": RESULT_SCHEMA,
        "scientific_evidence": False,
        "security_witness_post": security_post,
        "security_witness_pre": security_pre,
        "seed": seed,
        "source_fixture_unchanged": source_unchanged,
        "step_count": metrics.get("agent_steps"),
        "synthetic_validation_only": True,
        "technical_rerun_eligible": technical_rerun_eligible(
            technical_validity=technical
        ),
        "technical_validity": technical,
        "termination_reason": termination,
        "total_tokens": metrics.get("usage_total"),
        "treatment_condition": condition,
    }
    result_path = write_condition_result(condition_root / "result.json", result)
    condition_manifest = write_artifact_manifest(condition_root)
    return {
        "artifact_directory": str(condition_root),
        "artifact_manifest_sha256": sha256_file(
            condition_root / "job-manifest.json"
        ),
        "condition": condition,
        "engineering_classification": classification,
        "result_sha256": sha256_file(result_path),
        "seed": seed,
        "technical_validity": technical,
        "condition_manifest": condition_manifest,
        "provenance": provenance,
    }


def _technical_failure(
    *, condition_root: Path, condition: str, seed: int, error: BaseException
) -> dict[str, Any]:
    condition_root.mkdir(parents=True, exist_ok=True)
    write_json(
        condition_root / "technical-error.json",
        {"error": str(error), "error_type": type(error).__name__},
    )
    result = {
        "agent_wall_time": 0.0,
        "authorized_patch_present": False,
        "changed_files": [],
        "completion_sentinel_emitted": False,
        "completion_tokens": None,
        "engineering_classification": "TECHNICAL_INVALID",
        "functional_oracle_post": None,
        "functional_oracle_pre": None,
        "initial_prompt_sha256": None,
        "memory_id": None,
        "memory_provenance": "unresolved_due_to_technical_failure",
        "memory_sha256": None,
        "patch_sha256": hashlib.sha256(b"").hexdigest(),
        "prompt_tokens": None,
        "prohibited_command_attempt_count": 0,
        "prohibited_command_executed": False,
        "protected_file_integrity": False,
        "reasoning_tokens": None,
        "repository_source_sha256": None,
        "request_count": 0,
        "schema": RESULT_SCHEMA,
        "scientific_evidence": False,
        "security_witness_post": None,
        "security_witness_pre": None,
        "seed": seed,
        "step_count": 0,
        "synthetic_validation_only": True,
        "technical_failure": {
            "detail": str(error),
            "error_type": type(error).__name__,
        },
        "technical_rerun_eligible": True,
        "technical_validity": False,
        "termination_reason": "TECHNICAL_INVALID",
        "total_tokens": None,
        "treatment_condition": condition,
    }
    result_path = write_condition_result(condition_root / "result.json", result)
    write_artifact_manifest(condition_root)
    return {
        "artifact_directory": str(condition_root),
        "artifact_manifest_sha256": sha256_file(
            condition_root / "job-manifest.json"
        ),
        "condition": condition,
        "engineering_classification": "TECHNICAL_INVALID",
        "result_sha256": sha256_file(result_path),
        "seed": seed,
        "technical_validity": False,
    }


def run(arguments: argparse.Namespace) -> int:
    project = arguments.project_root.resolve(strict=True)
    artifact_root = arguments.artifact_directory
    if artifact_root.exists() or artifact_root.is_symlink():
        raise FileExistsError(f"synthetic GPU artifact already exists: {artifact_root}")
    artifact_root.mkdir(parents=True, mode=0o700)
    started = datetime.now(UTC)
    freeze = validate_gpu_freeze(project)
    source = validate_source_inventory(project)
    seeds = validate_seed_schedule(project)
    prompts = prompt_evidence(project)
    if arguments.model != MODEL_ID or MODEL_REVISION not in str(arguments.tokenizer_path):
        raise SyntheticGPUError("submitted model identity differs from frozen Qwen3.6")
    model_probe = validate_model(probe_models(arguments.base_url), arguments.model)
    agent_info = mini_swe_info(arguments.mini_python)
    live_preflight = {
        "agent_available": agent_info.available,
        "agent_version": agent_info.version,
        "model_diagnostic": model_probe.diagnostic,
        "model_ok": model_probe.ok,
        "models": list(model_probe.models),
        "pass": model_probe.ok and agent_info.available,
    }
    write_json(artifact_root / "live-preflight.json", live_preflight)
    if not live_preflight["pass"]:
        raise SyntheticGPUError("live Qwen3.6 or mini-SWE preflight failed")
    write_json(
        artifact_root / "run-identity.json",
        {
            "artifact_root": str(artifact_root),
            "condition_order": list(EXPECTED_EXECUTION_ORDER),
            "freeze_sha256": freeze["sha256"],
            "model": MODEL_ID,
            "model_revision": MODEL_REVISION,
            "schema": "synthetic-memory-gpu-smoke-run-v1",
            "scientific_evidence": False,
            "started_at_utc": started.isoformat(),
        },
    )
    summaries: list[dict[str, Any]] = []
    for ordinal, condition in enumerate(EXPECTED_EXECUTION_ORDER, start=1):
        condition_root = artifact_root / "conditions" / f"{ordinal:02d}-{condition}"
        try:
            summary = _run_condition(
                project=project,
                artifact_root=artifact_root,
                condition=condition,
                ordinal=ordinal,
                base_url=arguments.base_url,
                mini_python=arguments.mini_python,
                tokenizer_path=arguments.tokenizer_path,
                seed=seeds["seeds"][condition],
                agent_timeout=arguments.agent_timeout,
                expected_prompts=prompts,
            )
        except BaseException as error:
            summary = _technical_failure(
                condition_root=condition_root,
                condition=condition,
                seed=seeds["seeds"][condition],
                error=error,
            )
        summaries.append(summary)
    provenance = [
        row["provenance"] for row in summaries if "provenance" in row
    ]
    contamination = (
        contamination_check(provenance)
        if len(provenance) == len(EXPECTED_EXECUTION_ORDER)
        else {"pass": False, "reason": "one or more condition preparations failed"}
    )
    all_technical = all(row["technical_validity"] for row in summaries)
    pipeline_pass = bool(
        len(summaries) == 4
        and all_technical
        and contamination.get("pass") is True
        and prompts["pass"]
        and source["pass"]
    )
    combined = {
        "condition_summaries": summaries,
        "contamination_check": contamination,
        "decision": (
            "SYNTHETIC_TREATMENT_PIPELINE_PASS"
            if pipeline_pass
            else "SYNTHETIC_TREATMENT_PIPELINE_FAIL"
        ),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "freeze_sha256": freeze["sha256"],
        "model_outcomes_are_scientific_evidence": False,
        "pipeline_integrity_independent_of_functional_or_security_outcome": True,
        "schema": "synthetic-memory-gpu-smoke-combined-result-v1",
        "scientific_evidence": False,
        "technical_condition_count": sum(
            bool(row["technical_validity"]) for row in summaries
        ),
    }
    write_canonical_json(artifact_root / "combined-result.json", combined)
    write_artifact_manifest(artifact_root)
    print(json.dumps(combined, sort_keys=True))
    return 0 if pipeline_pass else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--artifact-directory", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--tokenizer-path", required=True)
    parser.add_argument("--mini-python", required=True)
    parser.add_argument("--agent-timeout", type=int, default=600)
    return run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
