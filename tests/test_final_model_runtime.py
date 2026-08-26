from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

import pytest

from cmpilot import final_model_runtime
from cmpilot.experiment_models import QWEN32B_PROFILE
from cmpilot.final_model_runtime import (
    FinalModelRuntimeError,
    HealthProbe,
    QWEN_FROZEN_STEP_LIMIT,
    Qwen32BFinalModelExecutor,
    Qwen32BModelService,
    SharedMiniSWERuntime,
    build_qwen32b_model_executor,
    classify_mini_swe_execution,
    load_scientific_agent_binding,
    qwen_service_port,
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
        gpu_inspector=lambda **_kwargs: {
            "pass": True,
            "rows": ["0, NVIDIA A100", "1, NVIDIA A100"],
        },
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
    runtime_path = Path(environment["VLLM_RPC_BASE_PATH"])
    assert runtime_path.parent == runtime_root
    assert runtime_path.name.startswith("cmq-")
    assert "HF_TOKEN" not in environment
    assert json.loads((attempt / "server-startup.json").read_text())["pass"] is True
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
    observed: list[tuple[str, ...]] = []

    def fake_run(argv, *, environment, timeout):
        command_line = tuple(argv)
        observed.append(command_line)
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
    assert observed[0][0] == str(QWEN32B_PROFILE.environment.server_python)


def test_qwen_registry_is_ready_but_scientific_registry_waits_for_families() -> None:
    assert tuple(MODEL_EXECUTORS) == (QWEN32B_PROFILE.profile_id,)
    assert SCIENTIFIC_BACKENDS == {}
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
