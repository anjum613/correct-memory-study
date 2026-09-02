#!/usr/bin/env python3
"""Execute the declared SusVibes development matrix without model inference.

Docker is not available on the target HPC.  This adapter pulls only the five
prospectively pinned Docker manifests through Singularity, expands each SIF,
and executes the read-only rootfs through unprivileged namespaces with a clean
/project bind.  Test patches, commands, parsers, and expected thresholds remain
byte-identical to SusVibes v1.0.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Any, Mapping, Sequence

from cmpilot.susvibes_feasibility import (
    BUR_STATES,
    DEVELOPMENT_IDS,
    ParsedRun,
    SUSVIBES_REVISION,
    SUSVIBES_TAG,
    TASK_STATES,
    canonical_json,
    classify_official_runs,
    deterministic_irrelevant_patch,
    normalize_state,
    parse_count_logs,
    patch_line_counts,
    sha256_bytes,
    sha256_file,
    split_development_row,
    touched_files,
    tree_sha256,
    validate_irrelevant_patch,
)


TEST_START_MARKER = "__CMPILOT_SUSVIBES_TEST_STARTED__"
TIMEOUT_SECONDS = 1800


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def du_bytes(path: Path) -> int:
    result = subprocess.run(
        ["du", "-sb", str(path)], capture_output=True, text=True, check=True
    )
    return int(result.stdout.split()[0])


def directory_file_count(path: Path) -> int:
    return sum(1 for item in path.rglob("*") if item.is_file() or item.is_symlink())


def parse_time_metrics(path: Path) -> dict[str, float | int | None]:
    values: dict[str, float | int | None] = {
        "elapsed_seconds": None,
        "user_seconds": None,
        "system_seconds": None,
        "maximum_rss_kb": None,
        "cpu_percent": None,
    }
    if not path.is_file():
        return values
    text = path.read_text(encoding="utf-8", errors="replace")
    patterns = {
        "user_seconds": (r"^User time \(seconds\):\s*([0-9.]+)$", float),
        "system_seconds": (r"^System time \(seconds\):\s*([0-9.]+)$", float),
        "maximum_rss_kb": (r"^Maximum resident set size \(kbytes\):\s*(\d+)$", int),
        "cpu_percent": (r"^Percent of CPU this job got:\s*(\d+)%$", int),
    }
    for key, (pattern, converter) in patterns.items():
        match = re.search(pattern, text, re.MULTILINE)
        if match:
            values[key] = converter(match.group(1))
    elapsed = re.search(r"^Elapsed \(wall clock\) time.*:\s*([^\n]+)$", text, re.MULTILINE)
    if elapsed:
        parts = elapsed.group(1).strip().split(":")
        try:
            if len(parts) == 3:
                values["elapsed_seconds"] = int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
            elif len(parts) == 2:
                values["elapsed_seconds"] = int(parts[0]) * 60 + float(parts[1])
            else:
                values["elapsed_seconds"] = float(parts[0])
        except ValueError:
            pass
    return values


def run_timed(
    command: Sequence[str],
    *,
    metrics_path: Path,
    timeout: int,
    environment: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    full = ["/usr/bin/time", "-v", "-o", str(metrics_path), *command]
    started = time.monotonic()
    process = subprocess.Popen(
        full,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        env=None if environment is None else dict(environment),
        start_new_session=True,
    )
    timed_out = False
    try:
        output, _ = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(process.pid, signal.SIGTERM)
        try:
            output, _ = process.communicate(timeout=30)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            output, _ = process.communicate()
    elapsed = time.monotonic() - started
    metrics = parse_time_metrics(metrics_path)
    metrics["measured_wall_seconds"] = round(elapsed, 6)
    return {
        "command": list(command),
        "exit_code": process.returncode,
        "timed_out": timed_out,
        "output": output,
        "metrics": metrics,
    }


def copy_tree(source: Path, destination: Path) -> float:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite materialized state: {destination}")
    started = time.monotonic()
    shutil.copytree(source, destination, symlinks=True)
    return time.monotonic() - started


def apply_patch(repository: Path, patch: str, *, reverse: bool = False) -> float:
    patch_path = repository / ".cmpilot-susvibes.patch"
    if patch_path.exists():
        raise FileExistsError(patch_path)
    patch_path.write_text(patch, encoding="utf-8")
    command = ["git", "apply", "--ignore-space-change"]
    if reverse:
        command.append("--reverse")
    command.append(patch_path.name)
    started = time.monotonic()
    try:
        result = subprocess.run(
            command,
            cwd=repository,
            capture_output=True,
            text=True,
            check=False,
        )
    finally:
        patch_path.unlink(missing_ok=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"patch failed in {repository}: {result.stdout}\n{result.stderr}"
        )
    return time.monotonic() - started


def state_operations(row: Mapping[str, Any], state: str) -> list[tuple[str, bool, str]]:
    normalized = normalize_state(row, state)
    return [
        (operation["patch"], operation["direction"] == "reverse", operation["role"])
        for operation in normalized["operations"]
    ]


def materialize_state(
    baseline: Path,
    destination: Path,
    row: Mapping[str, Any],
    state: str,
    *,
    security_first: bool = False,
) -> dict[str, Any]:
    copy_seconds = copy_tree(baseline, destination)
    operations: list[tuple[str, bool, str]] = []
    if security_first:
        operations.append((str(row["test_patch"]), False, "security_test"))
    operations.extend(state_operations(row, state))
    patch_seconds = 0.0
    for patch, reverse, _ in operations:
        patch_seconds += apply_patch(destination, patch, reverse=reverse)
    return {
        "copy_seconds": round(copy_seconds, 6),
        "patch_seconds": round(patch_seconds, 6),
        "total_seconds": round(copy_seconds + patch_seconds, 6),
        "operations": [
            {
                "role": role,
                "direction": "reverse" if reverse else "forward",
                "sha256": sha256_bytes(patch.encode()),
                "touched_files": list(touched_files(patch)),
            }
            for patch, reverse, role in operations
        ],
    }


def extract_project(singularity: str, image_path: Path, destination: Path) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to overwrite extracted B: {destination}")
    destination.mkdir(parents=True)
    started = time.monotonic()
    producer = subprocess.Popen(
        [
            singularity,
            "exec",
            "--containall",
            "--cleanenv",
            str(image_path),
            "/bin/tar",
            "-C",
            "/project",
            "-cf",
            "-",
            ".",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert producer.stdout is not None
    consumer = subprocess.run(
        ["tar", "--no-same-owner", "-C", str(destination), "-xf", "-"],
        stdin=producer.stdout,
        capture_output=True,
        check=False,
    )
    producer.stdout.close()
    producer_stderr = producer.stderr.read().decode(errors="replace") if producer.stderr else ""
    producer_exit = producer.wait()
    elapsed = time.monotonic() - started
    if producer_exit != 0 or consumer.returncode != 0:
        raise RuntimeError(
            f"B extraction failed: singularity={producer_exit}, tar={consumer.returncode}: "
            f"{producer_stderr}\n{consumer.stderr.decode(errors='replace')}"
        )
    return {
        "seconds": round(elapsed, 6),
        "bytes": du_bytes(destination),
        "file_count": directory_file_count(destination),
        "tree_sha256": tree_sha256(destination),
    }


def dockerfile_cmd(dockerfile: str) -> str:
    commands = [line[4:].strip() for line in dockerfile.splitlines() if line.startswith("CMD ")]
    if len(commands) != 1:
        raise RuntimeError(f"expected one Docker CMD, found {len(commands)}")
    command = commands[0]
    if command.startswith("["):
        values = json.loads(command)
        return " ".join(subprocess.list2cmdline([str(value)]) for value in values)
    return command


def run_test(
    *,
    rootfs_launcher: Path,
    rootfs: Path,
    repository: Path,
    test_command: str,
    log_path: Path,
    metrics_path: Path,
    logs_handler: Mapping[str, Any],
    environment: Mapping[str, str],
) -> tuple[ParsedRun, dict[str, Any]]:
    shell = (
        "cd /project && printf '"
        + TEST_START_MARKER
        + "\\n' && exec "
        + test_command
    )
    command = [
        str(rootfs_launcher.resolve()),
        str(rootfs.resolve()),
        str(repository.resolve()),
        "/bin/sh",
        "-lc",
        shell,
    ]
    result = run_timed(
        command,
        metrics_path=metrics_path,
        timeout=TIMEOUT_SECONDS,
        environment=environment,
    )
    raw_output = result.pop("output")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(raw_output, encoding="utf-8")
    runtime_started = TEST_START_MARKER in raw_output
    parser_logs = raw_output.replace(TEST_START_MARKER + "\n", "", 1)
    parsed = parse_count_logs(
        parser_logs,
        logs_handler=logs_handler,
        timed_out=bool(result["timed_out"]),
        command_exit=result["exit_code"],
        runtime_started=runtime_started,
    )
    result.update(
        {
            "test_command": test_command,
            "runtime_started": runtime_started,
            "log_path": str(log_path),
            "log_sha256": sha256_file(log_path),
            "log_bytes": log_path.stat().st_size,
            "parsed": parsed.as_dict(),
        }
    )
    return parsed, result


def read_rows(dataset_path: Path) -> dict[str, dict[str, Any]]:
    selected: dict[str, dict[str, Any]] = {}
    for line in dataset_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("instance_id") in DEVELOPMENT_IDS:
            selected[row["instance_id"]] = row
    if tuple(instance_id for instance_id in DEVELOPMENT_IDS if instance_id in selected) != DEVELOPMENT_IDS:
        raise RuntimeError("declared development rows missing")
    return selected


def text_line_corpus(root: Path) -> set[str]:
    values: set[str] = set()
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or path.stat().st_size > 5_000_000:
            continue
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                normalized = line.strip()
                if len(normalized) >= 8:
                    values.add(normalized)
        except (UnicodeDecodeError, OSError):
            continue
    return values


def distinctive_patch_lines(patch: str, prefix: str) -> set[str]:
    return {
        line[1:].strip()
        for line in patch.splitlines()
        if line.startswith(prefix)
        and not line.startswith(prefix * 3)
        and len(line[1:].strip()) >= 8
    }


def masking_probe(row: Mapping[str, Any], baseline: Path) -> dict[str, Any]:
    corpus = text_line_corpus(baseline)
    vulnerable_lines = distinctive_patch_lines(str(row["mask_patch"]), "-")
    secure_lines = distinctive_patch_lines(str(row["golden_patch"]), "+")
    cve = str(row["cve_id"])
    cve_visible = any(cve.casefold() in line.casefold() for line in corpus)
    patch_artifacts = sorted(
        path.relative_to(baseline).as_posix()
        for path in baseline.rglob("*")
        if path.is_file() and any(token in path.name.casefold() for token in ("susvibes", "security_patch", "golden_patch", "mask_patch"))
    )
    git_count = subprocess.run(
        ["git", "rev-list", "--all", "--count"],
        cwd=baseline,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "mask_patch_sha256": sha256_bytes(str(row["mask_patch"]).encode()),
        "mask_touched_files": list(touched_files(str(row["mask_patch"]))),
        "mask_line_counts": patch_line_counts(str(row["mask_patch"])),
        "vulnerable_implementation_distinctive_lines": len(vulnerable_lines),
        "vulnerable_lines_absent_from_B": len(vulnerable_lines - corpus),
        "vulnerable_lines_present_elsewhere_in_B": len(vulnerable_lines & corpus),
        "secure_implementation_distinctive_lines": len(secure_lines),
        "secure_lines_absent_from_B": len(secure_lines - corpus),
        "secure_lines_present_elsewhere_in_B": len(secure_lines & corpus),
        "cve_identifier_visible_in_B": cve_visible,
        "patch_artifacts_visible_in_B": patch_artifacts,
        "git_history_commit_count": int(git_count.stdout.strip()) if git_count.returncode == 0 else None,
        "git_history_probe_exit": git_count.returncode,
    }


def pull_image(
    *,
    singularity: str,
    image: Mapping[str, Any],
    destination: Path,
    environment: Mapping[str, str],
) -> dict[str, Any]:
    if destination.exists():
        raise FileExistsError(f"refusing to reuse unverified image output: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    uri = f"docker://{image['image']}@{image['manifest_digest']}"
    metrics_path = destination.with_suffix(".pull.time.txt")
    tmp_root = Path(environment["SINGULARITY_TMPDIR"])
    before = set(tmp_root.glob("sbuild-tmp-cache-*"))
    result = run_timed(
        [singularity, "pull", "--disable-cache", str(destination), uri],
        metrics_path=metrics_path,
        timeout=TIMEOUT_SECONDS,
        environment=environment,
    )
    output = result.pop("output")
    recovered_from = None
    if result["exit_code"] == 0 and not destination.is_file():
        created = [path for path in tmp_root.glob("sbuild-tmp-cache-*") if path not in before]
        valid = []
        for path in created:
            probe = subprocess.run(
                [singularity, "sif", "list", str(path)], capture_output=True, text=True, check=False
            )
            if probe.returncode == 0 and "FS (Squashfs" in probe.stdout:
                valid.append(path)
        if len(valid) == 1:
            try:
                os.link(valid[0], destination)
            except OSError:
                shutil.copy2(valid[0], destination)
            recovered_from = str(valid[0])
    if result["exit_code"] != 0 or not destination.is_file():
        raise RuntimeError(f"Singularity pull failed for {uri}: {output}")
    result.update(
        {
            "uri": uri,
            "source_manifest_digest": image["manifest_digest"],
            "source_compressed_bytes": image["compressed_bytes"],
            "sif_bytes": destination.stat().st_size,
            "sif_sha256": sha256_file(destination),
            "pull_log_sha256": sha256_bytes(output.encode()),
            "recovered_from_singularity_tmp": recovered_from,
        }
    )
    return result


def build_rootfs(
    singularity: str,
    image_path: Path,
    rootfs: Path,
    environment: Mapping[str, str],
    metrics_root: Path,
) -> dict[str, Any]:
    result = run_timed(
        [singularity, "build", "--sandbox", str(rootfs), str(image_path)],
        metrics_path=metrics_root / "rootfs-build.time.txt",
        timeout=TIMEOUT_SECONDS,
        environment=environment,
    )
    output = result.pop("output")
    if result["exit_code"] != 0 or not rootfs.is_dir():
        raise RuntimeError(f"Singularity sandbox expansion failed: {output}")
    return {
        **result,
        "expanded_bytes": du_bytes(rootfs),
        "expanded_file_count": directory_file_count(rootfs),
        "build_log_sha256": sha256_bytes(output.encode()),
    }


def rootfs_startup_probe(
    *,
    rootfs_launcher: Path,
    rootfs: Path,
    repository: Path,
    environment: Mapping[str, str],
    metrics_path: Path,
) -> dict[str, Any]:
    result = run_timed(
        [str(rootfs_launcher), str(rootfs), str(repository), "/bin/true"],
        metrics_path=metrics_path,
        timeout=120,
        environment=environment,
    )
    output = result.pop("output")
    result["output_sha256"] = sha256_bytes(output.encode())
    if result["exit_code"] != 0:
        result["infrastructure_error"] = output
    return result


def verify_u_to_r(row: Mapping[str, Any], baseline: Path, r_hash: str, scratch: Path) -> dict[str, Any]:
    relationship = scratch / "u-to-r"
    materialization = materialize_state(
        baseline, relationship, row, "U_VULNERABLE_IMPLEMENTATION"
    )
    patch_seconds = apply_patch(relationship, str(row["security_patch"]))
    actual = tree_sha256(relationship)
    return {
        "security_patch_sha256": sha256_bytes(str(row["security_patch"]).encode()),
        "security_patch_touched_files": list(touched_files(str(row["security_patch"]))),
        "security_patch_line_counts": patch_line_counts(str(row["security_patch"])),
        "u_materialization": materialization,
        "patch_seconds": round(patch_seconds, 6),
        "result_tree_sha256": actual,
        "r_tree_sha256": r_hash,
        "applies_u_to_r": actual == r_hash,
    }


def stage_firewall(
    *,
    row: Mapping[str, Any],
    baseline: Path,
    root: Path,
    launcher: Path,
    python: str,
) -> dict[str, Any]:
    public, oracle = split_development_row(row)
    targets = root / "targets" / "public" / row["instance_id"]
    repository = targets / "repository"
    copy_tree(baseline, repository)
    (targets / "task.md").write_text(public.pop("problem_statement"), encoding="utf-8")
    write_json(targets / "public-metadata.json", public)
    sealed = root / "oracle_sealed" / row["instance_id"]
    sealed.mkdir(parents=True)
    for name, value in oracle.items():
        suffix = ".patch" if name.endswith("patch") else ".json"
        path = sealed / f"{name}{suffix}"
        if suffix == ".patch":
            path.write_text(str(value), encoding="utf-8")
        else:
            write_json(path, value)
    absolute_link = targets / "absolute-sealed-link"
    relative_link = targets / "relative-sealed-link"
    absolute_link.symlink_to(sealed / "test_patch.patch")
    relative_link.symlink_to(Path("../../../oracle_sealed") / row["instance_id"] / "test_patch.patch")
    probe = """
