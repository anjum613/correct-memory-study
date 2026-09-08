"""Treatment-blind V2 initial prompt construction and census inputs."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any

from .integrations.miniswe.action_protocol import INITIAL_SYSTEM_TEMPLATE, INSTANCE_TEMPLATE
from .task_file_policy import CALCULATOR_AGENT_POLICY_TEXT


NO_MEMORY = "NO_MEMORY"
SOURCE_CORRECT_MEMORY = "SOURCE_CORRECT_MEMORY"
MEMORY_WRAPPER_START = "<ADDITIONAL_TASK_CONTEXT>"
MEMORY_WRAPPER_END = "</ADDITIONAL_TASK_CONTEXT>"


class V2PromptError(ValueError):
    """Frozen family prompt inputs or a requested condition are invalid."""


@dataclass(frozen=True)
class InitialPrompt:
    family: str
    condition: str
    messages: tuple[dict[str, str], ...]
    task_text: str
    memory_text: str | None
    rendered_task: str
    task_policy_text: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "condition": self.condition,
            "messages": list(self.messages),
            "task_sha256": hashlib.sha256(self.task_text.encode()).hexdigest(),
            "memory_sha256": None if self.memory_text is None else hashlib.sha256(self.memory_text.encode()).hexdigest(),
            "rendered_task_sha256": hashlib.sha256(self.rendered_task.encode()).hexdigest(),
        }


def _load_object(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise V2PromptError(f"expected JSON object: {path}")
    return value


def render_v2_task(task_text: str, memory_text: str | None) -> str:
    """Render a neutral wrapper only when memory is actually available."""

    task = task_text.rstrip()
    if not task:
        raise V2PromptError("task text is empty")
    if memory_text is None:
        return task + "\n"
    memory = memory_text.rstrip()
    if not memory:
        raise V2PromptError("memory text is empty")
    return (
        task
        + "\n\n"
        + MEMORY_WRAPPER_START
        + "\n"
        + memory
        + "\n"
        + MEMORY_WRAPPER_END
        + "\n"
    )


def build_initial_prompt(family_root: Path, condition: str) -> InitialPrompt:
    root = Path(family_root)
    package = _load_object(root / "family-package.json")
    inputs = package.get("inputs")
    if not isinstance(inputs, dict):
        raise V2PromptError("family package inputs are missing")
    task_record = inputs.get("task")
    memory_record = inputs.get("source_memory")
    if not isinstance(task_record, dict) or not isinstance(memory_record, dict):
        raise V2PromptError("family task or source-memory record is missing")
    task_path = root / str(task_record["path"])
    memory_path = root / str(memory_record["path"])
    policy = _load_object(root / "task-policy.json")
    policy_text = policy.get("agent_visible_policy_text")
    if not isinstance(policy_text, str) or not policy_text.strip():
        raise V2PromptError("task policy has no agent-visible text")
    task_text = task_path.read_text(encoding="utf-8")
    if condition == NO_MEMORY:
        memory_text = None
    elif condition == SOURCE_CORRECT_MEMORY:
        memory_text = memory_path.read_text(encoding="utf-8")
    else:
        raise V2PromptError(f"unsupported V2 condition: {condition}")
    rendered_task = render_v2_task(task_text, memory_text)
    if INITIAL_SYSTEM_TEMPLATE.count(CALCULATOR_AGENT_POLICY_TEXT) != 1:
        raise V2PromptError("system prompt policy anchor is not unique")
    system = INITIAL_SYSTEM_TEMPLATE.replace(CALCULATOR_AGENT_POLICY_TEXT, policy_text, 1)
    user = INSTANCE_TEMPLATE.replace("{{task}}", rendered_task)
    return InitialPrompt(
        family=str(package.get("family_id")),
        condition=condition,
        messages=(
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ),
        task_text=task_text,
        memory_text=memory_text,
        rendered_task=rendered_task,
        task_policy_text=policy_text,
    )


def wrapper_leakage_findings() -> list[str]:
    combined = (MEMORY_WRAPPER_START + MEMORY_WRAPPER_END).casefold()
    forbidden = ("security", "trust", "histor", "source", "correct", "reuse", "evaluat")
    return [term for term in forbidden if term in combined]
