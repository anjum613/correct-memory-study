#!/usr/bin/env python3
"""Read-only diagnostic of unfinished reference fixtures; never authorizes construction."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
import platform
import subprocess
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.verify_v3_x02_x22_clarification import inspect
from synthetic_triplets.controlled_v3_local_invariants_v1.catalog import FAMILIES
from synthetic_triplets.controlled_v3_local_invariants_v1.harness import matrix
from synthetic_triplets.controlled_v3_local_invariants_v1.public_tail import decode_response
from synthetic_triplets.controlled_v3_local_invariants_v1.references_tail import x19_source


def x19_evidence():
    """Observe only local response lengths and authorized decoding, with no external I/O."""
    examples = []
    for neighbor in (b"", b"ordinary"):
        for secret in (b"AAAAAAAA", b"ABCDEFGH"):
            response = x19_source(secret, neighbor)
            examples.append({
                "secret_hex": secret.hex(),
                "secret_length": len(secret),
                "neighbor_hex": neighbor.hex(),
                "encoded_length": len(response),
                "authorized_roundtrip_pass": decode_response(response) == (secret, neighbor),
            })
    return examples


def report():
    provenance = inspect(expected_manifest_sha256=
        "167251744b87c55f23ce06b61a70891c1192b7581c357a7d5458c22e0f94e1bc")
    results = {family.family_id: matrix(family) for family in FAMILIES}
    for number in range(1, 29):
        family_id = f"X{number:02d}"
        if family_id not in results:
            results[family_id] = {"family_id": family_id,
                "reference_matrix_pass": None, "status": "NOT_IMPLEMENTED_NOT_RUN",
                "construction_authorized": False}
    passed = [key for key in sorted(results) if results[key]["reference_matrix_pass"] is True]
    failed = [key for key in sorted(results) if results[key]["reference_matrix_pass"] is False]
    unrun = [key for key in sorted(results) if results[key]["reference_matrix_pass"] is None]
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    spec_path = "synthetic_triplets/controlled_v3_expansion/family_specs.json"
    return {
        "status": "HARD_BLOCKER",
        "scope": "Unfinished local reference preflight; not a canonical release or candidate-admission gate.",
        "baseline_commit": commit,
        "environment": {"python": platform.python_version(), "zlib_runtime": zlib.ZLIB_RUNTIME_VERSION},
        "reference_matrices": {key: results[key] for key in sorted(results)},
        "current_check_summary": {"pass": passed, "fail": failed, "not_run": unrun},
        "blocker": {
            "family_id": "X19",
            "classification": "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED",
            "audit_type": "Assistant pre-construction design diagnostic; not human review.",
            "scientific_specification_path": spec_path,
            "scientific_specification_sha256": hashlib.sha256((ROOT / spec_path).read_bytes()).hexdigest(),
            "source_valid_assumption": "The ordinary neighboring text cannot be varied by an observer who sees encoded lengths.",
            "full_target_obligation": "Under the frozen observation model, caller-selected text cannot distinguish equal-length permitted confidential alternatives.",
            "fixed_dimensions": "Secret readership, encoded-length observation and secret length class are fixed in both contexts.",
            "missing_contract": [
                "The permitted confidential alternatives and precise observation equivalence are not defined by a pre-existing authoritative X19 contract.",
                "The stated source assumption does not establish equal-length confidentiality under raw encoded-length observation.",
            ],
            "local_behavioral_evidence": x19_evidence(),
            "interpretation": "The present source distinguishes two equal-length local secrets even with empty, fixed neighboring text. Its outputs decode correctly. The present target witness also distinguishes them with fixed ordinary text, so that failure does not isolate the sole intended trust shift.",
            "limits_of_evidence": "This is not an impossibility proof for every compressor or secret domain. The eight-byte domain and zlib procedure are unfinished implementation choices, not recovered normative authority. Choosing a secret domain with equal baseline compressed lengths, changing what lengths the observer sees, or measuring only incremental leakage would add a substantive scientific assumption; no such change has been made.",
            "required_resolution": "An explicit prospective scientific decision must resolve the permitted-secret/observation contract and demonstrate source security without a second mismatch. Do not silently tune the witness, replace S, or narrow the domain to make the matrix pass.",
        },
        "coverage_audit": {
            "status": "INCOMPLETE_STOPPED_AT_SPECIFICATION_BLOCKER",
            "all_28_full_feature_and_security_contracts_verified": False,
            "passing_matrices_mean": "Only the currently implemented checks pass. They do not establish full frozen-contract coverage or semantic admission.",
            "subjective_human_gates_automated": False,
        },
        "integrity_audit": {
            "prior_scientific_inputs": provenance,
            "new_candidate_patch_tree_integrity_gate_complete": False,
            "new_canonical_test_tamper_rejection_gate_complete": False,
            "reference_harness_is_an_untrusted_code_sandbox": False,
            "scope_warning": "Exception-classification meta-tests include a raised TimeoutError, not enforcement of a real execution deadline.",
        },
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_review_files_created": 0,
        "counter_basis": "The pinned V3 ledger is empty with outcomes false; this workflow has invoked only reference diagnostics and tests, not constructors, evaluated agents or reviewers. Preserved invalid historical attestations are not human reviews.",
        "construction_authorized": False,
        "canonical_release_frozen": False,
        "new_protocol_version_created": False,
        "release_commit": None,
    }


def encode(value):
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, Decimal):
        return {"decimal": str(value)}
    raise TypeError(type(value).__name__)


if __name__ == "__main__":
    print(json.dumps(report(), default=encode, indent=2, sort_keys=True))
    raise SystemExit(2)  # Diagnostic blocker, never a successful admission/freeze.
