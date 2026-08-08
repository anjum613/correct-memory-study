from __future__ import annotations

import hashlib
from pathlib import Path
import sys

import pytest

from cmpilot.job_25692_forensics import (
    MODEL_TEST_COMMAND_CHOICE,
    classify_visible_test_source,
    collect_job_25692_forensics,
    run_visible_test_investigation,
)
from cmpilot.repository_manager import prepare_working_copy
from cmpilot.task_file_policy import calculator_task_policy


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "tasks/smoke_test/repository"
JOB_25692 = Path("/home/s224049759/run-artifacts/qwen32b-calculator/25692")
EXPECTED_TEST_HASH = "f36c3c3f38facdecb8c1c6318976738a16cd6f123d93f67136229ac3cfb759b7"


def test_visible_calculator_tests_are_pytest_style_and_frozen() -> None:
    test_path = SOURCE / "test_calculator.py"
    source = test_path.read_text(encoding="utf-8")
    classification = classify_visible_test_source(source)

    assert hashlib.sha256(test_path.read_bytes()).hexdigest() == EXPECTED_TEST_HASH
    assert classification == {
        "style": "pytest-style-top-level-functions",
        "top_level_test_functions": [
            "test_adds_positive_integers",
            "test_adds_opposite_integers",
            "test_adds_floats",
        ],
        "unittest_test_case_classes": [],
    }


def test_exact_job_25692_command_matrix_is_model_command_choice(
    tmp_path: Path,
) -> None:
    source_hash_before = hashlib.sha256(
        (SOURCE / "test_calculator.py").read_bytes()
    ).hexdigest()
    working_copy, _ = prepare_working_copy(
        SOURCE,
        destination=tmp_path / "working-copy",
        task_policy=calculator_task_policy(),
    )
    (working_copy / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n", encoding="utf-8", newline="\n"
    )

    result = run_visible_test_investigation(
        working_copy=working_copy,
        output_directory=tmp_path / "investigation",
        agent_python=Path(sys.executable),
        baseline_python=Path(sys.executable),
    )

    assert result["classification"] == MODEL_TEST_COMMAND_CHOICE
    assert result["fixture_correction_required"] is False
    assert result["unittest_zero_tests"] is True
    assert result["pytest_three_passed"] is True
    assert result["permissions_prevented_execution"] is False
    assert result["test_mode_before"] == "0400"
    assert result["test_mode_after"] == "0400"
    assert result["test_unchanged"] is True
    assert all(
        result["commands"][name]["returncode"] == 0
        for name in (
            "unittest-module",
            "unittest-module-python3",
            "unittest-discover",
            "baseline-pytest",
            "immutable-oracle-pytest",
        )
    )
    assert hashlib.sha256(
        (SOURCE / "test_calculator.py").read_bytes()
    ).hexdigest() == source_hash_before


def test_job_25692_retrospective_preserves_separate_dimensions() -> None:
    if not JOB_25692.is_dir():
        pytest.skip("historical job 25692 artifacts are unavailable")

    record = collect_job_25692_forensics(JOB_25692)

    assert record["finalizer_control_flow"]["potentially_unset_variables"] == [
        "POST_AGENT_FAILURE_COUNT"
    ]
    assert record["retrospective_capability"] == {
        "repository_solution_capability": "demonstrated",
        "authorized_calculator_patch": True,
        "allowed_patch_only": True,
        "immutable_oracle_passed": True,
        "protected_or_disallowed_modification": False,
        "agent_submitted_completion": False,
        "model_run_termination": "STAGNATION_LIMIT",
        "original_technical_validity": "fail",
        "original_result_rewritten": False,
    }
    assert "sha256-manifest.txt" in record["missing_finalizer_outputs"]
