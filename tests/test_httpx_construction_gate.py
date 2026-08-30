from __future__ import annotations

import json
from pathlib import Path

from cmpilot.final_experiment import canonical_json_bytes
from scripts.probe_httpx_fix_boundary import (
    FIX_REVISION,
    FIX_TREE,
    VULNERABLE_REVISION,
    VULNERABLE_TREE,
    classify_observations,
)


ROOT = Path(__file__).parents[1]
FAMILY = ROOT / "families/httpx-v1"
STATUS_PATH = FAMILY / "provenance/construction-status.json"


def _status() -> dict[str, object]:
    payload = STATUS_PATH.read_bytes()
    value = json.loads(payload)
    assert payload == canonical_json_bytes(value)
    return value


def test_httpx_candidate_fails_closed_without_exact_selection_provenance() -> None:
    status = _status()

    gate = status["exact_selection_provenance_gate"]
    freeze = status["freeze"]
    materialization = status["materialization"]
    assert isinstance(gate, dict)
    assert isinstance(freeze, dict)
    assert isinstance(materialization, dict)
    assert gate["status"] == "BLOCKED"
    assert gate["expansion_rule_reachable"] is False
    assert gate["ordered_review_selection_full_commit_known"] is False
    assert gate["ordered_review_selection_reachable"] is False
    assert freeze["freeze_status"] == "NOT_FROZEN"
    assert freeze["model_ready"] is False
    assert freeze["production_manifest_permitted"] is False
    assert not any(materialization.values())


def test_no_final_httpx_family_artifacts_exist() -> None:
    forbidden = (
        "family-package.json",
        "memories",
        "oracles",
        "references",
        "repositories",
        "task-policy.json",
        "tasks",
        "validation",
    )

    assert all(not (FAMILY / relative).exists() for relative in forbidden)


def test_fix_boundary_constants_match_non_final_evidence_record() -> None:
    status = _status()
    evidence = status["fix_boundary_evidence"]
    assert isinstance(evidence, dict)

    assert evidence["scope"] == "NON_FINAL_ADVISORY_FIX_BOUNDARY_ONLY"
    assert evidence["assignment_to_track_b_triplet"] == "NOT_ESTABLISHED"
    assert evidence["fix_commit"] == FIX_REVISION
    assert evidence["fix_commit_parent"] == VULNERABLE_REVISION
    assert evidence["fix_commit_tree"] == FIX_TREE
    assert evidence["parent_tree"] == VULNERABLE_TREE


def test_fix_boundary_observation_classifier_requires_full_contrast() -> None:
    original = {"netloc": "", "raw_path": "//evilHost/path?t=w"}
    vulnerable = {
        "before": original,
        "after": {"netloc": "evilhost", "raw_path": "/path?t=w"},
    }
    fixed = {"before": original, "after": original}

    assert classify_observations(vulnerable, fixed) == {
        "fix_preserves_original_components": True,
        "parent_reinterprets_path_as_authority": True,
    }
    assert not all(classify_observations(fixed, fixed).values())
