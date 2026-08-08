"""Project-owned safety policy for mini-SWE-agent text actions."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

try:
    from ...task_file_policy import CALCULATOR_AGENT_POLICY_TEXT
except ImportError:
    from cmpilot_task_file_policy import (  # type: ignore[no-redef]
        CALCULATOR_AGENT_POLICY_TEXT,
    )


ACTION_REGEX = r"```mswea_bash_command\s*\n(.*?)\n```"
ACTION_FENCE_OPEN = "```mswea_bash_command"
COMPLETION_SENTINEL = "echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT"
MAX_CONSECUTIVE_PROTOCOL_ERRORS = 3

INITIAL_SYSTEM_TEMPLATE = """You are a coding agent that can interact with a repository through shell commands.

""" + CALCULATOR_AGENT_POLICY_TEXT + """

Every response must contain exactly one action block and exactly one concrete shell command.
A valid response may include brief reasoning, followed by the action syntax shown once here:

```mswea_bash_command
pwd
```

Wait for the observation from that command before choosing the next command.
Never return placeholder text. In particular, do not copy labels or template markers as a command.
Do not return more than one action block in a response.
"""

INSTANCE_TEMPLATE = """Please solve this issue: {{task}}

Work step by step: inspect the repository and tests, run tests, edit only the working
repository as needed, rerun tests, and submit when complete. Directory and environment
changes are not persistent between commands.

