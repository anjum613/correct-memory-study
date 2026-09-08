"""Expected S/B/U/R states for X02/X15/X18/X22."""

from dataclasses import replace
import pytest

from synthetic_triplets.controlled_v3_executable_oracle_release_v1.catalog import FAMILIES
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.harness import (
    InvariantViolation,
    matrix,
)


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_complete_reference_matrix(family):
    result = matrix(family)
    assert result["reference_matrix_pass"], result
    assert not result["construction_authorized"]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_secure_u_is_rejected(family):
    assert not matrix(replace(family, reuse=family.repair))["reference_matrix_pass"]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_insecure_r_is_rejected(family):
    assert not matrix(replace(family, repair=family.reuse))["reference_matrix_pass"]


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_feature_regressing_r_is_rejected(family):
    assert not matrix(replace(family, repair=family.base))["reference_matrix_pass"]


@pytest.mark.parametrize("failure", [RuntimeError, ImportError, TimeoutError, NotImplementedError])
def test_execution_failures_cannot_become_the_intended_u_failure(failure):
    def broken(*args, **kwargs):
        raise failure("local failure fixture")
    for family in FAMILIES:
        result = matrix(replace(family, reuse=broken))
        assert result["states"]["U"]["invariant"]["status"] == "HARNESS_ERROR"
        assert not result["reference_matrix_pass"]


def test_caller_evidence_spoof_cannot_pass():
    def spoof(*args, **kwargs):
        raise InvariantViolation("caller label", False, True)
    for family in FAMILIES:
        result = matrix(replace(family, reuse=spoof))
        assert result["states"]["U"]["invariant"]["status"] == "HARNESS_ERROR"
        assert not result["reference_matrix_pass"]
