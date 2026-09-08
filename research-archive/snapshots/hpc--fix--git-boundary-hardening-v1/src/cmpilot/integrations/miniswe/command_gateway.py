"""Structured controller gateways and the model-command filesystem boundary."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence

try:
    from ...task_file_policy import TaskFilePolicy
except ImportError:
    from cmpilot_task_file_policy import TaskFilePolicy  # type: ignore[no-redef]

try:
    from .filesystem_sandbox import SandboxedCommandResult, run_sandboxed_command
except ImportError:
    from cmpilot_filesystem_sandbox import (  # type: ignore[no-redef]
        SandboxedCommandResult,
        run_sandboxed_command,
    )


GATEWAY_SCHEMA = "cmpilot-controlled-command-gateway-v1"
_SHELL_CONTROL = frozenset({";", "&&", "||", "|", "|&", "&", "<", ">", ">>", "<<", "<<<", "(", ")"})
_SAFE_REVISION = re.compile(r"(?:HEAD|[0-9a-fA-F]{7,40})")
_MODEL_ENVIRONMENT_KEYS = frozenset(
    {
        "HOME",
        "LANG",
        "LC_ALL",
        "NO_PROXY",
        "PATH",
        "PYTHONDONTWRITEBYTECODE",
        "PYTHONNOUSERSITE",
        "TMPDIR",
        "TZ",
        "XDG_CONFIG_HOME",
        "no_proxy",
    }
)


class CommandGatewayRejected(ValueError):
    """Raised when a command resembles a gateway request but is not safe."""


@dataclass(frozen=True)
class GatewayRequest:
    route: str
    argv: tuple[str, ...]


def _tokens(command: str) -> list[str]:
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|()<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError as error:
        raise CommandGatewayRejected("malformed gateway command") from error
    if any(token in _SHELL_CONTROL or set(token) <= set(";&|()<>") for token in tokens):
        raise CommandGatewayRejected("gateway commands cannot contain shell control operators")
    return tokens


def _safe_relative_path(value: str, *, allow_dot: bool = False) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or any(part == ".." for part in path.parts):
        raise CommandGatewayRejected(f"path escapes the task repository: {value}")
    parts = [part for part in path.parts if part not in {"", "."}]
    if not parts:
        if allow_dot:
            return "."
        raise CommandGatewayRejected(f"path does not name a task file: {value}")
    if parts[0] == ".git":
        raise CommandGatewayRejected("evaluator Git metadata is not agent-visible")
    return PurePosixPath(*parts).as_posix()


def _validate_pathspecs(values: Sequence[str]) -> None:
    for value in values:
        _safe_relative_path(value, allow_dot=True)


def _validate_git(subcommand: str, arguments: Sequence[str]) -> None:
    if subcommand == "status":
        options = {"--short", "--porcelain", "--branch", "-s", "-b"}
        before, separator, after = list(arguments), False, []
        if "--" in before:
            index = before.index("--")
            after = before[index + 1 :]
            before = before[:index]
            separator = True
        if any(argument not in options for argument in before):
            raise CommandGatewayRejected("unsupported git status option")
        if separator:
            _validate_pathspecs(after)
        return

    if subcommand == "diff":
        safe_exact = {
            "--cached", "--staged", "--stat", "--name-only", "--name-status",
            "--check", "--no-color", "--color=never", "--binary",
        }
        before, after = list(arguments), []
        if "--" in before:
            index = before.index("--")
            after = before[index + 1 :]
            before = before[:index]
        for argument in before:
            if argument in safe_exact or re.fullmatch(r"-U\d+", argument):
                continue
            raise CommandGatewayRejected("unsupported or unsafe git diff option")
        _validate_pathspecs(after)
        return

    if subcommand == "log":
        safe_exact = {
            "--oneline", "--decorate", "--stat", "--name-only", "--no-color",
            "--color=never",
        }
        before, after = list(arguments), []
        if "--" in before:
            index = before.index("--")
            after = before[index + 1 :]
            before = before[:index]
        for argument in before:
            if argument in safe_exact or re.fullmatch(r"-\d+", argument):
                continue
            if _SAFE_REVISION.fullmatch(argument):
                continue
            raise CommandGatewayRejected("unsupported or unsafe git log option")
        _validate_pathspecs(after)
        return

    if subcommand == "show":
        safe_exact = {
            "--stat", "--name-only", "--name-status", "--no-color", "--color=never",
        }
        revision_seen = False
        for argument in arguments:
            if argument in safe_exact:
                continue
            revision, marker, path = argument.partition(":")
            if not revision_seen and _SAFE_REVISION.fullmatch(revision):
                if marker:
                    _safe_relative_path(path)
                revision_seen = True
                continue
            raise CommandGatewayRejected("unsupported or unsafe git show argument")
        if not revision_seen:
            raise CommandGatewayRejected("git show requires an explicit safe revision")
        return

    raise CommandGatewayRejected(f"unsupported Git operation: {subcommand}")


def parse_gateway_request(
    command: str,
    *,
    repository: Path,
    writable_paths: Sequence[str],
) -> GatewayRequest | None:
    """Return a structured request, ``None`` for ordinary sandboxed commands."""
    del repository  # The parser validates relative names; execution resolves them.
    tokens = _tokens(command)
    if not tokens:
        raise CommandGatewayRejected("empty command")
    executable = PurePosixPath(tokens[0]).name.casefold()
    if executable == "git":
        if tokens[0] not in {"git", "/usr/bin/git"} or len(tokens) < 2:
            raise CommandGatewayRejected("Git gateway requires a direct structured invocation")
        subcommand = tokens[1].casefold()
        _validate_git(subcommand, tokens[2:])
        return GatewayRequest("git_gateway", tuple([subcommand, *tokens[2:]]))
    if executable == "sed":
        if "-i" not in tokens[1:]:
            return None
        if tokens[0] not in {"sed", "/usr/bin/sed"}:
            raise CommandGatewayRejected("edit gateway requires the fixed sed executable")
        if len(tokens) != 4 or tokens[1] != "-i":
            raise CommandGatewayRejected("only a single-file sed -i edit is supported")
        if re.search(r"(?:^|[;{}\n])\s*[erw](?:\s|$)", tokens[2]):
            raise CommandGatewayRejected("sed filesystem/execute commands are prohibited")
        target = _safe_relative_path(tokens[3])
        if target not in set(writable_paths):
            raise CommandGatewayRejected("sed edit target is not task-policy writable")
        return GatewayRequest(
            "controlled_edit_gateway", ("--sandbox", "-i", tokens[2], target)
        )
    if executable in {"perl", "python", "python2", "python3", "ruby"} and any(
        argument == "-i" or argument.startswith("-i") for argument in tokens[1:]
    ):
        raise CommandGatewayRejected("unstructured in-place editing is not supported")
    return None


def _model_environment(environment: Mapping[str, str]) -> dict[str, str]:
    """Remove controller paths and metadata before model-command execution."""
    return {
        key: value for key, value in environment.items() if key in _MODEL_ENVIRONMENT_KEYS
    }


def _gateway_environment(environment: Mapping[str, str]) -> dict[str, str]:
    allowed = _model_environment(environment)
    allowed.update(
        {
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
        }
    )
    return allowed


def _run_gateway(
    request: GatewayRequest,
    *,
    repository: Path,
    evaluator_git_directory: Path,
    environment: Mapping[str, str],
    timeout: float,
) -> SandboxedCommandResult:
    if request.route == "git_gateway":
        command = [
            "/usr/bin/git", "--no-pager",
            f"--git-dir={evaluator_git_directory}",
            f"--work-tree={repository}",
            "-c", "core.hooksPath=/dev/null",
            *request.argv,
        ]
    elif request.route == "controlled_edit_gateway":
        target = repository / request.argv[-1]
        if target.is_symlink() or not target.is_file():
            raise CommandGatewayRejected("edit target must be an existing regular file")
        command = ["/usr/bin/sed", *request.argv]
    else:
        raise CommandGatewayRejected(f"unknown controlled route: {request.route}")
    try:
        completed = subprocess.run(
            command,
            cwd=repository,
            env=_gateway_environment(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout,
            close_fds=True,
            start_new_session=True,
        )
        returncode, output = completed.returncode, completed.stdout
    except subprocess.TimeoutExpired as error:
        returncode = 124
        output = (error.stdout or "") + (error.stderr or "")
    return SandboxedCommandResult(
        returncode=returncode,
        output=output,
        isolation_established=True,
        diagnostic={
            "schema": GATEWAY_SCHEMA,
            "classification": "CONTROLLED_GATEWAY",
            "route": request.route,
            "close_fds": True,
            "shell": False,
        },
        route=request.route,
    )


def _append_audit(
    path: Path,
    *,
    command: str,
    request: GatewayRequest | None,
    result: SandboxedCommandResult,
) -> None:
    record: dict[str, Any] = {
        "schema": GATEWAY_SCHEMA,
        "command_sha256": hashlib.sha256(command.encode()).hexdigest(),
        "route": result.route,
        "argv": None if request is None else list(request.argv),
        "returncode": result.returncode,
        "output_sha256": hashlib.sha256(result.output.encode()).hexdigest(),
        "isolation_established": result.isolation_established,
        "diagnostic": result.diagnostic,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")


def execute_controlled_command(
    command: str,
    *,
    repository: Path,
    evaluator_git_directory: Path,
    task_policy: TaskFilePolicy,
    environment: Mapping[str, str],
    timeout: float,
    audit_path: Path,
) -> SandboxedCommandResult:
    """Route narrow Git/edit requests or run under the structural sandbox."""
    repository = Path(repository).resolve(strict=True)
    evaluator_git_directory = Path(evaluator_git_directory).resolve(strict=True)
    dot_git = repository / ".git"
    if dot_git.exists() or dot_git.is_symlink():
        raise CommandGatewayRejected("agent-visible repository contains forbidden .git metadata")
    model_environment = _model_environment(environment)
    try:
        request = parse_gateway_request(
            command,
            repository=repository,
            writable_paths=task_policy.writable_paths,
        )
    except CommandGatewayRejected as error:
        rejected = SandboxedCommandResult(
            returncode=126,
            output="",
            isolation_established=True,
            diagnostic={
                "schema": GATEWAY_SCHEMA,
                "classification": "CONTROLLED_GATEWAY_REJECTED",
                "reason": str(error),
                "shell": False,
            },
            route="controlled_gateway_rejected",
        )
        _append_audit(
            Path(audit_path), command=command, request=None, result=rejected
        )
        raise
    if request is not None:
        result = _run_gateway(
            request,
            repository=repository,
            evaluator_git_directory=evaluator_git_directory,
            environment=model_environment,
            timeout=timeout,
        )
    else:
        writable_files = [repository / relative for relative in task_policy.writable_paths]
        writable_directories = [
            Path(environment[key])
            for key in ("HOME", "TMPDIR")
            if key in environment
        ]
        result = run_sandboxed_command(
            command,
            cwd=repository,
            environment=model_environment,
            readable_roots=[repository],
            writable_files=writable_files,
            writable_directories=writable_directories,
            timeout=timeout,
        )
    _append_audit(
        Path(audit_path), command=command, request=request, result=result
    )
    return result
