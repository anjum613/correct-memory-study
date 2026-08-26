"""Checked-in runtime bindings for frozen final-family packages.

No real family has been selected yet, so the scientific registry remains
intentionally empty.  The qualified Qwen model executor is safe to register
independently: it cannot start until a future scientific backend has written a
hash-bound attempt-local task-policy handoff.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import MappingProxyType
from typing import Any

from .experiment_models import QWEN32B_PROFILE
from .final_model_runtime import build_qwen32b_model_executor
from .final_runner import ModelExecutor, ScientificOperations


ScientificBackendBuilder = Callable[[Mapping[str, Any]], ScientificOperations]
ModelExecutorBuilder = Callable[[Mapping[str, Any]], ModelExecutor]


SCIENTIFIC_BACKENDS: Mapping[str, ScientificBackendBuilder] = MappingProxyType({})
MODEL_EXECUTORS: Mapping[str, ModelExecutorBuilder] = MappingProxyType(
    {QWEN32B_PROFILE.profile_id: build_qwen32b_model_executor}
)


__all__ = [
    "MODEL_EXECUTORS",
    "SCIENTIFIC_BACKENDS",
    "ModelExecutorBuilder",
    "ScientificBackendBuilder",
]
