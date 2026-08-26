from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from cmpilot.calculator_finalizer import (
    FINALIZER_CONTROL_FLOW_VERSION,
    FINALIZER_STATE_SCHEMA,
)
from cmpilot import devstral_profile
from cmpilot.devstral_profile import (
    AGENT_PYTHON,
    DEVSTRAL_PRODUCTION_PROFILE,
    EXPECTED_CONSOLIDATED_SHA256,
    EXPECTED_CONSOLIDATED_SIZE,
    MODEL_ID as DEVSTRAL_MODEL_ID,
    MODEL_REVISION as DEVSTRAL_MODEL_REVISION,
    SNAPSHOT_FREEZE_SHA256,
    SNAPSHOT_IDENTITY_SHA256,
    verify_devstral_production_qualification,
)
from cmpilot.experiment_models import (
    MODEL_PROFILES,
    PRODUCTION_AGENT_CONFIG,
    PRODUCTION_SCIENTIFIC_BOUNDARY,
    QWEN32B_PROFILE,
    ModelProfileError,
    get_model_profile,
)
from cmpilot.guided_backend import build_qwen32b_server_command
from cmpilot.integrations.miniswe.action_protocol import (
    ACTION_REGEX,
    COMPLETION_SENTINEL,
    MAX_CONSECUTIVE_PROTOCOL_ERRORS,
)
from cmpilot.integrations.miniswe.command_authorization import POLICY_VERSION
from cmpilot.integrations.miniswe.context_budget import (
    PINNED_TOKENIZER_CONFIG_SHA256,
    PINNED_TOKENIZER_JSON_SHA256,
)
from cmpilot.integrations.miniswe.source_manifest import EXPECTED_VERSION
from cmpilot.qualification import (
    CMPILOT_PYTHON,
    MINI_SWE_PYTHON,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    VLLM_PYTHON,
)
from cmpilot.server_command import (
    GUIDED_DECODING_BACKEND,
    load_command_argv,
    validate_qwen32b_server_command,
)
from cmpilot.task_file_policy import TASK_POLICY_SCHEMA


ROOT = Path(__file__).parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "job_25335_server_command.json"


def test_qwen_profile_delegates_to_exact_qualified_server_command() -> None:
    fixture_command = load_command_argv(FIXTURE)
    profile_command = QWEN32B_PROFILE.server_argv(port=47983)

    assert profile_command == build_qwen32b_server_command(port=47983)
    assert profile_command == fixture_command
    assert validate_qwen32b_server_command(profile_command) == profile_command


def test_qwen_profile_preserves_model_runtime_and_environment_identity() -> None:
    profile = QWEN32B_PROFILE

    assert profile.profile_id == "qwen2.5-coder-32b-instruct"
    assert profile.model_id == MODEL_ID == "Qwen/Qwen2.5-Coder-32B-Instruct"
    assert profile.model_revision == MODEL_REVISION == (
        "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
    )
    assert profile.model_snapshot == MODEL_SNAPSHOT
    assert profile.served_model_name == str(MODEL_SNAPSHOT)
    assert profile.environment.server_python == VLLM_PYTHON
    assert profile.environment.controller_python == CMPILOT_PYTHON
    assert profile.environment.agent_python == MINI_SWE_PYTHON
    assert profile.environment.environment_fingerprint == (
        "6afe3a785d3d96956e8eca1e57276637ac02f9793cbeb1fcc1955924f6277071"
    )
    assert profile.environment.environment_content_digest == (
        "5e640248ebe171e106707ad4aaca0eebf98673f5c4b10b87458364c6f300e9ee"
    )
    assert profile.server.dtype == "bfloat16"
    assert profile.server.tensor_parallel_size == 2
    assert profile.server.max_model_length == 4096
    assert profile.server.max_num_sequences == 1
    assert profile.server.gpu_memory_utilization == "0.90"
    assert profile.server.server_seed == 0
    assert profile.server.quantization is None


