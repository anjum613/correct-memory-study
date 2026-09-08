from __future__ import annotations

from dataclasses import replace

import pytest

from cmpilot.model_profiles import available_model_profiles, load_model_profile


DEVSTRAL_REVISION = "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
PRIMARY_REVISION = "381fc969f78efac66bc87ff7ddeadb7e73c218a7"


def test_primary_qwen_reference_resolves_without_launch_configuration() -> None:
    profile = load_model_profile("qwen2.5-coder-32b-primary")

    assert profile.model_id == "Qwen/Qwen2.5-Coder-32B-Instruct"
    assert profile.model_revision == PRIMARY_REVISION
    assert profile.tokenizer_revision == PRIMARY_REVISION
    assert profile.launchable is False
    assert profile.server_arguments == ()
    assert profile.runtime_environment == "existing_primary_environment_unchanged"


def test_devstral_profile_is_exact_and_unquantized() -> None:
    profile = load_model_profile("devstral-small-2507")

    assert profile.model_id == "mistralai/Devstral-Small-2507"
    assert profile.model_revision == DEVSTRAL_REVISION
    assert profile.tokenizer_id == profile.model_id
    assert profile.tokenizer_revision == DEVSTRAL_REVISION
    assert profile.served_model_name == "cmpilot-devstral-small-2507-bd165ab26ceb"
    assert profile.server["dtype"] == "bfloat16"
    assert profile.server["tensor_parallel_size"] == 2
    assert profile.server["maximum_model_length"] == 131072
    assert profile.server["quantization"] == "none"
    assert profile.reasoning_mode == "not_applicable"
    assert profile.guided_decoding == {
        "backend": "not_configured",
        "auto_tool_choice": True,
        "tool_call_parser": "mistral",
        "response_rewriting": False,
    }


def test_devstral_server_arguments_attest_every_identity() -> None:
    profile = load_model_profile("devstral-small-2507")
    arguments = profile.server_arguments

    assert arguments[0] == profile.model_id
    assert arguments[arguments.index("--revision") + 1] == profile.model_revision
    assert arguments[arguments.index("--tokenizer-revision") + 1] == profile.tokenizer_revision
    assert arguments[arguments.index("--served-model-name") + 1] == profile.served_model_name
    assert arguments[arguments.index("--tool-call-parser") + 1] == "mistral"
    assert "--enable-auto-tool-choice" in arguments
    assert not any("quant" in argument for argument in arguments)


def test_profile_validation_rejects_mutable_revisions_and_response_rewriting() -> None:
    profile = load_model_profile("devstral-small-2507")

    with pytest.raises(ValueError, match="immutable 40-character commit"):
        replace(profile, model_revision="main").validate()
    with pytest.raises(ValueError, match="must not be rewritten"):
        replace(profile, guided_decoding={**profile.guided_decoding, "response_rewriting": True}).validate()


def test_profile_identity_isolated_by_model_and_revision() -> None:
    devstral = load_model_profile("devstral-small-2507")
    primary = load_model_profile("qwen2.5-coder-32b-primary")

    assert devstral.identity == "devstral-small-2507-bd165ab26ceb"
    assert devstral.identity != primary.identity
    assert set(available_model_profiles()) == {"devstral-small-2507", "qwen2.5-coder-32b-primary"}
