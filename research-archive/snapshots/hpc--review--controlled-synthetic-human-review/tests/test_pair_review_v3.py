from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from cmpilot.pair_review import PAIR_REVIEW_QUESTIONS
from cmpilot.pair_review_v3 import (
    SEALED_PAIR_EVIDENCE_SCHEMA,
    PairReviewV3Error,
    evaluate_sealed_pair_v3,
)
from cmpilot.source_pairing import stable_record_hash
from cmpilot.source_safety_v3 import FOCAL_SOURCE_SAFETY, PAIR_FOCAL_SAFETY_SCHEMA
from cmpilot.target_eligibility_v3 import (
    FEATURE_RETENTION_SCHEMA,
    TARGET_ELIGIBILITY_SCHEMA,
    U_TO_R_INTEGRITY_SCHEMA,
)
from cmpilot.target_identity_v3 import TargetIdentityScope


ROOT = Path(__file__).resolve().parents[1]
TARGET_ID = "synthetic__sealed-review_" + "d" * 40


def _source_entry() -> dict:
    corpus = json.loads(
        (
            ROOT
            / "artifacts/context-dependent-memory-source-pairing-v2/expanded-source-corpus-manifest.json"
        ).read_text(encoding="utf-8")
    )
    return next(
        entry
        for entry in corpus["entries"]
        if entry["source_id"] == "src-wagtail-document-link-expand"
    )


def _pair_lock(entry: dict) -> dict:
    body = {
        "schema": "cmpilot-source-pair-lock-v3",
        "target_id": TARGET_ID,
        "target_scope_purpose": "DEVELOPMENT_SYNTHETIC_EXCLUDED_FIXTURE",
        "target_identity_list_sha256": "a" * 64,
        "top_source_id": entry["source_id"],
        "top_source_entry_sha256": stable_record_hash(entry),
        "target_representation_sha256": "b" * 64,
        "target_b_date_utc": "2030-01-01",
        "prepared_source_corpus_sha256": "c" * 64,
        "matcher_design_sha256": "d" * 64,
        "full_rankings_sha256": "e" * 64,
        "ambiguity": {"status": "TEST", "hash_tiebreak_used": False},
        "top_one": True,
        "rank_2_fallback": False,
        "focal_safety_evaluated_pre_lock": False,
    }
    return {**body, "pair_hash": stable_record_hash(body)}


def _pair_safety(entry: dict, lock: dict) -> dict:
    historical = entry["focal_source_safety"]
    pstar = deepcopy(historical["pstar"])
    test_paths = [
        path for path in entry["source_test_paths"] if path in historical["evidence_hashes"]
    ]
    return {
        "schema": PAIR_FOCAL_SAFETY_SCHEMA,
        "target_id": TARGET_ID,
        "top_source_id": entry["source_id"],
        "pair_hash": lock["pair_hash"],
        "level": "A",
        "historical_level": "A",
        "revalidation_kind": "POST_LOCK_REVALIDATION_OF_EXISTING_A_OR_B",
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
        "source_semantics": None,
        "derived_after_top_source_lock": True,
        "source_only_safety_evidence": True,
        "target_fix_evidence_used": False,
    }


def _target_eligibility() -> dict:
    feature_hash = hashlib.sha256(b"feature").hexdigest()
    tree_hashes = {"B": "1" * 64, "U": "2" * 64, "R": "3" * 64}
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
        "tree_hashes": tree_hashes,
        "u_to_r_integrity": {
            "schema": U_TO_R_INTEGRITY_SCHEMA,
            "target_id": TARGET_ID,
            "designated_security_patch_sha256": "4" * 64,
            "designated_security_patch_touched_files": ["pkg/feature.py"],
            "clean_u_tree_sha256": tree_hashes["U"],
            "result_tree_sha256": tree_hashes["R"],
            "r_tree_sha256": tree_hashes["R"],
            "patch_check_exit_code": 0,
            "patch_apply_exit_code": 0,
            "status": "PASS",
            "exact_non_git_tree_match": True,
            "failure": None,
        },
        "feature_retention": {
            "schema": FEATURE_RETENTION_SCHEMA,
            "target_id": TARGET_ID,
            "requested_functionality": "render the requested document href",
            "feature_test_sha256": feature_hash,
            "u_execution": {
                "classification": "PASS",
                "feature_test_sha256": feature_hash,
                "execution_evidence_sha256": "5" * 64,
            },
            "r_execution": {
                "classification": "PASS",
                "feature_test_sha256": feature_hash,
                "execution_evidence_sha256": "6" * 64,
            },
            "same_requested_functionality": True,
            "general_test_inference_only": False,
        },
    }


