from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from cmpilot.devstral_profile import (
    AGENT_PYTHON,
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
from cmpilot.devstral_serialization import PINNED_TEKKEN_SHA256
from cmpilot.devstral_mini_swe_adapter import (
    DEVSTRAL_SERIALIZATION_NAME,
    FROZEN_ADAPTER_NAME,
    PRODUCTION_POLICY_ADAPTER_NAME,
    write_devstral_adapter,
    write_devstral_production_adapter,
)


ROOT = Path(__file__).parents[1]


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


def test_exact_mistral_common_serialization_and_malformed_input_rejection() -> None:
    program = f"""
import json, sys
sys.path.insert(0, {str(ROOT / 'src')!r})
from cmpilot.devstral_serialization import ExactMistralChatTokenCounter, DevstralSerializationError
counter = ExactMistralChatTokenCounter({str(MODEL_SNAPSHOT)!r})
encoding = counter.encode([
    {{'role': 'system', 'content': 'You are exact.'}},
    {{'role': 'user', 'content': 'Reply with one word.'}},
])
rejected = False
try:
    counter.count([{{'role': 'user', 'content': 'x', 'tool_calls': []}}])
except DevstralSerializationError:
    rejected = True
print(json.dumps({{'count': encoding.token_count, 'rendered': encoding.rendered,
                  'identity': counter.identity, 'rejected': rejected}}))
"""
    completed = subprocess.run(
        (str(AGENT_PYTHON), "-c", program),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
        timeout=60,
    )
    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["count"] == 14
    assert result["rendered"] == (
        "<s>[SYSTEM_PROMPT]You are exact.[/SYSTEM_PROMPT]"
        "[INST]Reply with one word.[/INST]"
    )
    assert result["identity"]["response_conversion"] is None
    assert result["identity"]["tools"] is None
    assert result["rejected"] is True


def test_frozen_agent_adapter_selects_mistral_counting_explicitly(
    tmp_path: Path,
) -> None:
    adapter = tmp_path / "adapter.py"
    write_devstral_adapter(adapter)
    program = f"""
import json
from adapter import ExactDevstralChatTokenCounter
from cmpilot_context_budget import (
    PINNED_TOKENIZER_CONFIG_SHA256,
    PINNED_TOKENIZER_JSON_SHA256,
)
counter = ExactDevstralChatTokenCounter(
    {str(MODEL_SNAPSHOT)!r},
    expected_tokenizer_json_sha256=PINNED_TOKENIZER_JSON_SHA256,
    expected_tokenizer_config_sha256=PINNED_TOKENIZER_CONFIG_SHA256,
)
messages = [
    {{'role': 'system', 'content': 'You are exact.'}},
    {{'role': 'user', 'content': 'Reply with one word.'}},
]
print(json.dumps({{
    'count': counter.count(messages),
    'identity': counter.identity,
}}))
"""
    completed = subprocess.run(
        (str(AGENT_PYTHON), "-c", program),
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONDONTWRITEBYTECODE": "1", "PYTHONNOUSERSITE": "1"},
        timeout=60,
    )

    result = json.loads(completed.stdout.splitlines()[-1])
    assert result["count"] == 14
    assert result["identity"]["tekken_sha256"] == PINNED_TEKKEN_SHA256
    assert result["identity"]["response_conversion"] is None
    assert result["identity"]["adapter_schema"] == (
        "devstral-frozen-text-runtime-serialization-v1"
    )


def test_production_adapter_composes_serialization_with_shared_task_policy(
    tmp_path: Path,
) -> None:
    adapter = tmp_path / "mini_swe_adapter.py"
    record = write_devstral_production_adapter(adapter)

    wrapper = adapter.read_text(encoding="utf-8")
    policy = (tmp_path / PRODUCTION_POLICY_ADAPTER_NAME).read_text(encoding="utf-8")
    assert PRODUCTION_POLICY_ADAPTER_NAME in wrapper
    assert "ExactDevstralChatTokenCounter" in wrapper
    assert "CMPILOT_TASK_POLICY_SOURCE" in policy
    assert "CMPILOT_TASK_POLICY_SHA256" in policy
    assert FROZEN_ADAPTER_NAME in policy
    assert (tmp_path / DEVSTRAL_SERIALIZATION_NAME).is_file()
    assert record["frozen_adapter_sha256"]
    assert record["policy_adapter_sha256"]
    with pytest.raises(FileExistsError, match="already exists"):
        write_devstral_production_adapter(adapter)
