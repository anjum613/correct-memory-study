"""Narrow Devstral tokenizer adapter around the frozen text-action runtime.

Only prompt token counting is replaced. The OpenAI transport, assistant-text
response boundary, action parser, authorization policy, prompts, and agent
loop remain the byte-exact modules emitted by ``write_adapter``.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import runpy

import cmpilot_vllm_text_model
from cmpilot_context_budget import (
    PINNED_TOKENIZER_CONFIG_SHA256,
    PINNED_TOKENIZER_JSON_SHA256,
)
from cmpilot_devstral_serialization import ExactMistralChatTokenCounter


EXPECTED_FROZEN_ADAPTER_SHA256 = "__FROZEN_ADAPTER_SHA256__"
MODEL_ID = "mistralai/Devstral-Small-2507"
MODEL_REVISION = "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
MODEL_SNAPSHOT = Path(
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--mistralai--Devstral-Small-2507/snapshots/" + MODEL_REVISION
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExactDevstralChatTokenCounter:
    """Signature-compatible, non-repairing Mistral counter selection."""

    def __init__(
        self,
        tokenizer_path: Path,
        *,
        expected_tokenizer_json_sha256: str,
        expected_tokenizer_config_sha256: str,
    ) -> None:
        if expected_tokenizer_json_sha256 != PINNED_TOKENIZER_JSON_SHA256:
            raise RuntimeError("frozen base adapter tokenizer JSON field changed")
        if expected_tokenizer_config_sha256 != PINNED_TOKENIZER_CONFIG_SHA256:
            raise RuntimeError("frozen base adapter tokenizer config field changed")
        if Path(tokenizer_path) != MODEL_SNAPSHOT:
            raise RuntimeError("Devstral tokenizer snapshot path changed")
        self._counter = ExactMistralChatTokenCounter(MODEL_SNAPSHOT)
        self.identity = {
            **self._counter.identity,
            "adapter_schema": "devstral-frozen-text-runtime-serialization-v1",
            "base_adapter_compatibility_fields": {
                "tokenizer_config_sha256": PINNED_TOKENIZER_CONFIG_SHA256,
                "tokenizer_json_sha256": PINNED_TOKENIZER_JSON_SHA256,
            },
        }

    def count(self, messages):
        return self._counter.count(messages)


def main() -> None:
    if os.environ.get("CMPILOT_MODEL") != MODEL_ID:
        raise RuntimeError("Devstral served model identity changed")
    if Path(os.environ.get("CMPILOT_TOKENIZER_PATH", "")) != MODEL_SNAPSHOT:
        raise RuntimeError("Devstral tokenizer environment identity changed")

    frozen_adapter = Path(__file__).with_name("cmpilot_frozen_adapter_runtime.py")
    if _sha256(frozen_adapter) != EXPECTED_FROZEN_ADAPTER_SHA256:
        raise RuntimeError("frozen Qwen-proven text-action adapter changed")

    cmpilot_vllm_text_model.ExactQwenChatTokenCounter = (
        ExactDevstralChatTokenCounter
    )
    runpy.run_path(str(frozen_adapter), run_name="__main__")


if __name__ == "__main__":
    main()
