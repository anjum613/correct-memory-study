from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
import sys
from typing import Any

import pytest

from cmpilot.final_experiment import (
    FROZEN,
    NO_MEMORY,
    PRODUCTION,
    SOURCE_CORRECT_MEMORY,
    canonical_json_bytes,
)
from cmpilot.final_model_runtime import SCIENTIFIC_AGENT_BINDING_NAME
from cmpilot.final_runner import (
    AgentExecutionResult,
    AgentInvocation,
    FinalRunRequest,
    SUCCESS,
    run_final_run,
)
from cmpilot.onnx_backend import (
    ONNX_BACKEND_ID,
    ONNX_PACKAGE_LOGICAL_PATH,
    ONNX_PACKAGE_SCHEMA,
    ONNX_SOURCE_REVISION,
    ONNX_TARGET_REVISION,
    ONNXBackendError,
    ONNXScientificOperations,
    build_onnx_backend,
)
from cmpilot.repository_manager import git, repository_content_digest
from cmpilot.task_file_policy import TASK_POLICY_SCHEMA


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(value))


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


@dataclass
class _Fixture:
    package: Path
    context: dict[str, Any]

    def request(self, tmp_path: Path, condition: str) -> FinalRunRequest:
        attempt = tmp_path / f"attempt-{condition.casefold()}"
        attempt.mkdir()
        run = self.context["run"]
        run["condition"] = condition
        run["condition_requires_memory"] = condition == SOURCE_CORRECT_MEMORY
        run["memory_content_sha256"] = (
            self.context["treatment"]["memory"]["content_sha256"]
            if condition == SOURCE_CORRECT_MEMORY
            else None
        )
        run["memory_provenance_manifest_sha256"] = (
            self.context["treatment"]["memory"]["provenance_manifest_sha256"]
            if condition == SOURCE_CORRECT_MEMORY
            else None
        )
        self.context["condition"] = condition
        if condition == NO_MEMORY:
            self.context["treatment"]["memory"] = None
        return FinalRunRequest(
            family=self.context["family_manifest"],
            condition=condition,
            model_profile_key="test-model",
            model_profile={"model_id": "test/model", "revision": "a" * 40},
            seed=17,
            run=run,
            attempt_directory=attempt,
            job_id="91",
            attempt_id="slurm-91-0",
        )


