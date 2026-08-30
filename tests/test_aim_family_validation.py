from __future__ import annotations

from pathlib import Path

from scripts.validate_aim_family import validate


ROOT = Path(__file__).parents[1]


def test_provisional_aim_construction_passes_engineering_and_blocks_freeze() -> None:
    result = validate(ROOT / "families/aim-v1")

    assert result["engineering_validation_pass"] is True
    assert result["decision"] == "BLOCKED_PENDING_EXACT_SELECTION_PROVENANCE"
    assert result["final_family_freeze_permitted"] is False
    assert result["model_ready"] is False
    assert all(result["checks"].values())
    assert result["references"]["faithful_reuse"]["functional"]["passed"] is True
    assert result["references"]["faithful_reuse"]["security"]["passed"] is False
    assert result["references"]["safe_control"]["functional"]["passed"] is True
    assert result["references"]["safe_control"]["security"]["passed"] is True
