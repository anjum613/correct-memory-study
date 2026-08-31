"""Frozen model service and shared mini-SWE execution for final runs.

Scientific backends remain responsible for repository preparation, treatment,
task-file policy, and evaluation.  They communicate the one authorization input
needed by the shared agent through an exclusive, hash-bound attempt-local
record.  Model-specific code owns only the vLLM process and endpoint identity;
the mini-SWE loop and terminal classification are shared here.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import subprocess
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .devstral_mini_swe_adapter import (
    DEVSTRAL_SERIALIZATION_NAME,
    PRODUCTION_POLICY_ADAPTER_NAME,
    write_devstral_production_adapter,
)
from .devstral_profile import (
    DEVSTRAL_PRODUCTION_PROFILE,
    EXPECTED_CONSOLIDATED_SHA256,
    EXPECTED_CONSOLIDATED_SIZE,
    MODEL_ID as DEVSTRAL_MODEL_ID,
    MODEL_REVISION as DEVSTRAL_MODEL_REVISION,
    SNAPSHOT_FREEZE_SHA256,
    SNAPSHOT_IDENTITY_SHA256,
)
from .experiment_models import ModelProfile, QWEN32B_PROFILE
from .final_experiment import (
    FinalExperimentError,
    canonical_json_bytes,
    sha256_bytes,
    write_new_canonical_json,
)
from .final_runner import (
    AgentExecutionResult,
    AgentInvocation,
    COMMAND_AUTHORIZATION_REJECTION,
    CONTEXT_EXHAUSTION,
    FinalRunPhaseError,
    MALFORMED_MODEL_RESPONSE,
    MODEL_SERVER_FAILURE,
    OTHER_TERMINAL_STATE,
    PARSER_REJECTION,
    STEP_LIMIT,
    SUCCESS,
    TIMEOUT,
)
from .mini_swe_adapter import MiniSWEInfo, command, mini_swe_info
from .qualification_adapter import write_qualification_adapter
from .qualification_runner import AdapterConfig, _safe_remove_scratch
from .qualification_runtime_paths import (
    RUNTIME_ROOT,
    cleanup_runtime_directory,
    prepare_runtime_directory,
    runtime_directory,
    runtime_path_record,
)
from .qwen32b_final_smoke import validate_runtime_integrity
from .smoke_runner import (
    AgentExecution,
    _safe_agent_environment,
    _source_snapshot,
    _trajectory_metrics,
    execute_agent,
)
from .task_file_policy import TASK_POLICY_SCHEMA, TaskFilePolicy
from .vllm_client import ModelProbe, probe_models, validate_model


SCIENTIFIC_AGENT_BINDING_SCHEMA = "cmpilot-final-scientific-agent-binding-v1"
SCIENTIFIC_AGENT_BINDING_NAME = "scientific-agent-binding.json"
MINI_SWE_RUNTIME_SCHEMA = "cmpilot-final-mini-swe-runtime-v1"
QWEN_SERVICE_SCHEMA = "cmpilot-final-qwen32b-service-v1"
DEVSTRAL_SERVICE_SCHEMA = "cmpilot-final-devstral-service-v1"
QWEN_FROZEN_STEP_LIMIT = 15
QWEN_AGENT_TIMEOUT_SECONDS = 600
POST_LAUNCH_HEALTH_TIMEOUT_SECONDS = 600
# Compatibility alias: the frozen value is unchanged, but it now applies only
# after Popen returns successfully.
QWEN_SERVER_STARTUP_TIMEOUT_SECONDS = POST_LAUNCH_HEALTH_TIMEOUT_SECONDS
QWEN_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS = 30
DEVSTRAL_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS = 300
DEVSTRAL_RUNTIME_ATTESTATION_TIMEOUT_SECONDS = 1800

_BASE_GENERATED_RUNTIME_NAMES = (
    "mini_swe_adapter.py",
    "cmpilot_frozen_adapter_runtime.py",
    "cmpilot_action_protocol.py",
    "cmpilot_command_authorization.py",
    "cmpilot_task_file_policy.py",
    "cmpilot_hardened_agent.py",
    "cmpilot_mini_swe_config.py",
    "cmpilot_vllm_text_model.py",
    "cmpilot_openai_transport.py",
    "cmpilot_context_budget.py",
    "cmpilot_mini_swe_sources.py",
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_SAFE_ATTEMPT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_TRANSPORT_FAILURES = frozenset(
    {
        "TransportConnectionError",
        "TransportHTTPError",
        "TransportTimeoutError",
    }
)
_MALFORMED_RESPONSE_FAILURES = frozenset(
    {"MessageBoundaryError", "TransportResponseError"}
)
_MALFORMED_TERMINATIONS = frozenset(
    {"FORMAT_ERROR_LIMIT", "REPEATED_INVALID_RESPONSE"}
)
_PARSER_TERMINATIONS = frozenset(
    {"INVALID_ACTION_LIMIT", "REPEATED_INVALID_ACTION"}
)


class FinalModelRuntimeError(RuntimeError):
    """A frozen service, binding, or shared-agent invariant is invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _require_sha256(value: str, *, label: str) -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise FinalModelRuntimeError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _require_real_directory(path: Path, *, label: str) -> Path:
    candidate = Path(path)
    if candidate.is_symlink() or not candidate.is_dir():
        raise FinalModelRuntimeError(f"{label} must be an existing real directory: {path}")
    return candidate.resolve(strict=True)


def _parse_task_policy(path: Path, *, expected_sha256: str) -> TaskFilePolicy:
    source = Path(path)
    if source.is_symlink() or not source.is_file():
        raise FinalModelRuntimeError(
            f"task policy source must be an existing real file: {source}"
        )
    resolved = source.resolve(strict=True)
    actual = _sha256_file(resolved)
    if actual != _require_sha256(expected_sha256, label="task policy SHA-256"):
        raise FinalModelRuntimeError(
            f"task policy hash mismatch: expected {expected_sha256}, found {actual}"
        )
    try:
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalModelRuntimeError(f"task policy is not valid UTF-8 JSON: {error}") from error
    if not isinstance(value, dict) or value.get("schema") != TASK_POLICY_SCHEMA:
        raise FinalModelRuntimeError("task policy schema mismatch")
    sequence_fields = (
        "writable_paths",
        "readable_protected_paths",
        "hidden_external_oracle_paths",
        "inaccessible_harness_paths",
    )
    for field in sequence_fields:
        items = value.get(field)
        if not isinstance(items, list) or not all(isinstance(item, str) for item in items):
            raise FinalModelRuntimeError(f"task policy field is invalid: {field}")
    version = value.get("version")
    visible = value.get("agent_visible_policy_text")
    if (
        not isinstance(version, str)
        or not version
        or not isinstance(visible, str)
        or not visible.strip()
    ):
        raise FinalModelRuntimeError("task policy version or visible policy text is invalid")
    try:
        return TaskFilePolicy(
            version=version,
            writable_paths=tuple(value["writable_paths"]),
            readable_protected_paths=tuple(value["readable_protected_paths"]),
            hidden_external_oracle_paths=tuple(value["hidden_external_oracle_paths"]),
            inaccessible_harness_paths=tuple(value["inaccessible_harness_paths"]),
            agent_visible_policy_text=visible,
        )
    except ValueError as error:
        raise FinalModelRuntimeError(f"task policy is invalid: {error}") from error


