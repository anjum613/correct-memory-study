"""Task-policy shim that executes the frozen job-25887 adapter unchanged."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import runpy

import cmpilot_action_protocol
import cmpilot_task_file_policy


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


policy_path = Path(os.environ["CMPILOT_TASK_POLICY_SOURCE"]).resolve(strict=True)
expected_policy_sha256 = os.environ["CMPILOT_TASK_POLICY_SHA256"]
if _sha256(policy_path) != expected_policy_sha256:
    raise RuntimeError("qualification task policy hash mismatch")
value = json.loads(policy_path.read_text(encoding="utf-8"))
if value.get("schema") != cmpilot_task_file_policy.TASK_POLICY_SCHEMA:
    raise RuntimeError("qualification task policy schema mismatch")

sequence_fields = (
    "writable_paths",
    "readable_protected_paths",
    "hidden_external_oracle_paths",
    "inaccessible_harness_paths",
)
for field in sequence_fields:
    if not isinstance(value.get(field), list) or not all(
        isinstance(item, str) for item in value[field]
    ):
        raise RuntimeError(f"qualification task policy field is invalid: {field}")
policy = cmpilot_task_file_policy.TaskFilePolicy(
    version=value["version"],
    writable_paths=tuple(value["writable_paths"]),
    readable_protected_paths=tuple(value["readable_protected_paths"]),
    hidden_external_oracle_paths=tuple(value["hidden_external_oracle_paths"]),
    inaccessible_harness_paths=tuple(value["inaccessible_harness_paths"]),
    agent_visible_policy_text=value["agent_visible_policy_text"],
)


def _qualification_policy():
    return policy


cmpilot_task_file_policy.calculator_task_policy = _qualification_policy
anchor = cmpilot_task_file_policy.CALCULATOR_AGENT_POLICY_TEXT
for template_name in ("INITIAL_SYSTEM_TEMPLATE", "NATIVE_TOOL_SYSTEM_TEMPLATE"):
    template = getattr(cmpilot_action_protocol, template_name)
    if template.count(anchor) != 1:
        raise RuntimeError(
            f"system prompt task-policy anchor mismatch: {template_name}"
        )
    setattr(
        cmpilot_action_protocol,
        template_name,
        template.replace(
            anchor, policy.agent_visible_policy_text, 1
        ),
    )

frozen_adapter = Path(__file__).with_name("cmpilot_frozen_adapter_runtime.py")
expected_adapter_sha256 = os.environ["CMPILOT_FROZEN_ADAPTER_SHA256"]
if _sha256(frozen_adapter) != expected_adapter_sha256:
    raise RuntimeError("frozen job-25887 adapter hash mismatch")
runpy.run_path(str(frozen_adapter), run_name="__main__")
