from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from cmpilot.integrations.miniswe.openai_transport import normalize_message
from cmpilot.multiturn_preflight import (
    PASS_CLASSIFICATION,
    MultiturnPreflightConfig,
    run_multiturn_preflight,
)
from cmpilot.qwen36_candidate import (
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    SELECTED_CONTEXT_LENGTH,
    build_suite_reference,
    sha256_file,
)
from cmpilot.qwen36_qualification import (
    AGENT_CONFIG,
    ALL_TASKS,
    CANDIDATE_MANIFEST_SHA256,
    ENVIRONMENT_CONTENT_DIGEST,
    ENVIRONMENT_FINGERPRINT,
    MAX_OUTPUT_TOKENS,
    PRIMARY_TASKS,
    QUALIFICATION_FREEZE,
    QWEN36_PYTHON,
    REASONING_PARSER,
    RESERVE_TASKS,
    SEED_SCHEDULE,
    SUITE_REFERENCE,
    SUITE_REFERENCE_SHA256,
    SMOKE_ARTIFACT,
    build_smoke_result,
    resolved_agent_config,
    validate_agent_config,
    validate_freeze_manifest,
    validate_seed_schedule,
    write_canonical_json,
)
from scripts.generate_qwen36_qualification_batches import render


ROOT = Path(__file__).parents[1]
DEFAULT_MINI_PY = Path(
    "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
)


def _mini_python() -> Path:
    return Path(os.environ.get("MINI_SWE_PYTHON", DEFAULT_MINI_PY))


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_frozen_qwen36_generation_and_seed_schedule_are_exact() -> None:
    config = validate_agent_config(ROOT / AGENT_CONFIG)
    schedule = validate_seed_schedule(ROOT / SEED_SCHEDULE)

    assert config["pass"] is True
    assert config["model"] == {
        "connect_timeout_seconds": 10.0,
        "context_limit": 32768,
        "context_safety_margin": 32,
        "max_tokens": 8192,
        "min_p": 0.0,
        "minimum_useful_completion": 64,
        "presence_penalty": 0.0,
        "read_timeout_seconds": 120.0,
        "repetition_penalty": 1.0,
        "samples_per_call": 1,
        "temperature": 1.0,
        "tokenizer_config_sha256": (
            "5186f0defcd7f232382c7f0aebcd2252d073bb921ab240e407b7ae8745d2b29b"
        ),
        "tokenizer_json_sha256": (
            "5f9e4d4901a92b997e463c1f46055088b6cca5ca61a6522d1b9f64c4bb81cb42"
        ),
        "top_k": 20,
        "top_p": 0.95,
    }
    assert MAX_OUTPUT_TOKENS == 8192
    assert schedule["seeds"] == {
        "qnm-p01-interval-merge": 1602021252,
        "qnm-p02-shipment-summary": 1920009210,
        "qnm-p03-page-window": 924300403,
        "qnm-p04-record-parser": 856051484,
        "qnm-p05-event-replay": 1086801435,
        "qnm-r01-dependency-order": 166980876,
        "qnm-r02-ledger-transfer": 420537829,
    }
    assert ALL_TASKS == PRIMARY_TASKS + RESERVE_TASKS


def test_resolved_agent_config_only_adds_the_predeclared_task_seed() -> None:
    base = json.loads((ROOT / AGENT_CONFIG).read_text(encoding="utf-8"))
    resolved = resolved_agent_config(ROOT, "qnm-p03-page-window")

    assert resolved["agent"] == base["agent"]
    assert resolved["environment"] == base["environment"]
    assert resolved["model"] == {
        **base["model"],
        "seed": 924300403,
    }
    assert "seed" not in base["model"]


def test_reasoning_is_excluded_from_canonical_assistant_history() -> None:
    normalized = normalize_message(
        {
            "role": "assistant",
            "content": "THOUGHT: done\n\n```mswea_bash_command\necho ok\n```",
            "reasoning": "private provider reasoning",
            "provider_specific_fields": {"x": 1},
        },
        "$.choices[0].message",
    )

    assert normalized.value == {
        "role": "assistant",
        "content": "THOUGHT: done\n\n```mswea_bash_command\necho ok\n```",
    }
    assert normalized.excluded_paths == (
        "$.choices[0].message.provider_specific_fields",
        "$.choices[0].message.reasoning",
    )


