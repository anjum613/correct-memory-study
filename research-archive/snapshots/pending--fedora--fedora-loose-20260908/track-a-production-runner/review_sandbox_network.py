#!/usr/bin/env python3
"""Exact, candidate-free network checks for the Track A reviewer sandbox."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile
from typing import Mapping, Sequence


CHATGPT_HOST = "chatgpt.com"
CHATGPT_HTTPS_URL = "https://chatgpt.com/"
NETWORK_PROBE_TIMEOUT_SECONDS = 30
SAFE_RUN_RESOLVER_TARGETS = frozenset(
    {
        PurePosixPath("/run/systemd/resolve/stub-resolv.conf"),
        PurePosixPath("/run/systemd/resolve/resolv.conf"),
        PurePosixPath("/run/NetworkManager/resolv.conf"),
        PurePosixPath("/run/NetworkManager/no-stub-resolv.conf"),
    }
)


class ReviewSandboxConfigurationError(ValueError):
    """The host resolver cannot be mapped into the reviewer sandbox safely."""


@dataclass(frozen=True, slots=True)
class ResolverMountPolicy:
    mode: str
    host_resolv_conf: Path
    namespace_target: PurePosixPath
    host_target: Path
    bwrap_arguments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SandboxNetworkProbe:
    passed: bool
    role: str
    resolver_mode: str
    resolver_target: str
    dns_status: str
    https_status: str
    retryable: bool
    reason: str


def _host_path(host_root: Path, namespace_path: PurePosixPath) -> Path:
    return host_root / Path(*namespace_path.parts[1:])


def _namespace_path(host_root: Path, resolved_host_path: Path) -> PurePosixPath:
    resolved_root = host_root.resolve(strict=True)
    try:
        relative = resolved_host_path.relative_to(resolved_root)
    except ValueError as error:
        raise ReviewSandboxConfigurationError(
            "resolver symlink resolves outside the selected host root"
        ) from error
    return PurePosixPath("/", *relative.parts)


def _directory_arguments(target: PurePosixPath) -> tuple[str, ...]:
    arguments: list[str] = []
    current = PurePosixPath("/")
    for part in target.parent.parts[1:]:
        current /= part
        arguments.extend(("--dir", str(current)))
    return tuple(arguments)


def resolve_resolver_mount_policy(
    *, host_root: Path = Path("/")
) -> ResolverMountPolicy:
    """Resolve /etc/resolv.conf and allow only exact known resolver targets."""

    host_root = host_root.resolve(strict=True)
    resolv_conf = host_root / "etc/resolv.conf"
    try:
        mode = resolv_conf.lstat().st_mode
    except OSError as error:
        raise ReviewSandboxConfigurationError(
            f"host /etc/resolv.conf is unavailable: {error}"
        ) from error
    if stat.S_ISREG(mode):
        return ResolverMountPolicy(
            mode="REGULAR_FILE_IN_ETC_BIND",
            host_resolv_conf=resolv_conf,
            namespace_target=PurePosixPath("/etc/resolv.conf"),
            host_target=resolv_conf,
            bwrap_arguments=(),
        )
    if not stat.S_ISLNK(mode):
        raise ReviewSandboxConfigurationError(
            "host /etc/resolv.conf is neither a regular file nor a symlink"
        )
    raw_target = os.readlink(resolv_conf)
    joined = (
        PurePosixPath(raw_target)
        if raw_target.startswith("/")
        else PurePosixPath("/etc") / raw_target
    )
    normalized = PurePosixPath(os.path.normpath(str(joined)))
    if not normalized.is_absolute():
        raise ReviewSandboxConfigurationError("resolver symlink target is not absolute")
    candidate = _host_path(host_root, normalized)
    try:
        resolved_host_target = candidate.resolve(strict=True)
    except OSError as error:
        raise ReviewSandboxConfigurationError(
            f"resolver symlink target is unavailable: {normalized}: {error}"
        ) from error
    namespace_target = _namespace_path(host_root, resolved_host_target)
    if namespace_target not in SAFE_RUN_RESOLVER_TARGETS:
        raise ReviewSandboxConfigurationError(
            f"unexpected resolver symlink target rejected: {namespace_target}"
        )
    if resolved_host_target.is_symlink() or not resolved_host_target.is_file():
        raise ReviewSandboxConfigurationError(
            f"resolved resolver target is not a regular file: {namespace_target}"
        )
    arguments = (
        *_directory_arguments(namespace_target),
        "--ro-bind",
        str(resolved_host_target),
        str(namespace_target),
    )
    return ResolverMountPolicy(
        mode="SAFE_RUN_TARGET_BIND",
        host_resolv_conf=resolv_conf,
        namespace_target=namespace_target,
        host_target=resolved_host_target,
        bwrap_arguments=tuple(arguments),
    )


def reviewer_bwrap_prefix(
    *,
    capsule: Path,
    process_output: Path,
    codex_install: Path,
    auth: Path,
    resolver_policy: ResolverMountPolicy,
    mount_resolver_target: bool = True,
) -> list[str]:
    """Build the one reviewer mount/network template used by probes and Codex."""

    resolver_arguments: Sequence[str] = (
        resolver_policy.bwrap_arguments if mount_resolver_target else ()
    )
    return [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-all",
        "--share-net",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/bin",
        "/bin",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--ro-bind",
        "/etc",
        "/etc",
        *resolver_arguments,
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--dir",
        "/home",
        "--dir",
        "/home/anjum",
        "--dir",
        "/home/anjum/.local",
        "--ro-bind",
        str(codex_install),
        str(codex_install),
        "--dir",
        "/review-home",
        "--dir",
        "/review-home/.codex",
        "--ro-bind",
        str(auth),
        "/review-home/.codex/auth.json",
        "--ro-bind",
        str(capsule),
        "/workspace",
        "--bind",
        str(process_output),
        "/output",
        "--setenv",
        "HOME",
        "/review-home",
        "--setenv",
        "CODEX_HOME",
        "/review-home/.codex",
        "--setenv",
        "PATH",
        "/home/anjum/.local/npm/bin:/usr/bin:/bin",
        "--chdir",
        "/workspace",
    ]


_PROBE_SCRIPT = r"""
set -eu
test -r /etc/resolv.conf
resolved_target=$(readlink -f /etc/resolv.conf)
test "$resolved_target" = "$1"
cat /etc/resolv.conf >/dev/null
getent ahosts chatgpt.com >/dev/null
echo DNS_OK
if command -v curl >/dev/null 2>&1; then
    https_status=$(curl --head --silent --show-error --max-time 15 --output /dev/null --write-out '%{http_code}' https://chatgpt.com/)
    test "$https_status" != "000"
    echo "HTTPS_STATUS=$https_status"
else
    echo HTTPS_STATUS=SKIPPED_NO_CURL
fi
"""


def probe_reviewer_sandbox_network(
    *,
    runner_root: Path,
    role: str,
    environment: Mapping[str, str],
    codex_home: Path | None = None,
    codex_install: Path = Path("/home/anjum/.local/npm"),
    host_root: Path = Path("/"),
    mount_resolver_target: bool = True,
    timeout_seconds: float = NETWORK_PROBE_TIMEOUT_SECONDS,
) -> SandboxNetworkProbe:
    """Probe DNS and optional HTTPS inside a harmless exact reviewer template."""

    try:
        policy = resolve_resolver_mount_policy(host_root=host_root)
        selected_home = codex_home or Path(
            os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))
        )
        auth = selected_home / "auth.json"
        if auth.is_symlink() or not auth.is_file():
            raise ReviewSandboxConfigurationError(
                "Codex authentication file unavailable for reviewer sandbox probe"
            )
        if codex_install.is_symlink() or not codex_install.is_dir():
            raise ReviewSandboxConfigurationError(
                "Codex installation tree unavailable for reviewer sandbox probe"
            )
        with tempfile.TemporaryDirectory(
            prefix="review-sandbox-network-preflight-", dir=runner_root
        ) as temporary:
            root = Path(temporary)
            capsule = root / "capsule"
            output = root / "output"
            capsule.mkdir()
            output.mkdir()
            command = reviewer_bwrap_prefix(
                capsule=capsule,
                process_output=output,
                codex_install=codex_install,
                auth=auth,
                resolver_policy=policy,
                mount_resolver_target=mount_resolver_target,
            )
            command.extend(
                [
                    "/bin/sh",
                    "-c",
                    _PROBE_SCRIPT,
                    "review-sandbox-network-preflight",
                    str(policy.namespace_target),
                ]
            )
            completed = subprocess.run(
                command,
                cwd=runner_root,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                env=dict(environment),
                timeout=timeout_seconds,
            )
    except ReviewSandboxConfigurationError as error:
        return SandboxNetworkProbe(
            False,
            role,
            "REJECTED",
            "UNAVAILABLE",
            "NOT_RUN",
            "NOT_RUN",
            False,
            str(error),
        )
    except subprocess.TimeoutExpired:
        return SandboxNetworkProbe(
            False,
            role,
            policy.mode,
            str(policy.namespace_target),
            "TIMEOUT",
            "TIMEOUT",
            True,
            f"review sandbox network probe exceeded {timeout_seconds:g}s",
        )
    except OSError as error:
        return SandboxNetworkProbe(
            False,
            role,
            policy.mode,
            str(policy.namespace_target),
            "ERROR",
            "NOT_RUN",
            False,
            f"review sandbox probe could not start: {type(error).__name__}: {error}",
        )
    output_lines = completed.stdout.splitlines()
    dns_ok = "DNS_OK" in output_lines
    https_rows = [line.split("=", 1)[1] for line in output_lines if line.startswith("HTTPS_STATUS=")]
    https_status = https_rows[-1] if https_rows else "NOT_REACHED"
    if completed.returncode == 0 and dns_ok and https_status != "NOT_REACHED":
        return SandboxNetworkProbe(
            True,
            role,
            policy.mode,
            str(policy.namespace_target),
            "PASS",
            https_status,
            False,
            "resolver target, DNS, and HTTPS reachability passed",
        )
    detail = completed.stderr.strip() or completed.stdout.strip() or "no probe output"
    return SandboxNetworkProbe(
        False,
        role,
        policy.mode,
        str(policy.namespace_target),
        "FAIL",
        https_status,
        True,
        f"review sandbox network probe exit={completed.returncode}: {detail[-500:]}",
    )
