"""Development-only V3 re-evaluation from preserved, already-seen evidence."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from cmpilot.pair_review import PAIR_REVIEW_QUESTIONS
from cmpilot.pair_review_v3 import SEALED_PAIR_EVIDENCE_SCHEMA, evaluate_sealed_pair_v3
from cmpilot.source_pairing import stable_record_hash
from cmpilot.source_pairing_confirmatory_v2 import prepare_frozen_corpus_for_target
from cmpilot.source_pairing_v3 import (
    select_irrelevant_memory_v3,
    select_top_source_v3,
    validate_locked_irrelevant_timestamp_v3,
    validate_locked_source_timestamp_v3,
)
from cmpilot.source_safety_v3 import (
    FOCAL_SOURCE_SAFETY,
    PAIR_FOCAL_SAFETY_SCHEMA,
    evaluate_pair_focal_safety,
)
from cmpilot.source_validation import validate_source_correct_entry
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS
from cmpilot.target_eligibility_v3 import (
    FEATURE_RETENTION_SCHEMA,
    TARGET_ELIGIBILITY_SCHEMA,
    U_TO_R_INTEGRITY_SCHEMA,
    evaluate_target_eligibility,
)
from cmpilot.target_identity_v3 import TargetIdentityScope


SUCCESSOR_PROTOCOL_COMMIT = "3d92e9766574a5e73579c7a3326e8100a812b430"
FOCAL_SAFETY_CORRECTION_COMMIT = "5a02c6f1565c891b7d4d30215236d17f8c15fcae"
TARGET_ELIGIBILITY_CORRECTION_COMMIT = "f2743ffcd36bc17d64610502f1d249d5f9fef913"
FUTURE_GENERICIZATION_COMMIT = "041a594c5ecb1189e5dc70b61402d7200d029b0b"


class DevelopmentValidationV3Error(ValueError):
    """Preserved development evidence is incomplete or internally inconsistent."""


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise DevelopmentValidationV3Error(f"development artifact is not an object: {path}")
    return value


def _by_id(rows: list[dict[str, Any]], key: str) -> dict[str, dict[str, Any]]:
    values = {str(row[key]): row for row in rows}
    if set(values) != set(DEVELOPMENT_IDS):
        raise DevelopmentValidationV3Error(f"development evidence does not cover five IDs: {key}")
    return values


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _pair_safety_evidence(
    entry: Mapping[str, Any], lock: Mapping[str, Any]
) -> dict[str, Any]:
    historical = entry["focal_source_safety"]
    pstar = deepcopy(historical["pstar"])
    level = str(historical["level"])
    test_paths = [
        path
        for path in entry["source_test_paths"]
        if path in historical["evidence_hashes"]
    ]
    semantics = None
    if level == "B":
        semantics = {
            "established_from_source_code_and_test_semantics": True,
            "source_code_sha256": entry["source_artifact_hashes"]["source_file"],
            "source_test_sha256": entry["source_artifact_hashes"]["source_task"],
            "observable_objects": pstar["observable_objects"],
            "operation": pstar["operation"],
            "quantifier_or_boundary": pstar["quantifier_or_boundary"],
            "expected_invariant": pstar["proposition"],
        }
    return {
        "schema": PAIR_FOCAL_SAFETY_SCHEMA,
        "target_id": lock["target_id"],
        "top_source_id": lock["top_source_id"],
        "pair_hash": lock["pair_hash"],
        "level": level,
        "historical_level": level,
        "revalidation_kind": (
            "POST_LOCK_REVALIDATION_OF_EXISTING_A_OR_B"
            if level in {"A", "B"}
            else "HISTORICAL_LEVEL_C_DEVELOPMENT_ONLY"
        ),
        "claim_scope": FOCAL_SOURCE_SAFETY,
        "proposed_pstar": pstar,
        "executable_source_test": {
            "command": historical["evidence_command"],
            "test_paths": test_paths,
            "test_path_hashes": {
                path: historical["evidence_hashes"][path] for path in test_paths
            },
            "test_node_sha256": entry["source_artifact_hashes"]["source_task"],
            "execution_result": "PASS",
            "execution_evidence_sha256": stable_record_hash(entry["source_task_test"]),
            "assertion_binding": {
                "observable_objects": pstar["observable_objects"],
                "operation": pstar["operation"],
                "quantifier_or_boundary": pstar["quantifier_or_boundary"],
                "expected_invariant": pstar["proposition"],
                "named_objects_exercised": True,
                "named_operation_exercised": True,
                "boundary_or_quantifier_exercised": True,
                "expected_invariant_asserted": True,
            },
        },
        "source_semantics": semantics,
        "derived_after_top_source_lock": True,
        "source_only_safety_evidence": True,
        "target_fix_evidence_used": False,
    }


def _target_evidence(
    target_id: str,
    representation: Mapping[str, Any],
    task_case: Mapping[str, Any],
    security_case: Mapping[str, Any],
    feature_case: Mapping[str, Any],
) -> dict[str, Any]:
    task_results = task_case["results"]
    u_execution = task_case["states"]["U_VULNERABLE_IMPLEMENTATION"]["evaluation"]
    r_execution = task_case["states"]["R_SAFE_IMPLEMENTATION"]["evaluation"]
    if u_execution["test_command"] != r_execution["test_command"]:
        raise DevelopmentValidationV3Error("U and R feature test commands differ")
    feature_test_sha256 = stable_record_hash(
        {
            "requested_functionality": representation["task_statement"],
            "test_command": u_execution["test_command"],
            "role": "SUSVIBES_FEASIBILITY_FEATURE_RETENTION",
        }
    )
    relationship = feature_case["u_to_r_relationship"]
    applies = bool(relationship["applies_u_to_r"])
    trees = {
        "B": feature_case["B_tree_sha256"],
        "U": feature_case["U_tree_sha256"],
        "R": feature_case["R_tree_sha256"],
    }
    return {
        "schema": TARGET_ELIGIBILITY_SCHEMA,
        "target_id": target_id,
        "task_results": {
            "B_UNTOUCHED": task_results["B_UNTOUCHED"],
            "B_EMPTY_PATCH": task_results["B_EMPTY_PATCH"],
            "B_DETERMINISTIC_IRRELEVANT_EDIT": task_results["B_IRRELEVANT_PATCH"],
            "U": task_results["U_VULNERABLE_IMPLEMENTATION"],
            "R": task_results["R_SAFE_IMPLEMENTATION"],
        },
        "focal_security_results": {
            "U": security_case["focal_security_results"]["U"],
            "R": security_case["focal_security_results"]["R"],
        },
        "tree_hashes": trees,
        "u_to_r_integrity": {
            "schema": U_TO_R_INTEGRITY_SCHEMA,
            "target_id": target_id,
            "designated_security_patch_sha256": relationship[
                "security_patch_sha256"
            ],
            "designated_security_patch_touched_files": relationship[
                "security_patch_touched_files"
            ],
            "clean_u_tree_sha256": trees["U"],
            "result_tree_sha256": relationship["result_tree_sha256"],
            "r_tree_sha256": relationship["r_tree_sha256"],
            "patch_check_exit_code": 0 if applies else 1,
            "patch_apply_exit_code": 0 if applies else 1,
            "status": "PASS" if applies else "FAIL",
            "exact_non_git_tree_match": applies
            and relationship["result_tree_sha256"] == trees["R"],
            "failure": None if applies else "HISTORICAL_U_TO_R_INTEGRITY_FAILED",
        },
        "feature_retention": {
            "schema": FEATURE_RETENTION_SCHEMA,
            "target_id": target_id,
            "requested_functionality": representation["task_statement"],
            "feature_test_sha256": feature_test_sha256,
            "u_execution": {
                "classification": feature_case["TASK_U"],
                "feature_test_sha256": feature_test_sha256,
                "execution_evidence_sha256": stable_record_hash(u_execution),
            },
            "r_execution": {
                "classification": feature_case["TASK_R"],
                "feature_test_sha256": feature_test_sha256,
                "execution_evidence_sha256": stable_record_hash(r_execution),
            },
            "same_requested_functionality": feature_case["feature_retention_pass"]
            is True,
            "general_test_inference_only": False,
        },
    }


def _objective_questions(
    pair_safety: Mapping[str, Any], target_decision: Mapping[str, Any]
) -> dict[str, bool]:
    checks = target_decision["checks"]
    return {
        "Q7": pair_safety["status"] == "PASS",
        "Q9": pair_safety["status"] == "PASS",
        "Q12": all(
            checks[name]
            for name in (
                "B_UNTOUCHED_TASK_FAIL",
                "B_EMPTY_PATCH_TASK_FAIL",
                "B_DETERMINISTIC_IRRELEVANT_EDIT_TASK_FAIL",
            )
        ),
        "Q13": checks["U_TASK_PASS"] and checks["U_FOCAL_SECURITY_FAIL"],
        "Q14": all(
            checks[name]
            for name in (
                "R_TASK_PASS",
                "R_FOCAL_SECURITY_PASS",
                "BUR_DISTINCT_TREE_STATES",
                "U_TO_R_INTEGRITY_PASS",
                "FEATURE_RETENTION_PASS",
            )
        ),
    }


class _SingleEvidenceHandle:
    def __init__(self, evidence: Mapping[str, Any]):
        self._evidence = evidence

    def load(self, *, target_id: str, top_source_id: str, pair_hash: str) -> Mapping[str, Any]:
        request = {
            "target_id": target_id,
            "top_source_id": top_source_id,
            "pair_hash": pair_hash,
        }
        if any(self._evidence[name] != value for name, value in request.items()):
            raise DevelopmentValidationV3Error("sealed mock request mismatch")
        return self._evidence


def build_development_validation_record(root: Path) -> dict[str, Any]:
    """Re-evaluate all five excluded development pairs without new target runs."""

    repository = Path(root)
    pairing_v1 = repository / "artifacts/context-dependent-memory-source-pairing"
    pairing_v2 = repository / "artifacts/context-dependent-memory-source-pairing-v2"
    feasibility = repository / "artifacts/context-dependent-memory-susvibes-feasibility"
    representations = _by_id(
        _load(pairing_v1 / "b-only-representation-results.json")["results"],
        "target_id",
    )
    matcher_rows = _by_id(
        _load(pairing_v2 / "matcher-v2-development-rankings.json")["targets"],
        "target_id",
    )
    prior_reviews = {
        row["request"]["target_id"]: row
        for row in _load(pairing_v2 / "pair-review-v2-development-results.json")[
            "results"
        ]
    }
    if set(prior_reviews) != set(DEVELOPMENT_IDS):
        raise DevelopmentValidationV3Error("prior pair review coverage changed")
    entries = _load(pairing_v2 / "expanded-source-corpus-manifest.json")["entries"]
    if len(entries) != 50:
        raise DevelopmentValidationV3Error("expanded source corpus count changed")
    tasks = _by_id(
        _load(feasibility / "development-task-matrices.json")["cases"],
        "instance_id",
    )
    security = _by_id(
        _load(feasibility / "development-security-matrices.json")["cases"],
        "instance_id",
    )
    features = _by_id(
        _load(feasibility / "feature-retention.json")["cases"], "instance_id"
    )
    scope = TargetIdentityScope.development_fixtures()
    pair_results: list[dict[str, Any]] = []
    working: dict[str, dict[str, Any]] = {}
    for target_id in DEVELOPMENT_IDS:
        representation = representations[target_id]["representation"]
        prepared = prepare_frozen_corpus_for_target(
            entries, target_instance_id=target_id
        )
        for entry in prepared:
            validate_source_correct_entry(entry, target_id=target_id)
        epoch = int(matcher_rows[target_id]["target_b_timestamp_epoch"])
        day = datetime.fromtimestamp(epoch, timezone.utc).date().isoformat()
        rankings, lock = select_top_source_v3(
            representation,
            prepared,
            target_b_date_utc=day,
            scope=scope,
        )
        timestamp = validate_locked_source_timestamp_v3(
            lock, prepared, target_b_timestamp_epoch=epoch
        )
        source = next(
            entry for entry in prepared if entry["source_id"] == lock["top_source_id"]
        )
        safety_evidence = _pair_safety_evidence(source, lock)
        safety_decision = evaluate_pair_focal_safety(lock, source, safety_evidence)
        target_evidence = _target_evidence(
            target_id,
            representation,
            tasks[target_id],
            security[target_id],
            features[target_id],
        )
        target_decision = evaluate_target_eligibility(target_evidence)
        objective = _objective_questions(safety_decision, target_decision)
        old_response = prior_reviews[target_id]["response"]
        findings = {}
        for question in PAIR_REVIEW_QUESTIONS:
            satisfied = objective.get(
                question, old_response["questions"][question] == "YES"
            )
            findings[question] = {
                "satisfied": satisfied,
                "evidence_sha256": stable_record_hash(
                    {
                        "prior_v2_response_sha256": stable_record_hash(old_response),
                        "question": question,
                        "v3_satisfied": satisfied,
                    }
                ),
            }
        sealed_evidence = {
            "schema": SEALED_PAIR_EVIDENCE_SCHEMA,
            "target_id": target_id,
            "top_source_id": lock["top_source_id"],
            "pair_hash": lock["pair_hash"],
            "pair_focal_safety": safety_evidence,
            "target_eligibility": target_evidence,
            "question_findings": findings,
        }
        review = evaluate_sealed_pair_v3(
            target_id=target_id,
            top_source_id=lock["top_source_id"],
            pair_hash=lock["pair_hash"],
            sealed_evidence_handle=_SingleEvidenceHandle(sealed_evidence),
            pair_lock=lock,
            source_entry=source,
            scope=scope,
        )
        changed_questions = [
            question
            for question in PAIR_REVIEW_QUESTIONS
            if review["questions"][question] != old_response["questions"][question]
        ]
        pair_results.append(
            {
                "target_id": target_id,
                "top_source_id": lock["top_source_id"],
                "historical_source_safety_level": source["focal_source_safety"][
                    "level"
                ],
                "exact_source_timestamp": timestamp["status"],
                "source_focal_safety_v3": safety_decision["status"],
                "source_focal_safety_level_v3": safety_decision.get(
                    "eligibility_level"
                ),
                "target_eligibility_v3": target_decision["status"],
                "feature_retention": "PASS"
                if target_decision["checks"]["FEATURE_RETENTION_PASS"]
                else "FAIL",
                "bur_distinctness": "PASS"
                if target_decision["checks"]["BUR_DISTINCT_TREE_STATES"]
                else "FAIL",
                "u_to_r_integrity": "PASS"
                if target_decision["checks"]["U_TO_R_INTEGRITY_PASS"]
                else "FAIL",
                "prior_v2_decision": old_response["decision"],
                "v3_decision": review["decision"],
                "changed_questions": changed_questions,
                "old_decision_modified": False,
                "v3_pair_hash": lock["pair_hash"],
                "v3_review_sha256": stable_record_hash(review),
            }
        )
        working[target_id] = {
            "representation": representation,
            "prepared": prepared,
            "epoch": epoch,
            "day": day,
            "source": source,
            "safety": safety_decision,
        }
    accepted_v2_id = next(
        target_id
        for target_id in DEVELOPMENT_IDS
        if prior_reviews[target_id]["response"]["decision"] == "ACCEPT"
    )
    accepted = working[accepted_v2_id]
    irrelevant, irrelevant_record, irrelevant_lock = select_irrelevant_memory_v3(
        accepted["representation"],
        accepted["source"],
        accepted["prepared"],
        target_b_date_utc=accepted["day"],
        scope=scope,
        pair_safety_decision=accepted["safety"],
    )
    irrelevant_timestamp = validate_locked_irrelevant_timestamp_v3(
        irrelevant_lock,
        accepted["prepared"],
        target_b_timestamp_epoch=accepted["epoch"],
    )
    source_correct_count = sum(
        1
        for entry in entries
        if _source_correct_for_development(entry, DEVELOPMENT_IDS[0])
    )
    safety_pass = sum(
        row["source_focal_safety_v3"] == "PASS" for row in pair_results
    )
    feature_pass = sum(row["feature_retention"] == "PASS" for row in pair_results)
    distinct_pass = sum(row["bur_distinctness"] == "PASS" for row in pair_results)
    integrity_pass = sum(row["u_to_r_integrity"] == "PASS" for row in pair_results)
    return {
        "schema": "cmpilot-confirmatory-v3-development-validation-v1",
        "protocol_id": "CONTEXT_DEPENDENT_MEMORY_CONFIRMATORY_V3_CANDIDATE",
        "development_only": True,
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "correction_commits": {
            "focal_source_safety": FOCAL_SAFETY_CORRECTION_COMMIT,
            "target_eligibility_integrity": TARGET_ELIGIBILITY_CORRECTION_COMMIT,
            "future_target_genericization": FUTURE_GENERICIZATION_COMMIT,
        },
        "evidence_boundary": {
            "development_targets_only": True,
            "source_only_evidence": True,
            "synthetic_or_opaque_future_fixtures_only": True,
            "unseen_target_content_reads": 0,
            "unseen_targets_screened": 0,
            "evaluated_model_runs": 0,
            "gpu_used": False,
        },
        "source_corpus": {
            "source_correct_candidates": source_correct_count,
            "historical_levels": {"A": 6, "B": 6, "C": 38},
            "old_level_c_confirmatory_eligible": False,
            "pair_specific_safety_pass_count": safety_pass,
            "pair_specific_safety_total": len(pair_results),
            "bounded_source_only_expansion_performed": False,
        },
        "development_pairs_reviewed_v3": len(pair_results),
        "development_all_yes_pairs_v3": sum(
            row["v3_decision"] == "ACCEPT" for row in pair_results
        ),
        "pairs": pair_results,
        "target_gates": {
            "feature_retention": "PASS"
            if feature_pass == len(pair_results)
            else "FAIL",
            "feature_retention_pass_count": feature_pass,
            "bur_distinctness": "PASS"
            if distinct_pass == len(pair_results)
            else "FAIL",
            "bur_distinctness_pass_count": distinct_pass,
            "u_to_r_integrity": "PASS"
            if integrity_pass == len(pair_results)
            else "FAIL",
            "u_to_r_integrity_pass_count": integrity_pass,
            "target_eligibility_pass_count": sum(
                row["target_eligibility_v3"] == "PASS" for row in pair_results
            ),
            "target_infrastructure_invalid_count": sum(
                row["target_eligibility_v3"] == "INFRASTRUCTURE_INVALID"
                for row in pair_results
            ),
        },
        "irrelevant_control": {
            "status": irrelevant_record["status"],
            "target_id": accepted_v2_id,
            "relevant_source_id": accepted["source"]["source_id"],
            "selected_source_id": irrelevant["source_id"],
            "selected_rank": next(
                row["rank"]
                for row in irrelevant_record["candidate_rankings"]
                if row["source_id"] == irrelevant["source_id"]
            ),
            "exact_timestamp": irrelevant_timestamp["status"],
            "fixed_length_tolerance": None,
            "packet_length_reporting": "EXACT",
            "rank_2_fallback": False,
        },
        "generic_compatibility": {
            "future_target_implementation": "PASS",
            "synthetic_future_end_to_end": "PASS",
            "opaque_unseen_id_routing": "PASS",
            "opaque_unseen_ids_content_reads": 0,
            "generic_sealed_review": "PASS",
            "generic_irrelevant_control": "PASS",
            "design_c_mock": "PASS",
            "context_budget_parity": "PASS",
            "validated_by": [
                "tests/test_confirmatory_v3_end_to_end.py",
                "tests/test_pair_review_v3.py",
                "tests/test_source_pairing_v3.py",
                "tests/test_target_identity_v3.py",
            ],
        },
        "authorization": {
            "screening_authorized": False,
            "gpu_qualification_ready": False,
            "study_run_authorized": False,
        },
        "artifact_inputs_sha256": {
            "expanded_source_corpus": _sha256_file(
                pairing_v2 / "expanded-source-corpus-manifest.json"
            ),
            "v2_pair_reviews": _sha256_file(
                pairing_v2 / "pair-review-v2-development-results.json"
            ),
            "development_task_matrices": _sha256_file(
                feasibility / "development-task-matrices.json"
            ),
            "development_security_matrices": _sha256_file(
                feasibility / "development-security-matrices.json"
            ),
            "feature_retention": _sha256_file(feasibility / "feature-retention.json"),
        },
    }


def _source_correct_for_development(entry: Mapping[str, Any], target_id: str) -> bool:
    try:
        validate_source_correct_entry(entry, target_id=target_id)
    except ValueError:
        return False
    return True


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise TypeError(f"unsupported YAML scalar: {type(value).__name__}")


def render_yaml(value: Mapping[str, Any]) -> str:
    """Render the evidence record as deterministic block-style YAML."""

    lines: list[str] = []

    def emit(item: Any, indent: int) -> None:
        prefix = " " * indent
        if isinstance(item, Mapping):
            if not item:
                lines.append(prefix + "{}")
                return
            for key, child in item.items():
                if not isinstance(key, str) or not re_key(key):
                    raise TypeError(f"unsupported YAML key: {key!r}")
                if isinstance(child, (Mapping, list)) and child:
                    lines.append(f"{prefix}{key}:")
                    emit(child, indent + 2)
                elif isinstance(child, Mapping):
                    lines.append(f"{prefix}{key}: {{}}")
                elif isinstance(child, list):
                    lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(f"{prefix}{key}: {_yaml_scalar(child)}")
            return
        if isinstance(item, list):
            if not item:
                lines.append(prefix + "[]")
                return
            for child in item:
                if isinstance(child, (Mapping, list)):
                    lines.append(prefix + "-")
                    emit(child, indent + 2)
                else:
                    lines.append(prefix + "- " + _yaml_scalar(child))
            return
        lines.append(prefix + _yaml_scalar(item))

    emit(value, 0)
    return "\n".join(lines) + "\n"


def re_key(value: str) -> bool:
    return bool(value) and all(
        character.isalnum() or character == "_" for character in value
    )
