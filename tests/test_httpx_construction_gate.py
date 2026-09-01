from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys

from cmpilot.final_experiment import canonical_json_bytes
from cmpilot.repository_manager import copy_repository_tree, repository_content_digest
from scripts.validate_mcp_pinot_family import snapshot_identity


ROOT = Path(__file__).parents[1]
FAMILY = ROOT / "families/httpx-v1"


def _object(relative: str) -> dict[str, object]:
    payload = (FAMILY / relative).read_bytes()
    value = json.loads(payload)
    assert payload == canonical_json_bytes(value)
    return value


def _probe(kind: str, repository: Path) -> dict[str, object]:
    process = subprocess.run(
        [
            sys.executable,
            str(FAMILY / f"oracles/{kind}/evaluate.py"),
            "--repository",
            str(repository),
            "--timeout-seconds",
            "5",
        ],
        capture_output=True,
        check=True,
        text=True,
    )
    return json.loads(process.stdout)


def test_exact_selection_provenance_is_imported_byte_for_byte() -> None:
    status = _object("provenance/track-b-provenance-status.json")
    imported = status["imported_artifact"]
    assert isinstance(imported, dict)
    review = FAMILY / str(imported["path"])
    payload = review.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == imported["sha256"]
    assert subprocess.check_output(
        ["git", "hash-object", str(review)], text=True
    ).strip() == imported["git_blob"]
    assert status["authoritative_selection_commit"] == (
        "9fe5c350aee4efed5288a075168262df32162c76"
    )
    assert status["selection_provenance_blocks_final_family_freeze"] is False


def test_exact_snapshots_reconstruct_authoritative_trees() -> None:
    provenance = _object("provenance/upstream-snapshot-provenance.json")
    records = provenance["snapshots"]
    assert isinstance(records, dict)
    for name in ("source", "compatible", "invalidated"):
        record = records[name]
        assert isinstance(record, dict)
        repository = FAMILY / "repositories" / name
        observed = snapshot_identity(repository)
        assert observed["git_tree_sha"] == record["tree_sha"]
        assert observed["snapshot_content_sha256"] == record["snapshot_content_sha256"]
        assert repository_content_digest(repository).sha256 == record[
            "repository_content_sha256"
        ]


def test_frozen_p_star_transition_executes() -> None:
    results = {
        name: _probe("security", FAMILY / "repositories" / name)
        for name in ("source", "compatible", "invalidated")
    }
    assert results["source"]["passed"] is True
    assert results["compatible"]["passed"] is True
    assert results["invalidated"]["passed"] is False


def test_memory_chronology_and_grounding_are_frozen() -> None:
    status = _object("provenance/construction-status.json")
    memory = _object("memories/memory-status.json")
    chronology = status["memory_chronology"]
    assert isinstance(chronology, dict)
    assert chronology["source_only_generation"] is True
    assert chronology["target_snapshots_materialized_after_source_memory_freeze"] is True
    assert memory["status"] == "FROZEN"
    assert memory["source_grounding_validation"] == "PASS"


def test_faithful_reference_has_required_pass_fail_contrast() -> None:
    functional = _probe("functional", FAMILY / "repositories/invalidated")
    security = _probe("security", FAMILY / "repositories/invalidated")
    assert functional["complete"] is True and functional["passed"] is True
    assert security["complete"] is True and security["passed"] is False


def test_safe_control_has_required_pass_pass_contrast(tmp_path: Path) -> None:
    repository = tmp_path / "safe-control"
    copy_repository_tree(FAMILY / "repositories/invalidated", repository)
    subprocess.run(["git", "init", "-q", str(repository)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "apply",
            str(FAMILY / "references/safe-control/secure.patch"),
        ],
        check=True,
    )
    functional = _probe("functional", repository)
    security = _probe("security", repository)
    assert functional["complete"] is True and functional["passed"] is True
    assert security["complete"] is True and security["passed"] is True
