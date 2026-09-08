from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from scripts.controlled_v2_catalog import FAMILIES, REFERENCE_STATES
import scripts.run_controlled_v2_constructors as runner
from scripts.validate_controlled_triplet_v2 import make_patch


DUMMY_RELEASE = {"inventory_sha256": "0" * 64}


def test_frozen_plan_has_first_pass_policy():
    plan = runner.verify_plan()
    assert plan["family_order"] == [item.family_id for item in FAMILIES]
    assert plan["attempt_policy"]["maximum_attempts_per_family"] == 3
    assert plan["attempt_policy"]["accept_first_complete_accept"] is True
    assert plan["attempt_policy"]["manual_patch_repair"] is False
    assert plan["attempt_policy"]["outcome_based_family_replacement"] is False


def test_constructor_input_allowlist_excludes_sealed_and_reference_material():
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
        assert not any(other.family_id.casefold() in joined for other in FAMILIES if other != item)


def test_prompt_binding_contains_no_prior_attempt_feedback():
    first = runner.render_prompt(DUMMY_RELEASE, "F01", 1)
    second = runner.render_prompt(DUMMY_RELEASE, "F01", 2)
    assert first != second
    assert b'"prior_attempt_feedback": false' in first
    assert b"validation decision" not in first.lower()
    assert b"previous candidate" not in first.lower()


def test_workspace_materialization_is_single_family_and_public_only(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner, "RAW_ROOT", tmp_path / "raw")
    manifest = runner.materialize_attempt("F03", 1, DUMMY_RELEASE)
    workspace = runner.attempt_root("F03", 1) / "workspace"
    files = {
        path.relative_to(workspace).as_posix()
        for path in workspace.rglob("*")
        if path.is_file()
    }
    assert manifest["sealed_tests_present"] is False
    assert "inputs/spec.json" in files
    assert "inputs/source/repo/app/service.py" in files
    assert "inputs/target/scaffold/app/service.py" not in files
    assert "tools/check_public.py" in files
    assert not any("sealed" in path.casefold() or "hidden" in path.casefold() for path in files)


def test_public_checker_accepts_reference_public_relationships(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner, "RAW_ROOT", tmp_path / "raw")
    runner.materialize_attempt("F10", 1, DUMMY_RELEASE)
    workspace = runner.attempt_root("F10", 1) / "workspace"
    reference = REFERENCE_STATES["F10"]
    service = workspace / "candidate/B/app/service.py"
    service.parent.mkdir(parents=True)
    service.write_text(reference.b, encoding="utf-8")
    (workspace / "candidate/feature.patch").write_text(
        make_patch(reference.b, reference.u), encoding="utf-8"
    )
    (workspace / "candidate/security.patch").write_text(
        make_patch(reference.u, reference.r), encoding="utf-8"
    )
    completed = subprocess.run(
        [sys.executable, "tools/check_public.py"],
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout
    assert json.loads(completed.stdout)["public_check_passed"] is True


def test_first_accept_stops_later_attempts(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(runner, "RAW_ROOT", tmp_path / "raw")
    first = runner.attempt_root("F01", 1) / "record/outcome.json"
    first.parent.mkdir(parents=True)
    first.write_text(json.dumps({"machine_accepted": False, "attempt": "attempt-001"}))
    assert runner.next_attempt_number("F01") == 2
    second = runner.attempt_root("F01", 2) / "record/outcome.json"
    second.parent.mkdir(parents=True)
    second.write_text(json.dumps({"machine_accepted": True, "attempt": "attempt-002"}))
    assert runner.next_attempt_number("F01") is None
