#!/usr/bin/env python3
"""Materialize V2 B-only rankings before any new sealed pair review."""

from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from cmpilot.source_corpus_v2 import PROTOCOL_ID, SUCCESSOR_PROTOCOL_COMMIT
from cmpilot.source_pairing import stable_record_hash
from cmpilot.source_pairing_v2 import (
    GLOBAL_SIMILARITY_THRESHOLD_REQUIRED,
    matcher_design_record,
    select_top_source_v2,
    validate_locked_source_timestamp,
)
from cmpilot.susvibes_feasibility import DEVELOPMENT_IDS, sha256_file


ROOT = Path(__file__).resolve().parents[1]
V1_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing"
DEFAULT_ROOT = ROOT / "artifacts/context-dependent-memory-source-pairing-v2"
MATCHER_MODULE = ROOT / "src/cmpilot/source_pairing_v2.py"


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(path)
    return value


def write_json(path: Path, value: Any) -> None:
    if path.exists():
        raise FileExistsError(f"refusing to overwrite V2 evidence: {path}")
    path.write_bytes(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")


def matcher_import_audit() -> dict[str, Any]:
    tree = ast.parse(MATCHER_MODULE.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    forbidden = {
        "pathlib",
        "os",
        "subprocess",
        "socket",
        "requests",
        "urllib",
    }
    observed_forbidden = sorted(
        name for name in imports if name.split(".", 1)[0] in forbidden
    )
    if observed_forbidden:
        raise RuntimeError(f"pairing matcher gained I/O imports: {observed_forbidden}")
    return {
        "module": MATCHER_MODULE.relative_to(ROOT).as_posix(),
        "module_sha256": sha256_file(MATCHER_MODULE),
        "imports": sorted(imports),
        "forbidden_io_imports": observed_forbidden,
        "matcher_callable_inputs": [
            "B_ONLY_REPRESENTATION",
            "FROZEN_SOURCE_CORPUS",
            "COARSE_TARGET_B_DATE_UTC",
        ],
        "unseen_target_rows_read": 0,
        "unseen_u_r_security_artifacts_read": 0,
        "evaluated_model_outputs_read": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-root", type=Path, default=DEFAULT_ROOT)
    args = parser.parse_args()
    artifact_root = args.artifact_root.resolve(strict=True)

    manifest_path = artifact_root / "expanded-source-corpus-manifest.json"
    manifest = load_json(manifest_path)
    if manifest["successor_protocol_commit"] != SUCCESSOR_PROTOCOL_COMMIT:
        raise RuntimeError("expanded corpus is not bound to the frozen protocol")
    entries = manifest["entries"]
    representations = load_json(V1_ROOT / "b-only-representation-results.json")
    v1_rankings = load_json(V1_ROOT / "matcher-development-rankings.json")
    epochs = {
        row["target_id"]: int(row["target_timestamp_epoch"])
        for row in v1_rankings["targets"]
    }
    by_target = {
        row["target_id"]: row["representation"]
        for row in representations["results"]
    }
    if tuple(by_target) != DEVELOPMENT_IDS or set(epochs) != set(DEVELOPMENT_IDS):
        raise RuntimeError("development-only target set changed")

    design = matcher_design_record()
    design_artifact = {
        **design,
        "development_only": True,
        "source_corpus_manifest_sha256": sha256_file(manifest_path),
        "source_corpus_sha256": manifest["source_corpus_sha256"],
        "source_corpus_entries": len(entries),
        "target_side_inputs": ["B_ONLY_REPRESENTATION", "DATE_ONLY_METADATA"],
        "source_lock_precedes_pair_review": True,
        "evaluated_model_inference": False,
    }
    targets = []
    ambiguities = []
    for target_id in DEVELOPMENT_IDS:
        target = by_target[target_id]
        epoch = epochs[target_id]
        day = datetime.fromtimestamp(epoch, timezone.utc).date().isoformat()
        rankings, lock = select_top_source_v2(
            target, entries, target_b_date_utc=day
        )
        exact_timestamp = validate_locked_source_timestamp(
            lock, entries, target_b_timestamp_epoch=epoch
        )
        if exact_timestamp["status"] != "PASS":
            raise RuntimeError("locked development source failed sealed timestamp")
        eligible_count = sum(row["hard_gate_pass"] for row in rankings)
        targets.append(
            {
                "target_id": target_id,
                "target_b_date_utc": day,
                "target_b_timestamp_epoch": epoch,
                "target_commit_hash_exposed_to_pairing": False,
                "target_representation_sha256": stable_record_hash(target),
                "eligible_source_count": eligible_count,
                "full_rankings": rankings,
                "selection_lock": lock,
                "sealed_exact_timestamp_validation": exact_timestamp,
                "review_status": "LOCKED_AWAITING_INDEPENDENT_REVIEW",
            }
        )
        ambiguities.append(
            {
                "target_id": target_id,
                "top_source_id": lock["top_source_id"],
                "eligible_source_count": eligible_count,
                "decision": lock["ambiguity"],
                "accepted_for_lock": True,
            }
        )

    ranking_artifact = {
        "schema": "cmpilot-matcher-v2-development-rankings",
        "protocol_id": PROTOCOL_ID,
        "successor_protocol_commit": SUCCESSOR_PROTOCOL_COMMIT,
        "development_only": True,
        "source_corpus_sha256": manifest["source_corpus_sha256"],
        "source_corpus_entries": len(entries),
        "b_only": True,
        "global_similarity_threshold_required": False,
        "combined_or_weighted_score": None,
        "top_one": True,
        "rank_2_fallback": False,
        "source_selection_uses_target_oracle": False,
        "source_selection_uses_model_outcome": False,
        "targets": targets,
    }
    ambiguity_artifact = {
        "schema": "cmpilot-matcher-v2-ambiguity-policy",
        "protocol_id": PROTOCOL_ID,
        "policy": design["ambiguity_rule"],
        "numerical_margin": None,
        "hash_tiebreak_scope": "SCIENTIFICALLY_EQUIVALENT_EPISODES_ONLY",
        "substantively_different_exact_tie": "REJECT_TARGET",
        "results": ambiguities,
        "status": "PASS",
    }
    import_audit = matcher_import_audit()
    firewall = {
        "schema": "cmpilot-source-pairing-oracle-firewall-v2",
        "development_only": True,
        "pairing_side": import_audit,
        "inherited_v1_firewall_artifact_sha256": sha256_file(
            V1_ROOT / "oracle-firewall-audit.json"
        ),
        "new_review_not_started_when_locks_written": True,
        "unseen_screening_performed": False,
        "evaluated_model_inference": False,
        "status": "PASS",
    }
    if GLOBAL_SIMILARITY_THRESHOLD_REQUIRED:
        raise RuntimeError("global-threshold dependency returned")
    write_json(artifact_root / "matcher-v2-design.json", design_artifact)
    write_json(
        artifact_root / "matcher-v2-development-rankings.json", ranking_artifact
    )
    write_json(artifact_root / "ambiguity-policy.json", ambiguity_artifact)
    write_json(artifact_root / "oracle-firewall-v2.json", firewall)
    print(
        json.dumps(
            {
                "targets_locked": len(targets),
                "top_sources": [
                    row["selection_lock"]["top_source_id"] for row in targets
                ],
                "global_threshold_required": False,
                "ambiguity_policy": "PASS",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
