from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path

import pytest

from cmpilot.devstral_profile import (
    CANDIDATE_CUDA_WHEEL_RUNTIME,
    CANDIDATE_LOCK_SHA256,
    CANDIDATE_PYTHON_VERSION,
    DEVSTRAL_CANDIDATE,
    ENVIRONMENT_ID,
    ENVIRONMENT_PATH,
    MODEL_ID,
    MODEL_REVISION,
    MODEL_SNAPSHOT,
    PROFILE_ID,
    REQUIRED_SNAPSHOT_FILES,
    DevstralProfileError,
    verify_devstral_readiness,
)
from cmpilot.experiment_models import (
    PRODUCTION_AGENT_CONFIG,
    PRODUCTION_SCIENTIFIC_BOUNDARY,
)


ROOT = Path(__file__).parents[1]
CONFIG = ROOT / "configs/models/devstral-small-2507.json"


def test_candidate_records_exact_pinned_identity_without_claiming_readiness() -> None:
    profile = DEVSTRAL_CANDIDATE

    assert profile.profile_id == PROFILE_ID == "devstral-small-2507"
    assert profile.model_id == MODEL_ID == "mistralai/Devstral-Small-2507"
    assert profile.model_revision == MODEL_REVISION == (
        "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
    )
    assert profile.model_snapshot == MODEL_SNAPSHOT
    assert profile.environment_id == ENVIRONMENT_ID == "devstral-small-2507-v1"
    assert profile.environment_path == ENVIRONMENT_PATH
    assert CANDIDATE_PYTHON_VERSION == "3.11.11"
    assert CANDIDATE_CUDA_WHEEL_RUNTIME == "12.8"
    assert profile.verification_state == (
        "PARTIAL_METADATA_TOKENIZER_STAGED_WEIGHTS_ABSENT"
    )
    assert profile.server.dtype == "bfloat16"
    assert profile.server.tensor_parallel_size == 2
    assert profile.server.max_model_length == 4096
    assert profile.server.quantization is None


def test_candidate_uses_exact_shared_scientific_boundary_objects() -> None:
    profile = DEVSTRAL_CANDIDATE

    assert profile.agent_config is PRODUCTION_AGENT_CONFIG
    assert profile.scientific_boundary is PRODUCTION_SCIENTIFIC_BOUNDARY
    assert profile.model_system_prompt is None
    assert profile.native_tool_call_parser is None


def test_candidate_is_immutable_and_default_server_gate_fails_closed() -> None:
    with pytest.raises(FrozenInstanceError):
        DEVSTRAL_CANDIDATE.model_id = "changed"  # type: ignore[misc]
    with pytest.raises(DevstralProfileError, match="hashes have not been frozen"):
        DEVSTRAL_CANDIDATE.server_argv(port=48001)
    with pytest.raises(DevstralProfileError, match="hashes have not been frozen"):
        verify_devstral_readiness(verified_identity=None)


def test_checked_in_candidate_config_matches_code_and_has_no_fabricated_hashes() -> None:
    value = json.loads(CONFIG.read_text(encoding="utf-8"))

    assert value["schema"] == "cmpilot-model-profile-candidate-v1"
    assert value["status"] == "PARTIAL_METADATA_TOKENIZER_STAGED_WEIGHTS_ABSENT"
    assert value["profile_id"] == PROFILE_ID
    assert value["model"]["id"] == MODEL_ID
    assert value["model"]["revision"] == MODEL_REVISION
    assert value["model"]["snapshot"] == str(MODEL_SNAPSHOT)
    assert tuple(value["model"]["snapshot_required_files"]) == (
        REQUIRED_SNAPSHOT_FILES
    )
    assert value["model"]["snapshot_file_sha256"] is None
    assert value["model"]["runtime_weight"]["present"] is False
    assert value["model"]["alternative_hf_shards"]["present_count"] == 0
    assert value["model"]["verified"] is False
    assert value["environment"]["path"] == str(ENVIRONMENT_PATH)
    assert value["environment"]["candidate_lock_sha256"] == (
        CANDIDATE_LOCK_SHA256
    )
    assert value["environment"]["environment_fingerprint_sha256"] is not None
    assert value["environment"]["authoritative_content_digest_sha256"] is not None
    assert value["environment"]["verified"] is True