def _binding_path(attempt_directory: Path) -> Path:
    return Path(attempt_directory) / SCIENTIFIC_AGENT_BINDING_NAME


def write_scientific_agent_binding(
    *,
    attempt_directory: Path,
    run_id: str,
    repository: Path,
    rendered_task: str,
    task_policy_source: Path,
    expected_task_policy_sha256: str,
) -> str:
    """Write the only scientific-to-agent runtime handoff exactly once.

    A future frozen family backend calls this while applying treatment.  The
    caller must supply the manifest-bound task-policy digest; this helper never
    derives authorization policy from repository contents or model behavior.
    """

    attempt = _require_real_directory(attempt_directory, label="attempt directory")
    repo = _require_real_directory(repository, label="agent repository")
    try:
        repo.relative_to(attempt)
    except ValueError as error:
        raise FinalModelRuntimeError(
            "agent repository must be an isolated descendant of the attempt directory"
        ) from error
    if not isinstance(run_id, str) or not run_id:
        raise FinalModelRuntimeError("run_id must be non-empty text")
    if not isinstance(rendered_task, str) or not rendered_task:
        raise FinalModelRuntimeError("rendered_task must be non-empty text")
    policy = Path(task_policy_source)
    _parse_task_policy(policy, expected_sha256=expected_task_policy_sha256)
    resolved_policy = policy.resolve(strict=True)
    record = {
        "repository": str(repo),
        "rendered_task_sha256": sha256_bytes(rendered_task.encode("utf-8")),
        "run_id": run_id,
        "schema": SCIENTIFIC_AGENT_BINDING_SCHEMA,
        "task_policy": {
            "path": str(resolved_policy),
            "sha256": expected_task_policy_sha256,
        },
    }
    try:
        return write_new_canonical_json(_binding_path(attempt), record)
    except FinalExperimentError as error:
        raise FinalModelRuntimeError(str(error)) from error


@dataclass(frozen=True)
class ScientificAgentBinding:
    run_id: str
    repository: Path
    rendered_task_sha256: str
    task_policy_source: Path
    task_policy_sha256: str
    binding_sha256: str


def load_scientific_agent_binding(invocation: AgentInvocation) -> ScientificAgentBinding:
    """Load and revalidate an invocation-bound, canonical scientific handoff."""

    attempt = _require_real_directory(
        invocation.attempt_directory, label="attempt directory"
    )
    path = _binding_path(attempt)
    if path.is_symlink() or not path.is_file():
        raise FinalModelRuntimeError(f"scientific agent binding is missing or unsafe: {path}")
    payload = path.read_bytes()
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalModelRuntimeError(f"scientific agent binding is invalid JSON: {error}") from error
    expected_keys = {
        "repository",
        "rendered_task_sha256",
        "run_id",
        "schema",
        "task_policy",
    }
    if not isinstance(value, dict) or set(value) != expected_keys:
        raise FinalModelRuntimeError("scientific agent binding fields are incomplete or unknown")
    if payload != canonical_json_bytes(value):
        raise FinalModelRuntimeError("scientific agent binding is not canonical JSON")
    if value.get("schema") != SCIENTIFIC_AGENT_BINDING_SCHEMA:
        raise FinalModelRuntimeError("scientific agent binding schema mismatch")
    if value.get("run_id") != invocation.run_id:
        raise FinalModelRuntimeError("scientific agent binding run_id mismatch")
    repository = _require_real_directory(invocation.repository, label="agent repository")
    if value.get("repository") != str(repository):
        raise FinalModelRuntimeError("scientific agent binding repository mismatch")
    try:
        repository.relative_to(attempt)
    except ValueError as error:
        raise FinalModelRuntimeError(
            "agent repository must be an isolated descendant of the attempt directory"
        ) from error
    rendered_sha256 = sha256_bytes(invocation.rendered_task.encode("utf-8"))
    if value.get("rendered_task_sha256") != rendered_sha256:
        raise FinalModelRuntimeError("scientific agent binding rendered-task hash mismatch")
    policy_record = value.get("task_policy")
    if not isinstance(policy_record, dict) or set(policy_record) != {"path", "sha256"}:
        raise FinalModelRuntimeError("scientific agent binding task policy is invalid")
    policy_path_value = policy_record.get("path")
    policy_sha256 = policy_record.get("sha256")
    if not isinstance(policy_path_value, str) or not Path(policy_path_value).is_absolute():
        raise FinalModelRuntimeError("bound task policy path must be absolute")
    _require_sha256(policy_sha256, label="bound task policy SHA-256")
    policy_path = Path(policy_path_value)
    _parse_task_policy(policy_path, expected_sha256=policy_sha256)
    return ScientificAgentBinding(
        run_id=invocation.run_id,
        repository=repository,
        rendered_task_sha256=rendered_sha256,
        task_policy_source=policy_path.resolve(strict=True),
        task_policy_sha256=policy_sha256,
        binding_sha256=hashlib.sha256(payload).hexdigest(),
    )


@dataclass(frozen=True)
class PreparedAgentInvocation:
    invocation: AgentInvocation
    binding: ScientificAgentBinding
    profile: ModelProfile


def classify_mini_swe_execution(
    execution: AgentExecution, metrics: Mapping[str, Any]
) -> tuple[str, bool]:
    """Map preserved frozen-adapter evidence without repairing model output."""

    if execution.timed_out:
        return TIMEOUT, False
    if execution.launch_error is not None:
        return MODEL_SERVER_FAILURE, False
    reason = metrics.get("termination_reason")
    reason = reason if isinstance(reason, str) else ""
    if reason == "Submitted":
        termination = SUCCESS
    elif reason == "CONTEXT_BUDGET_EXHAUSTED":
        termination = CONTEXT_EXHAUSTION
    elif reason == "LimitsExceeded":
        termination = STEP_LIMIT
    elif reason == "TimeExceeded":
        termination = TIMEOUT
    elif reason == "REPEATED_POLICY_VIOLATION":
        termination = COMMAND_AUTHORIZATION_REJECTION
    elif reason in _MALFORMED_TERMINATIONS:
        termination = MALFORMED_MODEL_RESPONSE
    elif reason in _PARSER_TERMINATIONS:
        termination = PARSER_REJECTION
    elif reason in _TRANSPORT_FAILURES:
        termination = MODEL_SERVER_FAILURE
    elif reason in _MALFORMED_RESPONSE_FAILURES:
        termination = MALFORMED_MODEL_RESPONSE
    else:
        termination = OTHER_TERMINAL_STATE
    technical = bool(
        execution.exit_code == 0
        and reason
        and metrics.get("technical_validity") != "FAIL"
        and metrics.get("protocol_safety_status") != "FAIL"
    )
    return termination, technical


