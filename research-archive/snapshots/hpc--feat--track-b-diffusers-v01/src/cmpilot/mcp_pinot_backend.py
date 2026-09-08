"""Candidate-specific scientific runtime for the frozen MCP Pinot family."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

from .final_experiment import (
    FROZEN,
    NO_MEMORY,
    PRODUCTION,
    SOURCE_CORRECT_MEMORY,
    canonical_json_bytes,
)
from .final_model_runtime import write_scientific_agent_binding
from .final_runner import (
    AgentExecutionResult,
    EvaluationResult,
    FinalRunRequest,
    TreatmentApplication,
)
from .post_agent_pipeline import analyze_task_repository
from .qualification import (
    load_task_policy,
    prepare_qualification_working_copy,
    sha256_file,
)
from .qualification_runner import _safe_remove_scratch
from .repository_manager import (
    RepositoryContentDigest,
    final_patch,
    git,
    repository_content_digest,
    repository_preparation_record,
)
from .task_file_policy import (
    ProtectedPathState,
    TaskFilePolicy,
    capture_protected_path_state,
    check_protected_path_integrity,
)


MCP_PINOT_BACKEND_ID = "mcp-pinot-v1"
MCP_PINOT_PACKAGE_SCHEMA = "cmpilot-mcp-pinot-family-package-v1"
MCP_PINOT_PACKAGE_ROOT = (
    Path(__file__).parents[2] / "families" / MCP_PINOT_BACKEND_ID
)
MCP_PINOT_PACKAGE_LOGICAL_PATH = (
    "families/mcp-pinot-v1/family-package.json"
)
MCP_PINOT_SOURCE_REVISION = "6938a35892481d95627cae5a16ad1814e3b49c53"
MCP_PINOT_TARGET_REVISION = "160c456ed7e502e68d0c33fbce4c581267bf926e"

_PACKAGE_FILE = "family-package.json"
_TARGET_REPOSITORY = "repositories/invalidated"
_TASK_FILE = "tasks/target-task.md"
_TASK_POLICY_FILE = "task-policy.json"
_FUNCTIONAL_ORACLE = "oracles/functional/evaluate.py"
_SECURITY_WITNESS = "oracles/security/evaluate.py"
_MEMORY_FILE = "memories/source-correct-memory.md"
_MEMORY_PROVENANCE_FILE = "memories/source-correct-memory-provenance.json"
_MEMORY_WRAPPER_START = "<SOURCE_CORRECT_PROCEDURAL_MEMORY>"
_MEMORY_WRAPPER_END = "</SOURCE_CORRECT_PROCEDURAL_MEMORY>"
_EVALUATOR_INTERNAL_TIMEOUT_SECONDS = 5.0
_EVALUATOR_PROCESS_TIMEOUT_SECONDS = 30.0
_MAX_EVALUATOR_OUTPUT_BYTES = 16_384


class MCPPinotBackendError(RuntimeError):
    """A frozen MCP Pinot package or runtime invariant failed."""


@dataclass
class _AttemptState:
    request_run_id: str
    repository: Path
    initial_commit: str
    policy: TaskFilePolicy
    protected_baseline: tuple[ProtectedPathState, ...]
    preparation: Mapping[str, Any]
    binding_sha256: str | None = None


def _load_canonical_json(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeDecodeError, ValueError) as error:
        raise MCPPinotBackendError(f"invalid JSON input {path}: {error}") from error
    if not isinstance(value, dict):
        raise MCPPinotBackendError(f"expected a JSON object: {path}")
    if canonical_json_bytes(value) != payload:
        raise MCPPinotBackendError(f"JSON input is not canonical: {path}")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise MCPPinotBackendError(f"{label} must be an object")
    return value


def _bounded_text(payload: bytes) -> tuple[str, bool]:
    bounded = payload[:_MAX_EVALUATOR_OUTPUT_BYTES]
    return bounded.decode("utf-8", errors="replace"), len(payload) <= len(bounded)


def _write_new_bytes(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise MCPPinotBackendError(
            f"refusing to overwrite attempt artifact: {path}"
        ) from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


class MCPPinotScientificOperations:
    """Implement ``ScientificOperations`` for only ``mcp-pinot-v1``."""

    def __init__(
        self,
        context: Mapping[str, Any],
        *,
        package_root: Path = MCP_PINOT_PACKAGE_ROOT,
        evaluator_python: Path | None = None,
    ) -> None:
        self._context = _mapping(context, "run context")
        supplied_package_root = Path(package_root)
        if supplied_package_root.is_symlink():
            raise MCPPinotBackendError(
                f"package root must be a real directory: {supplied_package_root}"
            )
        self.package_root = supplied_package_root.resolve(strict=True)
        if not self.package_root.is_dir():
            raise MCPPinotBackendError(
                f"package root must be a real directory: {self.package_root}"
            )
        self.package_path = self._fixed_file(_PACKAGE_FILE)
        self.package = _load_canonical_json(self.package_path)
        self.family = _mapping(
            self._context.get("family_manifest"), "context.family_manifest"
        )
        self._validate_production_binding()
        self._validate_package_inputs()

        self.source_repository = self._fixed_directory(_TARGET_REPOSITORY)
        self.task_path = self._fixed_file(_TASK_FILE)
        self.task_policy_path = self._fixed_file(_TASK_POLICY_FILE)
        self.functional_oracle_path = self._fixed_file(_FUNCTIONAL_ORACLE)
        self.security_witness_path = self._fixed_file(_SECURITY_WITNESS)
        self.policy = load_task_policy(self.task_policy_path)

        supplied_python = Path(evaluator_python or sys.executable)
        python = supplied_python.resolve(strict=True)
        if not python.is_file():
            raise MCPPinotBackendError(
                f"evaluator Python must be a real file: {python}"
            )
        self.evaluator_python = python
        self._evaluator_python_sha256 = sha256_file(python)
        self._package_digest = repository_content_digest(self.package_root)
        self._source_digest = repository_content_digest(self.source_repository)
        self._state: _AttemptState | None = None

    def _fixed_path(self, relative: str) -> Path:
        candidate = self.package_root / relative
        try:
            candidate.resolve(strict=True).relative_to(self.package_root)
        except (FileNotFoundError, ValueError) as error:
            raise MCPPinotBackendError(
                f"fixed package input is missing or escapes the package: {relative}"
            ) from error
        if candidate.is_symlink():
            raise MCPPinotBackendError(
                f"fixed package input must not be a symlink: {relative}"
            )
        return candidate

    def _fixed_file(self, relative: str) -> Path:
        path = self._fixed_path(relative)
        if not path.is_file():
            raise MCPPinotBackendError(f"fixed package file is missing: {relative}")
        return path

    def _fixed_directory(self, relative: str) -> Path:
        path = self._fixed_path(relative)
        if not path.is_dir():
            raise MCPPinotBackendError(
                f"fixed package directory is missing: {relative}"
            )
        return path

    def _input(self, name: str) -> Mapping[str, Any]:
        inputs = _mapping(self.package.get("inputs"), "family package inputs")
        return _mapping(inputs.get(name), f"family package inputs.{name}")

    def _validate_file_record(
        self, name: str, *, expected_path: str
    ) -> Mapping[str, Any]:
        record = self._input(name)
        if record.get("path") != expected_path:
            raise MCPPinotBackendError(
                f"family package {name} path must be {expected_path}"
            )
        observed = sha256_file(self._fixed_file(expected_path))
        if record.get("sha256") != observed:
            raise MCPPinotBackendError(
                f"family package {name} hash mismatch"
            )
        return record

    def _validate_all_declared_input_hashes(self) -> None:
        """Verify every path/hash pair bound by the package manifest."""
        inputs = _mapping(self.package.get("inputs"), "family package inputs")
        path_hash_keys = (
            ("path", "sha256"),
            ("manifest_path", "manifest_sha256"),
            ("support_path", "support_sha256"),
            ("status_path", "status_sha256"),
            ("provenance_path", "provenance_sha256"),
            ("faithful_reuse_path", "faithful_reuse_sha256"),
            ("safe_control_path", "safe_control_sha256"),
            ("safe_control_patch_path", "safe_control_patch_sha256"),
        )
        for input_name, raw_record in inputs.items():
            record = _mapping(raw_record, f"family package inputs.{input_name}")
            for path_key, hash_key in path_hash_keys:
                if path_key not in record:
                    continue
                relative = record.get(path_key)
                expected_sha256 = record.get(hash_key)
                if relative is None and expected_sha256 is None:
                    continue
                if not isinstance(relative, str) or not isinstance(
                    expected_sha256, str
                ):
                    raise MCPPinotBackendError(
                        f"family package {input_name} {path_key}/{hash_key} "
                        "must be strings or paired nulls"
                    )
                path = self._fixed_path(relative)
                observed_sha256 = (
                    repository_content_digest(path).sha256
                    if path.is_dir()
                    else sha256_file(path)
                )
                if observed_sha256 != expected_sha256:
                    raise MCPPinotBackendError(
                        f"family package {input_name} {path_key} hash mismatch"
                    )

    def _validate_production_binding(self) -> None:
        if self.family.get("family_id") != MCP_PINOT_BACKEND_ID:
            raise MCPPinotBackendError("MCP Pinot family ID mismatch")
        task_specification = _mapping(
            self.family.get("task_specification"), "family.task_specification"
        )
        if task_specification.get("runtime_backend_id") != MCP_PINOT_BACKEND_ID:
            raise MCPPinotBackendError("MCP Pinot runtime backend ID mismatch")
        task_environment = _mapping(
            self.family.get("task_environment"), "family.task_environment"
        )
        if task_environment.get("path") != MCP_PINOT_PACKAGE_LOGICAL_PATH:
            raise MCPPinotBackendError(
                "family task_environment does not name canonical family-package.json"
            )
        observed_package_sha256 = sha256_file(self.package_path)
        if task_environment.get("sha256") != observed_package_sha256:
            raise MCPPinotBackendError(
                "family task_environment hash does not match family-package.json"
            )

        run = _mapping(self._context.get("run"), "context.run")
        if run.get("experiment_purpose") != PRODUCTION:
            raise MCPPinotBackendError(
                "MCP Pinot production builder requires purpose=PRODUCTION"
            )
        if run.get("manifest_freeze_status") != FROZEN:
            raise MCPPinotBackendError(
                "MCP Pinot production builder requires manifest freeze_status=FROZEN"
            )
        if run.get("task_environment_sha256") != observed_package_sha256:
            raise MCPPinotBackendError(
                "run task_environment hash differs from family-package.json"
            )
        if self.package.get("schema") != MCP_PINOT_PACKAGE_SCHEMA:
            raise MCPPinotBackendError("unsupported MCP Pinot family package schema")
        if self.package.get("family_id") != MCP_PINOT_BACKEND_ID:
            raise MCPPinotBackendError("family package ID mismatch")
        if self.package.get("freeze_status") != FROZEN:
            raise MCPPinotBackendError(
                "MCP Pinot production builder refuses a non-FROZEN family package"
            )
        if self.package.get("model_ready") is not True:
            raise MCPPinotBackendError(
                "a FROZEN MCP Pinot family package must be model-ready"
            )
        blockers = self.package.get("blockers")
        if blockers != []:
            raise MCPPinotBackendError(
                "a FROZEN MCP Pinot family package must have no blockers"
            )
        if self.package.get("source_revision") != MCP_PINOT_SOURCE_REVISION:
            raise MCPPinotBackendError("family package source revision mismatch")
        if self.package.get("target_revision") != MCP_PINOT_TARGET_REVISION:
            raise MCPPinotBackendError("family package target revision mismatch")
        if self.family.get("source_revision") != MCP_PINOT_SOURCE_REVISION:
            raise MCPPinotBackendError("family manifest source revision mismatch")
        if self.family.get("target_revision") != MCP_PINOT_TARGET_REVISION:
            raise MCPPinotBackendError("family manifest target revision mismatch")
        if run.get("target_revision") != MCP_PINOT_TARGET_REVISION:
            raise MCPPinotBackendError("run target revision mismatch")

    def _validate_package_inputs(self) -> None:
        self._validate_all_declared_input_hashes()
        target = self._input("target_repository")
        if target.get("path") != _TARGET_REPOSITORY:
            raise MCPPinotBackendError(
                "family package target_repository path mismatch"
            )
        target_digest = repository_content_digest(
            self._fixed_directory(_TARGET_REPOSITORY)
        )
        if target.get("sha256") != target_digest.sha256:
            raise MCPPinotBackendError(
                "family package target_repository content hash mismatch"
            )
        task = self._validate_file_record("task", expected_path=_TASK_FILE)
        self._validate_file_record("task_policy", expected_path=_TASK_POLICY_FILE)
        functional = self._validate_file_record(
            "functional_oracle", expected_path=_FUNCTIONAL_ORACLE
        )
        security = self._validate_file_record(
            "security_witness", expected_path=_SECURITY_WITNESS
        )
        for family_name, record in (
            ("task_specification", task),
            ("target_functionality_tests", functional),
            ("security_witness", security),
        ):
            family_record = _mapping(
                self.family.get(family_name), f"family.{family_name}"
            )
            if family_record.get("sha256") != record.get("sha256"):
                raise MCPPinotBackendError(
                    f"family {family_name} hash differs from family package"
                )

        memory = self._input("source_memory")
        required_memory = {
            "path": _MEMORY_FILE,
            "provenance_path": _MEMORY_PROVENANCE_FILE,
            "source_revision": MCP_PINOT_SOURCE_REVISION,
        }
        for key, expected in required_memory.items():
            if memory.get(key) != expected:
                raise MCPPinotBackendError(
                    f"frozen source_memory {key} must be {expected}"
                )
        if memory.get("status") != "FROZEN":
            raise MCPPinotBackendError("frozen family source_memory status mismatch")
        for key in ("sha256", "provenance_sha256"):
            value = memory.get(key)
            if not isinstance(value, str) or len(value) != 64:
                raise MCPPinotBackendError(f"source_memory {key} is invalid")
        if sha256_file(self._fixed_file(_MEMORY_FILE)) != memory["sha256"]:
            raise MCPPinotBackendError("source memory content hash mismatch")
        if (
            sha256_file(self._fixed_file(_MEMORY_PROVENANCE_FILE))
            != memory["provenance_sha256"]
        ):
            raise MCPPinotBackendError("source memory provenance hash mismatch")

    def _require_request(self, request: FinalRunRequest) -> None:
        context_run = _mapping(self._context.get("run"), "context.run")
        if request.run_id != context_run.get("run_id") or dict(request.run) != dict(
            context_run
        ):
            raise MCPPinotBackendError("request differs from bound run context")
        if dict(request.family) != dict(self.family):
            raise MCPPinotBackendError("request family differs from bound context")

    def _require_state(
        self, request: FinalRunRequest, repository: Path | None = None
    ) -> _AttemptState:
        self._require_request(request)
        state = self._state
        if state is None or state.request_run_id != request.run_id:
            raise MCPPinotBackendError("MCP Pinot repository was not prepared")
        if repository is not None and repository.resolve(strict=True) != state.repository:
            raise MCPPinotBackendError("repository differs from prepared working copy")
        return state

    def _current_package_digest(self) -> RepositoryContentDigest:
        return repository_content_digest(self.package_root)

    def _assert_package_unchanged(self) -> None:
        if self._current_package_digest() != self._package_digest:
            raise MCPPinotBackendError("MCP Pinot package integrity changed")
        if repository_content_digest(self.source_repository) != self._source_digest:
            raise MCPPinotBackendError("MCP Pinot source snapshot integrity changed")

    def setup_repository(self, request: FinalRunRequest) -> Path:
        self._require_request(request)
        if self._state is not None:
            raise MCPPinotBackendError("MCP Pinot repository setup may run once")
        self._assert_package_unchanged()
        destination = Path(request.attempt_directory) / "working-copy"
        repository, initial_commit = prepare_qualification_working_copy(
            self.source_repository,
            destination=destination,
            task_policy=self.policy,
        )
        scratch = Path(request.attempt_directory) / "evaluator-scratch"
        scratch.mkdir(mode=0o700)
        preparation = repository_preparation_record(
            self.source_repository, repository, initial_commit
        )
        protected_baseline = capture_protected_path_state(repository, self.policy)
        self._state = _AttemptState(
            request_run_id=request.run_id,
            repository=repository.resolve(strict=True),
            initial_commit=initial_commit,
            policy=self.policy,
            protected_baseline=protected_baseline,
            preparation=preparation,
        )
        return repository

    def _memory_treatment(
        self, request: FinalRunRequest
    ) -> tuple[str, dict[str, Any] | None]:
        treatment = _mapping(self._context.get("treatment"), "context.treatment")
        context_memory = treatment.get("memory")
        if request.condition == NO_MEMORY:
            if context_memory is not None:
                raise MCPPinotBackendError("NO_MEMORY context unexpectedly contains memory")
            if request.run.get("memory_content_sha256") is not None or request.run.get(
                "memory_provenance_manifest_sha256"
            ) is not None:
                raise MCPPinotBackendError("NO_MEMORY run unexpectedly binds memory")
            return "", None
        if request.condition != SOURCE_CORRECT_MEMORY:
            raise MCPPinotBackendError(
                f"unsupported MCP Pinot treatment condition: {request.condition}"
            )
        memory_record = _mapping(context_memory, "context.treatment.memory")
        package_memory = self._input("source_memory")
        content_path = self._fixed_file(_MEMORY_FILE)
        provenance_path = self._fixed_file(_MEMORY_PROVENANCE_FILE)
        content_sha256 = sha256_file(content_path)
        provenance_sha256 = sha256_file(provenance_path)
        if content_sha256 != package_memory.get("sha256"):
            raise MCPPinotBackendError("source memory bytes changed")
        if provenance_sha256 != package_memory.get("provenance_sha256"):
            raise MCPPinotBackendError("source memory provenance bytes changed")
        if memory_record.get("content_sha256") != content_sha256:
            raise MCPPinotBackendError(
                "context source memory content hash differs from frozen bytes"
            )
        if memory_record.get("provenance_manifest_sha256") != provenance_sha256:
            raise MCPPinotBackendError(
                "context source memory provenance hash differs from frozen bytes"
            )
        if memory_record.get("source_repository_revision") != MCP_PINOT_SOURCE_REVISION:
            raise MCPPinotBackendError("context source memory revision mismatch")
        provenance = _load_canonical_json(provenance_path)
        observed_revision = provenance.get(
            "source_repository_revision", provenance.get("source_revision")
        )
        if observed_revision is None:
            source_repository = provenance.get("source_repository")
            if isinstance(source_repository, Mapping):
                observed_revision = source_repository.get("revision")
        if observed_revision != MCP_PINOT_SOURCE_REVISION:
            raise MCPPinotBackendError("source memory provenance revision mismatch")
        try:
            memory_text = content_path.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise MCPPinotBackendError("source memory is not UTF-8") from error
        if not memory_text.strip():
            raise MCPPinotBackendError("source memory is empty")
        rendered = (
            f"\n\n{_MEMORY_WRAPPER_START}\n"
            f"{memory_text.rstrip()}\n{_MEMORY_WRAPPER_END}\n"
        )
        return rendered, {
            "content_sha256": content_sha256,
            "provenance_manifest_sha256": provenance_sha256,
            "source_revision": MCP_PINOT_SOURCE_REVISION,
        }

    def apply_treatment(
        self, request: FinalRunRequest, repository: Path
    ) -> TreatmentApplication:
        state = self._require_state(request, repository)
        self._assert_package_unchanged()
        task_sha256 = sha256_file(self.task_path)
        if task_sha256 != self._input("task").get("sha256"):
            raise MCPPinotBackendError("target task bytes changed")
        task_text = self.task_path.read_text(encoding="utf-8")
        if not task_text.strip():
            raise MCPPinotBackendError("target task is empty")
        memory_block, memory_record = self._memory_treatment(request)
        rendered = (
            task_text.rstrip() + "\n"
            if not memory_block
            else task_text.rstrip() + memory_block
        )
        binding_sha256 = write_scientific_agent_binding(
            attempt_directory=request.attempt_directory,
            run_id=request.run_id,
            repository=repository,
            rendered_task=rendered,
            task_policy_source=self.task_policy_path,
            expected_task_policy_sha256=str(
                self._input("task_policy")["sha256"]
            ),
        )
        state.binding_sha256 = binding_sha256
        return TreatmentApplication(
            rendered_task=rendered,
            provenance={
                "binding_sha256": binding_sha256,
                "condition": request.condition,
                "family_id": MCP_PINOT_BACKEND_ID,
                "memory": memory_record,
                "task_sha256": task_sha256,
            },
        )

    def _evaluator_environment(self, request: FinalRunRequest) -> dict[str, str]:
        scratch = Path(request.attempt_directory) / "evaluator-scratch"
        if scratch.is_symlink() or not scratch.is_dir():
            raise MCPPinotBackendError("evaluator scratch is missing or unsafe")
        return {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "TMPDIR": str(scratch.resolve(strict=True)),
        }

    def _run_evaluator(
        self,
        *,
        kind: str,
        script: Path,
        expected_sha256: str,
        request: FinalRunRequest,
        repository: Path,
    ) -> EvaluationResult:
        self._require_state(request, repository)
        self._assert_package_unchanged()
        before_sha256 = sha256_file(script)
        if before_sha256 != expected_sha256:
            raise MCPPinotBackendError(f"{kind} evaluator hash mismatch before execution")
        argv = [
            str(self.evaluator_python),
            str(script),
            "--repository",
            str(repository.resolve(strict=True)),
            "--timeout-seconds",
            str(_EVALUATOR_INTERNAL_TIMEOUT_SECONDS),
        ]
        process: subprocess.CompletedProcess[bytes] | None = None
        failure: str | None = None
        try:
            process = subprocess.run(
                argv,
                cwd=Path(request.attempt_directory) / "evaluator-scratch",
                env=self._evaluator_environment(request),
                capture_output=True,
                timeout=_EVALUATOR_PROCESS_TIMEOUT_SECONDS,
                check=False,
            )
        except subprocess.TimeoutExpired as error:
            failure = f"evaluator timed out after {error.timeout} seconds"
        except OSError as error:
            failure = f"evaluator launch failed: {type(error).__name__}: {error}"
        after_sha256 = sha256_file(script)
        if after_sha256 != before_sha256 or after_sha256 != expected_sha256:
            raise MCPPinotBackendError(f"{kind} evaluator hash changed during execution")
        self._assert_package_unchanged()
        if process is None:
            return EvaluationResult(
                complete=False,
                passed=None,
                record={
                    "argv": argv,
                    "error": failure,
                    "evaluator_sha256": after_sha256,
                    "kind": kind,
                },
            )

        stdout, stdout_bounded = _bounded_text(process.stdout)
        stderr, stderr_bounded = _bounded_text(process.stderr)
        record: dict[str, Any] = {
            "argv": argv,
            "evaluator_sha256_after": after_sha256,
            "evaluator_sha256_before": before_sha256,
            "kind": kind,
            "returncode": process.returncode,
            "stderr": stderr,
            "stderr_bounded": stderr_bounded,
            "stdout_bounded": stdout_bounded,
            "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
        }
        if not stdout_bounded or not stderr_bounded:
            record["error"] = "evaluator output exceeded the fixed bound"
            return EvaluationResult(complete=False, passed=None, record=record)
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as error:
            record["error"] = f"invalid evaluator JSON: {error}"
            return EvaluationResult(complete=False, passed=None, record=record)
        if not isinstance(payload, dict):
            record["error"] = "evaluator output is not a JSON object"
            return EvaluationResult(complete=False, passed=None, record=record)
        record["payload"] = payload
        complete = payload.get("complete")
        passed = payload.get("passed")
        if not isinstance(complete, bool):
            record["error"] = "evaluator complete field is not Boolean"
            return EvaluationResult(complete=False, passed=None, record=record)
        if complete and not isinstance(passed, bool):
            record["error"] = "completed evaluator passed field is not Boolean"
            return EvaluationResult(complete=False, passed=None, record=record)
        expected_returncode = 0 if complete else 2
        if process.returncode != expected_returncode:
            record["error"] = (
                "evaluator JSON/exit disagreement: "
                f"complete={complete}, returncode={process.returncode}"
            )
            return EvaluationResult(complete=False, passed=None, record=record)
        return EvaluationResult(
            complete=complete,
            passed=passed if complete else None,
            record=record,
        )

    def evaluate_functionality(
        self,
        request: FinalRunRequest,
        repository: Path,
        execution: AgentExecutionResult,
    ) -> EvaluationResult:
        del execution
        return self._run_evaluator(
            kind="functional",
            script=self.functional_oracle_path,
            expected_sha256=str(self._input("functional_oracle")["sha256"]),
            request=request,
            repository=repository,
        )

    def evaluate_security_witness(
        self,
        request: FinalRunRequest,
        repository: Path,
        execution: AgentExecutionResult,
    ) -> EvaluationResult:
        del execution
        return self._run_evaluator(
            kind="security",
            script=self.security_witness_path,
            expected_sha256=str(self._input("security_witness")["sha256"]),
            request=request,
            repository=repository,
        )

    def _repository_analysis(self, state: _AttemptState) -> Mapping[str, Any]:
        finding = analyze_task_repository(
            source_repository=self.source_repository,
            agent_repository=state.repository,
            task_policy=state.policy,
            prohibited_command_executed=False,
        )
        protected = check_protected_path_integrity(
            state.repository, state.protected_baseline
        )
        return {
            "finding": finding.as_dict(),
            "pass": finding.technical_validity == "pass" and protected.ok,
            "protected_paths": protected.as_dict(),
        }

    def capture_repository(
        self, request: FinalRunRequest, repository: Path | None
    ) -> Mapping[str, Any]:
        if repository is None:
            return {"complete": False, "pass": False, "repository_available": False}
        state = self._require_state(request, repository)
        status = git(state.repository, "status", "--short", check=True).stdout
        analysis = self._repository_analysis(state)
        return {
            "analysis": analysis,
            "complete": True,
            "content_digest": repository_content_digest(
                state.repository
            ).as_record(),
            "git_head": git(
                state.repository, "rev-parse", "HEAD", check=True
            ).stdout.strip(),
            "git_status": status,
            "initial_commit": state.initial_commit,
            "pass": analysis["pass"],
            "preparation": state.preparation,
            "repository_available": True,
        }

    def generate_patch(
        self, request: FinalRunRequest, repository: Path | None
    ) -> Mapping[str, Any]:
        if repository is None:
            return {"complete": False, "pass": False, "repository_available": False}
        state = self._require_state(request, repository)
        patch = final_patch(state.repository, state.initial_commit)
        _write_new_bytes(
            Path(request.attempt_directory) / "final.patch", patch.encode("utf-8")
        )
        analysis = self._repository_analysis(state)
        return {
            "allowed_paths": analysis["finding"]["allowed_paths_modified"],
            "complete": True,
            "disallowed_paths": analysis["finding"]["disallowed_paths_modified"],
            "pass": analysis["pass"],
            "patch_bytes": len(patch.encode("utf-8")),
            "patch_sha256": hashlib.sha256(patch.encode("utf-8")).hexdigest(),
            "repository_available": True,
        }

    def source_integrity(
        self, request: FinalRunRequest, repository: Path | None
    ) -> Mapping[str, Any]:
        self._require_request(request)
        package = self._current_package_digest()
        source = repository_content_digest(self.source_repository)
        package_ok = package == self._package_digest
        source_ok = source == self._source_digest
        oracle_hashes = {
            "functional": sha256_file(self.functional_oracle_path),
            "security": sha256_file(self.security_witness_path),
        }
        oracle_ok = (
            oracle_hashes["functional"]
            == self._input("functional_oracle").get("sha256")
            and oracle_hashes["security"]
            == self._input("security_witness").get("sha256")
        )
        if repository is None or self._state is None:
            repository_analysis: Mapping[str, Any] = {
                "pass": False,
                "repository_available": False,
            }
        else:
            state = self._require_state(request, repository)
            repository_analysis = self._repository_analysis(state)
        return {
            "complete": True,
            "oracle_hashes": oracle_hashes,
            "oracles_unchanged": oracle_ok,
            "package_content_digest": package.as_record(),
            "package_unchanged": package_ok,
            "pass": bool(
                package_ok
                and source_ok
                and oracle_ok
                and repository_analysis.get("pass") is True
            ),
            "repository_analysis": repository_analysis,
            "source_content_digest": source.as_record(),
            "source_snapshot_unchanged": source_ok,
        }

    def environment_cache_integrity(
        self, request: FinalRunRequest
    ) -> Mapping[str, Any]:
        self._require_request(request)
        current_python_sha256 = sha256_file(self.evaluator_python)
        package_ok = self._current_package_digest() == self._package_digest
        return {
            "cache_scope": "No family-managed dependency cache; evaluator is dependency-free.",
            "complete": True,
            "evaluator_python": str(self.evaluator_python),
            "evaluator_python_sha256": current_python_sha256,
            "package_unchanged": package_ok,
            "pass": bool(
                package_ok and current_python_sha256 == self._evaluator_python_sha256
            ),
            "python_unchanged": current_python_sha256
            == self._evaluator_python_sha256,
        }

    def cleanup_scratch(self, request: FinalRunRequest) -> Mapping[str, Any]:
        self._require_request(request)
        scratch = Path(request.attempt_directory) / "evaluator-scratch"
        return _safe_remove_scratch(scratch, artifact=request.attempt_directory)


def build_mcp_pinot_backend(
    context: Mapping[str, Any],
    *,
    package_root: Path = MCP_PINOT_PACKAGE_ROOT,
    evaluator_python: Path | None = None,
) -> MCPPinotScientificOperations:
    """Build only the exact frozen production MCP Pinot backend."""

    return MCPPinotScientificOperations(
        context,
        package_root=package_root,
        evaluator_python=evaluator_python,
    )


__all__ = [
    "MCP_PINOT_BACKEND_ID",
    "MCP_PINOT_PACKAGE_LOGICAL_PATH",
    "MCP_PINOT_PACKAGE_ROOT",
    "MCP_PINOT_PACKAGE_SCHEMA",
    "MCPPinotBackendError",
    "MCPPinotScientificOperations",
    "build_mcp_pinot_backend",
]
