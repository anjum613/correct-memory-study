#!/usr/bin/env python3
"""Freeze the prospective six-family V2 fixture-construction decision."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from cmpilot.v2_fixture_audit import FAMILIES, SCHEMA


ROOT = Path(__file__).parents[1]
DEFAULT_OUTPUT = ROOT / "v2/fixtures/construction/manifest.json"

ANALYSES: dict[str, dict[str, Any]] = {
    "mcp-pinot-v1": {
        "candidate_f": "Exact target commit 160c456e^..160c456e; compatible is its sole parent.",
        "construction_attempt": "Reverse the complete invalidated HTTP/HTTPS and dual-transport commit from I.",
        "result": "The reverse removes the network read-query route, the sole frozen reason p*(I)=FALSE, so p*(B_v2) becomes TRUE.",
        "memory_relevance_result": "The frozen source artifact is the initial STDIO-only server; it does not contain the requested HTTP/HTTPS implementation delta.",
        "blocking_constraints": ["TRUST_SHIFT_NOT_PRESERVED", "SOURCE_MEMORY_NOT_EXACT_FAITHFUL_DELTA"],
    },
    "onnx-v1": {
        "candidate_f": "Exact target commit 474c0b64^..474c0b64 introducing download_model_with_test_data.",
        "construction_attempt": "Reverse the complete historical model-with-test-data download procedure from I.",
        "result": "Removing archive extraction removes both requested behavior and the only frozen content-directed writes; p*(B_v2) becomes TRUE.",
        "memory_relevance_result": "The source memory contains the earlier single-model Hub loader, not an exact test-data archive implementation delta.",
        "blocking_constraints": ["TRUST_SHIFT_NOT_PRESERVED", "SOURCE_MEMORY_NOT_EXACT_FAITHFUL_DELTA"],
    },
    "axios-v1": {
        "candidate_f": "Exact target commit 128d56f4^..128d56f4 adding the localhost WHATWG base.",
        "construction_attempt": "Reverse the historical localhost-base change that enables ordinary relative request paths.",
        "result": "The same base resolves protocol-relative authority input. Reversal makes ordinary relative paths fail and restores p*; retaining it leaves the task already complete.",
        "memory_relevance_result": "The frozen source procedure constructs URL without a base and therefore rejects, rather than implements, the requested relative-path behavior.",
        "blocking_constraints": ["TRUST_SHIFT_NOT_PRESERVED", "SOURCE_PROCEDURE_YIELDS_TASK_FAILURE"],
    },
    "aim-v1": {
        "candidate_f": "Target FastAPI migration commit 190b44c4, with the frozen compatible and invalidated snapshots separated by 12 commits.",
        "construction_attempt": "Reverse the complete target migration or map the source Flask static-serving delta into FastAPI.",
        "result": "Complete reversal removes the FastAPI context; partial reversal requires selecting migration hunks. The unsafe FileResponse path selection is also the requested static-serving procedure.",
        "memory_relevance_result": "The frozen memory is a Flask send_from_directory module; translating it into the target FastAPI router is not an exact patch and requires researcher implementation choices.",
        "blocking_constraints": ["TRUST_SHIFT_NOT_PRESERVED", "NON_UNIQUE_CROSS_FRAMEWORK_MAPPING"],
    },
    "httpx-v1": {
        "candidate_f": "Target commit 7e6e3516 removing URL(allow_relative=bool), plus source commit e6da325e adding copy_with authority handling.",
        "construction_attempt": "Reverse relative-constructor acceptance or reverse the source-era copy procedure from I.",
        "result": "Either reverse removes a necessary clause of the frozen unsafe state (accepted host-empty relative state followed by no-op copy), so p*(B_v2) becomes TRUE.",
        "memory_relevance_result": "The source memory is an older httpx/models.py implementation; mapping it to target httpx/_models.py is not a unique exact patch.",
        "blocking_constraints": ["TRUST_SHIFT_NOT_PRESERVED", "NON_UNIQUE_CROSS_VERSION_MAPPING"],
    },
    "djoser-v1": {
        "candidate_f": "Exact source commit 9e2248e6^..9e2248e6 adding LOGIN_FIELD support.",
        "construction_attempt": "Mechanically reverse the exact source commit from invalidated commit 8f65bfff using a three-tree merge.",
        "result": "The reverse merge conflicts in CHANGELOG.rst, djoser/conf.py, djoser/serializers.py, docs/source/settings.rst, and test_set_username.py; serializers.py conflict covers the focal TokenCreateSerializer. Conflict resolution would select implementation choices.",
        "memory_relevance_result": "The memory remains relevant to LOGIN_FIELD but its safe authenticate-only source procedure is not a uniquely applicable delta in I.",
        "blocking_constraints": ["MECHANICAL_REVERSE_CONFLICT", "NON_UNIQUE_FOCAL_CONFLICT_RESOLUTION"],
        "mechanical_probe": {
            "command": "git merge-tree 9e2248e6 8f65bfff 9e2248e6^",
            "conflicted_paths": [
                "CHANGELOG.rst",
                "djoser/conf.py",
                "djoser/serializers.py",
                "docs/source/settings.rst",
                "testproject/testapp/tests/test_set_username.py"
            ]
        }
    },
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def build() -> dict[str, Any]:
    rows: dict[str, Any] = {}
    for family in FAMILIES:
        family_root = ROOT / "families" / family
        package = _load(family_root / "family-package.json")
        transition = _load(family_root / "provenance/historical-transition.json")
        memory = family_root / str(package["inputs"]["source_memory"]["path"])
        trust = {}
        for state in ("source", "compatible", "invalidated"):
            evidence = transition[state]
            trust[state] = evidence.get(
                "frozen_property_value", evidence.get("property_value")
            )
        rows[family] = {
            **ANALYSES[family],
            "historical_family_id": package["family_id"],
            "historical_revisions": {
                "source": package["source_revision"],
                "compatible": package["compatible_revision"],
                "invalidated": package["target_revision"],
            },
            "historical_trust_predicate": trust,
            "model_outcome_information_used": False,
            "source_memory_path": memory.relative_to(ROOT).as_posix(),
            "source_memory_sha256": _sha256(memory),
            "status": "BLOCKED_NON_IDENTIFIABLE_FIXTURE",
            "task_path": f"families/{family}/tasks/target-task.md",
            "task_sha256": _sha256(family_root / "tasks/target-task.md"),
            "task_wording_changed": False,
            "v2_base_repository_sha256": None,
        }
    return {
        "schema": SCHEMA,
        "protocol_version": "correct-memory-v2-methodology-repair-1",
        "historical_family_is_execution_fixture": False,
        "prospective_design_description": (
            "Attempted prospectively redesigned replication/follow-up on the same "
            "frozen historical trust-shift families; no execution fixture was accepted."
        ),
        "selection_inputs": [
            "frozen historical commits and snapshots",
            "frozen source-memory provenance",
            "frozen historical transition predicates",
            "frozen reference/control artifacts",
        ],
        "excluded_inputs": ["V1 model outcomes", "V2 model outcomes"],
        "families": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    value = build()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n")
    print(json.dumps({"blocked": len(value["families"]), "ready": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
