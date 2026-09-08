"""Fail-closed Landlock boundary for model-controlled subprocesses.

The controller launches a small Python child which establishes Landlock and
then ``exec``s the requested shell command.  The controller itself is never
restricted.  No user namespace is created or required.

Cluster qualification currently guarantees Landlock ABI 1.  This module only
handles ABI-1 rights and explicitly records the later rights it cannot claim.
Private evaluator state must therefore live outside every readable root and no
sensitive file descriptor may be inherited by the child.
"""

from __future__ import annotations

import argparse
import base64
import ctypes
import errno
import json
import os
import platform
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA = "cmpilot-model-filesystem-sandbox-v1"
SANDBOX_FAILURE_EXIT = 125
LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
PR_GET_NO_NEW_PRIVS = 39
PR_SET_SECCOMP = 22
SECCOMP_MODE_FILTER = 2
SECCOMP_RET_ERRNO = 0x00050000
SECCOMP_RET_ALLOW = 0x7FFF0000
LANDLOCK_SYSCALLS = {
    "aarch64": (444, 445, 446),
    "x86_64": (444, 445, 446),
}
ABI1_RIGHTS = {
    "EXECUTE": 1 << 0,
    "WRITE_FILE": 1 << 1,
    "READ_FILE": 1 << 2,
    "READ_DIR": 1 << 3,
    "REMOVE_DIR": 1 << 4,
    "REMOVE_FILE": 1 << 5,
    "MAKE_CHAR": 1 << 6,
    "MAKE_DIR": 1 << 7,
    "MAKE_REG": 1 << 8,
    "MAKE_SOCK": 1 << 9,
    "MAKE_FIFO": 1 << 10,
    "MAKE_BLOCK": 1 << 11,
    "MAKE_SYM": 1 << 12,
}
ABI1_HANDLED_ACCESS = sum(ABI1_RIGHTS.values())
READ_EXECUTE_ACCESS = (
    ABI1_RIGHTS["EXECUTE"] | ABI1_RIGHTS["READ_FILE"] | ABI1_RIGHTS["READ_DIR"]
)
FULL_ABI1_ACCESS = ABI1_HANDLED_ACCESS
UNSUPPORTED_RIGHTS = ["REFER", "TRUNCATE", "IOCTL_DEV"]


class _RulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class _PathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


class _SockFilter(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint32),
    ]


class _SockFprog(ctypes.Structure):
    _fields_ = [
        ("length", ctypes.c_ushort),
        ("filter", ctypes.POINTER(_SockFilter)),
    ]


_LIBC = ctypes.CDLL(None, use_errno=True)
_LIBC.syscall.restype = ctypes.c_long
_LIBC.prctl.restype = ctypes.c_int


@dataclass(frozen=True)
class SandboxedCommandResult:
    returncode: int
    output: str
    isolation_established: bool
    diagnostic: dict[str, Any]
    route: str = "landlock_shell"


def _errno_record(value: int) -> dict[str, Any]:
    return {
        "errno": value,
        "errno_name": errno.errorcode.get(value),
        "message": os.strerror(value) if value else None,
    }


def _syscall(number: int, *arguments: Any) -> tuple[int, dict[str, Any]]:
    ctypes.set_errno(0)
    result = int(_LIBC.syscall(ctypes.c_long(number), *arguments))
    value = ctypes.get_errno() if result < 0 else 0
    return result, _errno_record(value)


def _prctl(option: int, argument: int = 0) -> tuple[int, dict[str, Any]]:
    ctypes.set_errno(0)
    result = int(
        _LIBC.prctl(
            ctypes.c_int(option),
            ctypes.c_ulong(argument),
            ctypes.c_ulong(0),
            ctypes.c_ulong(0),
            ctypes.c_ulong(0),
        )
    )
    value = ctypes.get_errno() if result < 0 else 0
    return result, _errno_record(value)