def test_qwen_profile_binds_frozen_agent_and_serialization_inputs() -> None:
    profile = QWEN32B_PROFILE

    assert profile.agent_config is PRODUCTION_AGENT_CONFIG
    assert profile.agent_config.relative_path == Path(
        "configs/agent/mini_swe_agent_smoke.yaml"
    )
    assert profile.agent_config.sha256 == (
        "a4396981a64a5823672e908a2b9c1e488a23a0b8b726624fe86bc935c6ca1ac0"
    )
    assert profile.serialization.tokenizer_path == MODEL_SNAPSHOT
    assert profile.serialization.tokenizer_json_sha256 == (
        PINNED_TOKENIZER_JSON_SHA256
    )
    assert profile.serialization.tokenizer_config_sha256 == (
        PINNED_TOKENIZER_CONFIG_SHA256
    )
    assert profile.serialization.assets == (
        ("tokenizer.json", PINNED_TOKENIZER_JSON_SHA256),
        ("tokenizer_config.json", PINNED_TOKENIZER_CONFIG_SHA256),
    )
    assert profile.serialization.serialization_mode == "huggingface-chat-template"
    assert profile.serialization.chat_template_source == "tokenizer_config.json"
    assert profile.serialization.add_generation_prompt is True
    assert profile.generation.ordinary_request_parameters() == (
        ("temperature", 0.0),
        ("max_tokens", 512),
    )
    assert profile.generation.request_seed is None
    assert profile.generation.stop_tokens == ()

    verified = profile.verify_static_inputs(ROOT)
    assert ROOT / profile.agent_config.relative_path in verified
    assert MODEL_SNAPSHOT / "tokenizer.json" in verified
    assert MODEL_SNAPSHOT / "tokenizer_config.json" in verified


def test_qwen_profile_has_a_frozen_final_experiment_identity() -> None:
    assert QWEN32B_PROFILE.identity_sha256() == (
        "2c1bfe6fe074e34b0c130e70e766f34ad7cc6b59633c63d71d131bb0eb379993"
    )
    record = QWEN32B_PROFILE.final_experiment_record(step_limit=100)
    assert record == {
        "context_limit": 4096,
        "environment_id": "qwen32b-vllm-smoke-v1",
        "environment_sha256": (
            "5e640248ebe171e106707ad4aaca0eebf98673f5c4b10b87458364c6f300e9ee"
        ),
        "generation_parameters": QWEN32B_PROFILE.generation.as_record(),
        "generation_parameters_sha256": (
            "b8485f5f8fc2572154e1284e0ef05df23b17b4f8d293bad8d4078b0d08b5e705"
        ),
        "model_id": MODEL_ID,
        "profile_sha256": QWEN32B_PROFILE.identity_sha256(),
        "revision": MODEL_REVISION,
        "step_limit": 100,
    }
    with pytest.raises(ModelProfileError, match="step_limit"):
        QWEN32B_PROFILE.final_experiment_record(step_limit=0)


def test_every_profile_uses_the_unoverrideable_production_boundary() -> None:
    boundary = PRODUCTION_SCIENTIFIC_BOUNDARY

    assert all(
        profile.scientific_boundary is boundary for profile in MODEL_PROFILES.values()
    )
    assert boundary.action_regex == ACTION_REGEX
    assert boundary.completion_sentinel == COMPLETION_SENTINEL
    assert boundary.maximum_consecutive_protocol_errors == (
        MAX_CONSECUTIVE_PROTOCOL_ERRORS
    )
    assert boundary.hardened_agent_class.endswith(".HardenedDefaultAgent")
    assert boundary.command_policy_version == POLICY_VERSION
    assert boundary.task_policy_schema == TASK_POLICY_SCHEMA
    assert boundary.mini_swe_agent_version == EXPECTED_VERSION == "2.4.6"
    assert boundary.finalizer_state_schema == FINALIZER_STATE_SCHEMA
    assert boundary.finalizer_control_flow_version == (
        FINALIZER_CONTROL_FLOW_VERSION
    )
    assert boundary.verify(ROOT)


