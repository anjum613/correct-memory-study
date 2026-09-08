"""Verify prospective exclusion and preserved evidence; never authorize construction."""

import hashlib
import json
from pathlib import Path

from scripts.verify_v3_x02_x22_clarification import inspect as prior_inspect

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = "protocols/controlled-synthetic-v3-x19-exclusion-v1"


def verify(root=ROOT):
    prior = prior_inspect(root, "167251744b87c55f23ce06b61a70891c1192b7581c357a7d5458c22e0f94e1bc")
    amendment = json.loads((root / DIRECTORY / "amendment.json").read_text())
    assert list(amendment["excluded_families"]) == ["X19"]
    assert amendment["excluded_families"]["X19"]["classification"] == "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED"
    order = [f"X{i:02d}" for i in range(1, 29)]
    assert amendment["original_family_order"] == order
    assert amendment["construction_family_order"] == [f for f in order if f != "X19"]
    assert amendment["constructor_attempt_limit_per_in_scope_family"] == 4
    assert amendment["constructor_attempts"] == amendment["evaluated_agent_outcomes"] == amendment["actual_human_reviews"] == 0
    assert amendment["construction_authorized"] is False
    path = root / amendment["preservation"]["blocked_snapshot_inventory"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == "2f70831142ea25584714821e23be737385bb31ae1536ab2262f8c5c271f13b0b"
    snapshot = json.loads(path.read_text())
    for relative, record in snapshot["inventory"].items():
        artifact = root / relative
        assert artifact.is_file() and not artifact.is_symlink()
        assert hashlib.sha256(artifact.read_bytes()).hexdigest() == record["sha256"]
        assert artifact.stat().st_size == record["bytes"]
    historical = json.loads((root / amendment["excluded_families"]["X19"]["evidence_path"]).read_text())
    assert historical["reference_matrices"]["X19"]["states"]["S"]["invariant"]["status"] == "FAIL"
    return {"status": "EXCLUSION_INTEGRITY_PASS_NOT_CONSTRUCTION_AUTHORIZATION",
            "prior_files_verified": prior["preserved_files_verified"],
            "blocked_snapshot_files_preserved": len(snapshot["inventory"]) + 1,
            "in_scope_family_count": 27, "constructor_attempts": 0,
            "evaluated_agent_outcomes": 0, "actual_human_reviews": 0,
            "construction_authorized": False}
