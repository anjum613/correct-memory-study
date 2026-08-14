from __future__ import annotations

import json
import os
import subprocess
import textwrap
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import pytest

from cmpilot.mini_swe_config import (
    MiniSWEConfigError,
    MiniSWEEndpointSettings,
    PlainDataError,
    assert_no_sensitive_keys,
    build_mini_swe_config,
    describe_data_types,
    deterministic_json,
    to_plain_data,
    validate_plain_data,
)


ROOT = Path(__file__).parents[1]
DEFAULT_MINI_PY = Path("/home/s224049759/environments/mini-swe-agent-smoke/bin/python")


def _mini_python() -> Path:
    return Path(os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PY))


def _run_in_mini_environment(script: str) -> subprocess.CompletedProcess[str]:
    mini_python = _mini_python()
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    environment = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    return subprocess.run(
        [str(mini_python), "-c", textwrap.dedent(script)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=20,
    )


def _base_config() -> dict[str, object]:
    return {
        "agent": {"system_template": "system", "instance_template": "{{task}}"},
        "environment": {"env": {"PAGER": "cat"}},
        "model": {"observation_template": "{{output.output}}", "model_kwargs": {"drop_params": True}},
    }


def _generated_config(tmp_path: Path) -> dict[str, object]:
    return build_mini_swe_config(
        _base_config(),
        {
            "agent": {"step_limit": 15, "cost_limit": 0.0},
            "environment": {"timeout": 60},
            "model": {"cost_tracking": "ignore_errors", "model_kwargs": {"max_tokens": 512}},
        },
        endpoint=MiniSWEEndpointSettings("http://127.0.0.1:9/v1", "test-model", 2.0, 0),
        repository=tmp_path / "repository",
        trajectory=tmp_path / "trajectory.json",
        agent_environment={"PATH": "/usr/bin", "HOME": "/tmp/agent-home"},
    )


def test_validate_plain_data_accepts_supported_primitive_configuration() -> None:
    value = {"null": None, "bool": True, "int": 2, "float": 1.5, "text": "x", "list": [1, "two"]}

    validate_plain_data(value)
    assert to_plain_data(value) == value


def test_path_and_tuple_are_explicitly_converted() -> None:
    value = {"agent": {"output_path": Path("/tmp/trajectory.json")}, "items": (1, 2)}

    assert to_plain_data(value) == {
        "agent": {"output_path": "/tmp/trajectory.json"},
        "items": [1, 2],
    }


def test_enum_and_dataclass_are_explicitly_converted() -> None:
    class Mode(Enum):
        PREFLIGHT = "preflight"

    @dataclass(frozen=True)
    class Settings:
        mode: Mode
        path: Path

    assert to_plain_data(Settings(Mode.PREFLIGHT, Path("/tmp/run"))) == {
        "mode": "preflight",
        "path": "/tmp/run",
    }


def test_pydantic_model_is_converted_without_a_cmpilot_dependency() -> None:
    result = _run_in_mini_environment(
        """
        import json
        from pathlib import Path
        from pydantic import BaseModel
        from cmpilot.mini_swe_config import to_plain_data

        class Config(BaseModel):
            output_path: Path
            values: tuple[int, ...]

        print(json.dumps(to_plain_data(Config(output_path=Path('/tmp/t.json'), values=(1, 2))), sort_keys=True))
        """
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"output_path": "/tmp/t.json", "values": [1, 2]}


def test_unsupported_object_reports_exact_nested_path_and_type() -> None:
    class Unsupported:
        pass

    with pytest.raises(PlainDataError, match=r"\$\.model\.model_kwargs\.bad: unsupported value type") as error:
        validate_plain_data({"model": {"model_kwargs": {"bad": Unsupported()}}})

    assert f"{Unsupported.__module__}.{Unsupported.__qualname__}" in str(error.value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_float_is_rejected(value: float) -> None:
    with pytest.raises(PlainDataError, match=r"\$\.temperature: non-finite float"):
        to_plain_data({"temperature": value})


def test_json_round_trip_is_valid_and_deterministic() -> None:
    first_value, first_text = deterministic_json({"z": Path("/tmp/z"), "a": [True, 1, 1.5]})
    second_value, second_text = deterministic_json({"z": Path("/tmp/z"), "a": [True, 1, 1.5]})

    assert json.loads(first_text) == first_value == second_value
    assert first_text == second_text


def test_yaml_safe_round_trip_uses_only_plain_data() -> None:
    result = _run_in_mini_environment(
        """
        import json
        import yaml
        from pathlib import Path
        from cmpilot.mini_swe_config import deterministic_json, validate_plain_data

        plain, expected = deterministic_json({'agent': {'output_path': Path('/tmp/t.json')}, 'values': [1, True]})
        text = yaml.safe_dump(plain, sort_keys=True)
        loaded = yaml.safe_load(text)
        validate_plain_data(loaded)
        assert deterministic_json(loaded)[1] == expected
        print(json.dumps(loaded, sort_keys=True))
        """
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["agent"]["output_path"] == "/tmp/t.json"


def test_mini_swe_config_generation_uses_only_supported_sections(tmp_path: Path) -> None:
    raw = _generated_config(tmp_path)
    types = describe_data_types(raw)
    plain, _ = deterministic_json(raw)

    assert set(plain) == {"agent", "environment", "model"}
    assert types["$.agent.output_path"] == "pathlib.PosixPath"
    assert plain["agent"]["output_path"] == str(tmp_path / "trajectory.json")
    assert plain["environment"]["cwd"] == str(tmp_path / "repository")
    assert plain["model"]["model_class"] == "cmpilot_vllm_text_model.VllmTextModel"
    assert plain["model"]["model_name"] == "test-model"
    assert plain["model"]["base_url"] == "http://127.0.0.1:9/v1"
    assert plain["model"]["max_tokens"] == 512
    assert plain["model"]["context_limit"] == 4096
    assert plain["model"]["context_safety_margin"] == 32
    assert plain["model"]["minimum_useful_completion"] == 64
    assert plain["model"]["tokenizer_path"].endswith(
        "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
    )
    assert plain["model"]["request_budget_artifact_path"] == str(
        tmp_path / "request-budgets.jsonl"
    )
    assert plain["model"]["connect_timeout_seconds"] == 2.0
    assert plain["model"]["read_timeout_seconds"] == 2.0
    assert "model_kwargs" not in plain["model"]


def test_unknown_mini_swe_fields_are_rejected_instead_of_silently_discarded(tmp_path: Path) -> None:
    with pytest.raises(MiniSWEConfigError, match="unsupported mini-SWE-agent 2.4.6 fields"):
        build_mini_swe_config(
            _base_config(),
            {"agent": {"invented_field": True}},
            endpoint=MiniSWEEndpointSettings("http://127.0.0.1:9/v1", "model"),
            repository=tmp_path / "repository",
            trajectory=tmp_path / "trajectory.json",
            agent_environment={},
        )


def test_secrets_are_not_written_and_max_tokens_is_not_a_secret(tmp_path: Path) -> None:
    plain, text = deterministic_json(_generated_config(tmp_path))

    assert_no_sensitive_keys(plain)
    assert "local-smoke-placeholder" not in text
    assert "OPENAI_API_KEY" not in text
    assert plain["model"]["max_tokens"] == 512
    with pytest.raises(PlainDataError, match=r"\$\.model\.api_key: sensitive"):
        assert_no_sensitive_keys({"model": {"api_key": "must-not-persist"}})


def test_public_command_authorization_policy_metadata_is_not_a_credential() -> None:
    assert_no_sensitive_keys(
        {"command_authorization_policy": {"policy_version": "calculator-capability-policy-v4"}}
    )


def test_direct_model_rejects_context_policy_changes() -> None:
    result = _run_in_mini_environment(
        """
        from pydantic import ValidationError
        from cmpilot.integrations.miniswe.vllm_text_model import VllmTextModelConfig

        try:
            VllmTextModelConfig(
                model_name='model',
                base_url='http://127.0.0.1:9/v1',
                context_limit=8192,
            )
        except ValidationError:
            print('frozen-context-rejected')
        else:
            raise AssertionError('context policy change was accepted')
        """
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("frozen-context-rejected")


def test_secret_wrapper_is_rejected() -> None:
    class SecretWrapper:
        def get_secret_value(self) -> str:
            return "hidden"

    with pytest.raises(PlainDataError, match="secret wrapper"):
        to_plain_data({"credential": SecretWrapper()})
