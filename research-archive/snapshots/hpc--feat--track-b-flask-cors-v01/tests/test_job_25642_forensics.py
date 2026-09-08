from __future__ import annotations

from pathlib import Path

import pytest

from cmpilot.job_25642_forensics import collect_job_25642_forensics


JOB = Path("/home/s224049759/run-artifacts/qwen32b-calculator/25642")


def test_job_25642_forensics_confirm_all_three_technical_defects() -> None:
    if not JOB.is_dir():
        pytest.skip("historical job-25642 artifacts are unavailable")

    result = collect_job_25642_forensics(JOB)

    context = result["request_context_overflow"]
    assert context["request_index"] == 15
    assert context["prompt_tokens"] == 3696
    assert context["configured_completion_allowance"] == 512
    assert context["possible_total_tokens"] == 4208
    assert context["context_limit"] == 4096
    assert context["http_status"] == 400
    assert context["trajectory_exit_status"] == "TransportHTTPError"
    editor = result["interactive_editor_bypass"]
    assert editor["commands"] == [
        "nano test_calculator.py",
        "vim test_calculator.py",
    ]
    assert editor["shell_execution_count"] == 2
    assert editor["protected_test_modified"] is False
    source = result["source_integrity_generation_failure"]
    assert source["generated_python_line_number"] == 1135
    assert "unterminated string literal" in source["syntax_error"]
    assert source["interpolated_value"] == "newline terminator U+000A"
    assert result["artifact_manifest_valid"] is True
    assert result["historical_artifacts_modified"] is False
