"""Frozen, treatment-blind no-memory qualification task support."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
from typing import Any, Mapping, Sequence

from .integrations.miniswe.action_protocol import (
    CALCULATOR_AGENT_POLICY_TEXT,
    INITIAL_SYSTEM_TEMPLATE,
    INSTANCE_TEMPLATE,
    prompt_match_report,
)
from .repository_manager import copy_repository_tree, repository_content_digest
from .task_file_policy import TASK_POLICY_SCHEMA, TaskFilePolicy


QUALIFICATION_VERSION = "qwen32b-no-memory-qualification-v1"
TASK_MANIFEST_SCHEMA = "qwen32b-qualification-task-v1"
SUITE_MANIFEST_SCHEMA = "qwen32b-qualification-suite-v1"
ORACLE_VERSION = "qwen32b-qualification-oracle-v1"
ORACLE_MANIFEST_SCHEMA = "qwen32b-qualification-oracle-manifest-v1"
FROZEN_HARNESS_COMMIT = "ba039a0eaddc358d6b7174260c3b3c36169c44c0"
FROZEN_TAG = "qwen32b-qualification-v1"
MODEL_ID = "Qwen/Qwen2.5-Coder-32B-Instruct"
MODEL_REVISION = "381fc969f78efac66bc87ff7ddeadb7e73c218a7"
MODEL_SNAPSHOT = Path(
    "/home/s224049759/model-cache/huggingface/hub/"
    "models--Qwen--Qwen2.5-Coder-32B-Instruct/snapshots/"
    + MODEL_REVISION
)
CMPILOT_PYTHON = Path("/home/s224049759/environments/cmpilot-conda/bin/python")
MINI_SWE_PYTHON = Path(
    "/home/s224049759/environments/mini-swe-agent-smoke/bin/python"
)
VLLM_PYTHON = Path("/home/s224049759/environments/vllm-smoke/bin/python")
SHARED_ARTIFACT_ROOT = Path(
    "/home/s224049759/run-artifacts/qwen32b-no-memory-qualification/v1"
)
DETERMINISTIC_GIT_DATE = "2000-01-01T00:00:00+00:00"

_IGNORED_PARTS = frozenset({".git", ".pytest_cache", "__pycache__"})
_UNRESOLVED = re.compile(r"{{.*?}}|{%.*?%}|\b(?:TODO|TBD|FIXME)\b", re.DOTALL)


class QualificationError(RuntimeError):
    """A frozen qualification input or validation invariant failed."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")


def write_canonical_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(value)
    path.write_bytes(payload)
    if canonical_json_bytes(json.loads(path.read_text(encoding="utf-8"))) != payload:
        raise QualificationError(f"canonical JSON round trip changed {path}")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise QualificationError(f"expected a JSON object: {path}")
    return value


def load_task_policy(path: Path) -> TaskFilePolicy:
    value = load_json(path)
    if value.get("schema") != TASK_POLICY_SCHEMA:
        raise QualificationError(f"unsupported task policy schema: {path}")
    required = {
        "version",
        "writable_paths",
        "readable_protected_paths",
        "hidden_external_oracle_paths",
        "inaccessible_harness_paths",
        "agent_visible_policy_text",
    }
    missing = sorted(required - set(value))
    if missing:
        raise QualificationError(f"task policy fields missing from {path}: {missing}")
    sequences: dict[str, tuple[str, ...]] = {}
    for name in (
        "writable_paths",
        "readable_protected_paths",
        "hidden_external_oracle_paths",
        "inaccessible_harness_paths",
    ):
        raw = value[name]
        if not isinstance(raw, list) or not all(isinstance(item, str) for item in raw):
            raise QualificationError(f"task policy {name} is not a string list")
        sequences[name] = tuple(raw)
    return TaskFilePolicy(
        version=str(value["version"]),
        writable_paths=sequences["writable_paths"],
        readable_protected_paths=sequences["readable_protected_paths"],
        hidden_external_oracle_paths=sequences["hidden_external_oracle_paths"],
        inaccessible_harness_paths=sequences["inaccessible_harness_paths"],
        agent_visible_policy_text=str(value["agent_visible_policy_text"]),
    )


def prepare_qualification_working_copy(
    template: Path,
    *,
    destination: Path,
    task_policy: TaskFilePolicy,
) -> tuple[Path, str]:
    """Prepare a byte-identical fixture with deterministic initial Git metadata."""
    from .repository_manager import prepare_working_copy

    variable_names = ("GIT_AUTHOR_DATE", "GIT_COMMITTER_DATE")
    previous = {name: os.environ.get(name) for name in variable_names}
    try:
        for name in variable_names:
            os.environ[name] = DETERMINISTIC_GIT_DATE
        return prepare_working_copy(
            template,
            destination=destination,
            task_policy=task_policy,
        )
    finally:
        for name, value in previous.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