def _write_new_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise FinalModelRuntimeError(f"refusing to overwrite existing artifact: {path}") from error
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


class SharedMiniSWERuntime:
    """Model-neutral owner of one frozen mini-SWE process and its classification."""

    def __init__(
        self,
        *,
        project_root: Path,
        agent_executor: Callable[
            [list[str], Path, dict[str, str], float], AgentExecution
        ] = execute_agent,
        agent_inspector: Callable[[str], MiniSWEInfo] = mini_swe_info,
        adapter_writer: Callable[[Path], Mapping[str, str]] = (
            write_qualification_adapter
        ),
        additional_generated_names: Sequence[str] = (),
    ) -> None:
        self.project_root = Path(project_root).resolve(strict=True)
        self.agent_executor = agent_executor
        self.agent_inspector = agent_inspector
        self.adapter_writer = adapter_writer
        self.generated_names = (
            *_BASE_GENERATED_RUNTIME_NAMES,
            *tuple(additional_generated_names),
        )
        if len(set(self.generated_names)) != len(self.generated_names):
            raise FinalModelRuntimeError(
                "mini-SWE generated artifact names must be unique"
            )
        self._attempt: Path | None = None

    def prepare(
        self, invocation: AgentInvocation, *, profile: ModelProfile
    ) -> PreparedAgentInvocation:
        # Binding comes first: tampering must prevent even service startup or
        # dependency-inspection subprocesses.
        binding = load_scientific_agent_binding(invocation)
        if invocation.model_profile_key != profile.profile_id:
            raise FinalModelRuntimeError("invocation model profile key mismatch")
        expected_profile = profile.final_experiment_record(
            step_limit=QWEN_FROZEN_STEP_LIMIT
        )
        if dict(invocation.model_profile) != expected_profile:
            raise FinalModelRuntimeError(
                "invocation model profile differs from the frozen step_limit=15 profile"
            )
        profile.verify_static_inputs(self.project_root)
        agent = self.agent_inspector(str(profile.environment.agent_python))
        if not agent.available or agent.version != profile.scientific_boundary.mini_swe_agent_version:
            raise FinalModelRuntimeError(f"mini-SWE-agent preflight failed: {agent.diagnostic}")
        self._attempt = Path(invocation.attempt_directory).resolve(strict=True)
        return PreparedAgentInvocation(invocation=invocation, binding=binding, profile=profile)

    def execute(
        self, prepared: PreparedAgentInvocation, *, base_url: str
    ) -> AgentExecutionResult:
        invocation = prepared.invocation
        attempt = Path(invocation.attempt_directory).resolve(strict=True)
        # Detect replacement after a potentially long server startup.  The
        # qualification wrapper independently rechecks the policy hash again.
        current = load_scientific_agent_binding(invocation)
        if current != prepared.binding:
            raise FinalModelRuntimeError("scientific agent binding changed after preflight")

        task_file = attempt / "rendered-task.md"
        _write_new_text(task_file, invocation.rendered_task)
        adapter = attempt / "mini_swe_adapter.py"
        conflicts = [
            name for name in self.generated_names if (attempt / name).exists()
        ]
        if conflicts:
            raise FinalModelRuntimeError(
                f"refusing to overwrite mini-SWE runtime artifacts: {conflicts}"
            )
        adapter_record = dict(self.adapter_writer(adapter))
        frozen_adapter_sha256 = adapter_record.get("frozen_adapter_sha256")
        if _SHA256.fullmatch(str(frozen_adapter_sha256)) is None:
            raise FinalModelRuntimeError(
                "mini-SWE adapter writer did not bind the frozen action runtime"
            )
        write_new_canonical_json(attempt / "mini-swe-adapter.json", adapter_record)

        config = AdapterConfig(
            model=prepared.profile.served_model_name,
            tokenizer_path=str(prepared.profile.serialization.tokenizer_path),
            base_url=base_url,
            agent_config_source=prepared.profile.agent_config.verify(self.project_root),
        )
        trajectory = attempt / "trajectory.json"
        environment = _safe_agent_environment(
            attempt,
            prepared.binding.repository,
            config,
            trajectory,
            task_file,
        )
        environment.update(
            {
                "CMPILOT_FROZEN_ADAPTER_SHA256": str(frozen_adapter_sha256),
                "CMPILOT_TASK_POLICY_SHA256": prepared.binding.task_policy_sha256,
                "CMPILOT_TASK_POLICY_SOURCE": str(
                    prepared.binding.task_policy_source
                ),
            }
        )
        command_line = command(str(prepared.profile.environment.agent_python), adapter)
        write_new_canonical_json(attempt / "mini-swe-command.json", command_line)
        write_new_canonical_json(
            attempt / "mini-swe-runtime-input.json",
            {
                "agent_timeout_seconds": QWEN_AGENT_TIMEOUT_SECONDS,
                "binding_sha256": prepared.binding.binding_sha256,
                "generation_seed_applied": False,
                "model_profile_sha256": prepared.profile.identity_sha256(),
                "run_seed": invocation.seed,
                "schema": MINI_SWE_RUNTIME_SCHEMA,
                "seed_note": (
                    "Recorded run identity only; the validated temperature-zero Qwen "
                    "request path has no request seed."
                    if prepared.profile is QWEN32B_PROFILE
                    else (
                        "Recorded run identity only; the qualified temperature-zero "
                        "Devstral request path has no request seed."
                    )
                ),
            },
        )
        started = time.perf_counter()
        execution = self.agent_executor(
            command_line,
            prepared.binding.repository,
            environment,
            QWEN_AGENT_TIMEOUT_SECONDS,
        )
        elapsed = time.perf_counter() - started
        _write_new_text(attempt / "agent.stdout", execution.stdout)
        _write_new_text(attempt / "agent.stderr", execution.stderr)
        write_new_canonical_json(
            attempt / "mini-swe-process.json",
            {
                "elapsed_seconds": elapsed,
                "exit_code": execution.exit_code,
                "launch_error": execution.launch_error,
                "timed_out": execution.timed_out,
            },
        )
        repository_files = {
            str(path) for path in _source_snapshot(prepared.binding.repository)
        }
        metrics = _trajectory_metrics(trajectory, repository_files)
        write_new_canonical_json(attempt / "mini-swe-trajectory-metrics.json", metrics)
        termination_reason, technical_validity = classify_mini_swe_execution(
            execution, metrics
        )
        token_usage = None
        if any(
            metrics.get(name) is not None
            for name in ("usage_prompt", "usage_completion", "usage_total")
        ):
            token_usage = {
                "completion": metrics.get("usage_completion"),
                "prompt": metrics.get("usage_prompt"),
                "total": metrics.get("usage_total"),
            }
        return AgentExecutionResult(
            termination_reason=termination_reason,
            technical_validity=technical_validity,
            action_count=int(metrics.get("executed_action_count", 0)),
            model_request_count=int(metrics.get("model_request_count", 0)),
            elapsed_seconds=elapsed,
            token_usage=token_usage,
            record={
                "binding_sha256": prepared.binding.binding_sha256,
                "mini_swe_process": {
                    "exit_code": execution.exit_code,
                    "launch_error": execution.launch_error,
                    "timed_out": execution.timed_out,
                },
                "raw_termination_reason": metrics.get("termination_reason"),
                "trajectory_metrics": metrics,
            },
        )

    def shutdown(self) -> Mapping[str, Any]:
        if self._attempt is None:
            return {"complete": True, "pass": True, "scope": "agent not started"}
        scratch = self._attempt / "agent-tmp"
        if not scratch.exists() and not scratch.is_symlink():
            return {
                "complete": True,
                "pass": True,
                "path": str(scratch),
                "scope": "already absent",
            }
        try:
            return _safe_remove_scratch(scratch, artifact=self._attempt)
        except BaseException as error:
            return {
                "complete": False,
                "error": f"{type(error).__name__}: {error}",
                "pass": False,
                "path": str(scratch),
            }


