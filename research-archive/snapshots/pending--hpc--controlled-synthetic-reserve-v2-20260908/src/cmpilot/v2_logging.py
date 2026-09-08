"""Fail-closed V2 run logging schema and exclusive artifact writer."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
from typing import Any

from .v2_preflight import V2_PROTOCOL_VERSION, V2PreflightError


REQUIRED_METADATA_FIELDS = frozenset(
    {
        "run_id",
        "family",
        "masked_treatment_id",
        "model",
        "model_revision",
        "tokenizer_sha256",
        "harness_commit",
        "server_version",
        "cuda_version",
        "driver_version",
        "gpu_name",
        "gpu_count",
        "tensor_parallel_degree",
        "physical_context",
        "first_request_tokens",
        "trajectory_budget",
        "safety_reserve",
    }
)


@dataclass(frozen=True)
class V2TurnLog:
    decision_index: int
    transcript_tokens: int
    allowed_max_new_tokens: int
    server_prompt_tokens: int | None
    server_completion_tokens: int | None
    server_latency_seconds: float | None
    generated_tokens: int | None


@dataclass(frozen=True)
class V2CommandLog:
    decision_index: int
    command_sha256: str
    duration_seconds: float
    timed_out: bool
    raw_output_sha256: str
    raw_output_bytes: int
    visible_output_bytes: int
    output_truncated: bool
    omitted_output_bytes: int


@dataclass
class V2RunLog:
    metadata: dict[str, Any]
    turns: list[V2TurnLog] = field(default_factory=list)
    commands: list[V2CommandLog] = field(default_factory=list)
    tool_call_sequence: list[dict[str, Any]] = field(default_factory=list)
    termination_reason: str | None = None
    final_patch_sha256: str | None = None
    evaluator_results: dict[str, Any] | None = None
    technical_validity: str | None = None

    def __post_init__(self) -> None:
        missing = REQUIRED_METADATA_FIELDS - set(self.metadata)
        if missing:
            raise V2PreflightError(
                "V2 run metadata is missing: " + ", ".join(sorted(missing))
            )
        if self.metadata.get("protocol_version") != V2_PROTOCOL_VERSION:
            raise V2PreflightError("V2 run protocol version mismatch")

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "cmpilot-v2-run-log-v1",
            "metadata": self.metadata,
            "turns": [asdict(item) for item in self.turns],
            "commands": [asdict(item) for item in self.commands],
            "tool_call_sequence": self.tool_call_sequence,
            "termination_reason": self.termination_reason,
            "final_patch_sha256": self.final_patch_sha256,
            "evaluator_results": self.evaluator_results,
            "technical_validity": self.technical_validity,
        }


def write_v2_run_log(path: Path, record: V2RunLog) -> None:
    """Write a canonical run log once; replacement attempts need a new path."""

    payload = (
        json.dumps(record.as_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise V2PreflightError(f"refusing to overwrite V2 run log: {path}") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
