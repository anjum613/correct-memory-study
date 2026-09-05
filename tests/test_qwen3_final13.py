from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

import pytest

from cmpilot.qwen3_final13 import (
    MODEL_ID,
    MODEL_REVISION,
    RunConfig,
    _binding_by_family,
    evaluate_repository,
    materialize_repository,
    qwen3_cells,
    render_frozen_messages,
    run_canary,
    task_policy,
    validate_frozen_inputs,
    validate_model_profile,
    write_public_test_runner,
)
from cmpilot.smoke_runner import AgentExecution


ROOT = Path(__file__).parents[1]
FAMILIES = (
    "F01", "F02", "F04", "F08", "F17", "F20",
    "X02", "X05", "X06", "X11", "X20", "X24", "X28",
)


def test_frozen_cohort_and_qwen_projection_are_complete_and_unique() -> None:
    validation = validate_frozen_inputs(ROOT)
    cells = qwen3_cells(ROOT)

    assert validation["status"] == "PASS"
    assert validation["artifact_hashes_verified"] == 391
    assert validation["cohort_commit"].startswith("c03215d43")
    assert len(cells) == 104
    assert len({cell.actual_run_id for cell in cells}) == 104
    assert len({cell.source_run_id for cell in cells}) == 104
    assert [cell.source_execution_order for cell in cells] == sorted(
        cell.source_execution_order for cell in cells
    )
    assert {cell.family_id for cell in cells} == set(FAMILIES)
    assert {cell.condition for cell in cells} == {
        "NO_MEMORY",
        "SOURCE_CORRECT_MEMORY",
        "MATCHED_IRRELEVANT_MEMORY",
        "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY",
    }
    expected_design = {
        (condition, repetition)
        for condition in {
            "NO_MEMORY",
            "SOURCE_CORRECT_MEMORY",
            "MATCHED_IRRELEVANT_MEMORY",
            "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY",
        }
        for repetition in (1, 2)
    }
    for family_id in FAMILIES:
        assert {
            (cell.condition, cell.repetition)
            for cell in cells
            if cell.family_id == family_id
        } == expected_design


def test_every_projected_cell_reconstructs_its_frozen_message_hash() -> None:
    for cell in qwen3_cells(ROOT):
        messages, digest = render_frozen_messages(ROOT, cell)
        binding = _binding_by_family(ROOT, cell.family_id)

        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert digest == binding["messages_sha256"][cell.condition]


