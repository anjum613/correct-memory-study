from __future__ import annotations

import hashlib
import json
from pathlib import Path

from scripts.controlled_v2_catalog import FAMILIES as ORIGINAL_FAMILIES
from scripts.reserve_catalog_v2 import (
    FAMILIES,
    REFERENCE_STATES,
)
import scripts.freeze_controlled_v2_reserve as freeze
import scripts.run_controlled_v2_reserve as runner
from scripts.validate_controlled_triplet_v2 import make_patch
from scripts.validate_controlled_triplet_v2_reserve import validate_candidate


DUMMY_RELEASE = {"inventory_sha256": "0" * 64}


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


def test_reserve_order_and_policy_are_frozen():
    plan = runner.verify_plan()
    assert plan["reserve_order"] == ["R01", "R02", "R03", "R04", "R05"]
    assert plan["known_retired_original_families_at_freeze"] == ["F10"]
    assert plan["selection_policy"]["use_reserves_in_frozen_lexical_order"] is True
    assert plan["selection_policy"]["rerun_previously_accepted_families"] is False
    assert plan["attempt_policy"]["maximum_attempts_per_reserve_family"] == 5
    assert plan["attempt_policy"]["manual_patch_repair"] is False


def test_reserve_mechanisms_are_unique_and_new():
    reserve = {item.mechanism for item in FAMILIES}
    original = {item.mechanism for item in ORIGINAL_FAMILIES}
    assert len(reserve) == len(FAMILIES) == 5
    assert reserve.isdisjoint(original)


def test_reference_states_all_pass_unchanged_validator(tmp_path: Path):
    for item in FAMILIES:
        reference = REFERENCE_STATES[item.family_id]
        candidate = tmp_path / item.family_id
        service = candidate / "B/app/service.py"
        service.parent.mkdir(parents=True)
        service.write_text(reference.b, encoding="utf-8")
        (candidate / "feature.patch").write_text(
            make_patch(reference.b, reference.u), encoding="utf-8"
        )
        (candidate / "security.patch").write_text(
            make_patch(reference.u, reference.r), encoding="utf-8"
        )
        report = validate_candidate(item.family_id, candidate)
        assert report["terminal_reason"] == "COMPLETE_ACCEPT", report
        assert len(report["checks"]) == 21
        assert report["reserve_catalog_adapter_only"] is True


def test_constructor_allowlist_excludes_sealed_and_reference_material():
    for item in FAMILIES:
        mappings = runner.constructor_input_files(item.family_id)
        destinations = {path.as_posix() for path in mappings.values()}
        assert "inputs/spec.json" in destinations
        assert "inputs/source/source_correct_memory.md" in destinations
        assert "inputs/target/task.md" in destinations
        assert any("public_feature" in path for path in destinations)
        joined = "\n".join(destinations).casefold()
        assert "sealed" not in joined
        assert "hidden" not in joined
        assert "reference" not in joined


def test_prompt_has_no_prior_feedback_and_requires_exact_contract():
    prompt = runner.render_prompt(DUMMY_RELEASE, "R01", 1)
    assert b"Follow observable contracts" in prompt
    assert b"`NotImplementedError`" in prompt
    assert b"python3 tools/check_public.py" in prompt
    assert b'"prior_attempt_feedback": false' in prompt
    assert b"previous candidate" not in prompt.lower()


def test_materialization_is_one_family_and_public_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner, "RAW_ROOT", tmp_path / "raw")
    manifest = runner.materialize_attempt("R02", 1, DUMMY_RELEASE)
    workspace = runner.attempt_root("R02", 1) / "workspace"
    files = {
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file()
    }
    assert manifest["sealed_tests_present"] is False
    assert manifest["prior_attempt_feedback_present"] is False
    assert "inputs/spec.json" in files
    assert "inputs/source/repo/app/service.py" in files
    assert "tools/check_public.py" in files
    assert not any("sealed" in path.casefold() or "hidden" in path.casefold() for path in files)


def test_first_accept_stops_reserve_attempts(tmp_path: Path, monkeypatch):
    raw = tmp_path / "raw"
    monkeypatch.setattr(runner, "RAW_ROOT", raw)
    write_outcome(raw, "R01", 1, False)
    assert runner.next_attempt_number("R01") == 2
    write_outcome(raw, "R01", 2, True)
    assert runner.next_attempt_number("R01") is None


def test_release_inventory_excludes_acquisitions_and_references_are_not_materialized():
    paths = {path.relative_to(freeze.REPO_ROOT).as_posix() for path in freeze.released_paths()}
    assert "synthetic_triplets/controlled_v2_reserve/reserve_plan.json" in paths
    assert "synthetic_triplets/controlled_v2_reserve/generator_prompt.md" in paths
    assert "scripts/validate_controlled_triplet_v2.py" in paths
    assert not any("acquisitions" in path for path in paths)
    assert not any("reference_states" in path for path in paths)


def test_frozen_validator_file_is_bound_by_release_inventory():
    path = freeze.REPO_ROOT / "scripts/validate_controlled_triplet_v2.py"
    entry = freeze.inventory()[path.relative_to(freeze.REPO_ROOT).as_posix()]
    assert entry["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