def test_profile_is_immutable_registry_is_read_only_and_unknown_ids_fail() -> None:
    assert get_model_profile(QWEN32B_PROFILE.profile_id) is QWEN32B_PROFILE
    assert (
        get_model_profile(DEVSTRAL_PRODUCTION_PROFILE.profile_id)
        is DEVSTRAL_PRODUCTION_PROFILE
    )
    with pytest.raises(FrozenInstanceError):
        QWEN32B_PROFILE.model_id = "weakened"  # type: ignore[misc]
    with pytest.raises(TypeError):
        MODEL_PROFILES["weakened"] = QWEN32B_PROFILE  # type: ignore[index]
    with pytest.raises(ModelProfileError, match="unknown model profile"):
        get_model_profile("unknown")


def test_devstral_production_profile_binds_qualified_runtime_and_evidence() -> None:
    profile = DEVSTRAL_PRODUCTION_PROFILE
    identity = profile.identity_record()
    qualification = identity["qualification"]

    assert tuple(MODEL_PROFILES) == (
        QWEN32B_PROFILE.profile_id,
        profile.profile_id,
    )
    assert profile.profile_id == "devstral-small-2507"
    assert profile.model_id == DEVSTRAL_MODEL_ID
    assert profile.model_revision == DEVSTRAL_MODEL_REVISION
    assert profile.environment.agent_python == AGENT_PYTHON
    assert profile.serialization.serialization_mode == "mistral-common-tekken"
    assert profile.serialization.chat_template_source == "mistral-common/tekken.json"
    assert profile.server.dtype == "bfloat16"
    assert profile.server.tensor_parallel_size == 2
    assert profile.server.max_model_length == 4096
    assert profile.server.quantization is None
    assert qualification["snapshot_freeze"] == {
        "freeze_identity_sha256": (
            "7341bd8b1c9f1556fa39465e9b51b931ba1433d2fa23d1253d5f71b0739b6128"
        ),
        "path": "qualification/devstral-small-2507-snapshot-freeze.json",
        "runtime_weight": {
            "file": "consolidated.safetensors",
            "sha256": EXPECTED_CONSOLIDATED_SHA256,
            "size": EXPECTED_CONSOLIDATED_SIZE,
        },
        "sha256": SNAPSHOT_FREEZE_SHA256,
        "snapshot_identity_sha256": SNAPSHOT_IDENTITY_SHA256,
    }
    assert qualification["technical_smoke"]["job_id"] == "28589"
    assert qualification["environment_verifier"]["required_status"] == "READY"
    assert verify_devstral_production_qualification(ROOT)
    assert profile.verify_static_inputs(ROOT)


def test_devstral_production_profile_rejects_missing_or_wrong_freeze(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        devstral_profile,
        "SNAPSHOT_FREEZE",
        Path("qualification/synthetic-missing-devstral-freeze.json"),
    )
    with pytest.raises(OSError):
        verify_devstral_production_qualification(ROOT)

    monkeypatch.setattr(
        devstral_profile,
        "SNAPSHOT_FREEZE",
        Path("qualification/devstral-small-2507-snapshot-freeze.json"),
    )
    monkeypatch.setattr(devstral_profile, "SNAPSHOT_FREEZE_SHA256", "0" * 64)
    with pytest.raises(ModelProfileError, match="frozen project input changed"):
        verify_devstral_production_qualification(ROOT)


@pytest.mark.parametrize(
    "mutation",
    [
        lambda command: command.__setitem__(
            command.index(GUIDED_DECODING_BACKEND), "outlines"
        ),
        lambda command: command.extend(["--quantization", "awq"]),
        lambda command: command.__setitem__(
            command.index("--tensor-parallel-size") + 1, "1"
        ),
        lambda command: command.__setitem__(
            command.index("--max-model-len") + 1, "8192"
        ),
    ],
)
def test_qwen_profile_rejects_server_boundary_weakening(mutation) -> None:
    command = list(build_qwen32b_server_command(port=47983))
    mutation(command)

    with pytest.raises((ValueError, RuntimeError)):
        QWEN32B_PROFILE.validate_server_argv(command)
