"""Candidate-specific scientific runtime for the frozen HTTPX Track B family.

Lifecycle, isolation, evaluator execution, capture, and integrity behavior are
inherited unchanged from the frozen MCP Pinot scientific backend.  This module
only binds those generic operations to HTTPX's immutable package identities.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .final_experiment import FROZEN, NO_MEMORY, PRODUCTION, SOURCE_CORRECT_MEMORY
from .final_model_runtime import write_scientific_agent_binding
from .final_runner import FinalRunRequest, TreatmentApplication
from .mcp_pinot_backend import (
    MCPPinotBackendError,
    MCPPinotScientificOperations,
    _load_canonical_json,
    _mapping,
)
from .qualification import sha256_file
from .repository_manager import repository_content_digest


HTTPX_BACKEND_ID = "httpx-v1"
HTTPX_PACKAGE_SCHEMA = "cmpilot-httpx-family-package-v1"
HTTPX_PACKAGE_ROOT = Path(__file__).parents[2] / "families" / HTTPX_BACKEND_ID
HTTPX_PACKAGE_LOGICAL_PATH = "families/httpx-v1/family-package.json"
HTTPX_SOURCE_REVISION = "e6da325e8be4a7194571adea67053446c75d9aa3"
HTTPX_TARGET_REVISION = "7e6e35160f5c68150f2a9fba7e0dc889efc06510"

_TARGET_REPOSITORY = "repositories/invalidated"
_TASK_FILE = "tasks/target-task.md"
_TASK_POLICY_FILE = "task-policy.json"
_FUNCTIONAL_ORACLE = "oracles/functional/evaluate.py"
_SECURITY_WITNESS = "oracles/security/evaluate.py"
_MEMORY_FILE = "memories/source-correct-memory.md"
_MEMORY_PROVENANCE_FILE = "memories/source-correct-memory-provenance.json"
_MEMORY_WRAPPER_START = "<SOURCE_CORRECT_PROCEDURAL_MEMORY>"
_MEMORY_WRAPPER_END = "</SOURCE_CORRECT_PROCEDURAL_MEMORY>"

HTTPXBackendError = MCPPinotBackendError


class HTTPXScientificOperations(MCPPinotScientificOperations):
    """Bind the frozen generic scientific lifecycle to ``httpx-v1``."""

    def __init__(
        self,
        context: Mapping[str, Any],
        *,
        package_root: Path = HTTPX_PACKAGE_ROOT,
        evaluator_python: Path | None = None,
    ) -> None:
        super().__init__(
            context,
            package_root=package_root,
            evaluator_python=evaluator_python,
        )

    def _validate_production_binding(self) -> None:
        if self.family.get("family_id") != HTTPX_BACKEND_ID:
            raise HTTPXBackendError("HTTPX family ID mismatch")
        task_specification = _mapping(
            self.family.get("task_specification"), "family.task_specification"
        )
        if task_specification.get("runtime_backend_id") != HTTPX_BACKEND_ID:
            raise HTTPXBackendError("HTTPX runtime backend ID mismatch")
        task_environment = _mapping(
            self.family.get("task_environment"), "family.task_environment"
        )
        if task_environment.get("path") != HTTPX_PACKAGE_LOGICAL_PATH:
            raise HTTPXBackendError("HTTPX task environment path mismatch")
        observed_package_sha256 = sha256_file(self.package_path)
        if task_environment.get("sha256") != observed_package_sha256:
            raise HTTPXBackendError("HTTPX task_environment hash mismatch")

        run = _mapping(self._context.get("run"), "context.run")
        if run.get("experiment_purpose") != PRODUCTION:
            raise HTTPXBackendError("HTTPX production builder requires PRODUCTION")
        if run.get("manifest_freeze_status") != FROZEN:
            raise HTTPXBackendError("HTTPX production builder requires FROZEN")
        if run.get("task_environment_sha256") != observed_package_sha256:
            raise HTTPXBackendError("HTTPX run task_environment hash mismatch")
        if self.package.get("schema") != HTTPX_PACKAGE_SCHEMA:
            raise HTTPXBackendError("unsupported HTTPX family package schema")
        if self.package.get("family_id") != HTTPX_BACKEND_ID:
            raise HTTPXBackendError("HTTPX family package ID mismatch")
        if self.package.get("freeze_status") != FROZEN:
            raise HTTPXBackendError("HTTPX production builder refuses non-FROZEN package")
        if self.package.get("model_ready") is not True or self.package.get("blockers") != []:
            raise HTTPXBackendError("frozen HTTPX package must be model-ready and unblocked")
        identities = (
            self.package.get("source_revision") == HTTPX_SOURCE_REVISION,
            self.package.get("target_revision") == HTTPX_TARGET_REVISION,
            self.family.get("source_revision") == HTTPX_SOURCE_REVISION,
            self.family.get("target_revision") == HTTPX_TARGET_REVISION,
            run.get("target_revision") == HTTPX_TARGET_REVISION,
        )
        if not all(identities):
            raise HTTPXBackendError("HTTPX immutable revision binding mismatch")

    def _validate_package_inputs(self) -> None:
        self._validate_all_declared_input_hashes()
        target = self._input("target_repository")
        if target.get("path") != _TARGET_REPOSITORY:
            raise HTTPXBackendError("HTTPX target repository path mismatch")
        target_digest = repository_content_digest(
            self._fixed_directory(_TARGET_REPOSITORY)
        )
        if target.get("sha256") != target_digest.sha256:
            raise HTTPXBackendError("HTTPX target repository digest mismatch")
        task = self._validate_file_record("task", expected_path=_TASK_FILE)
        self._validate_file_record("task_policy", expected_path=_TASK_POLICY_FILE)
        functional = self._validate_file_record(
            "functional_oracle", expected_path=_FUNCTIONAL_ORACLE
        )
        security = self._validate_file_record(
            "security_witness", expected_path=_SECURITY_WITNESS
        )
        for family_name, record in (
            ("task_specification", task),
            ("target_functionality_tests", functional),
            ("security_witness", security),
        ):
            family_record = _mapping(
                self.family.get(family_name), f"family.{family_name}"
            )
            if family_record.get("sha256") != record.get("sha256"):
                raise HTTPXBackendError(f"HTTPX family {family_name} hash mismatch")

        memory = self._input("source_memory")
        required_memory = {
            "path": _MEMORY_FILE,
            "provenance_path": _MEMORY_PROVENANCE_FILE,
            "source_revision": HTTPX_SOURCE_REVISION,
            "status": FROZEN,
        }
        for key, expected in required_memory.items():
            if memory.get(key) != expected:
                raise HTTPXBackendError(f"HTTPX source_memory {key} mismatch")
        for key in ("sha256", "provenance_sha256"):
            value = memory.get(key)
            if not isinstance(value, str) or len(value) != 64:
                raise HTTPXBackendError(f"HTTPX source_memory {key} is invalid")
        if sha256_file(self._fixed_file(_MEMORY_FILE)) != memory["sha256"]:
            raise HTTPXBackendError("HTTPX source memory content hash mismatch")
        if sha256_file(self._fixed_file(_MEMORY_PROVENANCE_FILE)) != memory[
            "provenance_sha256"
        ]:
            raise HTTPXBackendError("HTTPX source memory provenance hash mismatch")

    def _memory_treatment(
        self, request: FinalRunRequest
    ) -> tuple[str, dict[str, Any] | None]:
        treatment = _mapping(self._context.get("treatment"), "context.treatment")
        context_memory = treatment.get("memory")
        if request.condition == NO_MEMORY:
            if context_memory is not None:
                raise HTTPXBackendError("NO_MEMORY context unexpectedly contains memory")
            if request.run.get("memory_content_sha256") is not None or request.run.get(
                "memory_provenance_manifest_sha256"
            ) is not None:
                raise HTTPXBackendError("NO_MEMORY run unexpectedly binds memory")
            return "", None
        if request.condition != SOURCE_CORRECT_MEMORY:
            raise HTTPXBackendError(f"unsupported HTTPX condition: {request.condition}")
        memory_record = _mapping(context_memory, "context.treatment.memory")
        package_memory = self._input("source_memory")
        content_path = self._fixed_file(_MEMORY_FILE)
        provenance_path = self._fixed_file(_MEMORY_PROVENANCE_FILE)
        content_sha256 = sha256_file(content_path)
        provenance_sha256 = sha256_file(provenance_path)
        if content_sha256 != package_memory.get("sha256"):
            raise HTTPXBackendError("HTTPX source memory bytes changed")
        if provenance_sha256 != package_memory.get("provenance_sha256"):
            raise HTTPXBackendError("HTTPX source memory provenance changed")
        if memory_record.get("content_sha256") != content_sha256:
            raise HTTPXBackendError("HTTPX context memory content hash differs")
        if memory_record.get("provenance_manifest_sha256") != provenance_sha256:
            raise HTTPXBackendError("HTTPX context memory provenance hash differs")
        if memory_record.get("source_repository_revision") != HTTPX_SOURCE_REVISION:
            raise HTTPXBackendError("HTTPX context memory revision differs")
        provenance = _load_canonical_json(provenance_path)
        source = provenance.get("source_repository")
        if not isinstance(source, Mapping) or source.get("revision") != HTTPX_SOURCE_REVISION:
            raise HTTPXBackendError("HTTPX memory provenance revision differs")
        memory_text = content_path.read_text(encoding="utf-8")
        if not memory_text.strip():
            raise HTTPXBackendError("HTTPX source memory is empty")
        rendered = (
            f"\n\n{_MEMORY_WRAPPER_START}\n{memory_text.rstrip()}\n"
            f"{_MEMORY_WRAPPER_END}\n"
        )
        return rendered, {
            "content_sha256": content_sha256,
            "provenance_manifest_sha256": provenance_sha256,
            "source_revision": HTTPX_SOURCE_REVISION,
        }

    def apply_treatment(
        self, request: FinalRunRequest, repository: Path
    ) -> TreatmentApplication:
        state = self._require_state(request, repository)
        self._assert_package_unchanged()
        task_sha256 = sha256_file(self.task_path)
        if task_sha256 != self._input("task").get("sha256"):
            raise HTTPXBackendError("HTTPX target task bytes changed")
        task_text = self.task_path.read_text(encoding="utf-8")
        if not task_text.strip():
            raise HTTPXBackendError("HTTPX target task is empty")
        memory_block, memory_record = self._memory_treatment(request)
        rendered = task_text.rstrip() + (memory_block or "\n")
        binding_sha256 = write_scientific_agent_binding(
            attempt_directory=request.attempt_directory,
            run_id=request.run_id,
            repository=repository,
            rendered_task=rendered,
            task_policy_source=self.task_policy_path,
            expected_task_policy_sha256=str(self._input("task_policy")["sha256"]),
        )
        state.binding_sha256 = binding_sha256
        return TreatmentApplication(
            rendered_task=rendered,
            provenance={
                "binding_sha256": binding_sha256,
                "condition": request.condition,
                "family_id": HTTPX_BACKEND_ID,
                "memory": memory_record,
                "task_sha256": task_sha256,
            },
        )


def build_httpx_backend(
    context: Mapping[str, Any],
    *,
    package_root: Path = HTTPX_PACKAGE_ROOT,
    evaluator_python: Path | None = None,
) -> HTTPXScientificOperations:
    """Build only the exact frozen production HTTPX backend."""

    return HTTPXScientificOperations(
        context,
        package_root=package_root,
        evaluator_python=evaluator_python,
    )


__all__ = [
    "HTTPX_BACKEND_ID",
    "HTTPX_PACKAGE_LOGICAL_PATH",
    "HTTPX_PACKAGE_ROOT",
    "HTTPX_PACKAGE_SCHEMA",
    "HTTPX_SOURCE_REVISION",
    "HTTPX_TARGET_REVISION",
    "HTTPXBackendError",
    "HTTPXScientificOperations",
    "build_httpx_backend",
]
