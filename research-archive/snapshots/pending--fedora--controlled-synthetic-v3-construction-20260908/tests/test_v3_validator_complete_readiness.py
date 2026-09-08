"""Regression tests for an honest, fail-closed canonical-test preflight."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.check_v3_validator_complete_readiness import (
    BASE, FAMILY_ORDER, ROOT, canonical_inventory, demonstrate_family, inspect,
    literal_security_test, main, result_of,
)


@pytest.mark.parametrize("family", FAMILY_ORDER)
def test_each_family_canonical_tests_fail_to_distinguish_missing_behavior(family):
    row = demonstrate_family(family)
    observed = {entry["fixture"]: entry for entry in row["observations"]}
    for fixture in ("empty_implementation", "syntax_error_implementation", "import_failure_sentinel"):
        assert observed[fixture]["public_test_result"] == "PASS"
        assert observed[fixture]["sealed_test_result"] == "PASS"
        assert observed[fixture]["candidate_code_executed"] is False
    assert observed["implementation_absent"]["public_test_result"].startswith("ASSERTION_FAILURE")
    assert observed["implementation_absent"]["sealed_test_result"] == "PASS"
    assert row["required_U_focal_failure_established"] is False
    assert set(row["matrix"].values()) == {"NOT_ESTABLISHED"}
    assert row["status"] == "INPUT_RELEASE_BLOCKED_NOT_A_FAMILY_REJECTION"


def test_all_inputs_match_recorded_release_and_readiness_remains_blocked():
    report = inspect()
    assert len(canonical_inventory()) == 168
    assert report["fixture_observations"] == 112
    assert report["families_with_required_matrix_established"] == 0
    assert report["construction_authorized"] is False
    assert report["human_semantic_decisions_made"] is False
    assert report["constructor_attempts_consumed"] == 0
    assert report["evaluated_agent_invocations"] == 0
    assert report["human_review_files_created"] == 0
    assert main(["--check"]) == 2


@pytest.mark.parametrize("filename", ["public_tests.py", "sealed_tests.py", "spec.json", "source_service.py"])
def test_altered_canonical_inputs_are_rejected_in_an_isolated_copy(tmp_path, filename):
    relative = BASE.relative_to(ROOT)
    shutil.copytree(BASE, tmp_path / relative, ignore=shutil.ignore_patterns("__pycache__"))
    path = tmp_path / relative / "families/X01" / filename
    path.write_bytes(path.read_bytes() + b"\n# changed inert verification copy\n")
    with pytest.raises(ValueError, match="protected input changed"):
        canonical_inventory(tmp_path)


def test_future_behavioral_test_cannot_be_silently_classified_as_current_placeholder(tmp_path):
    path = tmp_path / "sealed.py"
    path.write_text("def test_declared_obligations(candidate):\n    assert candidate.run() is True\n")
    assert not literal_security_test(path)


def test_errors_and_plain_assertions_are_never_classified_as_focal_failures():
    def assertion():
        assert False

    def crash():
        raise ImportError("inert meta-test error")

    assert result_of(assertion) == "ASSERTION_FAILURE_NOT_CLASSIFIED_AS_FOCAL_WITNESS"
    assert result_of(crash) == "HARNESS_ERROR:ImportError"
