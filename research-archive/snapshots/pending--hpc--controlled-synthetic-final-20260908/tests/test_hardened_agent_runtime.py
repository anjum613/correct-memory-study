from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

from cmpilot.mini_swe_adapter import write_adapter


ROOT = Path(__file__).parents[1]
DEFAULT_MINI_PY = Path("/home/s224049759/environments/mini-swe-agent-smoke/bin/python")


def _mini_python() -> Path:
    return Path(os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PY))


def test_hardened_agent_intercepts_actions_before_environment_execution(
    tmp_path: Path,
) -> None:
    mini_python = _mini_python()
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    write_adapter(tmp_path / "mini_swe_adapter.py")
    script = r"""
        import json
        import tempfile
        from pathlib import Path

        from minisweagent.exceptions import Submitted
        from minisweagent.models.utils.actions_text import parse_regex_actions

        from cmpilot_action_protocol import (
            ACTION_REGEX,
            FORMAT_ERROR_TEMPLATE,
            INITIAL_SYSTEM_TEMPLATE,
            INSTANCE_TEMPLATE,
            production_parser_match_count,
        )
        from cmpilot_hardened_agent import HardenedDefaultAgent


        def block(command):
            return "THOUGHT: next\n```mswea_bash_command\n" + command + "\n```"


        class FakeModel:
            def __init__(self, responses):
                self.responses = list(responses)
                self.requests = []

            def query(self, messages):
                self.requests.append(
                    [
                        {"role": message["role"], "content": message["content"]}
                        for message in messages
                    ]
                )
                content = self.responses.pop(0)
                actions = parse_regex_actions(
                    content,
                    action_regex=ACTION_REGEX,
                    format_error_template=FORMAT_ERROR_TEMPLATE,
                )
                return {
                    "role": "assistant",
                    "content": content,
                    "extra": {
                        "actions": actions,
                        "cost": 0.0,
                        "raw_response": {"content": content},
                        "request_sha256": "request",
                        "response_sha256": "response",
                    },
                }

            def format_message(self, **kwargs):
                return kwargs

            def format_observation_messages(self, message, outputs, template_vars=None):
                return [
                    {
                        "role": "user",
                        "content": "<returncode>"
                        + str(output["returncode"])
                        + "</returncode>\n<output>\n"
                        + output["output"]
                        + "</output>",
                        "extra": {
                            "raw_output": output["output"],
                            "returncode": output["returncode"],
                        },
                    }
                    for output in outputs
                ]

            def get_template_vars(self, **kwargs):
                return {}

            def serialize(self):
                return {"info": {"config": {"model": {"kind": "fake"}}}}


        class FakeEnvironment:
            def __init__(self, repository, *, outputs=None):
                self.repository = repository
                self.calls = []
                self.outputs = list(outputs or [])

            def execute(self, action, cwd="", timeout=None):
                command = action["command"]
                self.calls.append(command)
                if command == "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT":
                    raise Submitted(
                        {
                            "role": "exit",
                            "content": "Submitted",
                            "extra": {"exit_status": "Submitted", "submission": ""},
                        }
                    )
                if command == "printf fixed > calculator.py":
                    (self.repository / "calculator.py").write_text(
                        "fixed\n", encoding="utf-8"
                    )
                    return {"returncode": 0, "output": ""}
                if command == "ls":
                    return {"returncode": 0, "output": "calculator.py\n"}
                if command == "pytest":
                    source = (self.repository / "calculator.py").read_text(
                        encoding="utf-8"
                    )
                    return {
                        "returncode": 0 if source == "fixed\n" else 1,
                        "output": "3 passed\n" if source == "fixed\n" else "1 failed\n",
                    }
                if self.outputs:
                    return self.outputs.pop(0)
                return {"returncode": 0, "output": "ok\n"}

            def get_template_vars(self):
                return {
                    "system": "Linux",
                    "release": "test",
                    "version": "test",
                    "machine": "x86_64",
                }

            def serialize(self):
                return {"info": {"config": {"environment": {"kind": "fake"}}}}


        def run_case(responses, *, outputs=None):
            repository = Path(tempfile.mkdtemp())
            (repository / "calculator.py").write_text(
                "raise NotImplementedError\n", encoding="utf-8"
            )
            events = []
            model = FakeModel(responses)
            environment = FakeEnvironment(repository, outputs=outputs)
            agent = HardenedDefaultAgent(
                model,
                environment,
                repository=repository,
                event_sink=lambda event, **details: events.append(
                    {"event": event, **details}
                ),
                system_template=INITIAL_SYSTEM_TEMPLATE,
                instance_template=INSTANCE_TEMPLATE,
                step_limit=12,
                cost_limit=0,
                wall_time_limit_seconds=0,
                max_consecutive_format_errors=3,
            )
            result = agent.run("finish the calculator")
            return {
                "calls": environment.calls,
                "events": events,
                "messages": agent.messages,
                "protocol": agent.protocol_result(),
                "requests": model.requests,
                "result": result,
            }


        eight = "\n".join(block("echo " + str(index)) for index in range(8))
        recovery = run_case(
            [
                eight,
                block("<action>"),
                block("ls"),
                block("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"),
            ]
        )
        assert recovery["calls"] == [
            "ls",
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
        ]
        assert recovery["result"]["exit_status"] == "Submitted"
        assert recovery["protocol"]["invalid_response_count"] == 2
        assert recovery["protocol"]["invalid_action_count"] == 1
        assert recovery["protocol"]["executed_action_count"] == 2
        assert recovery["protocol"]["consecutive_protocol_errors"] == 0
        assert any(
            "calculator.py" in message["content"]
            for message in recovery["requests"][3]
            if message["role"] == "user"
        )
        assert all(
            production_parser_match_count(message["content"]) == 0
            for message in recovery["messages"]
            if message["role"] == "user"
            and message.get("extra", {}).get("protocol_recovery")
        )
        rejected_assistants = [
            message
            for message in recovery["messages"]
            if message["role"] == "assistant"
            and message.get("extra", {}).get("protocol_rejected")
        ]
        assert [message["content"] for message in rejected_assistants] == [
            eight,
            block("<action>"),
        ]
        assert rejected_assistants[1]["extra"]["rejected_command"] == "<action>"

        repeated_action = run_case([block("<action>"), block("<action>")])
        assert repeated_action["calls"] == []
        assert repeated_action["result"]["exit_status"] == "REPEATED_INVALID_ACTION"

        repeated_raw = run_case(["malformed", "malformed"])
        assert repeated_raw["calls"] == []
        assert repeated_raw["result"]["exit_status"] == "REPEATED_INVALID_RESPONSE"

        stagnation = run_case([block("ls"), block("ls")])
        assert stagnation["calls"] == ["ls", "ls"]
        assert stagnation["result"]["exit_status"] == "STAGNATION_LIMIT"
        assert len(stagnation["protocol"]["transitions"]) == 2

        after_edit = run_case(
            [
                block("pytest"),
                block("printf fixed > calculator.py"),
                block("pytest"),
                block("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"),
            ]
        )
        assert after_edit["calls"] == [
            "pytest",
            "printf fixed > calculator.py",
            "pytest",
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
        ]
        assert after_edit["result"]["exit_status"] == "Submitted"
        assert after_edit["protocol"]["termination_reason"] == "Submitted"

        print(
            json.dumps(
                {
                    "recovery": recovery,
                    "repeated_action": repeated_action,
                    "repeated_raw": repeated_raw,
                    "stagnation": stagnation,
                    "after_edit": after_edit,
                },
                sort_keys=True,
            )
        )
    """
    environment = {
        **os.environ,
        "HOME": str(tmp_path / "home"),
        "XDG_CONFIG_HOME": str(tmp_path / "home" / "config"),
        "MSWEA_SILENT_STARTUP": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(tmp_path),
    }
    result = subprocess.run(
        [str(mini_python), "-c", textwrap.dedent(script)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    transcript = json.loads(result.stdout)
    assert transcript["repeated_action"]["calls"] == []
    assert transcript["repeated_raw"]["calls"] == []
    assert transcript["stagnation"]["result"]["exit_status"] == "STAGNATION_LIMIT"
