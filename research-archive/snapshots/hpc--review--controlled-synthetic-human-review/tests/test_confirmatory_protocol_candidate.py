from __future__ import annotations

import json
from pathlib import Path

from cmpilot.memory_lifecycle import CONDITIONS, REVALIDATION_INSTRUCTION
from cmpilot.source_pairing import PSTAR_ONTOLOGY
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL_JSON = ROOT / "protocols/context-dependent-memory-confirmatory-v1-candidate.json"
PROTOCOL_MD = ROOT / "protocols/context-dependent-memory-confirmatory-v1-candidate.md"
ARTIFACT_JSON = ROOT / "artifacts/context-dependent-memory-source-pairing/context-dependent-memory-confirmatory-v1-candidate.json"
ARTIFACT_MD = ROOT / "artifacts/context-dependent-memory-source-pairing/context-dependent-memory-confirmatory-v1-candidate.md"


def candidate() -> dict:
    return json.loads(PROTOCOL_JSON.read_text(encoding="utf-8"))


def test_protocol_and_artifact_copies_are_byte_identical() -> None:
    assert PROTOCOL_JSON.read_bytes() == ARTIFACT_JSON.read_bytes()
    assert PROTOCOL_MD.read_bytes() == ARTIFACT_MD.read_bytes()


def test_candidate_is_complete_as_a_blocked_record_not_an_authorization() -> None:
    value = candidate()
    assert value["status"] == "BLOCKED_REVIEW_CANDIDATE"
    assert value["review_required_before_any_authorization"] is True
    assert value["prospective_confirmatory_protocol_candidate_ready"] is False
    assert value["susvibes"]["revision"] == SUSVIBES_REVISION
    assert value["development_exclusions"]["target_ids"] == list(DEVELOPMENT_IDS)
    assert value["development_exclusions"]["permanently_ineligible_for_confirmation"] is True
    assert value["unseen_universe"]["count"] == 181
    assert value["unseen_universe"]["ids_enumerated_or_opened_by_this_candidate_builder"] is False
    assert "target_ids" not in value["unseen_universe"]
    assert value["unseen_universe"]["screened"] is False
    assert value["authorizations"] == {
        "confirmatory_screening_authorized": False,
        "gpu_qualification_ready": False,
        "study_run_authorized": False,
    }


def test_candidate_freezes_settled_rules_and_preserves_blockers() -> None:
    value = candidate()
    assert value["source_universe"]["manifest_entry_count"] == 12
    assert value["source_universe"]["s4"] == "DISABLED"
    assert value["source_timestamp"]["rule"] == (
        "SOURCE_COMMIT_TIMESTAMP <= TARGET_B_TIMESTAMP"
    )
    assert value["source_timestamp"]["applies_to_relevant_and_irrelevant_source_memory"] is True
    assert value["pstar_ontology"]["classes"] == list(PSTAR_ONTOLOGY)
    assert value["matcher"]["thresholds"] is None
    assert value["matcher"]["thresholds_freezeable"] is False
    assert value["matcher"]["ambiguity_margins"] is None
    assert value["matcher"]["confirmatory_matcher_ready"] is False
    assert value["top_one_and_no_fallback"]["top_source_immutable"] is True
    assert value["top_one_and_no_fallback"]["rank_2_fallback"] is False
    assert value["top_one_and_no_fallback"]["manual_fallback_command"] is False
    assert value["oracle_firewall"]["status"] == "PASS"
    assert value["pair_review"]["all_yes_required"] is True
    assert len(value["pair_review"]["questions"]) == 16
    assert value["irrelevant_control"]["ready"] is False
    assert value["irrelevant_control"]["development_status"] == "NOT_AVAILABLE"
    assert value["applicable_control_policy"]["development_result"] == "NOT_AVAILABLE"
    assert value["revalidation_intervention"]["instruction"] == REVALIDATION_INSTRUCTION
    assert value["final_condition_design"]["recommendation"] == "DESIGN_C"
    assert value["final_condition_design"]["conditions"] == list(CONDITIONS)
    assert value["final_condition_design"]["design_ready"] is False
    assert value["development_results"]["development_end_to_end_pass"] is False


def test_target_order_and_stopping_are_prospective_and_nonadaptive() -> None:
    value = candidate()
    ordering = value["target_ordering"]
    assert ordering["domain_separator"] == "cmpilot-confirmatory-target-order-v1"
    assert ordering["unseen_order_materialized"] is False
    assert ordering["outcome_adaptive"] is False
    stopping = value["sample_size_and_stopping"]
    assert stopping["minimum_credible_n"] == 8
    assert stopping["target_n"] == 12
    assert stopping["maximum_practical_n"] == 20
    assert stopping["outcome_based_stopping"] is False
    assert value["complete_attrition_ledger"]["required_for_every_considered_target"] is True
    assert value["complete_attrition_ledger"]["rank_2_examined_after_rejection"] is False


def test_context_model_and_no_unseen_access_in_builder() -> None:
    value = candidate()
    assert value["context_budget"] == {
        "context_reserve": 256,
        "equal_post_ingestion_capacity": True,
        "model_decision_max": 32,
        "no_memory_semantic_padding": False,
        "per_turn_generation_max": 4096,
        "physical_context": 32768,
        "post_ingestion_budget": 16384,
        "relevant_irrelevant_tokenizer_matching": "REQUIRES_FUTURE_EVALUATED_TOKENIZER_RECHECK",
        "revalidation_reduces_trajectory_capacity": False,
    }
    assert value["model_and_decoding"]["evaluated_model_run_in_development"] is False
    assert value["model_and_decoding"]["gpu_qualification_ready"] is False
    assert value["model_and_decoding"]["decoding_choice"] == "UNRESOLVED"
    assert value["model_and_decoding"]["seeds_frozen"] is False
    builder = (ROOT / "scripts/build_confirmatory_protocol_candidate.py").read_text()
    assert "unseen-target-universe" not in builder
    assert "unseen_target_ids" not in builder
