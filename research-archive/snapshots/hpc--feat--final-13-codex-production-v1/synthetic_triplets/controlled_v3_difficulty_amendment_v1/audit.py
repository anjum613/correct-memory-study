"""Trusted local matrix/coverage verification; never a construction invocation."""
from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
import types

from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import candidate_oracle_audit as original
from synthetic_triplets.controlled_v3_executable_oracle_release_v1 import coverage_audit
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.catalog import FAMILIES
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.harness import functional, invariant, matrix, substitute
from .interface_adapter import adapt_application, INTERFACE_FAMILIES
from .reference_states import states

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "protocols/controlled-synthetic-v3-difficulty-amendment-v1"


def serializable(value):
    if isinstance(value, bytes):
        return {"type": "bytes", "hex": value.hex()}
    if isinstance(value, Decimal):
        return {"type": "decimal", "text": str(value)}
    if isinstance(value, dict):
        return {key: serializable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [serializable(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return {"type": "set", "items": sorted((serializable(item) for item in value),
                                               key=lambda item: json.dumps(item, sort_keys=True))}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError("unsupported audit evidence type: " + type(value).__name__)


@contextmanager
def public_suite(family):
    """Import only the exact per-family export into a temporary module namespace."""
    repository = DIRECTORY / "exports" / family / "repository"
    names = [name for name in sys.modules if name == "fixture_api" or name.startswith("fixture_api.")]
    saved = {name: sys.modules.pop(name) for name in names}
    package = types.ModuleType("fixture_api")
    package.__path__ = [str(repository / "fixture_api")]
    sys.modules["fixture_api"] = package
    try:
        spec = importlib.util.spec_from_file_location("difficulty_public_checks", repository / "public_tests.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        yield module
    finally:
        for name in list(sys.modules):
            if name == "fixture_api" or name.startswith("fixture_api."):
                del sys.modules[name]
        sys.modules.update(saved)


def amended_family(family):
    if family.family_id not in INTERFACE_FAMILIES | {"X05"}:
        return family
    replacements = states(family)
    return substitute(family, **{key: adapt_application(family.family_id, replacements[state])
        for key, state in (("source", "S"), ("base", "B"), ("reuse", "U"), ("repair", "R"))})


def run():
    baseline_coverage = coverage_audit.audit()
    baseline_generated = original.audit_candidate_oracle()
    rows = []
    for family in FAMILIES:
        state_functions = states(family)
        with public_suite(family.family_id) as public:
            existing = getattr(public, family.family_id.lower() + "_existing")
            feature = getattr(public, family.family_id.lower() + "_feature")
            public_rows = {state: {"existing": functional(existing, state_functions[state]),
                                   "feature": functional(feature, state_functions[state])}
                           for state in ("B", "U", "R")}
        updated = amended_family(family)
        full = matrix(updated)
        _existing, _feature, focal = original._target_checks(family.family_id)
        original_invariant = invariant(focal, original._states(family)["U"])
        mapped_invariant = invariant(focal, adapt_application(family.family_id, state_functions["U"]))
        negative = {}
        if family.family_id in INTERFACE_FAMILIES | {"X05"}:
            negative = {
                "secure_U_rejected": not matrix(substitute(updated, reuse=updated.repair))["reference_matrix_pass"],
                "insecure_R_rejected": not matrix(substitute(updated, repair=updated.reuse))["reference_matrix_pass"],
                "feature_regressing_R_rejected": not matrix(substitute(updated, repair=updated.base))["reference_matrix_pass"],
            }
        public_pass = all(row["existing"]["status"] == "PASS"
                          and row["feature"]["status"] == ("FAIL" if state == "B" else "PASS")
                          for state, row in public_rows.items())
        same_failure = (mapped_invariant["status"] == original_invariant["status"] == "FAIL"
                        and mapped_invariant.get("condition") == original_invariant.get("condition"))
        rows.append({"family_id": family.family_id, "public": public_rows,
                     "full_frozen_contract_matrix": full, "intended_failure_condition_preserved": same_failure,
                     "intended_U_invariant": mapped_invariant, "negative_meta": negative,
                     "coverage_scenarios": list(coverage_audit.SCENARIOS[family.family_id]),
                     "pass": full["reference_matrix_pass"] and public_pass and same_failure and all(negative.values())})
    return serializable({"schema": "v3-difficulty-oracle-coverage/1", "families": rows,
            "pass_count": sum(row["pass"] for row in rows),
            "pass": all(row["pass"] for row in rows) and baseline_coverage["coverage_audit_pass"]
                    and baseline_generated["candidate_oracle_audit_pass"],
            "original_coverage": baseline_coverage, "original_generated_matrices": baseline_generated,
            "constructor_attempts": 0, "evaluated_agent_outcomes": 0, "actual_human_reviews": 0,
            "semantic_naturalness_human_review_performed": False})
