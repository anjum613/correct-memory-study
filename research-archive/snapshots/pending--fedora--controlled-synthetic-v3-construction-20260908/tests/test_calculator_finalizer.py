from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.calculator_finalizer import (
    FINALIZER_SHELL_STATUS_VARIABLES,
    MANDATORY_FINALIZATION_STAGES,
    OPERATIONAL_FINALIZATION_STAGES,
    TERMINATION_PATHS,
    CalculatorFinalizerError,
    initialize_finalizer_state,
    insert_legacy_shell_state_initialization,
    inspect_shell_finalizer_control_flow,
    load_finalizer_state,
    require_shell_finalizer_control_flow,
    run_total_finalization,
    validate_total_finalization_artifacts,
)
from cmpilot.finalizer_replay import run_job_25692_stagnation_replay


ROOT = Path(__file__).parents[1]
FINALIZER_FIXTURE = ROOT / "tests/fixtures/job_25692_finalizer_excerpt.sbatch"
STDERR_FIXTURE = ROOT / "tests/fixtures/job_25692_slurm.stderr"


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def _callbacks(artifact: Path, calls: list[str], *, fail: str | None = None):
    def stage(name: str, filename: str, value: dict[str, object]):
        def run() -> dict[str, object]:
            calls.append(name)
            _write_json(artifact / filename, value)
            if name == fail:
                raise RuntimeError(f"simulated {name} failure")
            return value

        return run

    return {
        "final_repository_capture": stage(
            "final_repository_capture",
            "final-repository-capture.json",
            {"complete": True, "changed_files": ["calculator.py"]},
        ),
        "patch_generation": stage(
            "patch_generation",
            "patch-generation.json",
            {"pass": True, "allowed": ["calculator.py"], "disallowed": []},
        ),
        "immutable_oracle": stage(
            "immutable_oracle",
            "immutable-oracle-result.json",
            {"pass": True, "passed": 3, "failed": 0},
        ),
        "source_integrity": stage(
            "source_integrity",
            "source-integrity.json",
            {"pass": True},
        ),
        "project_environment_cache_integrity": stage(
            "project_environment_cache_integrity",
            "environment-cache-integrity.json",
            {"pass": True},
        ),
        "shutdown": stage(
            "shutdown", "shutdown.json", {"pass": True, "complete": True}
        ),
        "scratch_cleanup": stage(
            "scratch_cleanup",
            "scratch-cleanup.json",
            {"pass": True, "complete": True},
        ),
        "performance_summary": stage(
            "performance_summary",
            "performance-input.json",
            {"pass": True, "elapsed_seconds": 1.25},
        ),
    }


def test_job_25692_exact_traceback_is_preserved() -> None:
    assert STDERR_FIXTURE.read_text() == (
        "/var/lib/slurm/slurmd/job25692/slurm_script: line 1196: "
        "POST_AGENT_FAILURE_COUNT: unbound variable\n"
    )


def test_job_25692_inventory_finds_only_the_uninitialized_counter() -> None:
    record = inspect_shell_finalizer_control_flow(FINALIZER_FIXTURE.read_text())

    assert record["potentially_unset_variables"] == [
        "POST_AGENT_FAILURE_COUNT"
    ]
    assert set(record["variables"]) == set(FINALIZER_SHELL_STATUS_VARIABLES)
    counter = record["variables"]["POST_AGENT_FAILURE_COUNT"]
    assert counter["initialization_lines"] == []
    assert counter["increment_lines"]
    assert counter["read_lines"]
    with pytest.raises(CalculatorFinalizerError, match="POST_AGENT_FAILURE_COUNT"):
        require_shell_finalizer_control_flow(FINALIZER_FIXTURE.read_text())


def test_legacy_counter_is_initialized_once_before_agent_execution() -> None:
    corrected = insert_legacy_shell_state_initialization(
        FINALIZER_FIXTURE.read_text()
    )
    record = require_shell_finalizer_control_flow(corrected)

    assert corrected.count("POST_AGENT_FAILURE_COUNT=0") == 1
    assert record["legacy_counter_initialized_before_agent"] is True
    assert record["potentially_unset_variables"] == []


def test_corrected_shell_counter_survives_set_u(tmp_path: Path) -> None:
    script = tmp_path / "counter.sh"
    script.write_text(
        "#!/usr/bin/bash\n"
        "set -euo pipefail\n"
        "POST_AGENT_FAILURE_COUNT=0\n"
        "ANALYSIS_STATUS=0\n"
        "if (( ANALYSIS_STATUS != 0 )); then\n"
        "  POST_AGENT_FAILURE_COUNT=$((POST_AGENT_FAILURE_COUNT - -1))\n"
        "fi\n"
        "printf '%s\\n' \"$POST_AGENT_FAILURE_COUNT\"\n"
    )

    completed = subprocess.run(
        ["/usr/bin/bash", str(script)], text=True, capture_output=True, check=False
    )

    assert completed.returncode == 0
    assert completed.stdout == "0\n"
    assert "unbound variable" not in completed.stderr