Finish only by running `echo COMPLETE_TASK_AND_SUBMIT_FINAL_OUTPUT` as its own command.
The action syntax is defined in the system message. Return one concrete command, then wait
for its observation before choosing another command.
"""

RECOVERY_PROMPT = """The previous response did not contain exactly one safe action.
Provide exactly one concrete command. The action syntax is already defined in the initial
system message. Do not copy placeholder text and do not repeat the previous invalid
response. Wait for the resulting observation before selecting another command.
"""

FORMAT_ERROR_TEMPLATE = RECOVERY_PROMPT
INVALID_ACTION_TEMPLATE = RECOVERY_PROMPT
PROTOCOL_LIMIT_MESSAGE = (
    "The action protocol safety limit was reached. No rejected content was executed."
)

_EXACT_PLACEHOLDERS = frozenset(
    {"<action>", "<command>", "your_command_here", "anything"}
)
_GENERIC_ANGLE_PLACEHOLDER = re.compile(r"<[^<>\r\n]+>")
_UNRESOLVED_TEMPLATE = re.compile(r"{{.*?}}|{%.*?%}", re.DOTALL)
_EXCLUDED_REPOSITORY_PARTS = frozenset({".git", ".pytest_cache", "__pycache__"})


@dataclass(frozen=True)
class ActionValidation:
    valid: bool
    command: str
    reason: str | None = None


@dataclass(frozen=True)
class ProtocolEvaluation:
    accepted: bool
    raw_response: str
    action_count: int
    command: str | None
    rejected_command: str | None
    event: str | None
    validation_reason: str | None
    termination_reason: str | None


@dataclass(frozen=True)
class ProtocolDecision:
    termination_reason: str | None


class ProtocolErrorState:
    """Unified consecutive and repeated-invalid protocol state."""

    def __init__(self, maximum_consecutive_errors: int = MAX_CONSECUTIVE_PROTOCOL_ERRORS):
        if maximum_consecutive_errors < 1:
            raise ValueError("maximum_consecutive_errors must be positive")
        self.maximum_consecutive_errors = maximum_consecutive_errors
        self.consecutive_protocol_errors = 0
        self.invalid_response_count = 0
        self.invalid_action_count = 0
        self._last_invalid_raw: str | None = None
        self._raw_repeat_count = 0
        self._last_rejected_command: str | None = None
        self._command_repeat_count = 0

    def record_invalid(
        self,
        raw_response: str,
        *,
        rejected_command: str | None = None,
    ) -> ProtocolDecision:
        self.consecutive_protocol_errors += 1
        self.invalid_response_count += 1
        if raw_response == self._last_invalid_raw:
            self._raw_repeat_count += 1
        else:
            self._last_invalid_raw = raw_response
            self._raw_repeat_count = 1

        if rejected_command is not None:
            self.invalid_action_count += 1
            if rejected_command == self._last_rejected_command:
                self._command_repeat_count += 1
            else:
                self._last_rejected_command = rejected_command
                self._command_repeat_count = 1
            if self._command_repeat_count >= 2:
                return ProtocolDecision("REPEATED_INVALID_ACTION")
        else:
            self._last_rejected_command = None
            self._command_repeat_count = 0
            if self._raw_repeat_count >= 2:
                return ProtocolDecision("REPEATED_INVALID_RESPONSE")

        if self.consecutive_protocol_errors >= self.maximum_consecutive_errors:
            return ProtocolDecision(
                "INVALID_ACTION_LIMIT" if rejected_command is not None else "FORMAT_ERROR_LIMIT"
            )
        return ProtocolDecision(None)

    def record_valid_action(self) -> None:
        self.consecutive_protocol_errors = 0
        self._last_invalid_raw = None
        self._raw_repeat_count = 0
        self._last_rejected_command = None
        self._command_repeat_count = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "consecutive_protocol_errors": self.consecutive_protocol_errors,
            "invalid_response_count": self.invalid_response_count,
            "invalid_action_count": self.invalid_action_count,
        }


def extract_action_blocks(content: str, action_regex: str = ACTION_REGEX) -> list[str]:
    """Use the exact production parser expression and extraction semantics."""
    return [action.strip() for action in re.findall(action_regex, content, re.DOTALL)]


def production_parser_match_count(content: str, action_regex: str = ACTION_REGEX) -> int:
    return len(extract_action_blocks(content, action_regex))


def render_recovery_prompt(
    *,
    event: str,
    action_count: int,
    validation_reason: str | None = None,
) -> str:
    """Render safe feedback without echoing any untrusted response or action."""
    safe_event = event if re.fullmatch(r"[A-Z_]+", event) else "INVALID_ACTION"
    detail = f"Protocol event: {safe_event}. Parsed action count: {int(action_count)}."
    if validation_reason:
        detail += " The parsed command content was unsafe."
    return RECOVERY_PROMPT + "\n" + detail


def validate_action_content(command: str) -> ActionValidation:
    """Reject placeholders and unsafe protocol content, not general shell syntax."""
    normalized = command.strip()
    if not normalized:
        return ActionValidation(False, normalized, "empty or whitespace-only command")
    if normalized.casefold() in _EXACT_PLACEHOLDERS:
        return ActionValidation(False, normalized, "exact placeholder command")
    if _GENERIC_ANGLE_PLACEHOLDER.fullmatch(normalized):
        return ActionValidation(False, normalized, "generic angle-bracket placeholder")
    if _UNRESOLVED_TEMPLATE.search(normalized):
        return ActionValidation(False, normalized, "unresolved template marker")
    for character in normalized:
        codepoint = ord(character)
        if character == "\x00":
            return ActionValidation(False, normalized, "null byte")
        if (codepoint < 32 and character not in {"\n", "\t"}) or 127 <= codepoint <= 159:
            return ActionValidation(False, normalized, "prohibited control character")
    return ActionValidation(True, normalized)


def evaluate_action_response(
    raw_response: str,
    state: ProtocolErrorState,
    *,
    action_regex: str = ACTION_REGEX,
) -> ProtocolEvaluation:
    actions = extract_action_blocks(raw_response, action_regex)
    if len(actions) != 1:
        decision = state.record_invalid(raw_response)
        return ProtocolEvaluation(
            accepted=False,
            raw_response=raw_response,
            action_count=len(actions),
            command=None,
            rejected_command=None,
            event="INVALID_ACTION_FORMAT",
            validation_reason="expected exactly one action block",
            termination_reason=decision.termination_reason,
        )

    validation = validate_action_content(actions[0])
    if not validation.valid:
        decision = state.record_invalid(
            raw_response,
            rejected_command=validation.command,
        )
        return ProtocolEvaluation(
            accepted=False,
            raw_response=raw_response,
            action_count=1,
            command=None,
            rejected_command=validation.command,
            event="INVALID_ACTION_CONTENT",
            validation_reason=validation.reason,
            termination_reason=decision.termination_reason,
        )

    return ProtocolEvaluation(
        accepted=True,
        raw_response=raw_response,
        action_count=1,
        command=validation.command,
        rejected_command=None,
        event=None,
        validation_reason=None,
        termination_reason=None,
    )


def normalize_command(command: str) -> str:
    return "\n".join(line.rstrip() for line in command.replace("\r\n", "\n").split("\n")).strip()


def normalize_observation(observation: str) -> str:
    return "\n".join(
        line.rstrip() for line in observation.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    ).strip()


def repository_hash(root: Path) -> str:
    """Hash stable repository content while excluding transient test and Git data."""
    digest = hashlib.sha256()
    paths = sorted(
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in _EXCLUDED_REPOSITORY_PARTS for part in path.relative_to(root).parts)
        and path.suffix != ".pyc"
    )
    for path in paths:
        relative = path.relative_to(root).as_posix().encode("utf-8")
        contents = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(contents).to_bytes(8, "big"))
        digest.update(contents)
    return digest.hexdigest()


@dataclass(frozen=True)
class TransitionFingerprint:
    normalized_command: str
    repository_before: str
    repository_after: str
    returncode: int | None
    observation_sha256: str

    @property
    def repository_unchanged(self) -> bool:
        return self.repository_before == self.repository_after

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TransitionDecision:
    fingerprint: TransitionFingerprint
    termination_reason: str | None


class StagnationGuard:
    def __init__(self) -> None:
        self._previous: TransitionFingerprint | None = None
        self.transitions: list[TransitionFingerprint] = []

    def record(
        self,
        *,
        command: str,
        repository_before: str,
        repository_after: str,
        returncode: int | None,
        observation: str,
    ) -> TransitionDecision:
        fingerprint = TransitionFingerprint(
            normalized_command=normalize_command(command),
            repository_before=repository_before,
            repository_after=repository_after,
            returncode=returncode,
            observation_sha256=hashlib.sha256(
                normalize_observation(observation).encode("utf-8")
            ).hexdigest(),
        )
        stagnant_repeat = (
            fingerprint.normalized_command != COMPLETION_SENTINEL
            and fingerprint.repository_unchanged
            and self._previous is not None
            and self._previous.repository_unchanged
            and fingerprint == self._previous
        )
        self.transitions.append(fingerprint)
        self._previous = fingerprint
        return TransitionDecision(
            fingerprint=fingerprint,
            termination_reason="STAGNATION_LIMIT" if stagnant_repeat else None,
        )


def escape_action_syntax_for_prompt(content: str) -> str:
    """Keep command output visible without letting it become a new parser match."""
    return content.replace(ACTION_FENCE_OPEN, "``` mswea_bash_command")


def protocol_result_dimensions(
    *,
    termination_reason: str,
    invalid_response_count: int,
    invalid_action_count: int,
    executed_action_count: int,
    repository_progress: bool,
    functional_outcome: str,
) -> dict[str, Any]:
    protocol_reasons = {
        "FORMAT_ERROR_LIMIT",
        "INVALID_ACTION_LIMIT",
        "REPEATED_INVALID_RESPONSE",
        "REPEATED_INVALID_ACTION",
        "STAGNATION_LIMIT",
    }
    semantic_reasons = {
        "INVALID_ACTION_LIMIT",
        "REPEATED_INVALID_ACTION",
    }
    return {
        "technical_validity": "PASS",
        "protocol_safety_status": "PASS",
        "model_format_status": "FAIL" if termination_reason in protocol_reasons else "PASS",
        "termination_reason": termination_reason,
        "invalid_response_count": invalid_response_count,
        "invalid_action_count": invalid_action_count,
        "executed_action_count": executed_action_count,
        "repository_progress": repository_progress,
        "functional_outcome": functional_outcome,
        "failure_dimension": (
            "semantic_invalid_action"
            if termination_reason in semantic_reasons
            else "format_or_stagnation"
            if termination_reason in protocol_reasons
            else "model_task"
        ),
    }


def prompt_match_report(prompts: dict[str, str]) -> dict[str, int]:
    return {
        name: production_parser_match_count(content)
        for name, content in sorted(prompts.items())
    }
