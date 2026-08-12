from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from cmpilot.stage1_screening import (
    AUTOMATIC_GATES,
    MECHANISM_GATES,
    Stage1ScreeningError,
    apply_results_to_ledger,
    screen_batch,
    verify_screening,
)


ROOT = Path(__file__).parents[1]
METHOD_COMMIT = "a" * 40
SHA256 = "b" * 64


def _git(*arguments: str, cwd: Path | None = None) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_stage1_result_schema_freezes_scope_and_gate_vocabulary() -> None:
    schema = json.loads(
        (
            ROOT / "benchmark-selection/stage1/v0.1/result.schema.json"
        ).read_text(encoding="utf-8")
    )

    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert set(schema["properties"]["automatic_gates"]["required"]) == set(
        AUTOMATIC_GATES
    )
    assert schema["properties"]["trust_family_assigned"]["const"] is False
    assert schema["properties"]["ranked_or_selected"]["const"] is False
    assert schema["properties"]["treatment_results_consulted"]["const"] is False


def _write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _upstream_repository(tmp_path: Path) -> tuple[Path, str, str]:
    work = tmp_path / "upstream-work"
    work.mkdir()
    _git("init", cwd=work)
    _git("checkout", "-b", "main", cwd=work)
    _git("config", "user.email", "fixture@example.invalid", cwd=work)
    _git("config", "user.name", "Stage1 Fixture", cwd=work)

    (work / "src").mkdir()
    (work / "tests").mkdir()
    (work / "LICENSE").write_text("MIT License\n", encoding="utf-8")
    (work / "pyproject.toml").write_text(
        """[project]
name = "stage1-fixture"
requires-python = ">=3.11"
dependencies = ["requests"]

[project.optional-dependencies]
test = ["pytest"]
""",
        encoding="utf-8",
    )
    (work / "requirements.txt").write_text(
        "requests==2.32.0\n-e ../shared\n", encoding="utf-8"
    )
    (work / "src/demo.py").write_text(
        """import requests
import sqlite3

NETWORK_CLIENT = requests.get
GPU_BACKEND = "torch.cuda"
PROPRIETARY_CLIENT = "openai"
""",
        encoding="utf-8",
    )
    (work / "tests/test_demo.py").write_text(
        """import pytest

def test_one():
    assert True

async def test_two():
    assert True

class TestGroup:
    def test_three(self):
        assert True
""",
        encoding="utf-8",
    )
    _git("add", ".", cwd=work)
    _git("commit", "-m", "fixture", cwd=work)
    commit = _git("rev-parse", "HEAD", cwd=work)
    tree = _git("rev-parse", "HEAD^{tree}", cwd=work)
    bare = tmp_path / "upstream.git"
    _git("clone", "--bare", str(work), str(bare))
    return bare, commit, tree


def _candidate(
    *, candidate_id: str, position: int, repository: Path, commit: str, tree: str
) -> dict[str, object]:
    repository_url = repository.resolve().as_uri()
    return {
        "candidate_id": candidate_id,
        "position": position,
        "source": {
            "forge": "fixture.invalid",
            "repository_url": repository_url,
            "upstream_owner": "fixture",
            "upstream_name": f"repository-{position}",
            "licence_spdx": "MIT",
            "discovery": {
                "source_list_id": "stage1-fixture-source",
                "source_list_sha256": None,
                "position": position,
                "discovered_at_utc": "2026-08-12T00:00:00Z",
                "discoverer_id": "fixture-discoverer",
            },
            "snapshot": {
                "commit_sha": commit,
                "commit_date_utc": "2026-08-12T00:00:00Z",
                "tree_sha256": SHA256,
                "metadata_sha256": SHA256,
                "retrieval_method": "fixture exact commit",
            },
        },
        "normalized_metadata": {
            "repository": {
                "full_name": f"fixture/repository-{position}",
                "default_branch": "main",
                "language": "Python",
                "license_spdx": "MIT",
                "size_kib": 12,
            },
            "commit": {"sha": commit, "tree_sha": tree},
        },
    }


def _ledger_record(candidate: dict[str, object], source_hash: str) -> dict[str, object]:
    source = deepcopy(candidate["source"])
    assert isinstance(source, dict)
    discovery = source["discovery"]
    assert isinstance(discovery, dict)
    discovery["source_list_sha256"] = source_hash
    evidence = {
        "path": "benchmark-selection/discovery/source-list.json",
        "sha256": source_hash,
    }
    return {
        "candidate_id": candidate["candidate_id"],
        "protocol_version": "benchmark-selection-v0.1",
        "current_state": "DISCOVERED",
        "status_history": [
            {
                "sequence": 1,
                "state": "DISCOVERED",
                "recorded_at_utc": "2026-08-12T00:00:00Z",
                "actor_id": "fixture-discoverer",
                "protocol_version": "benchmark-selection-v0.1",
                "rationale": "fixture discovery",
                "evidence": [evidence],
            }
        ],
        "source": source,
        "trust_family": None,
        "mechanism_key": None,
        "hard_gates": {
            gate: {"status": "NOT_ASSESSED", "evidence": []}
            for gate in (*AUTOMATIC_GATES, *MECHANISM_GATES)
        },
        "treatment_results_consulted": False,
    }


