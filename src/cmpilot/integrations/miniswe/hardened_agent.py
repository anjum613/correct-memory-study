"""Project-owned mini-SWE agent interception before environment execution."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any, Callable

from minisweagent.agents.default import DefaultAgent
from minisweagent.exceptions import FormatError, InterruptAgentFlow

try:
    from .action_protocol import (
        ProtocolErrorState,
        ProtocolEvaluation,
        StagnationGuard,
        evaluate_action_response,
        protocol_result_dimensions,
        render_recovery_prompt,
        repository_hash,
    )
except ImportError:
    from cmpilot_action_protocol import (  # type: ignore[no-redef]
        ProtocolErrorState,
        ProtocolEvaluation,
        StagnationGuard,
        evaluate_action_response,
        protocol_result_dimensions,
        render_recovery_prompt,
        repository_hash,
    )


EventSink = Callable[..., None]


class ProtocolRejected(Exception):
    def __init__(self, evaluation: ProtocolEvaluation):
        super().__init__(evaluation.event or "action rejected")
        self.evaluation = evaluation


class HardenedDefaultAgent(DefaultAgent):
    """DefaultAgent with semantic validation and state-aware protocol guards."""

    def __init__(
        self,
        model: Any,
        env: Any,
        *,
        repository: Path,
        event_sink: EventSink | None = None,
        **kwargs: Any,
    ):
        super().__init__(model, env, **kwargs)
        self.repository = repository.resolve()
        self.event_sink = event_sink
        self.protocol_state = ProtocolErrorState(
            maximum_consecutive_errors=self.config.max_consecutive_format_errors or 3
        )
        self.stagnation_guard = StagnationGuard()
        self.executed_action_count = 0
        self.repository_progress = False
        self.termination_reason = ""

    def _emit(self, event: str, **details: Any) -> None:
        if self.event_sink is not None:
            self.event_sink(event, **details)

    def _exit_message(self, reason: str, **details: Any) -> dict[str, Any]:
        self.termination_reason = reason
        self._emit("protocol_terminated", termination_reason=reason, **details)
        return self.model.format_message(
            role="exit",
            content=reason,
            extra={
                "exit_status": reason,
                "submission": "",
                "protocol_termination": True,
                **details,
            },
        )

    @staticmethod
    def _raw_digest(raw_response: str) -> str:
        return hashlib.sha256(raw_response.encode("utf-8")).hexdigest()

    def _recovery_message(self, evaluation: ProtocolEvaluation) -> dict[str, Any]:
        content = render_recovery_prompt(
            event=evaluation.event or "INVALID_ACTION",
            action_count=evaluation.action_count,
            validation_reason=evaluation.validation_reason,
        )
        return self.model.format_message(
            role="user",
            content=content,
            extra={
                "interrupt_type": evaluation.event,
                "protocol_recovery": True,
                "action_count": evaluation.action_count,
                "validation_reason": evaluation.validation_reason,
                "rejected_command": evaluation.rejected_command,
                "termination_reason": evaluation.termination_reason,
            },
        )

    def _record_format_error(self, error: FormatError) -> None:
        source = error.messages[0] if error.messages else {}
        source_extra = source.get("extra", {}) if isinstance(source, dict) else {}
        if not isinstance(source_extra, dict):
            source_extra = {}
        raw_response = source_extra.get("model_response", "")
        if not isinstance(raw_response, str):
            raw_response = str(raw_response)
        action_count = source_extra.get("n_actions", 0)
        if not isinstance(action_count, int):
            action_count = 0
        self.cost += source_extra.get("cost", 0.0)

        decision = self.protocol_state.record_invalid(raw_response)
        evaluation = ProtocolEvaluation(
            accepted=False,
            raw_response=raw_response,
            action_count=action_count,
            command=None,
            rejected_command=None,
            event="INVALID_ACTION_FORMAT",
            validation_reason="expected exactly one action block",
            termination_reason=decision.termination_reason,
        )
        preserved = {
            key: source_extra[key]
            for key in ("cost", "raw_response", "response", "transport", "usage")
            if key in source_extra
        }
        assistant = self.model.format_message(
            role="assistant",
            content=raw_response,
            extra={
                **preserved,
                "protocol_event": "INVALID_ACTION_FORMAT",
                "protocol_rejected": True,
                "action_count": action_count,
                "raw_model_response": raw_response,
                "raw_response_sha256": self._raw_digest(raw_response),
            },
        )
        self._emit(
            "INVALID_ACTION_FORMAT",
            action_count=action_count,
            consecutive_protocol_errors=self.protocol_state.consecutive_protocol_errors,
            raw_response_sha256=self._raw_digest(raw_response),
            termination_reason=decision.termination_reason,
        )
        messages = [assistant, self._recovery_message(evaluation)]
        if decision.termination_reason:
            messages.append(
                self._exit_message(
                    decision.termination_reason,
                    action_count=action_count,
                    raw_response_sha256=self._raw_digest(raw_response),
                )
            )
        self.add_messages(*messages)

    def _record_semantic_rejection(self, evaluation: ProtocolEvaluation) -> None:
        last_message = self.messages[-1]
        extra = last_message.setdefault("extra", {})
        if not isinstance(extra, dict):
            extra = {}
            last_message["extra"] = extra
        extra.update(
            {
                "protocol_event": "INVALID_ACTION_CONTENT",
                "protocol_rejected": True,
                "rejected_command": evaluation.rejected_command,
                "validation_reason": evaluation.validation_reason,
                "raw_model_response": evaluation.raw_response,
                "raw_response_sha256": self._raw_digest(evaluation.raw_response),
            }
        )
        self._emit(
            "INVALID_ACTION_CONTENT",
            rejected_command=evaluation.rejected_command,
            validation_reason=evaluation.validation_reason,
            consecutive_protocol_errors=self.protocol_state.consecutive_protocol_errors,
            raw_response_sha256=self._raw_digest(evaluation.raw_response),
            termination_reason=evaluation.termination_reason,
        )
        messages = [self._recovery_message(evaluation)]
        if evaluation.termination_reason:
            messages.append(
                self._exit_message(
                    evaluation.termination_reason,
                    rejected_command=evaluation.rejected_command,
                    raw_response_sha256=self._raw_digest(evaluation.raw_response),
                )
            )
        self.add_messages(*messages)

    def run(self, task: str = "", **kwargs: Any) -> dict[str, Any]:
        self.extra_template_vars |= {"task": task, **kwargs}
        self.messages = []
        self.add_messages(
            self.model.format_message(
                role="system",
                content=self._render_template(self.config.system_template),
            ),
            self.model.format_message(
                role="user",
                content=self._render_template(self.config.instance_template),
            ),
        )
        while True:
            try:
                self.step()
            except FormatError as error:
                self._record_format_error(error)
            except ProtocolRejected as error:
                self._record_semantic_rejection(error.evaluation)
            except InterruptAgentFlow as error:
                self.add_messages(*error.messages)
            except Exception as error:
                self.handle_uncaught_exception(error)
                raise
            finally:
                self.save(self.config.output_path)
            if self.messages[-1].get("role") == "exit":
                extra = self.messages[-1].get("extra", {})
                if isinstance(extra, dict):
                    self.termination_reason = str(extra.get("exit_status", ""))
                break
        return self.messages[-1].get("extra", {})

    def execute_actions(self, message: dict[str, Any]) -> list[dict[str, Any]]:
        raw_response = message.get("content", "")
        if not isinstance(raw_response, str):
            raise TypeError("assistant content must be text")
        evaluation = evaluate_action_response(raw_response, self.protocol_state)
        if not evaluation.accepted:
            raise ProtocolRejected(evaluation)

        actions = message.get("extra", {}).get("actions", [])
        if (
            not isinstance(actions, list)
            or len(actions) != 1
            or not isinstance(actions[0], dict)
            or actions[0].get("command") != evaluation.command
        ):
            raise RuntimeError("production parser and semantic validator action mismatch")

        command = evaluation.command or ""
        before = repository_hash(self.repository)
        try:
            output = self.env.execute(actions[0])
        except InterruptAgentFlow:
            self.protocol_state.record_valid_action()
            self.executed_action_count += 1
            self._emit(
                "action_executed",
                command=command,
                completion_sentinel=True,
                repository_before=before,
            )
            raise

        self.protocol_state.record_valid_action()
        self.executed_action_count += 1
        after = repository_hash(self.repository)
        self.repository_progress = self.repository_progress or before != after
        observation = output.get("output", "") if isinstance(output, dict) else ""
        if not isinstance(observation, str):
            observation = str(observation)
        returncode = output.get("returncode") if isinstance(output, dict) else None
        transition = self.stagnation_guard.record(
            command=command,
            repository_before=before,
            repository_after=after,
            returncode=returncode,
            observation=observation,
        )
        self._emit(
            "action_executed",
            command=command,
            completion_sentinel=False,
            transition=transition.fingerprint.as_dict(),
            termination_reason=transition.termination_reason,
        )
        observation_messages = self.model.format_observation_messages(
            message,
            [output],
            self.get_template_vars(),
        )
        added = self.add_messages(*observation_messages)
        if transition.termination_reason:
            added.extend(
                self.add_messages(
                    self._exit_message(
                        transition.termination_reason,
                        transition=transition.fingerprint.as_dict(),
                    )
                )
            )
        return added

    def protocol_result(self) -> dict[str, Any]:
        reason = self.termination_reason
        dimensions = protocol_result_dimensions(
            termination_reason=reason,
            invalid_response_count=self.protocol_state.invalid_response_count,
            invalid_action_count=self.protocol_state.invalid_action_count,
            executed_action_count=self.executed_action_count,
            repository_progress=self.repository_progress,
            functional_outcome="SUBMITTED" if reason == "Submitted" else "INCOMPLETE",
        )
        return {
            **dimensions,
            **self.protocol_state.as_dict(),
            "transitions": [
                fingerprint.as_dict()
                for fingerprint in self.stagnation_guard.transitions
            ],
        }

    def serialize(self, *extra_dicts: dict[str, Any]) -> dict[str, Any]:
        protocol = self.protocol_result()
        return super().serialize(
            {"info": {"protocol": protocol}, "protocol": protocol},
            *extra_dicts,
        )
