"""Provenance regressions, not X-family behavioral-oracle or human gate tests."""

from __future__ import annotations

import json
from pathlib import Path
import shutil

import pytest

from scripts.verify_v3_x02_x22_clarification import (
    LEDGER, PROTOCOL, RELATIVE, ROOT, SPEC, digest, inspect, main,
)


def isolated_copy(destination: Path) -> None:
    manifest = json.loads((ROOT / RELATIVE / "manifest.json").read_text())
    baseline = json.loads((ROOT / RELATIVE / "preserved_file_inventory.json").read_text())
    paths = set(manifest["inventory"]) | set(baseline["inventory"]) | {str(RELATIVE / "manifest.json")}
    for relative in paths:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)


def test_amendment_integrity_is_not_behavioral_readiness():
    result = inspect()
    assert result["preserved_files_verified"] == 572
    assert result["original_28_specifications_byte_identical"] is True
    assert result["other_26_specifications_amended"] is False
    assert result["reference_matrices_established_by_this_check"] == 0
    assert result["human_reviews_performed_by_this_check"] == 0
    assert result["construction_authorized"] is False
    assert result["behavioral_validator_complete"] is False
    assert main([]) == 0


@pytest.mark.parametrize("relative", [SPEC, PROTOCOL, LEDGER,
    "synthetic_triplets/controlled_v2_final/human_review_resolution.json",
    "synthetic_triplets/controlled_v3_corrected_input_release_v1/families/X01/public_tests.py",
    "synthetic_triplets/controlled_v3_expansion/inputs/X22/pre_generation_audit.json",
    str(RELATIVE / "X02.md"), str(RELATIVE / "X02-machine.md"), str(RELATIVE / "X22.md"),
])
def test_tampering_is_rejected_only_in_an_isolated_copy(tmp_path, relative):
    isolated_copy(tmp_path)
    path = tmp_path / relative
    path.write_bytes(path.read_bytes() + b"\nchanged isolated copy\n")
    with pytest.raises(ValueError, match="content changed"):
        inspect(tmp_path)


def test_external_manifest_digest_rejects_self_rehashed_claims(tmp_path):
    isolated_copy(tmp_path)
    path = tmp_path / RELATIVE / "manifest.json"
    expected = digest(path)
    payload = json.loads(path.read_text())
    payload["construction_authorized"] = True
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match="manifest digest changed"):
        inspect(tmp_path, expected)
    with pytest.raises(ValueError, match="construction must remain blocked"):
        inspect(tmp_path)


def test_unspecified_status_is_recorded_without_fake_review():
    search = json.loads((ROOT / RELATIVE / "authority_search.json").read_text())
    assert [row["family_id"] for row in search["findings"]] == ["X02", "X22"]
    assert all(row["pre_amendment_classification"] == "PRE_CONSTRUCTION_SPECIFICATION_UNDERSPECIFIED"
               and row["authoritative_contract_found"] is False for row in search["findings"])
    notice = json.loads((ROOT / RELATIVE / "supersession_notice.json").read_text())
    assert notice["invalid_prior_attestations"]["status"] == "INVALID — NO HUMAN REVIEW OCCURRED"
    assert notice["invalid_prior_attestations"]["replacement_human_attestations_created"] == 0
