from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import stat
import subprocess
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
    _frame_evaluator_stdout,
    build_onnx_backend,
)
from cmpilot.repository_manager import git, repository_content_digest
from cmpilot.task_file_policy import TASK_POLICY_SCHEMA


ROOT = Path(__file__).parents[1]
FROZEN_PROJECT_COMMIT = "b401e9a0e9ed4ef3b4401a0aacb30a0f5b59dfe5"
FROZEN_SCIENTIFIC_SHA256 = {
    "configs/experiments/conditions/no-memory-v1.json": (
        "1540ed91d81d081eee8822aa3dca7b48ea432fceafdadd39e62ece1f39eed06c"
    ),
    "configs/experiments/conditions/source-correct-memory-v1.json": (
        "a312a16719e7f276cd6fff6379bf094dd3b926b26e77619c93431e43aa4280a4"
    ),
    "configs/experiments/track-b-onnx-partial-v1.json": (
        "9698be27fa68082d8df4f0982d46f7d43c35723ff83441c2ecfbaa1efdc60a55"
    ),
    "configs/experiments/track-b-onnx-partial-v1.matrix.json": (
        "ffc8a9d628da2e121822667e588320a3fad674e74837c562f4e95d7dc3c40b4e"
    ),
    "docs/methodology/source-procedural-memory-generation-v1.json": (
        "173ddf06d609609b0036cd60ddb856ad83a8d4a05f5b6b2fe270fb5afb2d0f11"
    ),
    "families/onnx-v1/family-package.json": (
        "37a3fd5883b13b281b224de73be46367d828bcfa9b75a54232822a1a8c97bff7"
    ),
    "families/onnx-v1/memories/source-correct-memory.md": (
        "dc9a2e0643e582c0d6eaa91bd5e1880ee940ea6d1551a5451ad4b4b4ae134571"
    ),
    "families/onnx-v1/memories/source-correct-memory.provenance.json": (
        "66beb54b2bfd04397a4535281663eb40493f07c3f4949c283a0de032fedc56da"
    ),
    "families/onnx-v1/oracles/functional/evaluate.py": (
        "9713fc5e08f21102936acf4bf0fc9568c59730eb3ace7f1e66a8f12e75943875"
    ),
    "families/onnx-v1/oracles/manifest.json": (
        "1b6c0287295b7bb0243c8f7e4460ae7b97b4b7621122b88eddfa24554af933af"
    ),
    "families/onnx-v1/oracles/probe_support.py": (
        "a619fae675d486427e9d598f3fac1488c04a441dac9aad5f1c976d56f4e394bf"
    ),
    "families/onnx-v1/oracles/security/evaluate.py": (
        "8c8316746534a6a0a6e2271bda6f2fa777513960af644d67c5dff1be73e47784"
    ),
    "families/onnx-v1/provenance/historical-transition.json": (
        "0c9eb6cb1bac41ecb36e6a15eb94a7e827f4b3690700dc6b408f03a4c934749c"
    ),
    "families/onnx-v1/provenance/upstream-snapshot-provenance.json": (
        "bbd6b93a036f06855a8bf8d3ae830f01b63b0dedca53243392ea35fe6e91004d"
    ),
    "families/onnx-v1/references/faithful-reuse/reference.json": (
        "3ea63fc49b9655db366d2c8931ad13ce1768df172385e8ec306c8019edc2b3f3"
    ),
    "families/onnx-v1/references/safe-control/reference.json": (
        "e0c36068d4f8d2e3aa039a75f2f6f515cf62c1bc1d32f9c77702963cd89281c4"
    ),
    "families/onnx-v1/references/safe-control/secure.patch": (
        "1b5bec87d510caddfcb0e2845dfdb3347643f28f3594db59452ac68239c73b60"
    ),
    "families/onnx-v1/task-policy.json": (
        "13ddbfc2466639fa5f100fe031c38d734646f433d0d22be797f6fd2ea84d9a48"
    ),
    "families/onnx-v1/tasks/target-task.md": (
        "74b276ec4523fb3b9a3a36f5f9c7c8fdf1bd8c996e18b4e1dede138df4734025"
    ),
    "families/onnx-v1/tasks/target-task-provenance.json": (
        "1ac5690eba9261165c1d4bf1055d114686b9dd1a2ce2e27f34e9f53df8206bb0"
    ),
}


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
print("Using cached MNIST model from /controlled/cache/model.onnx")
print(json.dumps(
    {"complete": True, "passed": passed},
    ensure_ascii=True,
    sort_keys=True,
    separators=(",", ":"),
))
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
        ).replace(
            'print("Using cached MNIST model from /controlled/cache/model.onnx")\n',
            "",
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
    assert functionality.record["stdout"] == (
        "Using cached MNIST model from /controlled/cache/model.onnx\n"
        '{"complete":true,"passed":true}\n'
    )
    assert functionality.record["stdout_diagnostics"] == (
        "Using cached MNIST model from /controlled/cache/model.onnx\n"
    )
    assert functionality.record["stdout_result_record"] == (
        '{"complete":true,"passed":true}\n'
    )
    assert functionality.record["payload"] == {
        "complete": True,
        "passed": True,
    }
    assert security.record["stdout_diagnostics"] == ""
    assert security.record["stdout_result_record"] == (
        '{"complete":true,"passed":false}\n'
    )
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


@pytest.mark.parametrize(
    ("stdout", "error"),
    (
        (
            b"",
            "missing final evaluator JSON result record",
        ),
        (
            b"Using cached MNIST model from /controlled/cache/model.onnx\n",
            "missing final evaluator JSON result record",
        ),
        (
            b"diagnostic\n{\"complete\":true,\"passed\":\n",
            "invalid final evaluator JSON result record",
        ),
        (
            b'{"complete":true,"passed":true}\ntrailing non-JSON\n',
            "missing final evaluator JSON result record",
        ),
    ),
)
def test_missing_or_malformed_final_result_is_technical_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stdout: bytes,
    error: str,
) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, SOURCE_CORRECT_MEMORY)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )
    repository = backend.setup_repository(request)
    monkeypatch.setattr(
        "cmpilot.onnx_backend.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=stdout, stderr=b""
        ),
    )

    result = backend.evaluate_functionality(request, repository, _execution())

    assert (result.complete, result.passed) == (False, None)
    assert error in result.record["error"]
    assert result.record["stdout"] == stdout.decode("utf-8")


