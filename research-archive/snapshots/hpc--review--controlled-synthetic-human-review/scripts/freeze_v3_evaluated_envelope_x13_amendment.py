"""Build this additive wording overlay and its exact inventory; never run agents."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import v3_evaluated_envelope as base
from scripts import v3_evaluated_envelope_x13_amendment as amendment


def freeze(root: Path) -> dict:
    directory = root / amendment.DIRECTORY
    if (directory / "commit_receipt.json").exists():
        raise FileExistsError("refusing to regenerate a committed wording amendment")
    parent = base.verify_contract(root, expected_manifest_sha256=amendment.BASE_MANIFEST_SHA256)
    ledger = json.loads((root / base.RELEASE / "admission_ledger.json").read_bytes())
    for key in ("constructor_attempts", "evaluated_agent_outcomes", "actual_human_reviews", "human_review_files"):
        if ledger[key] != 0:
            raise base.EnvelopeError("not a zero-outcome prospective amendment: " + key)
    if ledger["attempts"] or ledger["mutation_enabled"]:
        raise base.EnvelopeError("construction ledger is no longer inactive")
    for name, data in amendment.generated_overlay(root).items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    excluded = {"amendment_manifest.json", "commit_receipt.json"}
    names = list(amendment.CODE_FILES) + [p.relative_to(root).as_posix()
        for p in directory.rglob("*") if p.is_file() and p.name not in excluded]
    inventory = {name: base.digest((root / name).read_bytes()) for name in sorted(names)}
    manifest = {
        "schema": "v3-envelope-x13-wording-amendment-freeze/1",
        "amendment_id": amendment.AMENDMENT_ID,
        "base_contract_id": base.CONTRACT_ID,
        "base_contract_commit": amendment.BASE_COMMIT,
        "base_manifest_sha256": amendment.BASE_MANIFEST_SHA256,
        "base_content_sha256": amendment.BASE_CONTENT_SHA256,
        "base_inventoried_file_count": parent["exact_inventoried_file_count"],
        "scientific_manifest_sha256": base.RELEASE_MANIFEST_SHA256,
        "inventory": inventory,
        "exact_inventoried_file_count": len(inventory),
        "content_sha256": base.digest(base.canonical(inventory)),
        "changed_evaluator_bindings_only": amendment.expected_binding_changes(),
        "public_file_bytes_changed": 0,
        "memory_packet_bytes_changed": 0,
        "other_family_message_bytes_changed": 0,
        "ratings": "STATIC_PRE_OUTCOME_ADVISORY_NOT_ADMISSION_CRITERIA",
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
        "actual_v3_human_review_files": 0,
        "scope": "INFORMATION_FLOW_ONLY_NOT_EXPERIMENT_FREEZE",
        "construction_authorized": False,
        "evaluated_agent_execution_authorized": False,
    }
    raw = base.canonical(manifest)
    (directory / "amendment_manifest.json").write_bytes(raw)
    return {"manifest_sha256": base.digest(raw), "content_sha256": manifest["content_sha256"],
            "inventoried_files": len(inventory)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    print(base.canonical(freeze(parser.parse_args().root)).decode(), end="")
