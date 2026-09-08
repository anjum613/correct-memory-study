from __future__ import annotations

import csv
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from cmpilot.final_experiment import (
    FinalExperimentError,
    aggregate_run_results,
    canonical_json_bytes,
    write_new_canonical_json,
)
from cmpilot.final_reporting import (
    CSV_COLUMNS,
    FinalReportingError,
    build_analysis_report,
    render_analysis_csv,
    write_analysis_outputs,
)
from tests.test_final_experiment import _build, _complete_attempt


ROOT = Path(__file__).parents[1]


def _complete_with_metrics(path: Path, run: dict[str, object]) -> None:
    """Create clearly synthetic terminal evidence with paper-table metrics."""

    _complete_attempt(path, run, witness=False)
    result_path = path / "result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result.update(
        {
            "action_count": 4,
            "elapsed_seconds": 12.5,
            "final_classification": "FUNCTIONALITY_PASS_WITNESS_FAIL",
            "job_id": "synthetic-job-17",
            "model_request_count": 7,
            "security_witness_result": {"complete": True, "pass": False},
            "token_usage": {
                "completion_tokens": 50,
                "prompt_tokens": 100,
                "total_tokens": 150,
            },
        }
    )
    result_path.write_bytes(canonical_json_bytes(result))


def test_analysis_report_keeps_incomplete_inventory_visible(tmp_path: Path) -> None:
    matrix = _build()
    report = build_analysis_report(matrix, tmp_path / "runs")

    assert report["run_count"] == 48
    assert report["completed_run_count"] == 0
    assert report["incomplete_run_count"] == 48
    assert report["achieved_family_count"] == 6
    assert report["family_count_policy"] == {"mode": "EXACT_SIX"}
    assert report["achieved_trust_category_coverage"] == ["G6"]
    assert {row["state"] for row in report["incomplete_runs"]} == {"ABSENT"}
    assert len(report["runs"]) == 48
    assert all(row["attempt_state"] == "ABSENT" for row in report["runs"])

    csv_payload = render_analysis_csv(report)
    rows = list(csv.DictReader(io.StringIO(csv_payload.decode("utf-8"))))
    assert tuple(rows[0]) == CSV_COLUMNS
    assert len(rows) == 48
    assert rows[0]["run_id"] == matrix["runs"][0]["run_id"]
    assert rows[0]["functionality_outcome"] == "UNAVAILABLE"


def test_analysis_report_extracts_only_objective_terminal_fields(tmp_path: Path) -> None:
    matrix = _build()
    run = matrix["runs"][0]
    attempt = tmp_path / "runs" / str(run["run_id"])
    _complete_with_metrics(attempt, run)

    first = build_analysis_report(matrix, tmp_path / "runs")
    second = build_analysis_report(matrix, tmp_path / "runs")
    assert first == second
    row = first["runs"][0]
    assert row["model"] == run["model_id"]
    assert row["model_revision"] == run["model_revision"]
    assert row["family"] == run["family_id"]
    assert row["condition"] == run["condition"]
    assert row["repetition"] == run["repetition"]
    assert row["seed"] == run["seed"]
    assert row["functionality_outcome"] == "PASS"
    assert row["security_witness_outcome"] == "FAIL"
    assert row["final_classification"] == "FUNCTIONALITY_PASS_WITNESS_FAIL"
    assert row["termination_reason"] == "NORMAL_COMPLETION"
    assert row["action_count"] == 4
    assert row["model_request_count"] == 7
    assert row["elapsed_time_seconds"] == 12.5
    assert row["prompt_tokens"] == 100
    assert row["completion_tokens"] == 50
    assert row["total_tokens"] == 150
    assert row["memory_provenance_identifier"] == run[
        "memory_provenance_manifest_sha256"
    ]
    assert row["task_revision"] == run["target_revision"]
    assert row["run_id"] == run["run_id"]
    assert row["slurm_job_id"] == "synthetic-job-17"
    # Backward-compatible inventory aliases remain objective and deterministic.
    assert row["witness_outcome"] == "FAIL"
    assert aggregate_run_results(matrix, tmp_path / "runs")["runs"][0][
        "witness_outcome"
    ] == "FAIL"


def test_require_complete_fails_before_writing_partial_table(tmp_path: Path) -> None:
    matrix = _build()
    with pytest.raises(FinalReportingError, match="requires every planned run"):
        build_analysis_report(
            matrix,
            tmp_path / "runs",
            require_complete=True,
        )


def test_paired_outputs_are_deterministic_and_exclusive(tmp_path: Path) -> None:
    report = build_analysis_report(_build(), tmp_path / "runs")
    first_json = tmp_path / "first/report.json"
    first_csv = tmp_path / "first/report.csv"
    second_json = tmp_path / "second/report.json"
    second_csv = tmp_path / "second/report.csv"

    first = write_analysis_outputs(first_json, first_csv, report)
    second = write_analysis_outputs(second_json, second_csv, report)
    assert first == second
    assert first_json.read_bytes() == second_json.read_bytes()
    assert first_csv.read_bytes() == second_csv.read_bytes()
    with pytest.raises(FinalExperimentError, match="refusing to overwrite"):
        write_analysis_outputs(first_json, first_csv, report)


def test_aggregation_cli_writes_json_and_csv_without_omitting_runs(
    tmp_path: Path,
) -> None:
    matrix_path = tmp_path / "matrix.json"
    matrix_sha256 = write_new_canonical_json(matrix_path, _build())
    output = tmp_path / "analysis.json"
    csv_output = tmp_path / "paper-table.csv"
    completed = subprocess.run(
        (
            sys.executable,
            str(ROOT / "scripts/aggregate_final_experiment.py"),
            str(matrix_path),
            str(tmp_path / "runs"),
            str(output),
            "--csv",
            str(csv_output),
            "--expected-matrix-sha256",
            matrix_sha256,
        ),
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["run_count"] == 48
    assert summary["completed_run_count"] == 0
    assert summary["incomplete_run_count"] == 48
    assert json.loads(output.read_text(encoding="utf-8"))["run_count"] == 48
    assert len(list(csv.DictReader(csv_output.open(encoding="utf-8")))) == 48
