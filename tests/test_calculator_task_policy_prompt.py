from __future__ import annotations

from cmpilot.integrations.miniswe.action_protocol import (
    INITIAL_SYSTEM_TEMPLATE,
    production_parser_match_count,
)
from cmpilot.task_file_policy import (
    CALCULATOR_AGENT_POLICY_TEXT,
    CALCULATOR_TASK_POLICY_VERSION,
    calculator_task_policy,
)


def test_calculator_task_policy_is_explicit_and_versioned_for_the_agent() -> None:
    policy = calculator_task_policy()

    assert policy.version == CALCULATOR_TASK_POLICY_VERSION == "calculator-task-policy-v1"
    assert policy.writable_paths == ("calculator.py",)
    assert policy.readable_protected_paths == ("test_calculator.py",)
    assert policy.agent_visible_policy_text == CALCULATOR_AGENT_POLICY_TEXT
    assert policy.as_dict()["agent_visible_policy_text"] == CALCULATOR_AGENT_POLICY_TEXT


def test_agent_policy_states_permissions_without_solution_content() -> None:
    text = CALCULATOR_AGENT_POLICY_TEXT

    assert "Tests are read-only and must not be modified" in text
    assert "calculator.py may be modified" in text
    assert "test_calculator.py is read-only" in text
    assert "do not install packages" in text
    assert "Interactive terminal editors are not available" in text
    assert "noninteractive repository editing" in text
    assert "return a + b" not in text
    assert "def add" not in text
    assert production_parser_match_count(text) == 0


def test_initial_system_prompt_contains_policy_once_and_remains_parser_safe() -> None:
    assert INITIAL_SYSTEM_TEMPLATE.count("Task file policy: calculator-task-policy-v1") == 1
    assert INITIAL_SYSTEM_TEMPLATE.count("Only the task-authorized source file calculator.py") == 1
    assert production_parser_match_count(INITIAL_SYSTEM_TEMPLATE) == 1
