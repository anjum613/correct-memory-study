"""Generated-oracle, isolation, and exact release-integrity regression tests."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shutil

import pytest

from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_oracle_audit import (
    audit_candidate_oracle,
    audit_isolated_intended_u,
)
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_test_registry import checks
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.candidate_worker import _load_x02
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.contracts import IN_SCOPE
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.harness import functional
from synthetic_triplets.controlled_v3_executable_oracle_release_v1.integrity import (
    MANIFEST_RELATIVE,
    PACKAGE_RELATIVE,
    PROTECTED,
    RELEASE_TESTS,
    ReleaseIntegrityError,
    release_inventory_paths,
    verify_release,
)


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / PACKAGE_RELATIVE


def test_exact_generated_public_and_sealed_oracles_reproduce_all_26_matrices():
    result = audit_candidate_oracle()
    assert result["candidate_oracle_audit_pass"] is True
    assert result["candidate_oracle_pass_count"] == 26
    assert [row["family_id"] for row in result["families"]] == list(IN_SCOPE)
    assert all(row["candidate_oracle_pass"] for row in result["families"])
    assert result["constructor_attempts"] == 0
    assert result["evaluated_agent_outcomes"] == 0
    assert result["actual_human_reviews"] == 0


def test_every_intended_u_runs_in_production_isolation_and_has_trusted_failure():
    result = audit_isolated_intended_u()
    assert result["isolated_intended_u_audit_pass"] is True
    assert result["pass_count"] == 26
    for row in result["families"]:
        worker = row["worker_result"]
        assert worker["worker_status"] == "COMPLETE"
        assert worker["existing"]["status"] == "PASS"
        assert worker["feature"]["status"] == "PASS"
        assert worker["invariant"]["status"] == "FAIL"
        assert worker["invariant"]["condition"]


def _load_python(path):
    specification = importlib.util.spec_from_file_location("v3_unfinished_scaffold", path)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module.run


@pytest.mark.parametrize("family_id", IN_SCOPE)
def test_canonical_unfinished_scaffold_cannot_pass_requested_feature(family_id):
    extension = "csirpy" if family_id == "X02" else "py"
    path = PACKAGE / "agent_inputs" / family_id / f"target_scaffold.{extension}"
    application = _load_x02(path) if family_id == "X02" else _load_python(path)
    _existing, feature, _focal = checks(family_id)
    assert functional(feature, application)["status"] != "PASS"


def test_release_manifest_and_all_upstream_provenance_verify_exactly():
    result = verify_release()
    assert result["status"] == "CONSTRUCTION_READY"
    assert result["in_scope_family_count"] == 26
    assert result["excluded"] == ["X19", "X25"]
    assert result["constructor_attempts"] == 0
    assert result["evaluated_agent_outcomes"] == 0
    assert result["actual_v3_human_reviews"] == 0


def _copy_verification_tree(destination):
    paths = set(release_inventory_paths()) | set(PROTECTED) | {MANIFEST_RELATIVE.as_posix()}
    x19 = json.loads((ROOT / "protocols/controlled-synthetic-v3-x19-exclusion-v1/amendment.json").read_text())
    x25 = json.loads((ROOT / "protocols/controlled-synthetic-v3-x25-exclusion-v1/amendment.json").read_text())
    paths.add(x19["excluded_families"]["X19"]["evidence_path"])
    paths.update(x25["preservation"]["x25_diagnostic_snapshot"])
    for relative in paths:
        source = ROOT / relative
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


@pytest.mark.parametrize("mutation", (
    "frozen-specification",
    "canonical-source",
    "public-test",
    "sealed-test",
    "validator",
    "admission-ledger",
    "validator-meta-test",
    "extra-release-file",
))
def test_tampering_cannot_survive_exact_release_verification(tmp_path, mutation):
    _copy_verification_tree(tmp_path)
    assert verify_release(tmp_path)["status"] == "CONSTRUCTION_READY"
    paths = {
        "frozen-specification": "synthetic_triplets/controlled_v3_expansion/family_specs.json",
        "canonical-source": f"{PACKAGE_RELATIVE}/agent_inputs/X01/source_service.py",
        "public-test": f"{PACKAGE_RELATIVE}/agent_inputs/X01/public_tests.py",
        "sealed-test": f"{PACKAGE_RELATIVE}/researcher_tests/X01/sealed_tests.py",
        "validator": f"{PACKAGE_RELATIVE}/validator.py",
        "admission-ledger": f"{PACKAGE_RELATIVE}/admission_ledger.json",
        "validator-meta-test": RELEASE_TESTS[0],
        "extra-release-file": f"{PACKAGE_RELATIVE}/unexpected.txt",
    }
    path = tmp_path / paths[mutation]
    path.parent.mkdir(parents=True, exist_ok=True)
    if mutation == "extra-release-file":
        path.write_text("unexpected\n")
    else:
        path.write_bytes(path.read_bytes() + b"\ncontrolled tamper copy\n")
    with pytest.raises((ReleaseIntegrityError, ValueError)):
        verify_release(tmp_path)


def test_public_vectors_have_no_private_material_and_no_human_review_file_exists():
    public = json.loads((PACKAGE / "agent_inputs/shared/public_vectors.json").read_text())
    assert "private" not in json.dumps(public, sort_keys=True).lower()
    assert not list(PACKAGE.glob("human_review*"))
    ledger = json.loads((PACKAGE / "admission_ledger.json").read_text())
    assert ledger["constructor_attempts"] == 0
    assert ledger["evaluated_agent_outcomes"] == 0
    assert ledger["actual_human_reviews"] == 0
    assert ledger["human_review_files"] == 0