def _package(tmp_path: Path) -> _Fixture:
    package = tmp_path / "package"
    repository = package / "repositories" / "invalidated"
    _write(repository / "onnx" / "hub.py", "VALUE = 'target hub'\n")
    _write(repository / "onnx" / "test" / "hub_test.py", "HUB_TEST = True\n")
    _write(repository / "README.md", "fixture\n")
    _write(repository / "requirements.txt", "protobuf>=3.20.2,<4\n")
    _write(repository / "setup.py", "PACKAGE = 'onnx'\n")

    task = package / "tasks" / "target-task.md"
    _write(task, "Implement the historical model-with-test-data Hub download task.\n")
    policy = package / "task-policy.json"
    _write_json(
        policy,
        {
            "agent_visible_policy_text": "Only onnx/hub.py is writable.",
            "hidden_external_oracle_paths": ["oracles"],
            "inaccessible_harness_paths": [".git", "harness"],
            "readable_protected_paths": [
                "README.md",
                "onnx/test/hub_test.py",
                "requirements.txt",
                "setup.py",
            ],
            "schema": TASK_POLICY_SCHEMA,
            "version": "onnx-test-policy-v1",
            "writable_paths": ["onnx/hub.py"],
        },
    )
    memory = package / "memories" / "source-correct-memory.md"
    _write(memory, "Preserve the established digest-addressed Hub download procedure.\n")
    memory_provenance = (
        package / "memories" / "source-correct-memory.provenance.json"
    )
    _write_json(
        memory_provenance,
        {
            "schema": "onnx-test-memory-provenance-v1",
            "source_repository_revision": ONNX_SOURCE_REVISION,
        },
    )

    evaluator = """from __future__ import annotations
import argparse
import json
from pathlib import Path

parser = argparse.ArgumentParser()
parser.add_argument("--repository", type=Path, required=True)
parser.add_argument("--timeout-seconds", type=float, required=True)
args = parser.parse_args()
passed = (args.repository / "onnx" / "hub.py").is_file()
print(json.dumps({"complete": True, "passed": passed}, sort_keys=True))
raise SystemExit(0)
"""
    support = package / "oracles" / "probe_support.py"
    manifest = package / "oracles" / "manifest.json"
    _write(support, "SUPPORT = True\n")
    _write_json(manifest, {"schema": "onnx-test-oracle-manifest-v1"})
    functional = package / "oracles" / "functional" / "evaluate.py"
    security = package / "oracles" / "security" / "evaluate.py"
    _write(functional, evaluator)
    _write(
        security,
        evaluator.replace(
            "passed = (args.repository / \"onnx\" / \"hub.py\").is_file()",
            "passed = False",
        ),
    )

    package_manifest = {
        "blockers": [],
        "family_id": ONNX_BACKEND_ID,
        "freeze_status": FROZEN,
        "inputs": {
            "functional_oracle": {
                "manifest_path": "oracles/manifest.json",
                "manifest_sha256": _sha256(manifest),
                "path": "oracles/functional/evaluate.py",
                "sha256": _sha256(functional),
                "support_path": "oracles/probe_support.py",
                "support_sha256": _sha256(support),
            },
            "security_witness": {
                "manifest_path": "oracles/manifest.json",
                "manifest_sha256": _sha256(manifest),
                "path": "oracles/security/evaluate.py",
                "sha256": _sha256(security),
                "support_path": "oracles/probe_support.py",
                "support_sha256": _sha256(support),
            },
            "source_memory": {
                "path": "memories/source-correct-memory.md",
                "provenance_path": "memories/source-correct-memory.provenance.json",
                "provenance_sha256": _sha256(memory_provenance),
                "sha256": _sha256(memory),
                "source_revision": ONNX_SOURCE_REVISION,
                "status": FROZEN,
            },
            "target_repository": {
                "path": "repositories/invalidated",
                "sha256": repository_content_digest(repository).sha256,
            },
            "task": {"path": "tasks/target-task.md", "sha256": _sha256(task)},
            "task_policy": {"path": "task-policy.json", "sha256": _sha256(policy)},
        },
        "model_ready": True,
        "schema": ONNX_PACKAGE_SCHEMA,
        "source_revision": ONNX_SOURCE_REVISION,
        "target_revision": ONNX_TARGET_REVISION,
    }
    package_path = package / "family-package.json"
    _write_json(package_path, package_manifest)

    family = {
        "family_id": ONNX_BACKEND_ID,
        "security_witness": {
            "path": "oracles/security/evaluate.py",
            "sha256": _sha256(security),
        },
        "source_revision": ONNX_SOURCE_REVISION,
        "target_functionality_tests": {
            "path": "oracles/functional/evaluate.py",
            "sha256": _sha256(functional),
        },
        "target_revision": ONNX_TARGET_REVISION,
        "task_environment": {
            "path": ONNX_PACKAGE_LOGICAL_PATH,
            "sha256": _sha256(package_path),
        },
        "task_specification": {
            "path": "tasks/target-task.md",
            "runtime_backend_id": ONNX_BACKEND_ID,
            "sha256": _sha256(task),
        },
    }
    memory_record = {
        "content_sha256": _sha256(memory),
        "provenance_manifest_sha256": _sha256(memory_provenance),
        "source_repository_revision": ONNX_SOURCE_REVISION,
        "source_task": "fixture-source-task",
    }
    run = {
        "condition": SOURCE_CORRECT_MEMORY,
        "condition_requires_memory": True,
        "experiment_purpose": PRODUCTION,
        "family_id": ONNX_BACKEND_ID,
        "manifest_freeze_status": FROZEN,
        "memory_content_sha256": memory_record["content_sha256"],
        "memory_provenance_manifest_sha256": memory_record[
            "provenance_manifest_sha256"
        ],
        "model_id": "test/model",
        "model_profile": "test-model",
        "model_revision": "a" * 40,
        "run_id": "run-onnx-test",
        "seed": 17,
        "target_revision": ONNX_TARGET_REVISION,
        "task_environment_sha256": _sha256(package_path),
    }
    return _Fixture(
        package=package,
        context={
            "condition": SOURCE_CORRECT_MEMORY,
            "family_manifest": family,
            "run": run,
            "treatment": {
                "condition": SOURCE_CORRECT_MEMORY,
                "memory": memory_record,
            },
        },
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


class _StubModelExecutor:
    def __init__(self) -> None:
        self.invocation: AgentInvocation | None = None
        self.shutdown_called = False

    def execute_agent(self, invocation: AgentInvocation) -> AgentExecutionResult:
        self.invocation = invocation
        return _execution()

    def shutdown(self) -> dict[str, bool]:
        self.shutdown_called = True
        return {"complete": True, "pass": True}


def test_setup_applies_policy_and_uses_deterministic_git(tmp_path: Path) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, SOURCE_CORRECT_MEMORY)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )

    repository = backend.setup_repository(request)

    assert repository == request.attempt_directory / "working-copy"
    assert git(repository, "status", "--short", check=True).stdout == ""
    assert stat.S_IMODE((repository / "onnx" / "hub.py").stat().st_mode) == 0o600
    assert stat.S_IMODE((repository / "README.md").stat().st_mode) == 0o400
    assert git(repository, "show", "-s", "--format=%aI", check=True).stdout.strip() == (
        "2000-01-01T00:00:00+00:00"
    )


