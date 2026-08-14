#!/usr/bin/env python3
"""Self-contained unprivileged Landlock capability probe.

The unrestricted parent creates and verifies a disposable fixture.  A child
applies Landlock with PR_SET_NO_NEW_PRIVS, runs the access/inheritance matrix,
and reports through its already-open stdout pipe.  No user namespace is used.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable


SCHEMA = "cmpilot-landlock-capability-gate-v1"
LANDLOCK_UNAVAILABLE = "LANDLOCK_UNAVAILABLE"
LANDLOCK_AVAILABLE_BUT_INSUFFICIENT = "LANDLOCK_AVAILABLE_BUT_INSUFFICIENT"
LANDLOCK_AVAILABLE_AND_USABLE = "LANDLOCK_AVAILABLE_AND_USABLE"
PROBE_IMPLEMENTATION_ERROR = "PROBE_IMPLEMENTATION_ERROR"

LANDLOCK_CREATE_RULESET_VERSION = 1
LANDLOCK_RULE_PATH_BENEATH = 1
PR_SET_NO_NEW_PRIVS = 38
PR_GET_NO_NEW_PRIVS = 39

# Landlock syscall numbers are allocated consistently on the architectures
# used by this project.  Unknown architectures fail explicitly.
LANDLOCK_SYSCALLS = {
    "aarch64": (444, 445, 446),
    "x86_64": (444, 445, 446),
}

# (name, bit, minimum Landlock ABI).  Unsupported known rights are reported,
# never silently added or ignored.
KNOWN_FS_RIGHTS = (
    ("EXECUTE", 1 << 0, 1),
    ("WRITE_FILE", 1 << 1, 1),
    ("READ_FILE", 1 << 2, 1),
    ("READ_DIR", 1 << 3, 1),
    ("REMOVE_DIR", 1 << 4, 1),
    ("REMOVE_FILE", 1 << 5, 1),
    ("MAKE_CHAR", 1 << 6, 1),
    ("MAKE_DIR", 1 << 7, 1),
    ("MAKE_REG", 1 << 8, 1),
    ("MAKE_SOCK", 1 << 9, 1),
    ("MAKE_FIFO", 1 << 10, 1),
    ("MAKE_BLOCK", 1 << 11, 1),
    ("MAKE_SYM", 1 << 12, 1),
    ("REFER", 1 << 13, 2),
    ("TRUNCATE", 1 << 14, 3),
    ("IOCTL_DEV", 1 << 15, 5),
)


class LandlockRulesetAttr(ctypes.Structure):
    _fields_ = [("handled_access_fs", ctypes.c_uint64)]


class LandlockPathBeneathAttr(ctypes.Structure):
    _pack_ = 1
    _fields_ = [
        ("allowed_access", ctypes.c_uint64),
        ("parent_fd", ctypes.c_int32),
    ]


LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.syscall.restype = ctypes.c_long
LIBC.prctl.restype = ctypes.c_int


def _errno_record(value: int) -> dict[str, Any]:
    return {
        "errno": value,
        "errno_name": errno.errorcode.get(value),
        "message": os.strerror(value) if value else None,
    }


def _syscall(number: int, *arguments: Any) -> tuple[int, dict[str, Any]]:
    ctypes.set_errno(0)
    result = int(LIBC.syscall(ctypes.c_long(number), *arguments))
    value = ctypes.get_errno() if result < 0 else 0
    return result, _errno_record(value)


def _prctl(option: int, argument: int = 0) -> tuple[int, dict[str, Any]]:
    ctypes.set_errno(0)
    result = int(
        LIBC.prctl(
            ctypes.c_int(option),
            ctypes.c_ulong(argument),
            ctypes.c_ulong(0),
            ctypes.c_ulong(0),
            ctypes.c_ulong(0),
        )
    )
    value = ctypes.get_errno() if result < 0 else 0
    return result, _errno_record(value)


def query_landlock_abi() -> dict[str, Any]:
    machine = platform.machine().casefold()
    numbers = LANDLOCK_SYSCALLS.get(machine)
    if numbers is None:
        return {
            "available": False,
            "abi": None,
            "machine": machine,
            "reason": "unsupported-probe-architecture",
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


def _rights_for_abi(abi: int) -> tuple[int, list[str], list[dict[str, Any]]]:
    supported = [name for name, _, minimum in KNOWN_FS_RIGHTS if abi >= minimum]
    unsupported = [
        {"name": name, "minimum_abi": minimum}
        for name, _, minimum in KNOWN_FS_RIGHTS
        if abi < minimum
    ]
    mask = sum(bit for _, bit, minimum in KNOWN_FS_RIGHTS if abi >= minimum)
    return mask, supported, unsupported


def _rights_mask(abi: int, names: set[str]) -> int:
    return sum(
        bit
        for name, bit, minimum in KNOWN_FS_RIGHTS
        if abi >= minimum and name in names
    )


def _runtime_paths() -> list[tuple[Path, str]]:
    candidates: list[tuple[Path, str]] = []
    for raw in ("/usr", "/bin", "/lib", "/lib64", "/etc"):
        path = Path(raw)
        if path.exists():
            candidates.append((path, "runtime-read-execute"))
    for raw in (sys.prefix, sys.base_prefix, str(Path(sys.executable).parent)):
        path = Path(raw)
        if path.exists():
            candidates.append((path, "python-runtime-read-execute"))
    for raw in ("/dev/null", "/dev/urandom", "/dev/random"):
        path = Path(raw)
        if path.exists():
            candidates.append((path, "runtime-device"))

    unique: list[tuple[Path, str]] = []
    seen: set[tuple[int, int]] = set()
    for path, role in candidates:
        resolved = path.resolve(strict=True)
        information = resolved.stat()
        identity = (information.st_dev, information.st_ino)
        if identity not in seen:
            seen.add(identity)
            unique.append((resolved, role))
    return unique


def _add_path_rule(
    *,
    add_rule_number: int,
    ruleset_fd: int,
    path: Path,
    allowed_access: int,
    role: str,
) -> dict[str, Any]:
    descriptor = -1
    try:
        descriptor = os.open(path, os.O_PATH | os.O_CLOEXEC)
        attribute = LandlockPathBeneathAttr(
            allowed_access=allowed_access,
            parent_fd=descriptor,
        )
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
            "allowed_access": allowed_access,
            "success": result == 0,
            "result": result,
            **error,
        }
    except OSError as error:
        return {
            "path": str(path),
            "role": role,
            "allowed_access": allowed_access,
            "success": False,
            "result": -1,
            **_errno_record(error.errno or 0),
        }
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def apply_landlock(allowed: Path) -> dict[str, Any]:
    availability = query_landlock_abi()
    record: dict[str, Any] = {
        "availability": availability,
        "user_namespace_used": False,
        "user_namespace_required": None,
        "rules": [],
    }
    abi = availability.get("abi")
    if not availability["available"] or not isinstance(abi, int):
        return record

    handled, supported, unsupported = _rights_for_abi(abi)
    record.update(
        {
            "handled_access_fs": handled,
            "supported_rights": supported,
            "unsupported_known_rights": unsupported,
        }
    )
    create_number, add_number, restrict_number = LANDLOCK_SYSCALLS[
        availability["machine"]
    ]
    attribute = LandlockRulesetAttr(handled_access_fs=handled)
    ruleset_fd, create_error = _syscall(
        create_number,
        ctypes.byref(attribute),
        ctypes.c_size_t(ctypes.sizeof(attribute)),
        ctypes.c_uint32(0),
    )
    record["ruleset_creation"] = {
        "success": ruleset_fd >= 0,
        "result": ruleset_fd,
        **create_error,
    }
    if ruleset_fd < 0:
        return record

    try:
        full_allowed = handled
        record["rules"].append(
            _add_path_rule(
                add_rule_number=add_number,
                ruleset_fd=ruleset_fd,
                path=allowed.resolve(strict=True),
                allowed_access=full_allowed,
                role="task-allowed-read-write",
            )
        )
        for path, role in _runtime_paths():
            if role == "runtime-device":
                names = {"READ_FILE", "WRITE_FILE"}
            elif path.is_dir():
                names = {"EXECUTE", "READ_FILE", "READ_DIR"}
            else:
                names = {"EXECUTE", "READ_FILE"}
            record["rules"].append(
                _add_path_rule(
                    add_rule_number=add_number,
                    ruleset_fd=ruleset_fd,
                    path=path,
                    allowed_access=_rights_mask(abi, names),
                    role=role,
                )
            )

        record["rule_addition"] = {
            "success": bool(record["rules"])
            and all(rule["success"] for rule in record["rules"]),
            "count": len(record["rules"]),
            "failed": sum(not rule["success"] for rule in record["rules"]),
        }
        if not record["rule_addition"]["success"]:
            return record

        before, before_error = _prctl(PR_GET_NO_NEW_PRIVS)
        set_result, set_error = _prctl(PR_SET_NO_NEW_PRIVS, 1)
        after, after_error = _prctl(PR_GET_NO_NEW_PRIVS)
        record["no_new_privs"] = {
            "before": before,
            "before_error": before_error,
            "set_result": set_result,
            "set_error": set_error,
            "after": after,
            "after_error": after_error,
            "success": set_result == 0 and after == 1,
        }
        if not record["no_new_privs"]["success"]:
            return record

        restrict_result, restrict_error = _syscall(
            restrict_number,
            ctypes.c_int(ruleset_fd),
            ctypes.c_uint32(0),
        )
        record["restrict_self"] = {
            "success": restrict_result == 0,
            "result": restrict_result,
            **restrict_error,
        }
        if restrict_result == 0:
            record["user_namespace_required"] = False
        return record
    finally:
        os.close(ruleset_fd)


def _allowed_operation(name: str, operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        value = operation()
    except OSError as error:
        return {
            "name": name,
            "allowed": False,
            "value": None,
            **_errno_record(error.errno or 0),
        }
    return {
        "name": name,
        "allowed": True,
        "value": value,
        **_errno_record(0),
    }


def _denied_operation(name: str, operation: Callable[[], Any]) -> dict[str, Any]:
    try:
        value = operation()
    except OSError as error:
        return {
            "name": name,
            "blocked": error.errno in {errno.EACCES, errno.EPERM},
            "unexpected_value": None,
            **_errno_record(error.errno or 0),
        }
    return {
        "name": name,
        "blocked": False,
        "unexpected_value": value,
        **_errno_record(0),
    }


def _write_text(path: Path, value: str, mode: str) -> str:
    with path.open(mode, encoding="utf-8") as stream:
        stream.write(value)
    return value


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _json_stdout(completed: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    try:
        return json.loads(completed.stdout)
    except (json.JSONDecodeError, TypeError):
        return {"parse_error": True, "stdout": completed.stdout}


def _inheritance_checks(allowed_file: Path, denied_file: Path) -> dict[str, Any]:
    check_code = (
        "import json,sys; from pathlib import Path; "
        "denied=Path(sys.argv[1]); allowed=Path(sys.argv[2]); "
        "blocked=False; err=None; "
        "\ntry:\n denied.read_text()\nexcept OSError as e:\n blocked=e.errno in (1,13); err=e.errno\n"
        "payload={'denied_blocked':blocked,'denied_errno':err,"
        "'allowed_read':allowed.read_text()}; print(json.dumps(payload)); "
        "sys.exit(0 if blocked and payload['allowed_read']=='allowed-readable\\n' else 7)"
    )
    python_child = subprocess.run(
        [sys.executable, "-I", "-c", check_code, str(denied_file), str(allowed_file)],
        text=True,
        capture_output=True,
        check=False,
    )
    python_payload = _json_stdout(python_child)

    shell_child = subprocess.run(
        [
            "/bin/sh",
            "-c",
            'cat "$1" >/dev/null 2>&1; denied=$?; '
            'value=$(cat "$2" 2>/dev/null); allowed=$?; '
            '[ "$denied" -ne 0 ] && [ "$allowed" -eq 0 ] '
            '&& [ "$value" = "allowed-readable" ]',
            "landlock-shell",
            str(denied_file),
            str(allowed_file),
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    denied_exec = subprocess.run(
        ["/usr/bin/cat", str(denied_file)],
        text=True,
        capture_output=True,
        check=False,
    )
    allowed_exec = subprocess.run(
        ["/usr/bin/cat", str(allowed_file)],
        text=True,
        capture_output=True,
        check=False,
    )

    middle_code = (
        "import json,subprocess,sys; "
        "p=subprocess.Popen([sys.executable,'-I','-c',sys.argv[1],sys.argv[2],sys.argv[3]],"
        "text=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE); "
        "out,err=p.communicate(); "
        "print(json.dumps({'grandchild_pid':p.pid,'returncode':p.returncode,"
        "'stdout':out,'stderr':err})); sys.exit(0 if p.returncode==0 else 8)"
    )
    middle = subprocess.Popen(
        [
            sys.executable,
            "-I",
            "-c",
            middle_code,
            check_code,
            str(denied_file),
            str(allowed_file),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    middle_stdout, middle_stderr = middle.communicate(timeout=15)
    try:
        middle_payload = json.loads(middle_stdout)
    except json.JSONDecodeError:
        middle_payload = {"parse_error": True, "stdout": middle_stdout}
    grandchild_pid = middle_payload.get("grandchild_pid")

    return {
        "python_child": {
            "pass": python_child.returncode == 0
            and python_payload.get("denied_blocked") is True,
            "returncode": python_child.returncode,
            "payload": python_payload,
            "stderr": python_child.stderr,
        },
        "shell_child": {
            "pass": shell_child.returncode == 0,
            "returncode": shell_child.returncode,
            "stderr": shell_child.stderr,
        },
        "exec_child": {
            "pass": denied_exec.returncode != 0
            and allowed_exec.returncode == 0
            and allowed_exec.stdout == "allowed-readable\n",
            "denied_returncode": denied_exec.returncode,
            "allowed_returncode": allowed_exec.returncode,
            "denied_stderr": denied_exec.stderr,
        },
        "grandchild": {
            "pass": middle.returncode == 0
            and isinstance(grandchild_pid, int)
            and not _pid_alive(grandchild_pid),
            "middle_pid": middle.pid,
            "middle_returncode": middle.returncode,
            "middle_stderr": middle_stderr,
            "payload": middle_payload,
            "grandchild_alive_after_wait": (
                _pid_alive(grandchild_pid) if isinstance(grandchild_pid, int) else None
            ),
        },
        "middle_child_alive_after_wait": _pid_alive(middle.pid),
    }


def _walk_allowed(allowed: Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    entries: list[str] = []

    def on_error(error: OSError) -> None:
        errors.append({"path": error.filename, **_errno_record(error.errno or 0)})

    for root, directories, files in os.walk(allowed, followlinks=True, onerror=on_error):
        relative_root = Path(root).relative_to(allowed)
        entries.extend(
            (relative_root / name).as_posix() for name in [*directories, *files]
        )
    denied_descendant_discovered = any(
        entry.endswith("secret.txt") or entry.endswith("metadata.txt")
        for entry in entries
    )
    alias_block_recorded = any(
        item.get("errno") in {errno.EACCES, errno.EPERM} for item in errors
    )
    return {
        "pass": not denied_descendant_discovered and alias_block_recorded,
        "entries": sorted(entries),
        "errors": errors,
        "denied_descendant_discovered": denied_descendant_discovered,
        "alias_block_recorded": alias_block_recorded,
    }


def run_sandbox_child(configuration: dict[str, str]) -> dict[str, Any]:
    allowed = Path(configuration["allowed"])
    denied = Path(configuration["denied"])
    readable = allowed / "readable.txt"
    writable = allowed / "writable.txt"
    secret = denied / "secret.txt"
    delete_target = denied / "delete-me.txt"
    alias = allowed / "denied-alias"

    setup = apply_landlock(allowed)
    result: dict[str, Any] = {
        "setup": setup,
        "process": {
            "pid": os.getpid(),
            "uid": os.getuid(),
            "euid": os.geteuid(),
            "user_namespace_used": False,
        },
    }
    ready = bool(
        setup.get("ruleset_creation", {}).get("success")
        and setup.get("rule_addition", {}).get("success")
        and setup.get("no_new_privs", {}).get("success")
        and setup.get("restrict_self", {}).get("success")
    )
    if not ready:
        result["matrix_complete"] = False
        return result

    allowed_results = {
        "read": _allowed_operation("allowed-read", lambda: readable.read_text()),
        "enumerate": _allowed_operation(
            "allowed-enumerate", lambda: sorted(path.name for path in allowed.iterdir())
        ),
        "create": _allowed_operation(
            "allowed-create",
            lambda: _write_text(allowed / "created.txt", "created\n", "w"),
        ),
        "modify": _allowed_operation(
            "allowed-modify", lambda: _write_text(writable, "modified\n", "w")
        ),
    }
    denied_results = {
        "read": _denied_operation("denied-read", lambda: secret.read_text()),
        "enumerate": _denied_operation(
            "denied-enumerate", lambda: sorted(path.name for path in denied.iterdir())
        ),
        "write": _denied_operation(
            "denied-write", lambda: _write_text(secret, "changed\n", "w")
        ),
        "delete": _denied_operation("denied-delete", lambda: delete_target.unlink()),
    }
    symlink_results = {
        "read": _denied_operation(
            "symlink-read", lambda: (alias / "secret.txt").read_text()
        ),
        "enumerate": _denied_operation(
            "symlink-enumerate", lambda: sorted(path.name for path in alias.iterdir())
        ),
    }
    inheritance = _inheritance_checks(readable, secret)
    traversal = _walk_allowed(allowed)

    result.update(
        {
            "matrix_complete": True,
            "allowed": allowed_results,
            "denied": denied_results,
            "symlink_alias": symlink_results,
            "broad_traversal": traversal,
            "inheritance": inheritance,
            "runtime_execution_compatible": all(
                inheritance[name]["pass"]
                for name in ("python_child", "shell_child", "exec_child")
            ),
        }
    )
    return result


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _all_matrix_checks_pass(child: dict[str, Any], parent: dict[str, Any]) -> bool:
    if not child.get("matrix_complete"):
        return False
    return bool(
        all(item.get("allowed") for item in child["allowed"].values())
        and all(item.get("blocked") for item in child["denied"].values())
        and all(item.get("blocked") for item in child["symlink_alias"].values())
        and child["broad_traversal"].get("pass")
        and all(
            child["inheritance"][name].get("pass")
            for name in ("python_child", "shell_child", "exec_child", "grandchild")
        )
        and child["inheritance"].get("middle_child_alive_after_wait") is False
        and child.get("runtime_execution_compatible")
        and parent.get("denied_integrity")
        and parent.get("allowed_effects")
        and parent.get("scratch_cleanup", {}).get("pass")
    )


def _classify(availability: dict[str, Any], child: dict[str, Any], parent: dict[str, Any]) -> str:
    if availability.get("reason") == "unsupported-probe-architecture":
        return PROBE_IMPLEMENTATION_ERROR
    if not availability.get("available"):
        return LANDLOCK_UNAVAILABLE
    if child.get("probe_transport_error"):
        return PROBE_IMPLEMENTATION_ERROR
    if _all_matrix_checks_pass(child, parent):
        return LANDLOCK_AVAILABLE_AND_USABLE
    return LANDLOCK_AVAILABLE_BUT_INSUFFICIENT


def _cleanup_twice(scratch: Path) -> dict[str, Any]:
    attempts = []
    for index in range(2):
        try:
            shutil.rmtree(scratch, ignore_errors=False)
        except FileNotFoundError:
            success = True
            error = None
        except OSError as exception:
            success = False
            error = f"{type(exception).__name__}: {exception}"
        else:
            success = True
            error = None
        attempts.append(
            {
                "attempt": index + 1,
                "success": success,
                "error": error,
                "exists_after": scratch.exists(),
            }
        )
    return {
        "attempts": attempts,
        "pass": all(item["success"] and not item["exists_after"] for item in attempts),
    }


def run_probe(*, scratch_parent: Path | None, batch_script: Path | None) -> dict[str, Any]:
    availability = query_landlock_abi()
    parent_record: dict[str, Any] = {}
    child_record: dict[str, Any] = {}
    scratch = Path(
        tempfile.mkdtemp(
            prefix="cmpilot-landlock-gate-",
            dir=None if scratch_parent is None else scratch_parent,
        )
    )
    try:
        allowed = scratch / "allowed"
        denied = scratch / "denied"
        nested = denied / "nested"
        allowed.mkdir()
        nested.mkdir(parents=True)
        (allowed / "readable.txt").write_text("allowed-readable\n", encoding="utf-8")
        (allowed / "writable.txt").write_text("allowed-original\n", encoding="utf-8")
        (denied / "secret.txt").write_text("denied-secret\n", encoding="utf-8")
        (denied / "delete-me.txt").write_text("must-survive\n", encoding="utf-8")
        (nested / "metadata.txt").write_text("denied-metadata\n", encoding="utf-8")
        (allowed / "denied-alias").symlink_to(denied, target_is_directory=True)

        configuration = json.dumps(
            {"allowed": str(allowed), "denied": str(denied)},
            sort_keys=True,
            separators=(",", ":"),
        )
        child = subprocess.run(
            [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "--sandbox-child",
                configuration,
            ],
            text=True,
            capture_output=True,
            check=False,
            timeout=30,
        )
        try:
            child_record = json.loads(child.stdout)
        except json.JSONDecodeError:
            child_record = {
                "probe_transport_error": True,
                "stdout": child.stdout,
            }
        child_record["transport"] = {
            "returncode": child.returncode,
            "stderr": child.stderr,
        }
        parent_record.update(
            {
                "denied_integrity": (
                    (denied / "secret.txt").read_text(encoding="utf-8")
                    == "denied-secret\n"
                    and (denied / "delete-me.txt").read_text(encoding="utf-8")
                    == "must-survive\n"
                    and (nested / "metadata.txt").read_text(encoding="utf-8")
                    == "denied-metadata\n"
                ),
                "allowed_effects": (
                    (allowed / "created.txt").read_text(encoding="utf-8") == "created\n"
                    and (allowed / "writable.txt").read_text(encoding="utf-8")
                    == "modified\n"
                ),
                "child_reaped": not _pid_alive(child_record.get("process", {}).get("pid", -1)),
            }
        )
    except BaseException as error:
        child_record = {
            "probe_transport_error": True,
            "exception_type": type(error).__name__,
            "exception_message": str(error),
        }
    finally:
        parent_record["scratch_path"] = str(scratch)
        parent_record["scratch_cleanup"] = _cleanup_twice(scratch)

    classification = _classify(availability, child_record, parent_record)
    batch_identity = None
    if batch_script is not None:
        batch_identity = {
            "path": str(batch_script),
            "sha256": _sha256(batch_script),
        }
    return {
        "schema": SCHEMA,
        "classification": classification,
        "environment": {
            "hostname": socket.gethostname(),
            "kernel_release": platform.release(),
            "machine": platform.machine(),
            "python_executable": sys.executable,
            "python_version": platform.python_version(),
            "slurm_job_id": os.environ.get("SLURM_JOB_ID"),
            "slurm_job_name": os.environ.get("SLURM_JOB_NAME"),
            "uid": os.getuid(),
            "euid": os.geteuid(),
        },
        "availability": availability,
        "user_namespace_used": False,
        "user_namespace_required": (
            False if classification == LANDLOCK_AVAILABLE_AND_USABLE else None
        ),
        "child": child_record,
        "parent_verification": parent_record,
        "batch_script": batch_identity,
    }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    parser.add_argument("--scratch-parent", type=Path)
    parser.add_argument("--batch-script", type=Path)
    parser.add_argument("--sandbox-child")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    if arguments.sandbox_child is not None:
        try:
            value = run_sandbox_child(json.loads(arguments.sandbox_child))
        except BaseException as error:
            value = {
                "probe_transport_error": True,
                "exception_type": type(error).__name__,
                "exception_message": str(error),
            }
        print(json.dumps(value, sort_keys=True))
        return 0 if not value.get("probe_transport_error") else 2
    if arguments.output is None:
        raise SystemExit("--output is required")
    value = run_probe(
        scratch_parent=arguments.scratch_parent,
        batch_script=arguments.batch_script,
    )
    _write_json(arguments.output, value)
    print(json.dumps({"classification": value["classification"], "output": str(arguments.output)}))
    return 2 if value["classification"] == PROBE_IMPLEMENTATION_ERROR else 0


if __name__ == "__main__":
    raise SystemExit(main())
