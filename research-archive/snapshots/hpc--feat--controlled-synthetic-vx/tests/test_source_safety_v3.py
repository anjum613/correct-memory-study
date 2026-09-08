from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

import pytest

from cmpilot.source_pairing import stable_record_hash
from cmpilot.source_safety_v3 import (
    FOCAL_SOURCE_SAFETY,
    OLD_LEVEL_C_CONFIRMATORY_ELIGIBLE,
    PAIR_FOCAL_SAFETY_SCHEMA,
    SOURCE_SAFETY_INSUFFICIENT,
    SourceSafetyV3Error,
    evaluate_pair_focal_safety,
    validate_pair_focal_safety,
)
from cmpilot.source_validation import validate_source_correct_entry
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS


ROOT = Path(__file__).resolve().parents[1]
CORPUS = (
    ROOT
    / "artifacts/context-dependent-memory-source-pairing-v2/expanded-source-corpus-manifest.json"
)


def _entries() -> list[dict]:
    return json.loads(CORPUS.read_text(encoding="utf-8"))["entries"]


def _entry(source_id: str) -> dict:
    return next(entry for entry in _entries() if entry["source_id"] == source_id)


def _lock(target_id: str, source_id: str) -> dict:
    body = {
        "schema": "cmpilot-source-pair-lock-v3",
        "target_id": target_id,
        "top_source_id": source_id,
        "top_one": True,
        "rank_2_fallback": False,
    }
    return {**body, "pair_hash": stable_record_hash(body)}


def _evidence(entry: dict, lock: dict, *, level: str | None = None) -> dict:
    historical = entry["focal_source_safety"]
    pstar = deepcopy(historical["pstar"])
    test_paths = [
        path for path in entry["source_test_paths"] if path in historical["evidence_hashes"]
    ]
    binding = {
        "observable_objects": pstar["observable_objects"],
        "operation": pstar["operation"],
        "quantifier_or_boundary": pstar["quantifier_or_boundary"],
        "expected_invariant": pstar["proposition"],
        "named_objects_exercised": True,
        "named_operation_exercised": True,
        "boundary_or_quantifier_exercised": True,
        "expected_invariant_asserted": True,
    }
    selected_level = level or historical["level"]
    semantics = None
    if selected_level == "B":
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
        "level": selected_level,
        "historical_level": historical["level"],
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
            "assertion_binding": binding,
        },
        "source_semantics": semantics,
        "derived_after_top_source_lock": True,
        "source_only_safety_evidence": True,
        "target_fix_evidence_used": False,
    }


def test_all_50_entries_are_source_correct_without_using_focal_labels() -> None:
    entries = _entries()
    assert len(entries) == 50
    for entry in entries:
        validate_source_correct_entry(entry, target_id=DEVELOPMENT_IDS[0])
    assert sum(entry["focal_source_safety"]["level"] == "C" for entry in entries) == 38


def test_level_a_focal_safety_is_pair_specific_and_post_lock() -> None:
    entry = _entry("src-wagtail-document-link-expand")
    lock = _lock(DEVELOPMENT_IDS[2], entry["source_id"])
    evidence = _evidence(entry, lock)
    decision = validate_pair_focal_safety(lock, entry, evidence)
    assert decision["status"] == "PASS"
    assert decision["eligibility_level"] == "A"
    assert decision["claim"] == FOCAL_SOURCE_SAFETY
    before_lock = deepcopy(evidence)
    before_lock["derived_after_top_source_lock"] = False
    with pytest.raises(SourceSafetyV3Error, match="before top-source lock"):
        validate_pair_focal_safety(lock, entry, before_lock)


def test_level_b_requires_explicit_source_semantics_and_bound_executable_test() -> None:
    entry = _entry("src-django-constant-time-compare")
    lock = _lock(DEVELOPMENT_IDS[3], entry["source_id"])
    evidence = _evidence(entry, lock)
    assert validate_pair_focal_safety(lock, entry, evidence)["status"] == "PASS"
    unbound = deepcopy(evidence)
    unbound["executable_source_test"]["assertion_binding"]["operation"] = "other"
    with pytest.raises(SourceSafetyV3Error, match="named p-star operation"):
        validate_pair_focal_safety(lock, entry, unbound)
    no_semantics = deepcopy(evidence)
    no_semantics["source_semantics"] = None
    with pytest.raises(SourceSafetyV3Error, match="Level B"):
        validate_pair_focal_safety(lock, entry, no_semantics)


def test_old_level_c_is_not_confirmatory_eligible_or_silently_relabeled() -> None:
    assert OLD_LEVEL_C_CONFIRMATORY_ELIGIBLE is False
    entry = _entry("src-v2-buildbot-gerrit-defaultsummarycb-71d61463baee")
    lock = _lock(DEVELOPMENT_IDS[1], entry["source_id"])
    evidence = _evidence(entry, lock)
    decision = evaluate_pair_focal_safety(lock, entry, evidence)
    assert decision["status"] == SOURCE_SAFETY_INSUFFICIENT
    relabeled = _evidence(entry, lock, level="B")
    relabeled["source_semantics"] = {
        "established_from_source_code_and_test_semantics": True,
        "source_code_sha256": entry["source_artifact_hashes"]["source_file"],
        "source_test_sha256": entry["source_artifact_hashes"]["source_task"],
        "observable_objects": relabeled["proposed_pstar"]["observable_objects"],
        "operation": relabeled["proposed_pstar"]["operation"],
        "quantifier_or_boundary": relabeled["proposed_pstar"]["quantifier_or_boundary"],
        "expected_invariant": relabeled["proposed_pstar"]["proposition"],
    }
    assert evaluate_pair_focal_safety(lock, entry, relabeled)["status"] == (
        SOURCE_SAFETY_INSUFFICIENT
    )


def test_focal_source_safety_rejects_target_fix_backfitting_and_lock_mismatch() -> None:
    entry = _entry("src-wagtail-document-link-expand")
    lock = _lock(DEVELOPMENT_IDS[2], entry["source_id"])
    evidence = _evidence(entry, lock)
    backfit = deepcopy(evidence)
    backfit["target_fix_evidence_used"] = True
    with pytest.raises(SourceSafetyV3Error, match="backfit"):
        validate_pair_focal_safety(lock, entry, backfit)
    wrong_pair = deepcopy(evidence)
    wrong_pair["pair_hash"] = "0" * 64
    with pytest.raises(SourceSafetyV3Error, match="locked pair"):
        validate_pair_focal_safety(lock, entry, wrong_pair)
