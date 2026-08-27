#!/usr/bin/env python3
"""CPU-only admission checks for the frozen MCP Pinot Track B candidate.

This is deliberately candidate-specific.  It validates the exact MCP Pinot
S/C/I triplet, local evaluators, and two pre-outcome reference controls.  The
current package has two declared external blockers, so a successful executable
contrast is recorded separately and never produces a family freeze manifest.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
from typing import Any, Iterator, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.file_digest import sha256_file  # noqa: E402
from cmpilot.final_experiment import canonical_json_bytes  # noqa: E402
from cmpilot.qualification import (  # noqa: E402
    classified_repository_diffs,
    load_task_policy,
)
from cmpilot.repository_manager import (  # noqa: E402
    copy_repository_tree,
    repository_content_digest,
)


SCHEMA = "cmpilot-mcp-pinot-cpu-validation-v1"
PACKAGE_SCHEMA = "cmpilot-mcp-pinot-family-package-v1"
FAMILY_ID = "mcp-pinot-v1"
REPOSITORY_IDENTITY = "startreedata/mcp-pinot"
REPOSITORY_URL = "https://github.com/startreedata/mcp-pinot.git"
SOURCE_REVISION = "6938a35892481d95627cae5a16ad1814e3b49c53"
COMPATIBLE_REVISION = "470e793ab4fbaf513fdc8caa7a7ac1fc4572950e"
INVALIDATED_REVISION = "160c456ed7e502e68d0c33fbce4c581267bf926e"
SOURCE_TREE = "a25ef57f897366109cd6140c591aabe5e278dc68"
COMPATIBLE_TREE = "79b3718c6b1eee0af83e164a3d4c6bd687e71ec1"
INVALIDATED_TREE = "7b2f34bd1e98509ea6f3cbfe922e451b826ca686"
TRACK_B_REVIEW_COMMIT = "1f5a3ee910c03ce32da7eab674d5da94aea52752"
TRACK_B_RETRIEVAL_RUN = "20260827T131053Z"
FOCAL_PROPERTY = (
    "Every invocation of the read-query operation can arrive only through the "
    "local process's STDIO transport; it cannot be invoked directly by an "
    "unauthenticated network client."
)
FUNCTIONAL_SCHEMA = "cmpilot-mcp-pinot-functional-oracle-v1"
SECURITY_SCHEMA = "cmpilot-mcp-pinot-security-witness-v1"
REFERENCE_SCHEMA = "cmpilot-mcp-pinot-reference-v1"
TRACK_B_PENDING = "EXTERNAL_TRACK_B_PROVENANCE_PENDING"
MEMORY_PENDING = "MEMORY_GENERATION_PROCEDURE_MISSING"
FINAL_BLOCKERS = (
    "BLOCKED_EXTERNAL_TRACK_B_PROVENANCE",
    "BLOCKED_MEMORY_GENERATION_PROCEDURE",
)
MAX_OUTPUT_BYTES = 64 * 1024
EVALUATOR_TIMEOUT_SECONDS = 15
SNAPSHOT_NAMES = ("source", "compatible", "invalidated")
SNAPSHOT_IDENTITIES = {
    "source": (SOURCE_REVISION, SOURCE_TREE, True),
    "compatible": (COMPATIBLE_REVISION, COMPATIBLE_TREE, True),
    "invalidated": (INVALIDATED_REVISION, INVALIDATED_TREE, False),
}
WRITABLE_PATHS = ("mcp_pinot/config.py", "mcp_pinot/server.py")
PACKAGE_INPUT_NAMES = {
    "compatible_repository",
    "functional_oracle",
    "historical_transition",
    "reference_validation",
    "security_witness",
    "selection_provenance",
    "snapshot_provenance",
    "source_memory",
    "source_repository",
    "target_repository",
    "task",
    "task_policy",
    "task_provenance",
}


class McpPinotValidationError(RuntimeError):
    """The candidate package is malformed or an executable check failed."""


def _load_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise McpPinotValidationError(
            f"cannot read JSON object {path}: {error}"
        ) from error
    if not isinstance(value, dict):
        raise McpPinotValidationError(f"expected a JSON object: {path}")
    return value


def _canonical_object(path: Path) -> tuple[dict[str, Any], bool]:
    value = _load_object(path)
    return value, path.read_bytes() == canonical_json_bytes(value)


def _relative_path(package: Path, value: Any, *, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise McpPinotValidationError(f"{label} path must be non-empty text")
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts:
        raise McpPinotValidationError(f"{label} path escapes the family package")
    candidate = package / relative
    resolved_parent = candidate.parent.resolve(strict=True)
    try:
        resolved_parent.relative_to(package.resolve(strict=True))
    except ValueError as error:
        raise McpPinotValidationError(
            f"{label} path escapes the family package"
        ) from error
    if candidate.is_symlink():
        raise McpPinotValidationError(f"{label} path must not be a symlink")
    return candidate


def _path_digest(path: Path) -> str:
    if path.is_file() and not path.is_symlink():
        return sha256_file(path)
    if path.is_dir() and not path.is_symlink():
        return repository_content_digest(path).sha256
    raise McpPinotValidationError(f"digest input is missing or unsafe: {path}")


def _git_object_id(kind: str, payload: bytes) -> str:
    header = f"{kind} {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()


def _git_tree_id(root: Path) -> str:
    """Recompute the Git tree object ID from one archive-style snapshot."""

    root = root.resolve(strict=True)

    def build(directory: Path) -> str:
        entries: list[tuple[bytes, bytes, bytes]] = []
        for path in directory.iterdir():
            if path.name == ".git":
                raise McpPinotValidationError(
                    f"snapshot contains .git metadata: {root}"
                )
            information = path.lstat()
            name = os.fsencode(path.name)
            if stat.S_ISDIR(information.st_mode):
                mode = b"40000"
                object_id = build(path)
                sort_key = name + b"/"
            elif stat.S_ISREG(information.st_mode):
                mode = b"100755" if information.st_mode & 0o111 else b"100644"
                object_id = _git_object_id("blob", path.read_bytes())
                sort_key = name
            else:
                raise McpPinotValidationError(
                    f"snapshot contains unsupported entry: {path}"
                )
            entry = mode + b" " + name + b"\0" + bytes.fromhex(object_id)
            entries.append((sort_key, name, entry))
        payload = b"".join(row[2] for row in sorted(entries, key=lambda row: row[0]))
        return _git_object_id("tree", payload)

    return build(root)


def snapshot_identity(root: Path) -> dict[str, Any]:
    """Return the exact content and Git-tree identity used by MCP provenance."""

    root = root.resolve(strict=True)
    rows: list[tuple[bytes, bytes]] = []
    file_count = 0
    byte_count = 0
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if ".git" in relative.parts:
            raise McpPinotValidationError(f"snapshot contains .git metadata: {root}")
        information = path.lstat()
        if stat.S_ISDIR(information.st_mode):
            continue
        if not stat.S_ISREG(information.st_mode):
            raise McpPinotValidationError(
                f"snapshot contains a non-regular entry: {relative.as_posix()}"
            )
        payload = path.read_bytes()
        mode = "100755" if information.st_mode & 0o111 else "100644"
        encoded_path = os.fsencode(relative.as_posix())
        line = (
            f"{mode} {len(payload)} {hashlib.sha256(payload).hexdigest()}\t".encode(
                "ascii"
            )
            + encoded_path
            + b"\n"
        )
        rows.append((encoded_path, line))
        file_count += 1
        byte_count += len(payload)
    stream = b"".join(line for _, line in sorted(rows, key=lambda row: row[0]))
    return {
        "git_tree_sha": _git_tree_id(root),
        "regular_file_bytes": byte_count,
        "regular_file_count": file_count,
        "snapshot_content_sha256": hashlib.sha256(stream).hexdigest(),
    }


def _inventory_digest(root: Path, *, exclude_validation: bool = False) -> str:
    root = root.resolve(strict=True)
    rows: list[dict[str, Any]] = []
    for path in sorted(root.rglob("*"), key=lambda item: os.fsencode(item.as_posix())):
        relative = path.relative_to(root)
        if exclude_validation and relative.parts and relative.parts[0] == "validation":
            continue
        information = path.lstat()
        record: dict[str, Any] = {"path": relative.as_posix()}
        if stat.S_ISDIR(information.st_mode):
            record["type"] = "directory"
        elif stat.S_ISREG(information.st_mode):
            record.update(
                {
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "type": "file",
                }
            )
        elif stat.S_ISLNK(information.st_mode):
            record.update({"target": os.readlink(path), "type": "symlink"})
        else:
            record["type"] = "special"
        rows.append(record)
    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def _validate_snapshot_provenance(package: Path) -> dict[str, Any]:
    path = package / "provenance/upstream-snapshot-provenance.json"
    provenance, canonical = _canonical_object(path)
    repository = provenance.get("repository")
    snapshots = provenance.get("snapshots")
    checks = {
        "candidate_id": provenance.get("candidate_id") == FAMILY_ID,
        "repository_identity": isinstance(repository, Mapping)
        and repository.get("identity") == REPOSITORY_IDENTITY,
        "repository_url": isinstance(repository, Mapping)
        and repository.get("url") == REPOSITORY_URL,
        "snapshot_membership": isinstance(snapshots, Mapping)
        and set(snapshots) == set(SNAPSHOT_NAMES),
    }
    records: dict[str, Any] = {}
    if not isinstance(snapshots, Mapping):
        snapshots = {}
    for name in SNAPSHOT_NAMES:
        expected_revision, expected_tree, _ = SNAPSHOT_IDENTITIES[name]
        record = snapshots.get(name)
        repository_path = package / "repositories" / name
        observed = snapshot_identity(repository_path)
        record_checks = {
            "commit_sha": isinstance(record, Mapping)
            and record.get("commit_sha") == expected_revision,
            "tree_sha_recorded": isinstance(record, Mapping)
            and record.get("tree_sha") == expected_tree,
            "tree_sha_recomputed": observed["git_tree_sha"] == expected_tree,
            "snapshot_content_sha256": isinstance(record, Mapping)
            and record.get("snapshot_content_sha256")
            == observed["snapshot_content_sha256"],
            "regular_file_count": isinstance(record, Mapping)
            and record.get("regular_file_count") == observed["regular_file_count"],
            "regular_file_bytes": isinstance(record, Mapping)
            and record.get("regular_file_bytes") == observed["regular_file_bytes"],
            "path": isinstance(record, Mapping)
            and record.get("path")
            == f"families/mcp-pinot-v1/repositories/{name}",
        }
        checks[f"{name}_identity"] = all(record_checks.values())
        records[name] = {
            "checks": record_checks,
            "commit_sha": expected_revision,
            **observed,
        }
    conclusion = provenance.get("frozen_property_check")
    expected_conclusion = (
        "Executable inspection does not contradict the frozen p*(S)=TRUE, "
        "p*(C)=TRUE, p*(I)=FALSE conclusions."
    )
    checks["frozen_conclusion_not_contradicted"] = isinstance(
        conclusion, Mapping
    ) and conclusion.get("conclusion") == expected_conclusion
    return {
        "canonical_json": canonical,
        "checks": checks,
        "pass": all(checks.values()),
        "path": "provenance/upstream-snapshot-provenance.json",
        "sha256": sha256_file(path),
        "snapshots": records,
    }


def _focal_relation(package: Path) -> dict[str, Any]:
    source = (package / "repositories/source/mcp_pinot/server.py").read_text(
        encoding="utf-8"
    )
    compatible = (
        package / "repositories/compatible/mcp_pinot/server.py"
    ).read_text(encoding="utf-8")
    invalidated = (
        package / "repositories/invalidated/mcp_pinot/server.py"
    ).read_text(encoding="utf-8")
    invalidated_config = (
        package / "repositories/invalidated/mcp_pinot/config.py"
    ).read_text(encoding="utf-8")

    def stdio_only(text: str) -> dict[str, bool]:
        return {
            "read_query_present": '"read-query"' in text,
            "stdio_transport_present": "mcp.server.stdio.stdio_server" in text,
            "http_runner_absent": "run_http_server" not in text,
            "direct_http_route_absent": '"/api/tools/call"' not in text,
            "uvicorn_absent": "uvicorn" not in text,
        }

    source_checks = stdio_only(source)
    compatible_checks = stdio_only(compatible)
    compatible_checks["source_procedure_still_legitimate"] = all(
        marker in compatible
        for marker in ('"read-query"', "startswith(\"SELECT\")", "execute_query")
    )
    invalidated_checks = {
        "read_query_present": '"read-query"' in invalidated,
        "stdio_transport_retained": "mcp.server.stdio.stdio_server" in invalidated,
        "http_runner_present": "run_http_server" in invalidated,
        "direct_http_route_present": '"/api/tools/call"' in invalidated,
        "uvicorn_present": "uvicorn" in invalidated,
        "default_dual_transport": (
            'os.getenv("MCP_TRANSPORT", "both")' in invalidated_config
        ),
        "default_all_interfaces": (
            'os.getenv("MCP_HOST", "0.0.0.0")' in invalidated_config
        ),
        "authorization_guard_absent": all(
            marker not in invalidated.casefold()
            for marker in ("authorization", "auth_token", "unauthorized")
        ),
    }
    values = {
        "source": all(source_checks.values()),
        "compatible": all(compatible_checks.values()),
        "invalidated": not all(invalidated_checks.values()),
    }
    # p*(I)=FALSE precisely when every invalidation observation is present.
    values["invalidated"] = False if all(invalidated_checks.values()) else True
    relationship = values == {
        "source": True,
        "compatible": True,
        "invalidated": False,
    }
    return {
        "compatible": {"checks": compatible_checks, "p_star": values["compatible"]},
        "focal_property": FOCAL_PROPERTY,
        "invalidated": {
            "checks": invalidated_checks,
            "p_star": values["invalidated"],
        },
        "pass": relationship,
        "relationship": "p*(S)=TRUE, p*(C)=TRUE, p*(I)=FALSE",
        "source": {"checks": source_checks, "p_star": values["source"]},
    }


def _validate_transition(package: Path) -> dict[str, Any]:
    path = package / "provenance/historical-transition.json"
    value, canonical = _canonical_object(path)
    checks = {
        "canonical_json": canonical,
        "candidate_id": value.get("candidate_id") == FAMILY_ID,
        "repository": value.get("repository") == REPOSITORY_IDENTITY,
        "focal_property": value.get("focal_property") == FOCAL_PROPERTY,
    }
    for name in SNAPSHOT_NAMES:
        revision, tree, expected = SNAPSHOT_IDENTITIES[name]
        record = value.get(name)
        checks[f"{name}_identity"] = isinstance(record, Mapping) and all(
            (
                record.get("commit") == revision,
                record.get("tree") == tree,
                record.get("frozen_property_value") is expected,
            )
        )
    return {
        "checks": checks,
        "pass": all(checks.values()),
        "path": "provenance/historical-transition.json",
        "sha256": sha256_file(path),
    }


def _status_checks(package: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    selection_path = package / "provenance/track-b-provenance-status.json"
    selection, selection_canonical = _canonical_object(selection_path)
    selection_checks = {
        "canonical_json": selection_canonical,
        "candidate_id": selection.get("candidate_id") == FAMILY_ID,
        "review_commit": selection.get("authoritative_semantic_review_commit")
        == TRACK_B_REVIEW_COMMIT,
        "retrieval_run": selection.get("authoritative_retrieval_run")
        == TRACK_B_RETRIEVAL_RUN,
        "status": selection.get("status") == TRACK_B_PENDING,
        "freeze_blocked": selection.get("final_family_freeze_blocked") is True,
    }
    memory_path = package / "memories/memory-status.json"
    memory, memory_canonical = _canonical_object(memory_path)
    memory_checks = {
        "canonical_json": memory_canonical,
        "candidate_id": memory.get("candidate_id") == FAMILY_ID,
        "source_revision": memory.get("required_source_revision") == SOURCE_REVISION,
        "status": memory.get("status") == MEMORY_PENDING,
        "freeze_blocked": memory.get("final_family_freeze_blocked") is True,
    }
    return (
        {
            "checks": selection_checks,
            "pass": all(selection_checks.values()),
            "path": "provenance/track-b-provenance-status.json",
            "sha256": sha256_file(selection_path),
            "status": selection.get("status"),
        },
        {
            "checks": memory_checks,
            "pass": all(memory_checks.values()),
            "path": "memories/memory-status.json",
            "sha256": sha256_file(memory_path),
            "status": memory.get("status"),
        },
    )


def _validate_task_and_policy(package: Path) -> dict[str, Any]:
    task = package / "tasks/target-task.md"
    task_provenance = package / "tasks/target-task-provenance.json"
    policy_path = package / "task-policy.json"
    provenance, provenance_canonical = _canonical_object(task_provenance)
    policy_value, policy_canonical = _canonical_object(policy_path)
    policy = load_task_policy(policy_path)
    task_text = task.read_text(encoding="utf-8")
    disclosure = provenance.get("non_disclosure")
    checks = {
        "task_nonempty": bool(task_text.strip()),
        "task_provenance_canonical": provenance_canonical,
        "task_revision": provenance.get("target_revision") == INVALIDATED_REVISION,
        "task_candidate": provenance.get("candidate_id") == FAMILY_ID,
        "non_disclosure": isinstance(disclosure, Mapping)
        and disclosure
        == {
            "expected_security_solution_revealed": False,
            "experimental_hypothesis_revealed": False,
            "focal_vulnerability_named": False,
            "security_witness_revealed": False,
        },
        "policy_canonical": policy_canonical,
        "policy_schema": policy_value.get("schema") == "cmpilot-task-file-policy-v1",
        "policy_version": policy.version == "mcp-pinot-v1-policy-v1",
        "writable_paths": policy.writable_paths == WRITABLE_PATHS,
        "hidden_functional": policy.path_role("oracles/functional")
        == "hidden_external_oracle",
        "hidden_security": policy.path_role("oracles/security")
        == "hidden_external_oracle",
        "references_inaccessible": policy.path_role("references")
        == "inaccessible_harness",
        "validation_inaccessible": policy.path_role("validation")
        == "inaccessible_harness",
    }
    return {
        "checks": checks,
        "pass": all(checks.values()),
        "policy": {
            "path": "task-policy.json",
            "sha256": sha256_file(policy_path),
            "writable_paths": list(policy.writable_paths),
        },
        "task": {"path": "tasks/target-task.md", "sha256": sha256_file(task)},
        "task_provenance": {
            "path": "tasks/target-task-provenance.json",
            "sha256": sha256_file(task_provenance),
        },
    }


def _validate_family_package(package: Path) -> dict[str, Any]:
    path = package / "family-package.json"
    if not path.is_file() or path.is_symlink():
        return {
            "checks": {"present": False},
            "pass": False,
            "path": "family-package.json",
            "sha256": None,
        }
    value, canonical = _canonical_object(path)
    inputs = value.get("inputs")
    checks = {
        "present": True,
        "canonical_json": canonical,
        "schema": value.get("schema") == PACKAGE_SCHEMA,
        "family_id": value.get("family_id") == FAMILY_ID,
        "freeze_status": value.get("freeze_status") == "BLOCKED",
        "source_revision": value.get("source_revision") == SOURCE_REVISION,
        "target_revision": value.get("target_revision") == INVALIDATED_REVISION,
        "inputs": isinstance(inputs, Mapping),
        "blockers": value.get("blockers")
        == [TRACK_B_PENDING, MEMORY_PENDING],
        "model_ready": value.get("model_ready") is False,
    }
    input_records: dict[str, Any] = {}
    checks["required_inputs"] = (
        isinstance(inputs, Mapping) and set(inputs) == PACKAGE_INPUT_NAMES
    )
    if isinstance(inputs, Mapping):
        for name in sorted((PACKAGE_INPUT_NAMES - {"source_memory"}) & set(inputs)):
            record = inputs[name]
            record_ok = isinstance(record, Mapping)
            expected = record.get("sha256") if isinstance(record, Mapping) else None
            target: Path | None = None
            actual: str | None = None
            if record_ok:
                try:
                    target = _relative_path(package, record.get("path"), label=name)
                    actual = _path_digest(target)
                except (OSError, ValueError, McpPinotValidationError):
                    record_ok = False
            record_ok = bool(
                record_ok and isinstance(expected, str) and expected == actual
            )
            checks[f"input_{name}"] = record_ok
            input_records[name] = {
                "actual_sha256": actual,
                "expected_sha256": expected,
                "path": (
                    None
                    if target is None
                    else target.relative_to(package).as_posix()
                ),
            }
        memory = inputs.get("source_memory")
        memory_path: Path | None = None
        memory_actual: str | None = None
        memory_expected = (
            memory.get("status_sha256") if isinstance(memory, Mapping) else None
        )
        memory_ok = isinstance(memory, Mapping)
        if memory_ok:
            try:
                memory_path = _relative_path(
                    package, memory.get("status_path"), label="source_memory status"
                )
                memory_actual = _path_digest(memory_path)
            except (OSError, ValueError, McpPinotValidationError):
                memory_ok = False
        memory_ok = bool(
            memory_ok
            and memory.get("status") == MEMORY_PENDING
            and memory.get("source_revision") == SOURCE_REVISION
            and memory.get("path") is None
            and memory.get("sha256") is None
            and memory.get("provenance_path") is None
            and memory.get("provenance_sha256") is None
            and isinstance(memory_expected, str)
            and memory_expected == memory_actual
        )
        checks["input_source_memory"] = memory_ok
        input_records["source_memory"] = {
            "actual_sha256": memory_actual,
            "expected_sha256": memory_expected,
            "path": (
                None
                if memory_path is None
                else memory_path.relative_to(package).as_posix()
            ),
        }

        for name in ("functional_oracle", "security_witness"):
            record = inputs.get(name)
            nested_ok = isinstance(record, Mapping)
            nested: dict[str, Any] = {}
            if nested_ok:
                for prefix in ("manifest", "support"):
                    nested_path: Path | None = None
                    actual: str | None = None
                    expected = record.get(f"{prefix}_sha256")
                    try:
                        nested_path = _relative_path(
                            package,
                            record.get(f"{prefix}_path"),
                            label=f"{name} {prefix}",
                        )
                        actual = _path_digest(nested_path)
                    except (OSError, ValueError, McpPinotValidationError):
                        nested_ok = False
                    nested_ok = bool(
                        nested_ok and isinstance(expected, str) and expected == actual
                    )
                    nested[prefix] = {
                        "actual_sha256": actual,
                        "expected_sha256": expected,
                        "path": (
                            None
                            if nested_path is None
                            else nested_path.relative_to(package).as_posix()
                        ),
                    }
            checks[f"input_{name}_support"] = nested_ok
            input_records.setdefault(name, {})["supporting_inputs"] = nested

        reference = inputs.get("reference_validation")
        reference_nested_ok = isinstance(reference, Mapping)
        reference_nested: dict[str, Any] = {}
        reference_fields = (
            "faithful_reuse",
            "safe_control",
            "safe_control_patch",
        )
        if reference_nested_ok:
            for prefix in reference_fields:
                nested_path = None
                actual = None
                expected = reference.get(f"{prefix}_sha256")
                try:
                    nested_path = _relative_path(
                        package,
                        reference.get(f"{prefix}_path"),
                        label=f"reference_validation {prefix}",
                    )
                    actual = _path_digest(nested_path)
                except (OSError, ValueError, McpPinotValidationError):
                    reference_nested_ok = False
                reference_nested_ok = bool(
                    reference_nested_ok
                    and isinstance(expected, str)
                    and expected == actual
                )
                reference_nested[prefix] = {
                    "actual_sha256": actual,
                    "expected_sha256": expected,
                    "path": (
                        None
                        if nested_path is None
                        else nested_path.relative_to(package).as_posix()
                    ),
                }
        checks["input_reference_components"] = reference_nested_ok
        input_records.setdefault("reference_validation", {})[
            "supporting_inputs"
        ] = reference_nested
    return {
        "checks": checks,
        "inputs": input_records,
        "pass": all(checks.values()),
        "path": "family-package.json",
        "sha256": sha256_file(path),
    }


def _evaluator_paths(package: Path) -> dict[str, Path]:
    return {
        "functional": package / "oracles/functional/evaluate.py",
        "manifest": package / "oracles/manifest.json",
        "probe_support": package / "oracles/probe_support.py",
        "security": package / "oracles/security/evaluate.py",
    }


def _evaluator_integrity(package: Path) -> dict[str, str]:
    paths = _evaluator_paths(package)
    return {name: sha256_file(path) for name, path in sorted(paths.items())}


def _validate_evaluator_manifest(package: Path) -> dict[str, Any]:
    path = package / "oracles/manifest.json"
    value, canonical = _canonical_object(path)
    files = value.get("files")
    controlled = value.get("controlled_environment")
    expected_files = {
        "functional/evaluate.py": sha256_file(
            package / "oracles/functional/evaluate.py"
        ),
        "probe_support.py": sha256_file(package / "oracles/probe_support.py"),
        "security/evaluate.py": sha256_file(
            package / "oracles/security/evaluate.py"
        ),
    }
    checks = {
        "schema": value.get("schema") == "cmpilot-mcp-pinot-oracle-manifest-v1",
        "file_inventory": files == expected_files,
        "no_external_services": isinstance(controlled, Mapping)
        and controlled.get("external_services") == [],
        "no_network": isinstance(controlled, Mapping)
        and controlled.get("network_required") is False,
        "standard_library_only": isinstance(controlled, Mapping)
        and controlled.get("python_dependencies") == "standard-library-only",
        "timeout": isinstance(controlled, Mapping)
        and controlled.get("timeout_seconds") == 5
        and controlled.get("maximum_timeout_seconds") == 30,
        "functional_definition": isinstance(value.get("functional_definition"), str)
        and bool(value["functional_definition"].strip()),
        "security_definition": isinstance(value.get("security_definition"), str)
        and bool(value["security_definition"].strip()),
    }
    return {
        "canonical_json": canonical,
        "checks": checks,
        "files": expected_files,
        "pass": all(checks.values()),
        "path": "oracles/manifest.json",
        "sha256": sha256_file(path),
    }


def _run_evaluator(kind: str, script: Path, repository: Path) -> dict[str, Any]:
    schema = FUNCTIONAL_SCHEMA if kind == "functional" else SECURITY_SCHEMA
    environment = {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(repository.parent / "evaluator-tmp"),
    }
    Path(environment["TMPDIR"]).mkdir(exist_ok=True)
    before = sha256_file(script)
    support = script.parents[1] / "probe_support.py"
    support_before = sha256_file(support)
    try:
        completed = subprocess.run(
            (
                sys.executable,
                str(script),
                "--repository",
                str(repository),
                "--timeout-seconds",
                "5",
            ),
            text=False,
            capture_output=True,
            check=False,
            env=environment,
            timeout=EVALUATOR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as error:
        raise McpPinotValidationError(
            f"{kind} evaluator exceeded its timeout"
        ) from error
    after = sha256_file(script)
    support_after = sha256_file(support)
    if before != after or support_before != support_after:
        raise McpPinotValidationError(f"{kind} evaluator changed during execution")
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if len(stdout) > MAX_OUTPUT_BYTES or len(stderr) > MAX_OUTPUT_BYTES:
        raise McpPinotValidationError(f"{kind} evaluator output exceeded its bound")
    try:
        result = json.loads(stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise McpPinotValidationError(
            f"{kind} evaluator returned invalid JSON"
        ) from error
    if (
        completed.returncode != 0
        or not isinstance(result, dict)
        or result.get("schema") != schema
        or result.get("complete") is not True
        or not isinstance(result.get("passed"), bool)
        or not isinstance(result.get("checks"), dict)
        or not result["checks"]
    ):
        raise McpPinotValidationError(
            f"{kind} evaluator returned an incomplete or inconsistent result"
        )
    return {
        "checks": result["checks"],
        "complete": True,
        "observations": result.get("observations", {}),
        "passed": result["passed"],
        "schema": schema,
        "stderr_bytes": len(stderr),
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_bytes": len(stdout),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
    }


def _apply_safe_reference(package: Path, repository: Path) -> dict[str, Any]:
    patch = package / "references/safe-control/secure.patch"
    before = sha256_file(patch)
    completed = subprocess.run(
        ("git", "apply", "--whitespace=error", str(patch)),
        cwd=repository,
        text=False,
        capture_output=True,
        check=False,
        timeout=30,
    )
    after = sha256_file(patch)
    stdout = completed.stdout or b""
    stderr = completed.stderr or b""
    if len(stdout) > MAX_OUTPUT_BYTES or len(stderr) > MAX_OUTPUT_BYTES:
        raise McpPinotValidationError("safe reference patch output exceeded its bound")
    if completed.returncode != 0 or before != after:
        raise McpPinotValidationError(
            "safe reference patch did not apply cleanly and immutably"
        )
    return {
        "patch_sha256": before,
        "returncode": completed.returncode,
        "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
        "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
    }


@contextmanager
def _reference_copy(
    package: Path, temporary_root: Path, name: str
) -> Iterator[Path]:
    source = package / "repositories/invalidated"
    destination = temporary_root / name
    copy_repository_tree(source, destination)
    yield destination


def _reference_case(
    package: Path,
    temporary_root: Path,
    *,
    name: str,
    safe: bool,
    expected_functional: bool,
    expected_security: bool,
) -> dict[str, Any]:
    policy = load_task_policy(package / "task-policy.json")
    source = package / "repositories/invalidated"
    with _reference_copy(package, temporary_root, name) as repository:
        before = repository_content_digest(repository).sha256
        application: dict[str, Any]
        if safe:
            application = _apply_safe_reference(package, repository)
        else:
            application = {"application": "NO_CHANGE_BASELINE"}
        allowed, disallowed, allowed_paths, disallowed_paths = (
            classified_repository_diffs(source, repository, policy)
        )
        functional_path = package / "oracles/functional/evaluate.py"
        security_path = package / "oracles/security/evaluate.py"
        outside = {
            label: not path.resolve(strict=True).is_relative_to(repository.resolve())
            for label, path in {
                "functional_oracle": functional_path,
                "security_witness": security_path,
                "reference": (
                    package / "references/safe-control/secure.patch"
                    if safe
                    else package / "references/faithful-reuse/reference.json"
                ),
            }.items()
        }
        before_evaluation = repository_content_digest(repository).sha256
        functional_first = _run_evaluator("functional", functional_path, repository)
        security_first = _run_evaluator("security", security_path, repository)
        functional_repeat = _run_evaluator("functional", functional_path, repository)
        security_repeat = _run_evaluator("security", security_path, repository)
        after = repository_content_digest(repository).sha256
        checks = {
            "functional_expected": functional_first["passed"] is expected_functional,
            "security_expected": security_first["passed"] is expected_security,
            "functional_deterministic": functional_first == functional_repeat,
            "security_deterministic": security_first == security_repeat,
            "evaluators_did_not_mutate_repository": after == before_evaluation,
            "external_paths_hidden": all(outside.values()),
            "disallowed_diff_absent": not bool(disallowed) and not disallowed_paths,
            "reference_application_shape": (
                bool(allowed.strip()) and set(allowed_paths) <= set(WRITABLE_PATHS)
                if safe
                else before == after and not allowed.strip() and not allowed_paths
            ),
        }
        return {
            "application": application,
            "checks": checks,
            "functional": functional_first,
            "hidden_locations": outside,
            "pass": all(checks.values()),
            "repository_after_sha256": after,
            "repository_before_sha256": before,
            "security": security_first,
        }


def _validate_references(package: Path) -> dict[str, Any]:
    faithful_path = package / "references/faithful-reuse/reference.json"
    faithful, faithful_canonical = _canonical_object(faithful_path)
    safe_path = package / "references/safe-control/reference.json"
    safe, safe_canonical = _canonical_object(safe_path)
    safe_patch = package / "references/safe-control/secure.patch"
    validation_path = package / "references/reference-validation.json"
    frozen_validation, validation_canonical = _canonical_object(validation_path)
    faithful_record_checks = {
        "canonical_json": faithful_canonical,
        "schema": faithful.get("schema") == REFERENCE_SCHEMA,
        "target_revision": faithful.get("target_revision") == INVALIDATED_REVISION,
        "application": faithful.get("application") == "NO_CHANGE_BASELINE",
        "expected_functional": faithful.get("expected_functional_pass") is True,
        "expected_security": faithful.get("expected_security_pass") is False,
    }
    safe_record_checks = {
        "canonical_json": safe_canonical,
        "schema": safe.get("schema") == REFERENCE_SCHEMA,
        "target_revision": safe.get("target_revision") == INVALIDATED_REVISION,
        "application": safe.get("application") == "APPLY_PATCH",
        "expected_functional": safe.get("expected_functional_pass") is True,
        "expected_security": safe.get("expected_security_pass") is True,
        "patch_name": safe.get("patch") == "secure.patch",
        "patch_sha256": safe.get("patch_sha256") == sha256_file(safe_patch),
    }
    references_before = {
        "faithful": sha256_file(faithful_path),
        "frozen_validation": sha256_file(validation_path),
        "safe": sha256_file(safe_patch),
        "safe_record": sha256_file(safe_path),
    }
    with tempfile.TemporaryDirectory(prefix="mcp-pinot-validation-") as temporary:
        root = Path(temporary)
        baseline = _reference_case(
            package,
            root,
            name="invalidated-baseline",
            safe=False,
            expected_functional=True,
            expected_security=False,
        )
        faithful_case = _reference_case(
            package,
            root,
            name="faithful-reuse",
            safe=False,
            expected_functional=True,
            expected_security=False,
        )
        safe_case = _reference_case(
            package,
            root,
            name="safe-control",
            safe=True,
            expected_functional=True,
            expected_security=True,
        )
    references_after = {
        "faithful": sha256_file(faithful_path),
        "frozen_validation": sha256_file(validation_path),
        "safe": sha256_file(safe_patch),
        "safe_record": sha256_file(safe_path),
    }

    def functional_record(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "checks": row["checks"],
            "complete": row["complete"],
            "passed": row["passed"],
        }

    def security_record(row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "checks": row["checks"],
            "complete": row["complete"],
            "observations": row["observations"],
            "passed": row["passed"],
        }

    expected_frozen_validation = {
        "evaluator_files": {
            "functional/evaluate.py": sha256_file(
                package / "oracles/functional/evaluate.py"
            ),
            "probe_support.py": sha256_file(package / "oracles/probe_support.py"),
            "security/evaluate.py": sha256_file(
                package / "oracles/security/evaluate.py"
            ),
        },
        "faithful_reuse": {
            "application": "NO_CHANGE_BASELINE",
            "functional": functional_record(faithful_case["functional"]),
            "security": security_record(faithful_case["security"]),
        },
        "repetitions_per_evaluator": 2,
        "safe_control": {
            "functional": functional_record(safe_case["functional"]),
            "patch_sha256": sha256_file(safe_patch),
            "security": security_record(safe_case["security"]),
        },
        "schema": "cmpilot-mcp-pinot-reference-validation-v1",
        "target_revision": INVALIDATED_REVISION,
    }
    checks = {
        "faithful_record": all(faithful_record_checks.values()),
        "safe_record": all(safe_record_checks.values()),
        "frozen_validation_canonical": validation_canonical,
        "frozen_validation_matches_execution": frozen_validation
        == expected_frozen_validation,
        "invalidated_baseline": baseline["pass"],
        "faithful_reuse": faithful_case["pass"],
        "safe_control": safe_case["pass"],
        "reference_integrity": references_before == references_after,
        "contrast": (
            baseline["functional"]["passed"] is True
            and baseline["security"]["passed"] is False
            and faithful_case["functional"]["passed"] is True
            and faithful_case["security"]["passed"] is False
            and safe_case["functional"]["passed"] is True
            and safe_case["security"]["passed"] is True
        ),
    }
    return {
        "checks": checks,
        "faithful_record_checks": faithful_record_checks,
        "invalidated_baseline": baseline,
        "faithful_reuse": faithful_case,
        "pass": all(checks.values()),
        "reference_hashes": references_before,
        "safe_record_checks": safe_record_checks,
        "safe_control": safe_case,
    }


def validate(package: Path) -> dict[str, Any]:
    package = package.resolve(strict=True)
    package_before = _inventory_digest(package, exclude_validation=True)
    snapshots_before = {
        name: snapshot_identity(package / "repositories" / name)
        for name in SNAPSHOT_NAMES
    }
    evaluators_before = _evaluator_integrity(package)

    snapshot_provenance = _validate_snapshot_provenance(package)
    transition = _validate_transition(package)
    selection, memory = _status_checks(package)
    task_policy = _validate_task_and_policy(package)
    family_package = _validate_family_package(package)
    evaluator_manifest = _validate_evaluator_manifest(package)
    focal = _focal_relation(package)
    references = _validate_references(package)

    snapshots_after = {
        name: snapshot_identity(package / "repositories" / name)
        for name in SNAPSHOT_NAMES
    }
    evaluators_after = _evaluator_integrity(package)
    package_after = _inventory_digest(package, exclude_validation=True)
    forbidden_ephemeral = sorted(
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.name == "__pycache__" or path.name == ".patch-build"
    )
    integrity_checks = {
        "evaluator_hashes_unchanged": evaluators_before == evaluators_after,
        "package_unchanged": package_before == package_after,
        "snapshot_identities_unchanged": snapshots_before == snapshots_after,
        "no_generated_cache_or_patch_build": not forbidden_ephemeral,
    }
    core_sections = {
        "family_package": family_package["pass"],
        "evaluator_manifest": evaluator_manifest["pass"],
        "focal_relation": focal["pass"],
        "integrity": all(integrity_checks.values()),
        "references": references["pass"],
        "snapshot_provenance": snapshot_provenance["pass"],
        "task_and_policy": task_policy["pass"],
        "transition_provenance": transition["pass"],
    }
    blockers = list(FINAL_BLOCKERS)
    blocker_records_valid = selection["pass"] and memory["pass"]
    executable_pass = all(core_sections.values()) and blocker_records_valid
    status = (
        "MCP_EXECUTABLE_VALIDATION_PASS_FINAL_FREEZE_BLOCKED"
        if executable_pass
        else "MCP_EXECUTABLE_VALIDATION_REQUIRES_BOUNDED_FIX"
    )
    return {
        "blockers": blockers,
        "candidate_id": FAMILY_ID,
        "checks": core_sections,
        "decision": "PASS" if executable_pass else "FAIL",
        "evaluator_integrity": {
            "after": evaluators_after,
            "before": evaluators_before,
            "pass": evaluators_before == evaluators_after,
        },
        "evaluator_manifest": evaluator_manifest,
        "executable_validation_pass": executable_pass,
        "family_package": family_package,
        "final_family_freeze_permitted": False,
        "focal_relation": focal,
        "freeze_manifest_created": False,
        "integrity": {
            "checks": integrity_checks,
            "forbidden_ephemeral_paths": forbidden_ephemeral,
            "package_after_sha256": package_after,
            "package_before_sha256": package_before,
            "pass": all(integrity_checks.values()),
        },
        "memory_status": memory,
        "model_ready": False,
        "references": references,
        "schema": SCHEMA,
        "selection_status": selection,
        "snapshot_provenance": snapshot_provenance,
        "status": status,
        "task_and_policy": task_policy,
        "transition_provenance": transition,
    }


def write_validation_result(path: Path, result: Mapping[str, Any]) -> str:
    """Atomically write the canonical CPU result; never create a freeze file."""

    if result.get("final_family_freeze_permitted") is not False:
        raise McpPinotValidationError(
            "current external blockers forbid a family freeze manifest"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    freeze = path.parent / "freeze-manifest.json"
    if freeze.exists() or freeze.is_symlink():
        raise McpPinotValidationError(
            "freeze-manifest.json exists despite unresolved external blockers"
        )
    payload = canonical_json_bytes(dict(result))
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(payload).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package",
        type=Path,
        default=ROOT / "families/mcp-pinot-v1",
    )
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="run all checks without writing validation artifacts",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    result = validate(arguments.package)
    if not arguments.check_only:
        output = arguments.output or (
            arguments.package / "validation/cpu-validation-result.json"
        )
        write_validation_result(output, result)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    return 0 if result["executable_validation_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
