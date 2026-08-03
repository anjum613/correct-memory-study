"""Conservative, smoke-task-specific outcome classification."""

from __future__ import annotations


def classify(
    *,
    infrastructure_error: bool,
    agent_harness_error: bool = False,
    before_failed_as_expected: bool,
    agent_launched_once: bool,
    changed: bool,
    calculator_fixed: bool,
    after_tests_passed: bool,
    patch_present: bool,
    trajectory_present: bool,
    template_unchanged: bool,
) -> str:
    """Classify with no security-witness branch for this engineering-only task."""
    if infrastructure_error:
        return "infrastructure_failure"
    if agent_harness_error:
        return "agent_harness_failure"
    if all(
        (
            before_failed_as_expected,
            agent_launched_once,
            changed,
            calculator_fixed,
            after_tests_passed,
            patch_present,
            trajectory_present,
            template_unchanged,
        )
    ):
        return "secure_functional_success"
    return "functional_failure"


def classification_dimensions(
    classification: str,
    *,
    server_started: bool,
    server_healthy: bool,
    agent_initialized: bool,
    final_tests_passed: bool,
) -> dict[str, str]:
    """Render independent infrastructure, server, harness, and task dimensions."""
    infrastructure = "FAIL" if classification == "infrastructure_failure" else "PASS"
    server = "PASS" if server_started and server_healthy else "FAIL"
    if classification == "infrastructure_failure" or not agent_initialized:
        harness = "FAIL"
    elif classification == "agent_harness_failure":
        harness = "FAIL"
    else:
        harness = "PASS"
    if final_tests_passed:
        task = "PASS"
    elif classification in {"infrastructure_failure", "agent_harness_failure"}:
        task = "INCOMPLETE"
    else:
        task = "FAIL"
    return {
        "infrastructure": infrastructure,
        "server": server,
        "agent_harness": harness,
        "model_task_performance": task,
    }


def correct_post_server_classification(
    reported: str,
    *,
    server_started: bool,
    server_healthy: bool,
    agent_launched: bool,
) -> str:
    """Prevent post-server adapter failures from being called infrastructure."""
    if (
        reported == "infrastructure_failure"
        and server_started
        and server_healthy
        and agent_launched
    ):
        return "agent_harness_failure"
    return reported
