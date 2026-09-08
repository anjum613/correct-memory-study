"""Immutable external calculator oracle and allowed-patch validation tree."""

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
from typing import Any

from .repository_manager import copy_repository_tree, repository_content_digest
from .task_file_policy import TaskFilePolicy, calculator_task_policy


ORACLE_VERSION = "calculator-external-oracle-v1"
ORACLE_MANIFEST_SHA256 = (
    "6c8f827166c974c696b032d151610617466e5609f6d5e9162373f5f1cf4a1c18"
)
DEFAULT_CALCULATOR_ORACLE = (
    Path(__file__).parents[2] / "oracles" / "calculator" / "v1"
)
_IGNORED_PARTS = frozenset({".git", ".pytest_cache", "__pycache__"})


class OracleIntegrityError(RuntimeError):
    """Raised when oracle bytes, layout, or validation inputs are invalid."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def validate_oracle_bundle(bundle: Path) -> dict[str, Any]:
    """Require the versioned oracle manifest and all declared hashes to match."""
    bundle = bundle.resolve(strict=True)
    if not bundle.is_dir():
        raise OracleIntegrityError(f"oracle bundle is not a directory: {bundle}")
    manifest_path = bundle / "manifest.json"
    if not manifest_path.is_file() or manifest_path.is_symlink():
        raise OracleIntegrityError("oracle manifest is missing or is a symlink")
    manifest_sha256 = _sha256_file(manifest_path)
    if manifest_sha256 != ORACLE_MANIFEST_SHA256:
        raise OracleIntegrityError(
            "oracle manifest hash mismatch: "
            f"expected {ORACLE_MANIFEST_SHA256}, observed {manifest_sha256}"
        )
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise OracleIntegrityError(f"oracle manifest is unreadable: {error}") from error
    if manifest.get("oracle_version") != ORACLE_VERSION:
        raise OracleIntegrityError("unexpected calculator oracle version")
    declared = manifest.get("files")
    if not isinstance(declared, dict) or not declared:
        raise OracleIntegrityError("oracle manifest has no file inventory")
    expected_names = {"manifest.json", *declared}
    actual_names = {path.name for path in bundle.iterdir()}
    if actual_names != expected_names:
        raise OracleIntegrityError(
            f"oracle bundle inventory mismatch: expected {sorted(expected_names)}, "
            f"observed {sorted(actual_names)}"
        )
    files: dict[str, dict[str, Any]] = {}
    for name, expected_hash in sorted(declared.items()):
        if not isinstance(name, str) or not isinstance(expected_hash, str):
            raise OracleIntegrityError("oracle manifest entry is not textual")
        path = bundle / name
        if not path.is_file() or path.is_symlink():
            raise OracleIntegrityError(f"oracle file is missing or not regular: {name}")
        actual_hash = _sha256_file(path)
        files[name] = {
            "actual_sha256": actual_hash,
            "expected_sha256": expected_hash,
            "matches": actual_hash == expected_hash,
            "mode": format(stat.S_IMODE(path.stat().st_mode), "04o"),
            "size_bytes": path.stat().st_size,
        }
        if actual_hash != expected_hash:
            raise OracleIntegrityError(f"oracle file hash mismatch: {name}")
    configuration = json.loads((bundle / "oracle.json").read_text(encoding="utf-8"))
    if configuration.get("oracle_version") != ORACLE_VERSION:
        raise OracleIntegrityError("oracle configuration version does not match")
    if configuration.get("test_file") != "test_calculator.py":
        raise OracleIntegrityError("oracle configuration test file is unexpected")
    return {
        "valid": True,
        "bundle": str(bundle),
        "oracle_version": ORACLE_VERSION,
        "manifest_sha256": manifest_sha256,
        "files": files,
    }


def copy_immutable_oracle_bundle(source: Path, destination: Path) -> Path:
    """Create a job-owned, read-only oracle copy outside the agent repository."""
    validate_oracle_bundle(source)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"oracle destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination, symlinks=True)
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise OracleIntegrityError(f"copied oracle contains a symlink: {path}")
        path.chmod(0o555 if path.is_dir() else 0o444)
    destination.chmod(0o555)
    validate_oracle_bundle(destination)
    return destination.resolve(strict=True)


def _snapshot(root: Path) -> dict[str, bytes]:
    snapshot: dict[str, bytes] = {}
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if (
            not path.is_file()
            or path.is_symlink()
            or any(part in _IGNORED_PARTS for part in relative.parts)
            or path.suffix == ".pyc"
        ):
            continue
        snapshot[relative.as_posix()] = path.read_bytes()
    return snapshot


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


def _classified_diffs(
    source_repository: Path,
    agent_repository: Path,
    task_policy: TaskFilePolicy,
) -> tuple[str, str, tuple[str, ...]]:
    source = _snapshot(source_repository)
    agent = _snapshot(agent_repository)
    allowed: list[str] = []
    disallowed: list[str] = []
    protected_modified: list[str] = []
    for relative in sorted(set(source) | set(agent)):
        before = source.get(relative)
        after = agent.get(relative)
        if before == after:
            continue
        diff = _text_diff(relative, before, after)
        if relative in task_policy.writable_paths:
            allowed.append(diff)
        else:
            disallowed.append(diff)
        if relative in task_policy.readable_protected_paths:
            protected_modified.append(relative)
    return "".join(allowed), "".join(disallowed), tuple(protected_modified)


@dataclass(frozen=True)
class CalculatorValidationTree:
    repository: Path
    allowed_patch: str
    disallowed_diff: str
    protected_paths_modified: tuple[str, ...]
    validation_tree_sha256: str
    oracle_test_sha256: str

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["repository"] = str(self.repository)
        value["protected_paths_modified"] = list(self.protected_paths_modified)
        return value


def build_calculator_validation_tree(
    *,
    source_repository: Path,
    agent_repository: Path,
    oracle_bundle: Path,
    destination: Path,
    task_policy: TaskFilePolicy | None = None,
) -> CalculatorValidationTree:
    """Build a fresh tree from frozen source plus only policy-authorized changes."""
    task_policy = task_policy or calculator_task_policy()
    source_repository = source_repository.resolve(strict=True)
    agent_repository = agent_repository.resolve(strict=True)
    oracle_bundle = oracle_bundle.resolve(strict=True)
    try:
        oracle_bundle.relative_to(agent_repository)
    except ValueError:
        pass
    else:
        raise OracleIntegrityError("external oracle is inside the agent repository")
    validate_oracle_bundle(oracle_bundle)
    destination.parent.mkdir(parents=True, exist_ok=True)
    copy_repository_tree(source_repository, destination)

    for relative in task_policy.writable_paths:
        source = agent_repository / relative
        target = destination / relative
        if not source.is_file() or source.is_symlink():
            raise OracleIntegrityError(f"allowed agent file is missing or unsafe: {relative}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target, follow_symlinks=False)
        target.chmod(0o600)

    oracle_test = oracle_bundle / "test_calculator.py"
    validation_test = destination / "test_calculator.py"
    shutil.copyfile(oracle_test, validation_test, follow_symlinks=False)
    validation_test.chmod(0o600)
    if _sha256_file(validation_test) != _sha256_file(oracle_test):
        raise OracleIntegrityError("validation tree oracle copy hash mismatch")

    allowed_patch, disallowed_diff, protected_modified = _classified_diffs(
        source_repository, agent_repository, task_policy
    )
    return CalculatorValidationTree(
        repository=destination.resolve(strict=True),
        allowed_patch=allowed_patch,
        disallowed_diff=disallowed_diff,
        protected_paths_modified=protected_modified,
        validation_tree_sha256=repository_content_digest(destination).sha256,
        oracle_test_sha256=_sha256_file(oracle_test),
    )


@dataclass(frozen=True)
class CalculatorOracleResult:
    returncode: int
    passed: int
    failed: int
    output: str
    command: tuple[str, ...]
    manifest_before_sha256: str
    manifest_after_sha256: str
    validation_tree_sha256: str
    oracle_test_sha256: str
    allowed_patch: str
    disallowed_diff: str
    protected_paths_modified: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["command"] = list(self.command)
        value["protected_paths_modified"] = list(self.protected_paths_modified)
        return value


def _count_outcome(output: str, label: str) -> int:
    matches = re.findall(rf"\b(\d+)\s+{label}\b", output)
    return int(matches[-1]) if matches else 0


def run_external_calculator_oracle(
    *,
    source_repository: Path,
    agent_repository: Path,
    oracle_bundle: Path,
    destination: Path,
    task_policy: TaskFilePolicy | None = None,
    artifact_directory: Path | None = None,
    python: Path | None = None,
) -> CalculatorOracleResult:
    """Run authoritative tests only after agent termination in a fresh tree."""
    before = validate_oracle_bundle(oracle_bundle)
    tree = build_calculator_validation_tree(
        source_repository=source_repository,
        agent_repository=agent_repository,
        oracle_bundle=oracle_bundle,
        destination=destination,
        task_policy=task_policy,
    )
    immediately_before = validate_oracle_bundle(oracle_bundle)
    if before["manifest_sha256"] != immediately_before["manifest_sha256"]:
        raise OracleIntegrityError("oracle manifest changed before execution")
    configuration = json.loads(
        (oracle_bundle / "oracle.json").read_text(encoding="utf-8")
    )
    arguments = configuration.get("command")
    if not isinstance(arguments, list) or not all(
        isinstance(argument, str) for argument in arguments
    ):
        raise OracleIntegrityError("oracle command is not a string list")
    command = (str(python or Path(sys.executable)), *arguments)
    environment = os.environ.copy()
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    completed = subprocess.run(
        command,
        cwd=tree.repository,
        text=True,
        capture_output=True,
        env=environment,
        check=False,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    after = validate_oracle_bundle(oracle_bundle)
    if immediately_before["manifest_sha256"] != after["manifest_sha256"]:
        raise OracleIntegrityError("oracle manifest changed during execution")
    result = CalculatorOracleResult(
        returncode=completed.returncode,
        passed=_count_outcome(output, "passed"),
        failed=_count_outcome(output, "failed"),
        output=output,
        command=command,
        manifest_before_sha256=immediately_before["manifest_sha256"],
        manifest_after_sha256=after["manifest_sha256"],
        validation_tree_sha256=tree.validation_tree_sha256,
        oracle_test_sha256=tree.oracle_test_sha256,
        allowed_patch=tree.allowed_patch,
        disallowed_diff=tree.disallowed_diff,
        protected_paths_modified=tree.protected_paths_modified,
    )
    if artifact_directory is not None:
        artifact_directory.mkdir(parents=True, exist_ok=True)
        (artifact_directory / "allowed.patch").write_text(
            result.allowed_patch, encoding="utf-8"
        )
        (artifact_directory / "disallowed.diff").write_text(
            result.disallowed_diff, encoding="utf-8"
        )
        (artifact_directory / "external-oracle-output.txt").write_text(
            result.output, encoding="utf-8"
        )
        _write_json(artifact_directory / "external-oracle-result.json", result.as_dict())
        _write_json(artifact_directory / "validation-tree.json", tree.as_dict())
    return result
