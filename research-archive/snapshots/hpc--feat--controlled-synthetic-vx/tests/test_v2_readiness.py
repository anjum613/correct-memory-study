import json
from pathlib import Path

from scripts import v2_readiness as readiness


def test_issue_audit_has_exactly_24_exclusive_classifications() -> None:
    issues = readiness.issue_audit()
    allowed = {
        "ACTUAL_V1_DESIGN_DEFECT",
        "INTERPRETATION_LIMITATION",
        "TECHNICAL_INFRASTRUCTURE_DEFECT_ALREADY_FIXED",
        "NOT_A_DEFECT",
        "UNRESOLVED",
    }
    assert [row["number"] for row in issues] == list(range(1, 25))
    assert all(row["classification"] in allowed for row in issues)
    assert all(row["evidence"] and row["tests"] for row in issues)


def test_architecture_map_covers_required_system_components() -> None:
    components = readiness.architecture_map()
    assert len(components) >= 20
    assert any(row["component"] == "seed handling" for row in components)


def test_missing_full_suite_is_conservatively_blocked(tmp_path: Path) -> None:
    assert readiness._pytest_summary(tmp_path / "absent.xml")["status"] == "BLOCKED"


def test_historical_snapshot_defect_is_reproducible() -> None:
    result = readiness.historical_snapshot_audit()
    assert result["status"] == "FAIL"
    assert len(result["rows"]) == 9
    assert all(not row["clean_checkout_matches"] for row in result["rows"])
    assert all(row["historical_worktree_matches"] for row in result["rows"])


def test_disjoint_junit_summary_records_v2_passes() -> None:
    result = readiness.test_execution_summary(readiness.ARTIFACT)
    assert result["executed_disjoint"] == 879
    assert result["failures"] == 19
    assert result["v2_tests"] > 0
    assert result["v2_failures"] == 0
    assert result["latest_focused_v2"]["tests"] == 42
    assert result["latest_focused_v2"]["status"] == "PASS"


def test_readiness_hardware_recommendations_are_conservative() -> None:
    hardware = json.loads(
        (readiness.ARTIFACT / "hardware-estimates.json").read_text(encoding="utf-8")
    )
    qwen, devstral = hardware["models"]
    assert qwen["estimated_total_vram_gib"] < 94
    assert devstral["estimated_total_vram_gib"] < 80