@pytest.mark.parametrize("termination_reason", TERMINATION_PATHS)
def test_every_model_termination_path_completes_total_finalization(
    tmp_path: Path, termination_reason: str
) -> None:
    artifact = tmp_path / termination_reason.casefold()
    artifact.mkdir()
    state_path = artifact / "finalizer-state.json"
    state = initialize_finalizer_state(state_path, run_id=termination_reason)
    assert state.post_agent_failure_count == 0
    assert set(state.stage_statuses) == set(MANDATORY_FINALIZATION_STAGES)
    assert set(state.stage_statuses.values()) == {"pending"}
    calls: list[str] = []
    technical_failure = termination_reason in {
        "ANALYZER_TECHNICAL_VIOLATION",
        "TRANSPORT_FAILURE",
    }
    normal = termination_reason == "NORMAL_COMPLETION"

    outcome = run_total_finalization(
        state_path=state_path,
        artifact_directory=artifact,
        termination_reason=termination_reason,
        callbacks=_callbacks(artifact, calls),
        success_label=("QWEN32B_CALCULATOR_PASS" if normal else "QWEN32B_CALCULATOR_MODEL_FAIL"),
        technical_failure_label="QWEN32B_CALCULATOR_TECHNICAL_FAIL",
        requested_exit_code=0 if normal else 3,
        initial_technical_validity=not technical_failure,
        classification_dimensions={
            "repository_solution_capability": "demonstrated"
        },
    )

    assert tuple(calls) == OPERATIONAL_FINALIZATION_STAGES
    validation = validate_total_finalization_artifacts(artifact)
    assert validation["pass"] is True
    assert outcome.state.final_exit_chosen_after_all_stages is True
    assert all(
        status != "pending" for status in outcome.state.stage_statuses.values()
    )
    assert (artifact / "result.json").is_file()
    assert (artifact / "classification.json").is_file()
    assert (artifact / "performance-summary.json").is_file()
    assert (artifact / "scratch-cleanup.json").is_file()
    assert (artifact / "sha256-manifest.txt").is_file()
    assert (artifact / "authoritative-result.txt").is_file()
    assert "unbound variable" not in json.dumps(outcome.as_dict())


def test_stage_failure_does_not_skip_later_finalization_stages(
    tmp_path: Path,
) -> None:
    artifact = tmp_path / "analyzer-failure"
    artifact.mkdir()
    state_path = artifact / "finalizer-state.json"
    initialize_finalizer_state(state_path, run_id="analyzer-failure")
    calls: list[str] = []

    outcome = run_total_finalization(
        state_path=state_path,
        artifact_directory=artifact,
        termination_reason="ANALYZER_TECHNICAL_VIOLATION",
        callbacks=_callbacks(
            artifact, calls, fail="final_repository_capture"
        ),
        success_label="QWEN32B_CALCULATOR_MODEL_FAIL",
        technical_failure_label="QWEN32B_CALCULATOR_TECHNICAL_FAIL",
        requested_exit_code=3,
        initial_technical_validity=False,
    )

    assert tuple(calls) == OPERATIONAL_FINALIZATION_STAGES
    assert outcome.state.stage_statuses["final_repository_capture"] == "failed"
    assert outcome.state.stage_statuses["immutable_oracle"] == "passed"
    assert outcome.state.stage_statuses["shutdown"] == "passed"
    assert outcome.state.stage_statuses["scratch_cleanup"] == "passed"
    assert outcome.state.stage_statuses["artifact_preservation"] == "passed"
    assert outcome.state.stage_statuses["manifest_validation"] == "passed"
    assert outcome.state.final_exit_code == 1


def test_finalizer_state_cannot_be_reused(tmp_path: Path) -> None:
    artifact = tmp_path / "once"
    artifact.mkdir()
    state_path = artifact / "finalizer-state.json"
    initialize_finalizer_state(state_path, run_id="once")
    run_total_finalization(
        state_path=state_path,
        artifact_directory=artifact,
        termination_reason="NORMAL_COMPLETION",
        callbacks=_callbacks(artifact, []),
        success_label="PASS",
        technical_failure_label="FAIL",
        requested_exit_code=0,
        initial_technical_validity=True,
    )

    with pytest.raises(CalculatorFinalizerError, match="already consumed"):
        run_total_finalization(
            state_path=state_path,
            artifact_directory=artifact,
            termination_reason="NORMAL_COMPLETION",
            callbacks=_callbacks(artifact, []),
            success_label="PASS",
            technical_failure_label="FAIL",
            requested_exit_code=0,
            initial_technical_validity=True,
        )

    persisted = load_finalizer_state(state_path)
    assert persisted.final_exit_chosen_after_all_stages is True


def test_exact_job_25692_stagnation_replay_is_totally_finalized(
    tmp_path: Path,
) -> None:
    result = run_job_25692_stagnation_replay(
        source_repository=ROOT / "tasks/smoke_test/repository",
        oracle_source=ROOT / "oracles/calculator/v1",
        output_directory=tmp_path / "replay",
        python=Path(sys.executable),
    )

    assert result["pass"] is True
    assert result["termination_reason"] == "STAGNATION_LIMIT"
    assert result["repository_solution_capability"] == "demonstrated"
    assert result["external_oracle"]["passed"] == 3
    assert result["external_oracle"]["failed"] == 0
    assert result["visible_test_investigation"]["classification"] == (
        "MODEL_TEST_COMMAND_CHOICE"
    )
    assert result["scratch_cleanup_complete"] is True
    assert result["artifact_validation"]["pass"] is True
