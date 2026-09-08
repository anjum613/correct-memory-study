"""Static, non-executing Stage-1 repository feasibility inspection."""

from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
from typing import Any


PROTOCOL_VERSION = "benchmark-selection-v0.1"
SPEC_SCHEMA = "stage1-inspection-spec-v0.1"
RESULT_SCHEMA = "stage1-candidate-result-v0.1"
BATCH_SCHEMA = "stage1-screening-batch-v0.1"
VERIFICATION_SCHEMA = "stage1-screening-verification-v0.1"
AUTOMATIC_GATES = (
    "usable_licence",
    "immutable_commit",
    "reproducible_setup",
    "deterministic_baseline_tests",
    "manageable_task_size",
    "no_proprietary_credentials_or_uncontrolled_service",
)
MECHANISM_GATES = (
    "narrow_observable_p_star",
    "one_condition_isolation",
    "target_not_already_vulnerable",
    "faithful_reuse_functional_and_witness_open",
    "secure_reference_functional_and_witness_blocked",
    "implementation_independent_functional_oracle",
    "deterministic_security_witness",
    "independent_approval",
)
EXCLUSION_CODES = {
    "usable_licence": "LICENCE_UNUSABLE",
    "immutable_commit": "IMMUTABLE_COMMIT_UNAVAILABLE",
    "reproducible_setup": "SETUP_NOT_REPRODUCIBLE",
    "deterministic_baseline_tests": "BASELINE_TESTS_NONDETERMINISTIC",
    "manageable_task_size": "TASK_SIZE_UNMANAGEABLE",
    "no_proprietary_credentials_or_uncontrolled_service": (
        "CREDENTIAL_OR_SERVICE_DEPENDENCY"
    ),
}
LICENSE_BASENAME = re.compile(
    r"^(?:licen[cs]e|copying|copyright|notice)(?:[._-].*)?$", re.IGNORECASE
)
TEST_BASENAME = re.compile(r"^(?:test_.+|.+_test)\.py$", re.IGNORECASE)
BUILD_BASENAMES = frozenset(
    {
        "build.gradle",
        "build.gradle.kts",
        "cargo.toml",
        "environment.yml",
        "environment.yaml",
        "gemfile",
        "go.mod",
        "makefile",
        "meson.build",
        "noxfile.py",
        "package.json",
        "pipfile",
        "pipfile.lock",
        "poetry.lock",
        "pom.xml",
        "pyproject.toml",
        "pytest.ini",
        "requirements.txt",
        "runtime.txt",
        "setup.cfg",
        "setup.py",
        "tox.ini",
        "uv.lock",
    }
)
TEXT_SUFFIXES = frozenset(
    {
        ".cfg",
        ".ini",
        ".json",
        ".md",
        ".py",
        ".rst",
        ".sh",
        ".toml",
        ".txt",
        ".yaml",
        ".yml",
    }
)
SIGNALS: dict[str, tuple[str, ...]] = {
    "external_service": (
        "redis",
        "postgres",
        "mysql",
        "mongodb",
        "elasticsearch",
        "rabbitmq",
        "kafka",
        "openai",
        "anthropic",
        "google cloud",
        "amazon web services",
    ),
    "gpu": (
        "torch.cuda",
        "cuda",
        "nvidia",
        "cupy",
        "tensorflow-gpu",
        "triton",
    ),
    "database": (
        "postgres",
        "mysql",
        "mariadb",
        "mongodb",
        "redis",
        "sqlite",
        "sqlalchemy",
    ),
    "network": (
        "requests.",
        "httpx",
        "aiohttp",
        "urllib",
        "socket.",
        "https://",
        "http://",
    ),
    "proprietary_dependency": (
        "openai",
        "anthropic",
        "cohere",
        "gemini",
        "azure",
        "aws_access_key",
        "google_api_key",
    ),
}
SHA256 = re.compile(r"^[0-9a-f]{64}$")
COMMIT = re.compile(r"^[0-9a-f]{40}$")


class Stage1ScreeningError(RuntimeError):
    """Raised when Stage-1 evidence cannot be safely produced or verified."""


def _canonical_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode("utf-8")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise Stage1ScreeningError(f"cannot read JSON {path}: {error}") from error


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise Stage1ScreeningError(f"{label} must be an object")
    return value


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise Stage1ScreeningError(f"{label} must be a non-empty string")
    return value


def _safe_relative(value: Any, label: str) -> Path:
    path = Path(_string(value, label))
    if path.is_absolute() or ".." in path.parts:
        raise Stage1ScreeningError(f"{label} must be a safe relative path")
    return path


def load_spec(path: Path) -> Mapping[str, Any]:
    spec = _mapping(_load_json(path), "inspection spec")
    expected = {
        "schema": SPEC_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "candidate_code_execution": False,
        "installation_executed": False,
        "test_execution_allowed": False,
        "treatment_results_consulted": False,
    }
    for key, value in expected.items():
        if spec.get(key) != value:
            raise Stage1ScreeningError(f"inspection spec {key} must equal {value!r}")
    if tuple(spec.get("automatic_gate_order", ())) != AUTOMATIC_GATES:
        raise Stage1ScreeningError("inspection spec automatic gate order changed")
    candidate_ids = spec.get("expected_candidate_ids")
    if (
        not isinstance(candidate_ids, list)
        or not candidate_ids
        or any(
            not isinstance(candidate_id, str)
            or re.fullmatch(r"CMVP-CAND-[0-9]{4}", candidate_id) is None
            for candidate_id in candidate_ids
        )
        or len(candidate_ids) != len(set(candidate_ids))
    ):
        raise Stage1ScreeningError(
            "inspection spec expected_candidate_ids must be unique candidate IDs"
        )
    _safe_relative(spec.get("input_source_list"), "input_source_list")
    _safe_relative(spec.get("output_directory"), "output_directory")
    if not SHA256.fullmatch(str(spec.get("input_source_list_sha256", ""))):
        raise Stage1ScreeningError("inspection spec source-list hash is invalid")
    limits = _mapping(spec.get("content_limits"), "content limits")
    for name in ("maximum_blob_bytes", "maximum_total_scanned_blob_bytes"):
        value = limits.get(name)
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            raise Stage1ScreeningError(f"inspection spec {name} must be positive")
    return spec