def render_task_prompts(task_text: str, policy: TaskFilePolicy) -> dict[str, Any]:
    if CALCULATOR_AGENT_POLICY_TEXT not in INITIAL_SYSTEM_TEMPLATE:
        raise QualificationError("frozen system prompt policy anchor is missing")
    system = INITIAL_SYSTEM_TEMPLATE.replace(
        CALCULATOR_AGENT_POLICY_TEXT, policy.agent_visible_policy_text, 1
    )
    instance = INSTANCE_TEMPLATE.replace("{{task}}", task_text)
    prompts = {"system": system, "task": instance}
    matches = prompt_match_report(prompts)
    unresolved = {
        name: bool(_UNRESOLVED.search(text)) for name, text in prompts.items()
    }
    if matches != {"system": 1, "task": 0}:
        raise QualificationError(f"unsafe canonical prompt parser matches: {matches}")
    if any(unresolved.values()):
        raise QualificationError(f"canonical prompt has unresolved text: {unresolved}")
    return {
        "parser_match_counts": matches,
        "prompts": prompts,
        "sha256": {
            name: sha256_bytes(text.encode("utf-8"))
            for name, text in sorted(prompts.items())
        },
        "unresolved": unresolved,
    }


def create_oracle_manifest(bundle: Path) -> dict[str, Any]:
    files = {}
    for name in ("oracle.json", "test_oracle.py"):
        path = bundle / name
        if not path.is_file() or path.is_symlink():
            raise QualificationError(f"oracle input is missing or unsafe: {path}")
        files[name] = sha256_file(path)
    configuration = load_json(bundle / "oracle.json")
    if configuration.get("oracle_version") != ORACLE_VERSION:
        raise QualificationError(f"unexpected oracle version: {bundle}")
    if configuration.get("test_file") != "test_oracle.py":
        raise QualificationError(f"unexpected oracle test file: {bundle}")
    return {
        "files": files,
        "oracle_version": ORACLE_VERSION,
        "schema": ORACLE_MANIFEST_SCHEMA,
    }


def validate_oracle_bundle(
    bundle: Path, *, expected_manifest_sha256: str | None = None
) -> dict[str, Any]:
    bundle = bundle.resolve(strict=True)
    if not bundle.is_dir() or bundle.is_symlink():
        raise QualificationError(f"oracle bundle is not a real directory: {bundle}")
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise QualificationError(f"oracle manifest is missing: {bundle}")
    manifest_sha256 = sha256_file(manifest_path)
    if expected_manifest_sha256 and manifest_sha256 != expected_manifest_sha256:
        raise QualificationError(
            f"oracle manifest hash mismatch: expected {expected_manifest_sha256}, "
            f"observed {manifest_sha256}"
        )
    manifest = load_json(manifest_path)
    expected = create_oracle_manifest(bundle)
    if manifest != expected:
        raise QualificationError(f"oracle manifest content mismatch: {bundle}")
    if {path.name for path in bundle.iterdir()} != {
        "manifest.json",
        "oracle.json",
        "test_oracle.py",
    }:
        raise QualificationError(f"oracle bundle inventory mismatch: {bundle}")
    return {
        "bundle": str(bundle),
        "bundle_sha256": repository_content_digest(bundle).sha256,
        "manifest_sha256": manifest_sha256,
        "valid": True,
    }


def copy_immutable_oracle_bundle(
    source: Path, destination: Path, *, expected_manifest_sha256: str
) -> Path:
    validate_oracle_bundle(source, expected_manifest_sha256=expected_manifest_sha256)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"oracle destination already exists: {destination}")
    shutil.copytree(source, destination, symlinks=True)
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise QualificationError(f"copied oracle contains a symlink: {path}")
        path.chmod(0o555 if path.is_dir() else 0o444)
    destination.chmod(0o555)
    validate_oracle_bundle(
        destination, expected_manifest_sha256=expected_manifest_sha256
    )
    return destination.resolve(strict=True)


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and not any(part in _IGNORED_PARTS for part in path.relative_to(root).parts)
        and path.suffix != ".pyc"
    }


def _text_diff(path: str, before: bytes | None, after: bytes | None) -> str:
    before_lines = (
        []
        if before is None
        else before.decode("utf-8", errors="replace").splitlines(keepends=True)
    )
    after_lines = (
        []
        if after is None
        else after.decode("utf-8", errors="replace").splitlines(keepends=True)
    )
    return "".join(
        difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile="/dev/null" if before is None else f"a/{path}",
            tofile="/dev/null" if after is None else f"b/{path}",
        )
    )


