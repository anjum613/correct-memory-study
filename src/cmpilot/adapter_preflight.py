"""CPU-only acceptance preflight for the mini-SWE-agent adapter boundary."""

from __future__ import annotations

import json
import platform
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifact_logger import write_json, write_text
from .mini_swe_adapter import command, mini_swe_info, write_adapter
from .repository_manager import final_patch, git, prepare_working_copy, template_snapshot
from .smoke_runner import (
    DEFAULT_TASK,
    DEFAULT_TEMPLATE,
    SmokeConfig,
    _safe_agent_environment,
    _snapshot_artifact,
    _source_snapshot,
    _trajectory_metrics,
    execute_agent,
)


DUMMY_BASE_URL = "http://127.0.0.1:9/v1"
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"
PASS_CLASSIFICATION = "ADAPTER_PREFLIGHT_PASS"
FAIL_CLASSIFICATION = "ADAPTER_PREFLIGHT_FAIL"


@dataclass(frozen=True)
class AdapterPreflightConfig:
    mini_python: str
    artifact_dir: Path
    timeout_seconds: float = 45
    model: str = DEFAULT_MODEL
    base_url: str = DUMMY_BASE_URL
    template: Path = DEFAULT_TEMPLATE
    task_file: Path = DEFAULT_TASK