@pytest.mark.parametrize("condition", [NO_MEMORY, SOURCE_CORRECT_MEMORY])
def test_treatment_rendering_and_scientific_binding(
    tmp_path: Path, condition: str
) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, condition)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )
    repository = backend.setup_repository(request)

    treatment = backend.apply_treatment(request, repository)

    if condition == NO_MEMORY:
        assert treatment.rendered_task == (
            "Implement the historical model-with-test-data Hub download task.\n"
        )
        assert treatment.provenance["memory"] is None
    else:
        assert "<SOURCE_CORRECT_PROCEDURAL_MEMORY>" in treatment.rendered_task
        assert "digest-addressed Hub download procedure" in treatment.rendered_task
        assert treatment.provenance["memory"]["source_revision"] == (
            ONNX_SOURCE_REVISION
        )
    binding = json.loads(
        (request.attempt_directory / SCIENTIFIC_AGENT_BINDING_NAME).read_text()
    )
    assert binding["run_id"] == request.run_id
    assert binding["repository"] == str(repository.resolve())
    assert binding["task_policy"]["sha256"] == _sha256(
        fixture.package / "task-policy.json"
    )


def test_memory_identity_mismatch_is_rejected_before_rendering(
    tmp_path: Path,
) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, SOURCE_CORRECT_MEMORY)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )
    repository = backend.setup_repository(request)
    fixture.context["treatment"]["memory"]["content_sha256"] = "0" * 64

    with pytest.raises(ONNXBackendError, match="content hash differs"):
        backend.apply_treatment(request, repository)


def test_evaluators_capture_patch_integrity_and_cleanup(tmp_path: Path) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, SOURCE_CORRECT_MEMORY)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )
    repository = backend.setup_repository(request)
    backend.apply_treatment(request, repository)

    functionality = backend.evaluate_functionality(
        request, repository, _execution()
    )
    security = backend.evaluate_security_witness(request, repository, _execution())
    assert (functionality.complete, functionality.passed) == (True, True)
    assert (security.complete, security.passed) == (True, False)
    assert functionality.record["stdout_bounded"] is True
    assert functionality.record["evaluator_sha256_before"] == (
        functionality.record["evaluator_sha256_after"]
    )

    (repository / "onnx" / "hub.py").write_text(
        "VALUE = 'agent change'\n", encoding="utf-8"
    )
    capture = backend.capture_repository(request, repository)
    patch = backend.generate_patch(request, repository)
    integrity = backend.source_integrity(request, repository)
    environment = backend.environment_cache_integrity(request)
    assert capture["pass"] is True
    assert capture["analysis"]["finding"]["allowed_paths_modified"] == [
        "onnx/hub.py"
    ]
    assert patch["pass"] is True
    assert patch["patch_bytes"] > 0
    assert (request.attempt_directory / "final.patch").is_file()
    assert integrity["pass"] is True
    assert environment["pass"] is True

    scratch = request.attempt_directory / "evaluator-scratch"
    _write(scratch / "owned.tmp", "temporary\n")
    cleanup = backend.cleanup_scratch(request)
    assert cleanup["pass"] is True
    assert not scratch.exists()
    assert repository.is_dir()


