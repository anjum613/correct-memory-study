"""Select exact Mistral native-tool counting around the shared policy adapter."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import runpy

import cmpilot_vllm_text_model
from cmpilot_devstral_native_serialization import (
    ExactMistralNativeChatTokenCounter,
    PINNED_TEKKEN_SHA256,
    canonicalize_mistral_native_history,
)


EXPECTED_POLICY_ADAPTER_SHA256 = "92697bd7b2c040a0c72945194e70ebd497d83042364575ca173133811c081f52"
MODEL_NAME = "devstral-small-2507"
MODEL_REVISION = "bd165ab26cebbcc2eea2c4ecbfc07f3ac42b3c39"
MODEL_SNAPSHOT = Path(
    "/home/s224049759/model-cache/devstral-small-2507/" + MODEL_REVISION
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ExactDevstralNativeChatTokenCounter:
    """Signature-compatible counter selected before mini-SWE constructs its model."""

    def __init__(
        self,
        tokenizer_path: Path,
        *,
        expected_tokenizer_json_sha256: str,
        expected_tokenizer_config_sha256: str,
    ) -> None:
        if (
            expected_tokenizer_json_sha256 != PINNED_TEKKEN_SHA256
            or expected_tokenizer_config_sha256 != PINNED_TEKKEN_SHA256
        ):
            raise RuntimeError("Devstral Tekken compatibility identity changed")
        if Path(tokenizer_path) != MODEL_SNAPSHOT:
            raise RuntimeError("Devstral tokenizer snapshot path changed")
        self._counter = ExactMistralNativeChatTokenCounter(MODEL_SNAPSHOT)
        self.identity = {
            **self._counter.identity,
            "adapter_schema": "devstral-native-tool-runtime-v1",
        }

    def count(self, messages, *, tools=None):
        return self._counter.count(messages, tools=tools)


def main() -> None:
    if os.environ.get("CMPILOT_MODEL") != MODEL_NAME:
        raise RuntimeError("Devstral served model identity changed")
    if Path(os.environ.get("CMPILOT_TOKENIZER_PATH", "")) != MODEL_SNAPSHOT:
        raise RuntimeError("Devstral tokenizer environment identity changed")
    policy_adapter = Path(__file__).with_name("cmpilot_policy_adapter_runtime.py")
    if _sha256(policy_adapter) != EXPECTED_POLICY_ADAPTER_SHA256:
        raise RuntimeError("Devstral policy adapter changed")
    cmpilot_vllm_text_model.ExactQwenChatTokenCounter = (
        ExactDevstralNativeChatTokenCounter
    )
    cmpilot_vllm_text_model.canonicalize_provider_messages = (
        canonicalize_mistral_native_history
    )
    runpy.run_path(str(policy_adapter), run_name="__main__")


if __name__ == "__main__":
    main()
