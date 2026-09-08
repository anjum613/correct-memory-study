"""Strict, deterministic configuration handling for mini-SWE-agent 2.4.6."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path, PurePath
from typing import Any


DEFAULT_QWEN32B_TOKENIZER_PATH = (
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
    "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
)


class PlainDataError(ValueError):
    """Raised when a value cannot safely cross the configuration boundary."""


class MiniSWEConfigError(ValueError):
    """Raised when a mini-SWE configuration contains unsupported structure."""


@dataclass(frozen=True)
class MiniSWEEndpointSettings:
    """OpenAI-compatible endpoint settings, kept separate from run metadata."""

    base_url: str
    model: str
    request_timeout_seconds: float | None = None
    max_retries: int | None = None
    connect_timeout_seconds: float = 10.0
    read_timeout_seconds: float = 120.0
    tokenizer_path: str = DEFAULT_QWEN32B_TOKENIZER_PATH


SUPPORTED_TOP_LEVEL_FIELDS = frozenset({"agent", "environment", "model"})
SUPPORTED_AGENT_FIELDS = frozenset(
    {
        "system_template",
        "instance_template",
        "step_limit",
        "cost_limit",
        "wall_time_limit_seconds",
        "max_consecutive_format_errors",
        "output_path",
    }
)
SUPPORTED_ENVIRONMENT_FIELDS = frozenset({"cwd", "env", "timeout"})
SUPPORTED_MODEL_FIELDS = frozenset(
    {
        "model_kwargs",
        "cost_tracking",
        "format_error_template",
        "observation_template",
        "multimodal_regex",
        "action_regex",
        "temperature",
        "max_tokens",
        "top_p",
        "top_k",
        "min_p",
        "presence_penalty",
        "repetition_penalty",
        "seed",
        "samples_per_call",
        "connect_timeout_seconds",
        "read_timeout_seconds",
        "tokenizer_path",
        "tokenizer_json_sha256",
        "tokenizer_config_sha256",
        "context_limit",
        "context_safety_margin",
        "minimum_useful_completion",
        "request_budget_artifact_path",
    }
)
DIRECT_MODEL_CLASS = "cmpilot_vllm_text_model.VllmTextModel"
_SENSITIVE_KEY = re.compile(
    r"(?:^|[_-])(?:api[_-]?key|authorization|token|password|secret)(?:$|[_-])", re.IGNORECASE
)
_PUBLIC_AUTHORIZATION_KEYS = frozenset(
    {"command_authorization_policy", "command_authorization_status"}
)


def _is_sensitive_key(key: str) -> bool:
    return (
        key.lower() not in _PUBLIC_AUTHORIZATION_KEYS
        and _SENSITIVE_KEY.search(key) is not None
    )


def _type_name(value: object) -> str:
    value_type = type(value)
    return f"{value_type.__module__}.{value_type.__qualname__}"


def _child_path(path: str, key: str) -> str:
    if key.isidentifier():
        return f"{path}.{key}"
    return f"{path}[{json.dumps(key)}]"


def _is_pydantic_model(value: object) -> bool:
    """Recognize Pydantic v2 models without making Pydantic a cmpilot dependency."""
    return callable(getattr(value, "model_dump", None)) and isinstance(
        getattr(type(value), "model_fields", None), dict
    )


def to_plain_data(value: Any, path: str = "$") -> Any:
    """Convert supported structured values to JSON/YAML-safe basic data.

    Path, Enum, dataclass, Pydantic-model, and tuple values are converted
    explicitly. All other custom values are rejected at their exact path.
    """
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PlainDataError(f"{path}: non-finite float {_type_name(value)} is not supported")
        return float(value)
    if isinstance(value, PurePath):
        return str(value)
    if isinstance(value, Enum):
        return to_plain_data(value.value, path)
    if callable(getattr(value, "get_secret_value", None)):
        raise PlainDataError(f"{path}: secret wrapper {_type_name(value)} is not supported")
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: to_plain_data(getattr(value, field.name), _child_path(path, field.name))
            for field in fields(value)
        }
    if _is_pydantic_model(value):
        return to_plain_data(value.model_dump(mode="python"), path)
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise PlainDataError(
                    f"{path}: dictionary key {key!r} has unsupported type {_type_name(key)}; expected builtins.str"
                )
            result[key] = to_plain_data(item, _child_path(path, key))
        return result
    if isinstance(value, (list, tuple)):
        return [to_plain_data(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise PlainDataError(f"{path}: unsupported value type {_type_name(value)}")


def validate_plain_data(value: Any, path: str = "$") -> None:
    """Require only null, scalar primitives, lists, and string-keyed dictionaries."""
    if value is None or isinstance(value, (str, bool)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PlainDataError(f"{path}: non-finite float {_type_name(value)} is not supported")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_plain_data(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise PlainDataError(
                    f"{path}: dictionary key {key!r} has unsupported type {_type_name(key)}; expected builtins.str"
                )
            validate_plain_data(item, _child_path(path, key))
        return
    raise PlainDataError(f"{path}: unsupported value type {_type_name(value)}")


def describe_data_types(value: Any, path: str = "$") -> dict[str, str]:
    """Return the Python type observed at every reachable configuration path."""
    result = {path: _type_name(value)}
    if isinstance(value, dict):
        for key, item in value.items():
            key_path = _child_path(path, key) if isinstance(key, str) else f"{path}[key={key!r}]"
            result.update(describe_data_types(item, key_path))
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            result.update(describe_data_types(item, f"{path}[{index}]"))
    elif is_dataclass(value) and not isinstance(value, type):
        for field in fields(value):
            result.update(describe_data_types(getattr(value, field.name), _child_path(path, field.name)))
    elif _is_pydantic_model(value):
        result.update(describe_data_types(value.model_dump(mode="python"), path))
    return result


def deterministic_json(value: Any) -> tuple[Any, str]:
    """Canonicalize, validate, serialize, parse, and compare a JSON structure."""
    plain = to_plain_data(value)
    validate_plain_data(plain)
    text = json.dumps(plain, indent=2, sort_keys=True, allow_nan=False) + "\n"
    parsed = json.loads(text)
    validate_plain_data(parsed)
    if json.dumps(parsed, sort_keys=True, allow_nan=False) != json.dumps(plain, sort_keys=True, allow_nan=False):
        raise PlainDataError("$: JSON round trip changed the configuration structure")
    return plain, text


def assert_no_sensitive_keys(value: Any, path: str = "$") -> None:
    """Reject secret-bearing fields before a configuration artifact is written."""
    validate_plain_data(value, path)
    if isinstance(value, dict):
        for key, item in value.items():
            child = _child_path(path, key)
            if _is_sensitive_key(key):
                raise PlainDataError(f"{child}: sensitive configuration keys must not be persisted")
            assert_no_sensitive_keys(item, child)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            assert_no_sensitive_keys(item, f"{path}[{index}]")


def _merge_dicts(*layers: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for layer in layers:
        for key, value in layer.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = _merge_dicts(result[key], value)
            elif isinstance(value, dict):
                result[key] = _merge_dicts(value)
            else:
                result[key] = value
    return result


def _require_supported_fields(section: str, value: Any, supported: frozenset[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise MiniSWEConfigError(f"$.{section}: expected dictionary, found {_type_name(value)}")
    unknown = sorted(set(value) - supported)
    if unknown:
        raise MiniSWEConfigError(f"$.{section}: unsupported mini-SWE-agent 2.4.6 fields: {unknown}")
    return value


def build_mini_swe_config(
    base_config: dict[str, Any],
    overlay_config: dict[str, Any],
    *,
    endpoint: MiniSWEEndpointSettings,
    repository: Path,
    trajectory: Path,
    agent_environment: dict[str, str],
    transport_artifact: Path | None = None,
    request_budget_artifact: Path | None = None,
    event_path: Path | None = None,
) -> dict[str, Any]:
    """Build the minimal direct-model configuration loaded by mini-SWE 2.4.6."""
    for name, layer in (("base", base_config), ("overlay", overlay_config)):
        if not isinstance(layer, dict):
            raise MiniSWEConfigError(f"$.{name}: expected dictionary, found {_type_name(layer)}")
        unknown = sorted(set(layer) - SUPPORTED_TOP_LEVEL_FIELDS)
        if unknown:
            raise MiniSWEConfigError(f"$.{name}: unsupported top-level fields: {unknown}")

    merged = _merge_dicts(base_config, overlay_config)
    agent = dict(_require_supported_fields("agent", merged.get("agent", {}), SUPPORTED_AGENT_FIELDS))
    environment = dict(
        _require_supported_fields("environment", merged.get("environment", {}), SUPPORTED_ENVIRONMENT_FIELDS)
    )
    model_input = dict(_require_supported_fields("model", merged.get("model", {}), SUPPORTED_MODEL_FIELDS))

    agent["output_path"] = trajectory
    environment["cwd"] = str(repository)
    configured_environment = environment.get("env", {})
    if not isinstance(configured_environment, dict):
        raise MiniSWEConfigError("$.environment.env: expected dictionary")
    environment["env"] = configured_environment | agent_environment

    # default.yaml contains LiteLLM's drop_params setting. It is recognized
    # only as legacy input and never crosses the direct-model boundary.
    legacy_kwargs = model_input.pop("model_kwargs", {})
    if not isinstance(legacy_kwargs, dict):
        raise MiniSWEConfigError("$.model.model_kwargs: expected dictionary")
    unknown_legacy = sorted(set(legacy_kwargs) - {"drop_params", "temperature", "max_tokens"})
    if unknown_legacy:
        raise MiniSWEConfigError(
            f"$.model.model_kwargs: unsupported direct-adapter fields: {unknown_legacy}"
        )
    model_input.pop("cost_tracking", None)
    if endpoint.max_retries not in (None, 0):
        raise MiniSWEConfigError(
            "$.endpoint.max_retries: the direct adapter performs exactly one HTTP attempt"
        )

    request_timeout = endpoint.request_timeout_seconds
    temperature = model_input.pop("temperature", legacy_kwargs.get("temperature", 0.0))
    max_tokens = model_input.pop("max_tokens", legacy_kwargs.get("max_tokens", 512))
    connect_timeout = model_input.pop(
        "connect_timeout_seconds",
        request_timeout if request_timeout is not None else endpoint.connect_timeout_seconds,
    )
    read_timeout = model_input.pop(
        "read_timeout_seconds",
        request_timeout if request_timeout is not None else endpoint.read_timeout_seconds,
    )
    tokenizer_path = model_input.pop("tokenizer_path", endpoint.tokenizer_path)
    tokenizer_json_sha256 = model_input.pop("tokenizer_json_sha256", None)
    tokenizer_config_sha256 = model_input.pop("tokenizer_config_sha256", None)
    context_limit = model_input.pop("context_limit", 4096)
    context_safety_margin = model_input.pop("context_safety_margin", 32)
    minimum_useful_completion = model_input.pop("minimum_useful_completion", 64)
    configured_budget_artifact = model_input.pop(
        "request_budget_artifact_path", None
    )
    model = {
        "model_class": DIRECT_MODEL_CLASS,
        "model_name": endpoint.model,
        "base_url": endpoint.base_url,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "tokenizer_path": tokenizer_path,
        "context_limit": context_limit,
        "context_safety_margin": context_safety_margin,
        "minimum_useful_completion": minimum_useful_completion,
        "connect_timeout_seconds": connect_timeout,
        "read_timeout_seconds": read_timeout,
        "transport_artifact_path": str(
            transport_artifact or trajectory.with_name("model-transport.jsonl")
        ),
        "request_budget_artifact_path": str(
            request_budget_artifact
            or configured_budget_artifact
            or trajectory.with_name("request-budgets.jsonl")
        ),
        "event_path": str(event_path or trajectory.with_name("adapter-events.jsonl")),
        **model_input,
    }
    if tokenizer_json_sha256 is not None:
        model["tokenizer_json_sha256"] = tokenizer_json_sha256
    if tokenizer_config_sha256 is not None:
        model["tokenizer_config_sha256"] = tokenizer_config_sha256

    return {"agent": agent, "environment": environment, "model": model}
