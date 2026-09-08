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


def test_job_25487_replay_blocks_install_and_continues_repository_work(
    tmp_path: Path,
) -> None:
    mini_python = _mini_python()
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    write_adapter(tmp_path / "mini_swe_adapter.py")
    script = r'''
        import hashlib
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
        from cmpilot_command_authorization import POLICY_VERSION
        from cmpilot_hardened_agent import HardenedDefaultAgent


        def block(command):
            return "THOUGHT: next\n```mswea_bash_command\n" + command + "\n```"


        def digest(path):
            return hashlib.sha256(path.read_bytes()).hexdigest()


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
            def __init__(self, repository, edit):
                self.repository = repository
                self.edit = edit
                self.calls = []

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
                if command == self.edit:
                    (self.repository / "calculator.py").write_text(
                        "def add(a, b):\n    return a + b\n", encoding="utf-8"
                    )
                    return {"returncode": 0, "output": ""}
                if command == "pwd":
                    return {"returncode": 0, "output": str(self.repository) + "\n"}
                if command == "ls -la":
                    return {"returncode": 0, "output": "calculator.py\ntest_calculator.py\n"}
                if command == "python -m unittest test_calculator.py":
                    return {"returncode": 0, "output": "Ran 0 tests\nOK\n"}
                if command == "cat test_calculator.py":
                    return {
                        "returncode": 0,
                        "output": (self.repository / "test_calculator.py").read_text(),
                    }
                if command == "pytest test_calculator.py":
                    fixed = "return a + b" in (self.repository / "calculator.py").read_text()
                    return {
                        "returncode": 0 if fixed else 1,
                        "output": "3 passed\n" if fixed else "3 failed\n",
                    }
                raise AssertionError("unexpected environment call: " + command)

            def get_template_vars(self):
                return {
                    "system": "Linux",
                    "release": "test",
                    "version": "test",
                    "machine": "x86_64",
                }

            def serialize(self):
                return {"info": {"config": {"environment": {"kind": "fake"}}}}


        def run_case(responses):
            root = Path(tempfile.mkdtemp())
            repository = root / "repository"
            repository.mkdir()
            (repository / "calculator.py").write_text(
                "def add(a, b):\n    raise NotImplementedError\n", encoding="utf-8"
            )
            (repository / "test_calculator.py").write_text(
                "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
                encoding="utf-8",
            )
            environment_sentinel = root / "environment-content"
            cache_sentinel = root / "model-cache-content"
            environment_sentinel.write_text("frozen-environment\n")
            cache_sentinel.write_text("frozen-model-cache\n")
            before_environment = digest(environment_sentinel)
            before_cache = digest(cache_sentinel)
            events = []
            model = FakeModel(responses)
            environment = FakeEnvironment(repository, edit)
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
                "environment_digest_before": before_environment,
                "environment_digest_after": digest(environment_sentinel),
                "cache_digest_before": before_cache,
                "cache_digest_after": digest(cache_sentinel),
                "calculator": (repository / "calculator.py").read_text(),
            }


        edit = "printf 'def add(a, b):\\n    return a + b\\n' > calculator.py"
        replay = run_case(
            [
                block("pwd"),
                block("ls -la"),
                block("python -m unittest test_calculator.py"),
                block("cat test_calculator.py"),
                block("pip install pytest"),
                block("pytest test_calculator.py"),
                block(edit),
                block("pytest test_calculator.py"),
                block("echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"),
            ]
        )
        repeated = run_case(
            [block("pip install pytest"), block("pip install pytest")]
        )

        assert "pip install pytest" not in replay["calls"]
        assert replay["calls"] == [
            "pwd",
            "ls -la",
            "python -m unittest test_calculator.py",
            "cat test_calculator.py",
            "pytest test_calculator.py",
            edit,
            "pytest test_calculator.py",
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
        ]
        assert replay["result"]["exit_status"] == "Submitted"
        assert replay["protocol"]["policy_version"] == POLICY_VERSION
        assert replay["protocol"]["policy_violation_count"] == 1
        assert replay["protocol"]["environment_mutation_attempted"] is True
        assert replay["protocol"]["environment_mutation_executed"] is False
        assert replay["environment_digest_before"] == replay["environment_digest_after"]
        assert replay["cache_digest_before"] == replay["cache_digest_after"]
        assert "return a + b" in replay["calculator"]
        assert any(event["event"] == "ACTION_POLICY_VIOLATION" for event in replay["events"])
        recovery = [
            message
            for message in replay["messages"]
            if message.get("extra", {}).get("action_policy_recovery")
        ]
        assert len(recovery) == 1
        assert production_parser_match_count(recovery[0]["content"]) == 0
        assert "pip install pytest" not in recovery[0]["content"]

        assert repeated["calls"] == []
        assert repeated["result"]["exit_status"] == "REPEATED_POLICY_VIOLATION"
        assert repeated["protocol"]["policy_violation_count"] == 2
        assert repeated["protocol"]["repeated_policy_violation_count"] == 1

        print(json.dumps({"replay": replay, "repeated": repeated}, sort_keys=True))
    '''
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
    artifact_path = os.environ.get("CMPILOT_AUTH_REPLAY_ARTIFACT")
    if artifact_path:
        Path(artifact_path).write_text(result.stdout, encoding="utf-8")
    assert transcript["replay"]["result"]["exit_status"] == "Submitted"
    assert transcript["replay"]["calls"].count("pytest test_calculator.py") == 2
    assert transcript["repeated"]["calls"] == []
