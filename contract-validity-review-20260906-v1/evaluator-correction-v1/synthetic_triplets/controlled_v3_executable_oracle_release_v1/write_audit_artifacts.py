#!/usr/bin/env python3
"""Write deterministic, status-only pre-construction audit artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from .candidate_oracle_audit import audit_candidate_oracle, audit_isolated_intended_u
from .coverage_audit import audit as audit_coverage


PACKAGE = Path(__file__).resolve().parent


def _write(name, document):
    path = PACKAGE / name
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n")
    return path


def build():
    coverage = audit_coverage()
    candidate = audit_candidate_oracle()
    isolated = audit_isolated_intended_u()
    if not coverage["coverage_audit_pass"] or coverage["reference_matrix_pass_count"] != 26:
        raise ValueError("reference/coverage audit is not complete")
    if not candidate["candidate_oracle_audit_pass"] or candidate["candidate_oracle_pass_count"] != 26:
        raise ValueError("generated candidate oracle is not complete")
    if not isolated["isolated_intended_u_audit_pass"] or isolated["pass_count"] != 26:
        raise ValueError("isolated intended-U audit is not complete")

    reference_rows = []
    coverage_rows = []
    for row in coverage["families"]:
        reference_rows.append({
            "family_id": row["family_id"],
            "status": row["status"],
            "matrix": {state: {name: result["status"] for name, result in checks.items()}
                       for state, checks in row["matrix"].items()},
            "intended_U_failure_condition": row["matrix"]["U"]["invariant"].get("condition"),
            "negative_meta": row["negative_meta"],
        })
        coverage_rows.append({
            "family_id": row["family_id"],
            "status": row["status"],
            "audit_pass": row["audit_pass"],
            "source_functional": row["source_functional"],
            "source_invariant": row["source_invariant"],
            "full_contract_R_feature": row["full_contract_R_feature"],
            "full_contract_R_invariant": row["full_contract_R_invariant"],
            "coverage": row["coverage"],
        })
    reference_document = {
        "schema_version": "controlled-v3-reference-matrix-results/1",
        "status": "PASS",
        "families": reference_rows,
        "pass_count": 26,
        "excluded": coverage["excluded"],
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_reviews": 0,
    }
    coverage_document = {
        "schema_version": "controlled-v3-frozen-contract-coverage-audit/1",
        "status": "PASS",
        "specification_sha256": coverage["specification_sha256"],
        "families": coverage_rows,
        "pass_count": 26,
        "subjective_human_gates_automated": False,
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_reviews": 0,
    }
    candidate_document = {
        "schema_version": "controlled-v3-generated-candidate-oracle-results/1",
        "status": "PASS",
        "families": [{
            "family_id": row["family_id"],
            "source": {name: result["status"] for name, result in row["source"].items()},
            "target": {state: {name: result["status"] for name, result in checks.items()}
                       for state, checks in row["target"].items()},
            "candidate_oracle_pass": row["candidate_oracle_pass"],
        } for row in candidate["families"]],
        "pass_count": 26,
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_reviews": 0,
    }
    isolated_document = {
        "schema_version": "controlled-v3-isolated-intended-u-results/1",
        "status": "PASS",
        "isolation": {
            "network_namespace": "PRIVATE_UNSHARE_NET",
            "mount_namespace": "PRIVATE_UNSHARE_MOUNT",
            "user_namespace": "PRIVATE_MAPPED_ROOT",
            "filesystem": "CHROOT_WITH_READ_ONLY_RUNTIME_AND_CANDIDATE",
            "wider_repository_mounted": False,
        },
        "families": [{
            "family_id": row["family_id"],
            "status": row["status"],
            "worker_status": row["worker_result"]["worker_status"],
            "existing": row["worker_result"]["existing"]["status"],
            "feature": row["worker_result"]["feature"]["status"],
            "invariant": row["worker_result"]["invariant"]["status"],
            "intended_failure_condition": row["worker_result"]["invariant"].get("condition"),
        } for row in isolated["families"]],
        "pass_count": 26,
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_human_reviews": 0,
    }
    return tuple(_write(name, document) for name, document in (
        ("reference_matrix_results.json", reference_document),
        ("coverage_audit_results.json", coverage_document),
        ("candidate_oracle_results.json", candidate_document),
        ("validator_isolation_results.json", isolated_document),
    ))


if __name__ == "__main__":
    for output in build():
        print(output)
