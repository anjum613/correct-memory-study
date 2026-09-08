from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from cmpilot import final_model_runtime
from cmpilot.devstral_profile import (
    DEVSTRAL_PRODUCTION_PROFILE,
    TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION,
)
from cmpilot.devstral_mini_swe_adapter import write_devstral_production_adapter
from cmpilot.experiment_models import QWEN32B_PROFILE
from cmpilot.final_model_runtime import (
    DevstralFinalModelExecutor,
    DevstralModelService,
    FinalModelRuntimeError,
    HealthProbe,
    QWEN_FROZEN_STEP_LIMIT,
    Qwen32BFinalModelExecutor,
    Qwen32BModelService,
    SharedMiniSWERuntime,
    build_devstral_model_executor,
    build_qwen32b_model_executor,
    classify_mini_swe_execution,
    load_scientific_agent_binding,
    qwen_service_port,
    validate_devstral_environment_verification,
    write_scientific_agent_binding,
)
from cmpilot.final_runner import (
    AgentInvocation,
    COMMAND_AUTHORIZATION_REJECTION,
    CONTEXT_EXHAUSTION,
    MALFORMED_MODEL_RESPONSE,
    MODEL_SERVER_FAILURE,
    OTHER_TERMINAL_STATE,
    PARSER_REJECTION,
    STEP_LIMIT,
    SUCCESS,
    TIMEOUT,
)
from cmpilot.final_runtime_backends import MODEL_EXECUTORS, SCIENTIFIC_BACKENDS
from cmpilot.mini_swe_adapter import MiniSWEInfo
from cmpilot.smoke_runner import AgentExecution
from cmpilot.task_file_policy import calculator_task_policy
from cmpilot.vllm_client import ModelProbe