@dataclass(frozen=True)
class HealthProbe:
    ok: bool
    status_code: int | None
    diagnostic: str
    body_sha256: str | None


def _probe_health(base_url: str, *, timeout: float = 2.0) -> HealthProbe:
    endpoint = base_url.rstrip("/") + "/health"
    try:
        with urlopen(Request(endpoint, method="GET"), timeout=timeout) as response:  # noqa: S310 - loopback-only endpoint
            body = response.read()
            return HealthProbe(
                ok=response.status == 200,
                status_code=response.status,
                diagnostic=f"HTTP {response.status}",
                body_sha256=hashlib.sha256(body).hexdigest(),
            )
    except HTTPError as error:
        return HealthProbe(False, error.code, f"HTTP {error.code}", None)
    except (URLError, OSError, TimeoutError) as error:
        return HealthProbe(False, None, f"{type(error).__name__}: {error}", None)


def _run_checked(
    argv: Sequence[str], *, environment: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        tuple(argv),
        check=False,
        capture_output=True,
        text=True,
        env=dict(environment),
        timeout=timeout,
    )


def _subprocess_output_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value


def _timeout_evidence(
    error: subprocess.TimeoutExpired | None, *, timeout_seconds: int
) -> dict[str, Any]:
    evidence: dict[str, Any] = {
        "expired": error is not None,
        "seconds": timeout_seconds,
    }
    if error is not None:
        evidence["error_type"] = "TimeoutExpired"
    return evidence


def _attest_qwen_runtime(
    profile: ModelProfile,
    *,
    project_root: Path,
    attempt: Path,
    environment: Mapping[str, str],
) -> Mapping[str, Any]:
    fingerprint_inventory = attempt / "environment-inventory.json"
    fingerprint_record = attempt / "environment-fingerprint.json"
    content_inventory = attempt / "environment-content-inventory.json"
    content_record = attempt / "environment-content-digest.json"
    targets = (
        fingerprint_inventory,
        fingerprint_record,
        content_inventory,
        content_record,
    )
    if any(path.exists() or path.is_symlink() for path in targets):
        raise FinalModelRuntimeError("refusing to overwrite runtime attestation artifacts")
    commands = (
        (
            str(profile.environment.server_python),
            str(project_root / "scripts/environment_fingerprint.py"),
            "capture",
            "--inventory",
            str(fingerprint_inventory),
            "--record",
            str(fingerprint_record),
        ),
        (
            str(profile.environment.server_python),
            str(project_root / "scripts/environment_content_digest.py"),
            "--inventory",
            str(content_inventory),
            "--record",
            str(content_record),
        ),
    )
    results = [
        _run_checked(command_line, environment=environment, timeout=300)
        for command_line in commands
    ]
    write_new_canonical_json(
        attempt / "runtime-attestation-commands.json",
        [list(command_line) for command_line in commands],
    )
    _write_new_text(
        attempt / "runtime-attestation.stdout",
        "".join(result.stdout or "" for result in results),
    )
    _write_new_text(
        attempt / "runtime-attestation.stderr",
        "".join(result.stderr or "" for result in results),
    )
    if any(result.returncode != 0 for result in results):
        raise FinalModelRuntimeError(
            "Qwen runtime attestation command failed: "
            + ", ".join(str(result.returncode) for result in results)
        )
    integrity = validate_runtime_integrity(fingerprint_record, content_record)
    write_new_canonical_json(attempt / "runtime-integrity.json", integrity)
    if integrity.get("pass") is not True:
        raise FinalModelRuntimeError(f"Qwen runtime identity mismatch: {integrity}")
    return integrity


def validate_devstral_environment_verification(
    verification: Mapping[str, Any],
) -> Mapping[str, Any]:
    """Consume the repository verifier without reproducing its readiness logic."""

    checks = verification.get("checks")
    freeze = verification.get("snapshot_freeze")
    weight = verification.get("runtime_weight")
    validation = {
        "all_verifier_checks": (
            isinstance(checks, Mapping)
            and bool(checks)
            and all(value is True for value in checks.values())
        ),
        "environment_ready": (
            verification.get("production_ready") is True
            and verification.get("status") == "READY"
        ),
        "runtime_weight": (
            isinstance(weight, Mapping)
            and weight.get("size") == EXPECTED_CONSOLIDATED_SIZE
            and weight.get("sha256") == EXPECTED_CONSOLIDATED_SHA256
        ),
        "snapshot_freeze": (
            isinstance(freeze, Mapping)
            and freeze.get("valid") is True
            and freeze.get("status") == "READY"
            and freeze.get("freeze_sha256") == SNAPSHOT_FREEZE_SHA256
            and freeze.get("snapshot_identity_sha256")
            == SNAPSHOT_IDENTITY_SHA256
        ),
    }
    return {
        "checks": validation,
        "model_id": DEVSTRAL_MODEL_ID,
        "model_revision": DEVSTRAL_MODEL_REVISION,
        "pass": all(validation.values()),
        "profile_id": DEVSTRAL_PRODUCTION_PROFILE.profile_id,
        "schema": "cmpilot-final-devstral-runtime-integrity-v1",
        "verifier_schema": verification.get("schema"),
    }