def _apply_abi1_metadata_mutation_filter(machine: str) -> dict[str, Any]:
    """Block path-metadata mutations not mediated by Landlock ABI 1.

    Allowed task content edits continue through WRITE_FILE or the controlled
    edit gateway.  File-descriptor truncation remains usable for descriptors
    opened *after* sandbox entry; sensitive descriptors are closed before it.
    """
    syscall_tables = {
        "x86_64": {
            "truncate": 76,
            "chmod": 90,
            "fchmod": 91,
            "chown": 92,
            "fchown": 93,
            "lchown": 94,
            "utime": 132,
            "setxattr": 188,
            "lsetxattr": 189,
            "fsetxattr": 190,
            "removexattr": 197,
            "lremovexattr": 198,
            "fremovexattr": 199,
            "utimes": 235,
            "fchownat": 260,
            "futimesat": 261,
            "fchmodat": 268,
            "utimensat": 280,
        },
        "aarch64": {
            "setxattr": 5,
            "lsetxattr": 6,
            "fsetxattr": 7,
            "removexattr": 14,
            "lremovexattr": 15,
            "fremovexattr": 16,
            "fchmod": 52,
            "fchmodat": 53,
            "fchownat": 54,
            "fchown": 55,
            "utimensat": 88,
        },
    }
    syscalls = syscall_tables.get(machine)
    if syscalls is None:
        return {
            "success": False,
            "machine": machine,
            "blocked_syscalls": [],
            "reason": "unsupported-seccomp-architecture",
            **_errno_record(0),
        }
    # struct seccomp_data begins with the 32-bit syscall number.  Each match
    # returns EPERM; all other syscalls continue to normal kernel enforcement.
    rows = [_SockFilter(0x20, 0, 0, 0)]
    for syscall_number in syscalls.values():
        rows.extend(
            (
                _SockFilter(0x15, 0, 1, syscall_number),
                _SockFilter(0x06, 0, 0, SECCOMP_RET_ERRNO | errno.EPERM),
            )
        )
    rows.append(_SockFilter(0x06, 0, 0, SECCOMP_RET_ALLOW))
    instructions = (_SockFilter * len(rows))(*rows)
    program = _SockFprog(len(instructions), instructions)
    ctypes.set_errno(0)
    result = int(
        _LIBC.prctl(
            ctypes.c_int(PR_SET_SECCOMP),
            ctypes.c_ulong(SECCOMP_MODE_FILTER),
            ctypes.byref(program),
            ctypes.c_ulong(0),
            ctypes.c_ulong(0),
        )
    )
    value = ctypes.get_errno() if result < 0 else 0
    return {
        "success": result == 0,
        "machine": machine,
        "blocked_syscalls": sorted(syscalls),
        "result": result,
        **_errno_record(value),
    }


def query_landlock_abi() -> dict[str, Any]:
    machine = platform.machine().casefold()
    numbers = LANDLOCK_SYSCALLS.get(machine)
    if numbers is None:
        return {
            "available": False,
            "abi": None,
            "machine": machine,
            "reason": "unsupported-architecture",
            **_errno_record(0),
        }
    result, error = _syscall(
        numbers[0],
        ctypes.c_void_p(),
        ctypes.c_size_t(0),
        ctypes.c_uint32(LANDLOCK_CREATE_RULESET_VERSION),
    )
    return {
        "available": result >= 1,
        "abi": result if result >= 1 else None,
        "machine": machine,
        "reason": None if result >= 1 else "landlock-version-query-failed",
        **error,
    }


