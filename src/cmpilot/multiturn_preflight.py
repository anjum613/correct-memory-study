"""CPU-only deterministic multi-turn acceptance test for the direct adapter."""

from __future__ import annotations

import json
import platform
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .artifact_logger import write_json, write_text
from .artifact_preserver import atomic_preserve_directory
from .mock_openai_server import FIRST_ACTION, SECOND_ACTION, DeterministicOpenAIServer
from .repository_manager import template_snapshot
from .smoke_runner import (
    DEFAULT_TASK,
    DEFAULT_TEMPLATE,
    SmokeConfig,
    _source_snapshot,
    _trajectory_metrics,
    run_smoke,
)


PASS_CLASSIFICATION = "MULTITURN_ADAPTER_PREFLIGHT_PASS"
FAIL_CLASSIFICATION = "MULTITURN_ADAPTER_PREFLIGHT_FAIL"
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"


@dataclass(frozen=True)
class MultiturnPreflightConfig:
    mini_python: str
    artifact_dir: Path
    timeout_seconds: int = 90
    model: str = DEFAULT_MODEL
    template: Path = DEFAULT_TEMPLATE
    task_file: Path = DEFAULT_TASK


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            values.append(value)
    return values


def _commands(trajectory: dict[str, Any]) -> list[str]:
    commands: list[str] = []
    messages = trajectory.get("messages", [])
    if not isinstance(messages, list):
        return commands
    for message in messages:
        if not isinstance(message, dict):
            continue
        extra = message.get("extra", {})
        if not isinstance(extra, dict):
            continue
        actions = extra.get("actions", [])
        if not isinstance(actions, list):
            continue
        commands.extend(
            str(action["command"])
            for action in actions
            if isinstance(action, dict) and action.get("command")
        )
    return commands


def _request_histories_are_canonical(requests: list[dict[str, Any]]) -> bool:
    for record in requests:
        request = record.get("request", {})
        messages = request.get("messages", []) if isinstance(request, dict) else []
        serialized = json.dumps(messages, sort_keys=True)
        if "provider_specific_fields" in serialized or '"extra"' in serialized:
            return False
    return True


