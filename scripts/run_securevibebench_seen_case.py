#!/usr/bin/env python3
"""Run B/U/R security and strict task matrices in a rootless ARVO rootfs.

The rootfs must be an unmodified extraction of the pinned ``-vul`` image.  The
runner sources the SIF-captured OCI environment before invoking ARVO commands.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shlex
import subprocess
import time
from pathlib import Path
from typing import Any

from cmpilot.securevibebench_development import (
    SEEN_IDS,
    classify_security_result,
    guard_instance_access,
    load_seen_ids,
)


CHROOT_WRAPPER = r"""
set -e
rootfs="$1"
command="$2"
mount --make-rprivate /
mount --rbind /proc "$rootfs/proc"
mount --rbind /dev "$rootfs/dev"
mount --rbind /sys "$rootfs/sys"
mount --bind /etc/resolv.conf "$rootfs/etc/resolv.conf"
chroot "$rootfs" /bin/bash -lc "$command"
""".strip()

CONTAINER_ENV = 'for f in /.singularity.d/env/*.sh; do source "$f"; done; export TAR_OPTIONS=--no-same-owner'


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")


def parse_time_metrics(log: str) -> dict[str, Any]:
    patterns = {
        "maximum_rss_kb": r"Maximum resident set size \(kbytes\): (\d+)",
        "user_seconds": r"User time \(seconds\): ([0-9.]+)",
        "system_seconds": r"System time \(seconds\): ([0-9.]+)",
        "filesystem_outputs": r"File system outputs: (\d+)",
    }
    result: dict[str, Any] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, log)
        if match:
            result[key] = float(match.group(1)) if "seconds" in key else int(match.group(1))
    return result


def run_chroot(rootfs: Path, command: str, log_path: Path, timeout: int) -> dict[str, Any]:
    argv = [
        "/usr/bin/time",
        "-v",
        "unshare",
        "-Urm",
        "--map-root-user",
        "bash",
        "-lc",
        CHROOT_WRAPPER,
        "_",
        str(rootfs),
        command,
    ]
    started = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        exit_code: int | None = result.returncode
        output = result.stdout
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        exit_code = None
        output = (exc.stdout or b"") + b"\n[TIMEOUT]\n"
    elapsed = time.monotonic() - started
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_bytes(output)
    text = output.decode("utf-8", errors="replace")
    return {
        "command": command,
        "exit_code": exit_code,
        "timeout": timed_out,
        "elapsed_seconds": round(elapsed, 3),
        "log_path": str(log_path),
        "log_sha256": sha256(output),
        "log_size_bytes": len(output),
        **parse_time_metrics(text),
    }


def prepare(rootfs: Path, repo_cwd: str, commit: str, output: Path, label: str) -> dict[str, Any]:
    command = f"{CONTAINER_ENV}; cd {repo_cwd}; git reset --hard; git clean -fdx; git checkout -f {commit}; git status --porcelain"
    result = run_chroot(rootfs, command, output / f"prepare-{label}.log", timeout=300)
    if result["exit_code"] != 0:
        raise RuntimeError(f"failed to prepare {label}; see {result['log_path']}")
    return result


def irrelevant_patch(rootfs: Path, repo_cwd: str, output: Path) -> dict[str, Any]:
    repo = rootfs / repo_cwd.lstrip("/")
    names = subprocess.check_output(["git", "-C", str(repo), "ls-files"], text=True).splitlines()
    candidates = [name for name in names if Path(name).name.lower().startswith("readme")]
    if not candidates:
        raise RuntimeError("no tracked README available for irrelevant patch")
    name = sorted(candidates, key=lambda value: (value.count("/"), value))[0]
    path = repo / name
    marker = b"\nSecureVibeBench deterministic irrelevant development-matrix marker.\n"
    with path.open("ab") as handle:
        handle.write(marker)
    patch = subprocess.check_output(["git", "-C", str(repo), "diff", "--binary", "--", name])
    patch_path = output / "irrelevant.patch"
    patch_path.write_bytes(patch)
    return {"path": name, "patch_sha256": sha256(patch), "patch_size_bytes": len(patch), "patch_path": str(patch_path)}


def load_parser(path: Path):
    spec = importlib.util.spec_from_file_location("securevibebench_parse_test_report", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load parser {path}")
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def parsed_result(module: Any, parse_id: int, log: str) -> dict[str, Any]:
    value = module.parse_test_output(localid=parse_id, s=log)
    if value.__class__.__name__ == "BoolResult":
        return {"type": "BoolResult", "Status": bool(value.Status)}
    if value.__class__.__name__ == "ListResult":
        return {"type": "ListResult", "PassList": value.PassList, "FailList": value.FailList, "UnknownList": value.UnknownList}
    if value.__class__.__name__ == "NumberResult":
        return {"type": "NumberResult", "PassNumber": value.PassNumber, "FailNumber": value.FailNumber, "UnknownNumber": value.UnknownNumber}
    raise TypeError(value)


def benchmark_compare(candidate: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    if candidate["type"] == baseline["type"] == "BoolResult":
        passed = candidate["Status"] == baseline["Status"]
        return {"functional_pass": passed, "functional_compare_error": False, "comparison": "bool_equality"}
    if candidate["type"] == baseline["type"] == "ListResult":
        passed = set(baseline["PassList"]).issubset(candidate["PassList"])
        return {"functional_pass": passed, "functional_compare_error": False, "comparison": "baseline_pass_subset"}
    return {"functional_pass": False, "functional_compare_error": True, "comparison": "unsupported_parser_type"}


def security_matrix(args: argparse.Namespace, case: dict[str, str], output: Path) -> dict[str, Any]:
    matrix = {}
    security_cwd = case.get("security_cwd", case["repo_cwd"])
    for label in ("B", "U", "R"):
        prepare_result = prepare(args.rootfs, case["repo_cwd"], case[label], output / "security" / label, label)
        cleanup_paths = case.get("security_cleanup_paths", [])
        for path in cleanup_paths:
            if not path.startswith("/src/") or ".." in Path(path).parts:
                raise ValueError(f"unsafe security cleanup path: {path}")
        cleanup = None
        if cleanup_paths:
            cleanup_command = "rm -rf -- " + " ".join(shlex.quote(path) for path in cleanup_paths)
            cleanup = run_chroot(
                args.rootfs,
                cleanup_command,
                output / "security" / label / "cleanup.log",
                timeout=300,
            )
            if cleanup["exit_code"] != 0:
                raise RuntimeError(f"failed to clean derived security build paths for {label}")
        build = run_chroot(
            args.rootfs,
            f"{CONTAINER_ENV}; cd {security_cwd}; arvo compile",
            output / "security" / label / "build.log",
            timeout=args.build_timeout,
        )
        if build["exit_code"] == 0:
            pov = run_chroot(args.rootfs, f"{CONTAINER_ENV}; cd {security_cwd}; arvo", output / "security" / label / "pov.log", timeout=args.pov_timeout)
            log = (output / "security" / label / "pov.log").read_text(errors="replace")
        else:
            pov = {"exit_code": None, "timeout": False, "log_path": None}
            log = ""
        classification = classify_security_result(
            build_exit=build["exit_code"],
            pov_exit=pov["exit_code"],
            log=log,
            timeout=bool(build["timeout"] or pov["timeout"]),
        )
        matrix[label] = {
            "commit": case[label],
            "prepare": prepare_result,
            "derived_build_cleanup": cleanup,
            "rootless_tar_no_same_owner": True,
            "build": build,
            "pov": pov,
            **classification,
        }
        write_json(output / "security" / label / "result.json", matrix[label])
    return matrix


def functional_matrix(args: argparse.Namespace, case: dict[str, str], output: Path) -> dict[str, Any]:
    source_script = args.test_scripts / f"{case['test_script_id']}.sh"
    raw = source_script.read_bytes()
    filtered = b"".join(line for line in raw.splitlines(keepends=True) if not line.lstrip().startswith(b"git checkout"))
    target = args.rootfs / "tmp" / f"securevibebench-functional-{args.instance_id}.sh"
    target.write_bytes(filtered)
    os.chmod(target, 0o755)
    apt_override = args.rootfs / "etc" / "apt" / "apt.conf.d" / "99-securevibebench-rootless"
    apt_override.parent.mkdir(parents=True, exist_ok=True)
    apt_override.write_text('APT::Sandbox::User "root";\n')
    parser = load_parser(args.parser)
    parse_id = int(case["test_script_id"])
    variants = {
        "B_untouched": ("B", "untouched"),
        "B_empty": ("B", "empty_patch"),
        "B_irrelevant": ("B", "irrelevant_patch"),
        "U": ("U", "historical_vic"),
        "R": ("R", "historical_vfc"),
    }
    matrix: dict[str, Any] = {}
    for variant, (label, patch_kind) in variants.items():
        variant_output = output / "functional" / variant
        prep = prepare(args.rootfs, case["repo_cwd"], case[label], variant_output, variant)
        patch = {"kind": patch_kind, "patch_sha256": sha256(b""), "patch_size_bytes": 0}
        if patch_kind == "irrelevant_patch":
            patch.update(irrelevant_patch(args.rootfs, case["repo_cwd"], variant_output))
        command = f"{CONTAINER_ENV}; cd {case['repo_cwd']}; bash /tmp/{target.name}"
        run = run_chroot(args.rootfs, command, variant_output / "oracle.log", timeout=args.functional_timeout)
        log = (variant_output / "oracle.log").read_text(errors="replace")
        parsed = parsed_result(parser, parse_id, log)
        matrix[variant] = {"commit": case[label], "prepare": prep, "patch": patch, "oracle": run, "parsed": parsed}
    baseline = matrix["U"]["parsed"]
    for variant in matrix:
        matrix[variant].update(benchmark_compare(matrix[variant]["parsed"], baseline))
        write_json(output / "functional" / variant / "result.json", matrix[variant])
    matrix["_oracle"] = {
        "source_script": str(source_script),
        "source_script_sha256": sha256(raw),
        "filtered_script_sha256": sha256(filtered),
        "checkout_lines_removed": True,
        "parser": str(args.parser),
        "parser_sha256": sha256(args.parser.read_bytes()),
        "parse_id": parse_id,
        "rootless_runtime_accommodations": {
            "apt_sandbox_override": str(apt_override.relative_to(args.rootfs)),
            "apt_sandbox_override_sha256": sha256(apt_override.read_bytes()),
            "host_resolver_bind_mounted": True,
        },
    }
    return matrix


def main(args: argparse.Namespace) -> None:
    seen = load_seen_ids(args.seen_set)
    guard_instance_access(args.instance_id, seen, implementation_access=True)
    if not args.rootfs.is_dir():
        raise SystemExit(f"rootfs is missing: {args.rootfs}")
    config = json.loads(args.case_config.read_text())
    case = config["cases"][args.instance_id]
    output = args.output / "execution-logs" / args.instance_id
    result_path = output / "case-result.json"
    if result_path.exists():
        result = json.loads(result_path.read_text())
    else:
        result = {"instance_id": args.instance_id}
    result.update({"rootfs": str(args.rootfs), "cpu_cores": os.cpu_count()})
    if args.security:
        result["security_matrix"] = security_matrix(args, case, output)
    if args.functional:
        result["functional_matrix"] = functional_matrix(args, case, output)
    write_json(result_path, result)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--instance-id", required=True, choices=SEEN_IDS)
    result.add_argument("--rootfs", required=True, type=Path)
    result.add_argument("--seen-set", required=True, type=Path)
    result.add_argument("--case-config", required=True, type=Path)
    result.add_argument("--test-scripts", required=True, type=Path)
    result.add_argument("--parser", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--security", action="store_true")
    result.add_argument("--functional", action="store_true")
    result.add_argument("--build-timeout", type=int, default=1800)
    result.add_argument("--pov-timeout", type=int, default=120)
    result.add_argument("--functional-timeout", type=int, default=1800)
    return result


if __name__ == "__main__":
    main(parser().parse_args())
