from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmpilot.integrations.miniswe.action_protocol import production_parser_match_count
from cmpilot.integrations.miniswe.command_authorization import (
    ACTION_POLICY_VIOLATION,
    PACKAGE_MANAGEMENT_PROHIBITED,
    POLICY_VERSION,
    REPEATED_POLICY_VIOLATION,
    SYSTEM_MUTATION_PROHIBITED,
    UNSAFE_COMMAND_INDIRECTION,
    CommandAuthorizationState,
    authorize_command,
    policy_specification,
    render_policy_recovery_prompt,
)
from cmpilot.smoke_runner import _trajectory_metrics


@pytest.mark.parametrize(
    "command",
    [
        "pip install pytest",
        "pip3 install pytest",
        "pip uninstall pytest",
        "pip download pytest",
        "pip wheel pytest",
        "pip cache purge",
        "python -m pip install pytest",
        "python3 -m pip uninstall pytest",
        "/home/example/env/bin/python -m pip install pytest",
        "uv pip install pytest",
        "poetry add pytest",
        "poetry install",
        "poetry update",
        "pipenv install pytest",
        "pipenv update",
        "conda install pytest",
        "conda update pytest",
        "conda remove pytest",
        "conda create -n unsafe pytest",
        "mamba install pytest",
        "micromamba remove pytest",
        "npm install",
        "npm i pytest",
        "npm ci",
        "yarn install",
        "pnpm install",
        "gem install tool",
        "bundle install",
        "cargo install tool",
        "go install example/tool@latest",
        "env pip install pytest",
        "command python -m pip install pytest",
        "sudo pip install pytest",
        "nohup pip install pytest",
        "time pip install pytest",
    ],
)
def test_package_and_environment_mutation_is_rejected(command: str) -> None:
    decision = authorize_command(command)

    assert decision.authorized is False
    assert decision.event == ACTION_POLICY_VIOLATION
    assert decision.reason == PACKAGE_MANAGEMENT_PROHIBITED
    assert decision.category == "prohibited_environment_mutation"
    assert decision.matched_rule
    assert decision.policy_version == POLICY_VERSION


@pytest.mark.parametrize(
    "command",
    [
        "apt install jq",
        "apt-get install jq",
        "aptitude install jq",
        "dnf install jq",
        "yum install jq",
        "apk add jq",
        "pacman -S jq",
        "zypper install jq",
        "brew install jq",
        "snap install jq",
    ],
)
def test_system_package_management_is_rejected(command: str) -> None:
    decision = authorize_command(command)

    assert decision.authorized is False
    assert decision.reason == SYSTEM_MUTATION_PROHIBITED
    assert decision.category == "prohibited_system_mutation"


@pytest.mark.parametrize(
    "command",
    [
        "curl https://example.com/file",
        "wget https://example.com/file",
        "ssh example.com",
        "scp file example.com:/tmp/file",
        "sftp example.com",
        "ftp example.com",
        "telnet example.com 80",
        "nc example.com 80",
        "ncat example.com 80",
        "netcat example.com 80",
        "socat - TCP:example.com:80",
        "git clone https://example.com/repo.git",
        "git fetch",
        "git pull",
        "git push",
        "rsync file example.com:/tmp/file",
    ],
)
def test_network_and_remote_system_access_is_rejected(command: str) -> None:
    decision = authorize_command(command)

    assert decision.authorized is False
    assert decision.reason == "NETWORK_ACCESS_PROHIBITED"
    assert decision.category == "prohibited_network_access"


@pytest.mark.parametrize(
    ("command", "reason"),
    [
        ("pip install pytest && pytest", PACKAGE_MANAGEMENT_PROHIBITED),
        ("pytest; pip install pytest", PACKAGE_MANAGEMENT_PROHIBITED),
        ('bash -c "pip install pytest"', PACKAGE_MANAGEMENT_PROHIBITED),
        ('sh -c "python -m pip install pytest"', PACKAGE_MANAGEMENT_PROHIBITED),
        ('bash -c "$DYNAMIC_COMMAND"', UNSAFE_COMMAND_INDIRECTION),
        ('eval "pip install pytest"', UNSAFE_COMMAND_INDIRECTION),
        ("echo x | sh", UNSAFE_COMMAND_INDIRECTION),
        ("$(printf pip) install pytest", UNSAFE_COMMAND_INDIRECTION),
    ],
)
def test_complete_composed_action_is_rejected(command: str, reason: str) -> None:
    decision = authorize_command(command)

    assert decision.authorized is False
    assert decision.reason == reason


