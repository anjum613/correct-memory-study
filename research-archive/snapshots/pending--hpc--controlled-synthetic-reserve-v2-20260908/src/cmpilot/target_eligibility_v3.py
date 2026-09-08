"""Fail-closed SusVibes target eligibility and U-to-R integrity for V3."""

from __future__ import annotations

import hashlib
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

from cmpilot.source_pairing import stable_record_hash
from cmpilot.susvibes_feasibility import MATRIX_RESULTS, touched_files, tree_sha256


TARGET_ELIGIBILITY_SCHEMA = "cmpilot-target-eligibility-evidence-v3"
FEATURE_RETENTION_SCHEMA = "cmpilot-feature-retention-v3"
U_TO_R_INTEGRITY_SCHEMA = "cmpilot-u-to-r-integrity-v3"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_INSTANCE_ID = re.compile(r"^[A-Za-z0-9.-]+__[^/]+_[0-9a-f]{40}$")


class TargetEligibilityV3Error(ValueError):
    """Target evidence is malformed or fails a mandatory integrity invariant."""


def _require_sha256(value: Any, name: str) -> str:
    rendered = str(value)
    if not _SHA256.fullmatch(rendered):
        raise TargetEligibilityV3Error(f"{name} is not a SHA-256 digest")
    return rendered


def validate_distinct_tree_states(tree_hashes: Mapping[str, Any]) -> None:
    """Require exact, pairwise-distinct non-Git B/U/R tree states."""

    if set(tree_hashes) != {"B", "U", "R"}:
        raise TargetEligibilityV3Error("B/U/R tree hash fields changed")
    hashes = {state: _require_sha256(tree_hashes[state], state) for state in ("B", "U", "R")}
    if len(set(hashes.values())) != 3:
        raise TargetEligibilityV3Error("B/U/R tree states are not pairwise distinct")


def _validate_patch_paths(patch: str) -> tuple[str, ...]:
    paths = touched_files(patch)
    if not paths:
        raise TargetEligibilityV3Error("designated security patch has no declared paths")
    for value in paths:
        path = PurePosixPath(value)
        if path.is_absolute() or not path.parts or ".." in path.parts:
            raise TargetEligibilityV3Error("designated security patch path is unsafe")
    return paths


