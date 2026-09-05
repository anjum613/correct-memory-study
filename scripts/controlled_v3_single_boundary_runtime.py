#!/usr/bin/env python3
"""One-boundary Codex containment used by construction V3 and its dummy gate.

Codex runs with its internal command sandbox disabled only after entering a
dedicated user/mount/pid namespace and chroot containing the rendered workspace.
This avoids nested bubblewrap/user-namespace and nested devpts setup.  One
devpts instance is created at the outer boundary so Codex command execution can
open a PTY without another namespace layer.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import tempfile
import time
from typing import Any


TOOL_ITEM_TYPES = {
    "command_execution",
    "file_change",
    "mcp_tool_call",
    "web_search",
    "image_generation",
    "dynamic_tool_call",
    "tool_call",
    "function_call",
}
POST_TERMINAL_GRACE_SECONDS = 15.0


CHROOT_SCRIPT = r'''
root=$1
workspace=$2
runtime_root=$3
runtime_executable=$4
shift 4
mount --make-rprivate /
mount --bind /usr "$root/usr"
mount -o remount,bind,ro "$root/usr"
mount --bind /opt/miniconda3 "$root/opt/miniconda3"
mount -o remount,bind,ro "$root/opt/miniconda3"
mount --bind "$runtime_root/bin/codex" "$root/codex-runtime/bin/codex"
mount -o remount,bind,ro "$root/codex-runtime/bin/codex"
mount --bind "$runtime_root/bin/codex-code-mode-host" "$root/codex-runtime/bin/codex-code-mode-host"
mount -o remount,bind,ro "$root/codex-runtime/bin/codex-code-mode-host"
mount --bind "$workspace" "$root/workspace"
for member in AGENTS.md inputs repository tools interface.json; do
  if [ -e "$workspace/$member" ]; then
    mount --bind "$workspace/$member" "$root/workspace/$member"
    mount -o remount,bind,ro "$root/workspace/$member"
  fi
done
for directory in ssl alternatives; do
  if [ -d "/etc/$directory" ]; then
    mount --bind "/etc/$directory" "$root/etc/$directory"
    mount -o remount,bind,ro "$root/etc/$directory"
  fi
done
for name in resolv.conf hosts nsswitch.conf passwd group; do
  if [ -f "/etc/$name" ]; then
    mount --bind "/etc/$name" "$root/etc/$name"
    mount -o remount,bind,ro "$root/etc/$name"
  fi
done
for name in null random urandom; do
  mount --bind "/dev/$name" "$root/dev/$name"
done
mount -t devpts -o newinstance,ptmxmode=0666,mode=0620 devpts "$root/dev/pts"
mount -t tmpfs -o size=256m,nosuid,nodev tmpfs "$root/tmp"
mount -t proc -o nosuid,nodev,noexec proc "$root/proc"
exec /usr/sbin/chroot "$root" /usr/bin/env -i \
  HOME=/home/constructor CODEX_HOME=/codex-home \
  PATH=/codex-runtime/bin:/opt/miniconda3/bin:/usr/bin:/bin \
  LC_ALL=C.UTF-8 PYTHONDONTWRITEBYTECODE=1 \
  SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
  /usr/bin/setpriv --bounding-set=-all --inh-caps=-all --ambient-caps=-all \
  --no-new-privs "$runtime_executable" "$@"
'''


def canonical(value: object) -> bytes:
    return json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(65_536), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_codex() -> Path:
    configured = os.environ.get("CONTROLLED_V3_CODEX")
    found = configured or shutil.which("codex")
    if not found:
        fallback = Path.home() / ".local/bin/codex"
        found = str(fallback) if fallback.is_file() else None
    if not found:
        raise FileNotFoundError("currently available Codex executable was not found")
    executable = Path(found).resolve()
    if not executable.is_file():
        raise FileNotFoundError(f"Codex executable is not regular: {executable}")
    return executable


def runtime_observation(codex: Path | None = None) -> dict[str, Any]:
    executable = (codex or resolve_codex()).resolve()
    release = executable.parents[1]
    host = release / "bin/codex-code-mode-host"
    version = subprocess.run(
        [str(executable), "--version"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        timeout=120,
    )
    if version.returncode or not host.is_file():
        raise RuntimeError("current Codex runtime is incomplete")
    return {
        "constructor_runtime_is_scientific_variable": False,
        "codex_executable": str(executable),
        "codex_executable_sha256": sha256_file(executable),
        "codex_version": version.stdout.strip(),
        "code_mode_host": str(host),
        "code_mode_host_sha256": sha256_file(host),
        "model_selection": "current available Codex configuration",
        "containment": "single outer user+mount+pid namespace and chroot",
        "nested_bubblewrap": False,
        "nested_devpts": False,
    }


def initialize_chroot(root: Path, codex: Path | None = None) -> None:
    executable = (codex or resolve_codex()).resolve()
    for directory in (
        "usr",
        "opt/miniconda3",
        "codex-runtime/bin",
        "workspace",
        "etc/ssl",
        "etc/alternatives",
        "dev/pts",
        "tmp",
        "proc",
        "home/constructor",
        "codex-home",
    ):
        (root / directory).mkdir(parents=True, exist_ok=True)
    for name, target in (
        ("bin", "usr/bin"),
        ("sbin", "usr/sbin"),
        ("lib", "usr/lib"),
        ("lib64", "usr/lib64"),
    ):
        link = root / name
        if not link.exists():
            link.symlink_to(target)
    for name in ("resolv.conf", "hosts", "nsswitch.conf", "passwd", "group"):
        (root / "etc" / name).touch()
    for name in ("null", "random", "urandom"):
        (root / "dev" / name).touch()
    (root / "dev/ptmx").symlink_to("pts/ptmx")
    (root / "codex-runtime/bin/codex").touch()
    (root / "codex-runtime/bin/codex-code-mode-host").touch()
    codex_home = Path.home() / ".codex"
    for name in ("auth.json", "installation_id", "models_cache.json"):
        source = codex_home / name
        if source.is_file():
            shutil.copy2(source, root / "codex-home" / name)
def codex_exec_arguments(final_message: str) -> list[str]:
    return [
        "exec",
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "--ephemeral",
        "--dangerously-bypass-approvals-and-sandbox",
        "--cd",
        "/workspace",
        "--skip-git-repo-check",
        "--json",
        "--color",
        "never",
        "--output-last-message",
        final_message,
        "-",
    ]


def isolated_command(
    root: Path,
    workspace: Path,
    inside: list[str],
    *,
    codex: Path | None = None,
    runtime_executable: str = "/codex-runtime/bin/codex",
) -> list[str]:
    executable = (codex or resolve_codex()).resolve()
    release_root = executable.parents[1]
    return [
        "/usr/bin/unshare",
        "--user",
        "--map-root-user",
        "--mount",
        "--pid",
        "--fork",
        "/bin/sh",
        "-eu",
        "-c",
        CHROOT_SCRIPT,
        "sh",
        str(root),
        str(Path(workspace).resolve()),
        str(release_root),
        runtime_executable,
        *inside,
    ]


def telemetry(path: Path) -> dict[str, Any]:
    terminal: list[str] = []
    tool_keys: set[str] = set()
    output_tokens: list[int] = []
    parse_errors = 0
    event_count = 0
    if Path(path).is_file():
        for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                parse_errors += 1
                continue
            if not isinstance(event, dict):
                continue
            event_count += 1
            event_type = event.get("type")
            if event_type in {"turn.completed", "turn.failed"}:
                terminal.append(str(event_type))
            if event_type == "turn.completed":
                usage = event.get("usage")
                if isinstance(usage, dict) and type(usage.get("output_tokens")) is int:
                    output_tokens.append(usage["output_tokens"])
            if event_type in {"item.started", "item.completed"}:
                item = event.get("item")
                if isinstance(item, dict) and item.get("type") in TOOL_ITEM_TYPES:
                    identifier = item.get("id")
                    key = (
                        "id:" + identifier
                        if isinstance(identifier, str)
                        else "item:" + hashlib.sha256(canonical(item)).hexdigest()
                    )
                    tool_keys.add(key)
    return {
        "event_count": event_count,
        "json_parse_errors": parse_errors,
        "terminal_event_present": bool(terminal),
        "terminal_event_types": terminal,
        "tool_calls": len(tool_keys),
        "output_tokens": max(output_tokens) if output_tokens else None,
    }


def _terminate_group(process: subprocess.Popen[bytes], reason: str) -> tuple[int, str]:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        return process.wait(timeout=5), reason
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        return process.wait(), reason + "_THEN_KILLED"


def execute_codex(
    command: list[str],
    *,
    workspace: Path,
    prompt: bytes,
    events: Path,
    stderr: Path,
    timeout_seconds: int,
    tool_call_limit: int,
    maximum_output_tokens: int,
) -> dict[str, Any]:
    started = time.monotonic()
    terminal_seen_at: float | None = None
    timed_out = False
    tool_limit_exceeded = False
    termination_reason = "PROCESS_EXIT"
    with Path(events).open("xb") as stdout_handle, Path(stderr).open("xb") as stderr_handle:
        try:
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=stdout_handle,
                stderr=stderr_handle,
                start_new_session=True,
            )
        except BaseException as error:
            stderr_handle.write(
                f"{type(error).__name__}: {error}\n".encode("utf-8", "replace")
            )
            return {
                "returncode": None,
                "duration_seconds": round(time.monotonic() - started, 3),
                "timed_out": False,
                "tool_limit_exceeded": False,
                "output_limit_exceeded": False,
                "termination_reason": "PROCESS_START_ERROR",
                "telemetry": telemetry(events),
            }
        assert process.stdin is not None
        try:
            process.stdin.write(prompt)
            process.stdin.close()
        except BrokenPipeError:
            process.stdin.close()
        while process.poll() is None:
            now = time.monotonic()
            observed = telemetry(events)
            if observed["tool_calls"] > tool_call_limit:
                tool_limit_exceeded = True
                termination_reason = "TOOL_CALL_LIMIT_EXCEEDED"
                returncode, termination_reason = _terminate_group(process, termination_reason)
                break
            if terminal_seen_at is None and observed["terminal_event_present"]:
                terminal_seen_at = now
            if terminal_seen_at is not None and now - terminal_seen_at >= POST_TERMINAL_GRACE_SECONDS:
                termination_reason = "TERMINATED_AFTER_RECORDED_TERMINAL_EVENT"
                returncode, termination_reason = _terminate_group(process, termination_reason)
                break
            if now - started >= timeout_seconds:
                timed_out = True
                termination_reason = "TIMEOUT"
                returncode, termination_reason = _terminate_group(process, termination_reason)
                break
            time.sleep(0.25)
        else:
            returncode = process.returncode
    observed = telemetry(events)
    output_limit_exceeded = (
        observed["output_tokens"] is not None
        and observed["output_tokens"] > maximum_output_tokens
    )
    return {
        "returncode": returncode,
        "duration_seconds": round(time.monotonic() - started, 3),
        "timed_out": timed_out,
        "tool_limit_exceeded": tool_limit_exceeded,
        "output_limit_exceeded": output_limit_exceeded,
        "termination_reason": termination_reason,
        "telemetry": observed,
    }


def static_preflight() -> dict[str, Any]:
    codex = resolve_codex()
    observation = runtime_observation(codex)
    with tempfile.TemporaryDirectory(prefix="controlled-v3-single-boundary-preflight-") as temporary:
        temporary_root = Path(temporary)
        root = temporary_root / "root"
        workspace = temporary_root / "workspace"
        workspace.mkdir()
        for name in ("inputs", "repository", "tools", "components", ".scratch"):
            (workspace / name).mkdir()
        (workspace / "AGENTS.md").write_text("Static non-benchmark preflight.\n", encoding="utf-8")
        (workspace / "interface.json").write_text("{}\n", encoding="utf-8")
        initialize_chroot(root, codex)
        version = subprocess.run(
            isolated_command(root, workspace, ["--version"], codex=codex),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=120,
        )
        pty = subprocess.run(
            isolated_command(
                root,
                workspace,
                [
                    "-c",
                    "import os,pty; m,s=pty.openpty(); os.close(m); os.close(s); print('PTY_OK')",
                ],
                codex=codex,
                runtime_executable="/usr/bin/python3",
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            timeout=120,
        )
    if version.returncode or "codex-cli" not in version.stdout:
        raise RuntimeError("single-boundary Codex version preflight failed")
    if pty.returncode or pty.stdout.strip() != "PTY_OK":
        raise RuntimeError("single-boundary host-devpts preflight failed")
    return {
        "status": "PASS",
        "benchmark_invocation": False,
        "constructor_attempts": 0,
        "runtime": observation,
        "pty_strategy": "one devpts instance at the external boundary",
        "bubblewrap_dependency": False,
        "platform": platform.platform(),
    }