def classified_repository_diffs(
    source_repository: Path,
    agent_repository: Path,
    policy: TaskFilePolicy,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    source = _snapshot(source_repository)
    agent = _snapshot(agent_repository)
    allowed: list[str] = []
    disallowed: list[str] = []
    allowed_paths: list[str] = []
    disallowed_paths: list[str] = []
    for relative in sorted(set(source) | set(agent)):
        before = source.get(relative)
        after = agent.get(relative)
        if before == after:
            continue
        diff = _text_diff(relative, before, after)
        if policy.mutation_allowed(relative):
            allowed.append(diff)
            allowed_paths.append(relative)
        else:
            disallowed.append(diff)
            disallowed_paths.append(relative)
    return (
        "".join(allowed),
        "".join(disallowed),
        tuple(allowed_paths),
        tuple(disallowed_paths),
    )


@dataclass(frozen=True)
class QualificationOracleResult:
    returncode: int
    passed: int
    failed: int
    output: str
    command: tuple[str, ...]
    manifest_before_sha256: str
    manifest_after_sha256: str
    validation_tree_sha256: str
    allowed_patch: str
    disallowed_diff: str
    allowed_paths_modified: tuple[str, ...]
    disallowed_paths_modified: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["command"] = list(self.command)
        value["allowed_paths_modified"] = list(self.allowed_paths_modified)
        value["disallowed_paths_modified"] = list(self.disallowed_paths_modified)
        return value


def _outcome_count(output: str, label: str) -> int:
    matches = re.findall(rf"\b(\d+)\s+{label}\b", output)
    return int(matches[-1]) if matches else 0


def run_external_oracle(
    *,
    source_repository: Path,
    agent_repository: Path,
    oracle_bundle: Path,
    expected_manifest_sha256: str,
    destination: Path,
    policy: TaskFilePolicy,
    artifact_directory: Path | None = None,
    python: Path = CMPILOT_PYTHON,
) -> QualificationOracleResult:
    before = validate_oracle_bundle(
        oracle_bundle, expected_manifest_sha256=expected_manifest_sha256
    )
    source_repository = source_repository.resolve(strict=True)
    agent_repository = agent_repository.resolve(strict=True)
    try:
        oracle_bundle.resolve(strict=True).relative_to(agent_repository)
    except ValueError:
        pass
    else:
        raise QualificationError("immutable oracle is inside the agent repository")
    copy_repository_tree(source_repository, destination)
    for relative in policy.writable_paths:
        source = agent_repository / relative
        target = destination / relative
        if not source.is_file() or source.is_symlink():
            raise QualificationError(f"authorized agent file is missing: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target, follow_symlinks=False)
        target.chmod(0o600)

    oracle_test = oracle_bundle / "test_oracle.py"
    validation_test = destination / "test_oracle.py"
    shutil.copyfile(oracle_test, validation_test, follow_symlinks=False)
    validation_test.chmod(0o600)
    if sha256_file(validation_test) != sha256_file(oracle_test):
        raise QualificationError("oracle copy in validation tree changed")
    configuration = load_json(oracle_bundle / "oracle.json")
    arguments = configuration.get("command")
    if not isinstance(arguments, list) or not all(
        isinstance(argument, str) for argument in arguments
    ):
        raise QualificationError("oracle command must be a string list")
    command = (str(python), *arguments)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=destination,
        text=True,
        capture_output=True,
        check=False,
        env=environment,
        timeout=120,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    after = validate_oracle_bundle(
        oracle_bundle, expected_manifest_sha256=expected_manifest_sha256
    )
    allowed, disallowed, allowed_paths, disallowed_paths = classified_repository_diffs(
        source_repository, agent_repository, policy
    )
    result = QualificationOracleResult(
        returncode=completed.returncode,
        passed=_outcome_count(output, "passed"),
        failed=_outcome_count(output, "failed"),
        output=output,
        command=command,
        manifest_before_sha256=before["manifest_sha256"],
        manifest_after_sha256=after["manifest_sha256"],
        validation_tree_sha256=repository_content_digest(destination).sha256,
        allowed_patch=allowed,
        disallowed_diff=disallowed,
        allowed_paths_modified=allowed_paths,
        disallowed_paths_modified=disallowed_paths,
    )
    if artifact_directory is not None:
        artifact_directory.mkdir(parents=True, exist_ok=True)
        (artifact_directory / "allowed.patch").write_text(
            result.allowed_patch, encoding="utf-8"
        )
        (artifact_directory / "disallowed.diff").write_text(
            result.disallowed_diff, encoding="utf-8"
        )
        (artifact_directory / "oracle-output.txt").write_text(
            result.output, encoding="utf-8"
        )
        write_canonical_json(
            artifact_directory / "oracle-result.json", result.as_dict()
        )
    return result


def load_suite_manifest(path: Path) -> dict[str, Any]:
    value = load_json(path)
    if value.get("schema") != SUITE_MANIFEST_SCHEMA:
        raise QualificationError(f"unsupported qualification suite: {path}")
    primary = value.get("primary_task_ids")
    reserve = value.get("reserve_task_ids")
    if not isinstance(primary, list) or len(primary) != 5 or len(set(primary)) != 5:
        raise QualificationError("suite must freeze exactly five unique primary tasks")
    if not isinstance(reserve, list) or len(reserve) != 2 or len(set(reserve)) != 2:
        raise QualificationError("suite must freeze exactly two unique reserve tasks")
    if set(primary) & set(reserve):
        raise QualificationError("primary and reserve tasks overlap")
    return value


def verify_sha256_record(path: Path, expected: str, *, name: str) -> dict[str, Any]:
    actual = sha256_file(path)
    return {
        "actual_sha256": actual,
        "expected_sha256": expected,
        "name": name,
        "pass": actual == expected,
        "path": str(path),
    }


def validate_task_manifest(project: Path, value: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    required = {
        "task_id",
        "repository",
        "task_description",
        "expected_user_visible_behavior",
        "allowed_writable_paths",
        "visible_protected_paths",
        "prohibited_paths",
        "immutable_external_oracle",
        "reference_patch",
        "expected_clean_state_oracle_result",
        "expected_reference_patch_oracle_result",
        "maximum_steps",
        "timeout_seconds",
        "model_configuration",
        "treatment_marker",
        "artifact_destination",
        "selection_rationale",
    }
    missing = sorted(required - set(value))
    if missing:
        errors.append(f"missing fields: {missing}")
        return errors
    if value.get("schema") != TASK_MANIFEST_SCHEMA:
        errors.append("unexpected task manifest schema")
    if value.get("treatment_marker") != "no_memory":
        errors.append("treatment marker is not no_memory")
    if value.get("maximum_steps") != 15 or value.get("timeout_seconds") != 600:
        errors.append("task limits differ from the frozen limits")
    if _UNRESOLVED.search(json.dumps(value, sort_keys=True)):
        errors.append("unresolved placeholder found")
    for section, key in (
        ("repository", "source_path"),
        ("immutable_external_oracle", "path"),
        ("reference_patch", "path"),
        ("task_instruction", "path"),
        ("task_policy", "path"),
    ):
        record = value.get(section)
        if isinstance(record, dict) and isinstance(record.get(key), str):
            path = project / record[key]
            if not path.exists():
                errors.append(f"missing {section} path: {path}")
    return errors


def task_policy_from_manifest(project: Path, task: Mapping[str, Any]) -> TaskFilePolicy:
    policy_record = task.get("task_policy")
    if not isinstance(policy_record, dict) or not isinstance(policy_record.get("path"), str):
        raise QualificationError("task manifest has no policy path")
    path = project / policy_record["path"]
    expected = policy_record.get("sha256")
    if expected != sha256_file(path):
        raise QualificationError(f"task policy hash mismatch: {path}")
    policy = load_task_policy(path)
    if list(policy.writable_paths) != task.get("allowed_writable_paths"):
        raise QualificationError("task policy writable paths differ from manifest")
    if list(policy.readable_protected_paths) != task.get("visible_protected_paths"):
        raise QualificationError("task policy protected paths differ from manifest")
    return policy


def task_paths(project: Path, task: Mapping[str, Any]) -> dict[str, Path]:
    return {
        "repository": project / task["repository"]["source_path"],
        "oracle": project / task["immutable_external_oracle"]["path"],
        "reference_patch": project / task["reference_patch"]["path"],
        "task_instruction": project / task["task_instruction"]["path"],
        "task_policy": project / task["task_policy"]["path"],
    }


def no_memory_prompt_check(rendered: Mapping[str, Any]) -> dict[str, Any]:
    prompts = rendered.get("prompts", {})
    text = "\n".join(str(item) for item in prompts.values())
    forbidden = [
        phrase
        for phrase in (
            "procedural memory",
            "memory block",
            "retrieved memory",
            "previous conversation",
        )
        if phrase in text.casefold()
    ]
    return {
        "forbidden_phrases": forbidden,
        "fresh_session_required": True,
        "memory_block_present": False,
        "pass": not forbidden,
        "residual_messages": 0,
    }


def artifact_manifest(root: Path, *, excluded: Sequence[str] = ()) -> dict[str, Any]:
    excluded_set = set(excluded)
    rows = []
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if relative in excluded_set:
            continue
        rows.append({"path": relative, "sha256": sha256_file(path)})
    payload = canonical_json_bytes(rows)
    return {
        "algorithm": "sha256 exact file bytes",
        "entry_count": len(rows),
        "inventory_sha256": sha256_bytes(payload),
        "rows": rows,
    }
