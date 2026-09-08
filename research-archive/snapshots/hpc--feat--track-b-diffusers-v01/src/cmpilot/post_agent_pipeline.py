"""Non-aborting post-agent analysis and dimensional classification."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from pathlib import Path
from typing import Any, Callable

from .task_file_policy import TaskFilePolicy


MANDATORY_POST_AGENT_STAGES = (
    "analysis",
    "final_validation",
    "integrity",
    "shutdown",
    "preservation",
)


@dataclass(frozen=True)
class RepositoryAnalysisFinding:
    """Structured analyzer output; it deliberately has no process exit code."""

    technical_validity: str
    protected_path_violation: bool
    protected_paths_modified: tuple[str, ...]
    disallowed_paths_modified: tuple[str, ...]
    allowed_paths_modified: tuple[str, ...]
    prohibited_command_executed: bool
    returncode: None = None

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        for key in (
            "protected_paths_modified",
            "disallowed_paths_modified",
            "allowed_paths_modified",
        ):
            value[key] = list(value[key])
        return value


def _file_hashes(root: Path) -> dict[str, str]:
    ignored = {".git", ".pytest_cache", "__pycache__"}
    result: dict[str, str] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or path.is_symlink()
            or any(part in ignored for part in relative.parts)
            or path.suffix == ".pyc"
        ):
            continue
        result[relative.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def analyze_task_repository(
    *,
    source_repository: Path,
    agent_repository: Path,
    task_policy: TaskFilePolicy,
    prohibited_command_executed: bool = False,
) -> RepositoryAnalysisFinding:
    """Record every changed-path dimension without terminating later stages."""
    source = _file_hashes(source_repository.resolve(strict=True))
    agent = _file_hashes(agent_repository.resolve(strict=True))
    changed = sorted(
        path
        for path in set(source) | set(agent)
        if source.get(path) != agent.get(path)
    )
    writable = set(task_policy.writable_paths)
    protected = set(task_policy.readable_protected_paths)
    allowed = tuple(path for path in changed if path in writable)
    protected_modified = tuple(path for path in changed if path in protected)
    disallowed = tuple(path for path in changed if path not in writable)
    invalid = bool(disallowed or prohibited_command_executed)
    return RepositoryAnalysisFinding(
        technical_validity="fail" if invalid else "pass",
        protected_path_violation=bool(protected_modified),
        protected_paths_modified=protected_modified,
        disallowed_paths_modified=disallowed,
        allowed_paths_modified=allowed,
        prohibited_command_executed=prohibited_command_executed,
    )


@dataclass(frozen=True)
class DimensionalClassification:
    model_capability: str
    task_functional_result: str
    technical_validity: str
    protected_path_violation: bool
    protected_paths_modified: tuple[str, ...]
    prohibited_command_executed: bool
    external_oracle_result: str
    allowed_patch_result: str
    post_agent_analysis_complete: bool
    cleanup_complete: bool

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["protected_paths_modified"] = list(self.protected_paths_modified)
        return value


@dataclass(frozen=True)
class StageResult:
    name: str
    status: str
    value: Any
    error_type: str | None
    error_message: str | None

    def as_dict(self) -> dict[str, Any]:
        value = self.value
        if hasattr(value, "as_dict"):
            value = value.as_dict()
        elif isinstance(value, Path):
            value = str(value)
        return {
            "name": self.name,
            "status": self.status,
            "value": value,
            "error_type": self.error_type,
            "error_message": self.error_message,
        }


@dataclass(frozen=True)
class PostAgentOutcome:
    stage_results: dict[str, StageResult]
    post_agent_analysis_complete: bool
    cleanup_complete: bool
    artifact_preservation_complete: bool
    final_process_exit_chosen: bool
    final_exit_code: int

    def as_dict(self) -> dict[str, Any]:
        return {
            "stage_results": {
                name: result.as_dict()
                for name, result in self.stage_results.items()
            },
            "post_agent_analysis_complete": self.post_agent_analysis_complete,
            "cleanup_complete": self.cleanup_complete,
            "artifact_preservation_complete": self.artifact_preservation_complete,
            "final_process_exit_chosen": self.final_process_exit_chosen,
            "final_exit_code": self.final_exit_code,
        }


StageCallback = Callable[[], Any]


class PostAgentPipeline:
    """Run all mandatory stages, then and only then choose one final exit code."""

    def __init__(
        self,
        *,
        analysis: StageCallback | None,
        final_validation: StageCallback | None,
        integrity: StageCallback | None,
        shutdown: StageCallback | None,
        preservation: StageCallback | None,
    ) -> None:
        callbacks = {
            "analysis": analysis,
            "final_validation": final_validation,
            "integrity": integrity,
            "shutdown": shutdown,
            "preservation": preservation,
        }
        missing = [name for name, callback in callbacks.items() if callback is None]
        if missing:
            raise ValueError(f"mandatory post-agent callbacks missing: {missing}")
        self._callbacks: dict[str, StageCallback] = {
            name: callback
            for name, callback in callbacks.items()
            if callback is not None
        }
        self.final_exit_code: int | None = None
        self._running = False

    @staticmethod
    def _stage_indicates_failure(result: StageResult) -> bool:
        if result.status != "passed":
            return True
        value = result.value
        if isinstance(value, RepositoryAnalysisFinding):
            return value.technical_validity != "pass"
        if isinstance(value, dict):
            if value.get("pass") is False or value.get("valid") is False:
                return True
            if value.get("complete") is False:
                return True
            if value.get("technical_validity") == "fail":
                return True
            if value.get("protected_path_violation") is True:
                return True
            failed = value.get("failed")
            if isinstance(failed, int) and failed > 0:
                return True
            returncode = value.get("returncode")
            if isinstance(returncode, int) and returncode != 0:
                return True
        returncode = getattr(value, "returncode", None)
        if isinstance(returncode, int) and returncode != 0:
            return True
        return False

    def run(self) -> PostAgentOutcome:
        if self._running or self.final_exit_code is not None:
            raise RuntimeError("post-agent pipeline may run exactly once")
        self._running = True
        results: dict[str, StageResult] = {}
        try:
            for name in MANDATORY_POST_AGENT_STAGES:
                callback = self._callbacks[name]
                try:
                    value = callback()
                except BaseException as error:
                    results[name] = StageResult(
                        name=name,
                        status="failed",
                        value=None,
                        error_type=type(error).__name__,
                        error_message=str(error),
                    )
                else:
                    results[name] = StageResult(
                        name=name,
                        status="passed",
                        value=value,
                        error_type=None,
                        error_message=None,
                    )
        finally:
            # No stage callback can observe a chosen process status.  Selection
            # occurs only after every callback has returned or raised.
            self.final_exit_code = (
                1
                if any(
                    self._stage_indicates_failure(result)
                    for result in results.values()
                )
                else 0
            )
            self._running = False
        return PostAgentOutcome(
            stage_results=results,
            post_agent_analysis_complete=(
                results.get("analysis") is not None
                and results["analysis"].status == "passed"
            ),
            cleanup_complete=(
                (shutdown_result := results.get("shutdown")) is not None
                and shutdown_result.status == "passed"
                and not (
                    isinstance(shutdown_result.value, dict)
                    and shutdown_result.value.get("complete") is False
                )
            ),
            artifact_preservation_complete=(
                (preservation_result := results.get("preservation")) is not None
                and preservation_result.status == "passed"
                and not (
                    isinstance(preservation_result.value, dict)
                    and preservation_result.value.get("complete") is False
                )
            ),
            final_process_exit_chosen=True,
            final_exit_code=self.final_exit_code,
        )
