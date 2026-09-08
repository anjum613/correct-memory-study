from __future__ import annotations

import json
from pathlib import Path

from scripts.controlled_v2_catalog import FAMILIES
import scripts.freeze_controlled_v2_continuation as freeze
import scripts.run_controlled_v2_continuation as runner


DUMMY_RELEASE = {
    "base_filter_inventory_sha256": "0" * 64,
    "inventory_sha256": "1" * 64,
}


def write_outcome(root: Path, family_id: str, number: int, accepted: bool) -> None:
    path = root / family_id / f"attempt-{number:03d}" / "record/outcome.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "family_id": family_id,
                "attempt": f"attempt-{number:03d}",
                "machine_accepted": accepted,
            }
        ),
        encoding="utf-8",
    )


def test_plan_skips_accepted_and_caps_continuation():
    plan = runner.verify_plan()
    assert plan["family_order"] == [item.family_id for item in FAMILIES]
    assert plan["eligibility"]["accepted_families_are_never_rerun"] is True
    assert plan["attempt_policy"]["first_continuation_attempt"] == 4
    assert plan["attempt_policy"]["last_continuation_attempt"] == 8
    assert plan["attempt_policy"]["manual_patch_repair"] is False
    assert plan["attempt_policy"]["validator_changes"] is False


def test_prompt_makes_full_B_interface_and_explicit_rejection_unambiguous():
    prompt = runner.render_prompt(DUMMY_RELEASE, "F02", 4)
    assert b"complete target callable interface" in prompt
    assert b"raise `NotImplementedError`" in prompt
    assert b"silently ignore" in prompt
    assert b"python3 tools/check_public.py" in prompt
    assert b'"prior_attempt_feedback": false' in prompt
    assert b"previous candidate" not in prompt.lower()


def test_materialized_workspace_has_one_family_and_no_prior_attempts(
    tmp_path: Path, monkeypatch
):
    monkeypatch.setattr(runner, "RAW_ROOT", tmp_path / "raw")
    manifest = runner.materialize_attempt("F04", 4, DUMMY_RELEASE)
    workspace = runner.attempt_root("F04", 4) / "workspace"
    files = {
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file()
    }
    assert manifest["prior_attempt_artifacts_present"] is False
    assert manifest["sealed_tests_present"] is False
    assert "inputs/spec.json" in files
    assert "tools/check_public.py" in files
    assert not any("sealed" in path.casefold() or "hidden" in path.casefold() for path in files)


def test_existing_accept_is_never_rerun(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw"
    monkeypatch.setattr(runner, "RAW_ROOT", raw)
    write_outcome(raw, "F01", 1, True)
    assert runner.next_attempt_number("F01") is None


def test_three_rejections_start_at_four_and_first_accept_stops(
    tmp_path: Path, monkeypatch
):
    raw = tmp_path / "raw"
    monkeypatch.setattr(runner, "RAW_ROOT", raw)
    for number in range(1, 4):
        write_outcome(raw, "F05", number, False)
    assert runner.next_attempt_number("F05") == 4
    write_outcome(raw, "F05", 4, True)
    assert runner.next_attempt_number("F05") is None


def test_eight_rejections_exhaust_continuation(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw"
    monkeypatch.setattr(runner, "RAW_ROOT", raw)
    for number in range(1, 9):
        write_outcome(raw, "F07", number, False)
    assert runner.next_attempt_number("F07") is None


def test_release_inventory_is_narrow_and_excludes_acquisitions():
    paths = {path.relative_to(freeze.REPO_ROOT).as_posix() for path in freeze.released_paths()}
    assert "synthetic_triplets/controlled_v2_continuation/continuation_plan.json" in paths
    assert "synthetic_triplets/controlled_v2_continuation/continuation_prompt.md" in paths
    assert "synthetic_triplets/controlled_v2/filter_release.json" in paths
    assert "scripts/run_controlled_v2_continuation.py" in paths
    assert not any("acquisitions" in path for path in paths)
