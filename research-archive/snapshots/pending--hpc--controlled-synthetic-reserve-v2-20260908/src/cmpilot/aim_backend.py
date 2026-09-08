"""Candidate-specific scientific runtime for the Aim Track B family."""

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


AIM_BACKEND_ID = "aim-v1"
AIM_PACKAGE_SCHEMA = "cmpilot-aim-family-package-v1"
AIM_PACKAGE_ROOT = Path(__file__).parents[2] / "families" / AIM_BACKEND_ID
AIM_PACKAGE_LOGICAL_PATH = "families/aim-v1/family-package.json"
AIM_SOURCE_REVISION = "dfd8368c7eb01142af69ed27cfebde0697110876"
AIM_TARGET_REVISION = "190b44c420aca4a7a9042d8b5ff6901652aac2c2"

_PACKAGE_FILE = "family-package.json"
_TARGET_REPOSITORY = "repositories/invalidated"
_TASK_FILE = "tasks/target-task.md"
_TASK_POLICY_FILE = "task-policy.json"
_FUNCTIONAL_ORACLE = "oracles/functional/evaluate.py"
_SECURITY_WITNESS = "oracles/security/evaluate.py"
_MEMORY_FILE = "memories/source-correct-memory.md"
_MEMORY_PROVENANCE_FILE = "memories/source-correct-memory.provenance.json"
_MEMORY_WRAPPER_START = "<SOURCE_CORRECT_PROCEDURAL_MEMORY>"
_MEMORY_WRAPPER_END = "</SOURCE_CORRECT_PROCEDURAL_MEMORY>"
_EVALUATOR_INTERNAL_TIMEOUT_SECONDS = 5.0
_EVALUATOR_PROCESS_TIMEOUT_SECONDS = 30.0
_MAX_EVALUATOR_OUTPUT_BYTES = 16_384


class AimBackendError(RuntimeError):
    """An Aim package or runtime invariant failed."""


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
        raise AimBackendError(f"invalid JSON input {path}: {error}") from error
    if not isinstance(value, dict):
        raise AimBackendError(f"expected a JSON object: {path}")
    if canonical_json_bytes(value) != payload:
        raise AimBackendError(f"JSON input is not canonical: {path}")
    return value


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AimBackendError(f"{label} must be an object")
    return value


def _bounded_text(payload: bytes) -> tuple[str, bool]:
    bounded = payload[:_MAX_EVALUATOR_OUTPUT_BYTES]
    return bounded.decode("utf-8", errors="replace"), len(payload) <= len(bounded)


def _write_new_bytes(path: Path, payload: bytes) -> None:
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise AimBackendError(f"refusing to overwrite attempt artifact: {path}") from error
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise


