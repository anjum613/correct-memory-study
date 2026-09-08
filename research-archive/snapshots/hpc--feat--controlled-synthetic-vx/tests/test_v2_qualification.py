from pathlib import Path

import pytest

from cmpilot.v2_preflight import V2PreflightError
from cmpilot.v2_qualification import (
    CHECKS,
    assert_synthetic_scope,
    cpu_preflight,
    server_command,
)


ROOT = Path(__file__).parents[1]
QWEN = ROOT / "configs/v2/models/qwen2.5-coder-32b-instruct.json"


def test_study_family_paths_are_rejected() -> None:
    with pytest.raises(V2PreflightError, match="six-family"):
        assert_synthetic_scope(ROOT / "families/onnx-v1")


def test_server_command_is_exact_and_32k() -> None:
    command = server_command(QWEN, port=28080)
    assert command[command.index("--max-model-len") + 1] == "32768"
    assert command[command.index("--revision") + 1] == (
        "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
    )


def test_cpu_preflight_covers_full_checklist(tmp_path: Path) -> None:
    result = cpu_preflight(QWEN, tmp_path)
    assert tuple(result["checks"]) == CHECKS
    assert result["overall_status"] == "NOT_TESTED_NO_GPU"
    assert result["study_run_authorized"] is False
    for check in ("file_edit", "test_execution", "nonempty_patch"):
        assert result["checks"][check] == "PASS"
