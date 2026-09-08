"""V2-only scientific runtime primitives.

Nothing in this module is imported by the frozen V1 execution path.  The
functions are intentionally small so CPU tests can qualify the accounting and
classification rules before any model server is started.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
from typing import Any, Protocol


V2_PROTOCOL_VERSION = "correct-memory-v2-preflight-1"
TRAJECTORY_BUDGET_EXHAUSTED = "TRAJECTORY_BUDGET_EXHAUSTED"
VISIBLE_TOOL_OUTPUT_BYTES = 32 * 1024


class V2PreflightError(ValueError):
    """A V2 runtime invariant is invalid."""


@dataclass(frozen=True)
class V2ContextProfile:
    physical_context: int = 32_768
    trajectory_budget: int = 16_384
    safety_reserve: int = 256
    per_turn_generation_ceiling: int = 4_096
    maximum_model_decisions: int = 32

    def __post_init__(self) -> None:
        values = asdict(self)
        if any(type(value) is not int or value <= 0 for value in values.values()):
            raise V2PreflightError("V2 context-profile values must be positive integers")
        if self.trajectory_budget + self.safety_reserve > self.physical_context:
            raise V2PreflightError("trajectory budget and reserve exceed physical context")


@dataclass(frozen=True)
class V2TurnBudget:
    first_request_tokens: int
    transcript_tokens: int
    post_ingestion_tokens: int
    available_trajectory_tokens: int
    allowed_max_new_tokens: int
    physical_context: int
    trajectory_budget: int
    safety_reserve: int
    per_turn_generation_ceiling: int
    request_allowed: bool
    termination_reason: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "cmpilot-v2-turn-budget-v1",
            "protocol_version": V2_PROTOCOL_VERSION,
            **asdict(self),
        }


def calculate_v2_turn_budget(
    *,
    first_request_tokens: int,
    transcript_tokens: int,
    profile: V2ContextProfile = V2ContextProfile(),
) -> V2TurnBudget:
    """Apply P/B/R/G accounting to one complete serialized transcript."""

    if type(first_request_tokens) is not int or first_request_tokens < 0:
        raise V2PreflightError("first_request_tokens must be a non-negative integer")
    if type(transcript_tokens) is not int or transcript_tokens < first_request_tokens:
        raise V2PreflightError("transcript_tokens must be an integer no smaller than P")
    if first_request_tokens + profile.trajectory_budget + profile.safety_reserve > profile.physical_context:
        raise V2PreflightError("P + B + R exceeds physical context")

    post_ingestion = transcript_tokens - first_request_tokens
    available = profile.trajectory_budget - post_ingestion
    allowed = min(profile.per_turn_generation_ceiling, max(0, available))
    request_allowed = available > 0
    return V2TurnBudget(
        first_request_tokens=first_request_tokens,
        transcript_tokens=transcript_tokens,
        post_ingestion_tokens=post_ingestion,
        available_trajectory_tokens=available,
        allowed_max_new_tokens=allowed,
        physical_context=profile.physical_context,
        trajectory_budget=profile.trajectory_budget,
        safety_reserve=profile.safety_reserve,
        per_turn_generation_ceiling=profile.per_turn_generation_ceiling,
        request_allowed=request_allowed,
        termination_reason=None if request_allowed else TRAJECTORY_BUDGET_EXHAUSTED,
    )


@dataclass(frozen=True)
class VisibleToolOutput:
    visible_text: str
    raw_sha256: str
    raw_bytes: int
    visible_bytes: int
    truncated: bool
    omitted_bytes: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "cmpilot-v2-visible-tool-output-v1",
            **asdict(self),
        }


def _utf8_prefix(payload: bytes, limit: int) -> bytes:
    candidate = payload[:limit]
    while candidate:
        try:
            candidate.decode("utf-8")
            return candidate
        except UnicodeDecodeError as error:
            candidate = candidate[: error.start]
    return b""


def _utf8_suffix(payload: bytes, limit: int) -> bytes:
    candidate = payload[-limit:]
    while candidate:
        try:
            candidate.decode("utf-8")
            return candidate
        except UnicodeDecodeError as error:
            candidate = candidate[error.end :]
    return b""


def bound_visible_tool_output(
    raw_text: str,
    *,
    maximum_visible_bytes: int = VISIBLE_TOOL_OUTPUT_BYTES,
) -> VisibleToolOutput:
    """Preserve deterministic UTF-8 head/tail text within one byte ceiling."""

    if not isinstance(raw_text, str):
        raise V2PreflightError("tool output must be text")
    if type(maximum_visible_bytes) is not int or maximum_visible_bytes < 256:
        raise V2PreflightError("visible output ceiling must be an integer >= 256")
    raw = raw_text.encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if len(raw) <= maximum_visible_bytes:
        return VisibleToolOutput(raw_text, digest, len(raw), len(raw), False, 0)

    marker_template = "\n<V2_TOOL_OUTPUT_TRUNCATED omitted_bytes={omitted} raw_sha256={digest}>\n"
    omitted = len(raw)
    for _ in range(3):
        marker = marker_template.format(omitted=omitted, digest=digest).encode("ascii")
        payload_budget = maximum_visible_bytes - len(marker)
        if payload_budget <= 0:
            raise V2PreflightError("visible output ceiling is too small for metadata")
        head_limit = (payload_budget + 1) // 2
        tail_limit = payload_budget // 2
        head = _utf8_prefix(raw, head_limit)
        tail = _utf8_suffix(raw, tail_limit)
        omitted = len(raw) - len(head) - len(tail)
    marker = marker_template.format(omitted=omitted, digest=digest).encode("ascii")
    visible = head + marker + tail
    if len(visible) > maximum_visible_bytes:
        raise AssertionError("bounded tool output exceeded its byte ceiling")
    return VisibleToolOutput(
        visible.decode("utf-8"), digest, len(raw), len(visible), True, omitted
    )


def preserve_raw_tool_output(path: Path, raw_text: str) -> VisibleToolOutput:
    """Exclusively save full raw output and return model-visible metadata."""

    path = Path(path)
    raw = raw_text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise V2PreflightError(f"refusing to overwrite raw tool output: {path}") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    return bound_visible_tool_output(raw_text)


SCIENTIFIC_TERMINATIONS = frozenset(
    {
        "NO_TOOL_CALLS",
        "REFUSAL",
        "MALFORMED_MODEL_TOOL_CALL",
        "EMPTY_PATCH",
        "TEST_FAILURE",
        "SECURITY_FAILURE",
        "MODEL_CHOSEN_COMMAND_TIMEOUT",
        "MAXIMUM_STEP_EXHAUSTION",
        TRAJECTORY_BUDGET_EXHAUSTED,
    }
)
TECHNICAL_INVALID_TERMINATIONS = frozenset(
    {
        "MACHINE_FAILURE",
        "CUDA_FAILURE",
        "SERVER_CRASH_OR_OOM",
        "TRANSPORT_FAILURE",
        "HARNESS_EXCEPTION",
        "CORRUPTED_CHECKOUT",
        "EVALUATOR_INFRASTRUCTURE_FAILURE",
        "MODEL_SERVER_UNAVAILABLE",
        "PARSER_DEFECT_VALID_SYNTAX",
    }
)


def classify_v2_technical_validity(termination_reason: str) -> str:
    """Return SCIENTIFIC or TECHNICAL_INVALID without outcome-based guessing."""

    if termination_reason in SCIENTIFIC_TERMINATIONS:
        return "SCIENTIFIC"
    if termination_reason in TECHNICAL_INVALID_TERMINATIONS:
        return "TECHNICAL_INVALID"
    raise V2PreflightError(f"unclassified V2 termination reason: {termination_reason}")


class ExactTranscriptCounter(Protocol):
    def count(self, messages: list[dict[str, Any]]) -> int: ...


class V2RuntimeLedger:
    """Count complete histories without dropping, compacting, or summarizing."""

    def __init__(
        self,
        *,
        initial_messages: list[dict[str, Any]],
        counter: ExactTranscriptCounter,
        raw_output_directory: Path,
        profile: V2ContextProfile = V2ContextProfile(),
    ):
        if not initial_messages:
            raise V2PreflightError("initial transcript must not be empty")
        self.messages = [dict(message) for message in initial_messages]
        self.counter = counter
        self.raw_output_directory = Path(raw_output_directory)
        self.profile = profile
        self.first_request_tokens = counter.count(self.messages)
        if (
            self.first_request_tokens
            + profile.trajectory_budget
            + profile.safety_reserve
            > profile.physical_context
        ):
            raise V2PreflightError("P + B + R exceeds physical context")
        self.tool_output_index = 0

    def append_message(self, role: str, content: str) -> None:
        if role not in {"assistant", "tool", "user"} or not isinstance(content, str):
            raise V2PreflightError("invalid model-visible transcript message")
        self.messages.append({"role": role, "content": content})

    def append_tool_output(self, raw_text: str) -> VisibleToolOutput:
        self.tool_output_index += 1
        path = self.raw_output_directory / f"tool-output-{self.tool_output_index:04d}.txt"
        visible = preserve_raw_tool_output(path, raw_text)
        self.append_message("user", visible.visible_text)
        return visible

    def next_turn_budget(self) -> V2TurnBudget:
        transcript_tokens = self.counter.count(self.messages)
        return calculate_v2_turn_budget(
            first_request_tokens=self.first_request_tokens,
            transcript_tokens=transcript_tokens,
            profile=self.profile,
        )
