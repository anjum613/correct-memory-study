"""Reproduce missing-policy evidence without editing prior X25 artifacts or tests."""

import json

from scripts.check_v3_x25_specification_defect import diagnostic, encode


def test_functional_derivations_do_not_establish_an_undeclared_work_policy():
    result = diagnostic()
    first, second = (result["reference_diagnostic"][key] for key in ("4096", "8192"))
    for record in (first, second):
        assert record["R_existing"]["status"] == "PASS"
        assert record["R_requested_feature"]["status"] == "PASS"
    assert first["R_current_narrow_focal_check"]["status"] == "PASS"
    assert second["R_current_narrow_focal_check"]["status"] == "FAIL"
    assert second["R_current_narrow_focal_check"]["condition"] == "new verifier is actual policy-strength derivation"


def test_missing_contract_cannot_authorize_construction_or_an_exclusion():
    result = json.loads(json.dumps(diagnostic(), default=encode))
    assert result["classification"] == "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED"
    assert result["frozen_invariant_verdict"] == "UNDETERMINED_MISSING_NORMATIVE_CONTRACT"
    assert result["constructor_attempts"] == result["evaluated_agent_outcomes"] == result["actual_V3_human_reviews"] == 0
    assert not result["construction_authorized"]
    assert not result["new_scientific_amendment_created"]
    assert result["preservation"]["blocked_snapshot_files_preserved"] == 20
