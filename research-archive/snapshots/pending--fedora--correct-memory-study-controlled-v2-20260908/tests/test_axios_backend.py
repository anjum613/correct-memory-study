from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from cmpilot.axios_backend import (
    AXIOS_BACKEND_ID,
    AXIOS_DEFAULT_NODE,
    AXIOS_NODE_SHA256,
    AXIOS_PACKAGE_LOGICAL_PATH,
    AXIOS_PACKAGE_ROOT,
    AXIOS_SOURCE_REVISION,
    AXIOS_TARGET_REVISION,
    AxiosBackendError,
    AxiosScientificOperations,
    build_axios_backend,
)
from cmpilot.final_experiment import FROZEN, NO_MEMORY, PRODUCTION, SOURCE_CORRECT_MEMORY
from cmpilot.final_runner import (
    AgentExecutionResult,
    AgentInvocation,
    FinalRunRequest,
    SUCCESS,
    run_final_run,
)
from cmpilot.final_runtime_backends import SCIENTIFIC_BACKENDS


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _context(condition: str) -> dict[str, Any]:
    package = json.loads((AXIOS_PACKAGE_ROOT / "family-package.json").read_text())
    inputs = package["inputs"]
    memory = {
        "content_sha256": inputs["source_memory"]["sha256"],
        "provenance_manifest_sha256": inputs["source_memory"]["provenance_sha256"],
        "source_repository_revision": AXIOS_SOURCE_REVISION,
        "source_task": "Use WHATWG URL API instead of url.parse() (#4852)",
    }
    family = {
        "family_id": AXIOS_BACKEND_ID,
        "security_witness": {
            "path": inputs["security_witness"]["path"],
            "sha256": inputs["security_witness"]["sha256"],
        },
        "source_revision": AXIOS_SOURCE_REVISION,
        "target_functionality_tests": {
            "path": inputs["functional_oracle"]["path"],
            "sha256": inputs["functional_oracle"]["sha256"],
        },
        "target_revision": AXIOS_TARGET_REVISION,
        "task_environment": {
            "path": AXIOS_PACKAGE_LOGICAL_PATH,
            "sha256": _sha256(AXIOS_PACKAGE_ROOT / "family-package.json"),
        },
        "task_specification": {
            "path": inputs["task"]["path"],
            "runtime_backend_id": AXIOS_BACKEND_ID,
            "sha256": inputs["task"]["sha256"],
        },
    }
    run = {
        "condition": condition,
        "condition_requires_memory": condition == SOURCE_CORRECT_MEMORY,
        "experiment_purpose": PRODUCTION,
        "family_id": AXIOS_BACKEND_ID,
        "manifest_freeze_status": FROZEN,
        "memory_content_sha256": memory["content_sha256"] if condition == SOURCE_CORRECT_MEMORY else None,
        "memory_provenance_manifest_sha256": memory["provenance_manifest_sha256"] if condition == SOURCE_CORRECT_MEMORY else None,
        "model_id": "test/model",
        "model_profile": "test-model",
        "model_revision": "a" * 40,
        "run_id": f"run-axios-test-{condition.casefold()}",
        "seed": 17,
        "target_revision": AXIOS_TARGET_REVISION,
        "task_environment_sha256": family["task_environment"]["sha256"],
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


def _request(context: dict[str, Any], attempt: Path) -> FinalRunRequest:
    attempt.mkdir()
    run = context["run"]
    return FinalRunRequest(
        family=context["family_manifest"],
        condition=run["condition"],
        model_profile_key="test-model",
        model_profile={"model_id": "test/model", "revision": "a" * 40},
        seed=17,
        run=run,
        attempt_directory=attempt,
        job_id="91",
        attempt_id="slurm-91-0",
    )


def _execution() -> AgentExecutionResult:
    return AgentExecutionResult(
        termination_reason=SUCCESS,
        technical_validity=True,
        action_count=1,
        model_request_count=1,
        elapsed_seconds=0.1,
        token_usage=None,
        record={"fixture": True},
    )


@dataclass
class _StubModelExecutor:
    invocation: AgentInvocation | None = None
    shutdown_called: bool = False

    def execute_agent(self, invocation: AgentInvocation) -> AgentExecutionResult:
        self.invocation = invocation
        return _execution()

    def shutdown(self) -> dict[str, bool]:
        self.shutdown_called = True
        return {"complete": True, "pass": True}


@pytest.mark.parametrize("condition", [NO_MEMORY, SOURCE_CORRECT_MEMORY])
def test_frozen_backend_treatment_and_evaluators(tmp_path: Path, condition: str) -> None:
    context = _context(condition)
    request = _request(context, tmp_path / "attempt")
    backend = AxiosScientificOperations(context)
    repository = backend.setup_repository(request)

    treatment = backend.apply_treatment(request, repository)
    functionality = backend.evaluate_functionality(request, repository, _execution())
    security = backend.evaluate_security_witness(request, repository, _execution())

    assert functionality.complete is True and functionality.passed is True
    assert security.complete is True and security.passed is False
    if condition == NO_MEMORY:
        assert treatment.provenance["memory"] is None
    else:
        assert "<SOURCE_CORRECT_PROCEDURAL_MEMORY>" in treatment.rendered_task
        assert treatment.provenance["memory"]["source_revision"] == AXIOS_SOURCE_REVISION
    assert backend.environment_cache_integrity(request)["pass"] is True


def test_shared_runner_with_dummy_model_executor(tmp_path: Path) -> None:
    context = _context(NO_MEMORY)
    request = _request(context, tmp_path / "attempt")
    backend = AxiosScientificOperations(context)
    model = _StubModelExecutor()

    outcome = run_final_run(request, scientific=backend, model=model)

    assert outcome.state.final_exit_code == 0
    assert model.shutdown_called is True
    assert model.invocation is not None
    result = json.loads((request.attempt_directory / "result.json").read_text())
    assert result["final_classification"] == "FUNCTIONALITY_PASS_WITNESS_FAIL"
    assert result["functionality_result"]["pass"] is True
    assert result["security_witness_result"]["pass"] is False


def test_registry_and_node_binding_fail_closed(tmp_path: Path) -> None:
    assert SCIENTIFIC_BACKENDS[AXIOS_BACKEND_ID] is build_axios_backend
    assert _sha256(AXIOS_DEFAULT_NODE) == AXIOS_NODE_SHA256
    context = _context(NO_MEMORY)
    bad_node = tmp_path / "node"
    bad_node.write_bytes(AXIOS_DEFAULT_NODE.read_bytes()[:1024])
    bad_node.chmod(0o700)
    with pytest.raises(AxiosBackendError, match="hash mismatch"):
        AxiosScientificOperations(context, node_executable=bad_node)
