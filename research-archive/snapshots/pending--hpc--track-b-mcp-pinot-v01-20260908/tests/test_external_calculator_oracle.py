from __future__ import annotations

import hashlib
import json
from pathlib import Path

from cmpilot.external_calculator_oracle import (
    DEFAULT_CALCULATOR_ORACLE,
    build_calculator_validation_tree,
    copy_immutable_oracle_bundle,
    run_external_calculator_oracle,
    validate_oracle_bundle,
)
from cmpilot.protected_oracle_replay import retrospective_job_25575_check
from cmpilot.repository_manager import copy_repository_tree
from cmpilot.task_file_policy import calculator_task_policy


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "tasks" / "smoke_test" / "repository"


def _agent_repository(tmp_path: Path, calculator: str) -> Path:
    repository = tmp_path / "agent-repository"
    copy_repository_tree(SOURCE, repository)
    (repository / "calculator.py").write_text(calculator, encoding="utf-8")
    return repository


def _immutable_bundle(tmp_path: Path) -> Path:
    return copy_immutable_oracle_bundle(
        DEFAULT_CALCULATOR_ORACLE, tmp_path / "immutable-oracle"
    )


def test_external_oracle_bundle_is_versioned_and_manifest_valid() -> None:
    manifest = validate_oracle_bundle(DEFAULT_CALCULATOR_ORACLE)

    assert manifest["valid"] is True
    assert manifest["oracle_version"] == "calculator-external-oracle-v1"
    assert manifest["files"]["test_calculator.py"]["matches"] is True


def test_external_oracle_is_outside_agent_working_tree(tmp_path: Path) -> None:
    repository = _agent_repository(
        tmp_path, "def add(a, b):\n    return a + b\n"
    )
    bundle = _immutable_bundle(tmp_path)

    assert not bundle.is_relative_to(repository)
    assert not repository.is_relative_to(bundle)


def test_agent_test_modification_cannot_change_external_oracle_hash(
    tmp_path: Path,
) -> None:
    repository = _agent_repository(
        tmp_path, "def add(a, b):\n    return a + b\n"
    )
    bundle = _immutable_bundle(tmp_path)
    before = validate_oracle_bundle(bundle)

    (repository / "test_calculator.py").write_text(
        "def test_fake():\n    assert True\n", encoding="utf-8"
    )
    after = validate_oracle_bundle(bundle)

    assert before["manifest_sha256"] == after["manifest_sha256"]
    assert before["files"] == after["files"]


def test_validation_tree_uses_only_allowed_agent_changes(tmp_path: Path) -> None:
    repository = _agent_repository(
        tmp_path, "def add(a, b):\n    return a + b\n"
    )
    (repository / "test_calculator.py").write_text(
        "def test_fake():\n    assert True\n", encoding="utf-8"
    )
    bundle = _immutable_bundle(tmp_path)

    result = build_calculator_validation_tree(
        source_repository=SOURCE,
        agent_repository=repository,
        oracle_bundle=bundle,
        destination=tmp_path / "validation",
        task_policy=calculator_task_policy(),
    )

    assert (result.repository / "calculator.py").read_text() == (
        "def add(a, b):\n    return a + b\n"
    )
    assert (result.repository / "test_calculator.py").read_bytes() == (
        bundle / "test_calculator.py"
    ).read_bytes()
    assert "test_calculator.py" in result.protected_paths_modified
    assert "test_fake" in result.disallowed_diff
    assert "calculator.py" in result.allowed_patch


def test_correct_allowed_patch_passes_immutable_oracle(tmp_path: Path) -> None:
    repository = _agent_repository(
        tmp_path, "def add(a, b):\n    return a + b\n"
    )
    bundle = _immutable_bundle(tmp_path)

    result = run_external_calculator_oracle(
        source_repository=SOURCE,
        agent_repository=repository,
        oracle_bundle=bundle,
        destination=tmp_path / "validation",
    )

    assert result.returncode == 0
    assert result.passed == 3
    assert result.failed == 0
    assert result.manifest_before_sha256 == result.manifest_after_sha256
    assert "3 passed" in result.output


def test_incorrect_allowed_patch_fails_immutable_oracle(tmp_path: Path) -> None:
    repository = _agent_repository(
        tmp_path, "def add(a, b):\n    return a - b\n"
    )
    bundle = _immutable_bundle(tmp_path)

    result = run_external_calculator_oracle(
        source_repository=SOURCE,
        agent_repository=repository,
        oracle_bundle=bundle,
        destination=tmp_path / "validation",
    )

    assert result.returncode != 0
    assert result.failed == 3
    assert result.passed == 0


def test_test_only_change_cannot_create_authoritative_pass(tmp_path: Path) -> None:
    repository = _agent_repository(
        tmp_path, "def add(a, b):\n    raise NotImplementedError\n"
    )
    (repository / "test_calculator.py").write_text(
        "def test_fake():\n    assert True\n", encoding="utf-8"
    )
    bundle = _immutable_bundle(tmp_path)

    result = run_external_calculator_oracle(
        source_repository=SOURCE,
        agent_repository=repository,
        oracle_bundle=bundle,
        destination=tmp_path / "validation",
    )

    assert result.returncode != 0
    assert result.failed == 3
    assert "test_calculator.py" in result.protected_paths_modified
