"""Checked-in runtime bindings for frozen final-family packages."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from .devstral_profile import DEVSTRAL_PRODUCTION_PROFILE
from .experiment_models import QWEN32B_PROFILE
from .final_model_runtime import (
    build_devstral_model_executor,
    build_qwen32b_model_executor,
)
from .final_runner import ModelExecutor, ScientificOperations
from .flask_cors_backend import FLASK_CORS_BACKEND_ID, build_flask_cors_backend
from .mcp_pinot_backend import MCP_PINOT_BACKEND_ID, build_mcp_pinot_backend


ScientificBackendBuilder = Callable[[Mapping[str, Any]], ScientificOperations]
ModelExecutorBuilder = Callable[[Mapping[str, Any]], ModelExecutor]


SCIENTIFIC_BACKENDS: Mapping[str, ScientificBackendBuilder] = MappingProxyType(
    {
        FLASK_CORS_BACKEND_ID: build_flask_cors_backend,
        MCP_PINOT_BACKEND_ID: build_mcp_pinot_backend,
    }
)
MODEL_EXECUTORS: Mapping[str, ModelExecutorBuilder] = MappingProxyType(
    {
        QWEN32B_PROFILE.profile_id: build_qwen32b_model_executor,
        DEVSTRAL_PRODUCTION_PROFILE.profile_id: build_devstral_model_executor,
    }
)


__all__ = [
    "MODEL_EXECUTORS",
    "SCIENTIFIC_BACKENDS",
    "ModelExecutorBuilder",
    "ScientificBackendBuilder",
]
