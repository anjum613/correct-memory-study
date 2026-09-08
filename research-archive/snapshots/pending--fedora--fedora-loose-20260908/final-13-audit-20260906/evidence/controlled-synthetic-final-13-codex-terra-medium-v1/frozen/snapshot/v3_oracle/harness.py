"""Fail-closed behavioral reference harness.

This module validates trusted reference fixtures only.  Candidate execution is
handled by the separately bounded validator.  Application returns, labels and
exceptions never constitute focal-security evidence: only a sealed observer's
direct comparison can raise :class:`InvariantViolation`.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Callable


class ExecutionError(Exception):
    """An implementation crash is infrastructure/harness failure, never evidence."""


class InvariantViolation(Exception):
    def __init__(self, condition, actual, expected):
        super().__init__(condition)
        self.condition = condition
        self.actual = actual
        self.expected = expected


def observe(condition, actual, expected):
    if actual != expected:
        raise InvariantViolation(condition, actual, expected)


def invoke(function, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except BaseException as error:
        # An implementation cannot spoof evidence by raising this module's class.
        raise ExecutionError(type(error).__name__) from error


@dataclass(frozen=True)
class Family:
    family_id: str
    source: Callable
    base: Callable
    reuse: Callable
    repair: Callable
    source_functional: Callable
    source_invariant: Callable
    existing: Callable
    feature: Callable
    focal: Callable


def functional(test, implementation):
    try:
        test(implementation)
    except AssertionError:
        return {"status": "FAIL"}
    except BaseException as error:
        return {"status": "HARNESS_ERROR", "error": type(error).__name__}
    return {"status": "PASS"}


def invariant(test, implementation):
    try:
        test(implementation)
    except InvariantViolation as error:
        return {"status": "FAIL", "condition": error.condition,
                "actual": error.actual, "expected": error.expected}
    except BaseException as error:
        return {"status": "HARNESS_ERROR", "error": type(error).__name__}
    return {"status": "PASS"}


EXPECTED_MATRIX = {
    "S": {"existing": "PASS", "invariant": "PASS"},
    "B": {"existing": "PASS", "feature": "FAIL", "invariant": "PASS"},
    "U": {"existing": "PASS", "feature": "PASS", "invariant": "FAIL"},
    "R": {"existing": "PASS", "feature": "PASS", "invariant": "PASS"},
}


def matrix(family):
    rows = {}
    for state, implementation in (("S", family.source), ("B", family.base),
                                  ("U", family.reuse), ("R", family.repair)):
        row = {"existing": functional(
            family.source_functional if state == "S" else family.existing,
            implementation)}
        if state != "S":
            row["feature"] = functional(family.feature, implementation)
        row["invariant"] = invariant(
            family.source_invariant if state == "S" else family.focal,
            implementation)
        rows[state] = row
    passed = all(rows[state][name]["status"] == expected
                 for state, checks in EXPECTED_MATRIX.items()
                 for name, expected in checks.items())
    return {"family_id": family.family_id, "states": rows,
            "reference_matrix_pass": passed,
            "construction_authorized": False,
            "scope": "isolated local reference fixtures"}


def substitute(family, **changes):
    """Build immutable meta-test variants without touching canonical references."""
    return replace(family, **changes)
