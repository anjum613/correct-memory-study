import json
from pathlib import Path

import pytest

from cmpilot.qualification import canonical_json_bytes


ROOT = Path(__file__).parents[1]
RESULT_PATH = ROOT / "qualification/qwen36-v1/qualification-result.json"
REPORT_PATH = ROOT / "docs/qualification/qwen36-no-memory-v1-result.md"


def _result() -> dict:
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def test_qwen36_result_is_canonical_and_frozen() -> None:
    result = _result()

    assert RESULT_PATH.read_bytes() == canonical_json_bytes(result)
    assert result["model"] == {
        "dtype": "bfloat16",
        "id": "Qwen/Qwen3.6-27B",
        "revision": "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9",
        "tensor_parallel_size": 2,
    }
    assert result["scientific_freeze"]["sha256"] == (
        "7c8e22bcdd6d2e264ed205310b584df3643e5499e01e354b71779fc3fdcfca91"
    )
    assert result["seed_schedule"]["sha256"] == (
        "32849f701145306bff8f235747588726735125bf65beb5b37406a400803ab108"
    )
    assert result["suite_reference"]["sha256"] == (
        "2403982c3d3681e746d741b357b52a7fc4e3b8b97d7219a1b46fe26f3c9200cf"
    )
    assert result["submission_gate"]["sha256"] == (
        "7f4d1d59b66dbf1648c6c559688b4669381e37b10cbdb75289bdd730cee3ed66"
    )


def test_qwen36_primary_result_uses_predeclared_competence_rule() -> None:
    result = _result()
    tasks = result["primary_tasks"]

    assert [task["job_id"] for task in tasks] == [
        "26053",
        "26205",
        "26206",
        "26207",
        "26208",
    ]
    assert [task["seed"] for task in tasks] == [
        1602021252,
        1920009210,
        924300403,
        856051484,
        1086801435,
    ]
    for task in tasks:
        expected = bool(
            task["technical_validity"]
            and task["authorized_patch_present"]
            and task["immutable_oracle"]["pass"]
            and task["protected_file_integrity"]
            and not task["prohibited_command_executed"]
        )
        assert task["repository_competence"] is expected
        assert task["artifact_manifest"]["verified"] is True
        assert task["controller_attestation"]["pass"] is True
        assert task["http_statuses"] == {"200": 15}
        assert task["server_shutdown_pass"] is True
        assert task["reasoning"]["canonical_history_contaminated"] is False
        assert task["treatment"] == "no_memory"

    assert [task["repository_competence"] for task in tasks] == [
        True,
        True,
        False,
        True,
        True,
    ]
    assert result["competence_count"] == {
        "failed": 1,
        "passed": 4,
        "technically_evaluable_primary_tasks": 5,
    }
    assert result["final_qualification_decision"] == "PASS"
    assert result["reserves_required"] is False
    assert result["reserve_tasks"] == []


def test_qwen36_aggregate_metrics_and_audit_history_are_separate() -> None:
    result = _result()

    assert result["technical_invalid_run_count"] == 5
    assert all(
        row["qualification_scored"] is False
        and row["repository_competence"] == "NOT_SCORED"
        for row in result["technical_invalid_history"]
    )
    assert result["completion_sentinel"] == {"count": 0, "rate": 0.0, "total": 5}
    assert result["termination_reason_distribution"] == {"LimitsExceeded": 5}
    assert result["prohibited_commands"] == {
        "attempt_event_count": 26,
        "execution_count": 0,
        "tasks_with_attempts": 5,
    }
    assert result["protected_file_violation_count"] == 0
    assert result["totals"] | {"agent_wall_time_seconds": None} == {
        "agent_requests": 75,
        "agent_wall_time_seconds": None,
        "completion_tokens": 9093,
        "model_tokens": 109113,
        "prompt_tokens": 100020,
        "slurm_elapsed_seconds": 1938,
    }
    assert result["totals"]["agent_wall_time_seconds"] == pytest.approx(
        637.6176476106048
    )
    assert result["reasoning_tokens"] == {
        "separately_available": False,
        "total": None,
    }


def test_qwen36_report_scopes_the_pass_to_engineering_qualification() -> None:
    result = _result()
    report = REPORT_PATH.read_text(encoding="utf-8")

    assert result["scientific_hypothesis_tested"] is False
    assert result["synthetic_memory_smoke"] == {
        "authorized_by_qualification_pass": True,
        "gpu_run_submitted": False,
        "status_at_qualification_record": "AUTHORIZED_FOR_CPU_PREPARATION",
    }
    assert "Decision: **PASS** (4/5" in report
    assert "Reserve tasks were not run" in report
    assert "does not test or support" in report
    assert "No memory-treatment GPU run" in report
