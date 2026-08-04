"""mini-SWE-agent 2.4.6 text model backed by direct OpenAI-compatible HTTP."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from minisweagent.exceptions import FormatError
from minisweagent.models import GLOBAL_MODEL_STATS
from minisweagent.models.utils.actions_text import format_observation_messages, parse_regex_actions
from minisweagent.models.utils.openai_multimodal import expand_multimodal_content

try:
    from .action_protocol import (
        ACTION_REGEX,
        FORMAT_ERROR_TEMPLATE,
        escape_action_syntax_for_prompt,
    )
except ImportError:
    from cmpilot_action_protocol import (  # type: ignore[no-redef]
        ACTION_REGEX,
        FORMAT_ERROR_TEMPLATE,
        escape_action_syntax_for_prompt,
    )

try:
    from .openai_transport import (
        CompletionResult,
        MessageBoundaryError,
        OpenAIChatTransport,
        TransportError,
        normalize_message,
    )
except ImportError:
    from cmpilot_openai_transport import (  # type: ignore[no-redef]
        CompletionResult,
        MessageBoundaryError,
        OpenAIChatTransport,
        TransportError,
        normalize_message,
    )


class VllmTextModelConfig(BaseModel):
    """Only settings consumed by the project-owned direct adapter."""

    model_config = ConfigDict(extra="forbid")
    model_name: str
    base_url: str
    temperature: float = Field(default=0.0, ge=0.0)
    max_tokens: int = Field(default=512, gt=0)
    connect_timeout_seconds: float = Field(default=10.0, gt=0.0)
    read_timeout_seconds: float = Field(default=120.0, gt=0.0)
    transport_artifact_path: Path | None = None
    event_path: Path | None = None
    action_regex: str = ACTION_REGEX
    format_error_template: str = FORMAT_ERROR_TEMPLATE
    observation_template: str = (
        "{% if output.exception_info %}<exception>{{output.exception_info}}</exception>\n{% endif %}"
        "<returncode>{{output.returncode}}</returncode>\n<output>\n{{output.output}}</output>"
    )
    multimodal_regex: str = ""


def _type_name(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _response_parts(response: dict[str, Any]) -> tuple[dict[str, Any], str, str]:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise MessageBoundaryError("$.response.choices: expected a non-empty list")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise MessageBoundaryError(
            f"$.response.choices[0]: expected dictionary, found {_type_name(choice)}"
        )
    message = choice.get("message")
    if not isinstance(message, dict):
        raise MessageBoundaryError(
            f"$.response.choices[0].message: expected dictionary, found {_type_name(message)}"
        )
    finish_reason = choice.get("finish_reason", "")
    if finish_reason is None:
        finish_reason = ""
    if not isinstance(finish_reason, str):
        raise MessageBoundaryError(
            "$.response.choices[0].finish_reason: expected builtins.str, "
            f"found {_type_name(finish_reason)}"
        )
    canonical = normalize_message(message, "$.response.choices[0].message").value
    if canonical["role"] != "assistant":
        raise MessageBoundaryError(
            "$.response.choices[0].message.role: expected 'assistant', "
            f"found {canonical['role']!r}"
        )
    return canonical, canonical["content"], finish_reason


class VllmTextModel:
    """Direct HTTP implementation of mini-SWE-agent's 2.4.6 Model protocol."""

    def __init__(self, **kwargs: Any):
        self.config = VllmTextModelConfig(**kwargs)
        self.transport = OpenAIChatTransport(
            self.config.base_url,
            connect_timeout_seconds=self.config.connect_timeout_seconds,
            read_timeout_seconds=self.config.read_timeout_seconds,
        )
        self.request_count = 0

    @staticmethod
    def _append_jsonl(path: Path | None, record: dict[str, Any]) -> None:
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _emit_event(self, event: str, **details: Any) -> None:
        self._append_jsonl(
            self.config.event_path,
            {"event": event, "time_epoch": time.time(), **details},
        )

    def _record_success(self, result: CompletionResult) -> None:
        self._append_jsonl(
            self.config.transport_artifact_path,
            {
                "attempt": self.request_count,
                "classification": "success",
                "excluded_message_paths": list(result.excluded_message_paths),
                "request": result.request,
                "request_sha256": result.request_sha256,
                "response": result.body,
                "response_raw_body": result.raw_body,
                "response_sha256": result.response_sha256,
                "status_code": result.status_code,
            },
        )

    def _record_failure(self, error: BaseException) -> None:
        record: dict[str, Any] = {
            "attempt": self.request_count,
            "classification": "adapter_exception",
            "exception_type": type(error).__name__,
            "message": str(error),
        }
        if isinstance(error, TransportError):
            record.update(error.artifact_record())
        self._append_jsonl(self.config.transport_artifact_path, record)

    def _request(self, messages: list[dict[str, Any]], **kwargs: Any) -> CompletionResult:
        unknown = sorted(set(kwargs) - {"temperature", "max_tokens"})
        if unknown:
            raise ValueError(f"unsupported per-query settings: {unknown}")
        temperature = kwargs.get("temperature", self.config.temperature)
        max_tokens = kwargs.get("max_tokens", self.config.max_tokens)
        self.request_count += 1
        self._emit_event("model_request_attempted", request_index=self.request_count)
        try:
            result = self.transport.complete(
                messages,
                model=self.config.model_name,
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except BaseException as error:
            self._record_failure(error)
            self._emit_event(
                "model_request_failed",
                request_index=self.request_count,
                exception_type=type(error).__name__,
                message=str(error),
                classification=(
                    error.classification if isinstance(error, TransportError) else "adapter_exception"
                ),
            )
            raise
        self._record_success(result)
        self._emit_event(
            "model_request_succeeded",
            request_index=self.request_count,
            request_sha256=result.request_sha256,
            response_sha256=result.response_sha256,
            status_code=result.status_code,
        )
        return result

    def query(self, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        result = self._request(messages, **kwargs)
        canonical, content, finish_reason = _response_parts(result.body)
        usage = result.body.get("usage", {})
        if not isinstance(usage, dict):
            raise MessageBoundaryError(
                f"$.response.usage: expected dictionary, found {_type_name(usage)}"
            )
        transport_metadata = {
            "excluded_message_paths": list(result.excluded_message_paths),
            "request_sha256": result.request_sha256,
            "response_sha256": result.response_sha256,
            "status_code": result.status_code,
        }
        GLOBAL_MODEL_STATS.add(0.0)
        try:
            actions = parse_regex_actions(
                content,
                action_regex=self.config.action_regex,
                format_error_template=self.config.format_error_template,
                template_kwargs={"finish_reason": finish_reason},
            )
        except FormatError as error:
            error.messages[0]["extra"].update(
                {
                    "cost": 0.0,
                    "response": result.body,
                    "raw_response": result.body,
                    "transport": transport_metadata,
                    "usage": usage,
                }
            )
            raise
        return {
            **canonical,
            "extra": {
                "actions": actions,
                "cost": 0.0,
                "raw_response": result.body,
                "response": result.body,
                "timestamp": time.time(),
                "transport": transport_metadata,
                "usage": usage,
            },
        }

    def format_message(self, **kwargs: Any) -> dict[str, Any]:
        return expand_multimodal_content(kwargs, pattern=self.config.multimodal_regex)

    def format_observation_messages(
        self,
        message: dict[str, Any],
        outputs: list[dict[str, Any]],
        template_vars: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        messages = format_observation_messages(
            outputs,
            observation_template=self.config.observation_template,
            template_vars=template_vars,
            multimodal_regex=self.config.multimodal_regex,
        )
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                safe_content = escape_action_syntax_for_prompt(content)
                if safe_content != content:
                    message["content"] = safe_content
                    extra = message.setdefault("extra", {})
                    if isinstance(extra, dict):
                        extra["action_syntax_escaped"] = True
        return messages

    def get_template_vars(self, **kwargs: Any) -> dict[str, Any]:
        return self.config.model_dump()

    def serialize(self) -> dict[str, Any]:
        return {
            "info": {
                "config": {
                    "model": self.config.model_dump(mode="json"),
                    "model_type": f"{self.__class__.__module__}.{self.__class__.__name__}",
                }
            }
        }
