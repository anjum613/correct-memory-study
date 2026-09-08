from __future__ import annotations

from pathlib import Path

import pytest

from cmpilot.v2_prompting import (
    MEMORY_WRAPPER_END,
    MEMORY_WRAPPER_START,
    NO_MEMORY,
    SOURCE_CORRECT_MEMORY,
    build_initial_prompt,
    wrapper_leakage_findings,
)
from cmpilot.v2_task_completion import audit_completion_identifiability


ROOT = Path(__file__).parents[1]
FAMILIES = ("mcp-pinot-v1", "onnx-v1", "axios-v1", "aim-v1", "httpx-v1", "djoser-v1")


@pytest.mark.parametrize("family", FAMILIES)
def test_conditions_differ_only_by_neutral_memory_availability(family: str) -> None:
    root = ROOT / "families" / family
    no_memory = build_initial_prompt(root, NO_MEMORY)
    memory = build_initial_prompt(root, SOURCE_CORRECT_MEMORY)
    assert no_memory.messages[0] == memory.messages[0]
    assert no_memory.task_text == memory.task_text
    assert no_memory.memory_text is None
    assert memory.memory_text
    assert MEMORY_WRAPPER_START not in no_memory.rendered_task
    assert MEMORY_WRAPPER_START in memory.rendered_task
    assert memory.rendered_task.endswith(MEMORY_WRAPPER_END + "\n")
    assert no_memory.rendered_task == no_memory.task_text.rstrip() + "\n"


def test_memory_wrapper_has_no_security_or_historical_cue() -> None:
    assert wrapper_leakage_findings() == []


@pytest.mark.parametrize("family", FAMILIES)
def test_frozen_no_change_reference_makes_completion_matrix_unidentifiable(family: str) -> None:
    result = audit_completion_identifiability(ROOT / "families" / family)
    assert result.faithful_application == "NO_CHANGE_BASELINE"
    assert result.untouched_and_faithful_same_state is True
    assert result.identifiable_from_final_state is False
    assert result.blocker
