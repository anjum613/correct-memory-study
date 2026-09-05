"""Exact Qwen chat-token accounting and frozen request-budget policy."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
from typing import Any


CONTEXT_BUDGET_VERSION = "qwen32b-context-budget-v1"
CONTEXT_BUDGET_EXHAUSTED = "CONTEXT_BUDGET_EXHAUSTED"
CONTEXT_LIMIT = 4096
CONTEXT_SAFETY_MARGIN = 32
MINIMUM_USEFUL_COMPLETION = 64
CONFIGURED_COMPLETION_LIMIT = 512
DEFAULT_QWEN32B_TOKENIZER = Path(
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
    "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
)
PINNED_TOKENIZER_JSON_SHA256 = (
    "c0382117ea329cdf097041132f6d735924b697924d6f6fc3945713e96ce87539"
)
PINNED_TOKENIZER_CONFIG_SHA256 = (
    "959e7f1d9a1b7641a6d6ce05ca97b75c7894fcb66cbe5a040406458fb1128ee4"
)


class ContextBudgetError(ValueError):
    """The frozen context policy or tokenizer inputs are invalid."""


@dataclass(frozen=True)
class RequestTokenBudget:
    """Pre-transport evidence for one canonical chat request."""

    prompt_tokens: int
    configured_completion_limit: int
    effective_completion_limit: int
    safety_margin: int
    minimum_useful_completion: int
    context_limit: int
    available_completion: int
    emitted_request_token_ceiling: int
    total_possible_with_reserve: int
    http_request_allowed: bool
    termination_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "qwen-chat-request-budget-v1",
            "policy_version": CONTEXT_BUDGET_VERSION,
            **asdict(self),
        }


class ContextBudgetExhausted(RuntimeError):
    """The conversation cannot support a useful completion without overflow."""

    def __init__(self, budget: RequestTokenBudget):
        self.budget = budget
        super().__init__(
            f"{CONTEXT_BUDGET_EXHAUSTED}: only "
            f"{budget.available_completion} completion tokens remain"
        )

    def artifact_record(self) -> dict[str, Any]:
        return {
            "classification": "context_budget_exhausted",
            "exception_type": type(self).__name__,
            "message": str(self),
            "http_request_sent": False,
            "termination_reason": CONTEXT_BUDGET_EXHAUSTED,
            "token_budget": self.budget.as_dict(),
        }


def calculate_request_budget(
    *,
    prompt_tokens: int,
    configured_completion_limit: int = CONFIGURED_COMPLETION_LIMIT,
    context_limit: int = CONTEXT_LIMIT,
    safety_margin: int = CONTEXT_SAFETY_MARGIN,
    minimum_useful_completion: int = MINIMUM_USEFUL_COMPLETION,
) -> RequestTokenBudget:
    """Clamp completion length or fail closed before HTTP transport."""
    values = {
        "prompt_tokens": prompt_tokens,
        "configured_completion_limit": configured_completion_limit,
        "context_limit": context_limit,
        "safety_margin": safety_margin,
        "minimum_useful_completion": minimum_useful_completion,
    }
    if any(not isinstance(value, int) for value in values.values()):
        raise ContextBudgetError("context-budget values must be integers")
    if prompt_tokens < 0:
        raise ContextBudgetError("prompt_tokens must not be negative")
    if configured_completion_limit < 1:
        raise ContextBudgetError("configured completion limit must be positive")
    if context_limit < 1:
        raise ContextBudgetError("context limit must be positive")
    if safety_margin < 0:
        raise ContextBudgetError("safety margin must not be negative")
    if minimum_useful_completion < 1:
        raise ContextBudgetError("minimum useful completion must be positive")
    if safety_margin + minimum_useful_completion > context_limit:
        raise ContextBudgetError(
            "safety margin and minimum completion exceed the context limit"
        )

    available = context_limit - prompt_tokens - safety_margin
    effective = min(configured_completion_limit, max(0, available))
    total = prompt_tokens + effective + safety_margin
    emitted_ceiling = prompt_tokens + effective
    allowed = effective >= minimum_useful_completion and total <= context_limit
    return RequestTokenBudget(
        prompt_tokens=prompt_tokens,
        configured_completion_limit=configured_completion_limit,
        effective_completion_limit=effective,
        safety_margin=safety_margin,
        minimum_useful_completion=minimum_useful_completion,
        context_limit=context_limit,
        available_completion=available,
        emitted_request_token_ceiling=emitted_ceiling,
        total_possible_with_reserve=total,
        http_request_allowed=allowed,
        termination_reason=None if allowed else CONTEXT_BUDGET_EXHAUSTED,
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class ExactQwenChatTokenCounter:
    """Use the pinned tokenizer JSON and its exact Qwen chat template.

    Imports are deliberately lazy: the evaluated mini-SWE environment contains
    the already-frozen tokenizers and jinja2 packages, while cmpilot's
    controller environment does not need either dependency.
    """

    def __init__(
        self,
        tokenizer_path: Path,
        *,
        expected_tokenizer_json_sha256: str = PINNED_TOKENIZER_JSON_SHA256,
        expected_tokenizer_config_sha256: str = PINNED_TOKENIZER_CONFIG_SHA256,
    ):
        root = Path(tokenizer_path)
        if not root.is_absolute() or not root.is_dir():
            raise ContextBudgetError(
                f"tokenizer path must be an existing absolute directory: {root}"
            )
        tokenizer_json = root / "tokenizer.json"
        tokenizer_config = root / "tokenizer_config.json"
        if not tokenizer_json.is_file() or not tokenizer_config.is_file():
            raise ContextBudgetError("pinned tokenizer files are incomplete")
        tokenizer_digest = _sha256(tokenizer_json)
        config_digest = _sha256(tokenizer_config)
        if tokenizer_digest != expected_tokenizer_json_sha256:
            raise ContextBudgetError(
                "tokenizer.json does not match the pinned Qwen tokenizer"
            )
        if config_digest != expected_tokenizer_config_sha256:
            raise ContextBudgetError(
                "tokenizer_config.json does not match the pinned Qwen chat template"
            )
        try:
            configuration = json.loads(tokenizer_config.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ContextBudgetError(
                f"could not read tokenizer configuration: {error}"
            ) from error
        template_source = configuration.get("chat_template")
        if not isinstance(template_source, str) or not template_source:
            raise ContextBudgetError("pinned tokenizer chat template is missing")
        try:
            from jinja2.sandbox import ImmutableSandboxedEnvironment
            from tokenizers import Tokenizer
        except ImportError as error:
            raise ContextBudgetError(
                "frozen tokenizers and jinja2 dependencies are required"
            ) from error

        environment = ImmutableSandboxedEnvironment(
            trim_blocks=True,
            lstrip_blocks=True,
        )

        def raise_exception(message: str) -> None:
            raise ContextBudgetError(str(message))

        environment.globals["raise_exception"] = raise_exception
        self._template = environment.from_string(template_source)
        self._tokenizer = Tokenizer.from_file(str(tokenizer_json))
        self._template_values = {
            key: value
            for key, value in configuration.items()
            if key.endswith("_token") and isinstance(value, (str, type(None)))
        }
        self.identity = {
            "schema": "qwen-chat-tokenizer-identity-v1",
            "tokenizer_path": str(root),
            "tokenizer_json_sha256": tokenizer_digest,
            "tokenizer_config_sha256": config_digest,
            "chat_template_source": "tokenizer_config.json",
            "chat_template_add_generation_prompt": True,
            "encoding_add_special_tokens": False,
            "tool_call_arguments_normalized_for_template": True,
        }

    @staticmethod
    def _template_messages(
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Adapt OpenAI JSON-string arguments to Qwen's Jinja mapping shape."""
        normalized_messages: list[dict[str, Any]] = []
        for message in messages:
            normalized_message = dict(message)
            tool_calls = message.get("tool_calls")
            if not isinstance(tool_calls, list):
                normalized_messages.append(normalized_message)
                continue
            normalized_calls: list[Any] = []
            for tool_call in tool_calls:
                if not isinstance(tool_call, dict):
                    normalized_calls.append(tool_call)
                    continue
                normalized_call = dict(tool_call)
                function = tool_call.get("function")
                if isinstance(function, dict):
                    normalized_function = dict(function)
                    arguments = function.get("arguments")
                    if isinstance(arguments, str):
                        try:
                            arguments = json.loads(arguments)
                        except json.JSONDecodeError as error:
                            raise ContextBudgetError(
                                "assistant tool-call arguments are not valid JSON"
                            ) from error
                        if not isinstance(arguments, dict):
                            raise ContextBudgetError(
                                "assistant tool-call arguments must decode to a mapping"
                            )
                        normalized_function["arguments"] = arguments
                    normalized_call["function"] = normalized_function
                normalized_calls.append(normalized_call)
            normalized_message["tool_calls"] = normalized_calls
            normalized_messages.append(normalized_message)
        return normalized_messages

    def render(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> str:
        return self._template.render(
            messages=self._template_messages(messages),
            tools=tools,
            documents=None,
            add_generation_prompt=True,
            **self._template_values,
        )

    def count(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> int:
        rendered = self.render(messages, tools=tools)
        return len(
            self._tokenizer.encode(rendered, add_special_tokens=False).ids
        )
