"""Post-lock, pair-specific focal source-safety validation for V3.

This module does not discover p-star from keywords and does not read target
implementations, patches, tests, or vulnerability metadata.  It validates an
explicit semantic binding between the locked pair's proposed p-star and an
already-executed source-side assertion.
"""

from __future__ import annotations

import ast
import re
import textwrap
from typing import Any, Mapping

from cmpilot.source_pairing import SourcePairingError, stable_record_hash, validate_pstar


PAIR_FOCAL_SAFETY_SCHEMA = "cmpilot-pair-focal-source-safety-v3"
CONFIRMATORY_FOCAL_SAFETY_LEVELS_V3 = frozenset({"A", "B"})
OLD_LEVEL_C_CONFIRMATORY_ELIGIBLE = False
SOURCE_SAFETY_INSUFFICIENT = "SOURCE_SAFETY_INSUFFICIENT"
FOCAL_SOURCE_SAFETY = "FOCAL_SOURCE_SAFETY"
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SourceSafetyV3Error(SourcePairingError):
    """The locked pair lacks substantively bound focal source-safety evidence."""


def _call_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        parent = _call_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr
    return None


def _assertion_node_exercises_operation(node_text: str, operation: str) -> bool:
    try:
        tree = ast.parse(textwrap.dedent(node_text))
    except SyntaxError:
        return False
    calls = [
        name
        for candidate in ast.walk(tree)
        if isinstance(candidate, ast.Call)
        for name in [_call_name(candidate.func)]
        if name
    ]
    has_assertion = any(isinstance(candidate, ast.Assert) for candidate in ast.walk(tree))
    has_assertion = has_assertion or any(
        name.split(".")[-1].startswith(("assert", "fail"))
        or name.split(".")[-1] == "raises"
        for name in calls
    )
    calls_operation = any(name.split(".")[-1] == operation for name in calls)
    return has_assertion and calls_operation


def _validate_lock(lock: Mapping[str, Any], source_entry: Mapping[str, Any]) -> None:
    required = {"target_id", "top_source_id", "pair_hash"}
    if not required <= set(lock):
        raise SourceSafetyV3Error("pair-specific safety requires a complete top-source lock")
    if lock["top_source_id"] != source_entry.get("source_id"):
        raise SourceSafetyV3Error("focal safety source differs from the locked top source")
    if lock.get("top_one") is not True or lock.get("rank_2_fallback") is not False:
        raise SourceSafetyV3Error("pair-specific safety requires the top-one no-fallback lock")
    body = {key: value for key, value in lock.items() if key != "pair_hash"}
    if stable_record_hash(body) != lock["pair_hash"]:
        raise SourceSafetyV3Error("pair-specific safety lock hash mismatch")


def _validate_binding(binding: Mapping[str, Any], pstar: Mapping[str, Any]) -> None:
    required = {
        "observable_objects",
        "operation",
        "quantifier_or_boundary",
        "expected_invariant",
        "named_objects_exercised",
        "named_operation_exercised",
        "boundary_or_quantifier_exercised",
        "expected_invariant_asserted",
    }
    if set(binding) != required:
        raise SourceSafetyV3Error("executable assertion binding fields changed")
    if binding["observable_objects"] != pstar["observable_objects"]:
        raise SourceSafetyV3Error("executable assertion does not bind the named p-star objects")
    if binding["operation"] != pstar["operation"]:
        raise SourceSafetyV3Error("executable assertion does not bind the named p-star operation")
    if binding["quantifier_or_boundary"] != pstar["quantifier_or_boundary"]:
        raise SourceSafetyV3Error("executable assertion does not bind the p-star boundary")
    if binding["expected_invariant"] != pstar["proposition"]:
        raise SourceSafetyV3Error("executable assertion does not bind the expected invariant")
    if any(binding[name] is not True for name in required if name.endswith(("exercised", "asserted"))):
        raise SourceSafetyV3Error("executable assertion binding is not substantive")


