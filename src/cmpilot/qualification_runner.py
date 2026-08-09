"""One-shot execution of one frozen no-memory qualification task."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import stat
import time
from typing import Any

from .artifact_logger import write_json, write_text
from .calculator_finalizer import (
    initialize_finalizer_state,
    run_total_finalization,
)
from .mini_swe_adapter import mini_swe_info
from .post_agent_pipeline import analyze_task_repository
from .qualification import (
    CMPILOT_PYTHON,
    FROZEN_HARNESS_COMMIT,
    MODEL_REVISION,
    QualificationError,
    copy_immutable_oracle_bundle,
    load_json,
    load_suite_manifest,
    no_memory_prompt_check,
    prepare_qualification_working_copy,
    render_task_prompts,
    run_external_oracle,
    sha256_file,
    task_paths,
    task_policy_from_manifest,
    validate_oracle_bundle,
    validate_task_manifest,
)
from .qualification_adapter import command, write_qualification_adapter
from .repository_manager import (
    final_patch,
    git,
    repository_content_digest,
    repository_preparation_record,
    run_tests,
    template_snapshot,
)
from .smoke_runner import (
    AgentExecution,
    _safe_agent_environment,
    _source_snapshot,
    _snapshot_artifact,
    _trajectory_metrics,
    execute_agent,
)
from .task_file_policy import (
    capture_protected_path_state,
    check_protected_path_integrity,
)
from .vllm_client import probe_models, validate_model


@dataclass(frozen=True)
class QualificationRunConfig:
    project_root: Path
    suite_manifest: Path
    task_manifest: Path
    freeze_manifest: Path
    artifact_directory: Path
    base_url: str
    model: str
    mini_python: str
    agent_timeout: int = 600
    server_pid: int | None = None
    runtime_integrity: Path | None = None


def _combined(result: Any) -> str:
    return (result.stdout or "") + (result.stderr or "")


def _safe_remove_scratch(path: Path, *, artifact: Path) -> dict[str, Any]:
    resolved_artifact = artifact.resolve(strict=True)
    resolved = path.resolve(strict=False)
    try:
        resolved.relative_to(resolved_artifact)
    except ValueError as error:
        raise QualificationError(f"scratch path escapes run artifact: {path}") from error
    symlinks = [
        str(item.relative_to(path))
        for item in path.rglob("*")
        if item.is_symlink()
    ] if path.is_dir() else []
    if symlinks:
        raise QualificationError(f"scratch contains symlinks: {symlinks}")
    if path.exists():
        shutil.rmtree(path)
    return {
        "complete": not path.exists(),
        "pass": not path.exists(),
        "path": str(path),
        "symlinks": symlinks,
    }


def _shutdown_server(server_pid: int | None) -> dict[str, Any]:
    if server_pid is None:
        return {"complete": True, "pass": True, "server_pid": None, "scope": "not owned"}
    if server_pid <= 1:
        raise QualificationError("refusing to signal an invalid server process group")
    graceful = True
    force_kill_used = False
    def process_running() -> bool:
        try:
            os.kill(server_pid, 0)
        except ProcessLookupError:
            return False
        stat_path = Path(f"/proc/{server_pid}/stat")
        try:
            state = stat_path.read_text(encoding="ascii").split()[2]
        except (OSError, IndexError):
            return True
        return state != "Z"

    if not process_running():
        return {
            "complete": True,
            "pass": True,
            "server_pid": server_pid,
            "already_exited": True,
        }
    os.killpg(server_pid, signal.SIGTERM)
    for _ in range(30):
        if not process_running():
            break
        time.sleep(1)
    else:
        graceful = False
        force_kill_used = True
        os.killpg(server_pid, signal.SIGKILL)
    return {
        "complete": True,
        "force_kill_used": force_kill_used,
        "graceful": graceful,
        "pass": True,
        "server_pid": server_pid,
    }


def _task_by_id(project: Path, suite: dict[str, Any], task_id: str) -> dict[str, Any]:
    records = suite.get("tasks")
    if not isinstance(records, list):
        raise QualificationError("suite task inventory is missing")
    matching = [record for record in records if record.get("task_id") == task_id]
    if len(matching) != 1:
        raise QualificationError(f"suite task ID is not unique: {task_id}")
    record = matching[0]
    manifest_path = project / record["manifest_path"]
    if sha256_file(manifest_path) != record["manifest_sha256"]:
        raise QualificationError(f"suite task manifest hash mismatch: {task_id}")
    return load_json(manifest_path)


def run_qualification_task(config: QualificationRunConfig) -> int:
    """Run one frozen task once and finalize every model-level outcome."""
    started = datetime.now(UTC)
    artifact = config.artifact_directory
    if artifact.exists() or artifact.is_symlink():
        raise FileExistsError(f"qualification artifact already exists: {artifact}")
    artifact.mkdir(parents=True, mode=0o700)
    state_path = artifact / "finalizer-state.json"
    initialize_finalizer_state(state_path, run_id=artifact.name)

    project = config.project_root.resolve(strict=True)
    suite = load_suite_manifest(config.suite_manifest)
    requested_task = load_json(config.task_manifest)
    task_id = str(requested_task.get("task_id"))
    task = _task_by_id(project, suite, task_id)
    if task != requested_task:
        raise QualificationError("submitted task manifest differs from suite inventory")
    errors = validate_task_manifest(project, task)
    if errors:
        raise QualificationError(f"task manifest validation failed: {errors}")
    paths = task_paths(project, task)
    policy = task_policy_from_manifest(project, task)
    task_text = paths["task_instruction"].read_text(encoding="utf-8")
    prompts = render_task_prompts(task_text, policy)
    memory_check = no_memory_prompt_check(prompts)
    if not memory_check["pass"]:
        raise QualificationError("qualification prompt contains memory material")

    input_hashes = {
        "freeze_manifest": sha256_file(config.freeze_manifest),
        "suite_manifest": sha256_file(config.suite_manifest),
        "task_manifest": sha256_file(config.task_manifest),
        "task_policy": sha256_file(paths["task_policy"]),
        "task_instruction": sha256_file(paths["task_instruction"]),
    }
    expected_freeze = suite["freeze_manifest"]["sha256"]
    if input_hashes["freeze_manifest"] != expected_freeze:
        raise QualificationError("freeze manifest hash differs from frozen suite")
    if config.model != str(task["model_configuration"]["served_model_path"]):
        raise QualificationError("submitted model path differs from task manifest")
    if task["model_configuration"]["revision"] != MODEL_REVISION:
        raise QualificationError("submitted model revision differs from frozen revision")

    write_json(artifact / "input-hashes.json", input_hashes)
    write_json(artifact / "task-manifest.json", task)
    write_json(artifact / "canonical-prompts.json", prompts)
    write_json(artifact / "no-memory-validation.json", memory_check)
    write_json(
        artifact / "run-identity.json",
        {
            "frozen_harness_commit": FROZEN_HARNESS_COMMIT,
            "model": config.model,
            "project_root": str(project),
            "python": str(CMPILOT_PYTHON),
            "python_version": platform.python_version(),
            "schema": "qwen32b-qualification-run-identity-v1",
            "started_at_utc": started.isoformat(),
            "task_id": task_id,
            "treatment": "no_memory",
        },
    )

    source = paths["repository"].resolve(strict=True)
    source_before = template_snapshot(source)
    validate_oracle_bundle(
        paths["oracle"],
        expected_manifest_sha256=task["immutable_external_oracle"][
            "manifest_sha256"
        ],
    )
    model_probe = validate_model(probe_models(config.base_url), config.model)
    agent_info = mini_swe_info(config.mini_python)
    write_json(
        artifact / "live-preflight.json",
        {
            "agent": {
                "available": agent_info.available,
                "diagnostic": agent_info.diagnostic,
                "version": agent_info.version,
            },
            "model": {
                "diagnostic": model_probe.diagnostic,
                "models": list(model_probe.models),
                "ok": model_probe.ok,
            },
            "pass": model_probe.ok and agent_info.available,
        },
    )
    if not model_probe.ok or not agent_info.available:
        raise QualificationError("live model or mini-SWE preflight failed")

    working_copy, initial_commit = prepare_qualification_working_copy(
        source,
        destination=artifact / "working-copy",
        task_policy=policy,
    )
    preparation = repository_preparation_record(source, working_copy, initial_commit)
    protected_baseline = capture_protected_path_state(working_copy, policy)
    write_json(artifact / "repository-preparation.json", preparation)
    write_json(
        artifact / "protected-path-baseline.json",
        {
            "paths": [item.as_dict() for item in protected_baseline],
            "policy_version": policy.version,
        },
    )
    write_json(
        artifact / "initial-file-hashes.json",
        _snapshot_artifact(_source_snapshot(working_copy)),
    )
    visible_before = run_tests(working_copy)
    write_text(artifact / "visible-tests-before.stdout", visible_before.stdout or "")
    write_text(artifact / "visible-tests-before.stderr", visible_before.stderr or "")
    write_text(
        artifact / "visible-tests-before.exit", f"{visible_before.returncode}\n"
    )
    if visible_before.returncode == 0:
        raise QualificationError("unpatched visible test suite unexpectedly passed")

    adapter = artifact / "mini_swe_adapter.py"
    adapter_record = write_qualification_adapter(adapter)
    write_json(artifact / "qualification-adapter.json", adapter_record)
    trajectory = artifact / "trajectory.json"
    environment = _safe_agent_environment(
        artifact,
        working_copy,
        type(
            "AdapterConfig",
            (),
            {
                "model": config.model,
                "tokenizer_path": config.model,
                "base_url": config.base_url,
            },
        )(),
        trajectory,
        paths["task_instruction"],
    )
    environment.update(
        {
            "CMPILOT_FROZEN_ADAPTER_SHA256": adapter_record[
                "frozen_adapter_sha256"
            ],
            "CMPILOT_TASK_POLICY_SHA256": sha256_file(paths["task_policy"]),
            "CMPILOT_TASK_POLICY_SOURCE": str(paths["task_policy"]),
        }
    )
    command_line = command(config.mini_python, adapter)
    write_json(artifact / "agent-command.json", command_line)
    agent_started = time.perf_counter()
    try:
        execution = execute_agent(
            command_line,
            working_copy,
            environment,
            config.agent_timeout,
        )
    except BaseException as error:
        execution = AgentExecution(
            None,
            "",
            "",
            False,
            f"agent execution raised {type(error).__name__}: {error}",
        )
    agent_wall_time = time.perf_counter() - agent_started
    write_text(artifact / "agent.stdout", execution.stdout)
    write_text(artifact / "agent.stderr", execution.stderr)
    write_json(
        artifact / "agent-execution.json",
        {
            "exit_code": execution.exit_code,
            "launch_error": execution.launch_error,
            "timed_out": execution.timed_out,
            "wall_time_seconds": agent_wall_time,
        },
    )

    patch = final_patch(working_copy, initial_commit)
    status = git(working_copy, "status", "--short").stdout
    write_text(artifact / "final.patch", patch)
    write_text(artifact / "git-status.txt", status)
    write_json(
        artifact / "final-file-hashes.json",
        _snapshot_artifact(_source_snapshot(working_copy)),
    )
    visible_after = run_tests(working_copy)
    write_text(artifact / "visible-tests-after.stdout", visible_after.stdout or "")
    write_text(artifact / "visible-tests-after.stderr", visible_after.stderr or "")
    write_text(artifact / "visible-tests-after.exit", f"{visible_after.returncode}\n")
    trajectory_metrics = _trajectory_metrics(
        trajectory, {str(path) for path in _source_snapshot(working_copy)}
    )
    write_json(artifact / "trajectory-metrics.json", trajectory_metrics)

    finding = analyze_task_repository(
        source_repository=source,
        agent_repository=working_copy,
        task_policy=policy,
        prohibited_command_executed=bool(
            trajectory_metrics.get("environment_mutation_executed")
            or trajectory_metrics.get("network_access_executed")
        ),
    )
    protected = check_protected_path_integrity(working_copy, protected_baseline)
    immutable_oracle = copy_immutable_oracle_bundle(
        paths["oracle"],
        artifact / "immutable-oracle",
        expected_manifest_sha256=task["immutable_external_oracle"][
            "manifest_sha256"
        ],
    )
    oracle = run_external_oracle(
        source_repository=source,
        agent_repository=working_copy,
        oracle_bundle=immutable_oracle,
        expected_manifest_sha256=task["immutable_external_oracle"][
            "manifest_sha256"
        ],
        destination=artifact / "validation-tree",
        policy=policy,
        artifact_directory=artifact / "external-oracle-artifacts",
    )
    expected_passed = task["expected_reference_patch_oracle_result"]["passed"]
    oracle_pass = (
        oracle.returncode == 0
        and oracle.passed == expected_passed
        and oracle.failed == 0
    )
    source_unchanged = template_snapshot(source) == source_before
    prohibited_executed = bool(
        trajectory_metrics.get("environment_mutation_executed")
        or trajectory_metrics.get("network_access_executed")
    )
    technical_before_finalizer = bool(
        not execution.timed_out
        and execution.launch_error is None
        and execution.exit_code == 0
        and trajectory.is_file()
        and finding.technical_validity == "pass"
        and protected.ok
        and source_unchanged
        and not prohibited_executed
    )
    authorized_patch = bool(
        oracle.allowed_patch.strip()
        and not oracle.disallowed_diff.strip()
        and not finding.disallowed_paths_modified
    )
    repository_competence = bool(
        technical_before_finalizer
        and authorized_patch
        and oracle_pass
        and protected.ok
        and not prohibited_executed
    )
    termination_reason = str(trajectory_metrics.get("termination_reason", ""))
    completion = termination_reason == "Submitted"
    dimensions = {
        "authorized_patch_present": authorized_patch,
        "completion_sentinel_emitted": completion,
        "completion_tokens": trajectory_metrics.get("usage_completion"),
        "immutable_oracle_pass": oracle_pass,
        "prohibited_command_attempted": bool(
            trajectory_metrics.get("policy_violation_count", 0)
        ),
        "prohibited_command_executed": prohibited_executed,
        "prompt_tokens": trajectory_metrics.get("usage_prompt"),
        "protected_file_integrity": protected.ok,
        "repository_competence": repository_competence,
        "request_count": trajectory_metrics.get("model_request_count"),
        "step_count": trajectory_metrics.get("agent_steps"),
        "technical_validity": technical_before_finalizer,
        "termination_reason": termination_reason,
        "wall_time": agent_wall_time,
    }
    write_json(artifact / "outcome-dimensions-pre-finalizer.json", dimensions)

    runtime_integrity = (
        load_json(config.runtime_integrity)
        if config.runtime_integrity is not None
        else {"pass": True, "scope": "runner-only test"}
    )
    scratch = artifact / "agent-tmp"

    def final_repository_capture() -> dict[str, Any]:
        return {
            "changed_files": list(finding.allowed_paths_modified),
            "complete": True,
            "status": status,
        }

    def patch_generation() -> dict[str, Any]:
        return {
            "allowed_paths": list(oracle.allowed_paths_modified),
            "disallowed_paths": list(oracle.disallowed_paths_modified),
            "authorized_patch_present": authorized_patch,
            "pass": not bool(oracle.disallowed_diff.strip()),
            "sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
        }

    def immutable_oracle_stage() -> dict[str, Any]:
        return {**oracle.as_dict(), "functional_pass": oracle_pass, "pass": True}

    def source_integrity() -> dict[str, Any]:
        return {
            "oracle_manifest_unchanged": (
                oracle.manifest_before_sha256 == oracle.manifest_after_sha256
            ),
            "pass": source_unchanged and protected.ok,
            "protected_paths": protected.as_dict(),
            "source_template_unchanged": source_unchanged,
        }

    def project_environment_cache_integrity() -> dict[str, Any]:
        return runtime_integrity

    def shutdown() -> dict[str, Any]:
        result = _shutdown_server(config.server_pid)
        write_json(artifact / "shutdown.json", result)
        return result

    def scratch_cleanup() -> dict[str, Any]:
        result = _safe_remove_scratch(scratch, artifact=artifact)
        write_json(artifact / "scratch-cleanup.json", result)
        return result

    def performance_summary() -> dict[str, Any]:
        return {
            "agent_wall_time_seconds": agent_wall_time,
            "pass": True,
            "request_count": trajectory_metrics.get("model_request_count"),
            "token_usage": trajectory_metrics.get("usage_total"),
        }

    callbacks = {
        "final_repository_capture": final_repository_capture,
        "patch_generation": patch_generation,
        "immutable_oracle": immutable_oracle_stage,
        "source_integrity": source_integrity,
        "project_environment_cache_integrity": project_environment_cache_integrity,
        "shutdown": shutdown,
        "scratch_cleanup": scratch_cleanup,
        "performance_summary": performance_summary,
    }
    outcome = run_total_finalization(
        state_path=state_path,
        artifact_directory=artifact,
        termination_reason=termination_reason or "MODEL_TASK_FAILURE",
        callbacks=callbacks,
        success_label="QWEN32B_QUALIFICATION_TECHNICAL_VALID",
        technical_failure_label="QWEN32B_QUALIFICATION_TECHNICAL_FAILURE",
        requested_exit_code=0,
        initial_technical_validity=technical_before_finalizer,
        base_result={
            "dimensions": dimensions,
            "frozen_harness_commit": FROZEN_HARNESS_COMMIT,
            "model_revision": MODEL_REVISION,
            "task_id": task_id,
            "treatment": "no_memory",
        },
        classification_dimensions=dimensions,
    )
    print(json.dumps({"task_id": task_id, "result": outcome.result}, sort_keys=True))
    return int(outcome.state.final_exit_code or 0)
