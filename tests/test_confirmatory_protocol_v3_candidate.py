from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE = ROOT / "protocols/context-dependent-memory-confirmatory-v3-candidate.yaml"


def test_final_v3_candidate_records_conservative_validation_state() -> None:
    text = CANDIDATE.read_text(encoding="utf-8")
    required_lines = {
        "status: READY_FOR_INDEPENDENT_FREEZE_REVIEW",
        "  development_pairs_reviewed_v3: 5",
        "  development_all_yes_pairs_v3: 0",
        "  old_level_c_confirmatory_eligible: false",
        "  feature_retention_gate: PASS",
        "  bur_distinctness_gate: PASS",
        "  u_to_r_integrity_gate: PASS",
        "  generic_future_target_implementation: PASS",
        "  synthetic_future_end_to_end: PASS",
        "  opaque_unseen_id_routing: PASS",
        "  unseen_target_content_reads: 0",
        "  unseen_targets_screened: 0",
        "  ready_for_independent_freeze_review: true",
        "  critical_blockers: []",
    }
    assert required_lines <= set(text.splitlines())


def test_final_v3_candidate_remains_unauthorized() -> None:
    text = CANDIDATE.read_text(encoding="utf-8")
    assert "authorization:\n" in text
    assert "  screening_authorized: false\n" in text
    assert "  gpu_qualification_ready: false\n" in text
    assert "  study_run_authorized: false\n" in text
    assert "  required_next_gate: INDEPENDENT_FREEZE_REVIEW\n" in text