class AimScientificOperations:
    """Implement ``ScientificOperations`` only for ``aim-v1``."""

    def __init__(
        self,
        context: Mapping[str, Any],
        *,
        package_root: Path = AIM_PACKAGE_ROOT,
        evaluator_python: Path | None = None,
    ) -> None:
        self._context = _mapping(context, "run context")
        supplied_root = Path(package_root)
        if supplied_root.is_symlink():
            raise AimBackendError(f"package root must be real: {supplied_root}")
        self.package_root = supplied_root.resolve(strict=True)
        if not self.package_root.is_dir():
            raise AimBackendError(f"package root must be a directory: {supplied_root}")
        self.package_path = self._fixed_file(_PACKAGE_FILE)
        self.package = _load_canonical_json(self.package_path)
        self.family = _mapping(
            self._context.get("family_manifest"), "context.family_manifest"
        )
        # This check deliberately runs before any missing-memory access.  The
        # checked-in provisional package must fail closed until a later exact
        # provenance-confirmed freeze changes all production bindings.
        self._validate_production_binding()
        self._validate_package_inputs()

        self.source_repository = self._fixed_directory(_TARGET_REPOSITORY)
        self.task_path = self._fixed_file(_TASK_FILE)
        self.task_policy_path = self._fixed_file(_TASK_POLICY_FILE)
        self.functional_oracle_path = self._fixed_file(_FUNCTIONAL_ORACLE)
        self.security_witness_path = self._fixed_file(_SECURITY_WITNESS)
        self.policy = load_task_policy(self.task_policy_path)
        python = Path(evaluator_python or sys.executable).resolve(strict=True)
        if not python.is_file():
            raise AimBackendError(f"evaluator Python must be a file: {python}")
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
            raise AimBackendError(
                f"fixed package input is missing or escapes: {relative}"
            ) from error
        if candidate.is_symlink():
            raise AimBackendError(f"fixed package input is a symlink: {relative}")
        return candidate

    def _fixed_file(self, relative: str) -> Path:
        path = self._fixed_path(relative)
        if not path.is_file():
            raise AimBackendError(f"fixed package file is missing: {relative}")
        return path

    def _fixed_directory(self, relative: str) -> Path:
        path = self._fixed_path(relative)
        if not path.is_dir():
            raise AimBackendError(f"fixed package directory is missing: {relative}")
        return path

    def _input(self, name: str) -> Mapping[str, Any]:
        inputs = _mapping(self.package.get("inputs"), "family package inputs")
        return _mapping(inputs.get(name), f"family package inputs.{name}")

    def _validate_production_binding(self) -> None:
        if self.family.get("family_id") != AIM_BACKEND_ID:
            raise AimBackendError("Aim family ID mismatch")
        specification = _mapping(
            self.family.get("task_specification"), "family.task_specification"
        )
        if specification.get("runtime_backend_id") != AIM_BACKEND_ID:
            raise AimBackendError("Aim runtime backend ID mismatch")
        environment = _mapping(
            self.family.get("task_environment"), "family.task_environment"
        )
        if environment.get("path") != AIM_PACKAGE_LOGICAL_PATH:
            raise AimBackendError("Aim task environment path mismatch")
        package_sha256 = sha256_file(self.package_path)
        if environment.get("sha256") != package_sha256:
            raise AimBackendError("Aim task_environment hash mismatch")
        run = _mapping(self._context.get("run"), "context.run")
        if run.get("experiment_purpose") != PRODUCTION:
            raise AimBackendError("Aim production builder requires purpose=PRODUCTION")
        if run.get("manifest_freeze_status") != FROZEN:
            raise AimBackendError("Aim production builder requires a frozen manifest")
        if run.get("task_environment_sha256") != package_sha256:
            raise AimBackendError("Aim run task_environment hash mismatch")
        if self.package.get("schema") != AIM_PACKAGE_SCHEMA:
            raise AimBackendError("unsupported Aim family package schema")
        if self.package.get("family_id") != AIM_BACKEND_ID:
            raise AimBackendError("Aim package ID mismatch")
        if self.package.get("freeze_status") != FROZEN:
            raise AimBackendError("Aim backend refuses a non-FROZEN family package")
        if self.package.get("model_ready") is not True:
            raise AimBackendError("a frozen Aim package must be model-ready")
        if self.package.get("blockers") != []:
            raise AimBackendError("a frozen Aim package must have no blockers")
        for label, observed, expected in (
            ("package source", self.package.get("source_revision"), AIM_SOURCE_REVISION),
            ("package target", self.package.get("target_revision"), AIM_TARGET_REVISION),
            ("family source", self.family.get("source_revision"), AIM_SOURCE_REVISION),
            ("family target", self.family.get("target_revision"), AIM_TARGET_REVISION),
            ("run target", run.get("target_revision"), AIM_TARGET_REVISION),
        ):
            if observed != expected:
                raise AimBackendError(f"Aim {label} revision mismatch")

    def _validate_declared_hashes(self) -> None:
        path_hash_keys = (
            ("path", "sha256"),
            ("manifest_path", "manifest_sha256"),
            ("support_path", "support_sha256"),
            ("provenance_path", "provenance_sha256"),
        )
        for name, raw in _mapping(
            self.package.get("inputs"), "family package inputs"
        ).items():
            record = _mapping(raw, f"family package inputs.{name}")
            for path_key, hash_key in path_hash_keys:
                if path_key not in record:
                    continue
                relative = record.get(path_key)
                expected = record.get(hash_key)
                if relative is None and expected is None:
                    continue
                if not isinstance(relative, str) or not isinstance(expected, str):
                    raise AimBackendError(
                        f"Aim package {name} {path_key}/{hash_key} is invalid"
                    )
                path = self._fixed_path(relative)
                observed = (
                    repository_content_digest(path).sha256
                    if path.is_dir()
                    else sha256_file(path)
                )
                if observed != expected:
                    raise AimBackendError(f"Aim package {name} {path_key} hash mismatch")

    def _validate_package_inputs(self) -> None:
        self._validate_declared_hashes()
        for name, path in (
            ("target_repository", _TARGET_REPOSITORY),
            ("task", _TASK_FILE),
            ("task_policy", _TASK_POLICY_FILE),
            ("functional_oracle", _FUNCTIONAL_ORACLE),
            ("security_witness", _SECURITY_WITNESS),
        ):
            if self._input(name).get("path") != path:
                raise AimBackendError(f"Aim package {name} path mismatch")
        memory = self._input("source_memory")
        required = {
            "path": _MEMORY_FILE,
            "provenance_path": _MEMORY_PROVENANCE_FILE,
            "source_revision": AIM_SOURCE_REVISION,
            "status": FROZEN,
        }
        for key, expected in required.items():
            if memory.get(key) != expected:
                raise AimBackendError(f"frozen Aim source_memory {key} mismatch")
        if sha256_file(self._fixed_file(_MEMORY_FILE)) != memory.get("sha256"):
            raise AimBackendError("Aim source memory hash mismatch")
        if (
            sha256_file(self._fixed_file(_MEMORY_PROVENANCE_FILE))
            != memory.get("provenance_sha256")
        ):
            raise AimBackendError("Aim source memory provenance hash mismatch")
        for family_name, input_name in (
            ("task_specification", "task"),
            ("target_functionality_tests", "functional_oracle"),
            ("security_witness", "security_witness"),
        ):
            family_record = _mapping(self.family.get(family_name), f"family.{family_name}")
            if family_record.get("sha256") != self._input(input_name).get("sha256"):
                raise AimBackendError(f"Aim family {family_name} hash mismatch")

    def _require_request(self, request: FinalRunRequest) -> None:
        context_run = _mapping(self._context.get("run"), "context.run")
        if request.run_id != context_run.get("run_id") or dict(request.run) != dict(
            context_run
        ):
            raise AimBackendError("Aim request differs from bound run context")
        if dict(request.family) != dict(self.family):
            raise AimBackendError("Aim request family differs from context")

    def _require_state(
        self, request: FinalRunRequest, repository: Path | None = None
    ) -> _AttemptState:
        self._require_request(request)
        state = self._state
        if state is None or state.request_run_id != request.run_id:
            raise AimBackendError("Aim repository was not prepared")
        if repository is not None and repository.resolve(strict=True) != state.repository:
            raise AimBackendError("repository differs from Aim working copy")
        return state

    def _current_package_digest(self) -> RepositoryContentDigest:
        return repository_content_digest(self.package_root)

    def _assert_package_unchanged(self) -> None:
        if self._current_package_digest() != self._package_digest:
            raise AimBackendError("Aim package integrity changed")
        if repository_content_digest(self.source_repository) != self._source_digest:
            raise AimBackendError("Aim target snapshot integrity changed")

    def setup_repository(self, request: FinalRunRequest) -> Path:
        self._require_request(request)
        if self._state is not None:
            raise AimBackendError("Aim repository setup may run once")
        self._assert_package_unchanged()
        destination = Path(request.attempt_directory) / "working-copy"
        repository, initial_commit = prepare_qualification_working_copy(
            self.source_repository,
            destination=destination,
            task_policy=self.policy,
        )
        scratch = Path(request.attempt_directory) / "evaluator-scratch"
        scratch.mkdir(mode=0o700)
        self._state = _AttemptState(
            request_run_id=request.run_id,
            repository=repository.resolve(strict=True),
            initial_commit=initial_commit,
            policy=self.policy,
            protected_baseline=capture_protected_path_state(repository, self.policy),
            preparation=repository_preparation_record(
                self.source_repository, repository, initial_commit
            ),
        )
        return repository

    def _memory_treatment(
        self, request: FinalRunRequest
    ) -> tuple[str, dict[str, Any] | None]:
        treatment = _mapping(self._context.get("treatment"), "context.treatment")
        context_memory = treatment.get("memory")
        if request.condition == NO_MEMORY:
            if context_memory is not None:
                raise AimBackendError("NO_MEMORY context unexpectedly contains memory")
            if request.run.get("memory_content_sha256") is not None or request.run.get(
                "memory_provenance_manifest_sha256"
            ) is not None:
                raise AimBackendError("NO_MEMORY run unexpectedly binds memory")
            return "", None
        if request.condition != SOURCE_CORRECT_MEMORY:
            raise AimBackendError(f"unsupported Aim condition: {request.condition}")
        record = _mapping(context_memory, "context.treatment.memory")
        package_memory = self._input("source_memory")
        content = self._fixed_file(_MEMORY_FILE)
        provenance = self._fixed_file(_MEMORY_PROVENANCE_FILE)
        content_sha256 = sha256_file(content)
        provenance_sha256 = sha256_file(provenance)
        if content_sha256 != package_memory.get("sha256"):
            raise AimBackendError("Aim source memory bytes changed")
        if provenance_sha256 != package_memory.get("provenance_sha256"):
            raise AimBackendError("Aim source memory provenance changed")
        if record.get("content_sha256") != content_sha256:
            raise AimBackendError("Aim context memory content hash differs")
        if record.get("provenance_manifest_sha256") != provenance_sha256:
            raise AimBackendError("Aim context memory provenance hash differs")
        if record.get("source_repository_revision") != AIM_SOURCE_REVISION:
            raise AimBackendError("Aim context memory revision differs")
        provenance_value = _load_canonical_json(provenance)
        source_record = provenance_value.get("source_repository")
        if not isinstance(source_record, Mapping) or source_record.get(
            "revision"
        ) != AIM_SOURCE_REVISION:
            raise AimBackendError("Aim memory provenance revision differs")
        try:
            memory_text = content.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            raise AimBackendError("Aim source memory is not UTF-8") from error
        if not memory_text.strip():
            raise AimBackendError("Aim source memory is empty")
        rendered = (
            f"\n\n{_MEMORY_WRAPPER_START}\n{memory_text.rstrip()}\n"
            f"{_MEMORY_WRAPPER_END}\n"
        )
        return rendered, {
            "content_sha256": content_sha256,
            "provenance_manifest_sha256": provenance_sha256,
            "source_revision": AIM_SOURCE_REVISION,
        }

    def apply_treatment(
        self, request: FinalRunRequest, repository: Path
    ) -> TreatmentApplication:
        state = self._require_state(request, repository)
        self._assert_package_unchanged()
        task_sha256 = sha256_file(self.task_path)
        if task_sha256 != self._input("task").get("sha256"):
            raise AimBackendError("Aim task bytes changed")
        task_text = self.task_path.read_text(encoding="utf-8")
        if not task_text.strip():
            raise AimBackendError("Aim task is empty")
        memory_block, memory_record = self._memory_treatment(request)
        rendered = task_text.rstrip() + (memory_block or "\n")
        binding_sha256 = write_scientific_agent_binding(
            attempt_directory=request.attempt_directory,
            run_id=request.run_id,
            repository=repository,
            rendered_task=rendered,
            task_policy_source=self.task_policy_path,
            expected_task_policy_sha256=str(self._input("task_policy")["sha256"]),
        )
        state.binding_sha256 = binding_sha256
        return TreatmentApplication(
            rendered_task=rendered,
            provenance={
                "binding_sha256": binding_sha256,
                "condition": request.condition,
                "family_id": AIM_BACKEND_ID,
                "memory": memory_record,
                "task_sha256": task_sha256,
            },
        )

    def _evaluator_environment(self, request: FinalRunRequest) -> dict[str, str]:
        scratch = Path(request.attempt_directory) / "evaluator-scratch"
        if scratch.is_symlink() or not scratch.is_dir():
            raise AimBackendError("Aim evaluator scratch is missing or unsafe")
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
        before = sha256_file(script)
        if before != expected_sha256:
            raise AimBackendError(f"Aim {kind} evaluator hash mismatch")
        argv = [
            str(self.evaluator_python),
            str(script),
            "--repository",
            str(repository.resolve(strict=True)),
            "--timeout-seconds",
            str(_EVALUATOR_INTERNAL_TIMEOUT_SECONDS),
        ]
        try:
            process = subprocess.run(
                argv,
                cwd=Path(request.attempt_directory) / "evaluator-scratch",
                env=self._evaluator_environment(request),
                capture_output=True,
                timeout=_EVALUATOR_PROCESS_TIMEOUT_SECONDS,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return EvaluationResult(
                complete=False,
                passed=None,
                record={"argv": argv, "error": f"{type(error).__name__}: {error}"},
            )
        after = sha256_file(script)
        if after != before or after != expected_sha256:
            raise AimBackendError(f"Aim {kind} evaluator changed during execution")
        self._assert_package_unchanged()
        stdout, stdout_bounded = _bounded_text(process.stdout)
        stderr, stderr_bounded = _bounded_text(process.stderr)
        record: dict[str, Any] = {
            "argv": argv,
            "evaluator_sha256_after": after,
            "evaluator_sha256_before": before,
            "kind": kind,
            "returncode": process.returncode,
            "stderr": stderr,
            "stderr_bounded": stderr_bounded,
            "stdout_bounded": stdout_bounded,
            "stdout_sha256": hashlib.sha256(process.stdout).hexdigest(),
        }
        if not stdout_bounded or not stderr_bounded:
            record["error"] = "Aim evaluator output exceeded the fixed bound"
            return EvaluationResult(complete=False, passed=None, record=record)
        try:
            payload = json.loads(stdout)
        except json.JSONDecodeError as error:
            record["error"] = f"invalid Aim evaluator JSON: {error}"
            return EvaluationResult(complete=False, passed=None, record=record)
        if not isinstance(payload, dict):
            record["error"] = "Aim evaluator output is not an object"
            return EvaluationResult(complete=False, passed=None, record=record)
        record["payload"] = payload
        complete = payload.get("complete")
        passed = payload.get("passed")
        if not isinstance(complete, bool) or (
            complete and not isinstance(passed, bool)
        ):
            record["error"] = "Aim evaluator completion fields are invalid"
            return EvaluationResult(complete=False, passed=None, record=record)
        if process.returncode != (0 if complete else 2):
            record["error"] = "Aim evaluator JSON/exit disagreement"
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
        analysis = self._repository_analysis(state)
        return {
            "analysis": analysis,
            "complete": True,
            "content_digest": repository_content_digest(state.repository).as_record(),
            "git_head": git(
                state.repository, "rev-parse", "HEAD", check=True
            ).stdout.strip(),
            "git_status": git(
                state.repository, "status", "--short", check=True
            ).stdout,
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
        encoded = patch.encode("utf-8")
        _write_new_bytes(Path(request.attempt_directory) / "final.patch", encoded)
        analysis = self._repository_analysis(state)
        return {
            "allowed_paths": analysis["finding"]["allowed_paths_modified"],
            "complete": True,
            "disallowed_paths": analysis["finding"]["disallowed_paths_modified"],
            "pass": analysis["pass"],
            "patch_bytes": len(encoded),
            "patch_sha256": hashlib.sha256(encoded).hexdigest(),
            "repository_available": True,
        }

    def source_integrity(
        self, request: FinalRunRequest, repository: Path | None
    ) -> Mapping[str, Any]:
        self._require_request(request)
        package = self._current_package_digest()
        source = repository_content_digest(self.source_repository)
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
            analysis: Mapping[str, Any] = {
                "pass": False,
                "repository_available": False,
            }
        else:
            analysis = self._repository_analysis(self._require_state(request, repository))
        return {
            "complete": True,
            "oracle_hashes": oracle_hashes,
            "oracles_unchanged": oracle_ok,
            "package_content_digest": package.as_record(),
            "package_unchanged": package == self._package_digest,
            "pass": bool(
                package == self._package_digest
                and source == self._source_digest
                and oracle_ok
                and analysis.get("pass") is True
            ),
            "repository_analysis": analysis,
            "source_content_digest": source.as_record(),
            "source_snapshot_unchanged": source == self._source_digest,
        }

    def environment_cache_integrity(
        self, request: FinalRunRequest
    ) -> Mapping[str, Any]:
        self._require_request(request)
        python_sha256 = sha256_file(self.evaluator_python)
        package_ok = self._current_package_digest() == self._package_digest
        return {
            "cache_scope": "No family-managed dependency cache; evaluator is dependency-free.",
            "complete": True,
            "evaluator_python": str(self.evaluator_python),
            "evaluator_python_sha256": python_sha256,
            "package_unchanged": package_ok,
            "pass": package_ok and python_sha256 == self._evaluator_python_sha256,
            "python_unchanged": python_sha256 == self._evaluator_python_sha256,
        }

    def cleanup_scratch(self, request: FinalRunRequest) -> Mapping[str, Any]:
        self._require_request(request)
        return _safe_remove_scratch(
            Path(request.attempt_directory) / "evaluator-scratch",
            artifact=request.attempt_directory,
        )


def build_aim_backend(
    context: Mapping[str, Any],
    *,
    package_root: Path = AIM_PACKAGE_ROOT,
    evaluator_python: Path | None = None,
) -> AimScientificOperations:
    """Build Aim only after its package has passed the frozen production gate."""

    return AimScientificOperations(
        context,
        package_root=package_root,
        evaluator_python=evaluator_python,
    )


__all__ = [
    "AIM_BACKEND_ID",
    "AIM_PACKAGE_LOGICAL_PATH",
    "AIM_PACKAGE_ROOT",
    "AIM_PACKAGE_SCHEMA",
    "AIM_SOURCE_REVISION",
    "AIM_TARGET_REVISION",
    "AimBackendError",
    "AimScientificOperations",
    "build_aim_backend",
]
