from __future__ import annotations

import pytest

from cmpilot.outcome_classifier import (
    classification_dimensions,
    classify,
    correct_post_server_classification,
)


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


def test_post_server_schema_failure_is_agent_harness_not_infrastructure() -> None:
    classification = correct_post_server_classification(
        "infrastructure_failure",
        server_started=True,
        server_healthy=True,
        agent_launched=True,
    )

    assert classification == "agent_harness_failure"
    assert classification_dimensions(
        classification,
        server_started=True,
        server_healthy=True,
        agent_initialized=True,
        final_tests_passed=False,
    ) == {
        "infrastructure": "PASS",
        "server": "PASS",
        "agent_harness": "FAIL",
        "model_task_performance": "INCOMPLETE",
    }


@pytest.mark.parametrize(
    "failure",
    [
        "unsupported_assistant_message_fields",
        "http_400_message_schema",
        "action_format_failure",
        "mini_swe_configuration_failure",
        "adapter_exception",
    ],
)
def test_job_24703_like_failures_do_not_become_infrastructure(failure: str) -> None:
    assert failure
    assert classify(**SUCCESS_FACTS, agent_harness_error=True) == "agent_harness_failure"
