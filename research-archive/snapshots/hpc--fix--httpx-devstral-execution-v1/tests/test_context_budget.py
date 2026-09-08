from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import textwrap

import pytest

from cmpilot.integrations.miniswe.context_budget import (
    CONFIGURED_COMPLETION_LIMIT,
    CONTEXT_BUDGET_EXHAUSTED,
    CONTEXT_LIMIT,
    CONTEXT_SAFETY_MARGIN,
    MINIMUM_USEFUL_COMPLETION,
    calculate_request_budget,
)
from cmpilot.mini_swe_adapter import write_adapter
from cmpilot.post_agent_pipeline import MANDATORY_POST_AGENT_STAGES, PostAgentPipeline


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "job_25642_request_15.json"
DEFAULT_MINI_PY = Path(
    "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
)


def _mini_python() -> Path:
    return Path(os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PY))


def test_job_25642_budget_is_clamped_to_the_frozen_context_limit() -> None:
    budget = calculate_request_budget(prompt_tokens=3696)

    assert budget.configured_completion_limit == CONFIGURED_COMPLETION_LIMIT == 512
    assert budget.context_limit == CONTEXT_LIMIT == 4096
    assert budget.safety_margin == CONTEXT_SAFETY_MARGIN == 32
    assert budget.minimum_useful_completion == MINIMUM_USEFUL_COMPLETION == 64
    assert budget.available_completion == 368
    assert budget.effective_completion_limit == 368
    assert budget.emitted_request_token_ceiling == 4064
    assert budget.total_possible_with_reserve == 4096
    assert budget.http_request_allowed is True
    assert budget.prompt_tokens + budget.effective_completion_limit + 32 <= 4096
    assert budget.prompt_tokens + 512 > 4096


def test_small_prompt_retains_configured_completion_allowance() -> None:
    budget = calculate_request_budget(prompt_tokens=100)

    assert budget.effective_completion_limit == 512
    assert budget.total_possible_with_reserve == 644
    assert budget.emitted_request_token_ceiling == 612
    assert budget.http_request_allowed is True


def test_near_limit_prompt_uses_minimum_completion_exactly() -> None:
    budget = calculate_request_budget(prompt_tokens=4000)

    assert budget.available_completion == 64
    assert budget.effective_completion_limit == 64
    assert budget.total_possible_with_reserve == 4096
    assert budget.emitted_request_token_ceiling == 4064
    assert budget.http_request_allowed is True


def test_context_exhaustion_is_a_pretransport_trajectory_outcome() -> None:
    budget = calculate_request_budget(prompt_tokens=4001)

    assert budget.available_completion == 63
    assert budget.effective_completion_limit == 63
    assert budget.http_request_allowed is False
    assert budget.termination_reason == CONTEXT_BUDGET_EXHAUSTED


