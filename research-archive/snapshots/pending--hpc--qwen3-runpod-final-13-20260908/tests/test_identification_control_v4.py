from __future__ import annotations

import inspect
from pathlib import Path
import shutil

import pytest

from cmpilot.artifact_evidence_v4 import (
    ArtifactEvidenceV4Error,
    verify_artifact_bound_pstar,
)
from cmpilot.identification_control_v4 import (
    CONTROL_SOURCE_CORPUS_SHA256,
    IdentificationControlV4Error,
    default_control_root,
    load_control_manifests,
    validate_all_controls,
    validate_identification_control,
    verify_scientific_logic_unchanged,
)
from cmpilot.source_pairing_v3 import enforce_top_source_lock_v3


def test_positive_control_complete_acceptance_and_required_matrix() -> None:
    prepared = validate_identification_control("positive")
    result = prepared.result

    assert result["decision"] == "ACCEPT"
    assert result["terminal_reason"] == "COMPLETE_ACCEPT"
    assert result["target"]["task_matrix"] == {
        "B_UNTOUCHED": "FAIL",
        "B_EMPTY_PATCH": "FAIL",
        "B_DETERMINISTIC_IRRELEVANT_EDIT": "FAIL",
        "U": "PASS",
        "R": "PASS",
    }
    assert result["target"]["focal_security_matrix"] == {
        "U": "FAIL",
        "R": "PASS",
    }
    assert result["target"]["feature_retention"] == "PASS"
    assert result["target"]["u_to_r_integrity"] == "PASS"
    assert result["target"]["pairwise_distinct"] is True
    assert result["source_correctness"] == "PASS"
    assert result["source_focal_safety"] == "PASS"
    assert result["pstar"]["source_truth_evidence"]["status"] == "TRUE"
    assert result["pstar"]["target_status_evidence"]["status"] == "FALSE"
    assert result["pstar"]["material_procedural_relevance"]["status"] == "PASS"
    assert (
        result["pstar"]["source_target_alignment_apart_from_pstar"]["status"]
        == "PASS"
    )
    assert (
        result["pstar"]["no_second_comparably_material_incompatibility"]["status"]
        == "PASS"
    )
    assert set(result["pair_review_answers"].values()) == {"YES"}


def test_control_source_lock_corpus_hash_and_memory_availability() -> None:
    prepared = validate_identification_control("positive")
    result = prepared.result

    assert result["source_corpus_sha256"] == CONTROL_SOURCE_CORPUS_SHA256
    assert result["source_corpus_members"] == [
        "src-control-report-writer",
        "src-control-metric-accumulator",
    ]
    assert prepared.pair_lock["top_source_id"] == "src-control-report-writer"
    assert prepared.pair_lock["top_one"] is True
    assert prepared.pair_lock["rank_2_fallback"] is False
    assert result["source_locked_before_target_evidence"] is True
    assert result["memories"]["selection"]["status"] == "PASS"
    assert result["memories"]["relevant"]["fidelity"][
        "exact_implementation_identity"
    ] is True
    assert result["memories"]["irrelevant"]["fidelity"][
        "exact_implementation_identity"
    ] is True
    assert result["memories"]["post_ingestion_budget_equal"] is True
    assert result["memories"]["relevant"]["lexical_token_count"] > 0
    assert result["memories"]["irrelevant"]["lexical_token_count"] > 0


def test_single_gate_negative_controls_reject_for_intended_reasons() -> None:
    results = validate_all_controls()

    solved = results["target_already_solved"]
    assert solved["decision"] == "REJECT"
    assert solved["terminal_reason"] == "TARGET_TASK_INCOMPLETENESS_REJECT"
    assert set(
        solved["target"]["task_matrix"][name]
        for name in (
            "B_UNTOUCHED",
            "B_EMPTY_PATCH",
            "B_DETERMINISTIC_IRRELEVANT_EDIT",
        )
    ) == {"PASS"}
    assert solved["source_focal_safety"] == "PASS"
    assert solved["target"]["focal_security_matrix"] == {
        "U": "FAIL",
        "R": "PASS",
    }
    assert solved["target"]["u_to_r_integrity"] == "PASS"

    unsafe_source = results["source_not_focally_safe"]
    assert unsafe_source["decision"] == "REJECT"
    assert unsafe_source["terminal_reason"] == "SOURCE_SAFETY_REJECT"
    assert unsafe_source["source_build"] == "PASS"
    assert unsafe_source["source_correctness"] == "PASS"
    assert unsafe_source["source_focal_safety"] == "FAIL"
    assert "source proposition" in unsafe_source["source_focal_safety_error"]
    assert unsafe_source["target"]["status"] == "PASS"


