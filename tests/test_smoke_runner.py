from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cmpilot.mini_swe_adapter import MiniSWEInfo
from cmpilot.smoke_runner import (
    AgentExecution,
    PreflightResult,
    SmokeConfig,
    dry_run,
    preflight,
    execute_agent,
    resolve_config,
    run_smoke,
    _source_snapshot,
    _trajectory_metrics,
)
from cmpilot.vllm_client import ModelProbe


def smoke_config(tmp_path: Path) -> SmokeConfig:
    repository_root = Path(__file__).parents[1]
    return SmokeConfig(
        base_url="http://127.0.0.1:8000/v1",
        model="smoke-model",
        mini_python="/fake/mini-python",
        runs_root=tmp_path / "runs",
        agent_timeout=10,
        template=repository_root / "tasks" / "smoke_test" / "repository",
        task_file=repository_root / "tasks" / "smoke_test" / "task.md",
    )


def passing_preflight() -> PreflightResult:
    return PreflightResult(
        ok=True,
        diagnostic="preflight passed",
        probe=ModelProbe("http://127.0.0.1:8000/v1/models", True, "endpoint responded", 200, ("smoke-model",)),
        mini_swe=MiniSWEInfo(True, "2.4.6", "mini-SWE-agent 2.4.6"),
    )


