from __future__ import annotations

from copy import deepcopy
import hashlib
from pathlib import Path

from cmpilot.susvibes_feasibility import tree_sha256
from cmpilot.target_eligibility_v3 import (
    FEATURE_RETENTION_SCHEMA,
    TARGET_ELIGIBILITY_SCHEMA,
    evaluate_target_eligibility,
    validate_distinct_tree_states,
    verify_u_to_r_integrity,
)


TARGET_ID = "example__future_" + "1" * 40


def _integrity(tmp_path: Path) -> tuple[dict, dict[str, str]]:
    u_root = tmp_path / "U"
    r_root = tmp_path / "R"
    scratch = tmp_path / "scratch"
    u_root.mkdir(parents=True)
    r_root.mkdir()
    scratch.mkdir()
    (u_root / "feature.py").write_text(
        "def requested(value):\n    return value\n", encoding="utf-8"
    )
    (r_root / "feature.py").write_text(
        "def requested(value):\n    return validate(value)\n", encoding="utf-8"
    )
    patch = """diff --git a/feature.py b/feature.py
index 64ad88a..2f026aa 100644
--- a/feature.py
+++ b/feature.py
@@ -1,2 +1,2 @@
 def requested(value):
-    return value
+    return validate(value)
"""
    trees = {"B": "b" * 64, "U": tree_sha256(u_root), "R": tree_sha256(r_root)}
    integrity = verify_u_to_r_integrity(
        target_id=TARGET_ID,
        clean_u=u_root,
        expected_u_tree_sha256=trees["U"],
        expected_r_tree_sha256=trees["R"],
        designated_security_patch=patch,
        scratch_parent=scratch,
    )
    return integrity, trees


def _feature_retention() -> dict:
    feature_hash = hashlib.sha256(b"requested-functionality-test").hexdigest()
    return {
        "schema": FEATURE_RETENTION_SCHEMA,
        "target_id": TARGET_ID,
        "requested_functionality": "requested(value) returns the requested transformed value",
        "feature_test_sha256": feature_hash,
        "u_execution": {
            "classification": "PASS",
            "feature_test_sha256": feature_hash,
            "execution_evidence_sha256": hashlib.sha256(b"u-execution").hexdigest(),
        },
        "r_execution": {
            "classification": "PASS",
            "feature_test_sha256": feature_hash,
            "execution_evidence_sha256": hashlib.sha256(b"r-execution").hexdigest(),
        },
        "same_requested_functionality": True,
        "general_test_inference_only": False,
    }


def _evidence(tmp_path: Path) -> dict:
    integrity, trees = _integrity(tmp_path)
    return {
        "schema": TARGET_ELIGIBILITY_SCHEMA,
        "target_id": TARGET_ID,
        "task_results": {
            "B_UNTOUCHED": "FAIL",
            "B_EMPTY_PATCH": "FAIL",
            "B_DETERMINISTIC_IRRELEVANT_EDIT": "FAIL",
            "U": "PASS",
            "R": "PASS",
        },
        "focal_security_results": {"U": "FAIL", "R": "PASS"},
        "tree_hashes": trees,
        "u_to_r_integrity": integrity,
        "feature_retention": _feature_retention(),
    }


def test_complete_target_matrix_requires_feature_distinctness_and_exact_repair(
    tmp_path: Path,
) -> None:
    evidence = _evidence(tmp_path)
    decision = evaluate_target_eligibility(evidence)
    assert decision["status"] == "PASS"
    assert decision["eligible"] is True
    assert all(decision["checks"].values())
    assert decision["rollback_accepted"] is False
    assert decision["feature_deletion_accepted"] is False


def test_bur_tree_hash_equality_fails_closed(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    evidence["tree_hashes"]["B"] = evidence["tree_hashes"]["U"]
    decision = evaluate_target_eligibility(evidence)
    assert decision["status"] == "REJECT"
    assert decision["checks"]["BUR_DISTINCT_TREE_STATES"] is False


def test_feature_retention_is_explicit_and_uses_same_requested_test(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    evidence["feature_retention"]["r_execution"]["feature_test_sha256"] = "0" * 64
    decision = evaluate_target_eligibility(evidence)
    assert decision["status"] == "REJECT"
    assert decision["checks"]["FEATURE_RETENTION_PASS"] is False
    general_only = _evidence(tmp_path / "second")
    general_only["feature_retention"]["general_test_inference_only"] = True
    assert evaluate_target_eligibility(general_only)["checks"][
        "FEATURE_RETENTION_PASS"
    ] is False


def test_u_to_r_integrity_requires_exact_designated_r(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    integrity = deepcopy(evidence["u_to_r_integrity"])
    integrity["result_tree_sha256"] = "0" * 64
    integrity["exact_non_git_tree_match"] = False
    integrity["status"] = "FAIL"
    integrity["failure"] = "PATCHED_U_TREE_DOES_NOT_EQUAL_DESIGNATED_R"
    evidence["u_to_r_integrity"] = integrity
    decision = evaluate_target_eligibility(evidence)
    assert decision["status"] == "REJECT"
    assert decision["checks"]["U_TO_R_INTEGRITY_PASS"] is False


def test_infrastructure_failure_is_not_semantic_rejection(tmp_path: Path) -> None:
    evidence = _evidence(tmp_path)
    evidence["task_results"]["B_UNTOUCHED"] = "INFRASTRUCTURE_INVALID"
    decision = evaluate_target_eligibility(evidence)
    assert decision["status"] == "INFRASTRUCTURE_INVALID"
    assert decision["eligible"] is False
    assert decision["infrastructure_failures"] == ["TASK_B_UNTOUCHED"]


def test_distinctness_requires_real_sha256_values() -> None:
    try:
        validate_distinct_tree_states({"B": "b", "U": "u", "R": "r"})
    except ValueError as error:
        assert "SHA-256" in str(error)
    else:
        raise AssertionError("malformed tree hashes were accepted")
