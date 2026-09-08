import json
from pathlib import Path

from cmpilot.qualification import canonical_json_bytes


ROOT = Path(__file__).parents[1]
RESULT_PATH = ROOT / "qualification/qwen32b-v1/qualification-result.json"
REPORT_PATH = ROOT / "docs/qualification/qwen32b-no-memory-v1-result.md"


def _result() -> dict:
    return json.loads(RESULT_PATH.read_text(encoding="utf-8"))


def test_qualification_result_is_canonical_and_uses_frozen_identity() -> None:
    result = _result()

    assert RESULT_PATH.read_bytes() == canonical_json_bytes(result)
    assert result["model"] == {
        "id": "Qwen/Qwen2.5-Coder-32B-Instruct",
        "revision": "381fc969f78efac66bc87ff7ddeadb7e73c218a7",
    }
    assert result["frozen_harness_commit"] == (
        "ba039a0eaddc358d6b7174260c3b3c36169c44c0"
    )
    assert result["runtime_fix_commit"] == (
        "b96e15c51eaa6db8a2deefbcd181c32ae34c0170"
    )
    assert result["freeze_manifest"]["sha256"] == (
        "d828512fb206e157eb99ac0a1929b5633f3a2a1b1a30693a4a4d2f193deea0c1"
    )
    assert result["suite_manifest"]["sha256"] == (
        "67a97e7ec0452907d80da681b128021d65a9205664ce7ff6be90944e92ba9c48"
    )


def test_primary_dimensions_apply_the_predeclared_competence_rule() -> None:
    result = _result()
    tasks = result["primary_tasks"]

    assert [task["job_id"] for task in tasks] == [
        "25913",
        "25914",
        "25915",
        "25920",
        "25921",
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
        assert task["finalizer_pass"] is True
        assert task["treatment"] == "no_memory"

    assert [task["repository_competence"] for task in tasks] == [
        True,
        True,
        False,
        False,
        False,
    ]
    assert result["competence_count"]["passed"] == 2
    assert result["final_qualification_decision"] == "FAIL"
    assert result["reserves_required"] is False
    assert result["reserve_tasks"] == []


def test_technical_invalid_history_and_agent_behavior_stay_separate() -> None:
    result = _result()

    assert result["technical_invalid_run_count"] == 1
    assert result["technical_rerun_linkage"] == {"25908": "25913"}
    assert result["technical_invalid_history"][0][
        "repository_competence_scored"
    ] is False
    assert result["completion_sentinel"] == {"count": 0, "rate": 0.0, "total": 5}
    assert result["termination_reason_distribution"] == {
        "LimitsExceeded": 3,
        "STAGNATION_LIMIT": 2,
    }
    assert result["protected_file_violation_count"] == 0
    assert result["prohibited_commands"] == {
        "attempt_event_count": 19,
        "execution_count": 0,
        "tasks_with_attempts": 3,
    }


def test_failed_qualification_does_not_prepare_treatment_infrastructure() -> None:
    result = _result()
    report = REPORT_PATH.read_text(encoding="utf-8")

    assert result["scientific_hypothesis_tested"] is False
    assert result["synthetic_memory_smoke_prepared"] is False
    assert "Decision: **FAIL**" in report
    assert "No reserve task was submitted" in report
    assert "synthetic memory-treatment smoke infrastructure was not prepared" in report
    assert "does not test or support" in report