def _validate_executable_test(
    test: Mapping[str, Any],
    *,
    source_entry: Mapping[str, Any],
    pstar: Mapping[str, Any],
) -> None:
    required = {
        "command",
        "test_paths",
        "test_path_hashes",
        "test_node_sha256",
        "execution_result",
        "execution_evidence_sha256",
        "assertion_binding",
    }
    if set(test) != required:
        raise SourceSafetyV3Error("executable source-test evidence fields changed")
    historical = source_entry.get("focal_source_safety", {})
    if test["command"] != historical.get("evidence_command"):
        raise SourceSafetyV3Error("source-test command is not the recorded focal command")
    paths = test["test_paths"]
    if not isinstance(paths, list) or not paths:
        raise SourceSafetyV3Error("focal source-test paths are absent")
    if not set(paths) <= set(source_entry.get("source_test_paths", ())):
        raise SourceSafetyV3Error("focal source-test path is outside the source task tests")
    hashes = test["test_path_hashes"]
    recorded_hashes = historical.get("evidence_hashes", {})
    if not isinstance(hashes, dict) or set(hashes) != set(paths):
        raise SourceSafetyV3Error("focal source-test path hashes are incomplete")
    if any(
        not _SHA256.fullmatch(str(hashes[path]))
        or hashes[path] != recorded_hashes.get(path)
        for path in paths
    ):
        raise SourceSafetyV3Error("focal source-test path hash mismatch")
    if test["execution_result"] != "PASS":
        raise SourceSafetyV3Error("focal executable source test did not pass")
    if source_entry.get("source_task_test", {}).get("classification") != "PASS":
        raise SourceSafetyV3Error("recorded source task execution did not pass")
    if test["execution_evidence_sha256"] != stable_record_hash(
        source_entry["source_task_test"]
    ):
        raise SourceSafetyV3Error("source-test execution evidence hash mismatch")
    if test["test_node_sha256"] != source_entry.get("source_artifact_hashes", {}).get(
        "source_task"
    ):
        raise SourceSafetyV3Error("assertion-bearing source-test node hash mismatch")
    if not _assertion_node_exercises_operation(
        str(source_entry.get("source_task_description", "")), str(pstar["operation"])
    ):
        raise SourceSafetyV3Error(
            "assertion-bearing source-test node does not call the named operation"
        )
    _validate_binding(test["assertion_binding"], pstar)


def _validate_level_b_semantics(
    semantics: Mapping[str, Any] | None,
    *,
    source_entry: Mapping[str, Any],
    pstar: Mapping[str, Any],
) -> None:
    required = {
        "established_from_source_code_and_test_semantics",
        "source_code_sha256",
        "source_test_sha256",
        "observable_objects",
        "operation",
        "quantifier_or_boundary",
        "expected_invariant",
    }
    if not isinstance(semantics, Mapping) or set(semantics) != required:
        raise SourceSafetyV3Error("Level B source-semantic evidence fields changed")
    if semantics["established_from_source_code_and_test_semantics"] is not True:
        raise SourceSafetyV3Error("Level B source invariant was not explicitly established")
    if semantics["source_code_sha256"] != source_entry.get("source_artifact_hashes", {}).get(
        "source_file"
    ):
        raise SourceSafetyV3Error("Level B source-code hash mismatch")
    if semantics["source_test_sha256"] != source_entry.get("source_artifact_hashes", {}).get(
        "source_task"
    ):
        raise SourceSafetyV3Error("Level B source-test hash mismatch")
    semantic_binding = {
        "observable_objects": semantics["observable_objects"],
        "operation": semantics["operation"],
        "quantifier_or_boundary": semantics["quantifier_or_boundary"],
        "expected_invariant": semantics["expected_invariant"],
        "named_objects_exercised": True,
        "named_operation_exercised": True,
        "boundary_or_quantifier_exercised": True,
        "expected_invariant_asserted": True,
    }
    _validate_binding(semantic_binding, pstar)


