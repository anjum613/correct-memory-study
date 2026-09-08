from __future__ import annotations

import json
from pathlib import Path

from cmpilot.memory_lifecycle import CONDITIONS, REVALIDATION_INSTRUCTION


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"


def _load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def test_v2_review_preserves_old_decisions_and_has_one_all_yes_pair() -> None:
    value = _load("pair-review-v2-development-results.json")
    assert value["development_pairs_reviewed_v2"] == 5
    assert value["accepted_count"] == 1
    assert value["v1_decisions_reopened_or_reinterpreted"] is False
    assert value["rank_2_fallback"] is False


def test_v2_irrelevant_control_is_timestamp_valid_and_operation_disjoint() -> None:
    value = _load("irrelevant-control-v2.json")
    assert value["status"] == "PASS"
    assert value["fixed_length_tolerance"] is None
    assert value["padding_or_truncation"] is False
    assert value["sealed_exact_timestamp_validation"]["status"] == "PASS"
    selected = next(
        row
        for row in value["candidate_rankings"]
        if row["source_id"] == value["selected_source_id"]
    )
    assert selected["rank"] == 1
    assert selected["operation_class_disjoint"] is True
    assert selected["target_api_or_symbol_leakage"] == []


def test_complete_design_c_has_equal_post_ingestion_capacity() -> None:
    design = _load("design-c-end-to-end.json")
    lifecycle = _load("memory-lifecycle-v2.json")
    assert design["design_c_end_to_end_pass"] is True
    assert tuple(design["conditions"]) == CONDITIONS
    assert all(row["pass"] for row in lifecycle["conditions"])
    assert {row["post_ingestion_budget"] for row in lifecycle["context_budgets"]} == {
        16384
    }
    no_memory = lifecycle["conditions"][0]
    assert no_memory["semantic_padding"] is False


def test_revalidation_wording_and_fidelity_remain_frozen() -> None:
    revalidation = _load("revalidation-v2.json")
    fidelity = _load("memory-fidelity-v2.json")
    assert revalidation["instruction"] == REVALIDATION_INSTRUCTION
    assert revalidation["wording_changed_from_v1"] is False
    assert fidelity["source_count"] == 50
    assert fidelity["all_exact"] is True
