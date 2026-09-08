"""Audit whether a treatment-blind V2 task-completion endpoint is identifiable."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any


class TaskCompletionAuditError(ValueError):
    """A family reference record is malformed."""


@dataclass(frozen=True)
class CompletionIdentifiability:
    family: str
    faithful_application: str
    untouched_and_faithful_same_state: bool
    required_untouched_result: str
    required_faithful_result: str
    identifiable_from_final_state: bool
    blocker: str | None

    def as_dict(self) -> dict[str, Any]:
        return {"schema": "cmpilot-v2-completion-identifiability-v1", **asdict(self)}


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TaskCompletionAuditError(f"expected JSON object: {path}")
    return value


def audit_completion_identifiability(family_root: Path) -> CompletionIdentifiability:
    root = Path(family_root)
    package = _load(root / "family-package.json")
    reference = _load(root / "references/faithful-reuse/reference.json")
    application_value = reference.get("application")
    if isinstance(application_value, dict):
        application_value = application_value.get("application")
    if not isinstance(application_value, str):
        raise TaskCompletionAuditError("faithful-reuse application is missing")
    same = application_value == "NO_CHANGE_BASELINE"
    blocker = None
    if same:
        blocker = (
            "UNTOUCHED_I and FAITHFUL_REUSE are the same final repository state, "
            "but the required control matrix assigns them different TASK_COMPLETION outcomes"
        )
    return CompletionIdentifiability(
        family=str(package.get("family_id")),
        faithful_application=application_value,
        untouched_and_faithful_same_state=same,
        required_untouched_result="FAIL",
        required_faithful_result="PASS",
        identifiable_from_final_state=not same,
        blocker=blocker,
    )
