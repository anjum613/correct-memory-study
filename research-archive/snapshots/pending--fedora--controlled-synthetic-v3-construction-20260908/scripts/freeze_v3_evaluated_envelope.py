#!/usr/bin/env python3
"""Generate and inventory the information-flow contract; never construct or evaluate."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import v3_evaluated_envelope as e


def freeze(root: Path):
    science = e.verify_science(root)
    directory = root / e.DIRECTORY
    if (directory / "commit_receipt.json").exists():
        raise FileExistsError("refusing to regenerate a committed envelope contract")
    for relative, data in e.generate_contract(root).items():
        destination = directory / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    included = ["scripts/v3_evaluated_envelope.py", "scripts/freeze_v3_evaluated_envelope.py",
                "tests/test_v3_evaluated_envelope.py"]
    excluded = {"contract_manifest.json", "commit_receipt.json"}
    included += [str(path.relative_to(root)) for path in directory.rglob("*")
                 if path.is_file() and path.name not in excluded and "__pycache__" not in path.parts]
    inventory = {name: e.digest((root / name).read_bytes()) for name in sorted(included)}
    manifest = {
        "schema": "v3-evaluated-envelope-freeze/1", "contract_id": e.CONTRACT_ID,
        "scope": "INFORMATION_FLOW_CONTRACT_ONLY_NOT_FINAL_EXPERIMENT_FREEZE",
        "scientific_release_commit": e.RELEASE_COMMIT,
        "scientific_manifest_sha256": e.RELEASE_MANIFEST_SHA256,
        "scientific_inventory_count": len(science["inventory"]),
        "scientific_inputs_unchanged": True,
        "conditions": list(e.CONDITIONS), "in_scope": list(e.IN_SCOPE),
        "inventory": inventory, "exact_inventoried_file_count": len(inventory),
        "content_sha256": e.digest(e.canonical(inventory)),
        "evaluated_agents_authorized": False, "construction_authorized_by_this_contract": False,
        "constructor_attempts": 0, "evaluated_agent_outcomes": 0, "actual_v3_human_reviews": 0,
        "production_B_exports_created": 0,
        "reference_S_U_R_programs_exported": 0,
        "model_token_equalization": "DEFERRED_TO_FINAL_EXPERIMENT_BINDING_NOT_CLAIMED",
        "human_semantic_admission": "MANDATORY_NOT_AUTOMATED_NOT_PERFORMED",
    }
    (directory / "contract_manifest.json").write_bytes(e.canonical(manifest))
    return {"manifest_sha256": e.digest(e.canonical(manifest)),
            "content_sha256": manifest["content_sha256"], "files": len(inventory)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    print(e.canonical(freeze(args.root)).decode(), end="")