ROOT = Path(__file__).parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _invocation(tmp_path: Path, *, step_limit: int = 15) -> tuple[AgentInvocation, Path]:
    attempt = tmp_path / "run-qwen" / "attempts" / "slurm-91-0"
    repository = attempt / "working-copy"
    repository.mkdir(parents=True)
    (repository / "task.py").write_text("value = 0\n", encoding="utf-8")
    policy = tmp_path / "task-policy.json"
    policy.write_text(
        json.dumps(calculator_task_policy().as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    invocation = AgentInvocation(
        run_id="run-qwen",
        model_profile_key=QWEN32B_PROFILE.profile_id,
        model_profile=QWEN32B_PROFILE.final_experiment_record(
            step_limit=step_limit
        ),
        seed=17,
        repository=repository,
        rendered_task="Synthetic runtime-binding test; no research family.",
        attempt_directory=attempt,
    )
    return invocation, policy


def _bind(invocation: AgentInvocation, policy: Path) -> str:
    return write_scientific_agent_binding(
        attempt_directory=invocation.attempt_directory,
        run_id=invocation.run_id,
        repository=invocation.repository,
        rendered_task=invocation.rendered_task,
        task_policy_source=policy,
        expected_task_policy_sha256=_sha256(policy),
    )


def _available_agent(_: str) -> MiniSWEInfo:
    return MiniSWEInfo(True, "2.4.6", "synthetic unit-test inspector")


def test_scientific_binding_is_exclusive_canonical_and_invocation_bound(
    tmp_path: Path,
) -> None:
    invocation, policy = _invocation(tmp_path)
    digest = _bind(invocation, policy)

    loaded = load_scientific_agent_binding(invocation)

    assert loaded.binding_sha256 == digest
    assert loaded.repository == invocation.repository.resolve()
    assert loaded.task_policy_sha256 == _sha256(policy)
    with pytest.raises(FinalModelRuntimeError, match="overwrite"):
        _bind(invocation, policy)


def test_tampered_policy_prevents_service_and_agent_launch(tmp_path: Path) -> None:
    invocation, policy = _invocation(tmp_path)
    _bind(invocation, policy)
    policy.write_text("{}\n", encoding="utf-8")
    launches: list[str] = []

    executor = Qwen32BFinalModelExecutor(
        project_root=ROOT,
        shared_runtime=SharedMiniSWERuntime(
            project_root=ROOT,
            agent_executor=lambda *_args, **_kwargs: launches.append("agent"),  # type: ignore[arg-type]
            agent_inspector=lambda _python: (_ for _ in ()).throw(
                AssertionError("inspector must not run before binding validation")
            ),
        ),
        service_factory=lambda: launches.append("service"),  # type: ignore[arg-type]
    )

    with pytest.raises(FinalModelRuntimeError, match="task policy hash mismatch"):
        executor.execute_agent(invocation)
    assert launches == []


def test_shared_runtime_rejects_nonfrozen_step_limit_before_service(
    tmp_path: Path,
) -> None:
    invocation, policy = _invocation(tmp_path, step_limit=16)
    _bind(invocation, policy)
    launches: list[str] = []
    executor = Qwen32BFinalModelExecutor(
        project_root=ROOT,
        shared_runtime=SharedMiniSWERuntime(
            project_root=ROOT, agent_inspector=_available_agent
        ),
        service_factory=lambda: launches.append("service"),  # type: ignore[arg-type]
    )

    with pytest.raises(FinalModelRuntimeError, match="step_limit=15"):
        executor.execute_agent(invocation)
    assert launches == []


def test_shared_mini_swe_runtime_reuses_frozen_wrapper_and_classifies(
    tmp_path: Path,
) -> None:
    invocation, policy = _invocation(tmp_path)
    binding_sha256 = _bind(invocation, policy)

    def fake_agent(
        command_line: list[str],
        cwd: Path,
        environment: dict[str, str],
        timeout: float,
    ) -> AgentExecution:
        assert command_line[0] == str(QWEN32B_PROFILE.environment.agent_python)
        assert cwd == invocation.repository.resolve()
        assert timeout == 600
        assert environment["CMPILOT_TASK_POLICY_SHA256"] == _sha256(policy)
        trajectory = {
            "info": {
                "exit_status": "Submitted",
                "model_stats": {"api_calls": 3},
                "protocol": {
                    "executed_action_count": 2,
                    "protocol_safety_status": "PASS",
                    "technical_validity": "PASS",
                },
            },
            "messages": [
                {
                    "extra": {
                        "actions": [{"command": "sed -n '1p' task.py"}],
                        "response": {
                            "usage": {
                                "completion_tokens": 7,
                                "prompt_tokens": 11,
                                "total_tokens": 18,
                            }
                        },
                    }
                }
            ],
        }
        Path(environment["CMPILOT_TRAJECTORY"]).write_text(
            json.dumps(trajectory), encoding="utf-8"
        )
        return AgentExecution(0, "agent stdout\n", "", False)

    runtime = SharedMiniSWERuntime(
        project_root=ROOT,
        agent_executor=fake_agent,
        agent_inspector=_available_agent,
    )
    prepared = runtime.prepare(invocation, profile=QWEN32B_PROFILE)
    result = runtime.execute(prepared, base_url="http://127.0.0.1:47983/v1")

    assert result.termination_reason == SUCCESS
    assert result.technical_validity is True
    assert result.action_count == 2
    assert result.model_request_count == 3
    assert result.token_usage == {"completion": 7, "prompt": 11, "total": 18}
    runtime_input = json.loads(
        (invocation.attempt_directory / "mini-swe-runtime-input.json").read_text()
    )
    assert runtime_input["binding_sha256"] == binding_sha256
    assert runtime_input["generation_seed_applied"] is False
    assert (invocation.attempt_directory / "cmpilot_frozen_adapter_runtime.py").is_file()
    assert runtime.shutdown()["pass"] is True


@pytest.mark.parametrize(
    ("raw_reason", "execution", "expected", "technical"),
    [
        ("Submitted", AgentExecution(0, "", "", False), SUCCESS, True),
        (
            "CONTEXT_BUDGET_EXHAUSTED",
            AgentExecution(0, "", "", False),
            CONTEXT_EXHAUSTION,
            True,
        ),
        ("LimitsExceeded", AgentExecution(0, "", "", False), STEP_LIMIT, True),
        ("TimeExceeded", AgentExecution(0, "", "", False), TIMEOUT, True),
        (
            "REPEATED_POLICY_VIOLATION",
            AgentExecution(0, "", "", False),
            COMMAND_AUTHORIZATION_REJECTION,
            True,
        ),
        (
            "FORMAT_ERROR_LIMIT",
            AgentExecution(0, "", "", False),
            MALFORMED_MODEL_RESPONSE,
            True,
        ),
        (
            "REPEATED_INVALID_ACTION",
            AgentExecution(0, "", "", False),
            PARSER_REJECTION,
            True,
        ),
        (
            "TransportConnectionError",
            AgentExecution(1, "", "", False),
            MODEL_SERVER_FAILURE,
            False,
        ),
        (
            "STAGNATION_LIMIT",
            AgentExecution(0, "", "", False),
            OTHER_TERMINAL_STATE,
            True,
        ),
        ("", AgentExecution(None, "", "", True), TIMEOUT, False),
    ],
)
def test_shared_terminal_mapping(
    raw_reason: str,
    execution: AgentExecution,
    expected: str,
    technical: bool,
) -> None:
    assert classify_mini_swe_execution(
        execution,
        {
            "protocol_safety_status": "PASS",
            "technical_validity": "PASS",
            "termination_reason": raw_reason,
        },
    ) == (expected, technical)


class _FakeProcess:
    pid = 99191

    def __init__(self) -> None:
        self.returncode: int | None = None

    def poll(self) -> int | None:
        return self.returncode

    def wait(self, timeout: int) -> int:
        if self.returncode is None:
            raise subprocess.TimeoutExpired("fake", timeout)
        return self.returncode


class _ManualClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def test_qwen_service_uses_exact_profile_argv_and_attempt_local_evidence(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "run-qwen" / "attempts" / "slurm-91-0"
    attempt.mkdir(parents=True)
    observed: dict[str, object] = {}
    process = _FakeProcess()
    runtime_root = Path(tempfile.mkdtemp(prefix="cmfrt-"))

    def fake_process(argv, **kwargs):
        observed["argv"] = tuple(argv)
        observed["environment"] = kwargs["env"]
        return process

    service = Qwen32BModelService(
        profile=QWEN32B_PROFILE,
        project_root=ROOT,
        runtime_root=runtime_root,
        process_factory=fake_process,
        health_probe=lambda _base: HealthProbe(True, 200, "HTTP 200", "a" * 64),
        models_probe=lambda _base: ModelProbe(
            "http://127.0.0.1:47983/v1/models",
            True,
            "endpoint responded",
            200,
            (QWEN32B_PROFILE.served_model_name,),
        ),
        runtime_attestor=lambda *_args, **_kwargs: {"pass": True},
        gpu_inspector=lambda **kwargs: (
            observed.update(gpu_arguments=kwargs)
            or {
                "pass": True,
                "rows": ["0, NVIDIA A100", "1, NVIDIA A100"],
            }
        ),
        port_available=lambda _port: True,
        monotonic=lambda: 1.0,
        sleeper=lambda _seconds: None,
        port=47983,
    )

    base_url = service.start(
        attempt_directory=attempt, run_id="run-qwen", slurm_job_id="91"
    )

    assert base_url == "http://127.0.0.1:47983/v1"
    assert observed["argv"] == QWEN32B_PROFILE.server_argv(port=47983)
    environment = observed["environment"]
    assert isinstance(environment, dict)
    gpu_arguments = observed["gpu_arguments"]
    assert isinstance(gpu_arguments, dict)
    assert "timeout_seconds" not in gpu_arguments
    runtime_path = Path(environment["VLLM_RPC_BASE_PATH"])
    assert runtime_path.parent == runtime_root
    assert runtime_path.name.startswith("cmq-")
    assert "HF_TOKEN" not in environment
    startup = json.loads((attempt / "server-startup.json").read_text())
    assert startup["pass"] is True
    assert startup["timeout_budgets_seconds"]["gpu_allocation_probe"] == 30
    assert json.loads((attempt / "server-models.json").read_text())["models"] == [
        QWEN32B_PROFILE.served_model_name
    ]

    process.returncode = 0
    shutdown = service.shutdown()
    assert shutdown["pass"] is True
    assert not runtime_path.exists()
    assert service.shutdown() == shutdown
    runtime_root.rmdir()


def test_partial_qwen_startup_preserves_failure_and_cleans_runtime(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "run-qwen" / "attempts" / "slurm-92-0"
    attempt.mkdir(parents=True)
    runtime_root = Path(tempfile.mkdtemp(prefix="cmfrt-"))
    service = Qwen32BModelService(
        profile=QWEN32B_PROFILE,
        project_root=ROOT,
        runtime_root=runtime_root,
        runtime_attestor=lambda *_args, **_kwargs: (_ for _ in ()).throw(
            FinalModelRuntimeError("synthetic attestation failure")
        ),
        gpu_inspector=lambda **_kwargs: {"pass": True, "rows": []},
        port_available=lambda _port: True,
        monotonic=lambda: 1.0,
        port=47984,
    )

    with pytest.raises(Exception, match="synthetic attestation failure"):
        service.start(
            attempt_directory=attempt, run_id="run-qwen", slurm_job_id="92"
        )
    assert json.loads((attempt / "server-startup.json").read_text())["pass"] is False
    assert service.shutdown()["pass"] is True
    assert not tuple(runtime_root.iterdir())
    runtime_root.rmdir()


def test_devstral_service_uses_qualified_profile_command_and_shared_lifecycle(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "run-devstral" / "attempts" / "slurm-93-0"
    attempt.mkdir(parents=True)
    observed: dict[str, object] = {}
    process = _FakeProcess()
    runtime_root = Path(tempfile.mkdtemp(prefix="cmdfrt-"))

    def fake_process(argv, **kwargs):
        observed["argv"] = tuple(argv)
        observed["environment"] = kwargs["env"]
        return process

    service = DevstralModelService(
        profile=DEVSTRAL_PRODUCTION_PROFILE,
        project_root=ROOT,
        runtime_root=runtime_root,
        process_factory=fake_process,
        health_probe=lambda _base: HealthProbe(True, 200, "HTTP 200", "a" * 64),
        models_probe=lambda _base: ModelProbe(
            "http://127.0.0.1:47985/v1/models",
            True,
            "endpoint responded",
            200,
            (DEVSTRAL_PRODUCTION_PROFILE.served_model_name,),
        ),
        runtime_attestor=lambda *_args, **_kwargs: {"pass": True},
        gpu_inspector=lambda **kwargs: (
            observed.update(gpu_timeout_seconds=kwargs["timeout_seconds"])
            or {
                "pass": True,
                "rows": ["0, NVIDIA A100", "1, NVIDIA A100"],
            }
        ),
        port_available=lambda _port: True,
        monotonic=lambda: 1.0,
        sleeper=lambda _seconds: None,
        port=47985,
    )

    assert service.start(
        attempt_directory=attempt, run_id="run-devstral", slurm_job_id="93"
    ) == "http://127.0.0.1:47985/v1"
    assert observed["argv"] == DEVSTRAL_PRODUCTION_PROFILE.server_argv(port=47985)
    assert observed["gpu_timeout_seconds"] == 300
    startup = json.loads((attempt / "server-startup.json").read_text())
    assert startup["schema"] == "cmpilot-final-devstral-service-v1"
    assert startup["served_model_name"] == "mistralai/Devstral-Small-2507"
    assert startup["technical_runtime_amendment"]["amendment_id"] == (
        "devstral-startup-pre-rerun-v1"
    )
    assert startup["technical_runtime_amendment"][
        "frozen_model_profile_sha256"
    ] == "67b76bfa32b0a32bdf5b2e95b97283dff39a29457839664752f1e635764883b0"

    process.returncode = 0
    shutdown = service.shutdown()
    assert shutdown["schema"] == "cmpilot-final-devstral-shutdown-v1"
    assert shutdown["pass"] is True
    runtime_root.rmdir()


def test_long_attestation_does_not_consume_post_launch_health_budget(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "run-devstral" / "attempts" / "slurm-94-0"
    attempt.mkdir(parents=True)
    runtime_root = Path(tempfile.mkdtemp(prefix="cmdfrt-"))
    clock = _ManualClock()
    process = _FakeProcess()
    launch_times: list[float] = []
    health_times: list[float] = []

    def inspect_gpu(**_kwargs):
        clock.advance(31.0)
        return {"pass": True}

    def attest(*_args, **_kwargs):
        clock.advance(699.0)
        return {"pass": True}

    def launch(*_args, **_kwargs):
        launch_times.append(clock())
        return process

    def probe(_base: str) -> HealthProbe:
        health_times.append(clock())
        return HealthProbe(True, 200, "HTTP 200", "a" * 64)

    service = DevstralModelService(
        profile=DEVSTRAL_PRODUCTION_PROFILE,
        project_root=ROOT,
        runtime_root=runtime_root,
        process_factory=launch,
        health_probe=probe,
        models_probe=lambda _base: ModelProbe(
            "http://127.0.0.1:47986/v1/models",
            True,
            "endpoint responded",
            200,
            (DEVSTRAL_PRODUCTION_PROFILE.served_model_name,),
        ),
        runtime_attestor=attest,
        gpu_inspector=inspect_gpu,
        port_available=lambda _port: True,
        monotonic=clock,
        sleeper=clock.advance,
        port=47986,
    )

    assert service.start(
        attempt_directory=attempt, run_id="run-devstral", slurm_job_id="94"
    ) == "http://127.0.0.1:47986/v1"
    startup = json.loads((attempt / "server-startup.json").read_text())
    assert startup["startup_seconds"] == 730.0
    assert startup["phase_durations_seconds"] == {
        "gpu_inspection": 31.0,
        "post_launch_health_wait": 0.0,
        "process_launch": 0.0,
        "runtime_attestation": 699.0,
    }
    assert startup["timeout_budgets_seconds"]["post_launch_health"] == 600
    assert startup["health_probe_count"] == 1
    assert launch_times == [730.0]
    assert health_times == [730.0]

    process.returncode = 0
    assert service.shutdown()["pass"] is True
    runtime_root.rmdir()


def test_post_popen_health_loop_receives_full_fixed_budget(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "run-devstral" / "attempts" / "slurm-95-0"
    attempt.mkdir(parents=True)
    runtime_root = Path(tempfile.mkdtemp(prefix="cmdfrt-"))
    clock = _ManualClock()
    process = _FakeProcess()
    launch_times: list[float] = []
    health_times: list[float] = []

    def attest(*_args, **_kwargs):
        clock.advance(601.0)
        return {"pass": True}

    def launch(*_args, **_kwargs):
        launch_times.append(clock())
        return process

    def probe(_base: str) -> HealthProbe:
        health_times.append(clock())
        return HealthProbe(False, None, "not ready", None)

    def advance_to_deadline(_seconds: float) -> None:
        clock.advance(600.0)

    service = DevstralModelService(
        profile=DEVSTRAL_PRODUCTION_PROFILE,
        project_root=ROOT,
        runtime_root=runtime_root,
        process_factory=launch,
        health_probe=probe,
        models_probe=lambda _base: (_ for _ in ()).throw(
            AssertionError("models probe must not run after a health timeout")
        ),
        runtime_attestor=attest,
        gpu_inspector=lambda **_kwargs: {"pass": True},
        port_available=lambda _port: True,
        monotonic=clock,
        sleeper=advance_to_deadline,
        port=47987,
    )

    with pytest.raises(Exception, match="vLLM health timeout: not ready"):
        service.start(
            attempt_directory=attempt, run_id="run-devstral", slurm_job_id="95"
        )
    startup = json.loads((attempt / "server-startup.json").read_text())
    assert launch_times == [601.0]
    assert health_times == [601.0, 1201.0]
    assert startup["health_probe_count"] == 2
    assert startup["phase_durations_seconds"]["runtime_attestation"] == 601.0
    assert startup["phase_durations_seconds"]["post_launch_health_wait"] == 600.0
    assert startup["timeout_budgets_seconds"]["post_launch_health"] == 600

    process.returncode = 0
    assert service.shutdown()["pass"] is True
    runtime_root.rmdir()


def test_true_devstral_attestation_failure_prevents_service_and_model_invocation(
    tmp_path: Path,
) -> None:
    attempt = tmp_path / "run-devstral" / "attempts" / "slurm-96-0"
    attempt.mkdir(parents=True)
    runtime_root = Path(tempfile.mkdtemp(prefix="cmdfrt-"))
    invocations: list[str] = []
    service = DevstralModelService(
        profile=DEVSTRAL_PRODUCTION_PROFILE,
        project_root=ROOT,
        runtime_root=runtime_root,
        process_factory=lambda *_args, **_kwargs: invocations.append("process"),
        health_probe=lambda _base: (_ for _ in ()).throw(
            AssertionError("health probe must not run after attestation failure")
        ),
        models_probe=lambda _base: invocations.append("model"),
        runtime_attestor=lambda *_args, **_kwargs: {"pass": False},
        gpu_inspector=lambda **_kwargs: {"pass": True},
        port_available=lambda _port: True,
        monotonic=lambda: 1.0,
        port=47988,
    )

    with pytest.raises(Exception, match="runtime attestation failed"):
        service.start(
            attempt_directory=attempt, run_id="run-devstral", slurm_job_id="96"
        )
    assert invocations == []
    startup = json.loads((attempt / "server-startup.json").read_text())
    assert startup["phase_durations_seconds"]["process_launch"] is None
    assert startup["phase_durations_seconds"]["post_launch_health_wait"] is None
    assert service.shutdown()["pass"] is True
    runtime_root.rmdir()


def test_devstral_runtime_requires_current_verifier_ready_and_exact_identities() -> None:
    verification = json.loads(
        TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION.read_text(encoding="utf-8")
    )
    assert validate_devstral_environment_verification(verification)["pass"] is True

    not_ready = {**verification, "production_ready": False, "status": "NOT_READY"}
    rejected = validate_devstral_environment_verification(not_ready)
    assert rejected["pass"] is False
    assert rejected["checks"]["environment_ready"] is False

    wrong_freeze = json.loads(json.dumps(verification))
    wrong_freeze["snapshot_freeze"]["freeze_sha256"] = "0" * 64
    rejected = validate_devstral_environment_verification(wrong_freeze)
    assert rejected["pass"] is False
    assert rejected["checks"]["snapshot_freeze"] is False


def test_devstral_runtime_attestor_reruns_repository_verifier_before_server(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    verification = json.loads(
        TECHNICAL_SMOKE_ENVIRONMENT_VERIFICATION.read_text(encoding="utf-8")
    )
    observed: list[tuple[str, ...]] = []

    def fake_run(argv, *, environment, timeout):
        command_line = tuple(argv)
        observed.append(command_line)
        assert environment["HF_HUB_OFFLINE"] == "1"
        assert timeout == 1800
        output = Path(command_line[command_line.index("--output") + 1])
        output.write_text(json.dumps(verification), encoding="utf-8")
        return subprocess.CompletedProcess(
            command_line, 0, stdout="READY\n", stderr=""
        )

    monkeypatch.setattr(final_model_runtime, "_run_checked", fake_run)
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    integrity = final_model_runtime._attest_devstral_runtime(
        DEVSTRAL_PRODUCTION_PROFILE,
        project_root=ROOT,
        attempt=attempt,
        environment={"HF_HUB_OFFLINE": "1"},
    )

    assert integrity["pass"] is True
    assert observed == [
        (
            str(DEVSTRAL_PRODUCTION_PROFILE.environment.server_python),
            str(ROOT / "scripts/verify_devstral_environment.py"),
            "--output",
            str(attempt / "devstral-environment-verification.json"),
        )
    ]
    assert json.loads((attempt / "runtime-integrity.json").read_text())["pass"]


def test_array_attempts_receive_distinct_deterministic_bounded_ports() -> None:
    first = qwen_service_port(slurm_job_id="28499", attempt_id="slurm-28499-0")
    second = qwen_service_port(slurm_job_id="28499", attempt_id="slurm-28499-1")

    assert 40000 <= first < 60000
    assert 40000 <= second < 60000
    assert first != second
    assert first == qwen_service_port(
        slurm_job_id="28499", attempt_id="slurm-28499-0"
    )
    with pytest.raises(FinalModelRuntimeError, match="derive from"):
        qwen_service_port(slurm_job_id="28499", attempt_id="slurm-OTHER-0")


def test_gpu_gate_uses_two_visible_torch_a100s_not_all_physical_gpus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: list[tuple[tuple[str, ...], int]] = []

    def fake_run(argv, *, environment, timeout):
        command_line = tuple(argv)
        observed.append((command_line, timeout))
        if command_line[0] == str(QWEN32B_PROFILE.environment.server_python):
            return subprocess.CompletedProcess(
                command_line,
                0,
                stdout=json.dumps(
                    {
                        "count": 2,
                        "names": ["NVIDIA A100-SXM4-80GB", "NVIDIA A100-SXM4-80GB"],
                    }
                ),
                stderr="",
            )
        return subprocess.CompletedProcess(
            command_line,
            0,
            stdout="\n".join(
                f"{index}, NVIDIA A100-SXM4-80GB, GPU-{index}, 81920, 0, 81920"
                for index in range(4)
            ),
            stderr="",
        )

    monkeypatch.setattr(final_model_runtime, "_run_checked", fake_run)
    record = final_model_runtime._inspect_a100_allocation(
        server_python=QWEN32B_PROFILE.environment.server_python,
        tensor_parallel_size=2,
        environment={"CUDA_VISIBLE_DEVICES": "2,3"},
    )

    assert record["pass"] is True
    assert record["torch_visible_allocation"]["count"] == 2
    assert len(record["nvidia_smi"]["rows"]) == 4
    assert observed[0][0][0] == str(QWEN32B_PROFILE.environment.server_python)
    assert [timeout for _command, timeout in observed] == [30, 30]


def test_gpu_probe_timeout_expired_is_structured_phase_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def fake_run(argv, *, environment, timeout):
        nonlocal calls
        del environment
        command_line = tuple(argv)
        calls += 1
        if calls == 1:
            raise subprocess.TimeoutExpired(
                command_line,
                timeout,
                output=b"partial torch output",
                stderr=b"cold CUDA initialization",
            )
        return subprocess.CompletedProcess(
            command_line,
            0,
            stdout="0, NVIDIA A100-PCIE-40GB, GPU-0, 40960, 0, 40339\n",
            stderr="",
        )

    monkeypatch.setattr(final_model_runtime, "_run_checked", fake_run)
    record = final_model_runtime._inspect_a100_allocation(
        server_python=DEVSTRAL_PRODUCTION_PROFILE.environment.server_python,
        tensor_parallel_size=2,
        environment={"CUDA_VISIBLE_DEVICES": "0,1"},
        timeout_seconds=300,
    )

    assert record["pass"] is False
    allocation = record["torch_visible_allocation"]
    assert allocation["returncode"] is None
    assert allocation["timeout"] == {
        "argv": allocation["command"],
        "exception_type": "TimeoutExpired",
        "stderr": "cold CUDA initialization",
        "stdout": "partial torch output",
        "timeout_seconds": 300,
    }


def test_model_and_mcp_pinot_scientific_registries_are_ready() -> None:
    assert tuple(MODEL_EXECUTORS) == (
        QWEN32B_PROFILE.profile_id,
        DEVSTRAL_PRODUCTION_PROFILE.profile_id,
    )
    assert tuple(SCIENTIFIC_BACKENDS) == ("axios-v1", "mcp-pinot-v1")
    context = {
        "model_profile_key": QWEN32B_PROFILE.profile_id,
        "model_profile": QWEN32B_PROFILE.final_experiment_record(
            step_limit=QWEN_FROZEN_STEP_LIMIT
        ),
    }
    assert isinstance(build_qwen32b_model_executor(context), Qwen32BFinalModelExecutor)
    context["model_profile"] = QWEN32B_PROFILE.final_experiment_record(step_limit=16)
    with pytest.raises(FinalModelRuntimeError, match="step_limit=15"):
        build_qwen32b_model_executor(context)

    devstral_context = {
        "model_profile_key": DEVSTRAL_PRODUCTION_PROFILE.profile_id,
        "model_profile": DEVSTRAL_PRODUCTION_PROFILE.final_experiment_record(
            step_limit=QWEN_FROZEN_STEP_LIMIT
        ),
    }
    executor = build_devstral_model_executor(devstral_context)
    assert isinstance(executor, DevstralFinalModelExecutor)
    assert type(executor.shared_runtime) is SharedMiniSWERuntime
    assert executor.shared_runtime.adapter_writer is write_devstral_production_adapter
    qwen_executor = build_qwen32b_model_executor(
        {
            "model_profile_key": QWEN32B_PROFILE.profile_id,
            "model_profile": QWEN32B_PROFILE.final_experiment_record(
                step_limit=QWEN_FROZEN_STEP_LIMIT
            ),
        }
    )
    assert type(qwen_executor.shared_runtime) is type(executor.shared_runtime)
    assert qwen_executor.shared_runtime.adapter_writer is not (
        executor.shared_runtime.adapter_writer
    )
    devstral_context["model_profile"] = {
        **devstral_context["model_profile"],
        "revision": "0" * 40,
    }
    with pytest.raises(FinalModelRuntimeError, match="exact frozen"):
        build_devstral_model_executor(devstral_context)
