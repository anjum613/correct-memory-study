"""Verify the cumulative X19/X25 exclusion provenance; never run construction."""

import hashlib
import json
from pathlib import Path

from scripts.verify_v3_x19_exclusion import verify as verify_x19

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = Path("protocols/controlled-synthetic-v3-x25-exclusion-v1")


def verify(root=ROOT):
    prior = verify_x19(root)
    amendment = json.loads((root / DIRECTORY / "amendment.json").read_text())
    order = [f"X{i:02d}" for i in range(1, 29)]
    assert amendment["newly_excluded_family"]["family_id"] == "X25"
    assert amendment["newly_excluded_family"]["classification"] == "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED"
    assert amendment["cumulative_permanently_preconstruction_excluded"] == ["X19", "X25"]
    assert amendment["original_family_order"] == order
    assert amendment["construction_family_order"] == [f for f in order if f not in ("X19", "X25")]
    assert amendment["pool_policy"]["remaining_in_scope_count"] == 26
    assert amendment["constructor_attempt_limit_per_in_scope_family"] == 4
    assert amendment["constructor_attempts"] == amendment["evaluated_agent_outcomes"] == amendment["actual_human_reviews"] == 0
    assert amendment["construction_authorized"] is False
    for relative, record in amendment["preservation"]["x25_diagnostic_snapshot"].items():
        path = root / relative
        assert path.is_file() and not path.is_symlink()
        assert path.stat().st_size == record["bytes"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]
    x25_spec = root / "synthetic_triplets/controlled_v3_expansion/inputs/X25/spec.json"
    assert hashlib.sha256(x25_spec.read_bytes()).hexdigest() == amendment["preservation"]["x25_original_specification_sha256"]
    evidence = json.loads((root / amendment["newly_excluded_family"]["evidence_path"]).read_text())
    assert evidence["frozen_invariant_verdict"] == "UNDETERMINED_MISSING_NORMATIVE_CONTRACT"
    assert evidence["constructor_attempts"] == evidence["evaluated_agent_outcomes"] == evidence["actual_V3_human_reviews"] == 0
    return {"status": "CUMULATIVE_EXCLUSION_INTEGRITY_PASS_NOT_CONSTRUCTION_AUTHORIZATION",
            "excluded": ["X19", "X25"], "in_scope_family_count": 26,
            "x25_diagnostic_files_preserved": len(amendment["preservation"]["x25_diagnostic_snapshot"]),
            "x19_blocked_snapshot_files_preserved": prior["blocked_snapshot_files_preserved"],
            "prior_files_verified": prior["prior_files_verified"],
            "constructor_attempts": 0, "evaluated_agent_outcomes": 0,
            "actual_human_reviews": 0, "construction_authorized": False}
