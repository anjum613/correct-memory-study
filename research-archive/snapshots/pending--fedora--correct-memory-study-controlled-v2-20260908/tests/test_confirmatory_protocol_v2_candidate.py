from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cmpilot.memory_lifecycle import (
    CONTEXT_RESERVE,
    MODEL_DECISION_MAX,
    PER_TURN_GENERATION_MAX,
    PHYSICAL_CONTEXT,
    POST_INGESTION_BUDGET,
    REVALIDATION_INSTRUCTION,
)
from cmpilot.source_pairing_v2 import HARD_GATES, LEXICOGRAPHIC_RANKING


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "protocols/context-dependent-memory-confirmatory-v2-candidate.json"
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"


def _load() -> dict:
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_candidate_and_artifact_copies_are_identical() -> None:
    for suffix in ("json", "md"):
        protocol = ROOT / f"protocols/context-dependent-memory-confirmatory-v2-candidate.{suffix}"
        artifact = ARTIFACT_ROOT / f"context-dependent-memory-confirmatory-v2-candidate.{suffix}"
        assert protocol.read_bytes() == artifact.read_bytes()


def test_candidate_freezes_source_universe_and_development_exclusions() -> None:
    value = _load()
    manifest = ARTIFACT_ROOT / "expanded-source-corpus-manifest.json"
    assert value["prospective_confirmatory_v2_candidate_ready"] is True
    assert value["susvibes"]["revision"] == "7e1b4b05240e56dc2b4e8253b2cc5c9481d016f3"
    assert value["permanent_development_exclusions"]["count"] == 5
    assert value["future_target_universe"]["count"] == 181
    assert value["future_target_universe"]["screened"] is False
    assert value["source_only_partition"]["used"] is False
    assert value["source_universe"]["entry_count"] == 50
    assert value["source_universe"]["manifest_sha256"] == _sha256(manifest)


def test_candidate_matcher_is_exact_threshold_free_top_one_design() -> None:
    matcher = _load()["b_only_matcher"]
    assert matcher["hard_gates"] == list(HARD_GATES)
    assert matcher["lexicographic_ranking"] == list(LEXICOGRAPHIC_RANKING)
    assert matcher["global_similarity_threshold_required"] is False
    assert matcher["combined_or_weighted_score"] is None
    top = _load()["top_one_and_no_fallback"]
    assert top["select_rank"] == 1
    assert top["rank_2_fallback"] is False
    assert top["source_shopping"] is False


def test_candidate_preserves_timestamp_control_packet_and_resource_rules() -> None:
    value = _load()
    timestamp = value["source_timestamp"]
    assert timestamp["pairing_side_field"] == "TARGET_B_DATE_UTC_ONLY"
    assert timestamp["pairing_side_target_commit_hash"] is False
    assert timestamp["applies_to_relevant_and_irrelevant_sources"] is True
    control = value["irrelevant_control_selector"]
    assert control["fixed_length_window"] is None
    assert control["rank_2_fallback"] is False
    assert control["padding"] is False and control["truncation"] is False
    packet = value["memory_packet"]
    assert packet["llm_summary"] is False
    assert packet["explicit_pstar"] is False
    assert value["revalidation_intervention"]["instruction"] == REVALIDATION_INSTRUCTION
    budget = value["context_budget"]
    assert budget == {
        "physical_context": PHYSICAL_CONTEXT,
        "post_ingestion_budget": POST_INGESTION_BUDGET,
        "context_reserve": CONTEXT_RESERVE,
        "per_turn_generation_max": PER_TURN_GENERATION_MAX,
        "model_decision_max": MODEL_DECISION_MAX,
        "equal_post_ingestion_capacity": True,
        "no_memory_junk_or_padding": True,
        "revalidation_reduces_trajectory_capacity": False,
    }


def test_candidate_n_stopping_attrition_and_authorizations_are_consistent() -> None:
    value = _load()
    sample = value["sample_size_and_stopping"]
    assert sample["recommended_minimum_n"] == 8
    assert sample["recommended_target_n"] == 12
    assert sample["maximum_practical_n"] == 16
    assert sample["outcome_based_stopping"] is False
    attrition = value["complete_attrition_ledger"]
    assert "NO_SOURCE_PASSES_HARD_GATES" in attrition["ordered_terminal_reasons"]
    assert all("THRESHOLD" not in reason for reason in attrition["ordered_terminal_reasons"])
    assert attrition["rank_2_examined_after_rejection"] is False
    assert attrition["model_outcomes_available_during_screening"] is False
    assert set(value["authorizations"].values()) == {False}
    assert value["cohort_and_inference_freeze"][
        "evaluated_model_inference_before_cohort_freeze"
    ] is False
