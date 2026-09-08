from __future__ import annotations

from pathlib import Path

import pytest

from cmpilot.integrations.miniswe.action_protocol import (
    COMPLETION_SENTINEL,
    FORMAT_ERROR_TEMPLATE,
    INITIAL_SYSTEM_TEMPLATE,
    INSTANCE_TEMPLATE,
    INVALID_ACTION_TEMPLATE,
    PROTOCOL_LIMIT_MESSAGE,
    ProtocolErrorState,
    StagnationGuard,
    escape_action_syntax_for_prompt,
    evaluate_action_response,
    production_parser_match_count,
    prompt_match_report,
    protocol_result_dimensions,
    render_recovery_prompt,
)


ROOT = Path(__file__).parents[1]


def _block(command: str) -> str:
    return f"THOUGHT: next\n```mswea_bash_command\n{command}\n```"


def test_every_harness_prompt_obeys_production_parser_match_limits() -> None:
    task = (ROOT / "tasks" / "smoke_test" / "task.md").read_text(encoding="utf-8")
    prompts = {
        "initial_system": INITIAL_SYSTEM_TEMPLATE,
        "memory_free_instance": INSTANCE_TEMPLATE.replace("{{task}}", task),
        "format_error_recovery": FORMAT_ERROR_TEMPLATE,
        "invalid_content_recovery": INVALID_ACTION_TEMPLATE,
        "protocol_limit": PROTOCOL_LIMIT_MESSAGE,
        "realistic_recovery": render_recovery_prompt(
            event="INVALID_ACTION_CONTENT",
            action_count=1,
            validation_reason="exact placeholder",
        ),
    }

    report = prompt_match_report(prompts)

    assert report == {
        "format_error_recovery": 0,
        "initial_system": 1,
        "invalid_content_recovery": 0,
        "memory_free_instance": 0,
        "protocol_limit": 0,
        "realistic_recovery": 0,
    }


def test_observation_action_syntax_is_escaped_without_losing_raw_output() -> None:
    raw_output = "file content:\n" + _block("echo should-not-be-an-action")
    safe_observation = escape_action_syntax_for_prompt(raw_output)

    assert production_parser_match_count(raw_output) == 1
    assert production_parser_match_count(safe_observation) == 0
    assert "echo should-not-be-an-action" in safe_observation
    assert raw_output.endswith("```")


@pytest.mark.parametrize("action_count", [0, 2, 8])
def test_wrong_action_counts_never_select_or_execute_a_command(action_count: int) -> None:
    raw = (
        "plain malformed response"
        if action_count == 0
        else "\n".join(_block(f"echo {index}") for index in range(action_count))
    )
    state = ProtocolErrorState()
    shell_calls: list[str] = []

    result = evaluate_action_response(raw, state)
    if result.accepted:
        shell_calls.append(result.command or "")

    assert result.action_count == action_count
    assert result.accepted is False
    assert result.event == "INVALID_ACTION_FORMAT"
    assert shell_calls == []


@pytest.mark.parametrize(
    "command",
    [
        "",
        " \t ",
        "<action>",
        "<command>",
        "your_command_here",
        "anything",
        "<generic_placeholder>",
        "{{ unresolved }}",
        "bad\x00command",
        "bad\x01command",
    ],
)
def test_semantically_invalid_commands_never_reach_shell(command: str) -> None:
    state = ProtocolErrorState()
    shell_calls: list[str] = []

    result = evaluate_action_response(_block(command), state)
    if result.accepted:
        shell_calls.append(result.command or "")

    assert result.accepted is False
    assert result.event == "INVALID_ACTION_CONTENT"
    assert shell_calls == []


def test_three_distinct_format_errors_use_format_error_limit() -> None:
    state = ProtocolErrorState()

    results = [
        evaluate_action_response(f"malformed response {index}", state)
        for index in range(3)
    ]

    assert results[-1].termination_reason == "FORMAT_ERROR_LIMIT"
    assert state.consecutive_protocol_errors == 3


def test_three_distinct_semantic_errors_use_invalid_action_limit() -> None:
    state = ProtocolErrorState()

    results = [
        evaluate_action_response(_block(command), state)
        for command in ("<action>", "<command>", "anything")
    ]

    assert results[-1].termination_reason == "INVALID_ACTION_LIMIT"
    assert state.invalid_action_count == 3


def test_same_command_with_different_output_or_return_code_is_not_stagnant() -> None:
    guard = StagnationGuard()
    first = guard.record(
        command="pytest",
        repository_before="tree",
        repository_after="tree",
        returncode=1,
        observation="1 failed",
    )
    changed_output = guard.record(
        command="pytest",
        repository_before="tree",
        repository_after="tree",
        returncode=1,
        observation="2 failed",
    )
    changed_returncode = guard.record(
        command="pytest",
        repository_before="tree",
        repository_after="tree",
        returncode=0,
        observation="2 failed",
    )

    assert first.termination_reason is None
    assert changed_output.termination_reason is None
    assert changed_returncode.termination_reason is None


def test_completion_sentinel_is_exempt_from_stagnation() -> None:
    guard = StagnationGuard()

    first = guard.record(
        command=COMPLETION_SENTINEL,
        repository_before="tree",
        repository_after="tree",
        returncode=0,
        observation="",
    )
    second = guard.record(
        command=COMPLETION_SENTINEL,
        repository_before="tree",
        repository_after="tree",
        returncode=0,
        observation="",
    )

    assert first.termination_reason is None
    assert second.termination_reason is None


def test_safe_protocol_failure_is_not_infrastructure_or_harness_failure() -> None:
    result = protocol_result_dimensions(
        termination_reason="REPEATED_INVALID_ACTION",
        invalid_response_count=2,
        invalid_action_count=2,
        executed_action_count=0,
        repository_progress=False,
        functional_outcome="INCOMPLETE",
    )

    assert result["technical_validity"] == "PASS"
    assert result["protocol_safety_status"] == "PASS"
    assert result["model_format_status"] == "FAIL"
    assert result["failure_dimension"] == "semantic_invalid_action"
    assert result["functional_outcome"] == "INCOMPLETE"
