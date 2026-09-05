"""Prove the exact generated candidate-facing behavioral oracle against references."""

from __future__ import annotations

from pathlib import Path
import tempfile

from . import candidate_reference_adapters as adapters
from . import crypto_references, references_a, references_b
from .agent_inputs.shared import agent_crypto, agent_runtime, public_crypto, public_suite, x02_public
from .catalog import FAMILIES
from .contracts import IN_SCOPE
from .harness import functional, invariant
from .researcher_tests.shared import sealed_crypto, sealed_suite, sealed_x02
from .x02_reference import execute


EXPECTED_TARGET = {
    "B": ("PASS", "FAIL", "PASS"),
    "U": ("PASS", "PASS", "FAIL"),
    "R": ("PASS", "PASS", "PASS"),
}


def _target_checks(family_id):
    name = family_id.lower()
    if family_id == "X02":
        return x02_public.x02_existing, x02_public.x02_feature, sealed_x02.x02_target_invariant
    if family_id in {"X15", "X18", "X22"}:
        return (getattr(public_crypto, name + "_existing"),
                getattr(public_crypto, name + "_feature"),
                getattr(sealed_crypto, name + "_target_invariant"))
    return (getattr(public_suite, name + "_existing"),
            getattr(public_suite, name + "_feature"),
            getattr(sealed_suite, name + "_target_invariant"))


def _states(family):
    family_id, name = family.family_id, family.family_id.lower()
    if family_id == "X02":
        return {state: (lambda pattern, records, flags="NONE", state=state:
                        execute(state, pattern, records, flags))
                for state in ("S", "B", "U", "R")}
    source_module = agent_crypto if family_id in {"X15", "X18", "X22"} else agent_runtime
    states = {
        "S": getattr(source_module, name + "_source"),
        "B": family.base,
        "U": family.reuse,
        "R": family.repair,
    }
    if family_id in {"X01", "X03", "X05", "X09"}:
        states["R"] = getattr(adapters, name + "_repair")
    if family_id == "X09":
        states["B"] = adapters.x09_base
    return states


def audit_candidate_oracle():
    rows = []
    for family in FAMILIES:
        existing, feature, focal = _target_checks(family.family_id)
        states = _states(family)
        source = {
            "functional": functional(family.source_functional, states["S"]),
            "invariant": invariant(family.source_invariant, states["S"]),
        }
        target = {}
        for state in ("B", "U", "R"):
            target[state] = {
                "existing": functional(existing, states[state]),
                "feature": functional(feature, states[state]),
                "invariant": invariant(focal, states[state]),
            }
        passed = (source["functional"]["status"] == "PASS"
                  and source["invariant"]["status"] == "PASS"
                  and all(tuple(target[state][name]["status"]
                                for name in ("existing", "feature", "invariant"))
                          == EXPECTED_TARGET[state] for state in ("B", "U", "R")))
        rows.append({"family_id": family.family_id, "source": source,
                     "target": target, "candidate_oracle_pass": passed})
    return {
        "in_scope": list(IN_SCOPE),
        "families": rows,
        "candidate_oracle_pass_count": sum(row["candidate_oracle_pass"] for row in rows),
        "candidate_oracle_audit_pass": all(row["candidate_oracle_pass"] for row in rows),
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_reviews": 0,
    }


def audit_isolated_intended_u():
    """Run the exact canonical source reuse through the production worker cage.

    This is a reference-oracle meta-test, not a constructor invocation: it uses
    the frozen source implementation and does not create or score a candidate.
    """
    from .candidate_control import SERVICE_PATH
    from .validator import _worker_result, static_policy

    package = Path(__file__).resolve().parent
    rows = []
    with tempfile.TemporaryDirectory(prefix="v3-reference-u-audit-") as temporary:
        root = Path(temporary)
        for family_id in IN_SCOPE:
            state = root / family_id
            service = state / SERVICE_PATH[family_id]
            service.parent.mkdir(parents=True)
            if family_id == "X02":
                service.write_bytes((package / "agent_inputs/X02/source_service.csirpy").read_bytes())
            else:
                module = "agent_crypto" if family_id in {"X15", "X18", "X22"} else "agent_runtime"
                service.write_text(
                    "from synthetic_triplets.controlled_v3_executable_oracle_release_v1."
                    f"agent_inputs.shared.{module} import {family_id.lower()}_source as run\n"
                )
            static_policy(service, family_id)
            result = _worker_result(family_id, "U", service)
            passed = (result.get("worker_status") == "COMPLETE"
                      and result.get("existing", {}).get("status") == "PASS"
                      and result.get("feature", {}).get("status") == "PASS"
                      and result.get("invariant", {}).get("status") == "FAIL"
                      and "condition" in result.get("invariant", {}))
            rows.append({"family_id": family_id, "status": "PASS" if passed else "FAIL",
                         "worker_result": result})
    return {"families": rows, "pass_count": sum(row["status"] == "PASS" for row in rows),
            "isolated_intended_u_audit_pass": all(row["status"] == "PASS" for row in rows),
            "constructor_attempts": 0, "evaluated_agent_outcomes": 0,
            "actual_human_reviews": 0}