def test_exact_job_25642_messages_use_pinned_template_and_guard_transport(
    tmp_path: Path,
) -> None:
    mini_python = _mini_python()
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    write_adapter(tmp_path / "mini_swe_adapter.py")
    script = r'''
        import json
        import os
        from pathlib import Path

        from cmpilot_context_budget import (
            ContextBudgetExhausted,
            ExactQwenChatTokenCounter,
        )
        from cmpilot_openai_transport import CompletionResult
        from cmpilot_vllm_text_model import VllmTextModel

        fixture = json.loads(Path(os.environ["REQUEST_FIXTURE"]).read_text())
        tokenizer = ExactQwenChatTokenCounter(
            Path(os.environ["PINNED_TOKENIZER"])
        )
        count = tokenizer.count(fixture["messages"])
        assert count == fixture["observed_prompt_tokens"] == 3696

        class SpyTransport:
            def __init__(self):
                self.calls = []

            def complete(self, messages, **kwargs):
                self.calls.append({"messages": messages, **kwargs})
                response = {
                    "choices": [{
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }],
                    "usage": {"prompt_tokens": count, "completion_tokens": 1},
                }
                return CompletionResult(
                    body=response,
                    raw_body=json.dumps(response),
                    status_code=200,
                    request={"messages": messages, **kwargs},
                    request_sha256="request",
                    response_sha256="response",
                    excluded_message_paths=(),
                )

        transport_path = Path(os.environ["TRANSPORT_ARTIFACT"])
        budget_path = Path(os.environ["BUDGET_ARTIFACT"])
        model = VllmTextModel(
            model_name="pinned-model",
            base_url="http://127.0.0.1:9/v1",
            tokenizer_path=Path(os.environ["PINNED_TOKENIZER"]),
            transport_artifact_path=transport_path,
            request_budget_artifact_path=budget_path,
        )
        spy = SpyTransport()
        model.transport = spy
        model._request(fixture["messages"])
        assert len(spy.calls) == 1
        assert spy.calls[0]["max_tokens"] == 368
        emitted = json.loads(budget_path.read_text().splitlines()[0])
        assert emitted["token_budget"]["prompt_tokens"] == 3696
        assert emitted["token_budget"]["total_possible_with_reserve"] == 4096
        assert emitted["tokenizer"]["chat_template_source"] == "tokenizer_config.json"

        class FixedCounter:
            identity = {"kind": "fixed-test-counter"}
            def count(self, messages):
                return 4001

        model._token_counter = FixedCounter()
        try:
            model._request([{"role": "user", "content": "near limit"}])
        except ContextBudgetExhausted as error:
            assert error.budget.termination_reason == "CONTEXT_BUDGET_EXHAUSTED"
            assert error.artifact_record()["http_request_sent"] is False
        else:
            raise AssertionError("context exhaustion was not raised")
        assert len(spy.calls) == 1
        records = [json.loads(line) for line in transport_path.read_text().splitlines()]
        assert records[-1]["classification"] == "context_budget_exhausted"
        assert records[-1]["http_request_sent"] is False
        print(json.dumps({
            "exact_prompt_tokens": count,
            "maximum_generated_request_size": 4096,
            "transport_calls": len(spy.calls),
            "context_exhaustion_http_calls": 0,
        }, sort_keys=True))
    '''
    environment = {
        **os.environ,
        "PYTHONPATH": str(tmp_path),
        "MSWEA_SILENT_STARTUP": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "REQUEST_FIXTURE": str(FIXTURE),
        "PINNED_TOKENIZER": (
            "/home/s224049759/model-cache/huggingface/hub/"
            "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
            "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
        ),
        "TRANSPORT_ARTIFACT": str(tmp_path / "transport.jsonl"),
        "BUDGET_ARTIFACT": str(tmp_path / "budgets.jsonl"),
    }
    result = subprocess.run(
        [str(mini_python), "-c", textwrap.dedent(script)],
        cwd=ROOT,
        env=environment,
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert evidence == {
        "context_exhaustion_http_calls": 0,
        "exact_prompt_tokens": 3696,
        "maximum_generated_request_size": 4096,
        "transport_calls": 1,
    }


def test_context_exhaustion_agent_exit_still_allows_full_post_agent_pipeline(
    tmp_path: Path,
) -> None:
    mini_python = _mini_python()
    if not mini_python.is_file():
        pytest.skip("dedicated mini-SWE-agent environment is unavailable")
    runtime = tmp_path / "runtime"
    runtime.mkdir()
    write_adapter(runtime / "mini_swe_adapter.py")
    repository = tmp_path / "repository"
    repository.mkdir()
    (repository / "calculator.py").write_text("raise NotImplementedError\n")
    (repository / "test_calculator.py").write_text("def test_visible(): pass\n")
    trajectory = tmp_path / "trajectory.json"
    script = r'''
        import json
        import os
        from pathlib import Path

        from cmpilot_action_protocol import INITIAL_SYSTEM_TEMPLATE, INSTANCE_TEMPLATE
        from cmpilot_context_budget import ContextBudgetExhausted, calculate_request_budget
        from cmpilot_hardened_agent import HardenedDefaultAgent

        class ExhaustedModel:
            def query(self, messages):
                raise ContextBudgetExhausted(
                    calculate_request_budget(prompt_tokens=4001)
                )
            def format_message(self, **kwargs):
                return kwargs
            def get_template_vars(self, **kwargs):
                return {}
            def serialize(self):
                return {"info": {"model": "exhausted"}}

        class NoShellEnvironment:
            calls = []
            def execute(self, action, cwd="", timeout=None):
                self.calls.append(action)
                raise AssertionError("context-exhausted turn reached the shell")
            def get_template_vars(self):
                return {}
            def serialize(self):
                return {"info": {"environment": "none"}}

        environment = NoShellEnvironment()
        agent = HardenedDefaultAgent(
            ExhaustedModel(),
            environment,
            repository=Path(os.environ["REPOSITORY"]),
            system_template=INITIAL_SYSTEM_TEMPLATE,
            instance_template=INSTANCE_TEMPLATE,
            output_path=Path(os.environ["TRAJECTORY"]),
            step_limit=15,
            cost_limit=0,
            wall_time_limit_seconds=0,
            max_consecutive_format_errors=3,
        )
        result = agent.run("calculator")
        assert result["exit_status"] == "CONTEXT_BUDGET_EXHAUSTED"
        assert result["http_request_sent"] is False
        assert environment.calls == []
        print(json.dumps({"result": result, "protocol": agent.protocol_result()}))
    '''
    result = subprocess.run(
        [str(mini_python), "-c", textwrap.dedent(script)],
        cwd=ROOT,
        env={
            **os.environ,
            "PYTHONPATH": str(runtime),
            "MSWEA_SILENT_STARTUP": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "REPOSITORY": str(repository),
            "TRAJECTORY": str(trajectory),
        },
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    transcript = json.loads(result.stdout)
    assert transcript["result"]["exit_status"] == CONTEXT_BUDGET_EXHAUSTED
    assert transcript["protocol"]["technical_validity"] == "PASS"
    assert trajectory.is_file()

    stages: list[str] = []

    def stage(name: str, value: object):
        def run() -> object:
            stages.append(name)
            return value

        return run

    outcome = PostAgentPipeline(
        analysis=stage("analysis", {"termination": CONTEXT_BUDGET_EXHAUSTED}),
        final_validation=stage("final_validation", {"passed": 3, "failed": 0}),
        integrity=stage("integrity", {"complete": True}),
        shutdown=stage("shutdown", {"complete": True}),
        preservation=stage("preservation", {"complete": True}),
    ).run()
    assert tuple(stages) == MANDATORY_POST_AGENT_STAGES
    assert outcome.post_agent_analysis_complete is True
    assert outcome.cleanup_complete is True
    assert outcome.artifact_preservation_complete is True