import json
from pathlib import Path
checks = {}
checks['public_task_readable'] = Path('/workspace/task.md').is_file()
for name, path in {
    'absolute_host_path': Path(%r),
    'relative_traversal': Path('/workspace/../../../oracle_sealed/%s/test_patch.patch'),
    'absolute_symlink': Path('/workspace/absolute-sealed-link'),
    'relative_symlink': Path('/workspace/relative-sealed-link'),
}.items():
    try:
        path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError, IsADirectoryError):
        checks[name] = not path.exists()
    else:
        checks[name] = False
print(json.dumps(checks, sort_keys=True))
raise SystemExit(0 if all(checks.values()) else 1)
""" % (str(sealed / "test_patch.patch"), row["instance_id"])
    environment = dict(os.environ)
    environment["CMPILOT_V2_SANDBOX_TMP_PARENT"] = str(root)
    result = subprocess.run(
        [str(launcher), str(targets.resolve()), python, "-c", probe],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
        env=environment,
    )
    checks = json.loads(result.stdout) if result.returncode == 0 else {}
    return {
        "layout_root": str(root),
        "public_path": str(targets),
        "sealed_path": str(sealed),
        "launcher": str(launcher),
        "exit_code": result.returncode,
        "stderr": result.stderr,
        "checks": checks,
        "pass": bool(checks) and all(checks.values()),
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    source = args.susvibes_root.resolve()
    if subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip() != SUSVIBES_REVISION:
        raise RuntimeError("SusVibes source revision mismatch")
    if subprocess.run(["git", "-C", str(source), "describe", "--tags", "--exact-match"], capture_output=True, text=True).stdout.strip() != SUSVIBES_TAG:
        raise RuntimeError("SusVibes source tag mismatch")
    if subprocess.run(["git", "-C", str(source), "status", "--porcelain"], capture_output=True, text=True).stdout:
        raise RuntimeError("SusVibes source checkout is dirty")

    image_manifest = json.loads(args.image_manifest.read_text(encoding="utf-8"))
    images = {row["instance_id"]: row for row in image_manifest["images"]}
    if tuple(images) != DEVELOPMENT_IDS:
        raise RuntimeError("development image manifest mismatch")
    dataset = source / "datasets/default/susvibes_dataset.jsonl"
    rows = read_rows(dataset)
    dockerfiles = json.loads((source / "susvibes/env_specs/default/dockerfile.json").read_text())
    log_handlers = json.loads((source / "susvibes/env_specs/default/logs_handler.json").read_text())

    runtime = args.runtime_root.resolve()
    if runtime.exists() and any(runtime.iterdir()):
        raise FileExistsError(f"runtime root must be absent or empty: {runtime}")
    runtime.mkdir(parents=True, exist_ok=True)
    artifacts = args.artifact_root.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    selected_ids = tuple(args.instance_id) if args.instance_id else DEVELOPMENT_IDS
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError("duplicate --instance-id")
    unknown_ids = set(selected_ids) - set(DEVELOPMENT_IDS)
    if unknown_ids:
        raise ValueError(f"undeclared development IDs: {sorted(unknown_ids)}")
    suffix = f".{args.run_label}" if args.run_label else ""
    log_root = artifacts / f"development-logs{suffix}"
    partial_path = artifacts / f"development-execution{suffix}.partial.json"
    result_path = artifacts / f"development-execution{suffix}.json"
    if log_root.exists() or partial_path.exists() or result_path.exists():
        raise FileExistsError(f"refusing to overwrite existing evidence namespace: {suffix or 'default'}")
    singularity = shutil.which("singularity")
    if not singularity:
        raise RuntimeError("Singularity unavailable")
    environment = {
        **os.environ,
        "SINGULARITY_CACHEDIR": str(runtime / "singularity-cache"),
        "SINGULARITY_TMPDIR": str(runtime / "singularity-tmp"),
    }
    Path(environment["SINGULARITY_CACHEDIR"]).mkdir()
    Path(environment["SINGULARITY_TMPDIR"]).mkdir()
    peak_disk = du_bytes(runtime)
    cases = []
    for index, instance_id in enumerate(selected_ids, start=1):
        print(f"[{index}/{len(selected_ids)}] {instance_id}: pull", flush=True)
        row = rows[instance_id]
        image_info = images[instance_id]
        case_root = runtime / "cases" / instance_id
        image_path = runtime / "images" / f"{instance_id}.sif"
        pull = pull_image(
            singularity=singularity,
            image=image_info,
            destination=image_path,
            environment=environment,
        )
        peak_disk = max(peak_disk, du_bytes(runtime))
        direct_singularity = run_timed(
            [singularity, "exec", "--containall", "--cleanenv", str(image_path), "/bin/true"],
            metrics_path=case_root / "image-metrics/direct-singularity.time.txt",
            timeout=120,
            environment=environment,
        )
        direct_output = direct_singularity.pop("output")
        direct_singularity["output_sha256"] = sha256_bytes(direct_output.encode())
        direct_singularity["failure"] = direct_output if direct_singularity["exit_code"] != 0 else None
        rootfs = case_root / "rootfs"
        rootfs_build = build_rootfs(
            singularity,
            image_path,
            rootfs,
            environment,
            case_root / "image-metrics",
        )
        print(f"[{index}/{len(selected_ids)}] {instance_id}: extract B", flush=True)
        baseline = case_root / "B"
        b_copy_seconds = copy_tree(rootfs / "project", baseline)
        b_materialization = {
            "seconds": round(rootfs_build["metrics"]["measured_wall_seconds"] + b_copy_seconds, 6),
            "rootfs_build": rootfs_build,
            "project_copy_seconds": round(b_copy_seconds, 6),
            "bytes": du_bytes(baseline),
            "file_count": directory_file_count(baseline),
            "tree_sha256": tree_sha256(baseline),
        }
        startup = rootfs_startup_probe(
            rootfs_launcher=args.rootfs_launcher.resolve(),
            rootfs=rootfs,
            repository=baseline,
            environment=environment,
            metrics_path=case_root / "image-metrics/rootfs-startup.time.txt",
        )
        if startup["exit_code"] != 0:
            raise RuntimeError(f"rootfs startup failed: {startup['infrastructure_error']}")
        runtime_probe = {
            "direct_singularity": direct_singularity,
            "rootfs_build": rootfs_build,
            "rootfs_startup": startup,
        }
        peak_disk = max(peak_disk, du_bytes(runtime))
        masking = masking_probe(row, baseline)
        test_command = dockerfile_cmd(dockerfiles[instance_id])
        state_results: dict[str, Any] = {}
        for state in TASK_STATES:
            print(f"[{index}/{len(selected_ids)}] {instance_id}: {state} func", flush=True)
            state_root = case_root / "states" / state
            func_repo = state_root / "func"
            func_materialization = materialize_state(baseline, func_repo, row, state)
            before_hash = tree_sha256(func_repo)
            func, func_run = run_test(
                rootfs_launcher=args.rootfs_launcher.resolve(),
                rootfs=rootfs,
                repository=func_repo,
                test_command=test_command,
                log_path=log_root / instance_id / state / "func.txt",
                metrics_path=log_root / instance_id / state / "func.time.txt",
                logs_handler=log_handlers[instance_id],
                environment=environment,
            )
            print(f"[{index}/{len(selected_ids)}] {instance_id}: {state} sec", flush=True)
            sec_repo = state_root / "sec"
            sec_materialization = materialize_state(
                baseline, sec_repo, row, state, security_first=True
            )
            sec, sec_run = run_test(
                rootfs_launcher=args.rootfs_launcher.resolve(),
                rootfs=rootfs,
                repository=sec_repo,
                test_command=test_command,
                log_path=log_root / instance_id / state / "sec.txt",
                metrics_path=log_root / instance_id / state / "sec.time.txt",
                logs_handler=log_handlers[instance_id],
                environment=environment,
            )
            official = classify_official_runs(func, sec, row["expected_pf"])
            state_results[state] = {
                "state_tree_sha256_before_tests": before_hash,
                "func_materialization": func_materialization,
                "sec_materialization": sec_materialization,
                "func_run": func_run,
                "sec_run": sec_run,
                "official_classification": official,
            }
            peak_disk = max(peak_disk, du_bytes(runtime))
        b_hash = state_results["B_UNTOUCHED"]["state_tree_sha256_before_tests"]
        u_hash = state_results["U_VULNERABLE_IMPLEMENTATION"]["state_tree_sha256_before_tests"]
        r_hash = state_results["R_SAFE_IMPLEMENTATION"]["state_tree_sha256_before_tests"]
        relationship = verify_u_to_r(
            row,
            baseline,
            r_hash,
            case_root / "relationship",
        )
        firewall = stage_firewall(
            row=row,
            baseline=baseline,
            root=case_root / "firewall",
            launcher=args.sandbox_launcher.resolve(),
            python=sys.executable,
        )
        peak_disk = max(peak_disk, du_bytes(runtime))
        cases.append(
            {
                "instance_id": instance_id,
                "record_sha256": sha256_bytes(canonical_json(row).rstrip(b"\n")),
                "image": {**image_info, "pull": pull, "runtime_probe": runtime_probe},
                "test_command": test_command,
                "security_test": {
                    "test_patch_sha256": sha256_bytes(str(row["test_patch"]).encode()),
                    "touched_files": list(touched_files(str(row["test_patch"]))),
                    "patch_bytes": len(str(row["test_patch"]).encode()),
                    "command": test_command,
                },
                "b_materialization": b_materialization,
                "state_results": state_results,
                "state_hashes": {"B": b_hash, "U": u_hash, "R": r_hash},
                "u_to_r_relationship": relationship,
                "masking_probe": masking,
                "oracle_firewall": firewall,
            }
        )
        write_json(partial_path, {"cases": cases})
    result = {
        "schema": "cmpilot-susvibes-development-execution-v1",
        "benchmark_revision": SUSVIBES_REVISION,
        "benchmark_tag": SUSVIBES_TAG,
        "development_ids": list(selected_ids),
        "run_label": args.run_label,
        "model_inference_executed": False,
        "runtime": {
            "adapter": "Singularity-expanded rootfs with unprivileged namespace/chroot execution",
            "network_mode": "host-equivalent connectivity matching the official Docker default",
            "rootfs_launcher": str(args.rootfs_launcher.resolve()),
            "singularity_path": singularity,
            "singularity_version": subprocess.check_output([singularity, "--version"], text=True).strip(),
            "timeout_seconds": TIMEOUT_SECONDS,
            "peak_runtime_disk_bytes": peak_disk,
        },
        "cases": cases,
    }
    write_json(result_path, result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--susvibes-root", type=Path, required=True)
    parser.add_argument("--runtime-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument(
        "--instance-id",
        action="append",
        choices=DEVELOPMENT_IDS,
        help="rerun only a prospectively declared development instance",
    )
    parser.add_argument(
        "--run-label",
        default="",
        choices=("", "infra-retry-1", "infra-retry-2", "infra-retry-3"),
        help="write a new immutable evidence namespace for an infrastructure retry",
    )
    parser.add_argument(
        "--image-manifest",
        type=Path,
        default=Path("protocols/susvibes-development-images-v1.json"),
    )
    parser.add_argument(
        "--sandbox-launcher", type=Path, default=Path("scripts/v2_agent_sandbox.sh")
    )
    parser.add_argument(
        "--rootfs-launcher", type=Path, default=Path("scripts/susvibes_rootfs_exec.sh")
    )
    args = parser.parse_args()
    run(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
