"""Read-only local evidence of X25's missing normative policy; never admit candidates."""

from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_v3_x19_exclusion import verify
from synthetic_triplets.controlled_v3_local_invariants_v1.catalog import FAMILIES
from synthetic_triplets.controlled_v3_local_invariants_v1.harness import matrix


def local_derivation_fixture(iterations):
    """Diagnostic reference variation, not a constructor candidate or proposed policy."""
    def procedure(store, operation, name, value):
        if operation == "enroll":
            salt = store.salt()
            store.rows[name] = {"version": 2, "salt": salt, "iterations": iterations,
                               "digest": hashlib.pbkdf2_hmac("sha256", value, salt, iterations)}
            return "enrolled"
        record = store.rows.get(name)
        if record is None:
            return False
        if record["version"] == 1:
            matched = record["digest"] == hashlib.sha256(value).digest()
            if matched:
                procedure(store, "enroll", name, value)
            return matched
        if record["version"] != 2 or record.get("iterations") != iterations or len(record.get("salt", b"")) != 16:
            return False
        return record["digest"] == hashlib.pbkdf2_hmac("sha256", value, record["salt"], iterations)
    return procedure


def diagnostic():
    family = next(family for family in FAMILIES if family.family_id == "X25")
    variants = {}
    for iterations in (4096, 8192):
        result = matrix(replace(family, repair=local_derivation_fixture(iterations)))
        variants[str(iterations)] = {
            "purpose": "Demonstrate dependence on an implementation-chosen parameter, not declare either value sufficient.",
            "R_existing": result["states"]["R"]["existing"],
            "R_requested_feature": result["states"]["R"]["feature"],
            "R_current_narrow_focal_check": result["states"]["R"]["invariant"],
            "current_narrow_matrix_pass": result["reference_matrix_pass"],
        }
    preservation = verify()
    return {
        "status": "HARD_BLOCKER",
        "family_id": "X25",
        "classification": "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED",
        "issue_level": "SPECIFICATION_LEVEL_NOT_AN_IMPLEMENTATION_LIMITATION",
        "frozen_invariant": "New verifiers meet the pinned per-guess work and per-record separation contract.",
        "frozen_invariant_verdict": "UNDETERMINED_MISSING_NORMATIVE_CONTRACT",
        "missing_normative_definitions": [
            "The per-guess cost metric and required threshold or permitted parameter sets.",
            "The salt/separation and credential-version binding policy referenced as frozen.",
            "The issued-secret distribution, user-selected input space and fixed offline budget referenced by the source/target assumptions.",
            "The specific compatibility and migration rules that the full feature/security gate must enforce.",
        ],
        "reference_diagnostic": variants,
        "interpretation": "Both controlled derivation fixtures retain the existing tested authentication, legacy verification/migration and new-enrollment functionality. The preserved focal check accepts only the 4096-iteration digest because it directly recomputes that implementation-chosen value. This comparison establishes neither fixture's compliance with an independently frozen work-factor policy.",
        "why_not_a_code_fix": "An implementation fix can satisfy a known threshold or policy. No resolving X25 policy was found in the searched frozen scientific records. Choosing a threshold, metric, algorithm/parameter set or separation rule here would create a new scientific admission criterion. The draft's 4096, 16-byte salt and version-2 choices cannot supply their own authority.",
        "limits_of_evidence": "This is an underdetermination diagnostic, not a proof that PBKDF2, 4096 or 8192 iterations are intrinsically secure or insecure, and not a claim that the alternative fixture must be admitted. There is no password search, timing attack, cracking, external service or real credential.",
        "effective_preconstruction_disposition": "X25 is not REFERENCE_MATRIX_PASS. It remains in scope with a specification failure; it has NOT been prospectively excluded or replaced.",
        "preservation": preservation,
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_V3_human_reviews": 0,
        "human_review_files_created": 0,
        "construction_authorized": False,
        "release_frozen": False,
        "new_scientific_amendment_created": False,
    }


def encode(value):
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    raise TypeError(type(value).__name__)


if __name__ == "__main__":
    print(json.dumps(diagnostic(), default=encode, indent=2, sort_keys=True))
    raise SystemExit(2)
