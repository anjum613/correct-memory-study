from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def _protocol():
    return importlib.import_module("cmpilot.integrations.miniswe.action_protocol")


def _block(command: str) -> str:
    return f"THOUGHT: next step\n```mswea_bash_command\n{command}\n```"


def _execute_if_accepted(raw: str, state, shell_calls: list[str]):
    protocol = _protocol()
    result = protocol.evaluate_action_response(raw, state)
    if result.accepted:
        shell_calls.append(result.command)
        state.record_valid_action()
    return result


def test_eight_actions_are_rejected_without_a_shell_call() -> None:
    protocol = _protocol()
    raw = "\n".join(_block(f"echo {index}") for index in range(8))
    shell_calls: list[str] = []

    result = _execute_if_accepted(raw, protocol.ProtocolErrorState(), shell_calls)

    assert result.action_count == 8
    assert result.event == "INVALID_ACTION_FORMAT"
    assert result.accepted is False
    assert shell_calls == []


def test_action_placeholder_is_rejected_without_a_shell_call() -> None:
    protocol = _protocol()
    shell_calls: list[str] = []

    result = _execute_if_accepted(
        _block("<action>"), protocol.ProtocolErrorState(), shell_calls
    )

    assert result.event == "INVALID_ACTION_CONTENT"
    assert result.rejected_command == "<action>"
    assert result.accepted is False
    assert shell_calls == []


def test_repeated_action_placeholder_terminates_within_two_responses() -> None:
    protocol = _protocol()
    state = protocol.ProtocolErrorState()
    shell_calls: list[str] = []

    first = _execute_if_accepted(_block("<action>"), state, shell_calls)
    second = _execute_if_accepted(_block("<action>"), state, shell_calls)

    assert first.termination_reason is None
    assert second.termination_reason == "REPEATED_INVALID_ACTION"
    assert state.invalid_action_count == 2
    assert shell_calls == []


def test_realistic_recovery_prompt_has_zero_production_parser_matches() -> None:
    protocol = _protocol()

    rendered = protocol.render_recovery_prompt(
        event="INVALID_ACTION_CONTENT",
        action_count=1,
        validation_reason="exact placeholder",
    )

    assert protocol.production_parser_match_count(rendered) == 0
    assert "exactly one concrete command" in rendered.lower()


def test_valid_ls_executes_once_and_observation_reaches_next_request() -> None:
    protocol = _protocol()
    state = protocol.ProtocolErrorState()
    shell_calls: list[str] = []
    messages = [{"role": "user", "content": "inspect the repository"}]

    result = _execute_if_accepted(_block("ls"), state, shell_calls)
    assert result.accepted is True
    messages.append({"role": "assistant", "content": result.raw_response})
    messages.append({"role": "user", "content": "<output>calculator.py</output>"})
    next_request = [dict(message) for message in messages]

    assert shell_calls == ["ls"]
    assert "calculator.py" in next_request[-1]["content"]
    assert all(set(message) == {"role", "content"} for message in next_request)


def test_identical_stagnant_transition_terminates_on_second_execution(
    tmp_path: Path,
) -> None:
    protocol = _protocol()
    (tmp_path / "calculator.py").write_text("value = 1\n", encoding="utf-8")
    tree_hash = protocol.repository_hash(tmp_path)
    guard = protocol.StagnationGuard()

    first = guard.record(
        command="ls",
        repository_before=tree_hash,
        repository_after=tree_hash,
        returncode=0,
        observation="calculator.py\n",
    )
    second = guard.record(
        command="ls",
        repository_before=tree_hash,
        repository_after=tree_hash,
        returncode=0,
        observation="calculator.py\n",
    )

    assert first.termination_reason is None
    assert second.termination_reason == "STAGNATION_LIMIT"
    assert first.fingerprint == second.fingerprint


def test_repeated_pytest_after_repository_edit_is_permitted(tmp_path: Path) -> None:
    protocol = _protocol()
    source = tmp_path / "calculator.py"
    source.write_text("raise NotImplementedError\n", encoding="utf-8")
    before_edit = protocol.repository_hash(tmp_path)
    guard = protocol.StagnationGuard()

    first = guard.record(
        command="pytest",
        repository_before=before_edit,
        repository_after=before_edit,
        returncode=1,
        observation="1 failed\n",
    )
    source.write_text("def add(a, b): return a + b\n", encoding="utf-8")
    after_edit = protocol.repository_hash(tmp_path)
    second = guard.record(
        command="pytest",
        repository_before=after_edit,
        repository_after=after_edit,
        returncode=0,
        observation="3 passed\n",
    )

    assert first.termination_reason is None
    assert second.termination_reason is None
    assert first.fingerprint != second.fingerprint


@pytest.mark.parametrize(
    "command",
    [
        "",
        "   \t",
        "<action>",
        "<command>",
        "your_command_here",
        "anything",
        "<replace_this>",
        "{{ unresolved }}",
        "printf 'bad\x00command'",
        "printf 'bad\x07command'",
    ],
)
def test_semantic_placeholders_and_controls_are_rejected(command: str) -> None:
    protocol = _protocol()

    validation = protocol.validate_action_content(command)

    assert validation.valid is False
    assert validation.reason


@pytest.mark.parametrize(
    "command",
    [
        "ls",
        "printf '%s\\n' 'quoted value' | sed -n '1p'",
        "printf x > result.txt",
        "printf 'one\\ntwo\\n'",
        "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
    ],
)
def test_legitimate_shell_content_remains_valid(command: str) -> None:
    protocol = _protocol()

    validation = protocol.validate_action_content(command)

    assert validation.valid is True
    assert validation.command == command.strip()


def test_repeated_identical_malformed_response_terminates_safely() -> None:
    protocol = _protocol()
    state = protocol.ProtocolErrorState()
    raw = "no fenced action here"

    first = protocol.evaluate_action_response(raw, state)
    second = protocol.evaluate_action_response(raw, state)

    assert first.termination_reason is None
    assert second.termination_reason == "REPEATED_INVALID_RESPONSE"
    assert state.invalid_response_count == 2


def test_valid_action_resets_consecutive_protocol_error_counter() -> None:
    protocol = _protocol()
    state = protocol.ProtocolErrorState()

    protocol.evaluate_action_response("no action", state)
    valid = protocol.evaluate_action_response(_block("ls"), state)

    assert valid.accepted is True
    state.record_valid_action()
    assert state.consecutive_protocol_errors == 0
