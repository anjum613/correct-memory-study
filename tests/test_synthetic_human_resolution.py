from __future__ import annotations

import json

import pytest

from scripts.verify_synthetic_human_resolution import (
    MACHINE_MANIFEST_PATH,
    PERMANENTLY_RETAINED,
    RESOLUTION_PATH,
    REVIEW_1_REJECTED,
    REVIEW_2_REJECTED,
    verify_resolution,
)


def test_frozen_human_review_resolution_is_exact_and_complete():
    result = verify_resolution()
    resolution = json.loads(RESOLUTION_PATH.read_text(encoding="utf-8"))

    assert result["status"] == "FROZEN_POST_HUMAN_REVIEW_COHORT_INCOMPLETE"
    assert tuple(result["permanently_retained"]) == PERMANENTLY_RETAINED
    assert result["permanently_rejected_count"] == 14
    assert len(REVIEW_1_REJECTED) == 8
    assert len(REVIEW_2_REJECTED) == 6
    assert resolution["resolution_approval"]["status"] == "SIGNED_BY_PROJECT_OWNER"
    assert resolution["resolution_approval"]["cryptographic_signature_supplied"] is False


def test_rejected_artifacts_remain_preserved_as_machine_accepted_history():
    resolution = json.loads(RESOLUTION_PATH.read_text(encoding="utf-8"))

    for row in resolution["rejected_families"]:
        artifact_root = RESOLUTION_PATH.parent / row["accepted_copy"]
        assert artifact_root.is_dir()
        assert (artifact_root / "B/app/service.py").is_file()
        assert (artifact_root / "feature.patch").is_file()
        assert (artifact_root / "security.patch").is_file()
        assert (artifact_root / "spec.json").is_file()
        assert (artifact_root / "provenance.json").is_file()


def test_resolution_rejects_a_changed_machine_manifest(tmp_path):
    changed_manifest = tmp_path / "cohort_manifest.json"
    changed_manifest.write_bytes(MACHINE_MANIFEST_PATH.read_bytes() + b"\n")

    with pytest.raises(ValueError, match="source machine-cohort manifest digest changed"):
        verify_resolution(machine_manifest_path=changed_manifest)
