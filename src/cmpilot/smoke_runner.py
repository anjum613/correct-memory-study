"""One-shot, artifact-preserving engineering calculator smoke test."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import re
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from .artifact_logger import create_run_directory, write_json, write_text
from .mini_swe_adapter import MiniSWEInfo, command, mini_swe_info, write_adapter
from .outcome_classifier import classify
from .repository_manager import final_patch, git, prepare_working_copy, run_tests, template_snapshot
from .vllm_client import ModelProbe, probe_models, validate_model


DEFAULT_TEMPLATE = Path(__file__).parents[2] / "tasks" / "smoke_test" / "repository"
DEFAULT_TASK = Path(__file__).parents[2] / "tasks" / "smoke_test" / "task.md"
DEFAULT_AGENT_CONFIG = Path(__file__).parents[2] / "configs" / "agent" / "mini_swe_agent_smoke.yaml"
EXIT_SUCCESS = 0
EXIT_INFRASTRUCTURE_FAILURE = 2
EXIT_FUNCTIONAL_FAILURE = 3


@dataclass(frozen=True)
class SmokeConfig:
    base_url: str
    model: str
    mini_python: str
    runs_root: Path
    agent_timeout: int = 600
    template: Path = DEFAULT_TEMPLATE
    task_file: Path = DEFAULT_TASK


@dataclass(frozen=True)
class PreflightResult:
    ok: bool
    diagnostic: str
    probe: ModelProbe | None
    mini_swe: MiniSWEInfo


@dataclass(frozen=True)
class AgentExecution:
    exit_code: int | None
    stdout: str
    stderr: str
    timed_out: bool
    launch_error: str | None = None


def resolve_config(arguments, environment: dict[str, str] | None = None) -> SmokeConfig:
    """Resolve CLI options over environment variables without machine-specific defaults."""
    env = os.environ if environment is None else environment
    return SmokeConfig(
        base_url=getattr(arguments, "base_url", None) or env.get("VLLM_BASE_URL", ""),
        model=getattr(arguments, "model", None) or env.get("VLLM_MODEL", "Qwen/Qwen2.5-Coder-1.5B-Instruct"),
        mini_python=getattr(arguments, "mini_python", None) or env.get("MINI_SWE_PYTHON", ""),
        runs_root=Path(getattr(arguments, "runs_root", None) or env.get("CMPILOT_RUNS_ROOT", "experiment-runs")),
        agent_timeout=getattr(arguments, "agent_timeout", 600),
    )


def preflight(config: SmokeConfig) -> PreflightResult:
    """Run every non-destructive dependency check required before a live run."""
    not_checked = MiniSWEInfo(False, "", "not checked")
    if not config.base_url.strip():
        return PreflightResult(False, "VLLM_BASE_URL or --base-url is required", None, not_checked)
    if not config.model.strip():
        return PreflightResult(False, "VLLM_MODEL or --model is required", None, not_checked)
    if config.agent_timeout <= 0:
        return PreflightResult(False, "agent timeout must be greater than zero", None, not_checked)
    if not config.template.is_dir() or not config.task_file.is_file():
        return PreflightResult(False, "smoke template or task instruction is missing", None, not_checked)

    model_probe = validate_model(probe_models(config.base_url), config.model)
    agent_info = mini_swe_info(config.mini_python)
    diagnostics = [result for result in (model_probe.diagnostic if not model_probe.ok else "", agent_info.diagnostic if not agent_info.available else "") if result]
    if diagnostics:
        return PreflightResult(False, "; ".join(diagnostics), model_probe, agent_info)
    return PreflightResult(True, "preflight passed", model_probe, agent_info)


def _config_artifact(config: SmokeConfig) -> dict[str, object]:
    return {
        **asdict(config),
        "runs_root": str(config.runs_root),
        "template": str(config.template),
        "task_file": str(config.task_file),
    }


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _snapshot_digest(snapshot: dict[Path, bytes]) -> str:
    digest = hashlib.sha256()
    for relative_path in sorted(snapshot):
        digest.update(str(relative_path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(snapshot[relative_path])
        digest.update(b"\0")
    return digest.hexdigest()


def _source_snapshot(root: Path) -> dict[Path, bytes]:
    """Snapshot repository content while excluding Git and test caches."""
    excluded = {".git", ".pytest_cache", "__pycache__"}
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in excluded for part in path.relative_to(root).parts)
        and path.suffix != ".pyc"
    }


def _snapshot_artifact(snapshot: dict[Path, bytes]) -> dict[str, object]:
    return {
        "content_sha256": _snapshot_digest(snapshot),
        "file_count": len(snapshot),
        "files": {
            str(path): {"sha256": _sha256(contents), "size_bytes": len(contents)}
            for path, contents in sorted(snapshot.items())
        },
    }


def _trajectory_metrics(path: Path, repository_files: set[str]) -> dict[str, object]:
    """Extract request, token, command, inspection, and termination evidence."""
    empty: dict[str, object] = {
        "agent_steps": 0,
        "model_request_count": 0,
        "command_count": 0,
        "usage_prompt": None,
        "usage_completion": None,
        "usage_total": None,
        "termination_reason": "trajectory missing",
        "repository_inspected": False,
        "files_inspected": [],
        "technical_validity": "UNKNOWN",
        "protocol_safety_status": "UNKNOWN",
        "model_format_status": "UNKNOWN",
        "invalid_response_count": 0,
        "invalid_action_count": 0,
        "executed_action_count": 0,
        "repository_progress": False,
        "functional_outcome": "UNKNOWN",
        "failure_dimension": "unknown",
        "command_authorization_status": "UNKNOWN",
        "policy_version": None,
        "policy_violation_count": 0,
        "prohibited_command_categories": [],
        "repeated_policy_violation_count": 0,
        "environment_mutation_attempted": False,
        "environment_mutation_executed": False,
        "network_access_attempted": False,
        "network_access_executed": False,
    }
    if not path.is_file():
        return empty
    try:
        trajectory = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {**empty, "termination_reason": "trajectory unreadable"}

    messages = trajectory.get("messages", [])
    if not isinstance(messages, list):
        messages = []
    commands: list[str] = []
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    usage_seen = False
    for message in messages:
        if not isinstance(message, dict):
            continue
        extra = message.get("extra", {})
        if not isinstance(extra, dict):
            continue
        actions = extra.get("actions", [])
        if (
            isinstance(actions, list)
            and not extra.get("protocol_rejected")
            and not extra.get("action_policy_rejected")
        ):
            commands.extend(
                str(action.get("command", ""))
                for action in actions
                if isinstance(action, dict) and action.get("command")
            )
        response = extra.get("response", {})
        if not isinstance(response, dict):
            continue
        usage = response.get("usage", {})
        if not isinstance(usage, dict):
            continue
        values = {
            "prompt": usage.get("prompt_tokens"),
            "completion": usage.get("completion_tokens"),
            "total": usage.get("total_tokens"),
        }
        if any(isinstance(value, int) for value in values.values()):
            usage_seen = True
            prompt_tokens += values["prompt"] if isinstance(values["prompt"], int) else 0
            completion_tokens += values["completion"] if isinstance(values["completion"], int) else 0
            total_tokens += values["total"] if isinstance(values["total"], int) else 0

    info = trajectory.get("info", {}) if isinstance(trajectory, dict) else {}
    model_stats = info.get("model_stats", {}) if isinstance(info, dict) else {}
    protocol = info.get("protocol", {}) if isinstance(info, dict) else {}
    if not isinstance(protocol, dict):
        protocol = {}
    protocol_defaults = {
        "technical_validity": "UNKNOWN",
        "protocol_safety_status": "UNKNOWN",
        "model_format_status": "UNKNOWN",
        "invalid_response_count": 0,
        "invalid_action_count": 0,
        "executed_action_count": len(commands),
        "repository_progress": False,
        "functional_outcome": "UNKNOWN",
        "failure_dimension": "unknown",
        "command_authorization_status": "UNKNOWN",
        "policy_version": None,
        "policy_violation_count": 0,
        "prohibited_command_categories": [],
        "repeated_policy_violation_count": 0,
        "environment_mutation_attempted": False,
        "environment_mutation_executed": False,
        "network_access_attempted": False,
        "network_access_executed": False,
    }
    protocol_metrics = {
        key: protocol.get(key, default)
        for key, default in protocol_defaults.items()
    }
    model_requests = model_stats.get("api_calls", len(commands)) if isinstance(model_stats, dict) else len(commands)
    inspected_files = sorted(
        relative_path
        for relative_path in repository_files
        if any(relative_path in command for command in commands)
    )
    inspection_pattern = re.compile(r"(^|[;&|]\s*)(ls|find|cat|sed|head|tail|grep|rg|python\s+-m\s+pytest|pytest)\b")
    repository_inspected = bool(inspected_files) or any(inspection_pattern.search(command) for command in commands)
    return {
        "agent_steps": model_requests,
        "model_request_count": model_requests,
        "command_count": len(commands),
        "usage_prompt": prompt_tokens if usage_seen else None,
        "usage_completion": completion_tokens if usage_seen else None,
        "usage_total": total_tokens if usage_seen else None,
        "termination_reason": info.get("exit_status", "") if isinstance(info, dict) else "",
        "repository_inspected": repository_inspected,
        "files_inspected": inspected_files,
        **protocol_metrics,
    }


def _runtime_dependency_versions(mini_python: str) -> dict[str, object]:
    """Capture the specific libraries used by the verified adapter, not secrets or full environments."""
    script = """import importlib.metadata as metadata
