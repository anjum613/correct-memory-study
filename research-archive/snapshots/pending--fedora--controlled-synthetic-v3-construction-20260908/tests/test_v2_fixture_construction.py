import hashlib
import json
from pathlib import Path

import pytest

from cmpilot.v2_fixture_audit import FAMILIES, validate_fixture_audit


ROOT = Path(__file__).parents[1]
MANIFEST = ROOT / "v2/fixtures/construction/manifest.json"


@pytest.fixture(scope="module")
def audit() -> dict:
    return validate_fixture_audit(ROOT, MANIFEST)


@pytest.mark.parametrize("family", FAMILIES)
def test_family_fixture_construction_is_honestly_blocked(audit: dict, family: str) -> None:
    row = audit["families"][family]
    assert row["status"] == "BLOCKED_NON_IDENTIFIABLE_FIXTURE"
    assert row["v2_base_repository_sha256"] is None
    assert row["blocking_constraints"]
    assert row["model_outcome_information_used"] is False


@pytest.mark.parametrize("family", FAMILIES)
def test_historical_trust_shift_is_frozen_but_no_bv2_is_claimed(
    audit: dict, family: str
) -> None:
    row = audit["families"][family]
    assert row["historical_trust_predicate"] == {
        "source": True,
        "compatible": True,
        "invalidated": False,
    }
    assert row["v2_base_repository_sha256"] is None


@pytest.mark.parametrize("family", FAMILIES)
def test_task_wording_and_source_memory_bytes_are_unchanged(
    audit: dict, family: str
) -> None:
    row = audit["families"][family]
    task = ROOT / row["task_path"]
    memory = ROOT / row["source_memory_path"]
    assert row["task_wording_changed"] is False
    assert hashlib.sha256(task.read_bytes()).hexdigest() == row["task_sha256"]
    assert hashlib.sha256(memory.read_bytes()).hexdigest() == row[
        "source_memory_sha256"
    ]


def test_no_completion_endpoint_or_control_matrix_is_fabricated(audit: dict) -> None:
    assert all(row["status"].startswith("BLOCKED_") for row in audit["families"].values())
    assert all("task_completion_endpoint_sha256" not in row for row in audit["families"].values())
    assert audit["historical_family_is_execution_fixture"] is False


def test_task_instructions_contain_no_new_security_cue(audit: dict) -> None:
    forbidden = ("p*", "trust assumption", "security witness", "safe control")
    for row in audit["families"].values():
        text = (ROOT / row["task_path"]).read_text().lower()
        assert not any(term in text for term in forbidden)


def test_all_frozen_security_witnesses_still_match_family_packages() -> None:
    for family in FAMILIES:
        root = ROOT / "families" / family
        package = json.loads((root / "family-package.json").read_text())
        witness = package["inputs"]["security_witness"]
        assert hashlib.sha256((root / witness["path"]).read_bytes()).hexdigest() == witness[
            "sha256"
        ]