def run_multiturn_preflight(config: MultiturnPreflightConfig) -> int:
    """Run exactly one mini-SWE trajectory against the deterministic mock."""
    started_at = datetime.now(UTC)
    artifacts = config.artifact_dir
    artifacts.mkdir(parents=True, exist_ok=True)
    write_json(
        artifacts / "preflight-config.json",
        {
            **asdict(config),
            "artifact_dir": str(config.artifact_dir),
            "template": str(config.template),
            "task_file": str(config.task_file),
        },
    )
    template_before = template_snapshot(config.template)
    record_path = artifacts / "mock-requests.jsonl"
    server = DeterministicOpenAIServer(config.model, record_path)
    smoke_exit = 125
    preserve_first = None
    preserve_second = None
    run_source: Path | None = None
    started = time.perf_counter()

    with tempfile.TemporaryDirectory(prefix="cmpilot-multiturn-") as temporary:
        runs_root = Path(temporary) / "agent-runs"
        try:
            server.start()
            write_json(
                artifacts / "mock-server.json",
                {
                    "base_url": server.base_url,
                    "health_url": server.base_url.removesuffix("/v1") + "/health",
                    "model": config.model,
                    "started": True,
                    "vllm_started": False,
                },
            )
            smoke_exit = run_smoke(
                SmokeConfig(
                    base_url=server.base_url,
                    model=config.model,
                    mini_python=config.mini_python,
                    runs_root=runs_root,
                    agent_timeout=config.timeout_seconds,
                    template=config.template,
                    task_file=config.task_file,
                )
            )
        finally:
            server.stop()

        candidates = sorted(path for path in runs_root.glob("smoke-*") if path.is_dir())
        if len(candidates) == 1:
            run_source = candidates[0]
            preserve_first = atomic_preserve_directory(
                run_source, artifacts / "agent-run"
            )
            preserve_second = atomic_preserve_directory(
                run_source, artifacts / "agent-run"
            )

    wall_time = time.perf_counter() - started
    preserved = artifacts / "agent-run"
    trajectory_path = preserved / "trajectory.json"
    trajectory = _load_json(trajectory_path)
    run = _load_json(preserved / "run.json")
    classification = _load_json(preserved / "classification.json")
    initial_hashes = _load_json(preserved / "initial-file-hashes.json")
    final_hashes = _load_json(preserved / "final-file-hashes.json")
    source_manifest = _load_json(preserved / "mini-swe-source-manifest.json")
    requests = server.state.requests
    transport = _load_jsonl(preserved / "model-transport.jsonl")
    patch_history = _load_jsonl(preserved / "patch-history.jsonl")
    commands = _commands(trajectory)
    metrics = _trajectory_metrics(
        trajectory_path, {"calculator.py", "test_calculator.py"}
    )
    patch_text = (
        (preserved / "final.patch").read_text(encoding="utf-8")
        if (preserved / "final.patch").is_file()
        else ""
    )
    trajectory_info = trajectory.get("info", {}) if isinstance(trajectory, dict) else {}
    messages = trajectory.get("messages", []) if isinstance(trajectory, dict) else []
    semantic_first_in_trajectory = any(
        isinstance(message, dict)
        and message.get("role") == "assistant"
        and message.get("content") == FIRST_ACTION
        for message in messages
    )
    semantic_second_in_trajectory = any(
        isinstance(message, dict)
        and message.get("role") == "assistant"
        and message.get("content") == SECOND_ACTION
        for message in messages
    )
    raw_provider_metadata_preserved = bool(transport) and (
        transport[0]
        .get("response", {})
        .get("choices", [{}])[0]
        .get("message", {})
        .get("provider_specific_fields", {})
        .get("mock_transport_metadata")
        == 1
    )
    request_usage_retained = all(
        isinstance(record.get("response", {}).get("usage"), dict)
        for record in transport
        if record.get("classification") == "success"
    )
    preservation_ok = (
        preserve_first is not None
        and preserve_second is not None
        and preserve_first.status == "preserved"
        and preserve_second.status == "already_preserved"
        and preserve_first.tree_sha256 == preserve_second.tree_sha256
        and not (preserved / "agent-run").exists()
    )
    source_unchanged = template_snapshot(config.template) == template_before
    checks = {
        "configuration_accepted": run.get("agent_exit_code") == 0,
        "agent_initialized": any(
            event.get("event") == "agent_initialized"
            for event in _load_jsonl(preserved / "adapter-events.jsonl")
        ),
        "exactly_three_successful_model_requests": len(requests) == 3
        and all(record.get("accepted") for record in requests)
        and len([record for record in transport if record.get("classification") == "success"]) == 3,
        "no_http_schema_retries": len(requests) == 3,
        "canonical_outgoing_histories": _request_histories_are_canonical(requests),
        "second_turn_history_accepted": len(requests) >= 2
        and requests[1].get("accepted") is True,
        "observation_reached_next_request": len(requests) >= 2
        and "NotImplementedError" in json.dumps(requests[1].get("request", {})),
        "valid_repository_inspection": metrics["repository_inspected"]
        and "sed -n '1,160p' calculator.py" in commands,
        "read_only_commands_only": commands
        == [
            "sed -n '1,160p' calculator.py",
            "sed -n '1,220p' test_calculator.py",
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
        ],
        "trajectory_complete": trajectory.get("trajectory_format")
        == "mini-swe-agent-1.1"
        and trajectory_info.get("exit_status") == "Submitted",
        "assistant_semantics_unchanged": semantic_first_in_trajectory
        and semantic_second_in_trajectory,
        "raw_provider_metadata_preserved_separately": raw_provider_metadata_preserved,
        "usage_retained": request_usage_retained and metrics["usage_total"] is not None,
        "source_repository_unchanged": source_unchanged,
        "temporary_repository_unchanged": initial_hashes.get("content_sha256")
        == final_hashes.get("content_sha256"),
        "empty_patch": patch_text == "",
        "cleanup_idempotent": preservation_ok,
        "installed_mini_sources_unchanged": source_manifest.get("all_match") is True,
        "no_authorization_header": all(
            record.get("authorization_present") is False for record in requests
        ),
        "mock_server_stopped": server.stopped,
        "agent_harness_pass": run.get("agent_exit_code") == 0
        and bool(trajectory)
        and metrics["repository_inspected"],
        "model_task_not_claimed_success": classification.get("classification")
        != "secure_functional_success",
    }
    passed = all(checks.values())
    cleanup_lines = [
        f"mock_server_stopped={str(server.stopped).lower()}",
        f"first_preservation={getattr(preserve_first, 'status', 'missing')}",
        f"second_preservation={getattr(preserve_second, 'status', 'missing')}",
        "no_external_model_process_started=true",
        f"no_process_remains={str(server.stopped).lower()}",
    ]
    write_text(artifacts / "process-cleanup.txt", "\n".join(cleanup_lines) + "\n")
    result = {
        "classification": PASS_CLASSIFICATION if passed else FAIL_CLASSIFICATION,
        "reason": (
            "direct adapter completed a sanitized deterministic multi-turn trajectory"
            if passed
            else "one or more deterministic multi-turn checks failed"
        ),
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "hostname": platform.node(),
        "mini_python": config.mini_python,
        "model": config.model,
        "mock_base_url": server.base_url,
        "mock_request_count": len(requests),
        "model_request_count": metrics["model_request_count"],
        "commands": commands,
        "repository_command_count": len(patch_history),
        "patch_size_bytes": len(patch_text.encode("utf-8")),
        "trajectory_path": str(trajectory_path),
        "agent_run_path": str(preserved),
        "smoke_exit_code": smoke_exit,
        "agent_exit_code": run.get("agent_exit_code"),
        "smoke_classification": classification.get("classification"),
        "usage": {
            "prompt_tokens": metrics["usage_prompt"],
            "completion_tokens": metrics["usage_completion"],
            "total_tokens": metrics["usage_total"],
        },
        "wall_time_seconds": wall_time,
        "preservation": {
            "first": asdict(preserve_first) if preserve_first else None,
            "second": asdict(preserve_second) if preserve_second else None,
        },
        "checks": checks,
    }
    write_json(artifacts / "result.json", result)
    write_json(
        artifacts / "classification.json",
        {
            "classification": result["classification"],
            "checks": checks,
            "infrastructure": "PASS",
            "server": "PASS" if len(requests) == 3 else "FAIL",
            "agent_harness": "PASS" if checks["agent_harness_pass"] else "FAIL",
            "model_task_performance": "INCOMPLETE",
        },
    )
    print(f"Multiturn preflight artifacts: {artifacts}")
    print(f"Classification: {result['classification']}")
    return 0 if passed else 1