def fake_successful_agent(_command, _cwd, environment, _timeout) -> AgentExecution:
    repository = Path(environment["CMPILOT_REPOSITORY"])
    (repository / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    Path(environment["CMPILOT_TRAJECTORY"]).write_text(
        '{"info":{"model_stats":{"api_calls":1},"exit_status":"Submitted"},'
        '"messages":[{"role":"assistant","extra":{"actions":[{"command":"cat calculator.py"}],'
        '"response":{"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}}}]}\n',
        encoding="utf-8",
    )
    return AgentExecution(exit_code=0, stdout="fake agent completed\n", stderr="", timed_out=False)


def fake_failed_agent(_command, _cwd, environment, _timeout) -> AgentExecution:
    repository = Path(environment["CMPILOT_REPOSITORY"])
    (repository / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    Path(environment["CMPILOT_TRAJECTORY"]).write_text('{"messages": []}\n', encoding="utf-8")
    return AgentExecution(exit_code=0, stdout="fake agent completed\n", stderr="", timed_out=False)


def fake_protocol_failure_agent(_command, _cwd, environment, _timeout) -> AgentExecution:
    Path(environment["CMPILOT_TRAJECTORY"]).write_text(
        '{"info":{"model_stats":{"api_calls":2},"exit_status":"REPEATED_INVALID_ACTION",'
        '"protocol":{"technical_validity":"PASS","protocol_safety_status":"PASS",'
        '"model_format_status":"FAIL","invalid_response_count":2,"invalid_action_count":2,'
        '"executed_action_count":0,"repository_progress":false,'
        '"functional_outcome":"INCOMPLETE","failure_dimension":"semantic_invalid_action"}},'
        '"messages":[{"role":"assistant","content":"rejected placeholder",'
        '"extra":{"protocol_rejected":true,"actions":[{"command":"<action>"}]}}]}',
        encoding="utf-8",
    )
    return AgentExecution(
        exit_code=0,
        stdout="safe model protocol failure\\n",
        stderr="",
        timed_out=False,
    )

def test_resolve_config_prefers_cli_over_environment(tmp_path: Path) -> None:
    arguments = SimpleNamespace(
        base_url="http://cli:8000/v1",
        model="cli-model",
        mini_python="/cli/python",
        runs_root=str(tmp_path / "cli-runs"),
        agent_timeout=12,
    )
    config = resolve_config(
        arguments,
        {
            "VLLM_BASE_URL": "http://environment:8000/v1",
            "VLLM_MODEL": "environment-model",
            "MINI_SWE_PYTHON": "/environment/python",
            "CMPILOT_RUNS_ROOT": str(tmp_path / "environment-runs"),
        },
    )

    assert config.base_url == "http://cli:8000/v1"
    assert config.model == "cli-model"
    assert config.mini_python == "/cli/python"
    assert config.runs_root == tmp_path / "cli-runs"
    assert config.agent_timeout == 12


def test_preflight_checks_mini_swe_even_when_the_model_server_is_unavailable(tmp_path: Path) -> None:
    config = smoke_config(tmp_path)
    unavailable = ModelProbe("http://127.0.0.1:8000/v1/models", False, "connection refused")
    installed = MiniSWEInfo(True, "2.4.6", "mini-SWE-agent 2.4.6")
    with patch("cmpilot.smoke_runner.probe_models", return_value=unavailable) as server, patch(
        "cmpilot.smoke_runner.mini_swe_info", return_value=installed
    ) as mini:
        result = preflight(config)

    assert result.ok is False
    assert result.diagnostic == "connection refused"
    server.assert_called_once_with(config.base_url)
    mini.assert_called_once_with(config.mini_python)


def test_dry_run_does_not_create_artifacts_or_launch_agent(tmp_path: Path, capsys) -> None:
    config = smoke_config(tmp_path)
    with patch("cmpilot.smoke_runner.preflight", return_value=passing_preflight()), patch(
        "cmpilot.smoke_runner.execute_agent"
    ) as launch:
        result = dry_run(config)

    output = capsys.readouterr().out
    assert result == 0
    assert "Resolved configuration:" in output
    assert "Would create artifacts:" in output
    assert "Would invoke exactly once:" in output
    assert not config.runs_root.exists()
    launch.assert_not_called()


def test_successful_smoke_uses_clean_copy_preserves_template_and_launches_once(tmp_path: Path) -> None:
    config = smoke_config(tmp_path)
    template_before = {path.relative_to(config.template): path.read_bytes() for path in config.template.rglob("*") if path.is_file()}
    with patch("cmpilot.smoke_runner.preflight", return_value=passing_preflight()), patch(
        "cmpilot.smoke_runner.execute_agent", side_effect=fake_successful_agent
    ) as launch:
        result = run_smoke(config)

    run_directory = next(config.runs_root.iterdir())
    run = (run_directory / "run.json").read_text(encoding="utf-8")
    assert result == 0
    assert launch.call_count == 1
    assert '"final_classification": "secure_functional_success"' in run
    assert (run_directory / "final.patch").read_text(encoding="utf-8").strip()
    assert (run_directory / "trajectory.json").is_file()
    assert (run_directory / "task-instruction.md").read_text(encoding="utf-8") == config.task_file.read_text(encoding="utf-8")
    assert {path.relative_to(config.template): path.read_bytes() for path in config.template.rglob("*") if path.is_file()} == template_before


def test_failed_functional_smoke_is_not_retried(tmp_path: Path) -> None:
    config = smoke_config(tmp_path)
    with patch("cmpilot.smoke_runner.preflight", return_value=passing_preflight()), patch(
        "cmpilot.smoke_runner.execute_agent", side_effect=fake_failed_agent
    ) as launch:
        result = run_smoke(config)

    run_directory = next(config.runs_root.iterdir())
    assert result == 3
    assert launch.call_count == 1
    assert '"final_classification": "functional_failure"' in (run_directory / "run.json").read_text()


def test_safe_model_protocol_failure_is_classified_dimensionally(tmp_path: Path) -> None:
    config = smoke_config(tmp_path)
    with patch("cmpilot.smoke_runner.preflight", return_value=passing_preflight()), patch(
        "cmpilot.smoke_runner.execute_agent", side_effect=fake_protocol_failure_agent
    ):
        result = run_smoke(config)

    run_directory = next(config.runs_root.iterdir())
    run = json.loads((run_directory / "run.json").read_text(encoding="utf-8"))
    classification = json.loads(
        (run_directory / "classification.json").read_text(encoding="utf-8")
    )

    assert result == 3
    assert run["final_classification"] == "functional_failure"
    assert run["technical_validity"] == "PASS"
    assert run["protocol_safety_status"] == "PASS"
    assert run["model_format_status"] == "FAIL"
    assert run["termination_reason"] == "REPEATED_INVALID_ACTION"
    assert run["command_count"] == 0
    assert classification["dimensions"]["failure_dimension"] == "semantic_invalid_action"

def test_unavailable_server_creates_infrastructure_failure_artifact(tmp_path: Path) -> None:
    config = smoke_config(tmp_path)
    unavailable = PreflightResult(
        ok=False,
        diagnostic="connection refused",
        probe=ModelProbe("http://127.0.0.1:8000/v1/models", False, "connection refused"),
        mini_swe=MiniSWEInfo(False, "", "not checked"),
    )
    with patch("cmpilot.smoke_runner.preflight", return_value=unavailable):
        result = run_smoke(config)

    run_directory = next(config.runs_root.iterdir())
    assert result == 2
    assert '"final_classification": "infrastructure_failure"' in (run_directory / "run.json").read_text()
    assert "connection refused" in (run_directory / "classification.json").read_text()


def test_timeout_result_is_preserved_as_infrastructure_failure(tmp_path: Path) -> None:
    config = smoke_config(tmp_path)
    timed_out = AgentExecution(exit_code=None, stdout="partial stdout", stderr="partial stderr", timed_out=True)
    with patch("cmpilot.smoke_runner.preflight", return_value=passing_preflight()), patch(
        "cmpilot.smoke_runner.execute_agent", return_value=timed_out
    ):
        result = run_smoke(config)

    run_directory = next(config.runs_root.iterdir())
    assert result == 2
    assert "partial stdout" in (run_directory / "agent-stdout.txt").read_text()
    assert '"final_classification": "infrastructure_failure"' in (run_directory / "run.json").read_text()


def test_execute_agent_terminates_a_timed_out_child_process() -> None:
    execution = execute_agent(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        Path.cwd(),
        {"PATH": str(Path(sys.executable).parent)},
        0.05,
    )

    assert execution.timed_out is True
    assert execution.exit_code is not None


def test_resolve_config_uses_environment_values_when_cli_is_absent(tmp_path: Path) -> None:
    arguments = SimpleNamespace(base_url=None, model=None, mini_python=None, runs_root=None, agent_timeout=600)
    config = resolve_config(
        arguments,
        {
            "VLLM_BASE_URL": "http://server:8000/v1",
            "VLLM_MODEL": "environment-model",
            "MINI_SWE_PYTHON": "/environment/python",
            "CMPILOT_RUNS_ROOT": str(tmp_path / "runs"),
        },
    )

    assert config.base_url == "http://server:8000/v1"
    assert config.model == "environment-model"
    assert config.mini_python == "/environment/python"
    assert config.runs_root == tmp_path / "runs"


def test_source_snapshot_excludes_git_and_test_caches(tmp_path: Path) -> None:
    (tmp_path / "calculator.py").write_text("def add(a, b): return a + b\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "index").write_bytes(b"git")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "calculator.pyc").write_bytes(b"cache")

    snapshot = _source_snapshot(tmp_path)

    assert set(snapshot) == {Path("calculator.py")}


def test_trajectory_metrics_records_usage_and_repository_inspection(tmp_path: Path) -> None:
    trajectory = tmp_path / "trajectory.json"
    trajectory.write_text(
        '{"info":{"model_stats":{"api_calls":2},"exit_status":"Submitted",'
        '"protocol":{"technical_validity":"PASS","protocol_safety_status":"PASS",'
        '"model_format_status":"PASS","invalid_response_count":1,"invalid_action_count":1,'
        '"executed_action_count":1,"repository_progress":true,'
        '"functional_outcome":"SUBMITTED","failure_dimension":"model_task"}},'
        '"messages":[{"role":"assistant","extra":{"actions":[{"command":"sed -n 1,80p calculator.py"}],'
        '"response":{"usage":{"prompt_tokens":40,"completion_tokens":12,"total_tokens":52}}}}]}',
        encoding="utf-8",
    )

    metrics = _trajectory_metrics(trajectory, {"calculator.py", "test_calculator.py"})

    assert metrics["agent_steps"] == 2
    assert metrics["model_request_count"] == 2
    assert metrics["command_count"] == 1
    assert metrics["usage_total"] == 52
    assert metrics["termination_reason"] == "Submitted"
    assert metrics["repository_inspected"] is True
    assert metrics["files_inspected"] == ["calculator.py"]
    assert metrics["technical_validity"] == "PASS"
    assert metrics["protocol_safety_status"] == "PASS"
    assert metrics["model_format_status"] == "PASS"
    assert metrics["invalid_response_count"] == 1
    assert metrics["invalid_action_count"] == 1
    assert metrics["executed_action_count"] == 1
    assert metrics["repository_progress"] is True
    assert metrics["functional_outcome"] == "SUBMITTED"
