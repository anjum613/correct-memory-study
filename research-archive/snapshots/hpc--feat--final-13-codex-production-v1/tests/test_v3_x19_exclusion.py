"""Prospective exclusion provenance, not human semantic review."""

from scripts.verify_v3_x19_exclusion import verify


def test_only_x19_is_excluded_and_frozen_evidence_is_unchanged():
    result = verify()
    assert result["in_scope_family_count"] == 27
    assert result["blocked_snapshot_files_preserved"] == 20
    assert result["prior_files_verified"] == 572
    assert not result["construction_authorized"]
