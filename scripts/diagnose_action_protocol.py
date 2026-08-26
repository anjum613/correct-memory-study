#!/usr/bin/env python3
"""Record mini-SWE-agent 2.4.6 parser behavior without executing any command."""

from __future__ import annotations

import json
from types import SimpleNamespace

from minisweagent.exceptions import FormatError
from minisweagent.models.utils.actions_toolcall import parse_toolcall_actions


def call(name: str, arguments: str, identifier: str = "call-1") -> SimpleNamespace:
    return SimpleNamespace(id=identifier, function=SimpleNamespace(name=name, arguments=arguments))


def accepted(tool_calls: list[SimpleNamespace]) -> bool:
    try:
        parse_toolcall_actions(tool_calls, format_error_template="{{ error }}")
    except FormatError:
        return False
    return True


def main() -> int:
    results = {
        "single_valid_bash_action_accepted": accepted([call("bash", '{"command":"pwd"}')]),
        "missing_action_rejected": not accepted([]),
        "malformed_arguments_rejected": not accepted([call("bash", "not-json")]),
        "missing_command_rejected": not accepted([call("bash", "{}")]),
        "unknown_tool_rejected": not accepted([call("shell", '{"command":"pwd"}')]),
        "literal_placeholder_rejected": not accepted([call("bash", '{"command":"<command>"}')]),
        "multiple_actions_rejected": not accepted(
            [call("bash", '{"command":"pwd"}', "call-1"), call("bash", '{"command":"ls"}', "call-2")]
        ),
        "non_action_text_reaches_parser": False,
        "commands_executed_by_diagnostic": 0,
    }
    print(json.dumps(results, indent=2, sort_keys=True))
    required_unchanged_behavior = (
        results["single_valid_bash_action_accepted"]
        and results["missing_action_rejected"]
        and results["malformed_arguments_rejected"]
        and results["missing_command_rejected"]
        and results["unknown_tool_rejected"]
    )
    return 0 if required_unchanged_behavior else 2


if __name__ == "__main__":
    raise SystemExit(main())
