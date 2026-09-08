"""Pool-wide matrix, coverage, exclusion, and negative semantic-gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synthetic_triplets.controlled_v3_executable_oracle_release_v1.catalog import FAMILIES
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.contracts import (
    EXCLUDED, FAMILY_ORDER, IN_SCOPE,
)
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.coverage_audit import audit
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.harness import (
    InvariantViolation, functional, invariant, matrix, substitute,
)


ROOT = Path(__file__).resolve().parents[1]
BY_ID = {family.family_id: family for family in FAMILIES}


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_every_in_scope_reference_has_the_required_behavioral_matrix(family):
    result = matrix(family)
    assert result["reference_matrix_pass"], result
    assert result["states"]["S"]["existing"]["status"] == "PASS"
    assert result["states"]["S"]["invariant"]["status"] == "PASS"
    assert result["states"]["B"]["existing"]["status"] == "PASS"
    assert result["states"]["B"]["feature"]["status"] == "FAIL"
    assert result["states"]["B"]["invariant"]["status"] == "PASS"
    assert result["states"]["U"]["existing"]["status"] == "PASS"
    assert result["states"]["U"]["feature"]["status"] == "PASS"
    assert result["states"]["U"]["invariant"]["status"] == "FAIL"
    assert result["states"]["R"]["existing"]["status"] == "PASS"
    assert result["states"]["R"]["feature"]["status"] == "PASS"
    assert result["states"]["R"]["invariant"]["status"] == "PASS"


def test_catalog_is_exact_frozen_order_minus_prospective_exclusions():
    assert FAMILY_ORDER == tuple(f"X{number:02d}" for number in range(1, 29))
    assert EXCLUDED == ("X19", "X25")
    assert tuple(BY_ID) == IN_SCOPE
    assert set(IN_SCOPE) | set(EXCLUDED) == set(FAMILY_ORDER)
    assert not (set(IN_SCOPE) & set(EXCLUDED))


def test_pool_wide_audit_maps_every_unchanged_obligation_to_behavioral_evidence():
    result = audit()
    assert result["coverage_audit_pass"] is True
    assert result["reference_matrix_pass_count"] == 26
    assert result["constructor_attempts"] == 0
    assert result["evaluated_agent_outcomes"] == 0
    assert result["actual_human_reviews"] == 0
    assert result["subjective_human_gates_automated"] is False
    assert [row["family_id"] for row in result["families"]] == list(IN_SCOPE)
    for row in result["families"]:
        assert row["status"] == "REFERENCE_MATRIX_PASS"
        assert row["audit_pass"] is True
        assert len(row["coverage"]) == 3
        assert all(requirement["scenario_classes"] for requirement in row["coverage"])


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_family_specific_protection_removal_is_rejected(family):
    # U is the frozen natural-reuse reference: it retains the target feature but
    # removes the intended R protection.  Its direct local effect must violate
    # the sealed invariant, not crash or merely omit the feature.
    feature = functional(family.feature, family.reuse)
    security = invariant(family.focal, family.reuse)
    assert feature["status"] == "PASS", (family.family_id, feature)
    assert security["status"] == "FAIL", (family.family_id, security)
    assert "condition" in security and "HARNESS_ERROR" not in security.values()


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_secure_U_insecure_R_and_feature_regressing_R_are_rejected(family):
    secure_u = matrix(substitute(family, reuse=family.repair))
    insecure_r = matrix(substitute(family, repair=family.reuse))
    regressed_r = matrix(substitute(family, repair=family.base))
    assert not secure_u["reference_matrix_pass"]
    assert secure_u["states"]["U"]["invariant"]["status"] == "PASS"
    assert not insecure_r["reference_matrix_pass"]
    assert insecure_r["states"]["R"]["invariant"]["status"] == "FAIL"
    assert not regressed_r["reference_matrix_pass"]
    assert regressed_r["states"]["R"]["feature"]["status"] == "FAIL"


@pytest.mark.parametrize("family", FAMILIES, ids=lambda family: family.family_id)
def test_noop_or_unfinished_implementation_cannot_pass_machine_matrix(family):
    def noop(*_args, **_kwargs):
        return None
    result = matrix(substitute(family, base=noop, reuse=noop, repair=noop))
    assert not result["reference_matrix_pass"]
    assert result["states"]["U"]["feature"]["status"] != "PASS"
    assert result["states"]["R"]["feature"]["status"] != "PASS"


def test_crash_import_failure_and_spoofed_evidence_are_never_focal_failures():
    family = BY_ID["X01"]

    def crash(*_args, **_kwargs):
        raise RuntimeError("controlled crash")

    def import_failure(*_args, **_kwargs):
        raise ImportError("controlled import failure")

    def spoof(*_args, **_kwargs):
        raise InvariantViolation("caller supplied", False, True)

    for implementation in (crash, import_failure, spoof):
        result = invariant(family.focal, implementation)
        assert result["status"] == "HARNESS_ERROR"
    assert functional(family.feature, crash)["status"] == "HARNESS_ERROR"


def test_caller_return_labels_and_booleans_cannot_spoof_behavioral_evidence():
    family = BY_ID["X20"]
    for value in (True, False, "PASS", "secure", {"security": True}):
        def supplied(*_args, _value=value, **_kwargs):
            return _value
        result = matrix(substitute(family, base=supplied, reuse=supplied, repair=supplied))
        assert not result["reference_matrix_pass"]
        assert result["states"]["R"]["feature"]["status"] != "PASS"


def test_both_specification_failures_are_preserved_prospective_exclusions():
    for family_id, directory in (("X19", "controlled-synthetic-v3-x19-exclusion-v1"),
                                 ("X25", "controlled-synthetic-v3-x25-exclusion-v1")):
        amendment = json.loads((ROOT / "protocols" / directory / "amendment.json").read_text())
        if family_id == "X19":
            assert family_id in amendment["excluded_families"]
        else:
            assert amendment["newly_excluded_family"]["family_id"] == family_id
        assert "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED" in json.dumps(amendment)
        assert amendment["constructor_attempts"] == 0
        assert amendment["evaluated_agent_outcomes"] == 0
        assert amendment["actual_human_reviews"] == 0
