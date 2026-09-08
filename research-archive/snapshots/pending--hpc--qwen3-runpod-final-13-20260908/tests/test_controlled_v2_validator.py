from __future__ import annotations

from pathlib import Path

import pytest

from scripts.controlled_v2_catalog import FAMILIES, FAMILY_BY_ID, REFERENCE_STATES
from scripts.validate_controlled_triplet_v2 import (
    AdmissionError,
    make_patch,
    validate_candidate,
    validate_python_policy,
)


def write_candidate(root: Path, family_id: str) -> Path:
    reference = REFERENCE_STATES[family_id]
    candidate = root / family_id
    service = candidate / "B/app/service.py"
    service.parent.mkdir(parents=True)
    service.write_text(reference.b, encoding="utf-8")
    (candidate / "feature.patch").write_text(
        make_patch(reference.b, reference.u), encoding="utf-8"
    )
    (candidate / "security.patch").write_text(
        make_patch(reference.u, reference.r), encoding="utf-8"
    )
    return candidate


def test_catalog_has_exactly_twenty_structurally_named_families():
    assert [item.family_id for item in FAMILIES] == [f"F{index:02d}" for index in range(1, 21)]
    assert len({item.slug for item in FAMILIES}) == 20
    assert len({item.mechanism for item in FAMILIES}) == 20
    assert len({item.mismatch_axis for item in FAMILIES}) == 20


@pytest.mark.parametrize("family_id", sorted(FAMILY_BY_ID))
def test_reference_candidate_satisfies_full_admission_matrix(tmp_path: Path, family_id: str):
    report = validate_candidate(family_id, write_candidate(tmp_path, family_id))
    failed = [item for item in report["checks"] if not item["passed"]]
    assert report["terminal_reason"] == "COMPLETE_ACCEPT", failed
    names = {item["name"] for item in report["checks"]}
    assert {
        "S_functional",
        "S_security",
        "B_existing",
        "B_requested_feature",
        "B_security_floor",
        "U_requested_feature",
        "U_security_witness",
        "R_requested_feature",
        "R_security_witness",
        "R_feature_retention",
        "U_to_R_unrelated_tree_integrity",
        "applicability_predicate_present_in_S",
        "applicability_predicate_invalidated_in_target",
        "single_mismatch_declaration",
        "witness_leakage_absent",
    } <= names


def test_constructor_payload_cannot_add_files(tmp_path: Path):
    candidate = write_candidate(tmp_path, "F01")
    (candidate / "notes.txt").write_text("not allowed", encoding="utf-8")
    report = validate_candidate("F01", candidate)
    assert report["terminal_reason"] == "REJECT"
    assert report["checks"][0]["name"] == "constructor_payload_allowlist"
    assert not report["checks"][0]["passed"]


def test_noop_feature_patch_is_rejected(tmp_path: Path):
    candidate = write_candidate(tmp_path, "F01")
    (candidate / "feature.patch").write_text("", encoding="utf-8")
    report = validate_candidate("F01", candidate)
    assert report["terminal_reason"] == "REJECT"


def test_patch_cannot_touch_scaffold_file(tmp_path: Path):
    candidate = write_candidate(tmp_path, "F01")
    (candidate / "security.patch").write_text(
        "--- a/app/dependencies.py\n+++ b/app/dependencies.py\n"
        "@@ -1,1 +1,1 @@\n-class PayloadSink:\n+class OtherSink:\n",
        encoding="utf-8",
    )
    report = validate_candidate("F01", candidate)
    assert report["terminal_reason"] == "REJECT"
    check = next(item for item in report["checks"] if item["name"] == "patches_touch_only_implementation")
    assert not check["passed"]


def test_incomplete_target_must_pass_security_floor(tmp_path: Path):
    candidate = write_candidate(tmp_path, "F01")
    reference = REFERENCE_STATES["F01"]
    # U as B makes the requested feature and the unsafe behavior pre-exist.
    (candidate / "B/app/service.py").write_text(reference.u, encoding="utf-8")
    (candidate / "feature.patch").write_text(
        make_patch(reference.u, reference.r), encoding="utf-8"
    )
    (candidate / "security.patch").write_text(
        make_patch(reference.r, reference.b), encoding="utf-8"
    )
    report = validate_candidate("F01", candidate)
    assert report["terminal_reason"] == "REJECT"
    by_name = {item["name"]: item for item in report["checks"]}
    assert not by_name["B_requested_feature"]["passed"]
    assert not by_name["B_security_floor"]["passed"]


def test_each_materialized_repo_has_four_application_source_files_and_config():
    for item in FAMILIES:
        assert len([path for path in item.source_files if path.endswith(".py")]) == 4
        assert len([path for path in item.target_scaffold_files if path.endswith(".py")]) == 3
        assert "pyproject.toml" in item.source_files
        assert "pyproject.toml" in item.target_scaffold_files
        assert item.implementation_path in item.source_files
        assert item.implementation_path not in item.target_scaffold_files


def test_source_memories_are_complete_but_do_not_state_target_answer():
    for item in FAMILIES:
        memory = item.source_memory
        assert "Source task\n" in memory
        assert "Reusable procedure\n" in memory
        assert "Why it was correct in the source\n" in memory
        assert "Implementation steps\n" in memory
        assert item.target_change not in memory
        assert item.secure_adaptation not in memory
        assert item.security_witness not in memory
        assert "hidden" not in memory.casefold()


def test_reference_patches_are_nonempty_and_directional():
    for family_id, reference in REFERENCE_STATES.items():
        assert reference.b != reference.u != reference.r
        assert reference.b != reference.r
        assert make_patch(reference.b, reference.u).strip()
        assert make_patch(reference.u, reference.r).strip()
        assert family_id in FAMILY_BY_ID


@pytest.mark.parametrize(
    "source",
    (
        "import socket\n",
        "import urllib.request\n",
        "from urllib.request import urlopen\n",
        "from pathlib import Path\n",
        "open('tests/test_contract.py')\n",
    ),
)
def test_static_policy_rejects_introspection_or_external_io(source: str):
    with pytest.raises(AdmissionError):
        validate_python_policy(source, label="candidate")
