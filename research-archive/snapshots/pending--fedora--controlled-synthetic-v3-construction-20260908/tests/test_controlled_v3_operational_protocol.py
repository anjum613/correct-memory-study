"""Static tests for the separately versioned V3 operational protocol."""

from __future__ import annotations

import json
from pathlib import Path

from scripts import prepare_controlled_v3_construction_v3 as preparation
from scripts import run_controlled_v3_pool_v3 as runner


def test_pilot_classification_is_complete_and_non_scientific_categories_are_explicit():
    pilot = json.loads(preparation.PILOT_PATH.read_text(encoding="utf-8"))
    assert pilot["completed_attempts"] == 40
    assert pilot["classification_counts"] == {
        "actual_matrix_level_scientific_failure": 1,
        "candidate_integrity_interface": 16,
        "constructor_refusal": 18,
        "infrastructure_tooling": 5,
    }
    assert sum(pilot["classification_counts"].values()) == 40
    assert all(
        row == {"attempts_used": 4, "status": "CONSTRUCTION_EXHAUSTED"}
        for row in pilot["family_summary"].values()
    )
    assert len(pilot["family_summary"]) == 10
    for category in (
        "infrastructure_tooling",
        "candidate_integrity_interface",
        "constructor_refusal",
    ):
        assert "not evidence" in pilot["interpretation"][category]


def test_runner_requests_only_two_neutral_functional_components():
    prompt = runner.render_prompt("X01", 1).decode("utf-8")
    assert "components/neutral_target/app/service.py" in prompt
    assert "components/functional_target/app/service.py" in prompt
    assert "Create exactly the two files" in prompt
    assert "insecure implementation" not in prompt.lower()
    assert "candidate/feature.patch" not in prompt
    assert "candidate/security.patch" not in prompt
    assert '"ceiling_risk_label_exposed": false' in prompt


def test_runner_gate_is_checked_before_attempt_materialization(monkeypatch, tmp_path: Path):
    calls: list[str] = []

    def blocked_gate():
        calls.append("gate")
        raise runner.InfrastructureBlocker("dummy absent")

    monkeypatch.setattr(runner, "verify_protocol_gate", blocked_gate)
    monkeypatch.setattr(runner, "RAW_ROOT", tmp_path / "raw")
    try:
        runner.run_attempt("X01", 1)
    except runner.InfrastructureBlocker:
        pass
    else:
        raise AssertionError("missing gate did not block construction")
    assert calls == ["gate"]
    assert not (tmp_path / "raw").exists()


def test_status_does_not_create_new_construction_root(monkeypatch, tmp_path: Path):
    root = tmp_path / "never-created"
    monkeypatch.setattr(runner, "RESULT_ROOT", root)
    status = runner.status_without_starting()
    assert status["status"] == "NOT_STARTED"
    assert status["total_constructor_attempts"] == 0
    assert not root.exists()


def test_protocol_keeps_all_frozen_scope_controls():
    result = preparation.verify_science()
    assert result["family_order"] == list(runner.IN_SCOPE)
    assert result["excluded_zero_attempts"] == ["X19", "X25"]
    assert result["attempt_cap"] == 4
    assert result["frozen_scientific_artifacts_unchanged"] is True
