from __future__ import annotations

import json
from pathlib import Path

from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, SUSVIBES_REVISION


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"


def load(name: str) -> dict:
    return json.loads((ARTIFACT_ROOT / name).read_text(encoding="utf-8"))


def test_runtime_estimates_use_counts_and_disclose_uncertainty() -> None:
    result = load("runtime-estimates.json")
    assert result["development_only"] is True
    assert result["susvibes_revision"] == SUSVIBES_REVISION
    assert result["source_corpus_entry_count"] == 12
    assert result["source_candidate_count"] == 13
    fractions = result["fractions"]
    assert fractions["buildable_source"]["numerator"] == 13
    assert fractions["buildable_source"]["denominator"] == 13
    assert fractions["source_correct"]["numerator"] == 12
    assert fractions["source_correct"]["denominator"] == 13
    assert fractions["focal_safe_among_source_correct"]["numerator"] == 12
    assert fractions["focal_safe_among_source_correct"]["denominator"] == 12
    assert fractions["task_statement_cue_eligible"]["numerator"] == 3
    assert fractions["pstar_pair_review_all_yes"]["numerator"] == 1
    assert result["matcher_pass_rate"]["confirmatory"] == "NOT_ESTIMABLE"
    assert result["matcher_pass_rate"]["do_not_extrapolate_as_confirmatory_yield"] is True
    assert result["irrelevant_control_yield"]["status"] == "NOT_AVAILABLE"
    assert result["irrelevant_control_yield"][
        "sealed_accepted_pairs_with_valid_matched_irrelevant"
    ] == 0
    assert result["source_pairing_time_per_target"]["confidence"] == "LOW"
    assert len(result["uncertainty"]) >= 5
    assert result["confirmatory_screening_authorized"] is False
    assert result["evaluated_model_inference"] is False


def test_sample_size_recommendations_have_prespecified_interpretations() -> None:
    sample = load("runtime-estimates.json")["sample_size_recommendation"]
    assert sample["minimum_credible_n"] == 8
    assert sample["minimum_interpretation"] == "controlled mechanism pilot"
    assert sample["target_n"] == 12
    assert sample["target_interpretation"] == "controlled causal workshop study"
    assert sample["maximum_practical_n"] == 20
    assert sample["below_3_policy"] == "no average memory treatment-effect claim"
    assert [row["n"] for row in sample["interpretation_bands"]] == [
        "12+",
        "8-11",
        "3-7",
        "<3",
    ]
    assert sample["power_analysis_status"].startswith("NOT_AVAILABLE")


def test_end_to_end_result_is_development_only_and_not_authorization() -> None:
    result = load("development-end-to-end-results.json")
    assert result["development_only"] is True
    assert result["development_targets"] == list(DEVELOPMENT_IDS)
    assert result["development_end_to_end_pass"] is False
    assert result["status"].startswith("FAIL_MISSING_IRRELEVANT")
    assert result["matcher_thresholds_freezeable"] is False
    assert result["confirmatory_readiness_implication"] == "NONE"
    assert result["confirmatory_screening_authorized"] is False
    assert result["gpu_qualification_ready"] is False
    assert result["study_run_authorized"] is False
    assert result["evaluated_model_inference"] is False
    assert set(result["artifact_dependencies_sha256"]) >= {
        "source-corpus-manifest.json",
        "matcher-threshold-candidate.json",
        "memory-lifecycle-audit.json",
    }
    assert result["checks"]["matched_irrelevant_memory_condition"] == (
        "FAIL_NOT_AVAILABLE"
    )
    assert result["checks"]["endpoint_plumbing"].startswith("PARTIAL")
    assert all(
        value.startswith("PASS")
        for key, value in result["checks"].items()
        if key not in {"matched_irrelevant_memory_condition", "endpoint_plumbing"}
    )