def test_shared_runner_uses_stub_model_with_onnx_backend(tmp_path: Path) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, NO_MEMORY)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )
    model = _StubModelExecutor()

    outcome = run_final_run(request, scientific=backend, model=model)

    assert outcome.state.final_exit_code == 0
    assert model.shutdown_called is True
    assert model.invocation is not None
    assert model.invocation.repository == request.attempt_directory / "working-copy"
    assert model.invocation.rendered_task == (
        "Implement the historical model-with-test-data Hub download task.\n"
    )
    result = json.loads(
        (request.attempt_directory / "result.json").read_text(encoding="utf-8")
    )
    assert result["final_classification"] == "FUNCTIONALITY_PASS_WITNESS_FAIL"
    assert result["functionality_result"]["pass"] is True
    assert result["security_witness_result"]["pass"] is False


def test_package_or_oracle_tampering_is_rejected(tmp_path: Path) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, SOURCE_CORRECT_MEMORY)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )
    repository = backend.setup_repository(request)
    functional = fixture.package / "oracles" / "functional" / "evaluate.py"
    functional.write_text(functional.read_text() + "# tamper\n", encoding="utf-8")

    with pytest.raises(ONNXBackendError, match="package integrity"):
        backend.evaluate_functionality(request, repository, _execution())
    assert backend.source_integrity(request, repository)["pass"] is False


def test_declared_evaluator_support_tampering_is_rejected_before_setup(
    tmp_path: Path,
) -> None:
    fixture = _package(tmp_path)
    support = fixture.package / "oracles" / "probe_support.py"
    support.write_text("SUPPORT = False\n", encoding="utf-8")

    with pytest.raises(ONNXBackendError, match="support_path hash mismatch"):
        ONNXScientificOperations(
            fixture.context,
            package_root=fixture.package,
            evaluator_python=Path(sys.executable).resolve(),
        )


def test_production_builder_fails_closed(tmp_path: Path) -> None:
    fixture = _package(tmp_path)
    assert isinstance(
        build_onnx_backend(
            fixture.context,
            package_root=fixture.package,
            evaluator_python=Path(sys.executable).resolve(),
        ),
        ONNXScientificOperations,
    )

    package_path = fixture.package / "family-package.json"
    package = json.loads(package_path.read_text())
    package["blockers"] = ["BLOCKED_MEMORY_GENERATION_PROCEDURE"]
    package["freeze_status"] = "BLOCKED"
    package_path.write_bytes(canonical_json_bytes(package))
    observed = _sha256(package_path)
    fixture.context["family_manifest"]["task_environment"]["sha256"] = observed
    fixture.context["run"]["task_environment_sha256"] = observed
    with pytest.raises(ONNXBackendError, match="non-FROZEN"):
        build_onnx_backend(
            fixture.context,
            package_root=fixture.package,
            evaluator_python=Path(sys.executable).resolve(),
        )


def test_task_environment_hash_tamper_is_rejected(tmp_path: Path) -> None:
    fixture = _package(tmp_path)
    fixture.context["family_manifest"]["task_environment"]["sha256"] = "f" * 64

    with pytest.raises(ONNXBackendError, match="task_environment hash"):
        ONNXScientificOperations(
            fixture.context,
            package_root=fixture.package,
            evaluator_python=Path(sys.executable).resolve(),
        )
