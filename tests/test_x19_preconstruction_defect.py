"""Preserve evidence of an unresolved specification defect, not a passing matrix."""

import json

from scripts.check_v3_local_invariant_preflight import encode, report, x19_evidence
from synthetic_triplets.controlled_v3_local_invariants_v1.catalog import FAMILIES
from synthetic_triplets.controlled_v3_local_invariants_v1.harness import matrix


def test_source_length_difference_exists_without_neighbor_control():
    first, second, *_ = x19_evidence()
    assert first["neighbor_hex"] == second["neighbor_hex"] == ""
    assert first["secret_length"] == second["secret_length"] == 8
    assert first["authorized_roundtrip_pass"] and second["authorized_roundtrip_pass"]
    assert first["encoded_length"] != second["encoded_length"]


def test_source_failure_blocks_the_matrix_without_execution_error():
    family = next(family for family in FAMILIES if family.family_id == "X19")
    result = matrix(family)
    assert result["states"]["S"]["existing"]["status"] == "PASS"
    assert result["states"]["S"]["invariant"]["status"] == "FAIL"
    assert result["states"]["U"]["invariant"]["status"] == "FAIL"
    assert not result["reference_matrix_pass"]
    assert not result["construction_authorized"]


def test_diagnostic_serializes_all_28_without_hiding_failures():
    result = json.loads(json.dumps(report(), default=encode))
    assert len(result["reference_matrices"]) == 28
    assert result["current_check_summary"]["fail"] == ["X19"]
    assert result["current_check_summary"]["not_run"] == ["X02", "X15", "X18", "X22"]
    assert result["status"] == "HARD_BLOCKER"
    assert not result["construction_authorized"]