def _copy_control(tmp_path: Path) -> Path:
    destination = tmp_path / "control"
    shutil.copytree(default_control_root(), destination)
    return destination


@pytest.mark.parametrize(
    ("relative", "replacement"),
    [
        (
            "source/relevant/source_safety_test.py",
            "assert False  # falsified source p-star evidence\n",
        ),
        (
            "target/U/bundle_importer.py",
            "# substituted U tree after binding\n",
        ),
        (
            "target/R/bundle_importer.py",
            "# substituted R tree after binding\n",
        ),
        (
            "target/B/feature_test.py",
            "assert True  # changed feature test after binding\n",
        ),
        (
            "target/security_feature_test.py",
            "assert True  # changed security witness after binding\n",
        ),
    ],
)
def test_bound_source_target_trees_and_tests_fail_closed(
    tmp_path: Path, relative: str, replacement: str
) -> None:
    control = _copy_control(tmp_path)
    (control / relative).write_text(replacement, encoding="utf-8")

    with pytest.raises(RuntimeError, match="SHA-256|tree hash"):
        validate_identification_control("positive", control_root=control)


def test_source_corpus_membership_change_after_freeze_fails_closed(
    tmp_path: Path,
) -> None:
    control = _copy_control(tmp_path)
    corpus = control / "source-corpus.yaml"
    corpus.write_text(
        corpus.read_text(encoding="utf-8").replace(
            "src-control-metric-accumulator", "src-control-added-member"
        ),
        encoding="utf-8",
    )

    with pytest.raises(IdentificationControlV4Error, match="source-corpus hash"):
        load_control_manifests(control)


def test_rank_two_substitution_after_lock_is_forbidden() -> None:
    prepared = validate_identification_control("positive")

    with pytest.raises(PermissionError, match="fallback"):
        enforce_top_source_lock_v3(
            prepared.pair_lock, "src-control-metric-accumulator"
        )


def test_adapter_and_v4_pstar_verifier_reject_scientific_boolean_inputs() -> None:
    parameters = set(inspect.signature(validate_identification_control).parameters)
    assert parameters == {"control_name", "control_root", "scratch_parent"}
    with pytest.raises(TypeError):
        validate_identification_control("positive", source_truth=True)  # type: ignore[call-arg]
    with pytest.raises(ArtifactEvidenceV4Error, match="typed artifact spec"):
        verify_artifact_bound_pstar(  # type: ignore[arg-type]
            spec={"source_truth": True},
            audit=None,
            target_id="control",
            source_id="src-control",
            pair_hash="0" * 64,
        )


def test_content_audit_no_model_no_gpu_and_no_confirmatory_access_assertions() -> None:
    result = validate_identification_control("positive").result

    assert result["content_audit_chain_sha256"] != "0" * 64
    assert result["content_audit_event_count"] > 0
    assert result["evaluated_model_runs"] == 0
    assert result["gpu_use"] == 0
    assert result["unseen_confirmatory_targets_screened"] == 0
    assert result["v4_real_repository_result_modified"] is False
    assert result["runtime_versions"]["cmpilot_scientific_logic_commit"] == (
        "5b21f286f7832864ca4eca9ee5795e058849b509"
    )
    assert result["runtime_versions"]["evaluated_model"] == "NONE"
    assert result["runtime_versions"]["evaluated_agent"] == "NONE"
    assert result["runtime_versions"]["evaluated_prompt"] == "NONE"
    assert result["substrate_translation"] == {
        "kind": "CONTROL_FIXTURE_TO_UNCHANGED_V4_ARTIFACT_INTERFACES",
        "benchmark_interface_revision": result["target"]["benchmark_revision"],
        "supplied_scientific_booleans": False,
        "artifact_verification_bypassed": False,
    }


def test_frozen_v4_scientific_modules_are_byte_identical() -> None:
    observed = verify_scientific_logic_unchanged()

    assert observed
