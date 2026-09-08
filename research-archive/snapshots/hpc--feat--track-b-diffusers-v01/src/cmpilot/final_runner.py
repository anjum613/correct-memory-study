"""Model-neutral orchestration for one frozen final-experiment run.

The final six family implementations do not exist yet.  This module therefore
defines the narrow execution boundary they must satisfy without guessing their
repositories, prompts, memories, or evaluators.  Scientific operations own
repository preparation, treatment application, and both evaluations.  A model
executor receives only the already-rendered invocation and may vary serving or
serialization details, never treatment semantics.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import time
from typing import Any, Mapping, Protocol

from .calculator_finalizer import (
    TotalFinalizationOutcome,
    initialize_finalizer_state,
    load_finalizer_state,
    run_total_finalization,
)
from .final_experiment import write_new_canonical_json


FINAL_RUNNER_SCHEMA = "cmpilot-shared-final-runner-v1"

SUCCESS = "SUCCESS"
MODEL_SERVER_FAILURE = "MODEL_SERVER_FAILURE"
MALFORMED_MODEL_RESPONSE = "MALFORMED_MODEL_RESPONSE"
PARSER_REJECTION = "PARSER_REJECTION"
COMMAND_AUTHORIZATION_REJECTION = "COMMAND_AUTHORIZATION_REJECTION"
CONTEXT_EXHAUSTION = "CONTEXT_EXHAUSTION"
STEP_LIMIT = "STEP_LIMIT"
TIMEOUT = "TIMEOUT"
FUNCTIONALITY_TEST_FAILURE = "FUNCTIONALITY_TEST_FAILURE"
RECOVERABLE_EVALUATOR_FAILURE = "RECOVERABLE_EVALUATOR_FAILURE"
REPOSITORY_SETUP_FAILURE = "REPOSITORY_SETUP_FAILURE"
TREATMENT_APPLICATION_FAILURE = "TREATMENT_APPLICATION_FAILURE"
OTHER_TERMINAL_STATE = "OTHER_TERMINAL_STATE"

FINAL_RUN_TERMINATION_REASONS = (
    SUCCESS,
    MODEL_SERVER_FAILURE,
    MALFORMED_MODEL_RESPONSE,
    PARSER_REJECTION,
    COMMAND_AUTHORIZATION_REJECTION,
    CONTEXT_EXHAUSTION,
    STEP_LIMIT,
    TIMEOUT,
    FUNCTIONALITY_TEST_FAILURE,
    RECOVERABLE_EVALUATOR_FAILURE,
    REPOSITORY_SETUP_FAILURE,
    TREATMENT_APPLICATION_FAILURE,
    OTHER_TERMINAL_STATE,
)


class FinalRunnerError(RuntimeError):
    """A shared-run input or lifecycle invariant is invalid."""


class FinalRunPhaseError(RuntimeError):
    """A phase failed with an explicit terminal classification."""

    def __init__(self, termination_reason: str, message: str):
        if termination_reason not in FINAL_RUN_TERMINATION_REASONS:
            raise FinalRunnerError(
                f"unsupported final-run termination reason: {termination_reason}"
            )
        super().__init__(message)
        self.termination_reason = termination_reason


def _json_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): item for key, item in value.items()}


@dataclass(frozen=True)
class FinalRunRequest:
    """Scientifically relevant inputs for exactly one immutable attempt."""

    family: Mapping[str, Any]
    condition: str
    model_profile_key: str
    model_profile: Mapping[str, Any]
    seed: int
    run: Mapping[str, Any]
    attempt_directory: Path
    job_id: str
    attempt_id: str

    def __post_init__(self) -> None:
        run_id = self.run.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            raise FinalRunnerError("run identity must contain a non-empty run_id")
        if self.family.get("family_id") != self.run.get("family_id"):
            raise FinalRunnerError("family manifest differs from the run identity")
        if self.condition != self.run.get("condition"):
            raise FinalRunnerError("condition differs from the run identity")
        if self.model_profile_key != self.run.get("model_profile"):
            raise FinalRunnerError("model profile differs from the run identity")
        if self.model_profile.get("model_id") != self.run.get("model_id"):
            raise FinalRunnerError("model identity differs from the run identity")
        if self.model_profile.get("revision") != self.run.get("model_revision"):
            raise FinalRunnerError("model revision differs from the run identity")
        if isinstance(self.seed, bool) or not isinstance(self.seed, int) or self.seed < 0:
            raise FinalRunnerError("seed must be a non-negative integer")
        if self.seed != self.run.get("seed"):
            raise FinalRunnerError("seed differs from the run identity")
        for label, value in (("job_id", self.job_id), ("attempt_id", self.attempt_id)):
            if not value or "/" in value or value in {".", ".."}:
                raise FinalRunnerError(f"{label} must be a safe non-empty path component")
        attempt = Path(self.attempt_directory)
        if attempt.is_symlink() or not attempt.is_dir():
            raise FinalRunnerError(
                f"attempt directory must be an existing real directory: {attempt}"
            )

    @property
    def run_id(self) -> str:
        return str(self.run["run_id"])

    def identity_record(self) -> dict[str, Any]:
        return {
            "attempt_id": self.attempt_id,
            "condition": self.condition,
            "experiment_manifest_sha256": self.run.get(
                "experiment_manifest_sha256"
            ),
            "family_id": self.family["family_id"],
            "identity_sha256": self.run.get("identity_sha256"),
            "job_id": self.job_id,
            "model_id": self.model_profile["model_id"],
            "model_profile": self.model_profile_key,
            "model_revision": self.model_profile["revision"],
            "run_id": self.run_id,
            "schema": FINAL_RUNNER_SCHEMA,
            "seed": self.seed,
        }


@dataclass(frozen=True)
class TreatmentApplication:
    """The exact model input produced by model-neutral treatment logic."""

    rendered_task: str
    provenance: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.rendered_task, str) or not self.rendered_task:
            raise FinalRunnerError("treatment must render a non-empty task")

    def as_dict(self) -> dict[str, Any]:
        return {
            "provenance": _json_mapping(self.provenance),
            "rendered_task": self.rendered_task,
        }


@dataclass(frozen=True)
class AgentInvocation:
    """Only data a model-specific executor may receive from the shared path."""

    run_id: str
    model_profile_key: str
    model_profile: Mapping[str, Any]
    seed: int
    repository: Path
    rendered_task: str
    attempt_directory: Path


@dataclass(frozen=True)
class AgentExecutionResult:
    termination_reason: str
    technical_validity: bool
    action_count: int
    model_request_count: int
    elapsed_seconds: float
    token_usage: Mapping[str, Any] | None
    record: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.termination_reason not in FINAL_RUN_TERMINATION_REASONS:
            raise FinalRunnerError(
                "model executor returned an unsupported termination reason: "
                f"{self.termination_reason}"
            )
        for label, value in (
            ("action_count", self.action_count),
            ("model_request_count", self.model_request_count),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise FinalRunnerError(f"{label} must be a non-negative integer")
        if self.elapsed_seconds < 0:
            raise FinalRunnerError("elapsed_seconds must not be negative")

    def as_dict(self) -> dict[str, Any]:
        return {
            "action_count": self.action_count,
            "elapsed_seconds": self.elapsed_seconds,
            "model_request_count": self.model_request_count,
            "record": _json_mapping(self.record),
            "technical_validity": self.technical_validity,
            "termination_reason": self.termination_reason,
            "token_usage": (
                None if self.token_usage is None else _json_mapping(self.token_usage)
            ),
        }


@dataclass(frozen=True)
class EvaluationResult:
    """Separates evaluator completion from the observed scientific outcome."""

    complete: bool
    passed: bool | None
    record: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.complete and not isinstance(self.passed, bool):
            raise FinalRunnerError("a completed evaluation requires a Boolean outcome")
        if not self.complete and self.passed is not None:
            raise FinalRunnerError("an incomplete evaluation cannot claim an outcome")

    def as_dict(self) -> dict[str, Any]:
        return {
            "complete": self.complete,
            "pass": self.passed,
            "record": _json_mapping(self.record),
        }


class ModelExecutor(Protocol):
    """Serving/serialization boundary; it has no treatment or evaluator methods."""

    def execute_agent(self, invocation: AgentInvocation) -> AgentExecutionResult: ...

    def shutdown(self) -> Mapping[str, Any]: ...


class ScientificOperations(Protocol):
    """Family-specific operations invoked only by the shared coordinator."""

    def setup_repository(self, request: FinalRunRequest) -> Path: ...

    def apply_treatment(
        self, request: FinalRunRequest, repository: Path
    ) -> TreatmentApplication: ...

    def evaluate_functionality(
        self,
        request: FinalRunRequest,
        repository: Path,
        execution: AgentExecutionResult,
    ) -> EvaluationResult: ...

    def evaluate_security_witness(
        self,
        request: FinalRunRequest,
        repository: Path,
        execution: AgentExecutionResult,
    ) -> EvaluationResult: ...

    def capture_repository(
        self, request: FinalRunRequest, repository: Path | None
    ) -> Mapping[str, Any]: ...

    def generate_patch(
        self, request: FinalRunRequest, repository: Path | None
    ) -> Mapping[str, Any]: ...

    def source_integrity(
        self, request: FinalRunRequest, repository: Path | None
    ) -> Mapping[str, Any]: ...

    def environment_cache_integrity(
        self, request: FinalRunRequest
    ) -> Mapping[str, Any]: ...

    def cleanup_scratch(self, request: FinalRunRequest) -> Mapping[str, Any]: ...


def _evaluation_failure(error: BaseException) -> EvaluationResult:
    return EvaluationResult(
        complete=False,
        passed=None,
        record={"error": f"{type(error).__name__}: {error}"},
    )


def _final_classification(
    *, technical_validity: bool, functionality: EvaluationResult, witness: EvaluationResult
) -> str:
    if not technical_validity or not functionality.complete or not witness.complete:
        return "TECHNICAL_INVALID"
    if functionality.passed is False:
        return "FUNCTIONALITY_FAIL"
    return (
        "FUNCTIONALITY_PASS_WITNESS_PASS"
        if witness.passed is True
        else "FUNCTIONALITY_PASS_WITNESS_FAIL"
    )


def run_final_run(
    request: FinalRunRequest,
    *,
    scientific: ScientificOperations,
    model: ModelExecutor,
) -> TotalFinalizationOutcome:
    """Run every scientific phase once and always invoke the total finalizer."""

    attempt = Path(request.attempt_directory)
    state_path = attempt / "finalizer-state.json"
    if state_path.exists():
        state = load_finalizer_state(state_path)
        if state.run_id != request.run_id:
            raise FinalRunnerError("reserved finalizer state belongs to another run")
        if state.final_exit_code is not None or any(
            status != "pending" for status in state.stage_statuses.values()
        ):
            raise FinalRunnerError("reserved finalizer state was already consumed")
    else:
        initialize_finalizer_state(state_path, run_id=request.run_id)
    write_new_canonical_json(attempt / "run-request.json", request.identity_record())
    started = time.perf_counter()

    repository: Path | None = None
    treatment: TreatmentApplication | None = None
    execution = AgentExecutionResult(
        termination_reason=OTHER_TERMINAL_STATE,
        technical_validity=False,
        action_count=0,
        model_request_count=0,
        elapsed_seconds=0.0,
        token_usage=None,
        record={"started": False},
    )
    termination_reason = OTHER_TERMINAL_STATE

    try:
        repository = scientific.setup_repository(request)
        if repository.is_symlink() or not repository.is_dir():
            raise FinalRunnerError(
                f"repository setup did not return a real directory: {repository}"
            )
    except BaseException as error:
        termination_reason = (
            error.termination_reason
            if isinstance(error, FinalRunPhaseError)
            else REPOSITORY_SETUP_FAILURE
        )
        execution = AgentExecutionResult(
            termination_reason=termination_reason,
            technical_validity=False,
            action_count=0,
            model_request_count=0,
            elapsed_seconds=time.perf_counter() - started,
            token_usage=None,
            record={"error": f"{type(error).__name__}: {error}", "phase": "repository_setup"},
        )

    if repository is not None:
        try:
            treatment = scientific.apply_treatment(request, repository)
            write_new_canonical_json(
                attempt / "treatment-application.json", treatment.as_dict()
            )
        except BaseException as error:
            termination_reason = (
                error.termination_reason
                if isinstance(error, FinalRunPhaseError)
                else TREATMENT_APPLICATION_FAILURE
            )
            execution = AgentExecutionResult(
                termination_reason=termination_reason,
                technical_validity=False,
                action_count=0,
                model_request_count=0,
                elapsed_seconds=time.perf_counter() - started,
                token_usage=None,
                record={"error": f"{type(error).__name__}: {error}", "phase": "treatment"},
            )

    if repository is not None and treatment is not None:
        invocation = AgentInvocation(
            run_id=request.run_id,
            model_profile_key=request.model_profile_key,
            model_profile=request.model_profile,
            seed=request.seed,
            repository=repository,
            rendered_task=treatment.rendered_task,
            attempt_directory=attempt,
        )
        try:
            execution = model.execute_agent(invocation)
        except BaseException as error:
            termination_reason = (
                error.termination_reason
                if isinstance(error, FinalRunPhaseError)
                else MODEL_SERVER_FAILURE
            )
            execution = AgentExecutionResult(
                termination_reason=termination_reason,
                technical_validity=False,
                action_count=0,
                model_request_count=0,
                elapsed_seconds=time.perf_counter() - started,
                token_usage=None,
                record={"error": f"{type(error).__name__}: {error}", "phase": "agent"},
            )
        else:
            termination_reason = execution.termination_reason

    write_new_canonical_json(attempt / "agent-execution.json", execution.as_dict())

    if repository is None:
        functionality = _evaluation_failure(
            FinalRunnerError("functionality evaluation unavailable without repository")
        )
        witness = _evaluation_failure(
            FinalRunnerError("security witness unavailable without repository")
        )
    else:
        try:
            functionality = scientific.evaluate_functionality(
                request, repository, execution
            )
        except BaseException as error:
            functionality = _evaluation_failure(error)
        try:
            witness = scientific.evaluate_security_witness(
                request, repository, execution
            )
        except BaseException as error:
            witness = _evaluation_failure(error)

    write_new_canonical_json(
        attempt / "functionality-evaluation.json", functionality.as_dict()
    )
    write_new_canonical_json(
        attempt / "security-witness-evaluation.json", witness.as_dict()
    )

    if (
        not functionality.complete or not witness.complete
    ) and termination_reason == SUCCESS:
        termination_reason = RECOVERABLE_EVALUATOR_FAILURE
    elif termination_reason == SUCCESS and functionality.passed is False:
        termination_reason = FUNCTIONALITY_TEST_FAILURE

    elapsed = time.perf_counter() - started
    technical = bool(
        execution.technical_validity and functionality.complete and witness.complete
    )
    final_classification = _final_classification(
        technical_validity=technical,
        functionality=functionality,
        witness=witness,
    )

    def evaluation_artifacts() -> dict[str, Any]:
        return {
            "complete": functionality.complete and witness.complete,
            "functionality": functionality.as_dict(),
            "security_witness": witness.as_dict(),
        }

    callbacks = {
        "final_repository_capture": lambda: scientific.capture_repository(
            request, repository
        ),
        "patch_generation": lambda: scientific.generate_patch(request, repository),
        "immutable_oracle": evaluation_artifacts,
        "source_integrity": lambda: scientific.source_integrity(request, repository),
        "project_environment_cache_integrity": lambda: (
            scientific.environment_cache_integrity(request)
        ),
        "shutdown": model.shutdown,
        "scratch_cleanup": lambda: scientific.cleanup_scratch(request),
        "performance_summary": lambda: {
            "action_count": execution.action_count,
            "complete": True,
            "elapsed_seconds": elapsed,
            "model_request_count": execution.model_request_count,
            "token_usage": (
                None
                if execution.token_usage is None
                else _json_mapping(execution.token_usage)
            ),
        },
    }
    base_result = {
        "action_count": execution.action_count,
        "attempt_id": request.attempt_id,
        "condition": request.condition,
        "elapsed_seconds": elapsed,
        "experiment_manifest_sha256": request.run.get(
            "experiment_manifest_sha256"
        ),
        "family_id": request.family["family_id"],
        "final_classification": final_classification,
        "functionality_result": functionality.as_dict(),
        "identity_sha256": request.run.get("identity_sha256"),
        "job_id": request.job_id,
        "memory_provenance_identifier": request.run.get(
            "memory_provenance_manifest_sha256"
        ),
        "model_id": request.model_profile["model_id"],
        "model_profile": request.model_profile_key,
        "model_request_count": execution.model_request_count,
        "model_revision": request.model_profile["revision"],
        "repetition": request.run.get("repetition"),
        "run_id": request.run_id,
        "security_witness_result": witness.as_dict(),
        "seed": request.seed,
        "task_revision": request.run.get("target_revision"),
        "termination_reason": termination_reason,
        "token_usage": (
            None
            if execution.token_usage is None
            else _json_mapping(execution.token_usage)
        ),
    }
    return run_total_finalization(
        state_path=state_path,
        artifact_directory=attempt,
        termination_reason=termination_reason,
        callbacks=callbacks,
        success_label="FINAL_RUN_TERMINAL_RECORDED",
        technical_failure_label="FINAL_RUN_TECHNICAL_INVALID",
        requested_exit_code=0 if technical else 1,
        initial_technical_validity=technical,
        base_result=base_result,
        classification_dimensions={
            "condition": request.condition,
            "family_id": request.family["family_id"],
            "final_classification": final_classification,
            "functionality": functionality.passed,
            "security_witness": witness.passed,
        },
    )


__all__ = [
    "AgentExecutionResult",
    "AgentInvocation",
    "COMMAND_AUTHORIZATION_REJECTION",
    "CONTEXT_EXHAUSTION",
    "EvaluationResult",
    "FINAL_RUNNER_SCHEMA",
    "FINAL_RUN_TERMINATION_REASONS",
    "FUNCTIONALITY_TEST_FAILURE",
    "FinalRunPhaseError",
    "FinalRunRequest",
    "FinalRunnerError",
    "MALFORMED_MODEL_RESPONSE",
    "MODEL_SERVER_FAILURE",
    "ModelExecutor",
    "OTHER_TERMINAL_STATE",
    "PARSER_REJECTION",
    "RECOVERABLE_EVALUATOR_FAILURE",
    "REPOSITORY_SETUP_FAILURE",
    "STEP_LIMIT",
    "SUCCESS",
    "ScientificOperations",
    "TIMEOUT",
    "TREATMENT_APPLICATION_FAILURE",
    "TreatmentApplication",
    "run_final_run",
]
