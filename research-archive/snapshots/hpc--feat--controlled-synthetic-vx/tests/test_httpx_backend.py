from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from cmpilot.final_experiment import FROZEN, NO_MEMORY, PRODUCTION, SOURCE_CORRECT_MEMORY
from cmpilot.final_runner import AgentExecutionResult, FinalRunRequest, SUCCESS
from cmpilot.final_runtime_backends import SCIENTIFIC_BACKENDS
from cmpilot.httpx_backend import (
    HTTPX_BACKEND_ID,
    HTTPX_PACKAGE_LOGICAL_PATH,
    HTTPX_SOURCE_REVISION,
    HTTPX_TARGET_REVISION,
    HTTPXBackendError,
    HTTPXScientificOperations,
    build_httpx_backend,
)
from cmpilot.qualification import sha256_file
from cmpilot.repository_manager import copy_repository_tree


ROOT = Path(__file__).parents[1]
PACKAGE = ROOT / "families/httpx-v1"


def _context(package: Path, condition: str) -> dict[str, object]:
    package_sha256 = sha256_file(package / "family-package.json")
    memory_sha256 = sha256_file(package / "memories/source-correct-memory.md")
    provenance_sha256 = sha256_file(
        package / "memories/source-correct-memory-provenance.json"
    )
    memory = {
        "content_sha256": memory_sha256,
        "provenance_manifest_sha256": provenance_sha256,
        "source_repository_revision": HTTPX_SOURCE_REVISION,
        "source_task": "added authority copy feature in URL.copy_with (#436)",
    }
    family = {
        "family_id": HTTPX_BACKEND_ID,
        "security_witness": {
            "path": "families/httpx-v1/oracles/security/evaluate.py",
            "sha256": sha256_file(package / "oracles/security/evaluate.py"),
        },
        "source_revision": HTTPX_SOURCE_REVISION,
        "target_functionality_tests": {
            "path": "families/httpx-v1/oracles/functional/evaluate.py",
            "sha256": sha256_file(package / "oracles/functional/evaluate.py"),
        },
        "target_revision": HTTPX_TARGET_REVISION,
        "task_environment": {
            "path": HTTPX_PACKAGE_LOGICAL_PATH,
            "sha256": package_sha256,
        },
        "task_specification": {
            "path": "families/httpx-v1/tasks/target-task.md",
            "runtime_backend_id": HTTPX_BACKEND_ID,
            "sha256": sha256_file(package / "tasks/target-task.md"),
        },
    }
    run = {
        "condition": condition,
        "experiment_purpose": PRODUCTION,
        "family_id": HTTPX_BACKEND_ID,
        "manifest_freeze_status": FROZEN,
        "memory_content_sha256": memory_sha256 if condition == SOURCE_CORRECT_MEMORY else None,
        "memory_provenance_manifest_sha256": provenance_sha256 if condition == SOURCE_CORRECT_MEMORY else None,
        "model_id": "test/model",
        "model_profile": "test-model",
        "model_revision": "a" * 40,
        "run_id": f"run-httpx-{condition.casefold()}",
        "seed": 17,
        "target_revision": HTTPX_TARGET_REVISION,
        "task_environment_sha256": package_sha256,
    }
    return {
        "condition": condition,
        "family_manifest": family,
        "run": run,
        "treatment": {
            "condition": condition,
            "memory": memory if condition == SOURCE_CORRECT_MEMORY else None,
        },
    }


def _request(context: dict[str, object], tmp_path: Path) -> FinalRunRequest:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    return FinalRunRequest(
        family=context["family_manifest"],
        condition=str(context["condition"]),
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
        model_request_count=1,
        elapsed_seconds=0.1,
        token_usage=None,
        record={"test": True},
    )


@pytest.mark.parametrize("condition", [NO_MEMORY, SOURCE_CORRECT_MEMORY])
def test_real_frozen_package_runs_shared_lifecycle(
    tmp_path: Path, condition: str
) -> None:
    context = _context(PACKAGE, condition)
    request = _request(context, tmp_path)
    backend = HTTPXScientificOperations(
        context, package_root=PACKAGE, evaluator_python=Path(sys.executable)
    )
    repository = backend.setup_repository(request)
    treatment = backend.apply_treatment(request, repository)
    functionality = backend.evaluate_functionality(request, repository, _execution())
    security = backend.evaluate_security_witness(request, repository, _execution())

    assert treatment.provenance["family_id"] == HTTPX_BACKEND_ID
    assert ("<SOURCE_CORRECT_PROCEDURAL_MEMORY>" in treatment.rendered_task) == (
        condition == SOURCE_CORRECT_MEMORY
    )
    assert (functionality.complete, functionality.passed) == (True, True)
    assert (security.complete, security.passed) == (True, False)
    assert backend.source_integrity(request, repository)["pass"] is True
    assert backend.environment_cache_integrity(request)["pass"] is True
    assert backend.cleanup_scratch(request)["pass"] is True


def test_registry_binds_exact_httpx_builder() -> None:
    assert SCIENTIFIC_BACKENDS[HTTPX_BACKEND_ID] is build_httpx_backend


def test_task_environment_hash_tamper_is_rejected(tmp_path: Path) -> None:
    package = tmp_path / "package"
    copy_repository_tree(PACKAGE, package)
    context = _context(package, NO_MEMORY)
    context["family_manifest"]["task_environment"]["sha256"] = "0" * 64
    with pytest.raises(HTTPXBackendError, match="task_environment hash"):
        HTTPXScientificOperations(
            context, package_root=package, evaluator_python=Path(sys.executable)
        )
