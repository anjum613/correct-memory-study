from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import stat
import subprocess
import sys
import tarfile
from typing import Any

import pytest

from cmpilot.djoser_backend import (
    DJOSER_BACKEND_ID,
    DJOSER_PACKAGE_LOGICAL_PATH,
    DJOSER_SOURCE_REVISION,
    DJOSER_TARGET_REVISION,
    DjoserScientificOperations,
    build_djoser_backend,
)
from cmpilot.final_experiment import FROZEN, PRODUCTION, SOURCE_CORRECT_MEMORY
from cmpilot.final_runner import AgentExecutionResult, FinalRunRequest, SUCCESS
from cmpilot.final_runtime_backends import SCIENTIFIC_BACKENDS
from cmpilot.repository_manager import git


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "families" / DJOSER_BACKEND_ID


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _context(package_root: Path = PACKAGE) -> dict[str, Any]:
    package = json.loads(
        (package_root / "family-package.json").read_text(encoding="utf-8")
    )
    inputs = package["inputs"]
    memory = {
        "content_sha256": inputs["source_memory"]["sha256"],
        "provenance_manifest_sha256": inputs["source_memory"][
            "provenance_sha256"
        ],
        "source_repository_revision": DJOSER_SOURCE_REVISION,
        "source_task": "Add LOGIN_FIELD setting, fixes #389",
    }
    family = {
        "family_id": DJOSER_BACKEND_ID,
        "security_witness": {
            "path": inputs["security_witness"]["path"],
            "sha256": inputs["security_witness"]["sha256"],
        },
        "source_revision": DJOSER_SOURCE_REVISION,
        "target_functionality_tests": {
            "path": inputs["functional_oracle"]["path"],
            "sha256": inputs["functional_oracle"]["sha256"],
        },
        "target_revision": DJOSER_TARGET_REVISION,
        "task_environment": {
            "path": DJOSER_PACKAGE_LOGICAL_PATH,
            "sha256": _sha256(package_root / "family-package.json"),
        },
        "task_specification": {
            "path": inputs["task"]["path"],
            "runtime_backend_id": DJOSER_BACKEND_ID,
            "sha256": inputs["task"]["sha256"],
        },
    }
    run = {
        "condition": SOURCE_CORRECT_MEMORY,
        "condition_requires_memory": True,
        "experiment_purpose": PRODUCTION,
        "family_id": DJOSER_BACKEND_ID,
        "manifest_freeze_status": FROZEN,
        "memory_content_sha256": memory["content_sha256"],
        "memory_provenance_manifest_sha256": memory[
            "provenance_manifest_sha256"
        ],
        "model_id": "test/model",
        "model_profile": "test-model",
        "model_revision": "a" * 40,
        "run_id": "run-djoser-test",
        "seed": 17,
        "target_revision": DJOSER_TARGET_REVISION,
        "task_environment_sha256": _sha256(
            package_root / "family-package.json"
        ),
    }
    return {
        "condition": SOURCE_CORRECT_MEMORY,
        "family_manifest": family,
        "run": run,
        "treatment": {"condition": SOURCE_CORRECT_MEMORY, "memory": memory},
    }


@pytest.fixture
def package_root(tmp_path: Path) -> Path:
    completed = subprocess.run(
        ("git", "archive", "HEAD", "families/djoser-v1"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        timeout=30,
    )
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        archive.extractall(tmp_path, filter="data")
    return tmp_path / "families/djoser-v1"


def _request(context: dict[str, Any], attempt: Path) -> FinalRunRequest:
    attempt.mkdir()
    return FinalRunRequest(
        family=context["family_manifest"],
        condition=SOURCE_CORRECT_MEMORY,
        model_profile_key="test-model",
        model_profile={"model_id": "test/model", "revision": "a" * 40},
        seed=17,
        run=context["run"],
        attempt_directory=attempt,
        job_id="91",
        attempt_id="slurm-91-0",
    )


def _execution() -> AgentExecutionResult:
    return AgentExecutionResult(
        termination_reason=SUCCESS,
        technical_validity=True,
        action_count=0,
        model_request_count=0,
        elapsed_seconds=0.1,
        token_usage=None,
        record={"fixture": True},
    )


def test_registry_constructs_exact_frozen_djoser_backend(
    package_root: Path,
) -> None:
    context = _context(package_root)

    assert SCIENTIFIC_BACKENDS[DJOSER_BACKEND_ID] is build_djoser_backend
    backend = build_djoser_backend(
        context,
        package_root=package_root,
        evaluator_python=Path(sys.executable).resolve(),
    )

    assert isinstance(backend, DjoserScientificOperations)
    assert backend.package["model_ready"] is True
    assert backend.package["blockers"] == []


def test_runtime_applies_policy_memory_and_frozen_reference_contrast(
    tmp_path: Path, package_root: Path,
) -> None:
    context = _context(package_root)
    request = _request(context, tmp_path / "attempt")
    backend = DjoserScientificOperations(
        context,
        package_root=package_root,
        evaluator_python=Path(sys.executable).resolve(),
    )

    repository = backend.setup_repository(request)
    treatment = backend.apply_treatment(request, repository)
    functional = backend.evaluate_functionality(request, repository, _execution())
    security = backend.evaluate_security_witness(request, repository, _execution())

    assert git(repository, "status", "--short", check=True).stdout == ""
    assert stat.S_IMODE((repository / "djoser/serializers.py").stat().st_mode) == 0o600
    assert stat.S_IMODE((repository / "CHANGELOG.rst").stat().st_mode) == 0o400
    assert "<SOURCE_CORRECT_PROCEDURAL_MEMORY>" in treatment.rendered_task
    assert (functional.complete, functional.passed) == (True, True)
    assert (security.complete, security.passed) == (True, False)
    assert security.record["payload"]["observations"] == {
        "backend_calls": 1,
        "direct_lookup_calls": 1,
        "password_check_calls": 1,
        "token_procedure_accepted": True,
    }


def test_actual_package_input_hashes_are_bound(package_root: Path) -> None:
    package = json.loads(
        (package_root / "family-package.json").read_text(encoding="utf-8")
    )

    for name in ("functional_oracle", "security_witness", "task", "task_policy"):
        record = package["inputs"][name]
        assert _sha256(package_root / record["path"]) == record["sha256"]
