from __future__ import annotations

import pytest

from cmpilot.devstral_profile import (
    CONFIG_FORMAT,
    DEVSTRAL_CANDIDATE,
    LOAD_FORMAT,
    MODEL_ID,
    MODEL_SNAPSHOT,
    SERVER_PYTHON,
    TOKENIZER_MODE,
    DevstralProfileError,
    build_devstral_server_argv,
    validate_devstral_server_argv,
)


def option(command: tuple[str, ...], name: str) -> str:
    return command[command.index(name) + 1]


def test_canonical_devstral_command_uses_only_required_mistral_serialization() -> None:
    command = build_devstral_server_argv(port=48001)

    assert command[:3] == (
        str(SERVER_PYTHON),
        "-m",
        "vllm.entrypoints.openai.api_server",
    )
    assert option(command, "--host") == "127.0.0.1"
    assert option(command, "--model") == str(MODEL_SNAPSHOT)
    assert option(command, "--tokenizer") == str(MODEL_SNAPSHOT)
    assert option(command, "--served-model-name") == MODEL_ID
    assert option(command, "--dtype") == "bfloat16"
    assert option(command, "--tensor-parallel-size") == "2"
    assert option(command, "--max-model-len") == "4096"
    assert option(command, "--max-num-seqs") == "1"
    assert option(command, "--tokenizer-mode") == TOKENIZER_MODE == "mistral"
    assert option(command, "--config-format") == CONFIG_FORMAT == "mistral"
    assert option(command, "--load-format") == LOAD_FORMAT == "mistral"
    assert "--quantization" not in command
    assert "--tool-call-parser" not in command
    assert "--enable-auto-tool-choice" not in command
    assert "--chat-template" not in command
    assert validate_devstral_server_argv(command) == command


@pytest.mark.parametrize(
    "mutate",
    [
        lambda command: command.extend(["--quantization", "awq"]),
        lambda command: command.extend(["--tool-call-parser", "mistral"]),
        lambda command: command.append("--enable-auto-tool-choice"),
        lambda command: command.extend(["--chat-template", "easier.jinja"]),
        lambda command: command.__setitem__(
            command.index("--tensor-parallel-size") + 1, "1"
        ),
        lambda command: command.__setitem__(
            command.index("--max-model-len") + 1, "8192"
        ),
        lambda command: command.__setitem__(command.index("--dtype") + 1, "float16"),
    ],
)
def test_command_validator_rejects_model_specific_scientific_weakening(mutate) -> None:
    command = list(build_devstral_server_argv(port=48001))
    mutate(command)

    with pytest.raises(DevstralProfileError, match="differs from the frozen"):
        validate_devstral_server_argv(command)


def test_candidate_serialization_does_not_create_a_second_action_boundary() -> None:
    assert DEVSTRAL_CANDIDATE.scientific_boundary.action_regex
    assert DEVSTRAL_CANDIDATE.scientific_boundary is (
        DEVSTRAL_CANDIDATE.scientific_boundary
    )
    assert DEVSTRAL_CANDIDATE.model_system_prompt is None
    assert DEVSTRAL_CANDIDATE.native_tool_call_parser is None
