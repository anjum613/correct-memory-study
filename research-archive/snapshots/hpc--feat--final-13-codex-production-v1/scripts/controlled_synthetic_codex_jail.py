#!/usr/bin/env python3
"""Create the minimal mount namespace used by the final Codex experiment."""

from __future__ import annotations

import argparse
import ctypes
import os
from pathlib import Path
import subprocess


parser = argparse.ArgumentParser()
parser.add_argument("--root", required=True)
parser.add_argument("--workspace", required=True)
parser.add_argument("--runtime", required=True)
parser.add_argument("--release", required=True)
parser.add_argument("command", nargs=argparse.REMAINDER)
arguments = parser.parse_args()
root = Path(arguments.root)


def mount(*args: object) -> None:
    subprocess.run(
        ["/bin/mount", *map(str, args)],
        check=True,
        stdout=subprocess.DEVNULL,
    )


mount("--make-rprivate", "/")
mount("-t", "tmpfs", "-o", "size=256m", "tmpfs", root)


def bind(source: str | Path, target: str, *, readonly: bool = False) -> None:
    source_path = Path(source)
    target_path = root / target.lstrip("/")
    if source_path.is_dir():
        target_path.mkdir(parents=True, exist_ok=True)
    else:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.touch()
    mount("--bind", source_path, target_path)
    if readonly:
        mount("-o", "remount,bind,ro", target_path)


for system_path in ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc"):
    if Path(system_path).exists():
        bind(system_path, system_path, readonly=True)
if Path("/run/systemd/resolve").exists():
    bind("/run/systemd/resolve", "/run/systemd/resolve", readonly=True)
for device in ("null", "zero", "full", "random", "urandom", "tty"):
    bind("/dev/" + device, "/dev/" + device)
for directory in (
    "proc",
    "tmp",
    "home/experiment",
    "dev/shm",
    "dev/pts",
    ".oldroot",
):
    (root / directory).mkdir(parents=True, exist_ok=True)
os.chmod(root / "tmp", 0o1777)
mount("-t", "proc", "proc", root / "proc")
mount("-t", "devpts", "-o", "newinstance,ptmxmode=0666", "devpts", root / "dev/pts")
(root / "dev/ptmx").symlink_to("pts/ptmx")
(root / "dev/fd").symlink_to("/proc/self/fd")
bind(arguments.workspace, "/workspace")
bind(arguments.runtime, "/runtime")
bind(arguments.release, "/opt/codex", readonly=True)

# pivot_root, unlike chroot, still permits Codex to create its nested command sandbox.
libc = ctypes.CDLL(None, use_errno=True)
os.chdir(root)
if libc.syscall(155, os.fsencode(root), os.fsencode(root / ".oldroot")) != 0:
    raise OSError(ctypes.get_errno(), "pivot_root failed")
os.chdir("/workspace")
if libc.umount2(b"/.oldroot", 2) != 0:
    raise OSError(ctypes.get_errno(), "old root detach failed")
os.rmdir("/.oldroot")

environment = {
    "PATH": "/usr/bin:/bin:/opt/codex/bin",
    "HOME": "/home/experiment",
    "CODEX_HOME": "/runtime/codex-home",
    "TMPDIR": "/tmp",
    "LANG": "C.UTF-8",
    "PYTHONPATH": "/workspace:/runtime",
    "PYTHONDONTWRITEBYTECODE": "1",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
}
command = arguments.command[1:] if arguments.command[:1] == ["--"] else arguments.command
if not command:
    raise SystemExit("no command supplied")
os.execvpe(command[0], command, environment)