def _run_git(
    arguments: Sequence[str],
    *,
    timeout: int,
) -> dict[str, Any]:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                "credential.helper=",
                "-c",
                "core.hooksPath=/dev/null",
                *arguments,
            ],
            check=False,
            capture_output=True,
            env=environment,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "arguments": ["git", *arguments],
            "returncode": None,
            "timed_out": True,
            "stdout": (error.stdout or b"").decode("utf-8", "replace"),
            "stderr": (error.stderr or b"").decode("utf-8", "replace"),
        }
    return {
        "arguments": ["git", *arguments],
        "returncode": result.returncode,
        "timed_out": False,
        "stdout": result.stdout.decode("utf-8", "replace"),
        "stderr": result.stderr.decode("utf-8", "replace"),
    }


def _git_output(repository: Path, arguments: Sequence[str], *, timeout: int) -> bytes:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "LC_ALL": "C",
        }
    )
    result = subprocess.run(
        [
            "git",
            "-c",
            "credential.helper=",
            "-c",
            "core.hooksPath=/dev/null",
            f"--git-dir={repository}",
            *arguments,
        ],
        check=False,
        capture_output=True,
        env=environment,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise Stage1ScreeningError(
            f"git {' '.join(arguments)} failed: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def _parse_tree(raw: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for item in raw.split(b"\0"):
        if not item:
            continue
        metadata, separator, raw_path = item.partition(b"\t")
        if not separator:
            raise Stage1ScreeningError("malformed git ls-tree output")
        parts = metadata.decode("ascii").split()
        if len(parts) != 4:
            raise Stage1ScreeningError("malformed git ls-tree metadata")
        mode, object_type, object_id, raw_size = parts
        path = raw_path.decode("utf-8", "surrogateescape")
        entries.append(
            {
                "mode": mode,
                "type": object_type,
                "object_id": object_id,
                "size_bytes": None if raw_size == "-" else int(raw_size),
                "path": path,
            }
        )
    return entries


def _directory_size(path: Path) -> tuple[int, int]:
    apparent = 0
    allocated = 0
    for candidate in path.rglob("*"):
        try:
            stat = candidate.lstat()
        except FileNotFoundError:
            continue
        apparent += stat.st_size
        allocated += getattr(stat, "st_blocks", 0) * 512
    return apparent, allocated


def _read_blob(
    repository: Path,
    commit: str,
    entry: Mapping[str, Any],
    *,
    timeout: int,
    maximum_blob_bytes: int,
) -> bytes | None:
    size = entry.get("size_bytes")
    if not isinstance(size, int) or size > maximum_blob_bytes:
        return None
    return _git_output(
        repository,
        ["show", f"{commit}:{entry['path']}"],
        timeout=timeout,
    )


def _is_build_metadata(path: str) -> bool:
    pure = PurePosixPath(path)
    basename = pure.name.casefold()
    return (
        basename in BUILD_BASENAMES
        or basename.startswith("requirements") and basename.endswith(".txt")
        or basename.startswith("dockerfile")
        or basename.startswith("compose.")
        or basename.startswith("docker-compose.")
        or len(pure.parts) >= 3
        and pure.parts[0:2] == (".github", "workflows")
        and pure.suffix.casefold() in {".yml", ".yaml"}
    )


def _is_test_file(path: str) -> bool:
    pure = PurePosixPath(path)
    lower_parts = tuple(part.casefold() for part in pure.parts)
    return bool(TEST_BASENAME.fullmatch(pure.name)) or any(
        part in {"test", "tests"} for part in lower_parts[:-1]
    )


def _is_scannable_text(path: str) -> bool:
    pure = PurePosixPath(path)
    return (
        pure.suffix.casefold() in TEXT_SUFFIXES
        or _is_build_metadata(path)
        or LICENSE_BASENAME.fullmatch(pure.name) is not None
        or pure.name.casefold() in {"readme", ".python-version"}
    )


def _test_directories(paths: Sequence[str]) -> list[str]:
    directories: set[str] = set()
    for path in paths:
        pure = PurePosixPath(path)
        for index, part in enumerate(pure.parts[:-1]):
            if part.casefold() in {"test", "tests"}:
                directories.add(PurePosixPath(*pure.parts[: index + 1]).as_posix())
    return sorted(directories)


def _runtime_constraints(text_by_path: Mapping[str, str]) -> list[dict[str, str]]:
    patterns = (
        re.compile(r"requires-python\s*=\s*[\"']([^\"']+)", re.IGNORECASE),
        re.compile(r"python_requires\s*=\s*([^\n#]+)", re.IGNORECASE),
    )
    findings: list[dict[str, str]] = []
    for path, text in text_by_path.items():
        basename = PurePosixPath(path).name.casefold()
        if basename in {".python-version", "runtime.txt"}:
            value = text.strip().splitlines()[0] if text.strip() else ""
            if value:
                findings.append({"path": path, "constraint": value[:200]})
        for pattern in patterns:
            for match in pattern.finditer(text):
                findings.append(
                    {"path": path, "constraint": match.group(1).strip()[:200]}
                )
    return sorted(findings, key=lambda item: (item["path"], item["constraint"]))


def _frameworks(text_by_path: Mapping[str, str], paths: Sequence[str]) -> list[str]:
    joined = "\n".join(text.casefold() for text in text_by_path.values())
    names = {PurePosixPath(path).name.casefold() for path in paths}
    detected: set[str] = set()
    if "pytest" in joined or "pytest.ini" in names:
        detected.add("pytest")
    if "import unittest" in joined or "from unittest" in joined:
        detected.add("unittest")
    if "nose" in joined:
        detected.add("nose")
    if "tox.ini" in names:
        detected.add("tox")
    if "noxfile.py" in names:
        detected.add("nox")
    if "hypothesis" in joined:
        detected.add("hypothesis")
    return sorted(detected)


def _count_python_tests(text_by_path: Mapping[str, str], test_paths: set[str]) -> dict[str, Any]:
    functions = 0
    methods = 0
    parse_errors: list[str] = []
    for path in sorted(test_paths):
        text = text_by_path.get(path)
        if text is None or not path.casefold().endswith(".py"):
            continue
        try:
            tree = ast.parse(text, filename=path)
        except SyntaxError:
            parse_errors.append(path)
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name.startswith("test")
            ):
                functions += 1
            elif isinstance(node, ast.ClassDef):
                methods += sum(
                    isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and child.name.startswith("test")
                    for child in node.body
                )
    return {
        "method": "static_python_ast_name_count",
        "function_nodes": functions,
        "class_method_nodes": methods,
        "total": functions,
        "parse_error_paths": parse_errors,
    }


def _setup_commands(paths: Sequence[str]) -> list[dict[str, str]]:
    names = {PurePosixPath(path).name.casefold(): path for path in paths}
    commands: list[dict[str, str]] = []
    if "uv.lock" in names:
        commands.append({"command": "uv sync --frozen", "basis": names["uv.lock"]})
    if "poetry.lock" in names:
        commands.append(
            {"command": "poetry install --no-interaction", "basis": names["poetry.lock"]}
        )
    if "pipfile.lock" in names:
        commands.append(
            {"command": "pipenv sync --dev", "basis": names["pipfile.lock"]}
        )
    requirement_paths = sorted(
        path
        for path in paths
        if PurePosixPath(path).name.casefold().startswith("requirements")
        and path.casefold().endswith(".txt")
    )
    for path in requirement_paths:
        commands.append(
            {"command": f"python -m pip install -r {path}", "basis": path}
        )
    for name in ("pyproject.toml", "setup.py", "setup.cfg"):
        if name in names:
            commands.append(
                {"command": "python -m pip install -e .", "basis": names[name]}
            )
            break
    if "environment.yml" in names:
        commands.append(
            {
                "command": f"conda env create -f {names['environment.yml']}",
                "basis": names["environment.yml"],
            }
        )
    if "environment.yaml" in names:
        commands.append(
            {
                "command": f"conda env create -f {names['environment.yaml']}",
                "basis": names["environment.yaml"],
            }
        )
    return commands


def _baseline_command(frameworks: Sequence[str]) -> dict[str, Any]:
    if "pytest" in frameworks:
        return {
            "command": "python -m pytest -q",
            "status": "STATIC_CANDIDATE",
            "reason": "pytest evidence detected; command not executed",
        }
    if "unittest" in frameworks:
        return {
            "command": "python -m unittest discover",
            "status": "STATIC_CANDIDATE",
            "reason": "unittest evidence detected; command not executed",
        }
    if "nox" in frameworks:
        return {
            "command": "nox",
            "status": "STATIC_CANDIDATE",
            "reason": "nox configuration detected; command not executed",
        }
    if "tox" in frameworks:
        return {
            "command": "tox",
            "status": "STATIC_CANDIDATE",
            "reason": "tox configuration detected; command not executed",
        }
    return {
        "command": None,
        "status": "NEEDS_REVIEW",
        "reason": "no supported baseline-test framework was statically identified",
    }


def _signal_facts(text_by_path: Mapping[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for category, tokens in SIGNALS.items():
        evidence: list[dict[str, str]] = []
        for path, text in sorted(text_by_path.items()):
            lowered = text.casefold()
            for token in tokens:
                if token in lowered:
                    evidence.append({"path": path, "signal": token})
                    if len(evidence) >= 40:
                        break
            if len(evidence) >= 40:
                break
        result[category] = {
            "status": (
                "DETECTED_BY_STATIC_SCAN"
                if evidence
                else "NOT_DETECTED_BY_STATIC_SCAN"
            ),
            "signals": evidence,
        }
    return result


def _inspect_candidate(
    *,
    candidate: Mapping[str, Any],
    spec: Mapping[str, Any],
    scratch_root: Path,
    method_commit: str,
    result_path: str,
) -> dict[str, Any]:
    candidate_id = _string(candidate.get("candidate_id"), "candidate_id")
    source = _mapping(candidate.get("source"), f"{candidate_id}.source")
    snapshot = _mapping(source.get("snapshot"), f"{candidate_id}.snapshot")
    normalized = _mapping(
        candidate.get("normalized_metadata"), f"{candidate_id}.normalized_metadata"
    )
    repository_metadata = _mapping(
        normalized.get("repository"), f"{candidate_id}.repository metadata"
    )
    commit_metadata = _mapping(
        normalized.get("commit"), f"{candidate_id}.commit metadata"
    )
    commit = _string(snapshot.get("commit_sha"), f"{candidate_id}.commit_sha")
    repository_url = _string(source.get("repository_url"), f"{candidate_id}.url")
    clone_url = (
        repository_url if repository_url.endswith(".git") else f"{repository_url}.git"
    )
    limits = _mapping(spec.get("content_limits"), "content limits")
    maximum_blob_bytes = int(limits["maximum_blob_bytes"])
    maximum_total_bytes = int(limits["maximum_total_scanned_blob_bytes"])
    clone = _mapping(spec.get("clone"), "clone spec")
    timeout = int(clone["network_timeout_seconds"])
    started_at = _utc_now()
    repository = scratch_root / f"{candidate_id}.git"
    commands: list[dict[str, Any]] = []
    init = _run_git(["init", "--bare", str(repository)], timeout=timeout)
    commands.append(init)
    if init["returncode"] != 0:
        raise Stage1ScreeningError(f"cannot initialize scratch repository for {candidate_id}")
    fetch = _run_git(
        [
            f"--git-dir={repository}",
            "fetch",
            "--depth=1",
            "--no-tags",
            clone_url,
            commit,
        ],
        timeout=timeout,
    )
    commands.append(fetch)
    fetch_ok = fetch["returncode"] == 0 and not fetch["timed_out"]
    resolved_commit: str | None = None
    resolved_tree: str | None = None
    entries: list[dict[str, Any]] = []
    object_error: str | None = None
    if fetch_ok:
        try:
            resolved_commit = _git_output(
                repository, ["rev-parse", "FETCH_HEAD^{commit}"], timeout=timeout
            ).decode("ascii").strip()
            resolved_tree = _git_output(
                repository, ["rev-parse", "FETCH_HEAD^{tree}"], timeout=timeout
            ).decode("ascii").strip()
            entries = _parse_tree(
                _git_output(
                    repository,
                    ["ls-tree", "-r", "-l", "-z", "FETCH_HEAD"],
                    timeout=timeout,
                )
            )
        except Stage1ScreeningError as error:
            object_error = str(error)
    apparent_bytes, allocated_bytes = _directory_size(repository)
    paths = [entry["path"] for entry in entries]
    test_paths = sorted(path for path in paths if _is_test_file(path))
    build_paths = sorted(path for path in paths if _is_build_metadata(path))
    license_entries = [
        entry
        for entry in entries
        if LICENSE_BASENAME.fullmatch(PurePosixPath(entry["path"]).name)
    ]
    scannable_paths = sorted(path for path in paths if _is_scannable_text(path))
    text_by_path: dict[str, str] = {}
    scanned_bytes = 0
    skipped_oversized: list[str] = []
    skipped_budget: list[str] = []
    skipped_binary: list[str] = []
    entry_by_path = {entry["path"]: entry for entry in entries}
    if resolved_commit is not None:
        for path in scannable_paths:
            entry = entry_by_path[path]
            size = entry.get("size_bytes")
            if not isinstance(size, int) or size > maximum_blob_bytes:
                skipped_oversized.append(path)
                continue
            if scanned_bytes + size > maximum_total_bytes:
                skipped_budget.append(path)
                continue
            raw = _read_blob(
                repository,
                resolved_commit,
                entry,
                timeout=timeout,
                maximum_blob_bytes=maximum_blob_bytes,
            )
            if raw is None:
                skipped_oversized.append(path)
                continue
            if b"\0" in raw:
                skipped_binary.append(path)
                continue
            text_by_path[path] = raw.decode("utf-8", "replace")
            scanned_bytes += len(raw)
    license_files = [
        {
            "path": entry["path"],
            "git_blob": entry["object_id"],
            "size_bytes": entry["size_bytes"],
        }
        for entry in license_entries
    ]
    frameworks = _frameworks(text_by_path, paths)
    setup_commands = _setup_commands(paths)
    signal_facts = _signal_facts(text_by_path)
    local_dependency_signals = []
    for path, text in sorted(text_by_path.items()):
        if _is_build_metadata(path) and re.search(
            r"(?:^|[=\s])(?:file:|\.\.?/)", text, re.MULTILINE
        ):
            local_dependency_signals.append(path)
    if setup_commands and not local_dependency_signals:
        install_assessment = {
            "status": "APPEARS_FEASIBLE_STATICALLY",
            "reason": "recognized setup metadata produced at least one command candidate; not executed",
        }
    else:
        install_assessment = {
            "status": "NEEDS_REVIEW",
            "reason": (
                "local/path dependency signals require review"
                if local_dependency_signals
                else "no recognized setup command candidate"
            ),
        }
    captured_spdx = str(repository_metadata.get("license_spdx", source.get("licence_spdx")))
    license_pass = captured_spdx not in {"", "NOASSERTION", "OTHER", "None"} and bool(
        license_files
    )
    captured_tree = commit_metadata.get("tree_sha")
    if not fetch_ok or resolved_commit is None or resolved_tree is None:
        immutable_status = "NEEDS_REVIEW"
        immutable_reason = "exact commit fetch or object resolution did not complete"
    elif resolved_commit != commit or resolved_tree != captured_tree:
        immutable_status = "FAIL"
        immutable_reason = "successfully fetched commit/tree differs from frozen identity"
    else:
        immutable_status = "PASS"
        immutable_reason = "exact commit and Git tree match frozen discovery metadata"
    automatic_gates = {
        "usable_licence": {
            "status": "PASS" if license_pass else "NEEDS_REVIEW",
            "reason": (
                "recognized captured SPDX value and at least one licence file"
                if license_pass
                else "captured SPDX or licence-file evidence is ambiguous"
            ),
        },
        "immutable_commit": {
            "status": immutable_status,
            "reason": immutable_reason,
        },
        "reproducible_setup": {
            "status": "NEEDS_REVIEW",
            "reason": "installation was not executed under the static protocol",
        },
        "deterministic_baseline_tests": {
            "status": "NEEDS_REVIEW",
            "reason": "tests were not executed or repeated under the static protocol",
        },
        "manageable_task_size": {
            "status": "NEEDS_REVIEW",
            "reason": "no repository-level repair task has been constructed",
        },
        "no_proprietary_credentials_or_uncontrolled_service": {
            "status": "NEEDS_REVIEW",
            "reason": "static signals cannot prove absence or necessity of external requirements",
        },
    }
    statuses = {gate["status"] for gate in automatic_gates.values()}
    resulting_state = (
        "EXCLUDED"
        if "FAIL" in statuses
        else "AUTOMATIC_GATES_PASSED"
        if statuses == {"PASS"}
        else "DISCOVERED"
    )
    inventory_digest = _sha256_bytes(_canonical_bytes(entries))
    result = {
        "schema": RESULT_SCHEMA,
        "protocol_version": PROTOCOL_VERSION,
        "candidate_id": candidate_id,
        "repository": {
            "full_name": repository_metadata.get("full_name"),
            "url": repository_url,
            "default_branch": repository_metadata.get("default_branch"),
            "captured_language": repository_metadata.get("language"),
            "captured_license_spdx": captured_spdx,
            "expected_commit": commit,
            "captured_git_tree_sha": captured_tree,
        },
        "inspection": {
            "started_at_utc": started_at,
            "completed_at_utc": _utc_now(),
            "actor_id": spec.get("actor_id"),
            "method_commit": method_commit,
            "result_path": result_path,
            "commands": commands,
            "candidate_code_executed": False,
            "checkout_created": False,
            "installation_executed": False,
            "tests_executed": False,
            "model_or_treatment_accessed": False,
            "temporary_clone_removed_after_batch": True,
        },
        "facts": {
            "license": {
                "captured_spdx": captured_spdx,
                "license_files": license_files,
            },
            "frozen_commit_resolution": {
                "fetch_succeeded": fetch_ok,
                "expected_commit": commit,
                "resolved_commit": resolved_commit,
                "expected_git_tree_sha": captured_tree,
                "resolved_git_tree_sha": resolved_tree,
                "object_error": object_error,
            },
            "language_runtime_metadata": {
                "captured_primary_language": repository_metadata.get("language"),
                "extension_counts": _extension_counts(paths),
                "declared_runtime_constraints": _runtime_constraints(text_by_path),
            },
            "static_text_scan": {
                "eligible_file_count": len(scannable_paths),
                "scanned_file_count": len(text_by_path),
                "scanned_bytes": scanned_bytes,
                "maximum_blob_bytes": maximum_blob_bytes,
                "maximum_total_scanned_blob_bytes": maximum_total_bytes,
                "skipped_oversized_paths": skipped_oversized,
                "skipped_budget_paths": skipped_budget,
                "skipped_binary_paths": skipped_binary,
                "coverage_complete_within_declared_suffixes": not (
                    skipped_oversized or skipped_budget or skipped_binary
                ),
            },
            "repository_size": {
                "captured_github_size_kib": repository_metadata.get("size_kib"),
                "bare_depth1_clone_apparent_bytes": apparent_bytes,
                "bare_depth1_clone_allocated_bytes": allocated_bytes,
                "logical_tree_blob_bytes": sum(
                    entry["size_bytes"]
                    for entry in entries
                    if isinstance(entry.get("size_bytes"), int)
                ),
                "tree_entry_count": len(entries),
                "tree_inventory_sha256": inventory_digest,
            },
            "tests": {
                "directories": _test_directories(test_paths),
                "files": test_paths,
                "detected_frameworks": frameworks,
                "cheap_test_count": _count_python_tests(text_by_path, set(test_paths)),
                "likely_baseline_command": _baseline_command(frameworks),
            },
            "package_build_metadata": {
                "paths": build_paths,
                "file_evidence": [
                    {
                        "path": path,
                        "git_blob": entry_by_path[path]["object_id"],
                        "size_bytes": entry_by_path[path]["size_bytes"],
                    }
                    for path in build_paths
                ],
            },
            "setup_command_candidates": setup_commands,
            "external_service_requirements": signal_facts["external_service"],
            "gpu_requirement": signal_facts["gpu"],
            "database_requirement": signal_facts["database"],
            "network_requirement": signal_facts["network"],
            "proprietary_dependency_requirement": signal_facts[
                "proprietary_dependency"
            ],
            "clean_installation": {
                **install_assessment,
                "local_dependency_signal_paths": local_dependency_signals,
            },
        },
        "automatic_gates": automatic_gates,
        "resulting_state": resulting_state,
        "trust_family_assigned": False,
        "p_star_decided": False,
        "references_constructed": False,
        "ranked_or_selected": False,
        "treatment_results_consulted": False,
    }
    return result


def _extension_counts(paths: Sequence[str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for path in paths:
        suffix = PurePosixPath(path).suffix.casefold() or "[no-extension]"
        counts[suffix] = counts.get(suffix, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def _build_summary(
    results: Sequence[Mapping[str, Any]], *, source_list_id: Any
) -> dict[str, Any]:
    return {
        "schema": "stage1-screening-summary-v0.1",
        "protocol_version": PROTOCOL_VERSION,
        "source_list_id": source_list_id,
        "candidate_count": len(results),
        "candidate_order": [result["candidate_id"] for result in results],
        "resulting_states": {
            state: sum(result["resulting_state"] == state for result in results)
            for state in ("DISCOVERED", "AUTOMATIC_GATES_PASSED", "EXCLUDED")
        },
        "gate_status_counts": {
            gate: {
                status: sum(
                    result["automatic_gates"][gate]["status"] == status
                    for result in results
                )
                for status in ("PASS", "FAIL", "NEEDS_REVIEW")
            }
            for gate in AUTOMATIC_GATES
        },
        "ranked_or_selected": False,
        "treatment_results_consulted": False,
    }


def screen_batch(
    *,
    project_root: Path,
    spec_path: Path,
    output_directory: Path,
    method_commit: str,
    scratch_parent: Path,
) -> dict[str, Any]:
    """Inspect every source-list candidate once and atomically write evidence."""

    if output_directory.exists():
        raise Stage1ScreeningError(f"output directory already exists: {output_directory}")
    if not COMMIT.fullmatch(method_commit):
        raise Stage1ScreeningError("method_commit must be a full Git commit")
    spec = load_spec(spec_path)
    source_list_path = project_root / _safe_relative(
        spec["input_source_list"], "input source list"
    )
    if _sha256_file(source_list_path) != spec["input_source_list_sha256"]:
        raise Stage1ScreeningError("source-list hash differs from frozen spec")
    source_list = _mapping(_load_json(source_list_path), "source list")
    candidates = source_list.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise Stage1ScreeningError("source list has no candidates")
    positions = [
        candidate.get("position")
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    if positions != list(range(1, len(candidates) + 1)):
        raise Stage1ScreeningError("source-list positions are not contiguous and ordered")
    candidate_ids = [
        candidate.get("candidate_id")
        for candidate in candidates
        if isinstance(candidate, Mapping)
    ]
    if candidate_ids != spec["expected_candidate_ids"]:
        raise Stage1ScreeningError(
            "source-list candidate order differs from frozen inspection spec"
        )
    output_directory.parent.mkdir(parents=True, exist_ok=True)
    scratch_parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="cmvp-stage1-clones-", dir=scratch_parent
    ) as scratch_value, tempfile.TemporaryDirectory(
        prefix=f".{output_directory.name}.stage-", dir=output_directory.parent
    ) as staged_value:
        scratch_root = Path(scratch_value)
        staged_root = Path(staged_value)
        results: list[dict[str, Any]] = []
        artifacts: list[dict[str, str]] = []
        for raw_candidate in candidates:
            candidate = _mapping(raw_candidate, "candidate")
            candidate_id = _string(candidate.get("candidate_id"), "candidate_id")
            relative = f"candidates/{candidate_id}.json"
            result = _inspect_candidate(
                candidate=candidate,
                spec=spec,
                scratch_root=scratch_root,
                method_commit=method_commit,
                result_path=(output_directory / relative).relative_to(project_root).as_posix(),
            )
            target = staged_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(_canonical_bytes(result))
            artifacts.append({"path": relative, "sha256": _sha256_file(target)})
            results.append(result)
        summary = _build_summary(
            results, source_list_id=source_list.get("source_list_id")
        )
        summary_path = staged_root / "summary.json"
        summary_path.write_bytes(_canonical_bytes(summary))
        artifacts.append({"path": "summary.json", "sha256": _sha256_file(summary_path)})
        manifest = {
            "schema": BATCH_SCHEMA,
            "protocol_version": PROTOCOL_VERSION,
            "source_list_id": source_list.get("source_list_id"),
            "source_list_sha256": _sha256_file(source_list_path),
            "inspection_spec": {
                "path": spec_path.relative_to(project_root).as_posix(),
                "sha256": _sha256_file(spec_path),
            },
            "screening_protocol": {
                "path": str(spec["screening_protocol"]),
                "sha256": _sha256_file(project_root / str(spec["screening_protocol"])),
            },
            "result_schema": {
                "path": "benchmark-selection/stage1/v0.1/result.schema.json",
                "sha256": _sha256_file(
                    project_root / "benchmark-selection/stage1/v0.1/result.schema.json"
                ),
            },
            "method_commit": method_commit,
            "started_at_utc": results[0]["inspection"]["started_at_utc"],
            "completed_at_utc": results[-1]["inspection"]["completed_at_utc"],
            "candidate_count": len(results),
            "candidate_order": [result["candidate_id"] for result in results],
            "artifacts": sorted(artifacts, key=lambda item: item["path"]),
            "temporary_clones_removed": True,
            "candidate_code_executed": False,
            "installation_executed": False,
            "tests_executed": False,
            "ranked_or_selected": False,
            "treatment_results_consulted": False,
        }
        (staged_root / "screening-manifest.json").write_bytes(
            _canonical_bytes(manifest)
        )
        Path(staged_value).rename(output_directory)
    return manifest


def _validate_result(
    result: Mapping[str, Any], *, candidate_id: str, method_commit: str
) -> None:
    if result.get("schema") != RESULT_SCHEMA:
        raise Stage1ScreeningError(f"unexpected result schema for {candidate_id}")
    if result.get("protocol_version") != PROTOCOL_VERSION:
        raise Stage1ScreeningError(f"wrong result protocol for {candidate_id}")
    if result.get("candidate_id") != candidate_id:
        raise Stage1ScreeningError(f"result identity mismatch for {candidate_id}")
    if any(
        result.get(key) is not False
        for key in (
            "trust_family_assigned",
            "p_star_decided",
            "references_constructed",
            "ranked_or_selected",
            "treatment_results_consulted",
        )
    ):
        raise Stage1ScreeningError(f"scope certification failed for {candidate_id}")
    inspection = _mapping(result.get("inspection"), f"{candidate_id}.inspection")
    if inspection.get("method_commit") != method_commit:
        raise Stage1ScreeningError(f"method commit mismatch for {candidate_id}")
    if any(
        inspection.get(key) is not False
        for key in (
            "candidate_code_executed",
            "checkout_created",
            "installation_executed",
            "tests_executed",
            "model_or_treatment_accessed",
        )
    ) or inspection.get("temporary_clone_removed_after_batch") is not True:
        raise Stage1ScreeningError(f"execution boundary failed for {candidate_id}")
    _safe_relative(inspection.get("result_path"), f"{candidate_id}.result_path")
    repository = _mapping(result.get("repository"), f"{candidate_id}.repository")
    repository_url = _string(repository.get("url"), f"{candidate_id}.url")
    clone_url = (
        repository_url if repository_url.endswith(".git") else f"{repository_url}.git"
    )
    expected_commit = _string(
        repository.get("expected_commit"), f"{candidate_id}.expected_commit"
    )
    commands = inspection.get("commands")
    if not isinstance(commands, list) or len(commands) != 2:
        raise Stage1ScreeningError(f"unexpected command count for {candidate_id}")
    command_arguments = [
        _mapping(command, f"{candidate_id}.command").get("arguments")
        for command in commands
    ]
    if (
        not isinstance(command_arguments[0], list)
        or len(command_arguments[0]) != 4
        or command_arguments[0][:3] != ["git", "init", "--bare"]
        or not str(command_arguments[0][3]).endswith(f"/{candidate_id}.git")
    ):
        raise Stage1ScreeningError(f"unexpected Git command for {candidate_id}")
    expected_fetch = [
        "git",
        f"--git-dir={command_arguments[0][3]}",
        "fetch",
        "--depth=1",
        "--no-tags",
        clone_url,
        expected_commit,
    ]
    if (
        not isinstance(command_arguments[1], list)
        or command_arguments[1] != expected_fetch
    ):
        raise Stage1ScreeningError(f"unexpected Git command for {candidate_id}")
    facts = _mapping(result.get("facts"), f"{candidate_id}.facts")
    expected_fact_keys = {
        "license",
        "frozen_commit_resolution",
        "language_runtime_metadata",
        "static_text_scan",
        "repository_size",
        "tests",
        "package_build_metadata",
        "setup_command_candidates",
        "external_service_requirements",
        "gpu_requirement",
        "database_requirement",
        "network_requirement",
        "proprietary_dependency_requirement",
        "clean_installation",
    }
    if set(facts) != expected_fact_keys:
        raise Stage1ScreeningError(f"objective fact inventory changed for {candidate_id}")
    gates = _mapping(result.get("automatic_gates"), f"{candidate_id}.gates")
    if set(gates) != set(AUTOMATIC_GATES):
        raise Stage1ScreeningError(f"automatic gate inventory changed for {candidate_id}")
    statuses: set[str] = set()
    for gate in AUTOMATIC_GATES:
        gate_result = _mapping(gates.get(gate), f"{candidate_id}.{gate}")
        status = gate_result.get("status")
        if status not in {"PASS", "FAIL", "NEEDS_REVIEW"}:
            raise Stage1ScreeningError(f"invalid gate status for {candidate_id}: {gate}")
        if not isinstance(gate_result.get("reason"), str) or not gate_result["reason"]:
            raise Stage1ScreeningError(f"missing gate reason for {candidate_id}: {gate}")
        statuses.add(str(status))
    licence = _mapping(facts.get("license"), f"{candidate_id}.license")
    captured_spdx = licence.get("captured_spdx")
    licence_files = licence.get("license_files")
    licence_static_pass = (
        isinstance(captured_spdx, str)
        and captured_spdx not in {"", "NOASSERTION", "OTHER", "None"}
        and isinstance(licence_files, list)
        and bool(licence_files)
    )
    expected_licence_status = "PASS" if licence_static_pass else "NEEDS_REVIEW"
    if gates["usable_licence"]["status"] != expected_licence_status:
        raise Stage1ScreeningError(f"licence gate/fact mismatch for {candidate_id}")
    resolution = _mapping(
        facts.get("frozen_commit_resolution"), f"{candidate_id}.commit resolution"
    )
    exact_resolution = (
        resolution.get("fetch_succeeded") is True
        and resolution.get("expected_commit") == expected_commit
        and resolution.get("resolved_commit") == expected_commit
        and resolution.get("expected_git_tree_sha")
        == repository.get("captured_git_tree_sha")
        and resolution.get("resolved_git_tree_sha")
        == repository.get("captured_git_tree_sha")
    )
    expected_immutable_status = (
        "NEEDS_REVIEW"
        if resolution.get("fetch_succeeded") is not True
        or resolution.get("resolved_commit") is None
        or resolution.get("resolved_git_tree_sha") is None
        else "PASS"
        if exact_resolution
        else "FAIL"
    )
    if gates["immutable_commit"]["status"] != expected_immutable_status:
        raise Stage1ScreeningError(f"immutable gate/fact mismatch for {candidate_id}")
    if any(
        gates[gate]["status"] != "NEEDS_REVIEW" for gate in AUTOMATIC_GATES[2:]
    ):
        raise Stage1ScreeningError(
            f"static-only gate was decided for {candidate_id}"
        )
    expected_state = (
        "EXCLUDED"
        if "FAIL" in statuses
        else "AUTOMATIC_GATES_PASSED"
        if statuses == {"PASS"}
        else "DISCOVERED"
    )
    if result.get("resulting_state") != expected_state:
        raise Stage1ScreeningError(f"gate/state mismatch for {candidate_id}")


def _load_results(
    output_directory: Path,
) -> tuple[Mapping[str, Any], list[Mapping[str, Any]]]:
    manifest = _mapping(
        _load_json(output_directory / "screening-manifest.json"),
        "screening manifest",
    )
    if (
        manifest.get("schema") != BATCH_SCHEMA
        or manifest.get("protocol_version") != PROTOCOL_VERSION
    ):
        raise Stage1ScreeningError("unexpected screening manifest schema")
    if any(
        manifest.get(key) is not False
        for key in (
            "candidate_code_executed",
            "installation_executed",
            "tests_executed",
            "ranked_or_selected",
            "treatment_results_consulted",
        )
    ) or manifest.get("temporary_clones_removed") is not True:
        raise Stage1ScreeningError("screening manifest execution boundary failed")
    method_commit = str(manifest.get("method_commit", ""))
    if COMMIT.fullmatch(method_commit) is None:
        raise Stage1ScreeningError("screening manifest method commit is invalid")
    candidate_order = manifest.get("candidate_order")
    if (
        not isinstance(candidate_order, list)
        or any(not isinstance(value, str) for value in candidate_order)
        or len(candidate_order) != len(set(candidate_order))
        or manifest.get("candidate_count") != len(candidate_order)
    ):
        raise Stage1ScreeningError("screening manifest candidate order is malformed")
    artifacts = manifest.get("artifacts")
    if not isinstance(artifacts, list):
        raise Stage1ScreeningError("screening manifest artifacts must be an array")
    expected_artifact_paths = {"summary.json"} | {
        f"candidates/{candidate_id}.json" for candidate_id in candidate_order
    }
    artifact_paths = [
        str(_mapping(artifact, "screening artifact").get("path"))
        for artifact in artifacts
    ]
    if set(artifact_paths) != expected_artifact_paths or len(artifact_paths) != len(
        expected_artifact_paths
    ):
        raise Stage1ScreeningError("screening manifest artifact inventory mismatch")
    for raw_artifact in artifacts:
        artifact = _mapping(raw_artifact, "screening artifact")
        path = _safe_relative(artifact.get("path"), "screening artifact path")
        if SHA256.fullmatch(str(artifact.get("sha256", ""))) is None:
            raise Stage1ScreeningError(f"invalid screening artifact hash: {path}")
        if _sha256_file(output_directory / path) != artifact.get("sha256"):
            raise Stage1ScreeningError(f"screening artifact hash mismatch: {path}")
    actual_paths = {
        path.relative_to(output_directory).as_posix()
        for path in output_directory.rglob("*")
        if path.is_file()
    }
    if actual_paths != expected_artifact_paths | {"screening-manifest.json"}:
        raise Stage1ScreeningError("screening output file inventory mismatch")
    results = [
        _mapping(
            _load_json(output_directory / f"candidates/{candidate_id}.json"),
            candidate_id,
        )
        for candidate_id in candidate_order
    ]
    for candidate_id, result in zip(candidate_order, results, strict=True):
        _validate_result(
            result, candidate_id=candidate_id, method_commit=method_commit
        )
    summary = _mapping(_load_json(output_directory / "summary.json"), "summary")
    if summary != _build_summary(
        results, source_list_id=manifest.get("source_list_id")
    ):
        raise Stage1ScreeningError("screening summary differs from candidate results")
    return manifest, results


def apply_results_to_ledger(
    *,
    project_root: Path,
    output_directory: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    """Attach Stage-1 gate evidence and append only actual state transitions."""

    manifest, results = _load_results(output_directory)
    records = [
        json.loads(line)
        for line in ledger_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_id = {record.get("candidate_id"): record for record in records}
    if len(by_id) != len(records):
        raise Stage1ScreeningError("ledger has duplicate candidate IDs")
    transitions: list[dict[str, str]] = []
    result_hashes = {
        artifact["path"].split("/")[-1].removesuffix(".json"): artifact["sha256"]
        for artifact in manifest["artifacts"]
        if artifact["path"].startswith("candidates/")
    }
    for result in results:
        candidate_id = str(result["candidate_id"])
        record = by_id.get(candidate_id)
        if not isinstance(record, dict):
            raise Stage1ScreeningError(f"ledger lacks {candidate_id}")
        if record.get("current_state") != "DISCOVERED":
            raise Stage1ScreeningError(f"{candidate_id} is no longer DISCOVERED")
        if "stage1_screening" in record:
            raise Stage1ScreeningError(f"{candidate_id} already has Stage-1 evidence")
        relative_result = Path(str(result["inspection"]["result_path"]))
        evidence = {
            "path": relative_result.as_posix(),
            "sha256": result_hashes[candidate_id],
        }
        record["stage1_screening"] = evidence
        for gate in AUTOMATIC_GATES:
            record["hard_gates"][gate] = {
                "status": result["automatic_gates"][gate]["status"],
                "evidence": [evidence],
            }
        expected_state = result["resulting_state"]
        if expected_state == "DISCOVERED":
            transitions.append(
                {"candidate_id": candidate_id, "from": "DISCOVERED", "to": "DISCOVERED"}
            )
            continue
        event = {
            "sequence": len(record["status_history"]) + 1,
            "state": expected_state,
            "recorded_at_utc": result["inspection"]["completed_at_utc"],
            "actor_id": "cmvp-stage1-static-inspector-v0.1",
            "protocol_version": PROTOCOL_VERSION,
            "rationale": (
                "All automatic feasibility gates passed"
                if expected_state == "AUTOMATIC_GATES_PASSED"
                else "Static Stage-1 inspection found an exact automatic hard-gate failure"
            ),
            "evidence": [evidence],
        }
        record["status_history"].append(event)
        record["current_state"] = expected_state
        if expected_state == "EXCLUDED":
            failed = [
                gate
                for gate in AUTOMATIC_GATES
                if result["automatic_gates"][gate]["status"] == "FAIL"
            ]
            primary = failed[0]
            record["exclusion"] = {
                "code": EXCLUSION_CODES[primary],
                "stage": "AUTOMATIC_GATE",
                "explanation": f"Failed automatic gates: {', '.join(failed)}",
                "recorded_at_utc": result["inspection"]["completed_at_utc"],
                "evidence": [evidence],
            }
        transitions.append(
            {"candidate_id": candidate_id, "from": "DISCOVERED", "to": expected_state}
        )
    temporary = ledger_path.with_suffix(".jsonl.stage1.tmp")
    temporary.write_bytes(
        b"".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")).encode("utf-8")
            + b"\n"
            for record in records
        )
    )
    temporary.replace(ledger_path)
    return {
        "schema": "stage1-ledger-application-v0.1",
        "candidate_count": len(results),
        "transitions": transitions,
        "treatment_results_consulted": False,
    }


def verify_screening(
    *,
    project_root: Path,
    spec_path: Path,
    output_directory: Path,
    ledger_path: Path,
) -> dict[str, Any]:
    """Verify frozen inputs, result hashes, scope limits, and ledger links."""

    spec = load_spec(spec_path)
    source_list_path = project_root / str(spec["input_source_list"])
    if _sha256_file(source_list_path) != spec["input_source_list_sha256"]:
        raise Stage1ScreeningError("source-list hash changed")
    source_list = _mapping(_load_json(source_list_path), "source list")
    manifest, results = _load_results(output_directory)
    if (
        manifest.get("source_list_id") != source_list.get("source_list_id")
        or manifest.get("source_list_sha256") != spec["input_source_list_sha256"]
        or manifest.get("inspection_spec")
        != {
            "path": spec_path.relative_to(project_root).as_posix(),
            "sha256": _sha256_file(spec_path),
        }
        or manifest.get("screening_protocol")
        != {
            "path": spec["screening_protocol"],
            "sha256": _sha256_file(project_root / str(spec["screening_protocol"])),
        }
        or manifest.get("result_schema")
        != {
            "path": "benchmark-selection/stage1/v0.1/result.schema.json",
            "sha256": _sha256_file(
                project_root
                / "benchmark-selection/stage1/v0.1/result.schema.json"
            ),
        }
    ):
        raise Stage1ScreeningError("screening manifest frozen-input mismatch")
    source_ids = [item["candidate_id"] for item in source_list["candidates"]]
    result_ids = [result["candidate_id"] for result in results]
    if source_ids != result_ids or manifest.get("candidate_order") != source_ids:
        raise Stage1ScreeningError("results do not cover source candidates in order")
    ledger = {
        record["candidate_id"]: record
        for record in (
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }
    transitions: list[dict[str, str]] = []
    exclusions: list[dict[str, str]] = []
    ambiguities: dict[str, list[str]] = {}
    source_by_id = {
        item["candidate_id"]: item for item in source_list["candidates"]
    }
    result_hashes = {
        str(artifact["path"]).split("/")[-1].removesuffix(".json"): artifact[
            "sha256"
        ]
        for artifact in manifest["artifacts"]
        if str(artifact["path"]).startswith("candidates/")
    }
    for result in results:
        candidate_id = str(result["candidate_id"])
        source = _mapping(source_by_id[candidate_id], f"source {candidate_id}")
        source_record = _mapping(source.get("source"), "source")
        snapshot = _mapping(source_record.get("snapshot"), "source snapshot")
        normalized = _mapping(source.get("normalized_metadata"), "metadata")
        commit_metadata = _mapping(normalized.get("commit"), "commit metadata")
        repository_metadata = _mapping(
            normalized.get("repository"), "repository metadata"
        )
        result_repository = _mapping(result.get("repository"), "result repository")
        if (
            result_repository.get("full_name")
            != repository_metadata.get("full_name")
            or result_repository.get("url") != source_record.get("repository_url")
            or result_repository.get("captured_language")
            != repository_metadata.get("language")
            or result_repository.get("captured_license_spdx")
            != repository_metadata.get("license_spdx")
            or result_repository.get("expected_commit") != snapshot.get("commit_sha")
            or result_repository.get("captured_git_tree_sha")
            != commit_metadata.get("tree_sha")
            or result_repository.get("default_branch")
            != repository_metadata.get("default_branch")
            or result["inspection"]["result_path"]
            != (
                output_directory / f"candidates/{candidate_id}.json"
            ).relative_to(project_root).as_posix()
        ):
            raise Stage1ScreeningError(f"source/result mismatch for {candidate_id}")
        record = _mapping(ledger.get(candidate_id), f"ledger {candidate_id}")
        evidence = _mapping(record.get("stage1_screening"), "stage1 evidence")
        evidence_path = project_root / _safe_relative(evidence.get("path"), "evidence path")
        if (
            evidence.get("path") != result["inspection"]["result_path"]
            or evidence.get("sha256") != result_hashes[candidate_id]
            or _sha256_file(evidence_path) != evidence.get("sha256")
        ):
            raise Stage1ScreeningError(f"ledger Stage-1 hash mismatch for {candidate_id}")
        for gate in AUTOMATIC_GATES:
            if record["hard_gates"][gate] != {
                "status": result["automatic_gates"][gate]["status"],
                "evidence": [dict(evidence)],
            }:
                raise Stage1ScreeningError(f"ledger gate mismatch for {candidate_id}: {gate}")
        for gate in MECHANISM_GATES:
            if record["hard_gates"][gate]["status"] != "NOT_ASSESSED":
                raise Stage1ScreeningError(f"mechanism gate was assessed for {candidate_id}")
        if record.get("trust_family") is not None or record.get("mechanism_key") is not None:
            raise Stage1ScreeningError(f"mechanism was assigned for {candidate_id}")
        if record.get("current_state") != result.get("resulting_state"):
            raise Stage1ScreeningError(f"ledger state mismatch for {candidate_id}")
        transitions.append(
            {"candidate_id": candidate_id, "from": "DISCOVERED", "to": str(record["current_state"])}
        )
        if record["current_state"] == "EXCLUDED":
            exclusion = _mapping(record.get("exclusion"), "exclusion")
            exclusions.append(
                {"candidate_id": candidate_id, "code": str(exclusion.get("code"))}
            )
        ambiguities[candidate_id] = [
            gate
            for gate in AUTOMATIC_GATES
            if result["automatic_gates"][gate]["status"] == "NEEDS_REVIEW"
        ]
    return {
        "schema": VERIFICATION_SCHEMA,
        "pass": True,
        "source_list_id": source_list.get("source_list_id"),
        "candidate_count": len(results),
        "transitions": transitions,
        "exclusions": exclusions,
        "ambiguities": ambiguities,
        "candidate_code_executed": False,
        "installation_executed": False,
        "tests_executed": False,
        "ranked_or_selected": False,
        "treatment_results_consulted": False,
    }
