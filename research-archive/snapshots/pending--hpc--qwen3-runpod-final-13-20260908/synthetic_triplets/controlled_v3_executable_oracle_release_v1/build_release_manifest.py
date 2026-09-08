#!/usr/bin/env python3
"""Build the deterministic pre-construction manifest after verification."""

from __future__ import annotations

import json
from pathlib import Path

from .candidate_control import sha256_file
from .contracts import (CONSTRUCTOR_ATTEMPT_LIMIT, EXCLUDED, FAMILY_ORDER,
                        IN_SCOPE, RELEASE_ID)
from .integrity import (MANIFEST_RELATIVE, PROTECTED, content_digest,
                        hash_inventory, repository_root)


def build(root=None):
    root = repository_root() if root is None else Path(root)
    verification_path = root / "synthetic_triplets/controlled_v3_executable_oracle_release_v1/verification_results.json"
    verification = json.loads(verification_path.read_text())
    if verification["status"] != "ALL_PREFREEZE_VERIFICATION_PASS":
        raise ValueError("verification results are not complete")
    inventory = hash_inventory(root)
    manifest = {
        "schema_version": "controlled-synthetic-v3-executable-oracle-release/1",
        "release_id": RELEASE_ID,
        "status": "CONSTRUCTION_READY",
        "release_frozen_for_construction": True,
        "construction_authorized_only_after_release_commit": True,
        "family_order": list(FAMILY_ORDER),
        "in_scope": list(IN_SCOPE),
        "excluded": {family: "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED"
                     for family in EXCLUDED},
        "per_family_status": {family: ("PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED"
                                        if family in EXCLUDED else "REFERENCE_MATRIX_PASS")
                              for family in FAMILY_ORDER},
        "constructor_attempt_limit_per_family": CONSTRUCTOR_ATTEMPT_LIMIT,
        "process_all_in_scope_in_frozen_relative_order": True,
        "retain_every_complete_machine_and_human_admissible_family": True,
        "independent_dual_human_review_and_disagreement_only_adjudication_unchanged": True,
        "subjective_semantic_gates_automated": False,
        "protected_scientific_and_provenance_hashes": PROTECTED,
        "inventory": inventory,
        "exact_inventoried_file_count": len(inventory),
        "release_content_sha256": content_digest(inventory),
        "admission_ledger_sha256": sha256_file(
            root / "synthetic_triplets/controlled_v3_executable_oracle_release_v1/admission_ledger.json"),
        "verification_results": verification,
        "constructor_attempts": 0,
        "evaluated_agent_outcomes": 0,
        "actual_v3_human_reviews": 0,
        "actual_v3_human_review_files": 0,
        "manifest_hash_policy": "This manifest is excluded from its own inventory. Its SHA-256 and release commit are recorded in a post-commit receipt.",
    }
    path = root / MANIFEST_RELATIVE
    path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


if __name__ == "__main__":
    document = build()
    print(document["release_id"], document["exact_inventoried_file_count"],
          document["release_content_sha256"])
