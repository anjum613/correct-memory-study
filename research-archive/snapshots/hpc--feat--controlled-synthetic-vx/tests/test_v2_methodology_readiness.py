from pathlib import Path

from cmpilot.v2_methodology_readiness import build


ROOT = Path(__file__).parents[1]


def test_readiness_is_conservative_and_complete() -> None:
    readiness, classifications, prompts = build(ROOT)
    required = {
        "protocol_version",
        "git_commit",
        "v1_immutability_preserved",
        "six_family_identity_preserved",
        "historical_evidence_preserved",
        "source_memories_preserved",
        "security_witnesses_preserved",
        "v2_fixture_construction_method",
        "v2_fixture_ready_by_family",
        "trust_shift_preserved_by_family",
        "task_completion_ready_by_family",
        "faithful_reuse_real_change_by_family",
        "faithful_reuse_completion_pass_by_family",
        "faithful_reuse_security_fail_by_family",
        "safe_control_completion_pass_by_family",
        "safe_control_security_pass_by_family",
        "clean_snapshot_reconstruction_by_family",
        "all_prompts_fit_32768",
        "v2_required_tests_pass",
        "full_repository_suite_pass",
        "os_sandbox_status",
        "remaining_non_gpu_blockers",
        "non_gpu_study_readiness",
        "gpu_qualification_ready",
        "study_run_authorized",
    }
    assert required <= readiness.keys()
    assert readiness["v1_immutability_preserved"] is True
    assert readiness["six_family_identity_preserved"] is True
    assert not any(readiness["v2_fixture_ready_by_family"].values())
    assert all(readiness["clean_snapshot_reconstruction_by_family"].values())
    assert readiness["all_prompts_fit_32768"] is True
    assert readiness["v2_required_tests_pass"] is False
    assert readiness["full_repository_suite_pass"] is False
    assert readiness["os_sandbox_status"] == "PASS"
    assert readiness["non_gpu_study_readiness"] == "FAIL"
    assert readiness["gpu_qualification_ready"] is False
    assert readiness["study_run_authorized"] is False
    assert classifications["unresolved_v2_logic_failures"] == []
    assert classifications["unresolved_v2_fixture_failures"] == []
    assert prompts["all_prompts_fit_32768"] is True


def test_historical_controls_are_not_mislabeled_as_v2_fixture_controls() -> None:
    readiness, _, _ = build(ROOT)
    assert all(readiness["historical_security_control_revalidated_by_family"].values())
    assert not any(readiness["faithful_reuse_security_fail_by_family"].values())
    assert not any(readiness["safe_control_security_pass_by_family"].values())


def test_every_preflight_nonpassing_test_has_an_allowed_classification() -> None:
    _, classification, _ = build(ROOT)
    allowed = set(classification["allowed_categories"])
    rows = classification["individual_nonpassing_tests"]
    assert len(rows) == 21
    assert all(row["category"] in allowed for row in rows)
    assert classification["unexecuted_group"]["category"] in allowed
