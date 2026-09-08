from __future__ import annotations

import json
from pathlib import Path

import pytest

from cmpilot.calculator_finalizer import (
    initialize_finalizer_state,
    validate_total_finalization_artifacts,
)
from cmpilot.final_runner import (
    AgentExecutionResult,
    AgentInvocation,
    COMMAND_AUTHORIZATION_REJECTION,
    CONTEXT_EXHAUSTION,
    EvaluationResult,
    FINAL_RUN_TERMINATION_REASONS,
    FUNCTIONALITY_TEST_FAILURE,
    FinalRunRequest,
    MALFORMED_MODEL_RESPONSE,
    MODEL_SERVER_FAILURE,
    OTHER_TERMINAL_STATE,
    PARSER_REJECTION,
    RECOVERABLE_EVALUATOR_FAILURE,
    REPOSITORY_SETUP_FAILURE,
    STEP_LIMIT,
    SUCCESS,
    TIMEOUT,
    TREATMENT_APPLICATION_FAILURE,
    TreatmentApplication,
    run_final_run,
)


def _request(tmp_path: Path) -> FinalRunRequest:
    attempt = tmp_path / "run-a" / "attempts" / "slurm-91-0"
    attempt.mkdir(parents=True)
    family = {"family_id": "synthetic-family"}
    profile = {
        "model_id": "synthetic/model",
        "revision": "a" * 40,
    }
    run = {
        "condition": "NO_MEMORY",
        "experiment_manifest_sha256": "b" * 64,
        "family_id": "synthetic-family",
        "identity_sha256": "c" * 64,
        "memory_provenance_manifest_sha256": None,
        "model_id": "synthetic/model",
        "model_profile": "synthetic-profile",
        "model_revision": "a" * 40,
        "repetition": 1,
        "run_id": "run-synthetic",
        "seed": 17,
        "target_revision": "d" * 40,
    }
    return FinalRunRequest(
        family=family,
        condition="NO_MEMORY",
        model_profile_key="synthetic-profile",
        model_profile=profile,
        seed=17,
        run=run,
        attempt_directory=attempt,
        job_id="91",
        attempt_id="slurm-91-0",
    )


class SyntheticScientificOperations:
    def __init__(
        self,
        calls: list[str],
        *,
        functionality: bool = True,
        witness: bool = True,
        evaluator_error: str | None = None,
        setup_error: bool = False,
        treatment_error: bool = False,
    ) -> None:
        self.calls = calls
        self.functionality = functionality
        self.witness = witness
        self.evaluator_error = evaluator_error
        self.setup_error = setup_error
        self.treatment_error = treatment_error

    def setup_repository(self, request: FinalRunRequest) -> Path:
        self.calls.append("setup_repository")
        if self.setup_error:
            raise RuntimeError("synthetic setup failure")
        repository = request.attempt_directory / "working-copy"
        repository.mkdir()
        (repository / "task.py").write_text("value = 0\n", encoding="utf-8")
        return repository

    def apply_treatment(
        self, request: FinalRunRequest, repository: Path
    ) -> TreatmentApplication:
        self.calls.append("apply_treatment")
        if self.treatment_error:
            raise RuntimeError("synthetic treatment failure")
        return TreatmentApplication(
            rendered_task="Synthetic unit-test task; no real family.",
            provenance={"condition": request.condition, "synthetic": True},
        )

    def evaluate_functionality(
        self,
        request: FinalRunRequest,
        repository: Path,
        execution: AgentExecutionResult,
    ) -> EvaluationResult:
        self.calls.append("evaluate_functionality")
        if self.evaluator_error == "functionality":
            raise RuntimeError("synthetic functionality crash")
        return EvaluationResult(
            complete=True,
            passed=self.functionality,
            record={"fixture": "synthetic", "kind": "functionality"},
        )

    def evaluate_security_witness(
        self,
        request: FinalRunRequest,
        repository: Path,
        execution: AgentExecutionResult,
    ) -> EvaluationResult:
        self.calls.append("evaluate_security_witness")
        if self.evaluator_error == "witness":
            raise RuntimeError("synthetic witness crash")
        return EvaluationResult(
            complete=True,
            passed=self.witness,
            record={"fixture": "synthetic", "kind": "witness"},
        )

    def capture_repository(
        self, request: FinalRunRequest, repository: Path | None
    ) -> dict[str, object]:
        self.calls.append("capture_repository")
        return {"complete": True, "repository_available": repository is not None}

    def generate_patch(
        self, request: FinalRunRequest, repository: Path | None
    ) -> dict[str, object]:
        self.calls.append("generate_patch")
        return {"complete": True, "patch": ""}

    def source_integrity(
        self, request: FinalRunRequest, repository: Path | None
    ) -> dict[str, object]:
        self.calls.append("source_integrity")
        return {"pass": True}

    def environment_cache_integrity(
        self, request: FinalRunRequest
    ) -> dict[str, object]:
        self.calls.append("environment_cache_integrity")
        return {"pass": True}

    def cleanup_scratch(self, request: FinalRunRequest) -> dict[str, object]:
        self.calls.append("cleanup_scratch")
        return {"complete": True}


