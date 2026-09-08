"""Reference preflight, not a sandbox or an untrusted-candidate admission API."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


class ExecutionError(Exception):
    """Application exceptions cannot become focal-invariant evidence."""


class InvariantViolation(Exception):
    def __init__(self, condition: str, actual, expected):
        super().__init__(condition)
        self.condition, self.actual, self.expected = condition, actual, expected


def observe(condition: str, actual, expected) -> None:
    """Called only by the frozen observer, after direct application execution."""
    if actual != expected:
        raise InvariantViolation(condition, actual, expected)


def invoke(function: Callable, *args, **kwargs):
    try:
        return function(*args, **kwargs)
    except BaseException as error:
        # Includes an application attempting to raise our evidence exception.
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


def functional(test: Callable, implementation: Callable) -> dict:
    try:
        test(implementation)
    except AssertionError:
        return {"status": "FAIL"}
    except BaseException as error:
        return {"status": "HARNESS_ERROR", "error": type(error).__name__}
    return {"status": "PASS"}


def invariant(test: Callable, implementation: Callable) -> dict:
    try:
        test(implementation)
    except InvariantViolation as error:
        return {"status": "FAIL", "condition": error.condition,
                "actual": error.actual, "expected": error.expected}
    except BaseException as error:
        return {"status": "HARNESS_ERROR", "error": type(error).__name__}
    return {"status": "PASS"}


def matrix(family: Family) -> dict:
    states = {"S": family.source, "B": family.base,
              "U": family.reuse, "R": family.repair}
    rows = {}
    for name, implementation in states.items():
        row = {"existing": functional(family.source_functional if name == "S" else family.existing, implementation)}
        if name != "S":
            row["feature"] = functional(family.feature, implementation)
        row["invariant"] = invariant(family.source_invariant if name == "S" else family.focal, implementation)
        rows[name] = row
    expected = {
        "S": {"existing": "PASS", "invariant": "PASS"},
        "B": {"existing": "PASS", "feature": "FAIL", "invariant": "PASS"},
        "U": {"existing": "PASS", "feature": "PASS", "invariant": "FAIL"},
        "R": {"existing": "PASS", "feature": "PASS", "invariant": "PASS"},
    }
    return {"family_id": family.family_id, "states": rows,
            "reference_matrix_pass": all(rows[s][k]["status"] == value
                for s, checks in expected.items() for k, value in checks.items()),
            "construction_authorized": False,
            "scope": "Pinned local reference fixtures only; not arbitrary candidate code."}