def verify_u_to_r_integrity(
    *,
    target_id: str,
    clean_u: Path,
    expected_u_tree_sha256: str,
    expected_r_tree_sha256: str,
    designated_security_patch: str,
    scratch_parent: Path,
) -> dict[str, Any]:
    """Apply the designated repair to clean U and compare its non-Git hash to R.

    This is the same relationship used in SusVibes feasibility: materialize
    clean U, apply the exact ``security_patch``, hash the resulting filesystem
    while excluding Git metadata, and require exact equality with R.
    """

    if not isinstance(target_id, str) or not _INSTANCE_ID.fullmatch(target_id):
        raise TargetEligibilityV3Error("invalid SusVibes target identity")
    u_root = Path(clean_u).resolve(strict=True)
    scratch = Path(scratch_parent).resolve(strict=True)
    if not u_root.is_dir() or u_root.is_symlink():
        raise TargetEligibilityV3Error("clean U must be a real directory")
    if not scratch.is_dir() or scratch.is_symlink():
        raise TargetEligibilityV3Error("integrity scratch parent must be a real directory")
    expected_u = _require_sha256(expected_u_tree_sha256, "expected U tree")
    expected_r = _require_sha256(expected_r_tree_sha256, "expected R tree")
    actual_u = tree_sha256(u_root)
    if actual_u != expected_u:
        raise TargetEligibilityV3Error("clean U tree hash does not match sealed evidence")
    if not isinstance(designated_security_patch, str) or not designated_security_patch.strip():
        raise TargetEligibilityV3Error("designated security patch is empty")
    patch_paths = _validate_patch_paths(designated_security_patch)
    patch_sha256 = hashlib.sha256(designated_security_patch.encode("utf-8")).hexdigest()
    with tempfile.TemporaryDirectory(prefix="cmpilot-u-to-r-v3-", dir=scratch) as temporary:
        materialized = Path(temporary) / "u-to-r"
        shutil.copytree(u_root, materialized, symlinks=True)
        check = subprocess.run(
            ["git", "apply", "--ignore-space-change", "--check", "-"],
            cwd=materialized,
            input=designated_security_patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if check.returncode:
            return {
                "schema": U_TO_R_INTEGRITY_SCHEMA,
                "target_id": target_id,
                "designated_security_patch_sha256": patch_sha256,
                "designated_security_patch_touched_files": list(patch_paths),
                "clean_u_tree_sha256": actual_u,
                "result_tree_sha256": None,
                "r_tree_sha256": expected_r,
                "patch_check_exit_code": check.returncode,
                "patch_apply_exit_code": None,
                "status": "FAIL",
                "exact_non_git_tree_match": False,
                "failure": "DESIGNATED_SECURITY_PATCH_DOES_NOT_APPLY_TO_CLEAN_U",
            }
        applied = subprocess.run(
            ["git", "apply", "--ignore-space-change", "-"],
            cwd=materialized,
            input=designated_security_patch,
            capture_output=True,
            text=True,
            check=False,
        )
        if applied.returncode:
            return {
                "schema": U_TO_R_INTEGRITY_SCHEMA,
                "target_id": target_id,
                "designated_security_patch_sha256": patch_sha256,
                "designated_security_patch_touched_files": list(patch_paths),
                "clean_u_tree_sha256": actual_u,
                "result_tree_sha256": None,
                "r_tree_sha256": expected_r,
                "patch_check_exit_code": check.returncode,
                "patch_apply_exit_code": applied.returncode,
                "status": "FAIL",
                "exact_non_git_tree_match": False,
                "failure": "DESIGNATED_SECURITY_PATCH_APPLICATION_FAILED",
            }
        result_hash = tree_sha256(materialized)
    exact = result_hash == expected_r
    return {
        "schema": U_TO_R_INTEGRITY_SCHEMA,
        "target_id": target_id,
        "designated_security_patch_sha256": patch_sha256,
        "designated_security_patch_touched_files": list(patch_paths),
        "clean_u_tree_sha256": actual_u,
        "result_tree_sha256": result_hash,
        "r_tree_sha256": expected_r,
        "patch_check_exit_code": check.returncode,
        "patch_apply_exit_code": applied.returncode,
        "status": "PASS" if exact else "FAIL",
        "exact_non_git_tree_match": exact,
        "failure": None if exact else "PATCHED_U_TREE_DOES_NOT_EQUAL_DESIGNATED_R",
    }


def validate_u_to_r_integrity(
    value: Mapping[str, Any], *, target_id: str, u_tree_sha256: str, r_tree_sha256: str
) -> None:
    required = {
        "schema",
        "target_id",
        "designated_security_patch_sha256",
        "designated_security_patch_touched_files",
        "clean_u_tree_sha256",
        "result_tree_sha256",
        "r_tree_sha256",
        "patch_check_exit_code",
        "patch_apply_exit_code",
        "status",
        "exact_non_git_tree_match",
        "failure",
    }
    if set(value) != required or value.get("schema") != U_TO_R_INTEGRITY_SCHEMA:
        raise TargetEligibilityV3Error("U-to-R integrity evidence schema changed")
    if value["target_id"] != target_id:
        raise TargetEligibilityV3Error("U-to-R integrity target mismatch")
    _require_sha256(value["designated_security_patch_sha256"], "security patch")
    if not isinstance(value["designated_security_patch_touched_files"], list) or not value[
        "designated_security_patch_touched_files"
    ]:
        raise TargetEligibilityV3Error("U-to-R integrity has no touched files")
    if value["clean_u_tree_sha256"] != u_tree_sha256:
        raise TargetEligibilityV3Error("U-to-R integrity is not bound to U")
    if value["r_tree_sha256"] != r_tree_sha256:
        raise TargetEligibilityV3Error("U-to-R integrity is not bound to R")
    if (
        value["status"] != "PASS"
        or value["exact_non_git_tree_match"] is not True
        or value["patch_check_exit_code"] != 0
        or value["patch_apply_exit_code"] != 0
        or value["result_tree_sha256"] != r_tree_sha256
        or value["failure"] is not None
    ):
        raise TargetEligibilityV3Error("designated security repair does not transform U to exact R")


def validate_feature_retention(
    value: Mapping[str, Any], *, target_id: str
) -> None:
    required = {
        "schema",
        "target_id",
        "requested_functionality",
        "feature_test_sha256",
        "u_execution",
        "r_execution",
        "same_requested_functionality",
        "general_test_inference_only",
    }
    if set(value) != required or value.get("schema") != FEATURE_RETENTION_SCHEMA:
        raise TargetEligibilityV3Error("feature-retention evidence schema changed")
    if value["target_id"] != target_id:
        raise TargetEligibilityV3Error("feature-retention target mismatch")
    if not isinstance(value["requested_functionality"], str) or not value[
        "requested_functionality"
    ].strip():
        raise TargetEligibilityV3Error("requested functionality is not explicit")
    feature_hash = _require_sha256(value["feature_test_sha256"], "feature test")
    execution_fields = {
        "classification",
        "feature_test_sha256",
        "execution_evidence_sha256",
    }
    for state in ("u_execution", "r_execution"):
        execution = value[state]
        if not isinstance(execution, Mapping) or set(execution) != execution_fields:
            raise TargetEligibilityV3Error("feature-retention execution fields changed")
        if execution["classification"] != "PASS":
            raise TargetEligibilityV3Error("requested functionality did not pass in both U and R")
        if execution["feature_test_sha256"] != feature_hash:
            raise TargetEligibilityV3Error("U and R did not run the same requested-feature test")
        _require_sha256(execution["execution_evidence_sha256"], f"{state} evidence")
    if value["same_requested_functionality"] is not True:
        raise TargetEligibilityV3Error("R does not retain the same requested functionality")
    if value["general_test_inference_only"] is not False:
        raise TargetEligibilityV3Error("feature retention was inferred only from general tests")


def evaluate_target_eligibility(evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Evaluate the complete V3 target matrix with infrastructure separation."""

    required = {
        "schema",
        "target_id",
        "task_results",
        "focal_security_results",
        "tree_hashes",
        "u_to_r_integrity",
        "feature_retention",
    }
    if set(evidence) != required or evidence.get("schema") != TARGET_ELIGIBILITY_SCHEMA:
        raise TargetEligibilityV3Error("target eligibility evidence schema changed")
    target_id = evidence["target_id"]
    if not isinstance(target_id, str) or not _INSTANCE_ID.fullmatch(target_id):
        raise TargetEligibilityV3Error("target eligibility has invalid target identity")
    task = evidence["task_results"]
    expected_task_fields = {
        "B_UNTOUCHED",
        "B_EMPTY_PATCH",
        "B_DETERMINISTIC_IRRELEVANT_EDIT",
        "U",
        "R",
    }
    security = evidence["focal_security_results"]
    if not isinstance(task, Mapping) or set(task) != expected_task_fields:
        raise TargetEligibilityV3Error("target task matrix fields changed")
    if not isinstance(security, Mapping) or set(security) != {"U", "R"}:
        raise TargetEligibilityV3Error("focal-security matrix fields changed")
    values = {**{f"TASK_{key}": value for key, value in task.items()}, **{
        f"FOCAL_SECURITY_{key}": value for key, value in security.items()
    }}
    if any(value not in MATRIX_RESULTS for value in values.values()):
        raise TargetEligibilityV3Error("target matrix has an unknown result classification")
    infrastructure = sorted(
        name for name, value in values.items() if value == "INFRASTRUCTURE_INVALID"
    )
    checks: dict[str, bool] = {
        "B_UNTOUCHED_TASK_FAIL": task["B_UNTOUCHED"] == "FAIL",
        "B_EMPTY_PATCH_TASK_FAIL": task["B_EMPTY_PATCH"] == "FAIL",
        "B_DETERMINISTIC_IRRELEVANT_EDIT_TASK_FAIL": task[
            "B_DETERMINISTIC_IRRELEVANT_EDIT"
        ]
        == "FAIL",
        "U_TASK_PASS": task["U"] == "PASS",
        "R_TASK_PASS": task["R"] == "PASS",
        "U_FOCAL_SECURITY_FAIL": security["U"] == "FAIL",
        "R_FOCAL_SECURITY_PASS": security["R"] == "PASS",
    }
    try:
        validate_distinct_tree_states(evidence["tree_hashes"])
    except (TypeError, TargetEligibilityV3Error):
        checks["BUR_DISTINCT_TREE_STATES"] = False
    else:
        checks["BUR_DISTINCT_TREE_STATES"] = True
    try:
        validate_u_to_r_integrity(
            evidence["u_to_r_integrity"],
            target_id=target_id,
            u_tree_sha256=evidence["tree_hashes"].get("U"),
            r_tree_sha256=evidence["tree_hashes"].get("R"),
        )
    except (AttributeError, TypeError, TargetEligibilityV3Error):
        checks["U_TO_R_INTEGRITY_PASS"] = False
    else:
        checks["U_TO_R_INTEGRITY_PASS"] = True
    try:
        validate_feature_retention(evidence["feature_retention"], target_id=target_id)
    except (TypeError, TargetEligibilityV3Error):
        checks["FEATURE_RETENTION_PASS"] = False
    else:
        checks["FEATURE_RETENTION_PASS"] = True
    semantic_failures = sorted(name for name, passed in checks.items() if not passed)
    if infrastructure:
        status = "INFRASTRUCTURE_INVALID"
    elif semantic_failures:
        status = "REJECT"
    else:
        status = "PASS"
    return {
        "schema": "cmpilot-target-eligibility-decision-v3",
        "target_id": target_id,
        "status": status,
        "eligible": status == "PASS",
        "checks": checks,
        "infrastructure_failures": infrastructure,
        "semantic_failures": semantic_failures,
        "rollback_accepted": False,
        "feature_deletion_accepted": False,
        "unrelated_secure_state_accepted": False,
        "evidence_sha256": stable_record_hash(evidence),
    }