def validate_pair_focal_safety(
    lock: Mapping[str, Any],
    source_entry: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate focal source safety only for the already-locked source pair."""

    _validate_lock(lock, source_entry)
    required = {
        "schema",
        "target_id",
        "top_source_id",
        "pair_hash",
        "level",
        "historical_level",
        "revalidation_kind",
        "claim_scope",
        "proposed_pstar",
        "executable_source_test",
        "source_semantics",
        "derived_after_top_source_lock",
        "source_only_safety_evidence",
        "target_fix_evidence_used",
    }
    if set(evidence) != required or evidence.get("schema") != PAIR_FOCAL_SAFETY_SCHEMA:
        raise SourceSafetyV3Error("pair focal-safety evidence schema changed")
    if (
        evidence["target_id"] != lock["target_id"]
        or evidence["top_source_id"] != lock["top_source_id"]
        or evidence["pair_hash"] != lock["pair_hash"]
    ):
        raise SourceSafetyV3Error("focal safety evidence is not bound to the locked pair")
    if evidence["derived_after_top_source_lock"] is not True:
        raise SourceSafetyV3Error("focal safety was evaluated before top-source lock")
    if evidence["source_only_safety_evidence"] is not True:
        raise SourceSafetyV3Error("focal source-safety evidence is not source-side")
    if evidence["target_fix_evidence_used"] is not False:
        raise SourceSafetyV3Error("focal source safety was backfit to a target fix")
    if evidence["claim_scope"] != FOCAL_SOURCE_SAFETY:
        raise SourceSafetyV3Error("source-safety claim exceeds the focal invariant")
    level = evidence["level"]
    if level not in CONFIRMATORY_FOCAL_SAFETY_LEVELS_V3:
        raise SourceSafetyV3Error("old Level C is not confirmatory eligible")
    historical_level = source_entry.get("focal_source_safety", {}).get("level")
    if evidence["historical_level"] != historical_level:
        raise SourceSafetyV3Error("historical focal-safety level was silently changed")
    if historical_level == "C":
        if evidence["revalidation_kind"] != "NEW_POST_LOCK_LEVEL_A_OR_B_EVIDENCE":
            raise SourceSafetyV3Error("old Level C lacks new A/B revalidation evidence")
    elif evidence["revalidation_kind"] != "POST_LOCK_REVALIDATION_OF_EXISTING_A_OR_B":
        raise SourceSafetyV3Error("existing A/B evidence was not re-evaluated post-lock")
    pstar = evidence["proposed_pstar"]
    validate_pstar(pstar)
    _validate_executable_test(
        evidence["executable_source_test"], source_entry=source_entry, pstar=pstar
    )
    if level == "B":
        _validate_level_b_semantics(
            evidence["source_semantics"], source_entry=source_entry, pstar=pstar
        )
    return {
        "schema": "cmpilot-pair-focal-source-safety-decision-v3",
        "target_id": lock["target_id"],
        "top_source_id": lock["top_source_id"],
        "pair_hash": lock["pair_hash"],
        "status": "PASS",
        "eligibility_level": level,
        "claim": FOCAL_SOURCE_SAFETY,
        "global_source_security_claimed": False,
        "old_level_c_confirmatory_eligible": False,
        "fallback_attempted": False,
        "evidence_sha256": stable_record_hash(evidence),
    }


def evaluate_pair_focal_safety(
    lock: Mapping[str, Any],
    source_entry: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a fail-closed V3 decision without selecting another source."""

    try:
        return validate_pair_focal_safety(lock, source_entry, evidence)
    except (KeyError, TypeError, ValueError, SourcePairingError) as error:
        return {
            "schema": "cmpilot-pair-focal-source-safety-decision-v3",
            "target_id": lock.get("target_id"),
            "top_source_id": lock.get("top_source_id"),
            "pair_hash": lock.get("pair_hash"),
            "status": SOURCE_SAFETY_INSUFFICIENT,
            "eligibility_level": None,
            "claim": None,
            "global_source_security_claimed": False,
            "old_level_c_confirmatory_eligible": False,
            "fallback_attempted": False,
            "reason": str(error),
        }