import json
names = ['mini-swe-agent', 'litellm', 'openai', 'PyYAML', 'pydantic']
versions = {}
for name in names:
    try:
        versions[name] = metadata.version(name)
    except metadata.PackageNotFoundError:
        versions[name] = None
print(json.dumps(versions, sort_keys=True))
"""
    try:
        result = subprocess.run([mini_python, "-c", script], text=True, capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as error:
        return {"diagnostic": f"could not collect mini-SWE-agent dependency versions: {error}"}
    if result.returncode != 0:
        return {"diagnostic": result.stderr.strip() or "could not collect mini-SWE-agent dependency versions"}
    try:
        versions = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"diagnostic": "mini-SWE-agent dependency-version output was invalid JSON"}
    return {"adapter_runtime": versions}


def _command_preview(config: SmokeConfig, artifact_directory: Path) -> list[str]:
    return command(config.mini_python or "<MINI_SWE_PYTHON>", artifact_directory / "mini_swe_adapter.py")


def dry_run(config: SmokeConfig) -> int:
    """Show the real preflight outcome without writing artifacts or launching an agent."""
    result = preflight(config)
    prospective_artifacts = config.runs_root / "smoke-YYYYMMDD-HHMMSS-<short-id>"
    print("Resolved configuration:")
    print(f"  base URL: {config.base_url}")
    print(f"  model: {config.model}")
    print(f"  mini Python: {config.mini_python}")
    print(f"  runs root: {config.runs_root}")
    print(f"  agent timeout: {config.agent_timeout}s")
    print(f"Would create artifacts: {prospective_artifacts}")
    print(f"Would create isolated working copy: {prospective_artifacts / 'working-copy'}")
    print(f"Would invoke exactly once: {' '.join(_command_preview(config, prospective_artifacts))}")
    print(f"Preflight: {result.diagnostic}")
    return EXIT_SUCCESS if result.ok else EXIT_INFRASTRUCTURE_FAILURE


def _safe_agent_environment(
    artifacts: Path,
    working_copy: Path,
    config: SmokeConfig,
    trajectory: Path,
    task_instruction: Path,
) -> dict[str, str]:
    """Supply only a minimal environment and an isolated home to the evaluated agent."""
    agent_home = artifacts / "agent-home"
    agent_tmp = artifacts / "agent-tmp"
    agent_home.mkdir(exist_ok=True)
    agent_tmp.mkdir(exist_ok=True)
    return {
        "PATH": os.environ.get("PATH", os.defpath),
        "HOME": str(agent_home),
        "XDG_CONFIG_HOME": str(agent_home / "config"),
        "TMPDIR": str(agent_tmp),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "NO_PROXY": "127.0.0.1,localhost",
        "no_proxy": "127.0.0.1,localhost",
        "CMPILOT_REPOSITORY": str(working_copy),
        "CMPILOT_TASK_FILE": str(task_instruction),
        "CMPILOT_TRAJECTORY": str(trajectory),
        "CMPILOT_PATCH_HISTORY": str(artifacts / "patch-history.jsonl"),
        "CMPILOT_AGENT_CONFIG_SOURCE": str(DEFAULT_AGENT_CONFIG),
        "CMPILOT_AGENT_CONFIG_ARTIFACT": str(artifacts / "agent-config.yaml"),
        "CMPILOT_AGENT_CONFIG_JSON_ARTIFACT": str(artifacts / "agent-config.json"),
        "CMPILOT_AGENT_CONFIG_TYPES_ARTIFACT": str(artifacts / "agent-config-types.json"),
        "CMPILOT_LOADER_VALIDATION_ARTIFACT": str(artifacts / "mini-swe-loader-validation.json"),
        "CMPILOT_RUN_METADATA_ARTIFACT": str(artifacts / "cmpilot-run-metadata.json"),
        "CMPILOT_ENDPOINT_CONFIG_ARTIFACT": str(artifacts / "endpoint-config.json"),
        "CMPILOT_ARTIFACT_METADATA_ARTIFACT": str(artifacts / "adapter-artifact-metadata.json"),
        "CMPILOT_ADAPTER_EVENTS": str(artifacts / "adapter-events.jsonl"),
        "CMPILOT_MODEL_TRANSPORT_ARTIFACT": str(artifacts / "model-transport.jsonl"),
        "CMPILOT_MINI_SOURCE_MANIFEST_ARTIFACT": str(artifacts / "mini-swe-source-manifest.json"),
        "CMPILOT_COMMAND_POLICY_ARTIFACT": str(artifacts / "command-authorization-policy.json"),
        "CMPILOT_AGENT_PATH": os.environ.get("PATH", os.defpath),
        "CMPILOT_MODEL": config.model,
        "CMPILOT_BASE_URL": config.base_url,
    }


def execute_agent(command_line: list[str], cwd: Path, environment: dict[str, str], timeout: float) -> AgentExecution:
    """Run exactly one child process and cleanly terminate its process group on timeout."""
    try:
        process = subprocess.Popen(
            command_line,
            cwd=cwd,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=os.name == "posix",
        )
    except OSError as error:
        return AgentExecution(None, "", "", False, f"could not launch mini-SWE-agent: {error}")

    try:
        stdout, stderr = process.communicate(timeout=timeout)
        return AgentExecution(process.returncode, stdout or "", stderr or "", False)
    except subprocess.TimeoutExpired:
        if os.name == "posix":
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        else:
            process.terminate()
        try:
            stdout, stderr = process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            else:
                process.kill()
            stdout, stderr = process.communicate()
        return AgentExecution(process.returncode, stdout or "", stderr or "", True)


def _combined_output(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stdout or "") + (result.stderr or "")


def _initial_failure_is_expected(result: subprocess.CompletedProcess[str], calculator_source: str) -> bool:
    output = _combined_output(result)
    return result.returncode != 0 and "NotImplementedError" in output and "3 failed" in output and _add_raises_not_implemented(calculator_source)


def _all_calculator_tests_passed(result: subprocess.CompletedProcess[str]) -> bool:
    return result.returncode == 0 and re.search(r"\b3 passed\b", _combined_output(result)) is not None


def _add_raises_not_implemented(source: str) -> bool:
    """Check specifically whether ``add`` still contains a NotImplementedError raise."""
    try:
        module = ast.parse(source)
    except SyntaxError:
        return True
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "add":
            for nested in ast.walk(node):
                if isinstance(nested, ast.Raise) and isinstance(nested.exc, ast.Name) and nested.exc.id == "NotImplementedError":
                    return True
                if (
                    isinstance(nested, ast.Raise)
                    and isinstance(nested.exc, ast.Call)
                    and isinstance(nested.exc.func, ast.Name)
                    and nested.exc.func.id == "NotImplementedError"
                ):
                    return True
            return False
    return True


def _write_run_json(artifacts: Path, run: dict[str, object]) -> None:
    run["artifact_paths"] = {path.name: str(path) for path in artifacts.iterdir()}
    run["artifact_paths"]["run.json"] = str(artifacts / "run.json")
    write_json(artifacts / "run.json", run)


def _finish(
    artifacts: Path,
    run: dict[str, object],
    classification: str,
    reason: str,
    exit_code: int,
    checks: dict[str, bool] | None = None,
) -> int:
    run["finished_at_utc"] = datetime.now(UTC).isoformat()
    run["final_classification"] = classification
    dimension_names = (
        "technical_validity",
        "protocol_safety_status",
        "model_format_status",
        "termination_reason",
        "invalid_response_count",
        "invalid_action_count",
        "executed_action_count",
        "repository_progress",
        "functional_outcome",
        "failure_dimension",
        "command_authorization_status",
        "policy_version",
        "policy_violation_count",
        "prohibited_command_categories",
        "repeated_policy_violation_count",
        "environment_mutation_attempted",
        "environment_mutation_executed",
        "network_access_attempted",
        "network_access_executed",
    )
    dimensions = {
        name: run[name]
        for name in dimension_names
        if name in run
    }
    write_json(
        artifacts / "classification.json",
        {
            "classification": classification,
            "dimensions": dimensions,
            "reason": reason,
            "success_checks": checks or {},
        },
    )
    _write_run_json(artifacts, run)
    print(f"Smoke artifacts: {artifacts}")
    print(f"Classification: {classification}")
    return exit_code


def run_smoke(
    config: SmokeConfig,
    *,
    agent_executor: Callable[[list[str], Path, dict[str, str], float], AgentExecution] | None = None,
) -> int:
    """Execute the isolated run once, preserving every outcome without retries."""
    started = datetime.now(UTC)
    try:
        artifacts, run_id = create_run_directory(config.runs_root)
    except OSError as error:
        print(f"Could not create smoke artifacts under {config.runs_root}: {error}", file=sys.stderr)
        return EXIT_INFRASTRUCTURE_FAILURE
    preflight_result = preflight(config)
    template_before = template_snapshot(config.template) if config.template.is_dir() else {}
    task_contents = config.task_file.read_bytes() if config.task_file.is_file() else b""
    probe = preflight_result.probe
    returned_model = config.model if probe and config.model in probe.models else None
    run: dict[str, object] = {
        "run_id": run_id,
        "started_at_utc": started.isoformat(),
        "task_name": "smoke_test",
        "source_template_path": str(config.template),
        "source_template_sha256": _snapshot_digest(template_before),
        "task_instruction_sha256": _sha256(task_contents) if task_contents else None,
        "temporary_repository_path": None,
        "initial_commit": None,
        "vllm_base_url": config.base_url,
        "requested_model": config.model,
        "model_returned_by_models": returned_model,
        "mini_swe_agent_version": preflight_result.mini_swe.version,
        "python_version": platform.python_version(),
        "operating_system": platform.platform(),
        "agent_configuration": {
            "adapter": "mini-SWE-agent 2.4.6 Python API",
            "agent_class": "project-owned HardenedDefaultAgent",
            "environment_class": "audited LocalEnvironment",
            "model_class": "cmpilot_vllm_text_model.VllmTextModel",
            "tool": "single fenced Bash action",
            "temperature": 0,
            "step_limit": 15,
            "wall_time_limit_seconds": 450,
            "shell_command_timeout_seconds": 60,
            "launches": 0,
        },
        "agent_command": None,
        "agent_exit_code": None,
        "before_test_exit_code": None,
        "after_test_exit_code": None,
        "native_trajectory_path": None,
        "artifact_paths": {},
    }
    write_json(artifacts / "resolved-config.json", _config_artifact(config))
    if task_contents:
        write_text(artifacts / "task-instruction.md", task_contents.decode("utf-8"))
        write_text(artifacts / "task.txt", task_contents.decode("utf-8"))
    write_json(
        artifacts / "model-info.json",
        {
            "endpoint": probe.endpoint if probe else None,
            "models": list(probe.models) if probe else [],
            "requested_model": config.model,
            "diagnostic": preflight_result.diagnostic,
        },
    )
    write_json(
        artifacts / "environment.json",
        {"python": sys.version, "platform": platform.platform(), "cmpilot_python": sys.executable},
    )
    write_text(artifacts / "mini-swe-version.txt", (preflight_result.mini_swe.version or "unavailable") + "\n")
    write_text(artifacts / "agent-version.txt", (preflight_result.mini_swe.version or "unavailable") + "\n")
    write_json(artifacts / "dependency-versions.json", _runtime_dependency_versions(config.mini_python))

    if not preflight_result.ok:
        return _finish(
            artifacts,
            run,
            "infrastructure_failure",
            preflight_result.diagnostic,
            EXIT_INFRASTRUCTURE_FAILURE,
        )

    try:
        working_copy, initial_commit = prepare_working_copy(
            config.template,
            destination=artifacts / "working-copy",
        )
    except (OSError, subprocess.SubprocessError) as error:
        return _finish(
            artifacts,
            run,
            "infrastructure_failure",
            f"repository preparation failed: {error}",
            EXIT_INFRASTRUCTURE_FAILURE,
        )

    run["temporary_repository_path"] = str(working_copy)
    run["initial_commit"] = initial_commit
    write_text(artifacts / "initial-commit.txt", initial_commit + "\n")
    initial_snapshot = _source_snapshot(working_copy)
    write_json(artifacts / "initial-file-hashes.json", _snapshot_artifact(initial_snapshot))
    write_text(artifacts / "initial-tree.txt", "\n".join(str(path) for path in sorted(initial_snapshot)) + "\n")
    before = run_tests(working_copy)
    before_output = _combined_output(before)
    write_text(artifacts / "before-tests.txt", before_output)
    write_text(artifacts / "initial-tests.stdout.txt", before.stdout or "")
    write_text(artifacts / "initial-tests.stderr.txt", before.stderr or "")
    write_text(artifacts / "before-tests-exit-code.txt", str(before.returncode) + "\n")
    run["before_test_exit_code"] = before.returncode
    calculator_path = working_copy / "calculator.py"
    calculator_source = calculator_path.read_text(encoding="utf-8") if calculator_path.is_file() else ""
    before_expected = _initial_failure_is_expected(before, calculator_source)
    untouched_before_agent = not final_patch(working_copy, initial_commit).strip() and not git(working_copy, "status", "--short").stdout.strip()
    if not before_expected or not untouched_before_agent:
        reason = "initial tests did not fail from the unfinished calculator implementation"
        if not untouched_before_agent:
            reason = "repository changed before mini-SWE-agent launch"
        return _finish(
            artifacts,
            run,
            "infrastructure_failure",
            reason,
            EXIT_INFRASTRUCTURE_FAILURE,
            {"before_failed_as_expected": before_expected, "working_copy_unchanged_before_agent": untouched_before_agent},
        )

    adapter = artifacts / "mini_swe_adapter.py"
    trajectory = artifacts / "trajectory.json"
    write_adapter(adapter)
    command_line = command(config.mini_python, adapter)
    run["agent_command"] = command_line
    run["agent_configuration"] = {**run["agent_configuration"], "launches": 1}
    write_text(artifacts / "mini-swe-command.txt", " ".join(command_line) + "\n")
    runner = agent_executor or execute_agent
    agent_started = time.perf_counter()
    try:
        execution = runner(
            command_line,
            working_copy,
            _safe_agent_environment(artifacts, working_copy, config, trajectory, artifacts / "task-instruction.md"),
            config.agent_timeout,
        )
    except Exception as error:  # Preserve an adapter/executor failure as a run artifact.
        execution = AgentExecution(None, "", "", False, f"mini-SWE-agent execution failed: {error}")
    run["agent_wall_time_seconds"] = time.perf_counter() - agent_started
    run["agent_exit_code"] = execution.exit_code
    write_text(artifacts / "agent-stdout.txt", execution.stdout)
    write_text(artifacts / "agent-stderr.txt", execution.stderr)
    write_text(artifacts / "agent.stdout.log", execution.stdout)
    write_text(artifacts / "agent.stderr.log", execution.stderr)

    patch = final_patch(working_copy, initial_commit)
    write_text(artifacts / "final.patch", patch)
    write_text(artifacts / "patch.diff", patch)
    status = git(working_copy, "status", "--short")
    write_text(artifacts / "git-status.txt", status.stdout + status.stderr)
    after = run_tests(working_copy)
    write_text(artifacts / "after-tests.txt", _combined_output(after))
    write_text(artifacts / "final-tests.stdout.txt", after.stdout or "")
    write_text(artifacts / "final-tests.stderr.txt", after.stderr or "")
    write_text(artifacts / "after-tests-exit-code.txt", str(after.returncode) + "\n")
    run["after_test_exit_code"] = after.returncode
    run["native_trajectory_path"] = str(trajectory) if trajectory.is_file() else None
    final_snapshot = _source_snapshot(working_copy)
    write_json(artifacts / "final-file-hashes.json", _snapshot_artifact(final_snapshot))
    trajectory_metrics = _trajectory_metrics(trajectory, {str(path) for path in initial_snapshot})
    run.update(trajectory_metrics)
    run["patch_sha256"] = _sha256(patch.encode("utf-8"))
    run["trajectory_sha256"] = _sha256(trajectory.read_bytes()) if trajectory.is_file() else None

    final_source = calculator_path.read_text(encoding="utf-8") if calculator_path.is_file() else ""
    checks = {
        "before_failed_as_expected": before_expected,
        "agent_launched_once": True,
        "agent_changed_repository": bool(patch.strip()),
        "calculator_add_no_longer_raises_not_implemented": not _add_raises_not_implemented(final_source),
        "all_three_tests_passed": _all_calculator_tests_passed(after),
        "final_patch_present": bool(patch.strip()),
        "native_trajectory_present": trajectory.is_file() and trajectory.stat().st_size > 0,
        "agent_inspected_repository": bool(trajectory_metrics["repository_inspected"]),
        "source_template_unchanged": template_snapshot(config.template) == template_before,
    }
    infrastructure_error = execution.timed_out or execution.launch_error is not None
    agent_harness_error = (
        execution.exit_code != 0 or not checks["native_trajectory_present"]
    ) and not infrastructure_error
    classification = classify(
        infrastructure_error=infrastructure_error,
        agent_harness_error=agent_harness_error,
        before_failed_as_expected=checks["before_failed_as_expected"],
        agent_launched_once=checks["agent_launched_once"],
        changed=checks["agent_changed_repository"],
        calculator_fixed=checks["calculator_add_no_longer_raises_not_implemented"],
        after_tests_passed=checks["all_three_tests_passed"],
        patch_present=checks["final_patch_present"],
        trajectory_present=checks["native_trajectory_present"],
        template_unchanged=checks["source_template_unchanged"],
    )
    if classification == "secure_functional_success" and not checks["agent_inspected_repository"]:
        classification = "functional_failure"
    if execution.timed_out:
        reason = "mini-SWE-agent timed out"
    elif execution.launch_error:
        reason = execution.launch_error
    elif execution.exit_code != 0:
        reason = f"mini-SWE-agent exited with code {execution.exit_code}"
    elif not checks["native_trajectory_present"]:
        reason = "mini-SWE-agent trajectory artifact is missing"
    elif classification == "secure_functional_success":
        reason = "all smoke success checks passed"
    else:
        reason = "agent completed but calculator smoke success checks failed"
    exit_code = EXIT_SUCCESS if classification == "secure_functional_success" else (
        EXIT_INFRASTRUCTURE_FAILURE
        if classification == "infrastructure_failure"
        else EXIT_FUNCTIONAL_FAILURE
    )
    return _finish(artifacts, run, classification, reason, exit_code, checks)
