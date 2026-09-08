"""Cumulative prospective exclusion checks, not human review."""

from scripts.verify_v3_x25_exclusion import verify


def test_x19_and_x25_are_zero_attempt_exclusions_with_preserved_evidence():
    result = verify()
    assert result["excluded"] == ["X19", "X25"]
    assert result["in_scope_family_count"] == 26
    assert result["x25_diagnostic_files_preserved"] == 6
    assert result["x19_blocked_snapshot_files_preserved"] == 20
    assert result["constructor_attempts"] == result["evaluated_agent_outcomes"] == result["actual_human_reviews"] == 0
    assert not result["construction_authorized"]
