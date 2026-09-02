from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cmpilot.memory_lifecycle import (
    ADAPTATION,
    APPLICABILITY_CHECKING,
    CONDITIONS,
    REVALIDATION_INSTRUCTION,
    UPTAKE,
    VERIFICATION,
    audit_memory_packet,
    render_memory_packet,
    sha256_bytes,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"


def load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def test_memory_lifecycle_artifact_is_complete_isolated_and_model_free() -> None:
    audit = load("memory-lifecycle-audit.json")
    assert audit["status"] == "PASS"
    assert audit["development_only"] is True
    assert audit["development_target_id"] in DEVELOPMENT_IDS
    assert [row["condition"] for row in audit["conditions"]] == list(CONDITIONS)
    assert audit["source_target_session_ids_disjoint"] is True
    assert audit["condition_store_roots_distinct"] is True
    assert audit["cross_condition_contamination"] is False
    assert audit["evaluated_model_inference"] is False
    assert audit["gpu_used"] is False
    assert audit["conditions"][0]["event_sequence"] == [
        "TARGET_SESSION_STARTED",
        "TARGET_ENDPOINT_COMPLETED",
        "TARGET_SESSION_ENDED",
    ]
    for condition in audit["conditions"]:
        assert condition["pass"] is True
        assert condition["evaluated_model_inference"] is False
        assert condition["endpoint"]["endpoint"] == "DETERMINISTIC_STUB_NO_MODEL"
        assert condition["endpoint"]["evaluated_model_inference"] is False
    for condition in audit["conditions"][1:]:
        assert condition["source_replay"]["source_build"]["classification"] == "PASS"
        assert condition["source_replay"]["source_task_test"]["classification"] == "PASS"
        assert condition["source_replay"]["correspondence"][
            "exact_source_correspondence"
        ] is True
        assert condition["source_validation_event"]["source_build_result"] == "PASS"
        assert condition["source_validation_event"]["source_task_test_result"] == "PASS"
        retrieval = condition["retrieval_log"]
        for key in load("memory-store-schema.json")["retrieval_log_required"]:
            assert key in retrieval
        assert retrieval["candidate_ids"]
        assert retrieval["candidate_scores"]
        assert retrieval["candidate_ranks"]
        assert retrieval["memory_hash"] == retrieval["delivered_bytes_hash"]
        assert condition["source_session_id"] != condition["target_session_id"]


def test_memory_fidelity_and_packet_leakage_guards_cover_both_memories() -> None:
    fidelity = load("memory-fidelity-results.json")
    manifest = load("source-corpus-manifest.json")
    representations = load("b-only-representation-results.json")
    assert fidelity["status"] == "PASS"
    assert fidelity["all_exact"] is True
    assert fidelity["all_source_tests_replayed_pass"] is True
    assert len(fidelity["sources"]) == 2
    entries = {entry["source_id"]: entry for entry in manifest["entries"]}
    target = next(
        row["representation"]
        for row in representations["results"]
        if row["target_id"] == "wagtail__wagtail_5c7a60977cba478f6a35390ba98cffc2bd41c8a4"
    )
    for result in fidelity["sources"]:
        entry = entries[result["source_id"]]
        packet = render_memory_packet(entry)
        observed = audit_memory_packet(packet, entry)
        assert observed["packet_sha256"] == result["packet_sha256"]
        assert result["exact_implementation_identity"] is True
        assert result["source_task_identity"] is True
        assert result["pstar_explanation_in_packet"] is False
        assert result["forbidden_target_or_oracle_material"] is False
        assert target["benchmark_instance_id"].encode() not in packet
        assert target["task_statement"].encode() not in packet
        assert b"<TARGET" not in packet
        assert b"<PSTAR>" not in packet
        assert b"<SECURITY_TEST>" not in packet


def test_irrelevant_control_is_objective_correct_safe_and_length_matched() -> None:
    result = load("irrelevant-memory-matching.json")
    selected = result["selected"]
    thresholds = result["thresholds"]
    assert result["development_status"] == "PASS"
    assert result["selection_uses_target_oracle"] is False
    assert result["selection_uses_model_outcome"] is False
    assert result["source_correct"] is True
    assert result["focal_safe_in_source"] is True
    assert result["same_template"] is True
    assert selected["hard_gate_pass"] is True
    assert selected["primary_operation_different"] is True
    assert selected["different_pstar_class"] is True
    assert selected["scores"]
    assert selected["deltas"]["packet_token_relative_difference"] <= thresholds[
        "packet_token_relative_difference_max"
    ]
    assert selected["deltas"][
        "implementation_token_relative_difference"
    ] <= thresholds["implementation_token_relative_difference_max"]
    assert selected["deltas"][
        "source_task_complexity_log_relative_difference"
    ] <= thresholds["source_task_complexity_log_relative_difference_max"]
    assert selected["semantic_similarity"] <= thresholds["semantic_similarity_max"]
    assert result["candidate_rankings"][0]["source_id"] == result[
        "selected_source_id"
    ]
    assert result["secondary_operation_overlap_disclosed"] is True
    assert result["future_evaluated_tokenizer_recheck_required"] is True


def test_context_balance_revalidation_and_condition_choice_are_consistent() -> None:
    audit = load("memory-lifecycle-audit.json")
    revalidation = load("revalidation-intervention.json")
    recommendation = load("condition-design-recommendation.json")
    assert {row["post_ingestion_budget"] for row in audit["context_budgets"]} == {
        16384
    }
    assert {row["physical_context"] for row in audit["context_budgets"]} == {32768}
    assert all(
        row["trajectory_capacity_reduced_by_revalidation"] is False
        for row in audit["context_budgets"]
    )
    assert audit["context_budgets"][0]["no_memory_semantic_padding"] is False
    expected_hash = hashlib.sha256(REVALIDATION_INSTRUCTION.encode()).hexdigest()
    assert revalidation["instruction"] == REVALIDATION_INSTRUCTION
    assert revalidation["instruction_sha256"] == expected_hash
    assert set(revalidation["target_instruction_hashes"]) == set(DEVELOPMENT_IDS)
    assert set(revalidation["target_instruction_hashes"].values()) == {expected_hash}
    assert revalidation["audits"]["forbidden_terms_found"] == []
    assert revalidation["revalidation_intervention_ready"] is True
    assert recommendation["recommended_condition_design"] == "DESIGN_C"
    assert recommendation["conditions"] == list(CONDITIONS)
    applicable = load("applicable-control-feasibility.json")
    assert applicable["overall"] == "NOT_AVAILABLE"
    assert applicable["target_implementation_edited"] is False
    assert applicable["security_evaluator_modified"] is False


def test_behavior_codebook_has_exact_ordinal_levels_and_no_reasoning_inference() -> None:
    codebook = load("behavior-codebook.json")
    features = load("automated-behavior-features.json")
    assert codebook["UPTAKE"]["levels"] == list(UPTAKE)
    assert codebook["APPLICABILITY_CHECKING"]["levels"] == list(
        APPLICABILITY_CHECKING
    )
    assert codebook["ADAPTATION"]["levels"] == list(ADAPTATION)
    assert codebook["VERIFICATION"]["levels"] == list(VERIFICATION)
    assert codebook["coding_policy"]["hidden_reasoning_inference"] is False
    assert codebook["coding_policy"]["automated_features_do_not_establish_mediation"] is True
    example = features["development_synthetic_unit_example"]
    assert example["hidden_reasoning_inferred"] is False
    assert example["exact_source_bytes_in_patch"] is True
    assert features["classification_policy"].startswith("features support codebook")


def test_memory_schemas_and_artifact_hashes_are_well_formed() -> None:
    store_schema = load("memory-store-schema.json")
    packet_schema = load("memory-packet-schema.json")
    assert store_schema["invariants"]["integrity"].startswith("delivered bytes")
    assert packet_schema["ordered_sections"] == [
        "SOURCE_TASK",
        "SOURCE_IMPLEMENTATION",
        "SOURCE_VALIDATION",
    ]
    assert packet_schema["llm_generated_summary"] is False
    for name in (
        "memory-lifecycle-audit.json",
        "memory-fidelity-results.json",
        "irrelevant-memory-matching.json",
        "applicable-control-feasibility.json",
        "revalidation-intervention.json",
        "condition-design-recommendation.json",
        "behavior-codebook.json",
        "automated-behavior-features.json",
    ):
        digest = sha256_bytes((ARTIFACT_ROOT / name).read_bytes())
        assert len(digest) == 64