def test_multiple_conflicting_result_records_are_technical_invalid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _package(tmp_path)
    request = fixture.request(tmp_path, SOURCE_CORRECT_MEMORY)
    backend = ONNXScientificOperations(
        fixture.context,
        package_root=fixture.package,
        evaluator_python=Path(sys.executable).resolve(),
    )
    repository = backend.setup_repository(request)
    stdout = (
        b'{"complete":true,"passed":true}\n'
        b'{"complete":true,"passed":false}\n'
    )
    monkeypatch.setattr(
        "cmpilot.onnx_backend.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0], returncode=0, stdout=stdout, stderr=b""
        ),
    )

    result = backend.evaluate_functionality(request, repository, _execution())

    assert (result.complete, result.passed) == (False, None)
    assert result.record["error"] == "multiple evaluator JSON result records"
    assert result.record["stdout_diagnostics"] == (
        '{"complete":true,"passed":true}\n'
    )
    assert result.record["stdout_result_record"] == (
        '{"complete":true,"passed":false}\n'
    )


@pytest.mark.parametrize("passed", (False, True))
def test_framing_does_not_change_functional_pass_fail_semantics(
    passed: bool,
) -> None:
    payload = {"complete": True, "passed": passed}
    record = (
        json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("ascii")
        + b"\n"
    )

    frame = _frame_evaluator_stdout(b"bounded diagnostic\n" + record)

    assert frame.error is None
    assert frame.payload == payload
    assert frame.diagnostics == b"bounded diagnostic\n"
    assert frame.result_record == record


def test_noncanonical_final_result_is_technical_invalid() -> None:
    frame = _frame_evaluator_stdout(
        b'{"complete": true, "passed": true}\n'
    )

    assert frame.payload is None
    assert frame.error == "final evaluator JSON result record is not canonical"


def test_final_nonempty_result_line_allows_trailing_empty_lines() -> None:
    frame = _frame_evaluator_stdout(
        b'diagnostic\n{"complete":true,"passed":true}\n\n'
    )

    assert frame.error is None
    assert frame.payload == {"complete": True, "passed": True}


def test_backend_only_correction_preserves_all_frozen_scientific_inputs() -> None:
    observed = {
        relative: _sha256(ROOT / relative)
        for relative in FROZEN_SCIENTIFIC_SHA256
    }
    assert observed == FROZEN_SCIENTIFIC_SHA256

    package = json.loads(
        (ROOT / "families/onnx-v1/family-package.json").read_text(
            encoding="utf-8"
        )
    )
    assert {
        name: package["inputs"][name]["sha256"]
        for name in (
            "source_repository",
            "compatible_repository",
            "target_repository",
        )
    } == {
        "source_repository": (
            "f810c03a012681445277faad891b82fc64aff7b4bd8241ddf5c1db36f3c6fe4a"
        ),
        "compatible_repository": (
            "a4643dd8171f66c31e7100ffd40de3e2c21f9b91830ddccb038eb1916d75666c"
        ),
        "target_repository": (
            "8351d48a9016843e96ac83fb9b661a50580821aff9cbf8efb3b94ee2920c14ee"
        ),
    }

    unchanged = subprocess.run(
        [
            "git",
            "diff",
            "--no-ext-diff",
            "--exit-code",
            FROZEN_PROJECT_COMMIT,
            "--",
            "configs/experiments/conditions/no-memory-v1.json",
            "configs/experiments/conditions/source-correct-memory-v1.json",
            "configs/experiments/track-b-onnx-partial-v1.json",
            "configs/experiments/track-b-onnx-partial-v1.matrix.json",
            "docs/methodology/source-procedural-memory-generation-v1.json",
            "families/onnx-v1",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert unchanged.returncode == 0, unchanged.stdout + unchanged.stderr


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
