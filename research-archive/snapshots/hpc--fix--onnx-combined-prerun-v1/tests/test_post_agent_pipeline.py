from __future__ import annotations

from pathlib import Path

import pytest

from cmpilot.post_agent_pipeline import (
    MANDATORY_POST_AGENT_STAGES,
    DimensionalClassification,
    PostAgentPipeline,
    analyze_task_repository,
)
from cmpilot.repository_manager import copy_repository_tree
from cmpilot.task_file_policy import calculator_task_policy


ROOT = Path(__file__).parents[1]
SOURCE = ROOT / "tasks" / "smoke_test" / "repository"


def test_analyzer_returns_structured_protected_path_finding(tmp_path: Path) -> None:
    repository = tmp_path / "repository"
    copy_repository_tree(SOURCE, repository)
    (repository / "test_calculator.py").write_text(
        "def test_fake():\n    assert True\n", encoding="utf-8"
    )

    finding = analyze_task_repository(
        source_repository=SOURCE,
        agent_repository=repository,
        task_policy=calculator_task_policy(),
    )

    assert finding.protected_path_violation is True
    assert finding.protected_paths_modified == ("test_calculator.py",)
    assert finding.technical_validity == "fail"
    assert finding.returncode is None


def test_analysis_violation_does_not_skip_mandatory_stages() -> None:
    calls: list[str] = []

    def stage(name: str, value: object = True):
        def run() -> object:
            calls.append(name)
            return value

        return run

    pipeline = PostAgentPipeline(
        analysis=stage("analysis", {"protected_path_violation": True}),
        final_validation=stage("final_validation", {"passed": 3, "failed": 0}),
        integrity=stage("integrity"),
        shutdown=stage("shutdown"),
        preservation=stage("preservation"),
    )

    outcome = pipeline.run()

    assert tuple(calls) == MANDATORY_POST_AGENT_STAGES
    assert outcome.post_agent_analysis_complete is True
    assert outcome.cleanup_complete is True
    assert outcome.artifact_preservation_complete is True
    assert outcome.final_process_exit_chosen is True


def test_analysis_exception_does_not_skip_validation_shutdown_or_preservation() -> None:
    calls: list[str] = []

    def broken_analysis() -> None:
        calls.append("analysis")
        raise RuntimeError("simulated analyzer failure")

    def record(name: str):
        def run() -> bool:
            calls.append(name)
            return True

        return run

    outcome = PostAgentPipeline(
        analysis=broken_analysis,
        final_validation=record("final_validation"),
        integrity=record("integrity"),
        shutdown=record("shutdown"),
        preservation=record("preservation"),
    ).run()

    assert tuple(calls) == MANDATORY_POST_AGENT_STAGES
    assert outcome.stage_results["analysis"].status == "failed"
    assert outcome.stage_results["final_validation"].status == "passed"
    assert outcome.stage_results["shutdown"].status == "passed"
    assert outcome.stage_results["preservation"].status == "passed"
    assert outcome.final_exit_code != 0


def test_final_exit_is_not_available_during_intermediate_stages() -> None:
    observed: list[int | None] = []
    pipeline: PostAgentPipeline

    def observe() -> bool:
        observed.append(pipeline.final_exit_code)
        return True

    pipeline = PostAgentPipeline(
        analysis=observe,
        final_validation=observe,
        integrity=observe,
        shutdown=observe,
        preservation=observe,
    )

    outcome = pipeline.run()

    assert observed == [None, None, None, None, None]
    assert outcome.final_exit_code == 0


def test_incomplete_shutdown_or_preservation_is_a_final_failure() -> None:
    outcome = PostAgentPipeline(
        analysis=lambda: {"technical_validity": "pass"},
        final_validation=lambda: {"passed": 3, "failed": 0},
        integrity=lambda: {"technical_validity": "pass"},
        shutdown=lambda: {"complete": False},
        preservation=lambda: {"complete": False},
    ).run()

    assert outcome.cleanup_complete is False
    assert outcome.artifact_preservation_complete is False
    assert outcome.stage_results["shutdown"].status == "passed"
    assert outcome.stage_results["preservation"].status == "passed"
    assert outcome.final_process_exit_chosen is True
    assert outcome.final_exit_code != 0


def test_pipeline_requires_every_mandatory_callback() -> None:
    with pytest.raises(ValueError, match="mandatory"):
        PostAgentPipeline(
            analysis=lambda: True,
            final_validation=lambda: True,
            integrity=lambda: True,
            shutdown=lambda: True,
            preservation=None,
        )


def test_dimensional_classification_does_not_collapse_capability_and_validity() -> None:
    classification = DimensionalClassification(
        model_capability="demonstrated",
        task_functional_result="pass",
        technical_validity="fail",
        protected_path_violation=True,
        protected_paths_modified=("test_calculator.py",),
        prohibited_command_executed=False,
        external_oracle_result="pass",
        allowed_patch_result="pass",
        post_agent_analysis_complete=True,
        cleanup_complete=True,
    )
