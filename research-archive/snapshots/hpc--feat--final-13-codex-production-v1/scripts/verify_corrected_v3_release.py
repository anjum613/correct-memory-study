#!/usr/bin/env python3
"""Verify the corrected executable X01-X28 release without running candidates."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "synthetic_triplets/controlled_v3_corrected_input_release_v1"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    m = json.loads((RELEASE / "release_manifest.json").read_text())
    assert m["release_id"] == "controlled-synthetic-v3-corrected-input-release-v1"
    assert m["schema_version"] == "construction-input-release/2"
    assert m["family_order"] == [f"X{i:02d}" for i in range(1, 29)]
    assert m["constructor_attempt_limit"] == 4
    assert m["constructor_attempts"] == 0
    assert m["evaluated_agent_outcomes_observed"] is False
    assert m["human_review_files_created"] is False
    assert m["constructor"]["version"].startswith("UNSET_PENDING")
    assert len(m["inventory"]) == m["input_file_count"] == 227
    for rel, digest in m["inventory"].items():
        path = ROOT / rel
        assert path.is_file(), rel
        assert sha(path) == digest, rel
    for family in m["family_order"]:
        d = RELEASE / "families" / family
        assert all((d / name).is_file() for name in ("spec.json", "source_service.py", "target_scaffold.py", "public_tests.py", "sealed_tests.py", "validator.py", "README.md"))
        assert not list(d.glob("*human*review*"))
    notice = json.loads((RELEASE / "supersession_notice.json").read_text())
    assert notice["status"] == "NONEXECUTABLE_PLACEHOLDER / SUPERSEDED_BEFORE_CONSTRUCTION"
    assert notice["generated_project_owner_attestations"] == "INVALID — NO HUMAN REVIEW OCCURRED"
    assert notice["original_files_and_commits_unchanged"] is True
    print(json.dumps({"release_id":m["release_id"],"input_file_count":m["input_file_count"],"release_sha256":sha(RELEASE/"release_manifest.json"),"constructor_attempts":0,"evaluated_agent_outcomes":0,"human_review_files":0},indent=2))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