class SyntheticModelExecutor:
    def __init__(
        self,
        calls: list[str],
        *,
        termination_reason: str = SUCCESS,
        technical_validity: bool = True,
        raises: bool = False,
    ) -> None:
        self.calls = calls
        self.termination_reason = termination_reason
        self.technical_validity = technical_validity
        self.raises = raises
        self.invocation: AgentInvocation | None = None

    def execute_agent(self, invocation: AgentInvocation) -> AgentExecutionResult:
        self.calls.append("execute_agent")
        self.invocation = invocation
        if self.raises:
            raise RuntimeError("synthetic server failure")
        return AgentExecutionResult(
            termination_reason=self.termination_reason,
            technical_validity=self.technical_validity,
            action_count=2,
            model_request_count=3,
            elapsed_seconds=0.25,
            token_usage={"prompt": 11, "completion": 7, "total": 18},
            record={"fixture": "synthetic"},
        )

    def shutdown(self) -> dict[str, object]:
        self.calls.append("shutdown")
        return {"complete": True, "pass": True}


def _result(path: Path) -> dict[str, object]:
    return json.loads((path / "result.json").read_text(encoding="utf-8"))


def test_shared_path_owns_treatment_evaluators_and_total_finalization(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    request = _request(tmp_path)
    scientific = SyntheticScientificOperations(calls, witness=False)
    model = SyntheticModelExecutor(calls)

    outcome = run_final_run(request, scientific=scientific, model=model)

    assert calls[:5] == [
        "setup_repository",
        "apply_treatment",
        "execute_agent",
        "evaluate_functionality",
        "evaluate_security_witness",
    ]
    assert model.invocation is not None
    assert not hasattr(model.invocation, "family")
    assert not hasattr(model.invocation, "condition")
    assert model.invocation.rendered_task.startswith("Synthetic unit-test")
    assert outcome.state.final_exit_code == 0
    assert validate_total_finalization_artifacts(request.attempt_directory)["pass"]
    result = _result(request.attempt_directory)
    assert result["run_id"] == "run-synthetic"
    assert result["action_count"] == 2
    assert result["model_request_count"] == 3
    assert result["functionality_result"]["pass"] is True
    assert result["security_witness_result"]["pass"] is False
    assert result["final_classification"] == "FUNCTIONALITY_PASS_WITNESS_FAIL"
    assert result["termination_reason"] == SUCCESS


@pytest.mark.parametrize(
    "termination_reason",
    [
        SUCCESS,
        MODEL_SERVER_FAILURE,
        MALFORMED_MODEL_RESPONSE,
        PARSER_REJECTION,
        COMMAND_AUTHORIZATION_REJECTION,
        CONTEXT_EXHAUSTION,
        STEP_LIMIT,
        TIMEOUT,
        FUNCTIONALITY_TEST_FAILURE,
        OTHER_TERMINAL_STATE,
    ],
)
def test_every_model_terminal_state_produces_machine_readable_total_artifacts(
    tmp_path: Path, termination_reason: str
) -> None:
    request = _request(tmp_path / termination_reason.casefold())
    calls: list[str] = []

    outcome = run_final_run(
        request,
        scientific=SyntheticScientificOperations(calls),
        model=SyntheticModelExecutor(calls, termination_reason=termination_reason),
    )

    assert outcome.state.final_exit_chosen_after_all_stages is True
    assert validate_total_finalization_artifacts(request.attempt_directory)["pass"]
    assert _result(request.attempt_directory)["termination_reason"] == (
        termination_reason
    )


def test_functionality_failure_is_a_completed_objective_model_outcome(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)

    outcome = run_final_run(
        request,
        scientific=SyntheticScientificOperations([], functionality=False),
        model=SyntheticModelExecutor([]),
    )

    result = _result(request.attempt_directory)
    assert result["termination_reason"] == FUNCTIONALITY_TEST_FAILURE
    assert result["final_classification"] == "FUNCTIONALITY_FAIL"
    assert result["technical_validity"] == "pass"
    assert outcome.state.final_exit_code == 0


def test_recoverable_evaluator_failure_still_runs_witness_and_finalizer(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    request = _request(tmp_path)

    outcome = run_final_run(
        request,
        scientific=SyntheticScientificOperations(
            calls, evaluator_error="functionality"
        ),
        model=SyntheticModelExecutor(calls),
    )

    assert "evaluate_security_witness" in calls
    assert calls.index("evaluate_security_witness") > calls.index(
        "evaluate_functionality"
    )
    assert "shutdown" in calls
    assert "cleanup_scratch" in calls
    result = _result(request.attempt_directory)
    assert result["termination_reason"] == RECOVERABLE_EVALUATOR_FAILURE
    assert result["functionality_result"]["complete"] is False
    assert result["security_witness_result"]["complete"] is True
    assert outcome.state.final_exit_chosen_after_all_stages is True
    assert outcome.state.final_exit_code == 1


def test_evaluator_failure_does_not_mask_the_primary_model_failure(
    tmp_path: Path,
) -> None:
    request = _request(tmp_path)

    outcome = run_final_run(
        request,
        scientific=SyntheticScientificOperations(
            [], evaluator_error="functionality"
        ),
        model=SyntheticModelExecutor(
            [], termination_reason=PARSER_REJECTION, technical_validity=False
        ),
    )

    result = _result(request.attempt_directory)
    assert result["termination_reason"] == PARSER_REJECTION
    assert result["functionality_result"]["complete"] is False
    assert outcome.state.final_exit_code == 1


def test_genuine_startup_failure_remains_technical_invalid_and_finalizes(
    tmp_path: Path,
) -> None:
    calls: list[str] = []
    request = _request(tmp_path)

    outcome = run_final_run(
        request,
        scientific=SyntheticScientificOperations(calls),
        model=SyntheticModelExecutor(calls, raises=True),
    )

    result = _result(request.attempt_directory)
    classification = json.loads(
        (request.attempt_directory / "classification.json").read_text()
    )
    assert result["termination_reason"] == MODEL_SERVER_FAILURE
    assert result["technical_validity"] == "fail"
    assert result["final_classification"] == "TECHNICAL_INVALID"
    assert result["action_count"] == 0
    assert result["model_request_count"] == 0
    assert classification["label"] == "FINAL_RUN_TECHNICAL_INVALID"
    assert "shutdown" in calls
    assert "cleanup_scratch" in calls
    assert outcome.state.final_exit_chosen_after_all_stages is True
    assert outcome.state.final_exit_code == 1
    assert validate_total_finalization_artifacts(request.attempt_directory)["pass"]


@pytest.mark.parametrize(
    ("setup_error", "treatment_error", "reason"),
    [
        (True, False, REPOSITORY_SETUP_FAILURE),
        (False, True, TREATMENT_APPLICATION_FAILURE),
    ],
)
def test_pre_agent_failure_still_finalizes_and_preserves_logs(
    tmp_path: Path,
    setup_error: bool,
    treatment_error: bool,
    reason: str,
) -> None:
    calls: list[str] = []
    request = _request(tmp_path)

    outcome = run_final_run(
        request,
        scientific=SyntheticScientificOperations(
            calls, setup_error=setup_error, treatment_error=treatment_error
        ),
        model=SyntheticModelExecutor(calls),
    )

    assert "shutdown" in calls
    assert "cleanup_scratch" in calls
    result = _result(request.attempt_directory)
    assert result["termination_reason"] == reason
    agent = json.loads(
        (request.attempt_directory / "agent-execution.json").read_text()
    )
    assert agent["termination_reason"] == reason
    assert outcome.state.final_exit_chosen_after_all_stages is True


def test_attempt_evidence_is_never_overwritten(tmp_path: Path) -> None:
    request = _request(tmp_path)
    run_final_run(
        request,
        scientific=SyntheticScientificOperations([]),
        model=SyntheticModelExecutor([]),
    )

    with pytest.raises(RuntimeError, match="already consumed"):
        run_final_run(
            request,
            scientific=SyntheticScientificOperations([]),
            model=SyntheticModelExecutor([]),
        )


def test_shared_runner_consumes_a_pending_atomic_reservation(tmp_path: Path) -> None:
    request = _request(tmp_path)
    initialize_finalizer_state(
        request.attempt_directory / "finalizer-state.json", run_id=request.run_id
    )

    outcome = run_final_run(
        request,
        scientific=SyntheticScientificOperations([]),
        model=SyntheticModelExecutor([]),
    )

    assert outcome.state.final_exit_code == 0
    assert validate_total_finalization_artifacts(request.attempt_directory)["pass"]


def test_terminal_inventory_covers_every_required_failure_class() -> None:
    assert set(
        (
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
            OTHER_TERMINAL_STATE,
        )
    ).issubset(FINAL_RUN_TERMINATION_REASONS)