def test_qwen36_scientific_adapter_multiturn_mock(
    tmp_path: Path,
) -> None:
    mini_python = _mini_python()
    if not mini_python.is_file() or not MODEL_SNAPSHOT.is_dir():
        pytest.skip("frozen HPC mini-SWE/Qwen3.6 assets are unavailable")
    resolved_path = tmp_path / "resolved-agent-config.json"
    write_canonical_json(
        resolved_path,
        resolved_agent_config(ROOT, "qnm-p01-interval-merge"),
    )
    artifacts = tmp_path / "qwen36-multiturn"

    exit_code = run_multiturn_preflight(
        MultiturnPreflightConfig(
            mini_python=str(mini_python),
            artifact_dir=artifacts,
            timeout_seconds=90,
            model=MODEL_ID,
            tokenizer_path=str(MODEL_SNAPSHOT),
            agent_config_source=resolved_path,
        )
    )

    result = json.loads((artifacts / "result.json").read_text(encoding="utf-8"))
    requests = _jsonl(artifacts / "mock-requests.jsonl")
    transport = _jsonl(artifacts / "agent-run/model-transport.jsonl")
    assert exit_code == 0
    assert result["classification"] == PASS_CLASSIFICATION
    assert result["model"] == MODEL_ID
    assert all(result["checks"].values())
    assert len(requests) == len(transport) == 3
    for record in requests:
        request = record["request"]
        assert request["temperature"] == 1.0
        assert request["top_p"] == 0.95
        assert request["top_k"] == 20
        assert request["min_p"] == 0.0
        assert request["presence_penalty"] == 0.0
        assert request["repetition_penalty"] == 1.0
        assert request["seed"] == 1602021252
        assert request["n"] == 1
        assert request["max_tokens"] <= MAX_OUTPUT_TOKENS
        serialized = json.dumps(request["messages"], sort_keys=True)
        assert '"reasoning"' not in serialized
        assert '"extra"' not in serialized
    assert all(
        isinstance(
            record["response"]["choices"][0]["message"]["reasoning"], str
        )
        for record in transport
    )


def test_all_seven_generated_batches_share_the_frozen_scientific_settings() -> None:
    seeds = validate_seed_schedule(ROOT / SEED_SCHEDULE)["seeds"]
    dummy_freeze = "a" * 64

    for task_id in ALL_TASKS:
        batch = render(task_id, seeds[task_id], dummy_freeze)
        assert f"TASK_ID={task_id}" in batch
        assert f"TASK_SEED={seeds[task_id]}" in batch
        assert f"EXPECTED_FREEZE_SHA256={dummy_freeze}" in batch
        assert "#SBATCH --gres=gpu:a100:2" in batch
        assert "--dtype bfloat16" in batch
        assert "--tensor-parallel-size 2" in batch
        assert "--max-model-len 32768" in batch
        assert "--gpu-memory-utilization 0.90" in batch
        assert "--reasoning-parser qwen3" in batch
        assert "--language-model-only" in batch
        assert 'RUNTIME_SCRATCH=/tmp/cmq-$SLURM_JOB_ID' in batch
        assert "run_qualification_task.py" in batch
        assert "reference-patches" not in batch
        assert "memory treatment" not in batch.casefold()
        assert "qwen36_model_load_request_smoke" not in batch


def test_candidate_and_suite_identity_remain_unchanged() -> None:
    assert sha256_file(ROOT / "qualification/qwen36-v1/candidate-freeze-manifest.json") == (
        CANDIDATE_MANIFEST_SHA256
    )
    assert sha256_file(ROOT / SUITE_REFERENCE) == SUITE_REFERENCE_SHA256
    reference = build_suite_reference(ROOT)
    assert reference["all_task_components_byte_identical"] is True
    assert MODEL_REVISION == "6a9e13bd6fc8f0983b9b99948120bc37f49c13e9"
    assert SELECTED_CONTEXT_LENGTH == 32768
    assert str(QWEN36_PYTHON) == (
        "/home/s224049759/environments/qwen36-vllm-v1/bin/python"
    )
    assert ENVIRONMENT_FINGERPRINT == (
        "fe63e366ca33bc2392eb173281764bdb8bd543ed3ce8d36c3b3fe6727df80bab"
    )
    assert ENVIRONMENT_CONTENT_DIGEST == (
        "b36b9c47b130dba7c2a0ae60161029d3f5b0b522e8bd0f5b0f0749bae86b3a74"
    )
    assert REASONING_PARSER == "qwen3"


def test_smoke_result_builds_from_the_two_gpu_array_artifact() -> None:
    if not SMOKE_ARTIFACT.is_dir():
        pytest.skip("preserved job-25940 artifacts are unavailable")

    result = build_smoke_result(SMOKE_ARTIFACT)

    assert result["classification"] == "PASS"
    assert result["job_id"] == "25940"
    assert result["context_decision"] == "SAFE_FOR_QUALIFICATION"
    assert len(result["gpu_memory_after_load"]) == 2
    assert all(result["checks"].values())


def test_final_freeze_validates_when_present() -> None:
    path = ROOT / QUALIFICATION_FREEZE
    if not path.is_file():
        pytest.skip("pre-outcome qualification freeze has not been emitted yet")

    result = validate_freeze_manifest(ROOT, path)

    assert result["pass"] is True
    assert len(result["sha256"]) == 64
