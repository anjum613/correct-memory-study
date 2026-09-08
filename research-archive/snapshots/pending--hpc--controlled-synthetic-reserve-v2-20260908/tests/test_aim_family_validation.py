from __future__ import annotations

from pathlib import Path

from scripts.validate_aim_family import validate


ROOT = Path(__file__).parents[1]


def test_frozen_aim_family_passes_cpu_admission() -> None:
    result = validate(ROOT / "families/aim-v1")

    assert result["cpu_admission_pass"] is True
    assert result["decision"] == "AIM_FAMILY_FROZEN_MODEL_READY"
    assert result["final_family_freeze_permitted"] is True
    assert result["model_ready"] is True
    assert all(result["checks"].values())
    assert result["references"]["faithful_reuse"]["functional"]["passed"] is True
    assert result["references"]["faithful_reuse"]["security"]["passed"] is False
    assert result["references"]["safe_control"]["functional"]["passed"] is True
    assert result["references"]["safe_control"]["security"]["passed"] is True