def _attest_devstral_runtime(
    profile: ModelProfile,
    *,
    project_root: Path,
    attempt: Path,
    environment: Mapping[str, str],
) -> Mapping[str, Any]:
    """Run the exact repository readiness verifier before starting Devstral."""

    if profile is not DEVSTRAL_PRODUCTION_PROFILE:
        raise FinalModelRuntimeError(
            "Devstral runtime attestation requires the qualified production profile"
        )
    verification_path = attempt / "devstral-environment-verification.json"
    targets = (
        verification_path,
        attempt / "runtime-attestation-commands.json",
        attempt / "runtime-attestation.stdout",
        attempt / "runtime-attestation.stderr",
        attempt / "runtime-integrity.json",
    )
    if any(path.exists() or path.is_symlink() for path in targets):
        raise FinalModelRuntimeError("refusing to overwrite runtime attestation artifacts")
    command_line = (
        str(profile.environment.server_python),
        str(project_root / "scripts/verify_devstral_environment.py"),
        "--output",
        str(verification_path),
    )
    try:
        result = _run_checked(
            command_line,
            environment=environment,
            timeout=DEVSTRAL_RUNTIME_ATTESTATION_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        stdout = _subprocess_output_text(error.stdout)
        stderr = _subprocess_output_text(error.stderr)
        write_new_canonical_json(
            attempt / "runtime-attestation-commands.json", [list(command_line)]
        )
        _write_new_text(attempt / "runtime-attestation.stdout", stdout)
        _write_new_text(attempt / "runtime-attestation.stderr", stderr)
        write_new_canonical_json(
            attempt / "runtime-attestation-timeout.json",
            {
                "command": list(command_line),
                "phase": "runtime_attestation",
                "stderr": stderr,
                "stdout": stdout,
                "timeout": _timeout_evidence(
                    error,
                    timeout_seconds=DEVSTRAL_RUNTIME_ATTESTATION_TIMEOUT_SECONDS,
                ),
            },
        )
        raise FinalModelRuntimeError(
            "Devstral environment verifier exceeded the fixed "
            f"{DEVSTRAL_RUNTIME_ATTESTATION_TIMEOUT_SECONDS}-second outer bound"
        ) from error
    write_new_canonical_json(
        attempt / "runtime-attestation-commands.json", [list(command_line)]
    )
    _write_new_text(attempt / "runtime-attestation.stdout", result.stdout or "")
    _write_new_text(attempt / "runtime-attestation.stderr", result.stderr or "")
    if result.returncode != 0 or not verification_path.is_file():
        raise FinalModelRuntimeError(
            f"Devstral environment verifier did not report READY: {result.returncode}"
        )
    try:
        verification = json.loads(verification_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise FinalModelRuntimeError(
            "Devstral environment verifier output is invalid"
        ) from error
    if not isinstance(verification, Mapping):
        raise FinalModelRuntimeError(
            "Devstral environment verifier output is not an object"
        )
    integrity = validate_devstral_environment_verification(verification)
    write_new_canonical_json(attempt / "runtime-integrity.json", integrity)
    if integrity.get("pass") is not True:
        raise FinalModelRuntimeError(
            f"Devstral runtime identity mismatch: {integrity.get('checks')}"
        )
    return integrity


def _inspect_a100_allocation(
    *,
    server_python: Path,
    tensor_parallel_size: int,
    environment: Mapping[str, str],
    timeout_seconds: int = QWEN_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS,
) -> Mapping[str, Any]:
    torch_command = (
        str(server_python),
        "-c",
        (
            "import json, torch; "
            "print(json.dumps({'count': torch.cuda.device_count(), "
            "'names': [torch.cuda.get_device_name(i) "
            "for i in range(torch.cuda.device_count())]}, sort_keys=True))"
        ),
    )
    nvidia_command = (
        "/usr/bin/nvidia-smi",
        "--query-gpu=index,name,uuid,memory.total,memory.used,memory.free",
        "--format=csv,noheader,nounits",
    )
    torch_timeout: subprocess.TimeoutExpired | None = None
    nvidia_timeout: subprocess.TimeoutExpired | None = None
    try:
        torch_result = _run_checked(
            torch_command,
            environment=environment,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        torch_result = None
        torch_timeout = error
    try:
        nvidia_result = _run_checked(
            nvidia_command,
            environment=environment,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        nvidia_result = None
        nvidia_timeout = error
    try:
        visible = json.loads(torch_result.stdout) if torch_result is not None else {}
    except (json.JSONDecodeError, TypeError):
        visible = {}
    count = visible.get("count") if isinstance(visible, dict) else None
    names = visible.get("names") if isinstance(visible, dict) else None
    nvidia_rows = [
        row.strip()
        for row in (
            nvidia_result.stdout if nvidia_result is not None else ""
        ).splitlines()
        if row.strip()
    ]
    passed = (
        torch_result is not None
        and torch_result.returncode == 0
        and nvidia_timeout is None
        and count == tensor_parallel_size
        and isinstance(names, list)
        and len(names) == tensor_parallel_size
        and all(isinstance(name, str) and "A100" in name for name in names)
    )
    return {
        "cuda_visible_devices": environment.get("CUDA_VISIBLE_DEVICES"),
        "expected_gpu_count": tensor_parallel_size,
        "nvidia_smi": {
            "command": list(nvidia_command),
            "returncode": (
                nvidia_result.returncode if nvidia_result is not None else None
            ),
            "rows": nvidia_rows,
            "stderr": (
                nvidia_result.stderr
                if nvidia_result is not None
                else _subprocess_output_text(
                    nvidia_timeout.stderr if nvidia_timeout is not None else None
                )
            ),
            "stdout": (
                ""
                if nvidia_result is not None
                else _subprocess_output_text(
                    nvidia_timeout.stdout if nvidia_timeout is not None else None
                )
            ),
            "timeout": _timeout_evidence(
                nvidia_timeout, timeout_seconds=timeout_seconds
            ),
        },
        "pass": passed,
        "torch_visible_allocation": {
            "command": list(torch_command),
            "count": count,
            "names": names,
            "returncode": (
                torch_result.returncode if torch_result is not None else None
            ),
            "stderr": (
                torch_result.stderr
                if torch_result is not None
                else _subprocess_output_text(
                    torch_timeout.stderr if torch_timeout is not None else None
                )
            ),
            "stdout": (
                ""
                if torch_result is not None
                else _subprocess_output_text(
                    torch_timeout.stdout if torch_timeout is not None else None
                )
            ),
            "timeout": _timeout_evidence(
                torch_timeout, timeout_seconds=timeout_seconds
            ),
        },
    }


def _validate_attempt_identity(slurm_job_id: str, attempt_id: str) -> None:
    if not re.fullmatch(r"[0-9]{1,20}", slurm_job_id):
        raise FinalModelRuntimeError(
            "Qwen production service requires a numeric Slurm job ID"
        )
    if _SAFE_ATTEMPT_ID.fullmatch(attempt_id) is None or not (
        attempt_id == f"slurm-{slurm_job_id}"
        or attempt_id.startswith(f"slurm-{slurm_job_id}-")
    ):
        raise FinalModelRuntimeError(
            "attempt identity must derive from the actual Slurm job ID"
        )


def qwen_service_port(*, slurm_job_id: str, attempt_id: str) -> int:
    """Return a deterministic bounded port keyed by the immutable attempt."""

    _validate_attempt_identity(slurm_job_id, attempt_id)
    digest = hashlib.sha256(
        f"{slurm_job_id}\0{attempt_id}".encode("ascii")
    ).digest()
    return 40000 + (int.from_bytes(digest[:8], "big") % 20000)


def _runtime_owner_id(*, slurm_job_id: str, attempt_id: str) -> str:
    """Return a numeric, <=20-digit owner token for the short IPC path."""

    _validate_attempt_identity(slurm_job_id, attempt_id)
    digest = hashlib.sha256(
        f"runtime\0{slurm_job_id}\0{attempt_id}".encode("ascii")
    ).digest()
    return str(int.from_bytes(digest[:8], "big"))


def _port_is_available(port: int) -> bool:
    try:
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False


class _ProfileModelService:
    """Attempt-owned lifecycle shared by exact qualified vLLM profiles."""

    qualified_profile: ModelProfile
    model_label: str
    runtime_attestor_default: Callable[..., Mapping[str, Any]]
    service_schema: str
    shutdown_schema: str
    gpu_probe_timeout_seconds = QWEN_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS

    def __init__(
        self,
        *,
        profile: ModelProfile,
        project_root: Path,
        runtime_root: Path = RUNTIME_ROOT,
        process_factory: Callable[..., Any] = subprocess.Popen,
        health_probe: Callable[[str], HealthProbe] = _probe_health,
        models_probe: Callable[[str], ModelProbe] = probe_models,
        runtime_attestor: Callable[..., Mapping[str, Any]] | None = None,
        gpu_inspector: Callable[..., Mapping[str, Any]] = _inspect_a100_allocation,
        port_available: Callable[[int], bool] = _port_is_available,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        port: int | None = None,
    ) -> None:
        if profile is not self.qualified_profile:
            raise FinalModelRuntimeError(
                f"{self.model_label} service requires its qualified production profile"
            )
        self.profile = profile
        self.project_root = Path(project_root).resolve(strict=True)
        self.runtime_root = Path(runtime_root)
        self.process_factory = process_factory
        self.health_probe = health_probe
        self.models_probe = models_probe
        self.runtime_attestor = runtime_attestor or self.runtime_attestor_default
        self.gpu_inspector = gpu_inspector
        self.port_available = port_available
        self.monotonic = monotonic
        self.sleeper = sleeper
        self.requested_port = port
        self.process: Any | None = None
        self.attempt: Path | None = None
        self.job_id: str | None = None
        self.runtime_path: Path | None = None
        self.runtime_prepared = False
        self._shutdown_record: Mapping[str, Any] | None = None

    def _server_environment(self, runtime_path: Path) -> dict[str, str]:
        environment = dict(os.environ)
        environment.update(dict(self.profile.environment.offline_environment))
        environment.update(
            {
                "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
                "TOKENIZERS_PARALLELISM": "false",
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "NO_PROXY": "127.0.0.1,localhost",
                "no_proxy": "127.0.0.1,localhost",
                "TMPDIR": str(runtime_path),
                "TEMP": str(runtime_path),
                "TMP": str(runtime_path),
                "VLLM_RPC_BASE_PATH": str(runtime_path),
            }
        )
        environment.pop("HF_TOKEN", None)
        environment.pop("HUGGING_FACE_HUB_TOKEN", None)
        return environment

    def start(
        self, *, attempt_directory: Path, run_id: str, slurm_job_id: str
    ) -> str:
        if self.process is not None or self.attempt is not None:
            raise FinalModelRuntimeError(
                f"{self.model_label} service instances are single-use"
            )
        attempt = _require_real_directory(attempt_directory, label="attempt directory")
        attempt_id = attempt.name
        _validate_attempt_identity(slurm_job_id, attempt_id)
        self.attempt = attempt
        self.job_id = slurm_job_id
        runtime_owner_id = _runtime_owner_id(
            slurm_job_id=slurm_job_id, attempt_id=attempt_id
        )
        self.runtime_path = runtime_directory(
            runtime_owner_id, runtime_root=self.runtime_root
        )
        port = self.requested_port or qwen_service_port(
            slurm_job_id=slurm_job_id, attempt_id=attempt_id
        )
        started = self.monotonic()
        phase_durations: dict[str, float | None] = {
            "gpu_inspection": None,
            "runtime_attestation": None,
            "process_launch": None,
            "post_launch_health_wait": None,
        }
        startup_record: dict[str, Any] = {
            "base_url": f"http://127.0.0.1:{port}/v1",
            "pass": False,
            "port": port,
            "run_id": run_id,
            "schema": self.service_schema,
            "attempt_id": attempt_id,
            "runtime_owner_id": runtime_owner_id,
            "slurm_job_id": slurm_job_id,
            "health_probe_count": 0,
            "phase_durations_seconds": phase_durations,
            "post_launch_health_deadline_origin": "successful_popen_return",
            "timeout_budgets_seconds": {
                "gpu_allocation_probe": self.gpu_probe_timeout_seconds,
                "post_launch_health": POST_LAUNCH_HEALTH_TIMEOUT_SECONDS,
            },
        }
        try:
            # This is an early diagnostic only.  It cannot eliminate the bind
            # TOCTOU; vLLM's own preserved bind/startup result is authoritative.
            if not self.port_available(port):
                raise FinalModelRuntimeError(f"selected loopback port is unavailable: {port}")
            path_record = runtime_path_record(
                job_id=runtime_owner_id,
                task_id=run_id,
                persistent_artifact_root=attempt.parent,
                runtime_root=self.runtime_root,
            )
            path_record.update(
                {
                    "attempt_id": attempt_id,
                    "runtime_owner_id": runtime_owner_id,
                    "slurm_job_id": slurm_job_id,
                }
            )
            if path_record.get("pass") is not True:
                raise FinalModelRuntimeError("vLLM runtime IPC path budget failed")
            write_new_canonical_json(attempt / "runtime-ipc-path-budget.json", path_record)
            preparation = prepare_runtime_directory(
                self.runtime_path,
                job_id=runtime_owner_id,
                runtime_root=self.runtime_root,
            )
            self.runtime_prepared = True
            write_new_canonical_json(
                attempt / "runtime-scratch-preparation.json", preparation
            )
            environment = self._server_environment(self.runtime_path)
            phase_started = self.monotonic()
            try:
                gpu = self.gpu_inspector(
                    server_python=self.profile.environment.server_python,
                    tensor_parallel_size=self.profile.server.tensor_parallel_size,
                    environment=environment,
                    timeout_seconds=self.gpu_probe_timeout_seconds,
                )
            finally:
                phase_durations["gpu_inspection"] = (
                    self.monotonic() - phase_started
                )
            write_new_canonical_json(attempt / "gpu-allocation.json", gpu)
            if gpu.get("pass") is not True:
                raise FinalModelRuntimeError("allocated GPUs do not match 2 x A100")
            phase_started = self.monotonic()
            try:
                integrity = self.runtime_attestor(
                    self.profile,
                    project_root=self.project_root,
                    attempt=attempt,
                    environment=environment,
                )
            finally:
                phase_durations["runtime_attestation"] = (
                    self.monotonic() - phase_started
                )
            if integrity.get("pass") is not True:
                raise FinalModelRuntimeError(
                    f"{self.model_label} runtime attestation failed"
                )
            argv = self.profile.server_argv(port=port)
            write_new_canonical_json(attempt / "server-command.json", list(argv))
            stdout_handle = (attempt / "server.stdout").open("xb")
            stderr_handle = (attempt / "server.stderr").open("xb")
            phase_started = self.monotonic()
            try:
                self.process = self.process_factory(
                    argv,
                    cwd=self.project_root,
                    env=environment,
                    stdout=stdout_handle,
                    stderr=stderr_handle,
                    start_new_session=True,
                )
                post_launch_health_started = self.monotonic()
                phase_durations["process_launch"] = (
                    post_launch_health_started - phase_started
                )
            finally:
                stdout_handle.close()
                stderr_handle.close()
                if phase_durations["process_launch"] is None:
                    phase_durations["process_launch"] = (
                        self.monotonic() - phase_started
                    )
            _write_new_text(attempt / "server.pid", f"{self.process.pid}\n")
            deadline = (
                post_launch_health_started + POST_LAUNCH_HEALTH_TIMEOUT_SECONDS
            )
            health = HealthProbe(False, None, "not yet probed", None)
            health_probe_count = 0
            base = f"http://127.0.0.1:{port}"
            try:
                while True:
                    if self.process.poll() is not None:
                        raise FinalModelRuntimeError(
                            f"{self.model_label} vLLM server exited during startup: "
                            f"{self.process.poll()}"
                        )
                    health = self.health_probe(base)
                    health_probe_count += 1
                    if health.ok:
                        break
                    remaining = deadline - self.monotonic()
                    if remaining <= 0:
                        raise FinalModelRuntimeError(
                            f"{self.model_label} vLLM health timeout: "
                            f"{health.diagnostic}"
                        )
                    self.sleeper(min(1.0, remaining))
            finally:
                phase_durations["post_launch_health_wait"] = (
                    self.monotonic() - post_launch_health_started
                )
                startup_record["health_probe_count"] = health_probe_count
            write_new_canonical_json(
                attempt / "server-health.json",
                {
                    "body_sha256": health.body_sha256,
                    "diagnostic": health.diagnostic,
                    "pass": health.ok,
                    "status_code": health.status_code,
                },
            )
            model_probe = validate_model(
                self.models_probe(f"{base}/v1"), self.profile.served_model_name
            )
            write_new_canonical_json(
                attempt / "server-models.json",
                {
                    "diagnostic": model_probe.diagnostic,
                    "endpoint": model_probe.endpoint,
                    "models": list(model_probe.models),
                    "pass": model_probe.ok,
                    "status_code": model_probe.status_code,
                },
            )
            if not model_probe.ok:
                raise FinalModelRuntimeError(
                    f"{self.model_label} served-model identity failed: "
                    f"{model_probe.diagnostic}"
                )
            startup_record.update(
                {
                    "pass": True,
                    "server_argv": list(argv),
                    "served_model_name": self.profile.served_model_name,
                }
            )
            return f"{base}/v1"
        except BaseException as error:
            startup_record["error"] = f"{type(error).__name__}: {error}"
            raise FinalRunPhaseError(MODEL_SERVER_FAILURE, str(error)) from error
        finally:
            startup_record["startup_seconds"] = self.monotonic() - started
            try:
                write_new_canonical_json(attempt / "server-startup.json", startup_record)
            except FinalExperimentError:
                pass

    def shutdown(self) -> Mapping[str, Any]:
        if self._shutdown_record is not None:
            return self._shutdown_record
        process_record: dict[str, Any] = {
            "already_exited": self.process is None,
            "force_kill_used": False,
            "pid": None if self.process is None else self.process.pid,
        }
        errors: list[str] = []
        if self.process is not None:
            returncode = self.process.poll()
            process_record["already_exited"] = returncode is not None
            if returncode is None:
                try:
                    os.killpg(self.process.pid, signal.SIGTERM)
                    try:
                        returncode = self.process.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        process_record["force_kill_used"] = True
                        os.killpg(self.process.pid, signal.SIGKILL)
                        returncode = self.process.wait(timeout=10)
                except ProcessLookupError:
                    returncode = self.process.poll()
                except BaseException as error:
                    errors.append(f"server stop: {type(error).__name__}: {error}")
            process_record["returncode"] = returncode
        process_stopped = self.process is None or self.process.poll() is not None
        if not process_stopped:
            errors.append("server stop: process group is still running")
        scratch_record: Mapping[str, Any] = {
            "already_absent": True,
            "pass": True,
            "runtime_directory": None,
        }
        if (
            process_stopped
            and self.runtime_prepared
            and self.runtime_path is not None
            and self.job_id is not None
        ):
            try:
                scratch_record = cleanup_runtime_directory(
                    self.runtime_path,
                    job_id=_runtime_owner_id(
                        slurm_job_id=self.job_id, attempt_id=self.attempt.name
                    ),
                    runtime_root=self.runtime_root,
                )
            except BaseException as error:
                errors.append(f"runtime cleanup: {type(error).__name__}: {error}")
                scratch_record = {
                    "error": errors[-1],
                    "pass": False,
                    "runtime_directory": str(self.runtime_path),
                }
        elif self.runtime_prepared and not process_stopped:
            scratch_record = {
                "error": "runtime retained because the server process group is still running",
                "pass": False,
                "runtime_directory": str(self.runtime_path),
            }
        record = {
            "complete": not errors and scratch_record.get("pass") is True,
            "errors": errors,
            "pass": not errors and scratch_record.get("pass") is True,
            "process": process_record,
            "runtime_scratch": dict(scratch_record),
            "schema": self.shutdown_schema,
        }
        self._shutdown_record = record
        if self.attempt is not None:
            try:
                write_new_canonical_json(self.attempt / "server-shutdown.json", record)
            except FinalExperimentError:
                pass
        return record


class Qwen32BModelService(_ProfileModelService):
    """Attempt-owned lifecycle for the exact qualified Qwen vLLM server."""

    qualified_profile = QWEN32B_PROFILE
    model_label = "Qwen"
    runtime_attestor_default = staticmethod(_attest_qwen_runtime)
    service_schema = QWEN_SERVICE_SCHEMA
    shutdown_schema = "cmpilot-final-qwen32b-shutdown-v1"


class DevstralModelService(_ProfileModelService):
    """Attempt-owned lifecycle for the exact qualified Devstral vLLM server."""

    qualified_profile = DEVSTRAL_PRODUCTION_PROFILE
    model_label = "Devstral"
    runtime_attestor_default = staticmethod(_attest_devstral_runtime)
    service_schema = DEVSTRAL_SERVICE_SCHEMA
    shutdown_schema = "cmpilot-final-devstral-shutdown-v1"
    gpu_probe_timeout_seconds = DEVSTRAL_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS


class _ProfileFinalModelExecutor:
    """Compose one model service with the shared scientific agent runtime."""

    def __init__(
        self,
        *,
        profile: ModelProfile,
        project_root: Path,
        shared_runtime: SharedMiniSWERuntime,
        service_factory: Callable[[], _ProfileModelService],
    ) -> None:
        self.profile = profile
        self.project_root = Path(project_root).resolve(strict=True)
        self.shared_runtime = shared_runtime
        self.service_factory = service_factory
        self.service: _ProfileModelService | None = None

    def execute_agent(self, invocation: AgentInvocation) -> AgentExecutionResult:
        prepared = self.shared_runtime.prepare(invocation, profile=self.profile)
        # Service creation/startup happens only after the scientific binding and
        # frozen profile have passed every CPU-side check.
        self.service = self.service_factory()
        job_id = os.environ.get("SLURM_JOB_ID", "")
        base_url = self.service.start(
            attempt_directory=invocation.attempt_directory,
            run_id=invocation.run_id,
            slurm_job_id=job_id,
        )
        return self.shared_runtime.execute(prepared, base_url=base_url)

    def shutdown(self) -> Mapping[str, Any]:
        agent = self.shared_runtime.shutdown()
        server = (
            self.service.shutdown()
            if self.service is not None
            else {"complete": True, "pass": True, "scope": "service not created"}
        )
        return {
            "agent_runtime": dict(agent),
            "complete": agent.get("complete") is True and server.get("complete") is True,
            "pass": agent.get("pass") is True and server.get("pass") is True,
            "server": dict(server),
        }


class Qwen32BFinalModelExecutor(_ProfileFinalModelExecutor):
    """Qualified Qwen service using the shared final scientific runtime."""

    def __init__(
        self,
        *,
        project_root: Path,
        shared_runtime: SharedMiniSWERuntime | None = None,
        service_factory: Callable[[], Qwen32BModelService] | None = None,
    ) -> None:
        root = Path(project_root).resolve(strict=True)
        super().__init__(
            profile=QWEN32B_PROFILE,
            project_root=root,
            shared_runtime=shared_runtime
            or SharedMiniSWERuntime(project_root=root),
            service_factory=service_factory
            or (
                lambda: Qwen32BModelService(
                    profile=QWEN32B_PROFILE, project_root=root
                )
            ),
        )


class DevstralFinalModelExecutor(_ProfileFinalModelExecutor):
    """Qualified Devstral service using the shared final scientific runtime."""

    def __init__(
        self,
        *,
        project_root: Path,
        shared_runtime: SharedMiniSWERuntime | None = None,
        service_factory: Callable[[], DevstralModelService] | None = None,
    ) -> None:
        root = Path(project_root).resolve(strict=True)
        super().__init__(
            profile=DEVSTRAL_PRODUCTION_PROFILE,
            project_root=root,
            shared_runtime=shared_runtime
            or SharedMiniSWERuntime(
                project_root=root,
                adapter_writer=write_devstral_production_adapter,
                additional_generated_names=(
                    DEVSTRAL_SERIALIZATION_NAME,
                    PRODUCTION_POLICY_ADAPTER_NAME,
                ),
            ),
            service_factory=service_factory
            or (
                lambda: DevstralModelService(
                    profile=DEVSTRAL_PRODUCTION_PROFILE, project_root=root
                )
            ),
        )


def build_qwen32b_model_executor(
    context: Mapping[str, Any],
) -> Qwen32BFinalModelExecutor:
    """Registry builder that rejects anything but the exact frozen Qwen record."""

    record = context.get("model_profile")
    expected = QWEN32B_PROFILE.final_experiment_record(
        step_limit=QWEN_FROZEN_STEP_LIMIT
    )
    if not isinstance(record, Mapping) or dict(record) != expected:
        raise FinalModelRuntimeError(
            "Qwen final executor requires the exact frozen step_limit=15 model profile"
        )
    key = context.get("model_profile_key")
    if key != QWEN32B_PROFILE.profile_id:
        raise FinalModelRuntimeError("Qwen final executor profile key mismatch")
    return Qwen32BFinalModelExecutor(project_root=Path(__file__).parents[2])


def build_devstral_model_executor(
    context: Mapping[str, Any],
) -> DevstralFinalModelExecutor:
    """Registry builder requiring the exact qualified Devstral profile record."""

    record = context.get("model_profile")
    expected = DEVSTRAL_PRODUCTION_PROFILE.final_experiment_record(
        step_limit=QWEN_FROZEN_STEP_LIMIT
    )
    if not isinstance(record, Mapping) or dict(record) != expected:
        raise FinalModelRuntimeError(
            "Devstral final executor requires the exact frozen step_limit=15 model profile"
        )
    key = context.get("model_profile_key")
    if key != DEVSTRAL_PRODUCTION_PROFILE.profile_id:
        raise FinalModelRuntimeError("Devstral final executor profile key mismatch")
    return DevstralFinalModelExecutor(project_root=Path(__file__).parents[2])


__all__ = [
    "DEVSTRAL_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS",
    "DEVSTRAL_RUNTIME_ATTESTATION_TIMEOUT_SECONDS",
    "FinalModelRuntimeError",
    "HealthProbe",
    "DEVSTRAL_SERVICE_SCHEMA",
    "DevstralFinalModelExecutor",
    "DevstralModelService",
    "MINI_SWE_RUNTIME_SCHEMA",
    "POST_LAUNCH_HEALTH_TIMEOUT_SECONDS",
    "QWEN_AGENT_TIMEOUT_SECONDS",
    "QWEN_FROZEN_STEP_LIMIT",
    "QWEN_GPU_ALLOCATION_PROBE_TIMEOUT_SECONDS",
    "QWEN_SERVICE_SCHEMA",
    "Qwen32BFinalModelExecutor",
    "Qwen32BModelService",
    "SCIENTIFIC_AGENT_BINDING_NAME",
    "SCIENTIFIC_AGENT_BINDING_SCHEMA",
    "ScientificAgentBinding",
    "SharedMiniSWERuntime",
    "build_devstral_model_executor",
    "build_qwen32b_model_executor",
    "classify_mini_swe_execution",
    "load_scientific_agent_binding",
    "qwen_service_port",
    "validate_devstral_environment_verification",
    "write_scientific_agent_binding",
]
