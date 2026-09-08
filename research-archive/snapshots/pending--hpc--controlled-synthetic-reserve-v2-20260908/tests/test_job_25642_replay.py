from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest

from cmpilot.external_calculator_oracle import (
    copy_immutable_oracle_bundle,
    run_external_calculator_oracle,
)
from cmpilot.mini_swe_adapter import write_adapter
from cmpilot.repository_manager import prepare_working_copy
from cmpilot.task_file_policy import calculator_task_policy


ROOT = Path(__file__).parents[1]
DEFAULT_MINI_PY = Path(
    "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
)
PINNED_TOKENIZER = Path(
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
    "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_exact_job_25642_combined_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mini_python = Path(os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PY))
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    repository, _ = prepare_working_copy(
        ROOT / "tasks" / "smoke_test" / "repository",
        destination=tmp_path / "working-copy",
        task_policy=calculator_task_policy(),
    )
    original_test_hash = _sha256(repository / "test_calculator.py")
    (tmp_path / "runtime").mkdir()
    write_adapter(tmp_path / "runtime" / "mini_swe_adapter.py")
    runtime = tmp_path / "runtime"
    trajectory = tmp_path / "trajectory.json"
    mini_result_path = tmp_path / "mini-replay.json"
    script = r'''
        import json
        import os
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
        from cmpilot_context_budget import (
            ExactQwenChatTokenCounter,
            calculate_request_budget,
        )
        from cmpilot_hardened_agent import HardenedDefaultAgent
        from cmpilot_openai_transport import normalize_messages


        def block(command):
            return "work\n```mswea_bash_command\n" + command + "\n```"


        sed_command = "sed -i 's/5/4/' test_calculator.py"
        unauthorized_test = "printf 'assert True\\n' > test_extra.py"
        python_indirection = (
            "python3 -c \"from pathlib import Path; "
            "Path('test_calculator.py').write_text('assert True\\\\n')\""
        )
        edit = "printf 'def add(a, b):\\n    return a + b\\n' > calculator.py"
        commands = [
            "ls -la",
            "pytest test_calculator.py",
            "cat test_calculator.py",
            sed_command,
            unauthorized_test,
            python_indirection,
            "nano test_calculator.py",
            "vim test_calculator.py",
            "pip install pytest",
            edit,
            "pytest test_calculator.py",
            "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
        ]


        class FakeModel:
            def __init__(self):
                self.responses = [block(command) for command in commands]
                self.requests = []
                self.budgets = []
                self.counter = ExactQwenChatTokenCounter(
                    Path(os.environ["PINNED_TOKENIZER"])
                )

            def query(self, messages):
                canonical, _ = normalize_messages(messages)
                budget = calculate_request_budget(
                    prompt_tokens=self.counter.count(canonical)
                )
                assert budget.http_request_allowed
                assert budget.total_possible_with_reserve <= 4096
                self.budgets.append(budget.as_dict())
                self.requests.append(canonical)
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
                    }
                    for output in outputs
                ]

            def get_template_vars(self, **kwargs):
                return {}

            def serialize(self):
                return {"info": {"config": {"model": {"kind": "fake"}}}}


        class FakeEnvironment:
            def __init__(self, repository):
                self.repository = repository
                self.calls = []

            def execute(self, action, cwd="", timeout=None):
                command = action["command"]
                self.calls.append(command)
                if command == "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT":
                    raise Submitted({
                        "role": "exit",
                        "content": "Submitted",
                        "extra": {"exit_status": "Submitted", "submission": ""},
                    })
                if command == "ls -la":
                    return {"returncode": 0, "output": "calculator.py\ntest_calculator.py\n"}
                if command == "cat test_calculator.py":
                    return {
                        "returncode": 0,
                        "output": (self.repository / "test_calculator.py").read_text(),
                    }
                if command == edit:
                    (self.repository / "calculator.py").write_text(
                        "def add(a, b):\n    return a + b\n", encoding="utf-8"
                    )
                    return {"returncode": 0, "output": ""}
                if command == "pytest test_calculator.py":
                    fixed = "return a + b" in (
                        self.repository / "calculator.py"
                    ).read_text()
                    return {
                        "returncode": 0 if fixed else 1,
                        "output": "3 passed\n" if fixed else "3 failed\n",
                    }
                raise AssertionError("prohibited command reached environment: " + command)

            def get_template_vars(self):
                return {
                    "system": "Linux",
                    "release": "test",
                    "version": "test",
                    "machine": "x86_64",
                }

            def serialize(self):
                return {"info": {"config": {"environment": {"kind": "fake"}}}}


        repository = Path(os.environ["REPOSITORY"])
        events = []
        model = FakeModel()
        environment = FakeEnvironment(repository)
        agent = HardenedDefaultAgent(
            model,
            environment,
            repository=repository,
            event_sink=lambda event, **details: events.append(
                {"event": event, **details}
            ),
            system_template=INITIAL_SYSTEM_TEMPLATE,
            instance_template=INSTANCE_TEMPLATE,
            output_path=Path(os.environ["TRAJECTORY"]),
            step_limit=15,
            cost_limit=0,
            wall_time_limit_seconds=0,
            max_consecutive_format_errors=3,
        )
        result = agent.run("implement the calculator task")
        recoveries = [
            message
            for message in agent.messages
            if message.get("extra", {}).get("action_policy_recovery")
        ]
        recovery_contents = [message["content"] for message in recoveries]
        for recovery in recovery_contents:
            assert production_parser_match_count(recovery) == 0
            assert any(
                recovery in message["content"]
                for request in model.requests
                for message in request
            )
        evidence = {
            "calls": environment.calls,
            "events": events,
            "protocol": agent.protocol_result(),
            "result": result,
            "request_budgets": model.budgets,
            "recovery_parser_matches": [
                production_parser_match_count(value)
                for value in recovery_contents
            ],
            "recovery_observations_propagated": len(recovery_contents),
            "commands": commands,
            "edit": edit,
            "sed_command": sed_command,
            "unauthorized_test": unauthorized_test,
            "python_indirection": python_indirection,
        }
        Path(os.environ["MINI_RESULT"]).write_text(
            json.dumps(evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    '''
    result = subprocess.run(
        [str(mini_python), "-c", textwrap.dedent(script)],
        cwd=ROOT,
        env={
            **os.environ,
            "HOME": str(tmp_path / "home"),
            "XDG_CONFIG_HOME": str(tmp_path / "home" / "config"),
            "MSWEA_SILENT_STARTUP": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONPATH": str(runtime),
            "PINNED_TOKENIZER": str(PINNED_TOKENIZER),
            "REPOSITORY": str(repository),
            "TRAJECTORY": str(trajectory),
            "MINI_RESULT": str(mini_result_path),
        },
        text=True,
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    evidence = json.loads(mini_result_path.read_text(encoding="utf-8"))

    allowed_calls = evidence["calls"]
    assert allowed_calls.count(evidence["edit"]) == 1
    assert "nano test_calculator.py" not in allowed_calls
    assert "vim test_calculator.py" not in allowed_calls
    assert "pip install pytest" not in allowed_calls
    assert evidence["sed_command"] not in allowed_calls
    assert evidence["unauthorized_test"] not in allowed_calls
    assert evidence["python_indirection"] not in allowed_calls
    assert evidence["recovery_parser_matches"] == [0] * 6
    assert evidence["recovery_observations_propagated"] == 6
    assert evidence["result"]["exit_status"] == "Submitted"
    assert all(
        budget["total_possible_with_reserve"] <= 4096
        for budget in evidence["request_budgets"]
    )
    assert trajectory.is_file()
    assert not (repository / "test_extra.py").exists()
    assert _sha256(repository / "test_calculator.py") == original_test_hash

    bundle = copy_immutable_oracle_bundle(
        ROOT / "oracles" / "calculator" / "v1",
        tmp_path / "immutable-oracle",
    )
    oracle = run_external_calculator_oracle(
        source_repository=ROOT / "tasks" / "smoke_test" / "repository",
        agent_repository=repository,
        oracle_bundle=bundle,
        destination=tmp_path / "validation-tree",
        artifact_directory=tmp_path / "oracle-artifacts",
    )
    assert (oracle.passed, oracle.failed, oracle.returncode) == (3, 0, 0)

    final_evidence = {
        **evidence,
        "package_install_shell_calls": allowed_calls.count("pip install pytest"),
        "nano_shell_calls": allowed_calls.count("nano test_calculator.py"),
        "vim_shell_calls": allowed_calls.count("vim test_calculator.py"),
        "protected_test_write_shell_calls": sum(
            command in allowed_calls
            for command in (
                evidence["sed_command"],
                evidence["unauthorized_test"],
                evidence["python_indirection"],
            )
        ),
        "calculator_edit_shell_calls": allowed_calls.count(evidence["edit"]),
        "visible_test_unchanged": True,
        "immutable_oracle_result": {"passed": oracle.passed, "failed": oracle.failed},
        "trajectory_preserved": trajectory.is_file(),
        "maximum_generated_request_size": max(
            budget["total_possible_with_reserve"]
            for budget in evidence["request_budgets"]
        ),
    }
    artifact = os.environ.get("CMPILOT_JOB25642_REPLAY_ARTIFACT")
    if artifact:
        Path(artifact).write_text(
            json.dumps(final_evidence, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
