from __future__ import annotations

import importlib.util
from pathlib import Path
import sys


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts/run_controlled_synthetic_final_13_codex_terra_medium.py"
)
SPEC = importlib.util.spec_from_file_location("final_codex_terra_runner", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
runner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runner
SPEC.loader.exec_module(runner)


def test_terra_medium_design_is_104_balanced_cells() -> None:
    matrix = runner.build_run_matrix(SCRIPT.parents[1])
    assert matrix["run_count"] == 104 == runner.EXPECTED_RUN_COUNT
    assert len({cell["run_id"] for cell in matrix["cells"]}) == 104
    counts: dict[tuple[str, str, str], int] = {}
    for cell in matrix["cells"]:
        key = (cell["family_id"], cell["condition"], cell["model_profile"])
        counts[key] = counts.get(key, 0) + 1
    assert set(counts.values()) == {2}
    assert len(counts) == 13 * 4


def test_only_terra_medium_is_selected() -> None:
    assert runner.MODEL_PROFILES == (
        {
            "key": "gpt-5.6-terra-medium",
            "model_id": "gpt-5.6-terra",
            "reasoning_effort": "medium",
        },
    )
    assert runner.PROTOCOL_ID == "controlled-synthetic-final-13-codex-terra-medium-v1"


def test_codex_invocation_uses_terra_medium_and_preserves_sessions() -> None:
    command = runner.codex_command(
        {
            "model_id": "gpt-5.6-terra",
            "model_profile": "gpt-5.6-terra-medium",
            "reasoning_effort": "medium",
        }
    )
    assert command[command.index("-m") + 1] == "gpt-5.6-terra"
    assert 'model_reasoning_effort="medium"' in command
    assert "--ephemeral" not in command
    assert "--json" in command
