#!/usr/bin/env python3
"""Read-only checks for prospective specifications and human admission evidence.

This verifies recorded evidence, not human identity, semantic truth or execution
of the separately frozen machine validator. It launches no constructor or agent.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.verify_synthetic_human_resolution import (  # noqa: E402
    EXPECTED_RESOLUTION_SHA256,
    PERMANENTLY_RETAINED,
    verify_resolution,
)

EXPANSION = REPO_ROOT / "synthetic_triplets/controlled_v3_expansion"
EXPECTED_FREEZE_SHA256 = "a2b6eaf731012feffeb03e5f2024d7fd7cc875f2d7d0f56846761f65c2dcb2dc"
GATES = tuple(str(i) for i in range(1, 10))
PRE_GATES = tuple(f"G{i:02d}" for i in range(1, 13))
INPUT_ROLES = {"source", "memory", "public", "sealed", "validator", "prompt", "environment"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory_digest(inventory: dict[str, str]) -> str:
    return hashlib.sha256(
        json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def read_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"expected JSON object: {path}")
    return value


def utc(value: str) -> datetime:
    require(isinstance(value, str) and value.endswith("Z"), "timestamp must use UTC Z")
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def inside(root: Path, relative: str) -> Path:
    require(isinstance(relative, str) and bool(relative), "missing evidence path")
    rel = Path(relative)
    require(not rel.is_absolute() and ".." not in rel.parts, "evidence path escapes repository")
    path = (root / rel).resolve()
    require(path.is_relative_to(root.resolve()), "evidence path escapes repository")
    require(path.is_file(), f"missing evidence: {relative}")
    return path


def check_inventory(root: Path, inventory: dict[str, str]) -> None:
    require(isinstance(inventory, dict), "inventory must be a path-to-digest object")
    for relative, digest in inventory.items():
        require(sha256(inside(root, relative)) == digest, f"evidence digest changed: {relative}")


def reference(root: Path, ref: dict[str, str], *, parse: bool = True) -> Any:
    require(isinstance(ref, dict) and set(ref) == {"path", "sha256"}, "invalid file reference")
    path = inside(root, ref["path"])
    require(sha256(path) == ref["sha256"], f"evidence digest changed: {ref['path']}")
    return read_object(path) if parse else None


def gate_vector(record: dict[str, Any], keys: tuple[str, ...]) -> list[bool]:
    gates = record.get("gates", {})
    require(set(gates) == set(keys), "incomplete gate record")
    for key in keys:
        require(type(gates[key].get("passed")) is bool, f"gate {key} is not a decision")
        require(isinstance(gates[key].get("evidence"), str) and bool(gates[key]["evidence"].strip()),
                f"gate {key} lacks evidence")
    require(bool(record.get("attestation")), "missing signed human/design-owner attestation")
    return [gates[key]["passed"] for key in keys]


def verify_specs(protocol: dict[str, Any], specs: list[dict[str, Any]]) -> None:
    order = [f"X{i:02d}" for i in range(1, 29)]
    require(protocol["new_family_order"] == order, "frozen order changed")
    require(protocol["retained_family_ids"] == list(PERMANENTLY_RETAINED), "retained six changed")
    require(protocol["additional_required"] == 14 and protocol["final_cohort_size"] == 20,
            "cohort threshold changed")
    require(protocol["constructor_attempt_limit_per_specification"] == 4, "attempt cap changed")
    require(set(protocol["human_gates"]) == set(GATES), "nine-gate contract changed")
    require(set(protocol["hard_pre_generation_rules"]) == set(PRE_GATES), "pre-generation rules changed")
    require([spec["family_id"] for spec in specs] == order, "specification order changed")
    pairs = set()
    for index, spec in enumerate(specs, 1):
        require(spec["frozen_order"] == index and spec["constructor_attempt_limit"] == 4,
                "specification order/cap changed")
        for field in ("source_procedure", "source_valid_assumption", "target_change",
                      "requested_feature", "unsafe_reuse", "secure_adaptation", "distinctness_rationale"):
            require(isinstance(spec.get(field), str) and bool(spec[field].strip()), f"missing {field}")
        matrix = spec["trust_matrix"]
        require(len(matrix) >= 4, "missing fixed trust dimensions")
        require(sum(row["source"] != row["target"] for row in matrix) == 1,
                "exactly one security-relevant assumption may change")
        require(len(spec["full_target_security_obligations"]) >= 3, "incomplete full-condition contract")
        require(len(spec["public_contract_plan"]) >= 2, "missing public information boundary")
        pair = (spec["unsafe_reuse"], spec["secure_adaptation"])
        require(pair not in pairs, "exact duplicate unsafe/secure pair")
        pairs.add(pair)


def construction_release(root: Path, ref: dict[str, str], protocol: dict[str, Any],
                         freeze_digest: str, frozen_at: datetime) -> tuple[dict[str, Any], dict[str, bool]]:
    release = reference(root, ref)
    require(release.get("schema_version") == "construction-input-release/1", "release schema mismatch")
    require(release.get("freeze_sha256") == freeze_digest, "release is not bound to specification freeze")
    require(release.get("no_evaluated_outcomes") is True and bool(release.get("owner_attestation")),
            "missing pre-outcome release attestation")
    require(utc(release["frozen_at_utc"]) >= frozen_at, "construction release predates specifications")
    constructor = release["constructor"]
    require(bool(constructor.get("model")) and bool(constructor.get("version")), "constructor version not locked")
    for key, value in protocol["constructor_controls"].items():
        require(constructor.get(key) == value, f"constructor control changed: {key}")
    inventory = release["inventory"]
    require(bool(inventory), "empty construction release")
    check_inventory(root, inventory)
    packages = release["packages"]
    require([row["family_id"] for row in packages] == protocol["new_family_order"],
            "all 28 input packages must be frozen before construction")
    audits = {}
    for package in packages:
        require(set(package["inputs"]) == INPUT_ROLES, "incomplete fixed input roles")
        for paths in package["inputs"].values():
            require(isinstance(paths, list) and bool(paths) and all(p in inventory for p in paths),
                    "unbound source/public/sealed input")
        visible = set().union(*(package["inputs"][role] for role in ("source", "memory", "public")))
        private = set(package["inputs"]["sealed"]) | set(package["inputs"]["validator"]) | {package["audit_path"]}
        require(visible.isdisjoint(private), "sealed evidence included in evaluated-agent input inventory")
        require(package["audit_path"] in inventory, "pre-generation audit not frozen")
        audit = read_object(inside(root, package["audit_path"]))
        require(audit.get("family_id") == package["family_id"], "audit family mismatch")
        require(audit.get("reviewer_type") in {"human", "design_owner"}, "AI is not a pre-generation sign-off")
        require(bool(audit.get("reviewer_id")) and audit.get("outcome_blind") is True,
                "pre-generation audit identity/blinding missing")
        require(frozen_at <= utc(audit["submitted_at_utc"]) <= utc(release["frozen_at_utc"]),
                "pre-generation audit must follow specs and precede construction release")
        audits[package["family_id"]] = all(gate_vector(audit, PRE_GATES))
    return release, audits


def review_decision(root: Path, refs: list[dict[str, str]], candidate: str,
                    release_digest: str, retained: list[str], earliest: datetime) -> tuple[str, datetime]:
    require(len(refs) <= 3, "too many reviewers")
    reviews = [reference(root, ref) for ref in refs]
    roles = [r.get("role") for r in reviews]
    require(len(set(roles)) == len(roles), "duplicate review role")
    require(set(roles) <= {"primary_1", "primary_2", "adjudicator"}, "invalid review role")
    require(len({r.get("reviewer_id") for r in reviews}) == len(reviews), "reviewers must be distinct humans")
    vectors = {}
    times = {}
    for review in reviews:
        role = review["role"]
        require(review.get("reviewer_type") == "human" and bool(review.get("reviewer_id")),
                "AI or unidentified reviewer cannot satisfy human admission")
        require(review.get("candidate_sha256") == candidate, "review candidate binding changed")
        require(review.get("input_release_sha256") == release_digest, "review input binding changed")
        require(review.get("outcome_blind") is True, "review is not outcome blind")
        require(review.get("signature_form") == "NON_CRYPTOGRAPHIC_HUMAN_ATTESTATION",
                "missing human signature form")
        require(review.get("compared_retained_family_ids") == retained, "incomplete semantic duplicate comparison")
        if role.startswith("primary"):
            require(review.get("other_primary_review_seen_before_submission") is False,
                    "primary reviews must be independently sealed")
            require(not review.get("disagreement_resolution"), "primary cannot adjudicate")
        vectors[role] = gate_vector(review, GATES)
        times[role] = utc(review["submitted_at_utc"])
        require(times[role] >= earliest, "review predates candidate completion")
    latest = max([earliest, *times.values()])
    if not {"primary_1", "primary_2"} <= set(roles):
        require("adjudicator" not in roles, "third reviewer before both primaries")
        return "HUMAN_REVIEW_PENDING", latest
    disagreements = [key for key, a, b in zip(GATES, vectors["primary_1"], vectors["primary_2"]) if a != b]
    if not disagreements:
        require("adjudicator" not in roles, "third reviewer without disagreement")
    elif "adjudicator" not in roles:
        return "ADJUDICATION_PENDING", latest
    else:
        adjudicator = next(r for r in reviews if r["role"] == "adjudicator")
        resolved = adjudicator.get("disagreement_resolution", {})
        require(set(resolved) == set(disagreements) and all(isinstance(v, str) and v.strip() for v in resolved.values()),
                "adjudicator must explain every disputed gate")
        require(times["adjudicator"] >= max(times["primary_1"], times["primary_2"]),
                "adjudication predates both primary submissions")
    complete_passes = sum(all(vector) for vector in vectors.values())
    if complete_passes >= 2:
        return "ADMITTED", latest
    return ("ADJUDICATED_REJECTED" if disagreements else "PRIMARY_REJECTED"), latest


def assess_ledger(root: Path, protocol: dict[str, Any], ledger: dict[str, Any],
                  freeze_digest: str, frozen_at: datetime,
                  historical_candidate_digests: tuple[str, ...] = ()) -> dict[str, Any]:
    require(ledger.get("schema_version") == "controlled-synthetic-expansion-ledger/1", "ledger schema mismatch")
    require(ledger.get("freeze_sha256") == freeze_digest, "ledger freeze binding changed")
    require(ledger.get("evaluated_agent_outcomes_observed") is False, "prospective outcome-blind boundary violated")
    require(ledger.get("agent_experiment_frozen") is False, "this ledger cannot freeze an agent experiment")
    rows = ledger["families"]
    require(isinstance(rows, list) and len(rows) <= 28, "invalid family record count")
    retained = list(protocol["retained_family_ids"])
    admitted = []
    dispositions = []
    totals = {"SPEC_AUDIT_REJECTED": 0, "MACHINE_EXHAUSTED": 0,
              "PRIMARY_REJECTED": 0, "ADJUDICATED_REJECTED": 0, "ADMITTED": 0}
    pending = None
    release_ref = ledger.get("construction_release")
    if release_ref is None:
        require(not rows, "construction before fixed input release")
        return {"status": "SPECIFICATIONS_FROZEN_CONSTRUCTION_RELEASE_PENDING", "retained": retained,
                "additional_admitted": [], "final_count": 6, "experiment_freeze_eligible": False,
                "evaluated_agent_runs_authorized": False, "attempt_count": 0, "machine_valid_count": 0,
                "attrition": totals, "next_family": "X01"}
    release, audits = construction_release(root, release_ref, protocol, freeze_digest, frozen_at)
    previous = utc(release["frozen_at_utc"])
    attempts_total = machine_valid_count = 0
    candidate_digests = set(historical_candidate_digests)
    for index, row in enumerate(rows):
        require(len(admitted) < 14, "work recorded after immediate cohort stop")
        require(pending is None, "later family processed before prior disposition")
        family = row["family_id"]
        require(family == protocol["new_family_order"][index], "family skipped or reordered")
        attempts = row["attempts"]
        refs = row["reviews"]
        require(isinstance(attempts, list) and len(attempts) <= 4, "constructor attempt limit exceeded")
        candidate = content_digest = None
        if not audits[family]:
            require(not attempts and not refs, "construction/review after pre-generation rejection")
            disposition = "SPEC_AUDIT_REJECTED"
        else:
            for number, attempt in enumerate(attempts, 1):
                require(candidate is None, "attempt after first machine-valid candidate")
                require(attempt["number"] == number, "non-contiguous constructor attempts")
                require(attempt.get("input_release_sha256") == release_ref["sha256"], "attempt input binding changed")
                require(attempt.get("constructor") == release["constructor"], "constructor model/control drift")
                started, completed = utc(attempt["started_at_utc"]), utc(attempt["completed_at_utc"])
                require(started >= previous and completed >= started, "attempt chronology violates frozen serial order")
                previous = completed
                artifacts = attempt["artifacts"]
                check_inventory(root, artifacts)
                digest = inventory_digest(artifacts)
                reference(root, attempt["trace"], parse=False)
                report = reference(root, attempt["machine_report"])
                require(report.get("family_id") == family and report.get("attempt_number") == number,
                        "machine report family/attempt binding changed")
                require(report.get("candidate_sha256") == digest, "machine report candidate binding changed")
                require(report.get("input_release_sha256") == release_ref["sha256"], "machine report input binding changed")
                checks = report["checks"]
                require(set(checks) == set(protocol["mandatory_machine_checks"]), "incomplete machine check matrix")
                require(all(type(value) is bool for value in checks.values()), "machine checks must be booleans")
                require(type(report.get("machine_valid")) is bool and report["machine_valid"] == all(checks.values()),
                        "machine validity contradicts check matrix")
                attempts_total += 1
                if report["machine_valid"]:
                    paths = [Path(p) for p in artifacts]
                    bases = {p.parents[2] if p.as_posix().endswith("/B/app/service.py") else p.parent for p in paths}
                    require(len(bases) == 1, "candidate artifacts have different roots")
                    base = next(iter(bases))
                    require({p.relative_to(base).as_posix() for p in paths} ==
                            {"B/app/service.py", "feature.patch", "security.patch"}, "invalid constructor payload")
                    content_digest = inventory_digest({p.relative_to(base).as_posix(): artifacts[str(p)] for p in paths})
                    candidate = digest
                    machine_valid_count += 1
            if candidate is None:
                require(not refs, "human reviews without machine-valid candidate")
                disposition = "MACHINE_EXHAUSTED" if len(attempts) == 4 else "CONSTRUCTION_PENDING"
            else:
                disposition, previous = review_decision(root, refs, candidate, release_ref["sha256"], retained, previous)
        dispositions.append({"family_id": family, "disposition": disposition})
        if disposition in totals:
            totals[disposition] += 1
        else:
            pending = disposition
        if disposition == "ADMITTED":
            require(content_digest not in candidate_digests, "exact duplicate retained candidate content")
            candidate_digests.add(content_digest)
            admitted.append(family)
            retained.append(family)
    complete = len(admitted) == 14
    exhausted = len(rows) == 28 and pending is None and not complete
    status = ("COHORT_COMPLETE_EXPERIMENT_FREEZE_ELIGIBLE" if complete else
              "COHORT_INCOMPLETE_POOL_EXHAUSTED" if exhausted else pending or "CONSTRUCTION_PENDING")
    return {"status": status, "retained": retained, "additional_admitted": admitted,
            "final_count": len(retained), "experiment_freeze_eligible": complete,
            "evaluated_agent_runs_authorized": False, "attempt_count": attempts_total,
            "machine_valid_count": machine_valid_count, "attrition": totals, "dispositions": dispositions,
            "unused_after_stop": protocol["new_family_order"][len(rows):] if complete else [],
            "next_family": None if complete or exhausted else
            (rows[-1]["family_id"] if pending else protocol["new_family_order"][len(rows)])}


def verify(ledger_path: Path | None = None) -> dict[str, Any]:
    freeze_path = EXPANSION / "freeze_manifest.json"
    require(sha256(freeze_path) == EXPECTED_FREEZE_SHA256, "specification freeze digest changed")
    freeze = read_object(freeze_path)
    require(freeze["historical_resolution_sha256"] == EXPECTED_RESOLUTION_SHA256, "historical resolution anchor changed")
    verify_resolution()
    check_inventory(REPO_ROOT, freeze["frozen_inventory"])
    check_inventory(REPO_ROOT, freeze["historical_inventory"])
    protocol = read_object(EXPANSION / "protocol.json")
    specs = read_object(EXPANSION / "family_specs.json")["specifications"]
    verify_specs(protocol, specs)
    ledger = read_object(ledger_path or EXPANSION / "admission_ledger.json")
    historical = read_object(REPO_ROOT / "synthetic_triplets/controlled_v2_final/cohort_manifest.json")
    historical_digests = []
    for row in historical["families"]:
        if row["family_id"] in PERMANENTLY_RETAINED:
            historical_digests.append(inventory_digest({
                "B/app/service.py": row["candidate_sha256"]["B"],
                "feature.patch": row["candidate_sha256"]["feature_patch"],
                "security.patch": row["candidate_sha256"]["security_patch"],
            }))
    result = assess_ledger(REPO_ROOT, protocol, ledger, EXPECTED_FREEZE_SHA256,
                           utc(freeze["frozen_at_utc"]), tuple(historical_digests))
    result.update({"specification_count": len(specs), "freeze_sha256": EXPECTED_FREEZE_SHA256,
                   "historical_files_verified": len(freeze["historical_inventory"]),
                   "historical_resolution_sha256": EXPECTED_RESOLUTION_SHA256})
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", required=True)
    parser.add_argument("--ledger", type=Path)
    parser.add_argument("--require-experiment-ready", action="store_true")
    args = parser.parse_args(argv)
    try:
        result = verify(args.ledger)
    except (ValueError, KeyError, TypeError, IndexError, OSError) as error:
        print(f"INVALID: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 2 if args.require_experiment_ready and not result["experiment_freeze_eligible"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
