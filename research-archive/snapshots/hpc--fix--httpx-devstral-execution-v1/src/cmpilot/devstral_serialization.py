"""Exact Devstral chat serialization for context accounting.

This module delegates only prompt serialization to the documented
``mistral-common`` tokenizer.  It deliberately has no response parser, tool
conversion, retry, or malformed-output repair; assistant text continues into
the existing project-owned action boundary unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import re
from typing import Any


PINNED_TEKKEN_SHA256 = (
    "839c48629ff570bd664586800aa3ee17ee628f56efc7fd8e145cc01467a1c188"
)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_MESSAGE_KEYS = frozenset(("content", "role"))
_ROLES = frozenset(("assistant", "system", "user"))


class DevstralSerializationError(ValueError):
    """The exact tokenizer identity or canonical chat input is invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


@dataclass(frozen=True)
class MistralEncoding:
    """Immutable evidence returned by the official Mistral serializer."""

    tokens: tuple[int, ...]
    rendered: str

    @property
    def token_count(self) -> int:
        return len(self.tokens)


class ExactMistralChatTokenCounter:
    """Count the exact native Devstral prompt tokens from ``tekken.json``."""

    def __init__(
        self,
        tokenizer_path: Path,
        *,
        expected_tekken_sha256: str = PINNED_TEKKEN_SHA256,
    ):
        root = Path(tokenizer_path)
        if not root.is_absolute() or not root.is_dir():
            raise DevstralSerializationError(
                f"tokenizer path must be an existing absolute directory: {root}"
            )
        if _SHA256.fullmatch(expected_tekken_sha256) is None:
            raise DevstralSerializationError(
                "expected_tekken_sha256 must be a lowercase SHA-256 digest"
            )
        tekken = root / "tekken.json"
        if not tekken.is_file():
            raise DevstralSerializationError(
                f"pinned Devstral tokenizer is absent: {tekken}"
            )
        digest = _sha256_file(tekken)
        if digest != expected_tekken_sha256:
            raise DevstralSerializationError(
                "tekken.json does not match the pinned Devstral tokenizer"
            )
        try:
            from mistral_common.protocol.instruct.request import (
                ChatCompletionRequest,
            )
            from mistral_common.tokens.tokenizers.mistral import MistralTokenizer
        except ImportError as error:
            raise DevstralSerializationError(
                "mistral-common 1.8.4 is required for exact serialization"
            ) from error

        self._request_type = ChatCompletionRequest
        self._tokenizer = MistralTokenizer.from_file(tekken)
        self.identity = {
            "schema": "devstral-mistral-chat-tokenizer-identity-v1",
            "tokenizer_path": str(root),
            "tekken_sha256": digest,
            "chat_template_source": "mistral-common/tekken.json",
            "mistral_common_version": "1.8.4",
            "tools": None,
            "response_conversion": None,
        }

    @staticmethod
    def _validate_messages(messages: list[dict[str, Any]]) -> None:
        if type(messages) is not list:
            raise DevstralSerializationError("messages must be a builtins.list")
        if not messages:
            raise DevstralSerializationError("messages must not be empty")
        for index, message in enumerate(messages):
            if type(message) is not dict:
                raise DevstralSerializationError(
                    f"messages[{index}] must be a builtins.dict"
                )
            if set(message) != _MESSAGE_KEYS:
                raise DevstralSerializationError(
                    f"messages[{index}] must contain exactly role and content"
                )
            if type(message["role"]) is not str or message["role"] not in _ROLES:
                raise DevstralSerializationError(
                    f"messages[{index}].role is not an allowed text-chat role"
                )
            if type(message["content"]) is not str:
                raise DevstralSerializationError(
                    f"messages[{index}].content must be a builtins.str"
                )

    def encode(self, messages: list[dict[str, Any]]) -> MistralEncoding:
        """Serialize canonical text messages without tools or content repair."""
        self._validate_messages(messages)
        try:
            request = self._request_type.from_openai(
                messages=messages,
                tools=None,
            )
            encoded = self._tokenizer.encode_chat_completion(request)
        except Exception as error:
            raise DevstralSerializationError(
                f"mistral-common rejected the canonical messages: {error}"
            ) from error
        if not isinstance(encoded.text, str):
            raise DevstralSerializationError(
                "mistral-common did not return a rendered text prompt"
            )
        if type(encoded.tokens) is not list or any(
            type(token) is not int for token in encoded.tokens
        ):
            raise DevstralSerializationError(
                "mistral-common did not return integer prompt tokens"
            )
        return MistralEncoding(tuple(encoded.tokens), encoded.text)

    def render(self, messages: list[dict[str, Any]]) -> str:
        return self.encode(messages).rendered

    def count(self, messages: list[dict[str, Any]]) -> int:
        return self.encode(messages).token_count


__all__ = [
    "DevstralSerializationError",
    "ExactMistralChatTokenCounter",
    "MistralEncoding",
    "PINNED_TEKKEN_SHA256",
]