class MockHandle:
    def __init__(self, evidence: dict):
        self.evidence = evidence
        self.requests: list[dict] = []

    def load(self, *, target_id: str, top_source_id: str, pair_hash: str) -> dict:
        self.requests.append(
            {
                "target_id": target_id,
                "top_source_id": top_source_id,
                "pair_hash": pair_hash,
            }
        )
        return deepcopy(self.evidence)


def _evidence(entry: dict, lock: dict) -> dict:
    return {
        "schema": SEALED_PAIR_EVIDENCE_SCHEMA,
        "target_id": TARGET_ID,
        "top_source_id": entry["source_id"],
        "pair_hash": lock["pair_hash"],
        "pair_focal_safety": _pair_safety(entry, lock),
        "target_eligibility": _target_eligibility(),
        "question_findings": {
            question: {
                "satisfied": True,
                "evidence_sha256": hashlib.sha256(question.encode()).hexdigest(),
            }
            for question in PAIR_REVIEW_QUESTIONS
        },
    }


def test_generic_sealed_review_accepts_supplied_all_yes_evidence() -> None:
    entry = _source_entry()
    lock = _pair_lock(entry)
    handle = MockHandle(_evidence(entry, lock))
    response = evaluate_sealed_pair_v3(
        target_id=TARGET_ID,
        top_source_id=entry["source_id"],
        pair_hash=lock["pair_hash"],
        sealed_evidence_handle=handle,
        pair_lock=lock,
        source_entry=entry,
        scope=TargetIdentityScope.synthetic_fixture((TARGET_ID,)),
    )
    assert response["decision"] == "ACCEPT"
    assert set(response["questions"]) == set(PAIR_REVIEW_QUESTIONS)
    assert all(answer == "YES" for answer in response["questions"].values())
    assert response["pair_focal_safety"]["status"] == "PASS"
    assert response["target_eligibility"]["status"] == "PASS"
    assert handle.requests == [response["request"]]


def test_sealed_review_rejects_missing_questions_and_objective_conflicts() -> None:
    entry = _source_entry()
    lock = _pair_lock(entry)
    evidence = _evidence(entry, lock)
    evidence["question_findings"].pop("Q16")
    with pytest.raises(PairReviewV3Error, match="fixed 16"):
        evaluate_sealed_pair_v3(
            target_id=TARGET_ID,
            top_source_id=entry["source_id"],
            pair_hash=lock["pair_hash"],
            sealed_evidence_handle=MockHandle(evidence),
            pair_lock=lock,
            source_entry=entry,
            scope=TargetIdentityScope.synthetic_fixture((TARGET_ID,)),
        )
    conflicting = _evidence(entry, lock)
    conflicting["target_eligibility"]["feature_retention"][
        "same_requested_functionality"
    ] = False
    with pytest.raises(PairReviewV3Error, match="Q14"):
        evaluate_sealed_pair_v3(
            target_id=TARGET_ID,
            top_source_id=entry["source_id"],
            pair_hash=lock["pair_hash"],
            sealed_evidence_handle=MockHandle(conflicting),
            pair_lock=lock,
            source_entry=entry,
            scope=TargetIdentityScope.synthetic_fixture((TARGET_ID,)),
        )
