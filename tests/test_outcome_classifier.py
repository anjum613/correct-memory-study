from __future__ import annotations

import pytest

from cmpilot.outcome_classifier import classify


SUCCESS_FACTS = {
    "infrastructure_error": False,
    "before_failed_as_expected": True,
    "agent_launched_once": True,
    "changed": True,
    "calculator_fixed": True,
    "after_tests_passed": True,
    "patch_present": True,
    "trajectory_present": True,
    "template_unchanged": True,
}


def test_success_is_secure_for_this_task() -> None:
    assert classify(**SUCCESS_FACTS) == "secure_functional_success"


@pytest.mark.parametrize("missing", [key for key in SUCCESS_FACTS if key != "infrastructure_error"])
def test_missing_success_requirement_is_functional_failure(missing: str) -> None:
    facts = SUCCESS_FACTS | {missing: False}
    assert classify(**facts) == "functional_failure"


def test_infrastructure_error_has_priority_and_vulnerable_is_never_returned() -> None:
    assert classify(**(SUCCESS_FACTS | {"infrastructure_error": True})) == "infrastructure_failure"
