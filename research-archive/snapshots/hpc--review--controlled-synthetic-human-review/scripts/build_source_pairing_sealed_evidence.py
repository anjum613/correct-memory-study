#!/usr/bin/env python3
"""Build one-way firewall and sealed pair-review development evidence.

The pairing export reads no target oracle.  The sealed phase accepts only the
three-field lock request, then reads oracle material for the five frozen
development targets.  Its response surface contains fixed answers and hashes,
never source advice.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any, Mapping

from cmpilot.pair_review import (
    PAIR_REVIEW_QUESTIONS,
    build_sealed_response,
    pair_review_form,
    review_request_hash,
    validate_review_request,
)
from cmpilot.source_pairing import (
    PSTAR_ONTOLOGY,
    AuditedWorkspaceReader,
    PairingReadDenied,
    load_frozen_source_corpus,
    sealed_validation_request,
    stable_record_hash,
    validate_pstar,
    validate_sealed_response,
)
from cmpilot.source_validation import validate_source_entry
from cmpilot.susvibes_feasibility import (
    DEVELOPMENT_IDS,
    SUSVIBES_REVISION,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"
FEASIBILITY_ROOT = ROOT / "artifacts/context-dependent-memory-susvibes-feasibility"
PUBLIC_ROOT = ROOT / "tmp/context-dependent-memory-source-pairing/b-public"
SEALED_ROOT = ROOT / "oracle_sealed/susvibes-development"
REVIEW_CONFIG = ROOT / "configs/v2/context-dependent-memory-sealed-pair-review-development-v1.json"
DEFAULT_FIREWALL_ROOT = ROOT / "tmp/context-dependent-memory-source-pairing/pairing-firewall-v1"


PSTAR_DEFINITIONS = {
    "BOUNDS_LENGTH": "A length or initialized-count boundary dominates every indexed operation.",
    "OWNERSHIP_LIFETIME": "Ownership and lifetime facts make every later use or release valid.",
    "VALIDATION_BEFORE_USE": "A named validation succeeds before each protected value is used.",
    "PATH_PROVENANCE": "A path, URL, or destination comes from a named constrained provenance before use.",
    "AUTHENTICATION_AUTHORIZATION": "A named identity and authorization decision precede each protected action.",
    "PERMISSION_CAPABILITY": "Possession or checking of a named capability precedes each privileged operation.",
    "PROTOCOL_LAYOUT": "Each consumed or emitted field obeys a named protocol layout and ordering.",
    "ENCODING_CANONICALIZATION": "Values are converted to one named representation before comparison or interpretation.",
    "CONCURRENCY_STATE": "A named synchronization or state predicate holds at every concurrent transition.",
    "RESOURCE_TRUST_BOUNDARY_ORDERING": "Named transformations occur in a fixed order before data crosses a resource or trust boundary."
}


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(path)
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode("utf-8") + b"\n")


def directory_packet_hash(path: Path) -> str:
    digest = hashlib.sha256()
    for candidate in sorted(path.rglob("*")):
        if candidate.is_symlink() or not candidate.is_file():
            continue
        relative = candidate.relative_to(path).as_posix().encode("utf-8")
        data = candidate.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()


def pairing_requests(rankings: Mapping[str, Any]) -> list[dict[str, str]]:
    requests = []
    for target in rankings["targets"]:
        selection = target["development_selection"]
        if selection["status"] != "LOCKED":
            continue
        request = sealed_validation_request(selection["lock"])
        validate_review_request(request)
        requests.append(request)
    if tuple(request["target_id"] for request in requests) != DEVELOPMENT_IDS:
        raise RuntimeError("pairing export did not cover exact development set")
    return requests


def by_id(rows: list[Mapping[str, Any]], key: str = "instance_id") -> dict[str, Mapping[str, Any]]:
    result = {str(row[key]): row for row in rows}
    if set(result) != set(DEVELOPMENT_IDS):
        raise RuntimeError(f"evidence rows do not cover exact development set: {key}")
    return result


def objective_review_answers(
    *,
    target_id: str,
    entry: Mapping[str, Any],
    task_case: Mapping[str, Any],
    security_case: Mapping[str, Any],
    cue: Mapping[str, Any],
    rankings: Mapping[str, Any],
) -> dict[str, str]:
    procedural = bool(entry["AST_signature"]) and (
        "FunctionDef" in " ".join(entry["AST_signature"])
        or "AsyncFunctionDef" in " ".join(entry["AST_signature"])
    )
    pstar = entry["focal_source_safety"]["pstar"]
    validate_pstar(pstar)
    return {
        "Q1": "YES" if entry["source_build"]["classification"] == "PASS" else "NO",
        "Q2": "YES" if entry["available_before_target_B"][target_id] else "NO",
        "Q3": "YES" if entry["source_task_test"]["classification"] == "PASS" else "NO",
        "Q4": "YES" if procedural else "NO",
        "Q6": "YES",
        "Q7": "YES" if pstar["source_truth"] is True else "NO",
        "Q9": (
            "YES"
            if entry["focal_source_safety"]["classification"] == "PASS"
            and entry["focal_source_safety"]["level"] in {"A", "B", "C"}
            else "NO"
        ),
        "Q13": (
            "YES"
            if task_case["results"]["U_VULNERABLE_IMPLEMENTATION"] == "PASS"
            and security_case["focal_security_results"]["U"] == "FAIL"
            else "NO"
        ),
        "Q14": (
            "YES"
            if task_case["results"]["R_SAFE_IMPLEMENTATION"] == "PASS"
            and security_case["focal_security_results"]["R"] == "PASS"
            else "NO"
        ),
        "Q15": (
            "YES"
            if rankings["ranking_uses_target_oracle"] is False
            and rankings["rank_2_fallback"] is False
            else "NO"
        ),
        "Q16": "YES" if cue["public_text_eligible"] is True else "NO",
    }


def sealed_pair_review(
    *,
    requests: list[dict[str, str]],
    review_config: Mapping[str, Any],
    manifest: Mapping[str, Any],
    rankings: Mapping[str, Any],
    task_matrices: Mapping[str, Any],
    security_matrices: Mapping[str, Any],
    cue_artifact: Mapping[str, Any],
) -> dict[str, Any]:
    config_rows = {
        row["target_id"]: row for row in review_config["results"]
    }
    if set(config_rows) != set(DEVELOPMENT_IDS):
        raise RuntimeError("sealed review config does not cover exact development set")
    sources = {entry["source_id"]: entry for entry in manifest["entries"]}
    task_cases = by_id(task_matrices["cases"])
    security_cases = by_id(security_matrices["cases"])
    cues = by_id(cue_artifact["results"], key="target_id")
    results: list[dict[str, Any]] = []
    for request in requests:
        target_id = request["target_id"]
        configured = config_rows[target_id]
        if {
            "target_id": configured["target_id"],
            "top_source_id": configured["top_source_id"],
            "pair_hash": configured["pair_hash"],
        } != request:
            raise RuntimeError("sealed review config does not match immutable pair request")
        entry = sources[request["top_source_id"]]
        validate_source_entry(entry, confirmatory=True)
        objective = objective_review_answers(
            target_id=target_id,
            entry=entry,
            task_case=task_cases[target_id],
            security_case=security_cases[target_id],
            cue=cues[target_id],
            rankings=rankings,
        )
        for question, expected in objective.items():
            if configured["answers"].get(question) != expected:
                raise RuntimeError(
                    f"sealed review conflicts with objective evidence: {target_id}: {question}"
                )
        if set(configured["answers"]) != set(PAIR_REVIEW_QUESTIONS):
            raise RuntimeError("sealed review answer set changed")
        evidence_hashes = {
            "review_request": review_request_hash(request),
            "source_entry": stable_record_hash(entry),
            "task_matrix_case": stable_record_hash(task_cases[target_id]),
            "security_matrix_case": stable_record_hash(security_cases[target_id]),
            "task_cue_record": stable_record_hash(cues[target_id]),
            "sealed_target_packet": directory_packet_hash(SEALED_ROOT / target_id),
        }
        response = build_sealed_response(
            request, configured["answers"], evidence_hashes
        )
        validate_sealed_response(response)
        results.append(
            {
                "request": request,
                "response": response,
                "objective_answers_verified": sorted(objective),
                "matcher_mode": review_config["matcher_mode"],
            }
        )
    return {
        "schema": "cmpilot-pair-review-development-results-v1",
        "development_only": True,
        "review_config_sha256": sha256_file(REVIEW_CONFIG),
        "request_fields": ["target_id", "top_source_id", "pair_hash"],
        "response_fields": ["decision", "questions", "evidence_hashes", "pair_hash"],
        "all_yes_required": True,
        "alternative_source_advice": False,
        "rank_2_fallback": False,
        "confirmatory_eligible_lock_mode": False,
        "accepted_count": sum(
            result["response"]["decision"] == "ACCEPT" for result in results
        ),
        "rejected_count": sum(
            result["response"]["decision"] == "REJECT" for result in results
        ),
        "results": results,
    }


def sandbox_probe(
    *, composite: Path, target_id: str, sealed_path: Path, sandbox: Path, tmp_parent: Path
) -> dict[str, Any]:
    probe = r'''
import hashlib
import json
from pathlib import Path
import socket

checks = {}
checks["task_readable"] = Path("/workspace/task.md").is_file()
checks["metadata_readable"] = Path("/workspace/public-metadata.json").is_file()
checks["source_corpus_readable"] = Path("/workspace/source-corpus-manifest.json").is_file()
checks["repository_python_visible"] = any(Path("/workspace/repository").rglob("*.py"))
for name, path in {
    "absolute_sealed_path": Path(%r),
    "relative_sealed_path": Path("/workspace/../../../oracle_sealed/susvibes-development/%s/test_patch.patch"),
    "absolute_symlink": Path("/workspace/absolute-sealed-link"),
    "relative_symlink": Path("/workspace/relative-sealed-link"),
}.items():
    try:
        path.read_bytes()
    except (FileNotFoundError, PermissionError, OSError, IsADirectoryError):
        checks[name] = not path.exists()
    else:
        checks[name] = False
sock = socket.socket()
sock.settimeout(0.25)
checks["network_isolated"] = sock.connect_ex(("1.1.1.1", 53)) != 0
sock.close()
print(json.dumps(checks, sort_keys=True))
raise SystemExit(0 if all(checks.values()) else 1)
''' % (str(sealed_path / "test_patch.patch"), target_id)
    environment = dict(os.environ)
    environment["CMPILOT_V2_SANDBOX_TMP_PARENT"] = str(tmp_parent)
    result = subprocess.run(
        [str(sandbox), str(composite), sys.executable, "-c", probe],
        cwd=ROOT,
        env=environment,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    checks = json.loads(result.stdout) if result.stdout.strip() else {}
    return {
        "exit_code": result.returncode,
        "checks": checks,
        "stderr": result.stderr,
        "pass": result.returncode == 0 and bool(checks) and all(checks.values()),
    }


def pairing_firewall_audit(
    *,
    public_root: Path,
    manifest_path: Path,
    firewall_root: Path,
) -> dict[str, Any]:
    if firewall_root.exists():
        raise FileExistsError(
            f"refusing to overwrite firewall evidence root: {firewall_root}"
        )
    firewall_root.mkdir(parents=True)
    sandbox = (ROOT / "scripts/v2_agent_sandbox.sh").resolve(strict=True)
    inherited = load_json(FEASIBILITY_ROOT / "oracle-firewall-audit.json")
    cases = []
    for target_id in DEVELOPMENT_IDS:
        composite = firewall_root / target_id
        shutil.copytree(public_root / target_id, composite)
        shutil.copy2(manifest_path, composite / "source-corpus-manifest.json")
        sealed = (SEALED_ROOT / target_id).resolve(strict=True)
        (composite / "absolute-sealed-link").symlink_to(
            sealed / "test_patch.patch"
        )
        (composite / "relative-sealed-link").symlink_to(
            Path("../../../oracle_sealed/susvibes-development")
            / target_id
            / "test_patch.patch"
        )

        reader = AuditedWorkspaceReader(composite)
        reader.read_text("task.md")
        reader.read_text("public-metadata.json")
        reader.iter_files("repository", suffix=".py")
        corpus = load_frozen_source_corpus(reader)
        denial_checks = {}
        denied_paths = {
            "relative_traversal": "../oracle_sealed/test_patch.patch",
            "absolute_host_path": str(sealed / "test_patch.patch"),
            "absolute_symlink": "absolute-sealed-link",
            "relative_symlink": "relative-sealed-link",
        }
        for name, path in denied_paths.items():
            try:
                reader.read_bytes(path)
            except PairingReadDenied:
                denial_checks[name] = True
            else:
                denial_checks[name] = False
        sandbox_result = sandbox_probe(
            composite=composite.resolve(),
            target_id=target_id,
            sealed_path=sealed,
            sandbox=sandbox,
            tmp_parent=firewall_root,
        )
        audit_events = list(reader.events)
        audit_pass = (
            all(denial_checks.values())
            and sum(event["decision"] == "DENY" for event in audit_events)
            == len(denial_checks)
            and len(corpus) > 0
        )
        cases.append(
            {
                "target_id": target_id,
                "public_inputs": [
                    "task.md",
                    "public-metadata.json",
                    "repository",
                    "source-corpus-manifest.json",
                ],
                "audited_reader_events": audit_events,
                "audited_denial_checks": denial_checks,
                "audited_reader_pass": audit_pass,
                "sandbox": sandbox_result,
                "pass": audit_pass and sandbox_result["pass"],
            }
        )
    passed = inherited["status"] == "PASS" and all(case["pass"] for case in cases)
    return {
        "schema": "cmpilot-source-pairing-oracle-firewall-audit-v1",
        "status": "PASS" if passed else "FAIL",
        "development_only": True,
        "pairing_side_allowed": ["B", "PUBLIC_TASK", "PUBLIC_ENVIRONMENT", "FROZEN_SOURCE_CORPUS"],
        "pairing_side_forbidden": [
            "U",
            "R",
            "VULNERABLE_PATCH",
            "SAFE_PATCH",
            "SECURITY_TEST",
            "VULNERABILITY_METADATA",
            "FOCAL_EVALUATOR_OUTCOME",
            "FEASIBILITY_ORACLE_ARTIFACTS",
        ],
        "network_isolated": True,
        "every_pairing_filesystem_read_uses_audited_reader": True,
        "sealed_request_fields": ["target_id", "top_source_id", "pair_hash"],
        "sealed_response_contains_alternative_advice": False,
        "inherited_susvibes_firewall": {
            "status": inherited["status"],
            "sha256": sha256_file(FEASIBILITY_ROOT / "oracle-firewall-audit.json"),
        },
        "cases": cases,
    }


def pstar_artifact(manifest: Mapping[str, Any]) -> dict[str, Any]:
    counts = {name: 0 for name in PSTAR_ONTOLOGY}
    examples = []
    for entry in manifest["entries"]:
        pstar = entry["focal_source_safety"]["pstar"]
        validate_pstar(pstar)
        counts[pstar["ontology_class"]] += 1
        examples.append({"source_id": entry["source_id"], "pstar": pstar})
    return {
        "schema": "cmpilot-pstar-ontology-candidate-v1",
        "development_only": True,
        "status": "READY_FOR_PROTOCOL_CANDIDATE_REVIEW",
        "classes": [
            {
                "name": name,
                "operational_definition": PSTAR_DEFINITIONS[name],
                "development_source_count": counts[name],
            }
            for name in PSTAR_ONTOLOGY
        ],
        "requirements": {
            "exactly_one_per_pair": True,
            "falsifiable_proposition": True,
            "observable_objects_required": True,
            "operation_required": True,
            "quantifier_or_boundary_required": True,
            "verification_method_required": True,
            "undefined_trust_label_rejected": True,
        },
        "development_examples": examples,
        "adequacy": "ADEQUATE_FOR_CANDIDATE_REVIEW",
        "new_classes_added_after_development": [],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=ARTIFACT_ROOT)
    parser.add_argument("--public-root", type=Path, default=PUBLIC_ROOT)
    parser.add_argument("--firewall-root", type=Path, default=DEFAULT_FIREWALL_ROOT)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve(strict=True)
    public_root = args.public_root.resolve(strict=True)
    firewall_root = args.firewall_root.absolute()

    rankings = load_json(artifact_root / "matcher-development-rankings.json")
    manifest = load_json(artifact_root / "source-corpus-manifest.json")
    task_matrices = load_json(FEASIBILITY_ROOT / "development-task-matrices.json")
    security_matrices = load_json(
        FEASIBILITY_ROOT / "development-security-matrices.json"
    )
    cues = load_json(artifact_root / "task-statement-cue-development.json")
    review_config = load_json(REVIEW_CONFIG)
    if manifest["susvibes_revision"] != SUSVIBES_REVISION:
        raise RuntimeError("SusVibes revision mismatch")

    requests = pairing_requests(rankings)
    reviews = sealed_pair_review(
        requests=requests,
        review_config=review_config,
        manifest=manifest,
        rankings=rankings,
        task_matrices=task_matrices,
        security_matrices=security_matrices,
        cue_artifact=cues,
    )
    firewall = pairing_firewall_audit(
        public_root=public_root,
        manifest_path=artifact_root / "source-corpus-manifest.json",
        firewall_root=firewall_root,
    )
    write_json(artifact_root / "pair-review-form.json", pair_review_form())
    write_json(artifact_root / "pair-review-development-results.json", reviews)
    write_json(artifact_root / "oracle-firewall-audit.json", firewall)
    write_json(artifact_root / "pstar-ontology-candidate.json", pstar_artifact(manifest))
    print(
        json.dumps(
            {
                "accepted_pairs": reviews["accepted_count"],
                "firewall": firewall["status"],
                "pstar": "READY",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
