"""Local reference checks. These never invoke a constructor or evaluated agent."""

from dataclasses import replace
import pytest

from synthetic_triplets.controlled_v3_local_invariants_v1.catalog import FAMILIES
from synthetic_triplets.controlled_v3_local_invariants_v1.harness import (
    InvariantViolation, matrix,
)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.family_id)
def test_reference_matrix(family):
    result = matrix(family)
    assert result["reference_matrix_pass"], result
    assert result["construction_authorized"] is False


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.family_id)
def test_secure_reuse_is_not_an_admissible_unsafe_reference(family):
    assert not matrix(replace(family, reuse=family.repair))["reference_matrix_pass"]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.family_id)
def test_insecure_repair_is_rejected(family):
    assert not matrix(replace(family, repair=family.reuse))["reference_matrix_pass"]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda f: f.family_id)
def test_feature_regression_is_rejected(family):
    assert not matrix(replace(family, repair=family.base))["reference_matrix_pass"]


@pytest.mark.parametrize("failure", [RuntimeError, ImportError, TimeoutError, NotImplementedError])
def test_execution_errors_never_supply_a_focal_failure(failure):
    def broken(*args, **kwargs):
        raise failure("local negative fixture")
    for family in FAMILIES:
        result = matrix(replace(family, reuse=broken))
        assert not result["reference_matrix_pass"]
        assert result["states"]["U"]["invariant"]["status"] == "HARNESS_ERROR"


def test_invariant_exception_raised_by_application_is_not_evidence():
    def spoof(*args, **kwargs):
        raise InvariantViolation("caller claim", False, True)
    for family in FAMILIES:
        result = matrix(replace(family, reuse=spoof))
        assert result["states"]["U"]["invariant"]["status"] == "HARNESS_ERROR"
        assert not result["reference_matrix_pass"]


def test_returned_labels_and_missing_behavior_do_not_complete_a_matrix():
    for replacement in (lambda *a, **k: None, lambda *a, **k: True,
                        lambda *a, **k: {"functional": True, "security": False}):
        for family in FAMILIES:
            result = matrix(replace(family, reuse=replacement))
            assert not result["reference_matrix_pass"]