def _screening_fixture(
    tmp_path: Path,
    *,
    candidate_count: int = 1,
    wrong_tree: bool = False,
    missing_repository: bool = False,
) -> tuple[Path, Path, Path, Path, dict[str, object]]:
    bare, commit, tree = _upstream_repository(tmp_path)
    project = tmp_path / "project"
    protocol = project / "benchmark-selection/stage1/v0.1/screening-protocol.md"
    schema = project / "benchmark-selection/stage1/v0.1/result.schema.json"
    protocol.parent.mkdir(parents=True)
    shutil.copyfile(
        ROOT / "benchmark-selection/stage1/v0.1/screening-protocol.md", protocol
    )
    shutil.copyfile(ROOT / "benchmark-selection/stage1/v0.1/result.schema.json", schema)

    repository = tmp_path / "missing.git" if missing_repository else bare
    candidates = [
        _candidate(
            candidate_id=f"CMVP-CAND-{index:04d}",
            position=index,
            repository=repository,
            commit=commit,
            tree=("f" * 40 if wrong_tree else tree),
        )
        for index in range(1, candidate_count + 1)
    ]
    source_list = {
        "source_list_id": "stage1-fixture-source",
        "candidate_count": candidate_count,
        "candidates": candidates,
    }
    source_path = project / "benchmark-selection/discovery/source-list.json"
    _write_json(source_path, source_list)
    source_hash = hashlib.sha256(source_path.read_bytes()).hexdigest()
    spec = {
        "schema": "stage1-inspection-spec-v0.1",
        "protocol_version": "benchmark-selection-v0.1",
        "actor_id": "fixture-stage1-inspector",
        "automatic_gate_order": list(AUTOMATIC_GATES),
        "candidate_code_execution": False,
        "installation_executed": False,
        "test_execution_allowed": False,
        "treatment_results_consulted": False,
        "expected_candidate_ids": [
            str(candidate["candidate_id"]) for candidate in candidates
        ],
        "clone": {
            "checkout": False,
            "depth": 1,
            "hooks": False,
            "method": "fresh_bare_init_plus_exact_commit_fetch",
            "network_timeout_seconds": 20,
            "tags": False,
            "terminal_credential_prompt": False,
        },
        "content_limits": {
            "maximum_blob_bytes": 1024 * 1024,
            "maximum_total_scanned_blob_bytes": 20 * 1024 * 1024,
        },
        "input_source_list": "benchmark-selection/discovery/source-list.json",
        "input_source_list_sha256": source_hash,
        "ordering": "ascending_source_list_position",
        "output_directory": "benchmark-selection/stage1/results/fixture",
        "screening_protocol": (
            "benchmark-selection/stage1/v0.1/screening-protocol.md"
        ),
    }
    spec_path = project / "benchmark-selection/stage1/v0.1/inspection-spec.json"
    _write_json(spec_path, spec)
    ledger = project / "benchmark-selection/candidate-ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        "".join(
            json.dumps(_ledger_record(candidate, source_hash), sort_keys=True) + "\n"
            for candidate in candidates
        ),
        encoding="utf-8",
    )
    output = project / str(spec["output_directory"])
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    manifest = screen_batch(
        project_root=project,
        spec_path=spec_path,
        output_directory=output,
        method_commit=METHOD_COMMIT,
        scratch_parent=scratch,
    )
    return project, spec_path, output, ledger, manifest


