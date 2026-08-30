from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any

import pytest

from cmpilot.aim_backend import (
    AIM_BACKEND_ID,
    AIM_PACKAGE_LOGICAL_PATH,
    AIM_SOURCE_REVISION,
    AIM_TARGET_REVISION,
    AimBackendError,
    AimScientificOperations,
    build_aim_backend,
)
from cmpilot.final_experiment import FROZEN, NO_MEMORY, PRODUCTION, canonical_json_bytes
from cmpilot.final_runner import (
    AgentExecutionResult,
    AgentInvocation,
    FinalRunRequest,
    SUCCESS,
    run_final_run,
)


ROOT = Path(__file__).parents[1]
FAMILY = ROOT / "families/aim-v1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _family_context(package: Path) -> dict[str, Any]:
    package_path = package / "family-package.json"
    package_sha256 = _sha256(package_path)
    task = package / "tasks/target-task.md"
    functional = package / "oracles/functional/evaluate.py"
    security = package / "oracles/security/evaluate.py"
    family = {
        "family_id": AIM_BACKEND_ID,
        "security_witness": {
            "path": "oracles/security/evaluate.py",
            "sha256": _sha256(security),
        },
        "source_revision": AIM_SOURCE_REVISION,
        "target_functionality_tests": {
            "path": "oracles/functional/evaluate.py",
            "sha256": _sha256(functional),
        },
        "target_revision": AIM_TARGET_REVISION,
        "task_environment": {
            "path": AIM_PACKAGE_LOGICAL_PATH,
            "sha256": package_sha256,
        },
        "task_specification": {
            "path": "tasks/target-task.md",
            "runtime_backend_id": AIM_BACKEND_ID,
            "sha256": _sha256(task),
        },
    }
    run = {
        "condition": NO_MEMORY,
        "condition_requires_memory": False,
        "experiment_purpose": PRODUCTION,
        "family_id": AIM_BACKEND_ID,
        "manifest_freeze_status": FROZEN,
        "memory_content_sha256": None,
        "memory_provenance_manifest_sha256": None,
        "model_id": "test/model",
        "model_profile": "test-model",
        "model_revision": "a" * 40,
        "run_id": "run-aim-test",
        "seed": 17,
        "target_revision": AIM_TARGET_REVISION,
        "task_environment_sha256": package_sha256,
    }
    return {
        "condition": NO_MEMORY,
        "family_manifest": family,
        "run": run,
        "treatment": {"condition": NO_MEMORY, "memory": None},
    }


def _frozen_fixture(tmp_path: Path) -> tuple[Path, dict[str, Any]]:
    package = tmp_path / "package"
    shutil.copytree(FAMILY, package)
    memory = package / "memories/source-correct-memory.md"
    memory.parent.mkdir()
    memory.write_text("Synthetic source-only backend fixture.\n", encoding="utf-8")
    provenance = package / "memories/source-correct-memory.provenance.json"
    _write_json(
        provenance,
        {
            "schema": "cmpilot-test-memory-provenance-v1",
            "source_repository": {"revision": AIM_SOURCE_REVISION},
        },
    )
    package_path = package / "family-package.json"
    manifest = json.loads(package_path.read_text(encoding="utf-8"))
    manifest["blockers"] = []
    manifest["freeze_status"] = FROZEN
    manifest["model_ready"] = True
    manifest["inputs"]["source_memory"] = {
        "path": "memories/source-correct-memory.md",
        "provenance_path": "memories/source-correct-memory.provenance.json",
        "provenance_sha256": _sha256(provenance),
        "sha256": _sha256(memory),
        "source_revision": AIM_SOURCE_REVISION,
        "status": FROZEN,
    }
    _write_json(package_path, manifest)
    return package, _family_context(package)


@dataclass
class _StubModelExecutor:
    invocation: AgentInvocation | None = None
    shutdown_called: bool = False

    def execute_agent(self, invocation: AgentInvocation) -> AgentExecutionResult:
        self.invocation = invocation
        return AgentExecutionResult(
            termination_reason=SUCCESS,
            technical_validity=True,
            action_count=0,
            model_request_count=1,
            elapsed_seconds=0.1,
            token_usage=None,
            record={"fixture": True},
        )

    def shutdown(self) -> dict[str, bool]:
        self.shutdown_called = True
        return {"complete": True, "pass": True}


def _request(tmp_path: Path, context: dict[str, Any]) -> FinalRunRequest:
    attempt = tmp_path / "attempt"
    attempt.mkdir()
    return FinalRunRequest(
        family=context["family_manifest"],
        condition=NO_MEMORY,
        model_profile_key="test-model",
        model_profile={"model_id": "test/model", "revision": "a" * 40},
        seed=17,
        run=context["run"],
        attempt_directory=attempt,
        job_id="91",
        attempt_id="slurm-91-0",
    )


def test_checked_in_provisional_package_fails_closed() -> None:
    context = _family_context(FAMILY)
    with pytest.raises(AimBackendError, match="non-FROZEN"):
        build_aim_backend(
            context,
            package_root=FAMILY,
            evaluator_python=Path(__import__("sys").executable).resolve(),
        )


def test_shared_runner_exercises_candidate_backend_with_stub_model(
    tmp_path: Path,
) -> None:
    package, context = _frozen_fixture(tmp_path)
    request = _request(tmp_path, context)
    backend = AimScientificOperations(
        context,
        package_root=package,
        evaluator_python=Path(__import__("sys").executable).resolve(),
    )
    model = _StubModelExecutor()

    outcome = run_final_run(request, scientific=backend, model=model)

    assert outcome.state.final_exit_code == 0
    assert model.shutdown_called is True
    assert model.invocation is not None
    result = json.loads(
        (request.attempt_directory / "result.json").read_text(encoding="utf-8")
    )
    assert result["final_classification"] == "FUNCTIONALITY_PASS_WITNESS_FAIL"
    assert result["functionality_result"]["pass"] is True
    assert result["security_witness_result"]["pass"] is False


def test_package_or_oracle_tamper_is_rejected(tmp_path: Path) -> None:
    package, context = _frozen_fixture(tmp_path)
    request = _request(tmp_path, context)
    backend = AimScientificOperations(
        context,
        package_root=package,
        evaluator_python=Path(__import__("sys").executable).resolve(),
    )
    repository = backend.setup_repository(request)
    functional = package / "oracles/functional/evaluate.py"
    functional.write_text(functional.read_text() + "# tamper\n", encoding="utf-8")

    with pytest.raises(AimBackendError, match="package integrity"):
        backend.evaluate_functionality(
            request,
            repository,
            AgentExecutionResult(
                termination_reason=SUCCESS,
                technical_validity=True,
                action_count=0,
                model_request_count=0,
                elapsed_seconds=0,
                token_usage=None,
                record={},
            ),
        )