def test_qwen3_run_ids_bind_the_actual_model_revision() -> None:
    first = qwen3_cells(ROOT)[0]
    identity = {
        "condition": first.condition,
        "family_id": first.family_id,
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "repetition": first.repetition,
        "seed": first.seed,
        "source_run_id": first.source_run_id,
    }
    expected = __import__("hashlib").sha256(
        (json.dumps(identity, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    ).hexdigest()[:24]

    assert first.actual_run_id == expected


def test_coder_next_projects_the_devstral_arm_with_the_identical_design() -> None:
    model_id = "Qwen/Qwen3-Coder-Next-FP8"
    revision = "da6e2ed27304dd39abadd9c82ef50e8de67bdd4c"
    cells = qwen3_cells(
        ROOT,
        source_model_key="devstral-small-2507",
        model_id=model_id,
        model_revision=revision,
    )
    validation = validate_frozen_inputs(
        ROOT,
        source_model_key="devstral-small-2507",
        model_id=model_id,
        model_revision=revision,
    )

    assert validation["status"] == "PASS"
    assert len(cells) == 104
    assert len({cell.actual_run_id for cell in cells}) == 104
    assert {cell.family_id for cell in cells} == set(FAMILIES)
    expected_design = {
        (condition, repetition)
        for condition in {
            "NO_MEMORY",
            "SOURCE_CORRECT_MEMORY",
            "MATCHED_IRRELEVANT_MEMORY",
            "SOURCE_MEMORY_PLUS_APPLICABILITY_BOUNDARY",
        }
        for repetition in (1, 2)
    }
    for family_id in FAMILIES:
        assert {
            (cell.condition, cell.repetition)
            for cell in cells
            if cell.family_id == family_id
        } == expected_design


def test_coder_next_runpod_profile_is_pinned_to_two_l40s() -> None:
    result = validate_model_profile(
        ROOT,
        model_profile_path=Path("configs/models/qwen3-coder-next-fp8-runpod.json"),
        model_id="Qwen/Qwen3-Coder-Next-FP8",
        model_revision="da6e2ed27304dd39abadd9c82ef50e8de67bdd4c",
        served_model_name="qwen3-coder-next-fp8",
        tokenizer_json_sha256=(
            "19564a48c4f71a2a1b937cce34c737a1e662b171c5f5d7edf641a15cd896f07d"
        ),
        tokenizer_config_sha256=(
            "fc76878832c668e3f0f8be66e6239a475b9093d2fe5cef97c242369779e6c6e6"
        ),
    )

    assert result["status"] == "PASS"


def test_runpod_profile_binds_two_l40s_and_frozen_generation_budget() -> None:
    result = validate_model_profile(ROOT)
    profile = json.loads(
        (ROOT / "configs/models/qwen3-coder-30b-a3b-instruct-fp8-runpod.json")
        .read_text(encoding="utf-8")
    )

    assert result["status"] == "PASS"
    assert profile["deployment"]["gpu_count"] == 2
    assert profile["deployment"]["gpu_model"] == "NVIDIA L40S"
    assert profile["server"]["tensor_parallel_size"] == 2
    assert profile["server"]["max_model_length"] == 4096
    assert profile["generation"] == {
        "max_tokens": 512,
        "samples_per_call": 1,
        "temperature": 0.0,
    }


@pytest.mark.parametrize("family_id", FAMILIES)
def test_baseline_materialization_has_expected_matrix(
    tmp_path: Path,
    family_id: str,
) -> None:
    if family_id.startswith("X"):
        cryptography = pytest.importorskip("cryptography")
        dependency_path = Path(cryptography.__file__).parents[1]
    else:
        dependency_path = None
    binding = _binding_by_family(ROOT, family_id)
    repository = tmp_path / family_id
    service, files = materialize_repository(ROOT, binding, repository)
    policy = task_policy(service, files)
    config = RunConfig(
        project_root=ROOT,
        run_root=tmp_path / "runs",
        base_url="http://127.0.0.1:9/v1",
        mini_python=sys.executable,
        tokenizer_path=tmp_path,
        v3_dependency_path=dependency_path,
    )
    result = evaluate_repository(config, binding, repository, service)

    assert (repository / service).is_file()
    assert policy.writable_paths == (service.as_posix(),)
    assert service.as_posix() not in policy.readable_protected_paths
    assert result["harness_ok"] is True
    assert result["statuses"] == {
        "existing": "PASS",
        "feature": "FAIL",
        "invariant": "PASS",
    }


@pytest.mark.parametrize("family_id", FAMILIES)
def test_agent_public_runner_exposes_only_public_checks(
    tmp_path: Path,
    family_id: str,
) -> None:
    if family_id.startswith("X"):
        cryptography = pytest.importorskip("cryptography")
        dependency_path = Path(cryptography.__file__).parents[1]
    else:
        dependency_path = None
    binding = _binding_by_family(ROOT, family_id)
    repository = tmp_path / "repository"
    service, _ = materialize_repository(ROOT, binding, repository)
    config = RunConfig(
        project_root=ROOT,
        run_root=tmp_path / "runs",
        base_url="http://127.0.0.1:9/v1",
        mini_python=sys.executable,
        tokenizer_path=tmp_path,
        v3_dependency_path=dependency_path,
    )
    record = write_public_test_runner(
        config,
        tmp_path / "agent-bin",
        binding=binding,
        service_path=service,
    )
    result = subprocess.run(
        [str(tmp_path / "agent-bin" / "run_public_tests")],
        cwd=repository,
        text=True,
        capture_output=True,
        timeout=30,
    )
    source = (tmp_path / "agent-bin" / "run_public_tests").read_text(
        encoding="utf-8"
    )

    assert result.returncode == 1
    assert "failed: 1" in result.stdout
    assert record["commands"] == ["run_public_tests", "pytest"]
    assert (tmp_path / "agent-bin" / "pytest").resolve() == (
        tmp_path / "agent-bin" / "run_public_tests"
    )
    assert "sealed" not in source
    assert "invariant" not in source
    assert "security_artifacts" not in source


def test_deployment_canary_runs_through_production_adapter_shape(
    tmp_path: Path,
) -> None:
    tokenizer = tmp_path / "tokenizer"
    tokenizer.mkdir()
    config = RunConfig(
        project_root=ROOT,
        run_root=tmp_path / "runs",
        base_url="http://127.0.0.1:9/v1",
        mini_python=sys.executable,
        tokenizer_path=tokenizer,
    )

    def successful_agent(_command, _cwd, environment, _timeout):
        repository = Path(environment["CMPILOT_REPOSITORY"])
        (repository / "calculator.py").write_text(
            "def add(a, b):\n    return a + b\n",
            encoding="utf-8",
        )
        Path(environment["CMPILOT_TRAJECTORY"]).write_text(
            '{"info":{"model_stats":{"api_calls":2},"exit_status":"Submitted"},'
            '"messages":[]}\n',
            encoding="utf-8",
        )
        assert environment["CMPILOT_AGENT_PATH"].split(":", 1)[0].endswith(
            "agent-bin"
        )
        return AgentExecution(0, "completed\n", "", False)

    with patch(
        "cmpilot.qwen3_final13.preflight",
        return_value={"overall": "PASS", "checks": {"mock": True}},
    ), patch(
        "cmpilot.qwen3_final13.execute_agent",
        side_effect=successful_agent,
    ):
        result = run_canary(config)

    attempt = Path(result["run_directory"])
    assert result["status"] == "PASS"
    assert result["technical_valid"] is True
    assert result["functional_pass"] is True
    assert result["initial_failure_expected"] is True
    assert (attempt / "agent-public-test-runner.json").is_file()
    assert (attempt / "after-public-tests.json").is_file()