def test_static_screen_collects_objective_facts_without_execution(
    tmp_path: Path,
) -> None:
    project, spec, output, ledger, manifest = _screening_fixture(tmp_path)
    result = json.loads(
        (output / "candidates/CMVP-CAND-0001.json").read_text(encoding="utf-8")
    )

    assert manifest["candidate_order"] == ["CMVP-CAND-0001"]
    assert result["repository"]["default_branch"] == "main"
    assert result["facts"]["license"]["captured_spdx"] == "MIT"
    assert result["facts"]["frozen_commit_resolution"]["fetch_succeeded"] is True
    assert result["facts"]["repository_size"]["bare_depth1_clone_apparent_bytes"] > 0
    assert result["facts"]["tests"]["directories"] == ["tests"]
    assert result["facts"]["tests"]["detected_frameworks"] == ["pytest"]
    assert result["facts"]["tests"]["cheap_test_count"]["total"] == 3
    assert result["facts"]["tests"]["likely_baseline_command"]["command"] == (
        "python -m pytest -q"
    )
    assert result["facts"]["setup_command_candidates"]
    assert result["facts"]["clean_installation"]["status"] == "NEEDS_REVIEW"
    assert result["facts"]["static_text_scan"]["scanned_file_count"] >= 5
    assert result["facts"]["network_requirement"]["status"] == (
        "DETECTED_BY_STATIC_SCAN"
    )
    assert result["facts"]["gpu_requirement"]["status"] == (
        "DETECTED_BY_STATIC_SCAN"
    )
    assert result["facts"]["database_requirement"]["status"] == (
        "DETECTED_BY_STATIC_SCAN"
    )
    assert result["facts"]["proprietary_dependency_requirement"]["status"] == (
        "DETECTED_BY_STATIC_SCAN"
    )
    assert result["automatic_gates"]["usable_licence"]["status"] == "PASS"
    assert result["automatic_gates"]["immutable_commit"]["status"] == "PASS"
    assert {
        result["automatic_gates"][gate]["status"]
        for gate in AUTOMATIC_GATES[2:]
    } == {"NEEDS_REVIEW"}
    assert result["resulting_state"] == "DISCOVERED"
    assert result["inspection"]["candidate_code_executed"] is False
    assert result["inspection"]["checkout_created"] is False
    assert result["inspection"]["installation_executed"] is False
    assert result["inspection"]["tests_executed"] is False
    assert not list((tmp_path / "scratch").iterdir())

    application = apply_results_to_ledger(
        project_root=project, output_directory=output, ledger_path=ledger
    )
    records = [json.loads(line) for line in ledger.read_text().splitlines()]
    assert application["candidate_count"] == 1
    assert records[0]["current_state"] == "DISCOVERED"
    assert len(records[0]["status_history"]) == 1
    assert records[0]["stage1_screening"]["sha256"]
    assert all(
        records[0]["hard_gates"][gate]["status"] != "NOT_ASSESSED"
        for gate in AUTOMATIC_GATES
    )
    assert all(
        records[0]["hard_gates"][gate]["status"] == "NOT_ASSESSED"
        for gate in MECHANISM_GATES
    )
    assert verify_screening(
        project_root=project,
        spec_path=spec,
        output_directory=output,
        ledger_path=ledger,
    )["pass"] is True


def test_screening_covers_every_frozen_candidate_in_order(tmp_path: Path) -> None:
    _, _, _, _, manifest = _screening_fixture(tmp_path, candidate_count=2)

    assert manifest["candidate_count"] == 2
    assert manifest["candidate_order"] == ["CMVP-CAND-0001", "CMVP-CAND-0002"]


def test_successful_tree_mismatch_is_an_exact_exclusion(tmp_path: Path) -> None:
    project, _, output, ledger, _ = _screening_fixture(tmp_path, wrong_tree=True)
    result = json.loads(
        (output / "candidates/CMVP-CAND-0001.json").read_text(encoding="utf-8")
    )

    assert result["automatic_gates"]["immutable_commit"]["status"] == "FAIL"
    assert result["resulting_state"] == "EXCLUDED"
    apply_results_to_ledger(
        project_root=project, output_directory=output, ledger_path=ledger
    )
    record = json.loads(ledger.read_text(encoding="utf-8"))
    assert record["current_state"] == "EXCLUDED"
    assert record["exclusion"]["code"] == "IMMUTABLE_COMMIT_UNAVAILABLE"
    assert len(record["status_history"]) == 2


def test_fetch_failure_is_needs_review_not_exclusion(tmp_path: Path) -> None:
    _, _, output, _, _ = _screening_fixture(tmp_path, missing_repository=True)
    result = json.loads(
        (output / "candidates/CMVP-CAND-0001.json").read_text(encoding="utf-8")
    )

    assert result["facts"]["frozen_commit_resolution"]["fetch_succeeded"] is False
    assert result["automatic_gates"]["immutable_commit"]["status"] == (
        "NEEDS_REVIEW"
    )
    assert result["resulting_state"] == "DISCOVERED"


def test_screening_refuses_overwrite_and_detects_tampering(tmp_path: Path) -> None:
    project, spec, output, ledger, _ = _screening_fixture(tmp_path)
    with pytest.raises(Stage1ScreeningError, match="already exists"):
        screen_batch(
            project_root=project,
            spec_path=spec,
            output_directory=output,
            method_commit=METHOD_COMMIT,
            scratch_parent=tmp_path / "scratch",
        )

    apply_results_to_ledger(
        project_root=project, output_directory=output, ledger_path=ledger
    )
    result_path = output / "candidates/CMVP-CAND-0001.json"
    result_path.write_text("{}\n", encoding="utf-8")
    with pytest.raises(Stage1ScreeningError, match="hash mismatch"):
        verify_screening(
            project_root=project,
            spec_path=spec,
            output_directory=output,
            ledger_path=ledger,
        )
