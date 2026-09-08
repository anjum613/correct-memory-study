from __future__ import annotations

import subprocess
import sys
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from cmpilot.mini_swe_adapter import MiniSWEInfo
from cmpilot.model_profiles import load_model_profile
from cmpilot.smoke_runner import (
    AgentExecution,
    PreflightResult,
    SmokeConfig,
    dry_run,
    preflight,
    execute_agent,
    resolve_config,
    run_smoke,
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
    Path(environment["CMPILOT_TRAJECTORY"]).write_text('{"messages": []}\n', encoding="utf-8")
    return AgentExecution(exit_code=0, stdout="fake agent completed\n", stderr="", timed_out=False)


def fake_failed_agent(_command, _cwd, environment, _timeout) -> AgentExecution:
    repository = Path(environment["CMPILOT_REPOSITORY"])
    (repository / "calculator.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    Path(environment["CMPILOT_TRAJECTORY"]).write_text('{"messages": []}\n', encoding="utf-8")
    return AgentExecution(exit_code=0, stdout="fake agent completed\n", stderr="", timed_out=False)


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
    arguments = SimpleNamespace(base_url=None, model=None, profile=None, mini_python=None, runs_root=None, agent_timeout=600)
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


def test_resolve_profile_uses_exact_served_identity_and_isolated_root(tmp_path: Path) -> None:
    arguments = SimpleNamespace(
        base_url="http://server:8000/v1",
        model=None,
        profile="devstral-small-2507",
        mini_python="/mini/python",
        runs_root=str(tmp_path / "runs"),
        agent_timeout=600,
    )
    config = resolve_config(arguments, {"VLLM_MODEL": "must-not-leak-into-profile"})
    profile = load_model_profile("devstral-small-2507")

    assert config.model == profile.served_model_name
    assert config.model_profile == profile
    assert config.runs_root == tmp_path / "runs" / "non-confirmatory" / profile.identity / profile.runtime_environment


def test_profiled_smoke_manifest_and_run_id_are_model_isolated(tmp_path: Path) -> None:
    profile = load_model_profile("devstral-small-2507")
    base = smoke_config(tmp_path)
    config = SmokeConfig(
        base_url=base.base_url,
        model=profile.served_model_name,
        mini_python=base.mini_python,
        runs_root=tmp_path / "runs" / "non-confirmatory" / profile.identity / profile.runtime_environment,
        agent_timeout=base.agent_timeout,
        template=base.template,
        task_file=base.task_file,
        model_profile=profile,
    )
    profiled_preflight = PreflightResult(
        ok=True,
        diagnostic="preflight passed",
        probe=ModelProbe(
            "http://127.0.0.1:8000/v1/models",
            True,
            "endpoint responded",
            200,
            (profile.served_model_name,),
        ),
        mini_swe=MiniSWEInfo(True, "2.4.6", "mini-SWE-agent 2.4.6"),
    )
    with patch("cmpilot.smoke_runner.preflight", return_value=profiled_preflight), patch(
        "cmpilot.smoke_runner.execute_agent", side_effect=fake_successful_agent
    ):
        result = run_smoke(config)

    run_directory = next(config.runs_root.iterdir())
    run = json.loads((run_directory / "run.json").read_text())
    model_info = json.loads((run_directory / "model-info.json").read_text())
    resolved = json.loads((run_directory / "resolved-config.json").read_text())
    assert result == 0
    assert run["run_id"].startswith(f"smoke-{profile.identity}-")
    assert run["model_profile"]["model_revision"] == profile.model_revision
    assert model_info["model_profile"]["tokenizer_revision"] == profile.tokenizer_revision
    assert resolved["model_profile"]["served_model_name"] == profile.served_model_name


def test_unprofiled_resolved_config_keeps_original_output_shape(tmp_path: Path) -> None:
    config = smoke_config(tmp_path)

    from cmpilot.smoke_runner import _config_artifact

    assert _config_artifact(config) == {
        "base_url": config.base_url,
        "model": config.model,
        "mini_python": config.mini_python,
        "runs_root": str(config.runs_root),
        "agent_timeout": config.agent_timeout,
        "template": str(config.template),
        "task_file": str(config.task_file),
    }
