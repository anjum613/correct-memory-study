"""Executable, artifact-bound SusVibes B/U/R gates for confirmatory V4."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from cmpilot.content_audit_v4 import ArtifactRef, ContentAccessAudit, TreeRef
from cmpilot.susvibes_feasibility import (
    IRRELEVANT_FILENAME,
    SUSVIBES_REVISION,
    tree_sha256,
)


class TargetRuntimeV4Error(RuntimeError):
    """A real target artifact or execution failed a frozen V4 gate."""


_SHA256 = re.compile(r"^[0-9a-f]{64}$")


def _sha(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _apply_patch(root: Path, patch: str, *, reverse: bool = False) -> None:
    if not patch.strip():
        raise TargetRuntimeV4Error("frozen benchmark patch is empty")
    command = ["git", "apply", "--ignore-space-change"]
    if reverse:
        command.append("--reverse")
    command.append("-")
    environment = {
        **os.environ,
        "GIT_CEILING_DIRECTORIES": str(root.parent.resolve(strict=True)),
    }
    checked = subprocess.run(
        [*command[:-1], "--check", "-"],
        cwd=root,
        input=patch,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    if checked.returncode:
        raise TargetRuntimeV4Error(
            "frozen benchmark patch does not apply: " + checked.stderr.strip()
        )
    applied = subprocess.run(
        command,
        cwd=root,
        input=patch,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    if applied.returncode:
        raise TargetRuntimeV4Error(
            "frozen benchmark patch application failed: " + applied.stderr.strip()
        )


def _dockerfile_command(dockerfile: str) -> str:
    commands = [line[4:].strip() for line in dockerfile.splitlines() if line.startswith("CMD ")]
    if len(commands) != 1:
        raise TargetRuntimeV4Error("feature definition must contain exactly one CMD")
    command = commands[0]
    if command.startswith("["):
        values = json.loads(command)
        if not isinstance(values, list) or not values:
            raise TargetRuntimeV4Error("feature definition CMD is malformed")
        return " ".join(subprocess.list2cmdline([str(value)]) for value in values)
    if not command:
        raise TargetRuntimeV4Error("feature definition CMD is empty")
    return command


@dataclass(frozen=True)
class BenchmarkRowBinding:
    target_id: str
    row_sha256: str
    benchmark_revision: str
    b_tree_sha256: str
    u_tree_sha256: str
    r_tree_sha256: str
    mask_patch_sha256: str
    golden_patch_sha256: str
    security_patch_sha256: str
    test_patch_sha256: str

    def __post_init__(self) -> None:
        if self.benchmark_revision != SUSVIBES_REVISION:
            raise TargetRuntimeV4Error("benchmark revision is not frozen SusVibes")
        for name, value in vars(self).items():
            if name.endswith("sha256") and not _SHA256.fullmatch(str(value)):
                raise TargetRuntimeV4Error(f"{name} is not a SHA-256 digest")


@dataclass(frozen=True)
class ExecutionEnvironment:
    """Exact non-model command wrapper used for target test execution."""

    argv_prefix: tuple[str, ...] = ()
    shell_executable: str = "/bin/sh"
    timeout_seconds: int = 1200
    environment: tuple[tuple[str, str], ...] = ()
    environment_identity: str = "LOCAL_TEST_ENVIRONMENT"

    def command(self, tree: Path, test_command: str) -> list[str]:
        if self.argv_prefix:
            return [
                *self.argv_prefix,
                str(tree),
                self.shell_executable,
                "-lc",
                "cd /project && exec " + test_command,
            ]
        return [self.shell_executable, "-lc", "cd " + subprocess.list2cmdline([str(tree)]) + " && exec " + test_command]


def load_bound_benchmark_row(
    audit: ContentAccessAudit,
    dataset: ArtifactRef,
    binding: BenchmarkRowBinding,
) -> dict[str, Any]:
    """Read the frozen dataset through the audit and verify the exact raw row."""

    payload = audit.read_bytes(
        dataset,
        target_id=binding.target_id,
        source_id=None,
        caller="target_runtime_v4.load_bound_benchmark_row",
    )
    selected: list[tuple[bytes, dict[str, Any]]] = []
    for raw_line in payload.splitlines():
        if not raw_line.strip():
            continue
        value = json.loads(raw_line)
        if value.get("instance_id") == binding.target_id:
            selected.append((raw_line, value))
    if len(selected) != 1:
        raise TargetRuntimeV4Error("frozen dataset does not contain exactly one target row")
    _, row = selected[0]
    canonical_row = json.dumps(
        row, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    if _sha(canonical_row) != binding.row_sha256:
        raise TargetRuntimeV4Error("frozen SusVibes row hash mismatch")
    for field in ("mask_patch", "golden_patch", "security_patch", "test_patch"):
        value = row.get(field)
        if not isinstance(value, str) or _sha(value.encode("utf-8")) != getattr(
            binding, f"{field}_sha256"
        ):
            raise TargetRuntimeV4Error(f"frozen {field} hash mismatch")
    return row


def load_feature_command(
    audit: ContentAccessAudit,
    definition: ArtifactRef,
    *,
    target_id: str,
) -> tuple[str, str]:
    """Derive the exact command from immutable SusVibes Dockerfile bytes."""

    payload = audit.read_bytes(
        definition,
        target_id=target_id,
        source_id=None,
        caller="target_runtime_v4.load_feature_command",
    )
    value = json.loads(payload)
    if not isinstance(value, Mapping) or target_id not in value:
        raise TargetRuntimeV4Error("feature definition omits target")
    dockerfile = value[target_id]
    if not isinstance(dockerfile, str):
        raise TargetRuntimeV4Error("target feature definition is not Dockerfile text")
    return _dockerfile_command(dockerfile), _sha(dockerfile.encode("utf-8"))


def _run(
    *,
    tree: Path,
    test_command: str,
    feature_test_sha256: str,
    environment: ExecutionEnvironment,
    state: str,
) -> dict[str, Any]:
    command = environment.command(tree, test_command)
    process_environment = {**os.environ, **dict(environment.environment)}
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=environment.timeout_seconds,
            env=process_environment,
            check=False,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as error:
        return {
            "state": state,
            "classification": "INFRASTRUCTURE_INVALID",
            "feature_test_sha256": feature_test_sha256,
            "command": command,
            "environment": environment.environment_identity,
            "exit_code": None,
            "stdout": b"",
            "stderr": str(error).encode("utf-8"),
            "stdout_sha256": _sha(b""),
            "stderr_sha256": _sha(str(error).encode("utf-8")),
        }
    combined = completed.stdout + b"\n" + completed.stderr
    infrastructure_failure = completed.returncode != 0 and re.search(
        rb"(?:ModuleNotFoundError|ImportError|FileNotFoundError|PermissionError|command not found)",
        combined,
    )
    return {
        "state": state,
        "classification": "PASS"
        if completed.returncode == 0
        else "INFRASTRUCTURE_INVALID"
        if infrastructure_failure
        else "FAIL",
        "feature_test_sha256": feature_test_sha256,
        "command": command,
        "environment": environment.environment_identity,
        "exit_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_sha256": _sha(completed.stdout),
        "stderr_sha256": _sha(completed.stderr),
    }


def _copy_clean(source: Path, destination: Path) -> None:
    if destination.exists():
        raise TargetRuntimeV4Error("refusing to overwrite a target materialization")
    shutil.copytree(
        source,
        destination,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git"),
    )


def _irrelevant_patch(target_id: str) -> str:
    content = (
        "# SusVibes feasibility probe\n"
        "\n"
        f"Development instance: `{target_id}`.\n"
        "\n"
        "This deterministic documentation-only file does not alter executable code, "
        "tests, dependencies, build configuration, or evaluator behavior.\n"
    )
    lines = content.splitlines()
    body = "\n".join(f"+{line}" for line in lines)
    return (
        f"diff --git a/{IRRELEVANT_FILENAME} b/{IRRELEVANT_FILENAME}\n"
        "new file mode 100644\n"
        "index 0000000..1111111\n"
        "--- /dev/null\n"
        f"+++ b/{IRRELEVANT_FILENAME}\n"
        f"@@ -0,0 +1,{len(lines)} @@\n"
        f"{body}\n"
    )


def execute_target_gates(
    *,
    audit: ContentAccessAudit,
    binding: BenchmarkRowBinding,
    dataset: ArtifactRef,
    baseline_b: TreeRef,
    feature_definition: ArtifactRef,
    environment: ExecutionEnvironment,
    scratch_parent: Path,
) -> dict[str, Any]:
    """Reconstruct and execute every target-side V4 eligibility gate.

    No caller-supplied result or integrity boolean is accepted. B, U and R are
    rebuilt from the exact frozen row, hashed independently, and tested using
    the same command derived from the same feature-definition bytes.
    """

    row = load_bound_benchmark_row(audit, dataset, binding)
    b_source = audit.verify_tree(
        baseline_b,
        target_id=binding.target_id,
        source_id=None,
        caller="target_runtime_v4.execute_target_gates",
    )
    test_command, feature_test_sha256 = load_feature_command(
        audit, feature_definition, target_id=binding.target_id
    )
    scratch = Path(scratch_parent).resolve(strict=True)
    if not scratch.is_dir() or scratch.is_symlink():
        raise TargetRuntimeV4Error("target scratch parent must be a real directory")
    with tempfile.TemporaryDirectory(prefix="cmpilot-v4-target-", dir=scratch) as temporary:
        root = Path(temporary)
        states = {name: root / name for name in ("B", "U", "R")}
        _copy_clean(b_source, states["B"])
        _copy_clean(b_source, states["U"])
        _apply_patch(states["U"], row["mask_patch"], reverse=True)
        _copy_clean(b_source, states["R"])
        _apply_patch(states["R"], row["golden_patch"])
        observed_hashes = {name: tree_sha256(path) for name, path in states.items()}
        expected_hashes = {
            "B": binding.b_tree_sha256,
            "U": binding.u_tree_sha256,
            "R": binding.r_tree_sha256,
        }
        if observed_hashes != expected_hashes:
            raise TargetRuntimeV4Error("reconstructed B/U/R tree hash mismatch")
        if len(set(observed_hashes.values())) != 3:
            raise TargetRuntimeV4Error("B/U/R trees are not pairwise distinct")

        feature: dict[str, dict[str, Any]] = {}
        for state in ("B", "U", "R"):
            execution_tree = root / f"{state}_FEATURE_EXECUTION"
            _copy_clean(states[state], execution_tree)
            feature[state] = _run(
                tree=execution_tree,
                test_command=test_command,
                feature_test_sha256=feature_test_sha256,
                environment=environment,
                state=state,
            )
        feature_pass = [feature[state]["classification"] for state in ("B", "U", "R")] == [
            "FAIL",
            "PASS",
            "PASS",
        ]

        empty_b = root / "B_EMPTY"
        irrelevant_b = root / "B_IRRELEVANT"
        _copy_clean(states["B"], empty_b)
        _copy_clean(states["B"], irrelevant_b)
        irrelevant = _irrelevant_patch(binding.target_id)
        _apply_patch(irrelevant_b, irrelevant)
        b_variants = {
            "B_UNTOUCHED": feature["B"],
            "B_EMPTY_PATCH": _run(
                tree=empty_b,
                test_command=test_command,
                feature_test_sha256=feature_test_sha256,
                environment=environment,
                state="B_EMPTY_PATCH",
            ),
            "B_DETERMINISTIC_IRRELEVANT_EDIT": _run(
                tree=irrelevant_b,
                test_command=test_command,
                feature_test_sha256=feature_test_sha256,
                environment=environment,
                state="B_DETERMINISTIC_IRRELEVANT_EDIT",
            ),
        }

        security: dict[str, dict[str, Any]] = {}
        for state in ("U", "R"):
            security_tree = root / f"{state}_SECURITY"
            _copy_clean(states[state], security_tree)
            _apply_patch(security_tree, row["test_patch"])
            security[state] = _run(
                tree=security_tree,
                test_command=test_command,
                feature_test_sha256=feature_test_sha256,
                environment=environment,
                state=f"{state}_FOCAL_SECURITY",
            )

        reconstructed = root / "U_TO_R"
        _copy_clean(states["U"], reconstructed)
        _apply_patch(reconstructed, row["security_patch"])
        reconstructed_hash = tree_sha256(reconstructed)
        integrity_pass = reconstructed_hash == observed_hashes["R"]

        reverted = root / "FEATURE_REVERSION"
        _copy_clean(states["U"], reverted)
        _apply_patch(reverted, row["mask_patch"])
        reversion_hash = tree_sha256(reverted)
        if reversion_hash != observed_hashes["B"]:
            raise TargetRuntimeV4Error("exact mask reversion does not reconstruct B")
        reversion = _run(
            tree=reverted,
            test_command=test_command,
            feature_test_sha256=feature_test_sha256,
            environment=environment,
            state="DIRECT_FEATURE_REVERSION",
        )

        task_matrix = {
            **{name: result["classification"] for name, result in b_variants.items()},
            "U": feature["U"]["classification"],
            "R": feature["R"]["classification"],
        }
        security_matrix = {
            state: security[state]["classification"] for state in ("U", "R")
        }
        expected_task = {
            "B_UNTOUCHED": "FAIL",
            "B_EMPTY_PATCH": "FAIL",
            "B_DETERMINISTIC_IRRELEVANT_EDIT": "FAIL",
            "U": "PASS",
            "R": "PASS",
        }
        eligible = (
            task_matrix == expected_task
            and security_matrix == {"U": "FAIL", "R": "PASS"}
            and feature_pass
            and integrity_pass
            and reversion["classification"] == "FAIL"
        )
        executions = {
            "feature": feature,
            "b_variants": b_variants,
            "focal_security": security,
            "feature_reversion": reversion,
        }
        execution_hashes: dict[str, Any] = {
            group: {
                key: _sha(
                    json.dumps(
                        {
                            name: value
                            for name, value in result.items()
                            if name not in {"stdout", "stderr"}
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ).encode("utf-8")
                )
                for key, result in values.items()
            }
            for group, values in executions.items()
            if group != "feature_reversion" and isinstance(values, Mapping)
        }
        execution_hashes["feature_reversion"] = _sha(
            json.dumps(
                {
                    name: value
                    for name, value in reversion.items()
                    if name not in {"stdout", "stderr"}
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
        technical_invalid = any(
            result["classification"] == "INFRASTRUCTURE_INVALID"
            for group in executions.values()
            for result in (
                group.values()
                if isinstance(group, Mapping) and "classification" not in group
                else (group,)
            )
            if isinstance(result, Mapping) and "classification" in result
        )
        return {
            "target_id": binding.target_id,
            "benchmark_revision": binding.benchmark_revision,
            "susvibes_row_sha256": binding.row_sha256,
            "patch_hashes": {
                name: getattr(binding, f"{name}_sha256")
                for name in ("mask_patch", "golden_patch", "security_patch", "test_patch")
            },
            "tree_hashes": observed_hashes,
            "pairwise_distinct": True,
            "feature_test_sha256": feature_test_sha256,
            "feature_test_command": test_command,
            "environment": environment.environment_identity,
            "task_matrix": task_matrix,
            "focal_security_matrix": security_matrix,
            "feature_retention": "PASS" if feature_pass else "FAIL",
            "feature_reversion": reversion["classification"],
            "u_to_r_result_tree_sha256": reconstructed_hash,
            "u_to_r_integrity": "PASS" if integrity_pass else "FAIL",
            "execution_hashes": execution_hashes,
            "technical_invalid": technical_invalid,
            "status": "PASS" if eligible else "REJECT",
            "evaluated_model_inference": False,
        }
