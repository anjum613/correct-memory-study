from __future__ import annotations

from pathlib import Path

from cmpilot.development_validation_v3 import (
    build_development_validation_record,
    render_yaml,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = (
    ROOT
    / "artifacts/context-dependent-memory-confirmatory-v3/development-v3-validation.yaml"
)


def test_five_development_pairs_are_re_evaluated_separately_under_v3() -> None:
    record = build_development_validation_record(ROOT)
    assert record["development_only"] is True
    assert record["development_pairs_reviewed_v3"] == 5
    assert [row["target_id"] for row in record["pairs"]] == list(DEVELOPMENT_IDS)
    assert all(row["old_decision_modified"] is False for row in record["pairs"])
    assert record["source_corpus"]["source_correct_candidates"] == 50
    assert record["source_corpus"]["old_level_c_confirmatory_eligible"] is False
    assert record["source_corpus"]["bounded_source_only_expansion_performed"] is False


def test_previously_accepted_pair_passes_source_safety_but_is_not_silently_kept() -> None:
    record = build_development_validation_record(ROOT)
    wagtail = next(row for row in record["pairs"] if row["target_id"].startswith("wagtail__"))
    assert wagtail["prior_v2_decision"] == "ACCEPT"
    assert wagtail["source_focal_safety_v3"] == "PASS"
    assert wagtail["source_focal_safety_level_v3"] == "A"
    assert wagtail["target_eligibility_v3"] == "INFRASTRUCTURE_INVALID"
    assert wagtail["v3_decision"] == "REJECT"
    assert set(wagtail["changed_questions"]) == {"Q12"}
    assert record["development_all_yes_pairs_v3"] == 0


def test_level_c_and_unbound_a_b_evidence_fail_closed_post_lock() -> None:
    record = build_development_validation_record(ROOT)
    by_prefix = {row["target_id"].split("__", 1)[0]: row for row in record["pairs"]}
    assert by_prefix["buildbot"]["historical_source_safety_level"] == "C"
    assert by_prefix["buildbot"]["source_focal_safety_v3"] == (
        "SOURCE_SAFETY_INSUFFICIENT"
    )
    assert by_prefix["wagtail"]["source_focal_safety_v3"] == "PASS"
    assert by_prefix["django"]["source_focal_safety_v3"] == "PASS"


def test_target_integrity_gates_and_irrelevant_control_pass() -> None:
    record = build_development_validation_record(ROOT)
    gates = record["target_gates"]
    assert gates["feature_retention"] == "PASS"
    assert gates["feature_retention_pass_count"] == 5
    assert gates["bur_distinctness"] == "PASS"
    assert gates["bur_distinctness_pass_count"] == 5
    assert gates["u_to_r_integrity"] == "PASS"
    assert gates["u_to_r_integrity_pass_count"] == 5
    assert gates["target_eligibility_pass_count"] == 4
    assert gates["target_infrastructure_invalid_count"] == 1
    irrelevant = record["irrelevant_control"]
    assert irrelevant["status"] == "PASS"
    assert irrelevant["selected_rank"] == 1
    assert irrelevant["exact_timestamp"] == "PASS"
    assert irrelevant["rank_2_fallback"] is False


def test_validation_boundary_and_generic_mock_evidence_are_explicit() -> None:
    record = build_development_validation_record(ROOT)
    boundary = record["evidence_boundary"]
    assert boundary["unseen_target_content_reads"] == 0
    assert boundary["unseen_targets_screened"] == 0
    assert boundary["evaluated_model_runs"] == 0
    assert boundary["gpu_used"] is False
    generic = record["generic_compatibility"]
    assert all(
        generic[name] == "PASS"
        for name in (
            "future_target_implementation",
            "synthetic_future_end_to_end",
            "opaque_unseen_id_routing",
            "generic_sealed_review",
            "generic_irrelevant_control",
            "design_c_mock",
            "context_budget_parity",
        )
    )
    assert generic["opaque_unseen_ids_content_reads"] == 0


def test_yaml_rendering_is_deterministic_block_yaml() -> None:
    first = render_yaml(build_development_validation_record(ROOT))
    second = render_yaml(build_development_validation_record(ROOT))
    assert first == second
    assert first.startswith('schema: "cmpilot-confirmatory-v3-development-validation-v1"\n')
    assert not first.lstrip().startswith("{")
    assert "development_pairs_reviewed_v3: 5\n" in first


def test_committed_development_validation_matches_the_renderer() -> None:
    expected = render_yaml(build_development_validation_record(ROOT))
    assert ARTIFACT.read_text(encoding="utf-8") == expected