def _resolved_existing_paths(paths: Iterable[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[tuple[int, int]] = set()
    for raw in paths:
        path = Path(raw).resolve(strict=True)
        information = path.stat()
        identity = (information.st_dev, information.st_ino)
        if identity not in seen:
            seen.add(identity)
            result.append(path)
    return result


def _resolved_writable_paths(
    paths: Iterable[Path], *, root: Path, expected_kind: str
) -> list[Path]:
    """Resolve writable paths without accepting a symlink or symlinked parent."""
    result: list[Path] = []
    seen: set[tuple[int, int]] = set()
    for raw in paths:
        supplied = Path(raw)
        candidate = root / supplied if not supplied.is_absolute() else supplied
        lexical = Path(os.path.abspath(candidate))
        resolved = lexical.resolve(strict=True)
        if lexical != resolved:
            raise ValueError(
                f"writable {expected_kind} path must not use a symlink or symlinked parent: {supplied}"
            )
        information = resolved.stat()
        if expected_kind == "file" and not resolved.is_file():
            raise ValueError(f"writable task path must be a regular file: {resolved}")
        if expected_kind == "directory" and not resolved.is_dir():
            raise ValueError(f"writable task path must be a directory: {resolved}")
        identity = (information.st_dev, information.st_ino)
        if identity not in seen:
            seen.add(identity)
            result.append(resolved)
    return result


def _runtime_paths() -> list[tuple[Path, int, str]]:
    read_execute = [Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64")]
    python_paths = [Path(sys.prefix), Path(sys.base_prefix), Path(sys.executable).parent]
    runtime_files = [
        Path("/etc/ld.so.cache"),
        Path("/etc/localtime"),
        Path("/etc/nsswitch.conf"),
        Path("/etc/passwd"),
        Path("/etc/group"),
    ]
    devices = [Path("/dev/null"), Path("/dev/urandom"), Path("/dev/random")]
    rows: list[tuple[Path, int, str]] = []
    seen: set[tuple[int, int]] = set()
    for path, access, role in [
        *((path, READ_EXECUTE_ACCESS, "system-runtime") for path in read_execute),
        *((path, READ_EXECUTE_ACCESS, "python-runtime") for path in python_paths),
        *((path, ABI1_RIGHTS["READ_FILE"], "runtime-configuration") for path in runtime_files),
        *((path, ABI1_RIGHTS["READ_FILE"] | ABI1_RIGHTS["WRITE_FILE"], "runtime-device") for path in devices),
    ]:
        if not path.exists():
            continue
        resolved = path.resolve(strict=True)
        information = resolved.stat()
        identity = (information.st_dev, information.st_ino)
        if identity not in seen:
            seen.add(identity)
            rows.append((resolved, access, role))
    return rows


def _open_descriptors(excluded: set[int]) -> list[int]:
    directory = Path("/proc/self/fd")
    if not directory.is_dir():
        return []
    descriptors: list[int] = []
    for entry in directory.iterdir():
        try:
            descriptor = int(entry.name)
        except ValueError:
            continue
        if descriptor <= 2 or descriptor in excluded:
            continue
        try:
            os.fstat(descriptor)
        except OSError:
            continue
        descriptors.append(descriptor)
    return sorted(descriptors)


def _add_rule(
    add_rule_number: int,
    ruleset_fd: int,
    path: Path,
    access: int,
    role: str,
) -> dict[str, Any]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
        attribute = _PathBeneathAttr(allowed_access=access, parent_fd=descriptor)
        result, error = _syscall(
            add_rule_number,
            ctypes.c_int(ruleset_fd),
            ctypes.c_int(LANDLOCK_RULE_PATH_BENEATH),
            ctypes.byref(attribute),
            ctypes.c_uint32(0),
        )
        return {
            "path": str(path),
            "role": role,
            "allowed_access": access,
            "success": result == 0,
            **error,
        }
    except OSError as error:
        return {
            "path": str(path),
            "role": role,
            "allowed_access": access,
            "success": False,
            **_errno_record(error.errno or 0),
        }
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _apply_landlock(configuration: Mapping[str, Any], status_fd: int) -> dict[str, Any]:
    availability = query_landlock_abi()
    abi = availability.get("abi")
    diagnostic: dict[str, Any] = {
        "schema": SCHEMA,
        "classification": "SANDBOX_IMPLEMENTATION_ERROR",
        "availability": availability,
        "landlock_abi": abi,
        "minimum_abi": configuration["minimum_abi"],
        "user_namespace_used": False,
        "user_namespace_required": False,
        "unsupported_rights": UNSUPPORTED_RIGHTS,
        "abi1_compensating_controls": {
            "close_fds": True,
            "private_paths_outside_readable_roots": True,
            "external_evaluator_git_metadata": True,
            "metadata_mutation_seccomp_filter": True,
        },
        "descriptor_hygiene": {
            "close_fds": True,
            "explicitly_passed_fds": [status_fd],
            "unexpected_fds": _open_descriptors({status_fd}),
        },
        "rules": [],
    }
    if not availability["available"] or not isinstance(abi, int):
        diagnostic["classification"] = "SANDBOX_CAPABILITY_UNAVAILABLE"
        return diagnostic
    if abi < int(configuration["minimum_abi"]):
        diagnostic["classification"] = "SANDBOX_CAPABILITY_UNAVAILABLE"
        diagnostic["reason"] = "landlock-abi-below-required-minimum"
        return diagnostic

    create_number, add_number, restrict_number = LANDLOCK_SYSCALLS[
        availability["machine"]
    ]
    attribute = _RulesetAttr(handled_access_fs=ABI1_HANDLED_ACCESS)
    ruleset_fd, error = _syscall(
        create_number,
        ctypes.byref(attribute),
        ctypes.c_size_t(ctypes.sizeof(attribute)),
        ctypes.c_uint32(0),
    )
    diagnostic["ruleset_creation"] = {
        "success": ruleset_fd >= 0,
        "result": ruleset_fd,
        **error,
    }
    if ruleset_fd < 0:
        return diagnostic
    try:
        rules: list[tuple[Path, int, str]] = []
        rules.extend(
            (Path(path), READ_EXECUTE_ACCESS, "task-readable-root")
            for path in configuration["readable_roots"]
        )
        rules.extend(
            (
                Path(path),
                ABI1_RIGHTS["READ_FILE"] | ABI1_RIGHTS["WRITE_FILE"],
                "task-writable-file",
            )
            for path in configuration["writable_files"]
        )
        rules.extend(
            (Path(path), FULL_ABI1_ACCESS, "isolated-writable-directory")
            for path in configuration["writable_directories"]
        )
        rules.extend(_runtime_paths())
        diagnostic["rules"] = [
            _add_rule(add_number, ruleset_fd, path, access, role)
            for path, access, role in rules
        ]
        if not diagnostic["rules"] or not all(
            row["success"] for row in diagnostic["rules"]
        ):
            diagnostic["reason"] = "landlock-rule-addition-failed"
            return diagnostic
        diagnostic["rule_addition"] = {
            "success": True,
            "count": len(diagnostic["rules"]),
        }

        before, before_error = _prctl(PR_GET_NO_NEW_PRIVS)
        set_result, set_error = _prctl(PR_SET_NO_NEW_PRIVS, 1)
        after, after_error = _prctl(PR_GET_NO_NEW_PRIVS)
        diagnostic["no_new_privs"] = {
            "before": before,
            "before_error": before_error,
            "set_result": set_result,
            "set_error": set_error,
            "after": after,
            "after_error": after_error,
            "success": set_result == 0 and after == 1,
        }
        if not diagnostic["no_new_privs"]["success"]:
            diagnostic["reason"] = "no-new-privs-failed"
            return diagnostic
        restrict_result, restrict_error = _syscall(
            restrict_number,
            ctypes.c_int(ruleset_fd),
            ctypes.c_uint32(0),
        )
        diagnostic["restrict_self"] = {
            "success": restrict_result == 0,
            "result": restrict_result,
            **restrict_error,
        }
        if restrict_result != 0:
            diagnostic["reason"] = "landlock-restrict-self-failed"
            return diagnostic
        diagnostic["seccomp_abi1_metadata_mutation"] = _apply_abi1_metadata_mutation_filter(
            availability["machine"]
        )
        if not diagnostic["seccomp_abi1_metadata_mutation"]["success"]:
            diagnostic["reason"] = "abi1-metadata-seccomp-filter-failed"
            return diagnostic
        diagnostic["classification"] = "SANDBOX_ESTABLISHED"
        return diagnostic
    finally:
        os.close(ruleset_fd)


def _write_status(status_fd: int, diagnostic: Mapping[str, Any]) -> None:
    payload = (json.dumps(diagnostic, sort_keys=True, separators=(",", ":")) + "\n").encode()
    try:
        os.write(status_fd, payload)
    finally:
        os.close(status_fd)


def _child(configuration_token: str, status_fd: int) -> int:
    try:
        configuration = json.loads(base64.urlsafe_b64decode(configuration_token).decode())
        os.chdir(configuration["cwd"])
        diagnostic = _apply_landlock(configuration, status_fd)
    except BaseException as error:
        diagnostic = {
            "schema": SCHEMA,
            "classification": "SANDBOX_IMPLEMENTATION_ERROR",
            "error_type": type(error).__name__,
            "error": str(error),
            "landlock_abi": None,
            "unsupported_rights": UNSUPPORTED_RIGHTS,
            "descriptor_hygiene": {"close_fds": True, "unexpected_fds": []},
        }
    _write_status(status_fd, diagnostic)
    if diagnostic["classification"] != "SANDBOX_ESTABLISHED":
        return SANDBOX_FAILURE_EXIT
    environment = {str(key): str(value) for key, value in configuration["environment"].items()}
    os.execve("/bin/sh", ["/bin/sh", "-c", configuration["command"]], environment)
    return SANDBOX_FAILURE_EXIT


def _terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def _cleanup_process_group(process_group: int) -> dict[str, Any]:
    try:
        os.killpg(process_group, 0)
    except ProcessLookupError:
        return {"complete": True, "signal": None, "process_group_running": False}
    os.killpg(process_group, signal.SIGTERM)
    deadline = time.monotonic() + 0.5
    while time.monotonic() < deadline:
        try:
            os.killpg(process_group, 0)
        except ProcessLookupError:
            return {"complete": True, "signal": "SIGTERM", "process_group_running": False}
        time.sleep(0.01)
    try:
        os.killpg(process_group, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return {"complete": True, "signal": "SIGKILL", "process_group_running": False}


def run_sandboxed_command(
    command: str,
    *,
    cwd: Path,
    environment: Mapping[str, str],
    readable_roots: Iterable[Path],
    writable_files: Iterable[Path],
    writable_directories: Iterable[Path],
    timeout: float,
    minimum_abi: int = 1,
) -> SandboxedCommandResult:
    """Execute ``command`` only after a child establishes strict Landlock."""
    root = Path(cwd).resolve(strict=True)
    readable = _resolved_existing_paths(readable_roots)
    writable_file_paths = _resolved_writable_paths(
        writable_files, root=root, expected_kind="file"
    )
    writable_directory_paths = _resolved_writable_paths(
        writable_directories, root=root, expected_kind="directory"
    )

    configuration = {
        "command": command,
        "cwd": str(root),
        "environment": dict(environment),
        "minimum_abi": minimum_abi,
        "readable_roots": [str(path) for path in readable],
        "writable_files": [str(path) for path in writable_file_paths],
        "writable_directories": [str(path) for path in writable_directory_paths],
    }
    token = base64.urlsafe_b64encode(
        json.dumps(configuration, sort_keys=True, separators=(",", ":")).encode()
    ).decode()
    status_read, status_write = os.pipe()
    process: subprocess.Popen[bytes] | None = None
    timed_out = False
    try:
        process = subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--sandbox-child", token, str(status_write)],
            cwd=root,
            env=dict(environment),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            close_fds=True,
            pass_fds=(status_write,),
            start_new_session=True,
        )
        os.close(status_write)
        status_write = -1
        try:
            output_bytes, _ = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_process_group(process)
            output_bytes, _ = process.communicate()
        status_bytes = b""
        while True:
            chunk = os.read(status_read, 65536)
            if not chunk:
                break
            status_bytes += chunk
        try:
            diagnostic = json.loads(status_bytes.decode().strip())
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            diagnostic = {
                "schema": SCHEMA,
                "classification": "SANDBOX_IMPLEMENTATION_ERROR",
                "error_type": type(error).__name__,
                "error": str(error),
                "raw_status": status_bytes.decode(errors="replace"),
                "landlock_abi": None,
                "unsupported_rights": UNSUPPORTED_RIGHTS,
                "descriptor_hygiene": {"close_fds": True, "unexpected_fds": []},
            }
        if timed_out:
            diagnostic["timeout"] = True
        diagnostic["process_group_cleanup"] = _cleanup_process_group(process.pid)
        isolation = diagnostic.get("classification") == "SANDBOX_ESTABLISHED"
        return SandboxedCommandResult(
            returncode=124 if timed_out else process.returncode,
            output=output_bytes.decode(errors="replace"),
            isolation_established=isolation,
            diagnostic=diagnostic,
        )
    finally:
        if status_write >= 0:
            os.close(status_write)
        os.close(status_read)
        if process is not None and process.poll() is None:
            _terminate_process_group(process)


def _main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--sandbox-child", action="store_true")
    parser.add_argument("configuration")
    parser.add_argument("status_fd", type=int)
    arguments = parser.parse_args()
    if not arguments.sandbox_child:
        return SANDBOX_FAILURE_EXIT
    return _child(arguments.configuration, arguments.status_fd)


if __name__ == "__main__":
    raise SystemExit(_main())
