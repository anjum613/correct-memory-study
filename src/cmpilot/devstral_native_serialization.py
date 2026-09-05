"""Exact Mistral serialization for the amended native-tool Devstral arm."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import importlib.metadata
from pathlib import Path
import re
from typing import Any


PINNED_TEKKEN_SHA256 = (
    "839c48629ff570bd664586800aa3ee17ee628f56efc7fd8e145cc01467a1c188"
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_ROLES = frozenset(("assistant", "system", "tool", "user"))


class DevstralNativeSerializationError(ValueError):
    """The pinned tokenizer or OpenAI-compatible native-tool history is invalid."""


def canonicalize_mistral_native_history(
    messages: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Represent rejected native actions as tool responses for Mistral.

    The shared hardened agent reports a rejected shell action with a user-role
    recovery message because that is the historical scaffold contract. Mistral's
    native protocol instead requires every assistant tool call to have a matching
    tool response before the conversation can continue. Convert only that
    unambiguous adjacency and leave executed tool responses and ordinary user
    messages unchanged.
    """
    if type(messages) is not list:
        raise DevstralNativeSerializationError("messages must be a list")
    canonical: list[dict[str, Any]] = []
    index = 0
    while index < len(messages):
        message = messages[index]
        if type(message) is not dict:
            raise DevstralNativeSerializationError(
                f"messages[{index}] must be a dictionary"
            )
        copied = dict(message)
        canonical.append(copied)
        tool_calls = copied.get("tool_calls")
        following = messages[index + 1] if index + 1 < len(messages) else None
        if (
            copied.get("role") == "assistant"
            and isinstance(tool_calls, list)
            and tool_calls
            and isinstance(following, dict)
            and following.get("role") == "user"
        ):
            content = following.get("content")
            if not isinstance(content, str):
                raise DevstralNativeSerializationError(
                    f"messages[{index + 1}] recovery content must be text"
                )
            for call_index, tool_call in enumerate(tool_calls):
                call_id = tool_call.get("id") if isinstance(tool_call, dict) else None
                if not isinstance(call_id, str) or not call_id:
                    raise DevstralNativeSerializationError(
                        f"messages[{index}].tool_calls[{call_index}] has no ID"
                    )
                canonical.append(
                    {
                        "role": "tool",
                        "content": content,
                        "tool_call_id": call_id,
                    }
                )
            index += 2
            continue
        index += 1
    return canonical


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class MistralNativeEncoding:
    tokens: tuple[int, ...]
    rendered: str

    @property
    def token_count(self) -> int:
        return len(self.tokens)


class ExactMistralNativeChatTokenCounter:
    """Serialize messages and tools with the pinned ``mistral-common`` tokenizer."""

    def __init__(
        self,
        tokenizer_path: Path,
        *,
        expected_tekken_sha256: str = PINNED_TEKKEN_SHA256,
    ) -> None:
        root = Path(tokenizer_path)
        if not root.is_absolute() or not root.is_dir():
            raise DevstralNativeSerializationError(
                f"tokenizer path must be an existing absolute directory: {root}"
            )
        if _SHA256.fullmatch(expected_tekken_sha256) is None:
            raise DevstralNativeSerializationError(
                "expected_tekken_sha256 must be a lowercase SHA-256 digest"
            )
        tekken = root / "tekken.json"
        if not tekken.is_file() or _sha256_file(tekken) != expected_tekken_sha256:
            raise DevstralNativeSerializationError(
                "tekken.json does not match the pinned Devstral tokenizer"
            )
        try:
            from mistral_common.protocol.instruct.request import ChatCompletionRequest
            from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
        except ImportError as error:
            raise DevstralNativeSerializationError(
                "mistral-common >=1.7.0 is required for native serialization"
            ) from error

        self._request_type = ChatCompletionRequest
        self._tokenizer = MistralTokenizer.from_file(tekken)
        self.identity = {
            "schema": "devstral-mistral-native-tokenizer-identity-v1",
            "tokenizer_path": str(root),
            "tekken_sha256": expected_tekken_sha256,
            "chat_template_source": "mistral-common/tekken.json",
            "tools": "openai-function-tools",
            "response_conversion": "vllm-mistral-tool-parser",
            "mistral_common_version": importlib.metadata.version("mistral-common"),
            "rejected_tool_call_feedback": "tool-response-per-call-v1",
        }

    @staticmethod
    def _validate_messages(messages: list[dict[str, Any]]) -> None:
        if type(messages) is not list or not messages:
            raise DevstralNativeSerializationError("messages must be a nonempty list")
        for index, message in enumerate(messages):
            if type(message) is not dict:
                raise DevstralNativeSerializationError(
                    f"messages[{index}] must be a dictionary"
                )
            if message.get("role") not in _ROLES or not isinstance(
                message.get("content"), str
            ):
                raise DevstralNativeSerializationError(
                    f"messages[{index}] has an invalid role or content"
                )

    def encode(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> MistralNativeEncoding:
        messages = canonicalize_mistral_native_history(messages)
        self._validate_messages(messages)
        if tools is not None and type(tools) is not list:
            raise DevstralNativeSerializationError("tools must be a list or null")
        try:
            request = self._request_type.from_openai(messages=messages, tools=tools)
            encoded = self._tokenizer.encode_chat_completion(request)
        except Exception as error:
            raise DevstralNativeSerializationError(
                f"mistral-common rejected the native-tool history: {error}"
            ) from error
        if not isinstance(encoded.text, str) or type(encoded.tokens) is not list:
            raise DevstralNativeSerializationError(
                "mistral-common returned an invalid encoded prompt"
            )
        if any(type(token) is not int for token in encoded.tokens):
            raise DevstralNativeSerializationError(
                "mistral-common returned non-integer prompt tokens"
            )
        return MistralNativeEncoding(tuple(encoded.tokens), encoded.text)

    def count(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> int:
        return self.encode(messages, tools=tools).token_count


__all__ = [
    "DevstralNativeSerializationError",
    "ExactMistralNativeChatTokenCounter",
    "MistralNativeEncoding",
    "PINNED_TEKKEN_SHA256",
    "canonicalize_mistral_native_history",
]
