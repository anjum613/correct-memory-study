from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cmpilot.integrations.miniswe.command_gateway import (
    CommandGatewayRejected,
    execute_controlled_command,
    parse_gateway_request,
)
from cmpilot.integrations.miniswe.filesystem_sandbox import SandboxedCommandResult
from cmpilot.task_file_policy import calculator_task_policy


@pytest.mark.parametrize(
    ("command", "route"),
    [
        ("git status", "git_gateway"),
        ("git status --short", "git_gateway"),
        ("git diff -- calculator.py", "git_gateway"),
        ("git log -1 --oneline", "git_gateway"),
        ("git show HEAD:calculator.py", "git_gateway"),
        ("sed -i 's/old/new/' calculator.py", "controlled_edit_gateway"),
        ("find . -type f", None),
    ],
)
def test_gateway_parser_accepts_only_justified_operations(
    command: str, route: str | None
) -> None:
    request = parse_gateway_request(
        command,
        repository=Path("/task"),
        writable_paths=("calculator.py",),
    )

    assert (None if request is None else request.route) == route


@pytest.mark.parametrize(
    "command",
    [
        "git config --list",
        "git grep value",
        "git fetch",
        "git status; cat calculator.py",
        "git diff --ext-diff",
        "git diff --textconv",
        "git diff --no-index left right",
        "git show --show-signature HEAD",
        "git show --output=calculator.py HEAD",
        "git --exec-path status",
        "sed -i 'e id' calculator.py",
        "sed -i 's/old/new/' test_calculator.py",
        "perl -i -pe 's/old/new/' calculator.py",
    ],
)
def test_gateway_parser_rejects_shell_escape_write_and_unsafe_flags(
    command: str,
) -> None:
    with pytest.raises(CommandGatewayRejected):
        parse_gateway_request(
            command,
            repository=Path("/task"),
            writable_paths=("calculator.py",),
        )


def test_model_command_environment_does_not_disclose_controller_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "calculator.py").write_text("value = 1\n", encoding="utf-8")
    evaluator_git = tmp_path / ".private-evaluator-git"
    evaluator_git.mkdir()
    home, temporary = tmp_path / "home", tmp_path / "tmp"
    home.mkdir()
    temporary.mkdir()
    captured: dict[str, Any] = {}

    def fake_sandbox(command: str, **kwargs: Any) -> SandboxedCommandResult:
        captured.update(kwargs)
        return SandboxedCommandResult(0, "ok\n", True, {"classification": "SANDBOX_ESTABLISHED"})

    monkeypatch.setattr(
        "cmpilot.integrations.miniswe.command_gateway.run_sandboxed_command",
        fake_sandbox,
    )
    result = execute_controlled_command(
        "cat calculator.py",
        repository=repository,
        evaluator_git_directory=evaluator_git,
        task_policy=calculator_task_policy(),
        environment={
            "PATH": "/usr/bin:/bin",
            "HOME": str(home),
            "TMPDIR": str(temporary),
            "PYTHONDONTWRITEBYTECODE": "1",
            "CMPILOT_EVALUATOR_GIT_DIR": str(evaluator_git),
            "CMPILOT_TRAJECTORY": str(tmp_path / "private-trajectory.json"),
            "UNRELATED_CONTROLLER_SECRET": "must-not-cross-boundary",
        },
        timeout=5,
        audit_path=tmp_path / "audit.jsonl",
    )

    assert result.returncode == 0
    assert captured["environment"] == {
        "PATH": "/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(temporary),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