def _load_events(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            events.append(value)
    return events


def _load_trajectory(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _connection_failure(trajectory: dict[str, Any], events: list[dict[str, Any]]) -> tuple[str, str]:
    messages = trajectory.get("messages", [])
    if isinstance(messages, list) and messages:
        final = messages[-1]
        if isinstance(final, dict):
            extra = final.get("extra", {})
            if isinstance(extra, dict):
                error_type = str(extra.get("exit_status", ""))
                error_message = str(extra.get("exception_str", ""))
                if error_type or error_message:
                    return error_type, error_message
    failures = [event for event in events if event.get("event") == "model_request_failed"]
    if failures:
        return str(failures[-1].get("exception_type", "")), str(failures[-1].get("message", ""))
    return "", ""


def _configuration_artifacts_contain_secrets(artifacts: Path) -> bool:
    names = (
        "agent-config.json",
        "agent-config.yaml",
        "endpoint-config.json",
        "cmpilot-run-metadata.json",
        "adapter-artifact-metadata.json",
        "mini-swe-loader-validation.json",
    )
    forbidden = ("openai_api_key", '"api_key"', "authorization:", "password:", "secret:")
    for name in names:
        path = artifacts / name
        if path.is_file() and any(term in path.read_text(encoding="utf-8").lower() for term in forbidden):
            return True
    return False


def run_adapter_preflight(config: AdapterPreflightConfig) -> int:
    """Run one adapter process and accept only the expected first-request failure."""
    started_at = datetime.now(UTC)
    artifacts = config.artifact_dir
    artifacts.mkdir(parents=True, exist_ok=True)
    result_path = artifacts / "result.json"
    write_json(
        artifacts / "preflight-config.json",
        {
            **asdict(config),
            "artifact_dir": str(config.artifact_dir),
            "template": str(config.template),
            "task_file": str(config.task_file),
        },
    )

    mini_info = mini_swe_info(config.mini_python)
    write_text(artifacts / "agent-version.txt", (mini_info.version or "unavailable") + "\n")
    if not mini_info.available:
        write_json(
            result_path,
            {
                "classification": FAIL_CLASSIFICATION,
                "reason": mini_info.diagnostic,
                "checks": {"mini_swe_agent_2_4_6": False},
            },
        )
        return 1
    if config.base_url != DUMMY_BASE_URL:
        write_json(
            result_path,
            {
                "classification": FAIL_CLASSIFICATION,
                "reason": f"adapter preflight requires {DUMMY_BASE_URL}",
                "checks": {"dummy_endpoint_exact": False},
            },
        )
        return 1

    template_before = template_snapshot(config.template)
    working_copy, initial_commit = prepare_working_copy(
        config.template,
        destination=artifacts / "working-copy",
    )
    initial_snapshot = _source_snapshot(working_copy)
    write_json(artifacts / "original-file-hashes.json", _snapshot_artifact(template_before))
    write_json(artifacts / "initial-file-hashes.json", _snapshot_artifact(initial_snapshot))
    write_text(artifacts / "initial-commit.txt", initial_commit + "\n")
    task_text = config.task_file.read_text(encoding="utf-8")
    write_text(artifacts / "task.txt", task_text)
    write_text(artifacts / "task-instruction.md", task_text)

    adapter_path = artifacts / "mini_swe_adapter.py"
    trajectory_path = artifacts / "trajectory.json"
    events_path = artifacts / "adapter-events.jsonl"
    write_adapter(adapter_path)
    command_line = command(config.mini_python, adapter_path)
    write_text(artifacts / "agent-command.txt", " ".join(command_line) + "\n")

    smoke_config = SmokeConfig(
        base_url=config.base_url,
        model=config.model,
        mini_python=config.mini_python,
        runs_root=artifacts,
        agent_timeout=int(config.timeout_seconds),
        template=config.template,
        task_file=config.task_file,
    )
    environment = _safe_agent_environment(
        artifacts,
        working_copy,
        smoke_config,
        trajectory_path,
        artifacts / "task-instruction.md",
    )
    environment["CMPILOT_ADAPTER_PREFLIGHT"] = "1"
    environment["MSWEA_MODEL_RETRY_STOP_AFTER_ATTEMPT"] = "1"

    started = time.perf_counter()
    execution = execute_agent(command_line, working_copy, environment, config.timeout_seconds)
    wall_time = time.perf_counter() - started
    write_text(artifacts / "agent.stdout.log", execution.stdout)
    write_text(artifacts / "agent.stderr.log", execution.stderr)
    write_text(artifacts / "agent-stdout.txt", execution.stdout)
    write_text(artifacts / "agent-stderr.txt", execution.stderr)

    patch = final_patch(working_copy, initial_commit)
    write_text(artifacts / "patch.diff", patch)
    write_text(artifacts / "final.patch", patch)
    status = git(working_copy, "status", "--short")
    write_text(artifacts / "git-status.txt", status.stdout + status.stderr)
    final_snapshot = _source_snapshot(working_copy)
    write_json(artifacts / "final-file-hashes.json", _snapshot_artifact(final_snapshot))

    events = _load_events(events_path)
    event_names = [str(event.get("event", "")) for event in events]
    trajectory = _load_trajectory(trajectory_path)
    metrics = _trajectory_metrics(trajectory_path, {str(path) for path in initial_snapshot})
    error_type, error_message = _connection_failure(trajectory, events)
    info = trajectory.get("info", {}) if isinstance(trajectory, dict) else {}
    submission = info.get("submission", "") if isinstance(info, dict) else ""
    patch_history = artifacts / "patch-history.jsonl"
    no_repository_commands = not patch_history.is_file() or not patch_history.read_text(encoding="utf-8").strip()
    connection_text = (error_type + " " + error_message + " " + execution.stderr).lower()
    expected_connection_error = error_type in {"APIConnectionError", "InternalServerError"} and (
        "connection error" in connection_text or "connection refused" in connection_text
    )
    config_artifacts = (
        "agent-config.json",
        "agent-config.yaml",
        "agent-config-types.json",
        "mini-swe-loader-validation.json",
    )
    checks = {
        "mini_swe_agent_2_4_6": mini_info.version == "2.4.6",
        "dummy_endpoint_exact": config.base_url == DUMMY_BASE_URL,
        "configuration_serialized": "configuration_serialized" in event_names,
        "configuration_artifacts_present": all((artifacts / name).is_file() for name in config_artifacts),
        "mini_swe_config_validated": "mini_swe_config_validated" in event_names,
        "agent_initialized": "agent_initialized" in event_names,
        "first_model_request_attempted": event_names.count("model_request_attempted") == 1,
        "expected_connection_error": expected_connection_error,
        "adapter_failed_after_request": execution.exit_code not in (None, 0) and not execution.timed_out,
        "trajectory_present": bool(trajectory),
        "trajectory_request_count_one": metrics["model_request_count"] == 1,
        "trajectory_not_completed": info.get("exit_status") == error_type and expected_connection_error and not submission,
        "no_completed_event": "agent_completed" not in event_names,
        "no_repository_commands": no_repository_commands and metrics["command_count"] == 0,
        "empty_patch": not patch,
        "working_copy_hashes_unchanged": final_snapshot == initial_snapshot,
        "working_copy_git_clean": not status.stdout.strip(),
        "source_template_unchanged": template_snapshot(config.template) == template_before,
        "secrets_not_written": not _configuration_artifacts_contain_secrets(artifacts),
    }
    passed = all(checks.values())
    result = {
        "classification": PASS_CLASSIFICATION if passed else FAIL_CLASSIFICATION,
        "reason": "expected dummy-endpoint connection failure after adapter initialization" if passed else "one or more adapter acceptance checks failed",
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "hostname": platform.node(),
        "python": sys.version,
        "mini_swe_agent_version": mini_info.version,
        "base_url": config.base_url,
        "model": config.model,
        "agent_command": command_line,
        "adapter_process_exit": execution.exit_code,
        "adapter_timed_out": execution.timed_out,
        "adapter_wall_time_seconds": wall_time,
        "expected_error_type": error_type,
        "expected_error_message": error_message,
        "event_sequence": event_names,
        "trajectory_metrics": metrics,
        "checks": checks,
    }
    write_json(result_path, result)
    print(f"Adapter preflight artifacts: {artifacts}")
    print(f"Classification: {result['classification']}")
    return 0 if passed else 1
