"""Conservative, smoke-task-specific outcome classification."""

from __future__ import annotations


def classify(
    *,
    infrastructure_error: bool,
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
