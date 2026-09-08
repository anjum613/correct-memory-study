from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cmpilot.integrations.miniswe.command_authorization import authorize_command
from cmpilot.integrations.miniswe.command_gateway import (
    CommandGatewayRejected,
    execute_controlled_command,
)
from cmpilot.repository_manager import (
    evaluator_git_dir,
    final_patch,
    git,
    prepare_working_copy,
)
from cmpilot.task_file_policy import calculator_task_policy


def _prepare_repository(
    tmp_path: Path,
    *,
    git_alias: bool = False,
    extra_files: dict[str, str] | None = None,
) -> tuple[Path, str]:
    source = tmp_path / "source"
    source.mkdir()
    (source / "calculator.py").write_text(
        "def add(a, b):\n    raise NotImplementedError\n", encoding="utf-8"
    )
    (source / "test_calculator.py").write_text(
        "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    for relative, contents in (extra_files or {}).items():
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    if git_alias:
        (source / "git-alias").symlink_to(".git")
    return prepare_working_copy(
        source,
        destination=tmp_path / "repository",
        task_policy=calculator_task_policy(),
    )


def _run_model_command(repository: Path, command: str):
    agent_home = repository.parent / "agent-home"
    agent_tmp = repository.parent / "agent-tmp"
    agent_home.mkdir(exist_ok=True)
    agent_tmp.mkdir(exist_ok=True)
    return execute_controlled_command(
        command,
        repository=repository,
        evaluator_git_directory=evaluator_git_dir(repository),
        task_policy=calculator_task_policy(),
        environment={
            "HOME": str(agent_home),
            "PATH": f"{Path(os.sys.executable).parent}:/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_ADDOPTS": "-p no:cacheprovider",
            "TMPDIR": str(agent_tmp),
        },
        timeout=10,
        audit_path=repository.parent / "controlled-command-audit.jsonl",
    )


@pytest.mark.parametrize(
    "command",
    [
        "cat .git/config",
        "ls ./.git",
        "find .git -type f",
        "stat nested/../.git/HEAD",
        "cat ../repository/.git/config",
        "printf '%s\\n' .git/*",
        "rm .git/HEAD",
        "find . -exec cat {} \\;",
    ],
)
def test_literal_git_access_and_dynamic_execution_are_rejected(
    command: str,
) -> None:
    assert authorize_command(command).authorized is False


def test_absolute_git_access_is_rejected(tmp_path: Path) -> None:
    repository, _ = _prepare_repository(tmp_path)

    assert authorize_command(f"cat {repository}/.git/config").authorized is False


@pytest.mark.parametrize(
    "command", ["find . -type f -print", "ls -R .", "ls -Ra ."]
)
def test_broad_repository_enumeration_does_not_disclose_git_metadata(
    tmp_path: Path, command: str
) -> None:
    repository, _ = _prepare_repository(tmp_path)

    assert authorize_command(command).authorized is True
    execution = _run_model_command(repository, command)

    assert execution.isolation_established is True
    assert execution.returncode == 0
    assert ".git" not in execution.output
    assert evaluator_git_dir(repository).is_dir()


def test_recursive_repository_read_does_not_reach_git_metadata(
    tmp_path: Path,
) -> None:
    repository, _ = _prepare_repository(tmp_path)
    command = "grep -R repositoryformatversion ."

    assert authorize_command(command).authorized is True
    execution = _run_model_command(repository, command)

    assert execution.isolation_established is True
    assert "repositoryformatversion" not in execution.output
    assert ".git" not in execution.output


def test_symlink_alias_cannot_read_git_metadata(tmp_path: Path) -> None:
    repository, _ = _prepare_repository(tmp_path, git_alias=True)
    command = "cat git-alias/config"

    assert authorize_command(command).authorized is True
    execution = _run_model_command(repository, command)

    assert execution.isolation_established is True
    assert "repositoryformatversion" not in execution.output


def test_dynamic_repository_mutation_cannot_change_private_git_metadata(
    tmp_path: Path,
) -> None:
    repository, _ = _prepare_repository(tmp_path)
    command = "find . -name HEAD -delete"
    head = evaluator_git_dir(repository) / "HEAD"
    before = head.read_bytes()

    assert authorize_command(command).authorized is True
    execution = _run_model_command(repository, command)

    assert execution.isolation_established is True
    assert execution.returncode == 0
    assert head.read_bytes() == before
    assert git(repository, "status", "--short", check=True).stdout == ""


def test_legitimate_source_inspection_edit_and_evaluator_diff_still_work(
    tmp_path: Path,
) -> None:
    repository, initial_commit = _prepare_repository(tmp_path)

    inspection = _run_model_command(
        repository, "find . -maxdepth 1 -type f -print"
    )
    edit = _run_model_command(
        repository,
        "sed -i 's/raise NotImplementedError/return a + b/' calculator.py",
    )
    read = _run_model_command(repository, "cat calculator.py")

    assert inspection.isolation_established is True
    assert inspection.returncode == 0
    assert "./calculator.py" in inspection.output
    assert "./test_calculator.py" in inspection.output
    assert edit.route == "controlled_edit_gateway"
    assert edit.returncode == 0
    assert "return a + b" in read.output
    assert "return a + b" in final_patch(repository, initial_commit)
    assert git(repository, "status", "--short", check=True).stdout == (
        " M calculator.py\n"
    )


def test_programmatic_traversal_and_runtime_created_alias_are_denied(
    tmp_path: Path,
) -> None:
    repository, _ = _prepare_repository(tmp_path)
    private = evaluator_git_dir(repository)
    script = f'''from pathlib import Path
import os

private = Path({str(private)!r})
blocked = 0
for operation in (
    lambda: list(private.iterdir()),
    lambda: (private / "config").read_text(),
):
    try:
        operation()
    except PermissionError:
        blocked += 1
alias = Path(os.environ["TMPDIR"]) / "runtime-alias"
alias.symlink_to(private, target_is_directory=True)
try:
    (alias / "config").read_text()
except PermissionError:
    blocked += 1
print(blocked)
raise SystemExit(0 if blocked == 3 else 9)
'''
    (repository / "traversal_probe.py").write_text(script, encoding="utf-8")

    execution = _run_model_command(repository, "python traversal_probe.py")

    assert execution.returncode == 0
    assert execution.output.strip() == "3"
    assert (repository.parent / "agent-tmp/runtime-alias").is_symlink()


def test_abi1_rename_hardlink_and_truncate_attempts_cannot_mutate_private_state(
    tmp_path: Path,
) -> None:
    repository, _ = _prepare_repository(tmp_path)
    private = evaluator_git_dir(repository)
    script = f'''from pathlib import Path
import os

source = Path({str(private / "HEAD")!r})
destination = Path(os.environ["TMPDIR"]) / "stolen"
blocked = 0
for operation in (
    lambda: os.rename(source, destination),
    lambda: os.link(source, destination),
    lambda: os.truncate(source, 0),
    lambda: os.chmod(source, 0),
    lambda: os.utime(source, None),
):
    try:
        operation()
    except OSError:
        blocked += 1
print(blocked)
raise SystemExit(0 if blocked == 5 else 10)
'''
    (repository / "mutation_probe.py").write_text(script, encoding="utf-8")
    head = evaluator_git_dir(repository) / "HEAD"
    before = head.read_bytes()

    execution = _run_model_command(repository, "python mutation_probe.py")

    assert execution.returncode == 0
    assert execution.output.strip() == "5"
    assert head.read_bytes() == before
    assert not (repository.parent / "agent-tmp/stolen").exists()


def test_python_shell_and_grandchild_inherit_the_boundary(tmp_path: Path) -> None:
    repository, _ = _prepare_repository(tmp_path)
    private_config = evaluator_git_dir(repository) / "config"
    script = f'''import json
import subprocess
import sys

private = {str(private_config)!r}
code = "import pathlib,sys; pathlib.Path(sys.argv[1]).read_text()"
python_child = subprocess.run([sys.executable, "-c", code, private])
shell_child = subprocess.run(["/bin/sh", "-c", "cat \\\"$1\\\"", "sh", private])
middle = "import subprocess,sys; raise SystemExit(subprocess.run([sys.executable,'-c',sys.argv[1],sys.argv[2]]).returncode)"
grandchild = subprocess.run([sys.executable, "-c", middle, code, private])
values = [python_child.returncode, shell_child.returncode, grandchild.returncode]
print(json.dumps(values))
raise SystemExit(0 if all(value != 0 for value in values) else 11)
'''
    (repository / "inheritance_probe.py").write_text(script, encoding="utf-8")

    execution = _run_model_command(repository, "python inheritance_probe.py")

    assert execution.returncode == 0
    assert all(value != 0 for value in json.loads(execution.output.splitlines()[-1]))


def test_sensitive_parent_descriptor_is_not_inherited(tmp_path: Path) -> None:
    script = '''import os
import sys

try:
    os.fstat(int(sys.argv[1]))
except OSError:
    print("closed")
    raise SystemExit(0)
print("inherited")
raise SystemExit(12)
'''
    repository, _ = _prepare_repository(
        tmp_path, extra_files={"fd_probe.py": script}
    )
    descriptor = os.open(evaluator_git_dir(repository) / "config", os.O_RDONLY)
    try:
        execution = _run_model_command(repository, f"python fd_probe.py {descriptor}")
    finally:
        os.close(descriptor)

    assert execution.returncode == 0
    assert execution.output.strip() == "closed"
    assert execution.diagnostic["descriptor_hygiene"]["unexpected_fds"] == []


def test_legitimate_test_execution_and_protected_file_integrity(
    tmp_path: Path,
) -> None:
    repository, _ = _prepare_repository(tmp_path)
    protected = (repository / "test_calculator.py").read_bytes()

    edit = _run_model_command(
        repository,
        "sed -i 's/raise NotImplementedError/return a + b/' calculator.py",
    )
    tests = _run_model_command(
        repository,
        "python -m pytest -q -p no:cacheprovider test_calculator.py",
    )

    assert edit.returncode == 0
    assert tests.returncode == 0
    assert "1 passed" in tests.output
    assert (repository / "test_calculator.py").read_bytes() == protected


def test_supported_git_gateway_operations_are_controller_side_and_audited(
    tmp_path: Path,
) -> None:
    repository, _ = _prepare_repository(tmp_path)
    _run_model_command(
        repository,
        "sed -i 's/raise NotImplementedError/return a + b/' calculator.py",
    )

    status = _run_model_command(repository, "git status --short")
    diff = _run_model_command(repository, "git diff -- calculator.py")
    log = _run_model_command(repository, "git log -1 --oneline")
    show = _run_model_command(repository, "git show HEAD:calculator.py")

    for result in (status, diff, log, show):
        assert result.route == "git_gateway"
        assert result.isolation_established is True
        assert result.returncode == 0
    assert "calculator.py" in status.output
    assert "return a + b" in diff.output
    assert "Initial smoke-test repository" in log.output
    assert "raise NotImplementedError" in show.output
    audit = [
        json.loads(line)
        for line in (repository.parent / "controlled-command-audit.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    assert [row["route"] for row in audit[-4:]] == ["git_gateway"] * 4


@pytest.mark.parametrize(
    "command",
    [
        "git config --list",
        "git grep secret",
        "git diff --no-index /etc/passwd calculator.py",
        "git diff --ext-diff",
        "git show --output=calculator.py HEAD",
        "git status && cat calculator.py",
    ],
)
def test_unsafe_or_unsupported_git_gateway_operations_are_rejected(
    tmp_path: Path, command: str
) -> None:
    repository, _ = _prepare_repository(tmp_path)

    with pytest.raises(CommandGatewayRejected):
        _run_model_command(repository, command)