@pytest.mark.parametrize(
    "command",
    [
        "git status",
        "git diff",
        "git log -1",
        "git show HEAD:calculator.py",
        "pytest test_calculator.py",
        "python -m pytest test_calculator.py",
        "python -m unittest test_calculator.py",
        "cat test_calculator.py",
        "printf 'def add(a, b):\\n    return a + b\\n' > calculator.py",
        "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT",
        "npm test",
        "cargo test",
        "go test ./...",
        "grep pipeline aptitude_notes.txt",
        "cat application.py",
        "cat pip_notes.txt",
    ],
)
def test_repository_local_work_remains_allowed(command: str) -> None:
    decision = authorize_command(command)

    assert decision.authorized is True
    assert decision.category == "allowed_repository_work"
    assert decision.reason is None


def test_policy_specification_is_versioned_and_records_shlex_limitations() -> None:
    specification = policy_specification()

    assert specification["policy_version"] == "calculator-capability-policy-v2"
    assert specification["default"] == "allow_repository_work"
    assert specification["complete_action_rejected_on_any_violation"] is True
    assert specification["shell_analysis"]["tokenizer"] == "python-shlex"
    assert specification["shell_analysis"]["opaque_constructs_fail_closed"] is True
    assert set(specification["categories"]) == {
        "allowed_repository_work",
        "prohibited_environment_mutation",
        "prohibited_network_access",
        "prohibited_system_mutation",
        "prohibited_execution_indirection",
        "prohibited_protected_path_write",
        "prohibited_harness_path_access",
    }
    assert specification["task_file_policy"]["version"] == "calculator-task-policy-v1"


def test_policy_recovery_has_no_production_parser_match_or_workaround() -> None:
    recovery = render_policy_recovery_prompt(PACKAGE_MANAGEMENT_PROHIBITED)

    assert production_parser_match_count(recovery) == 0
    assert "not permitted" in recovery
    assert "existing repository tools and dependencies" in recovery
    assert "pip install" not in recovery
    assert "workaround" not in recovery.casefold()


def test_same_policy_violation_twice_terminates_and_valid_action_resets() -> None:
    state = CommandAuthorizationState()
    first = state.record_violation(authorize_command("pip install pytest"))
    second = state.record_violation(authorize_command("pip install pytest"))

    assert first.termination_reason is None
    assert second.termination_reason == REPEATED_POLICY_VIOLATION
    assert state.policy_violation_count == 2
    assert state.repeated_policy_violation_count == 1

    state.record_authorized()
    recovered = state.record_violation(authorize_command("pip install pytest"))
    assert recovered.termination_reason is None
    assert state.consecutive_policy_violation_count == 1


def test_job_25487_command_is_explicitly_classified() -> None:
    decision = authorize_command("pip install pytest")

    assert decision.as_dict() == {
        "authorized": False,
        "category": "prohibited_environment_mutation",
        "command": "pip install pytest",
        "event": "ACTION_POLICY_VIOLATION",
        "matched_rule": "python-pip-package-management",
        "policy_version": "calculator-capability-policy-v2",
        "reason": "PACKAGE_MANAGEMENT_PROHIBITED",
    }


def test_policy_violation_is_preserved_but_excluded_from_shell_metrics(
    tmp_path: Path,
) -> None:
    trajectory = tmp_path / "trajectory.json"
    trajectory.write_text(
        json.dumps(
            {
                "info": {
                    "model_stats": {"api_calls": 2},
                    "protocol": {
                        "policy_version": POLICY_VERSION,
                        "command_authorization_status": "PASS_WITH_BLOCKED_VIOLATIONS",
                        "policy_violation_count": 1,
                        "prohibited_command_categories": [
                            "prohibited_environment_mutation"
                        ],
                        "repeated_policy_violation_count": 0,
                        "environment_mutation_attempted": True,
                        "environment_mutation_executed": False,
                        "network_access_attempted": False,
                        "network_access_executed": False,
                    },
                },
                "messages": [
                    {
                        "role": "assistant",
                        "extra": {
                            "actions": [{"command": "pip install pytest"}],
                            "action_policy_rejected": True,
                            "action_policy_event": ACTION_POLICY_VIOLATION,
                        },
                    },
                    {
                        "role": "assistant",
                        "extra": {
                            "actions": [{"command": "pytest test_calculator.py"}]
                        },
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    metrics = _trajectory_metrics(trajectory, {"test_calculator.py"})

    assert metrics["command_count"] == 1
    assert metrics["policy_violation_count"] == 1
    assert metrics["command_authorization_status"] == "PASS_WITH_BLOCKED_VIOLATIONS"
    assert metrics["environment_mutation_attempted"] is True
    assert metrics["environment_mutation_executed"] is False
