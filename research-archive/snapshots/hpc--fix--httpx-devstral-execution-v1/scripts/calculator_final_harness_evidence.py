#!/usr/bin/env python3
"""Generate deterministic context/editor/prompt evidence without HTTP or a model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from cmpilot.integrations.miniswe.action_protocol import production_parser_match_count
from cmpilot.integrations.miniswe.command_authorization import (
    INTERACTIVE_EDITOR_PROHIBITED,
    authorize_command,
    render_policy_recovery_prompt,
)
from cmpilot.integrations.miniswe.context_budget import (
    ContextBudgetExhausted,
    ExactQwenChatTokenCounter,
    calculate_request_budget,
)
from cmpilot.task_file_policy import calculator_task_policy


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request-fixture", type=Path, required=True)
    parser.add_argument("--tokenizer", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    arguments = build_parser().parse_args()
    fixture = json.loads(arguments.request_fixture.read_text(encoding="utf-8"))
    counter = ExactQwenChatTokenCounter(arguments.tokenizer)
    prompt_tokens = counter.count(fixture["messages"])
    guarded = calculate_request_budget(prompt_tokens=prompt_tokens)
    exhausted = calculate_request_budget(prompt_tokens=4001)
    if exhausted.http_request_allowed:
        raise AssertionError("context-exhaustion fixture was unexpectedly allowed")
    exhaustion = ContextBudgetExhausted(exhausted)
    editor_commands = (
        "nano test_calculator.py",
        "vim test_calculator.py",
        "/usr/bin/vim test_calculator.py",
        "env vim test_calculator.py",
        "command nano test_calculator.py",
        "/usr/bin/env nvim calculator.py",
    )
    editor_decisions = [authorize_command(command).as_dict() for command in editor_commands]
    if any(decision["authorized"] for decision in editor_decisions):
        raise AssertionError("an interactive editor passed authorization")
    if any(
        decision["reason"] != INTERACTIVE_EDITOR_PROHIBITED
        for decision in editor_decisions
    ):
        raise AssertionError("an interactive editor received the wrong classification")
    policy = calculator_task_policy()
    evidence = {
        "schema": "calculator-final-harness-evidence-v1",
        "context_budget": guarded.as_dict(),
        "context_exhaustion": exhaustion.artifact_record(),
        "context_exhaustion_http_calls": 0,
        "exact_fixture_prompt_tokens_match": (
            prompt_tokens == fixture["observed_prompt_tokens"] == 3696
        ),
        "maximum_emitted_request_tokens": guarded.emitted_request_token_ceiling,
        "maximum_with_safety_reserve": guarded.total_possible_with_reserve,
        "tokenizer": counter.identity,
        "interactive_editor_decisions": editor_decisions,
        "interactive_editor_shell_calls": 0,
        "interactive_editor_recovery_parser_matches": production_parser_match_count(
            render_policy_recovery_prompt(INTERACTIVE_EDITOR_PROHIBITED)
        ),
        "task_policy": policy.as_dict(),
        "task_policy_parser_matches": production_parser_match_count(
            policy.agent_visible_policy_text
        ),
    }
    required = (
        guarded.http_request_allowed
        and guarded.total_possible_with_reserve <= 4096
        and evidence["maximum_emitted_request_tokens"] <= 4096
        and evidence["exact_fixture_prompt_tokens_match"]
        and evidence["interactive_editor_recovery_parser_matches"] == 0
        and evidence["task_policy_parser_matches"] == 0
        and exhaustion.artifact_record()["http_request_sent"] is False
    )
    evidence["pass"] = bool(required)
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True))
    return 0 if evidence["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
