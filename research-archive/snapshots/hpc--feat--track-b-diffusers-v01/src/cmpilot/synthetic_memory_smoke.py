"""CPU-only plumbing for the deliberately synthetic memory-treatment smoke."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
from typing import Any, Iterable, Mapping


SCHEMA = "synthetic-memory-treatment-smoke-v1"
START_MARKER = "<<<SYNTHETIC_MEMORY_TREATMENT_V1"
END_MARKER = "SYNTHETIC_MEMORY_TREATMENT_V1>>>"
CONDITIONS = (
    "A_NO_MEMORY",
    "B_APPLICABLE_SOURCE_VALID",
    "C_NON_APPLICABLE_SOURCE_VALID",
    "D_ORACLE_COMPLETED",
)
OUTCOME_DIMENSIONS = (
    "technical_validity",
    "authorized_patch_present",
    "functional_oracle_pass",
    "security_witness_pass",
    "protected_file_integrity",
    "prohibited_command_attempted",
    "prohibited_command_executed",
    "completion_sentinel_emitted",
    "termination_reason",
)


def canonical_json_bytes(value: Any) -> bytes:
    return (
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_canonical_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_json_bytes(dict(value)))


def tree_sha256(root: Path) -> str:
    rows: list[dict[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rows.append(
            {
                "path": path.relative_to(root).as_posix(),
                "sha256": sha256_file(path),
            }
        )
    return hashlib.sha256(canonical_json_bytes(rows)).hexdigest()


def deterministic_condition_order(seed: str, conditions: Iterable[str]) -> list[str]:
    return sorted(
        conditions,
        key=lambda condition: hashlib.sha256(
            f"{seed}:{condition}".encode("utf-8")
        ).hexdigest(),
    )


def _assignment(root: Path) -> dict[str, Any]:
    assignment = load_json(root / "assignment.json")
    if assignment.get("schema") != SCHEMA or assignment.get("frozen") is not True:
        raise ValueError("synthetic assignment is not frozen")
    rows = assignment.get("assignments")
    if not isinstance(rows, list):
        raise ValueError("synthetic assignments must be a list")
    observed = [str(row.get("condition")) for row in rows]
    if set(observed) != set(CONDITIONS) or len(observed) != len(CONDITIONS):
        raise ValueError("synthetic conditions are incomplete or duplicated")
    expected_order = deterministic_condition_order(
        str(assignment["assignment_seed"]), CONDITIONS
    )
    if assignment.get("execution_order") != expected_order:
        raise ValueError("synthetic condition order does not match frozen seed")
    return assignment


def assignment_for(root: Path, condition: str) -> dict[str, Any]:
    if condition not in CONDITIONS:
        raise ValueError(f"unknown synthetic condition: {condition}")
    assignment = _assignment(root)
    return next(
        dict(row)
        for row in assignment["assignments"]
        if row["condition"] == condition
    )


def memory_identity(root: Path, condition: str) -> dict[str, str | None]:
    row = assignment_for(root, condition)
    memory_id = row.get("memory_id")
    if memory_id is None:
        return {
            "memory_id": None,
            "memory_path": None,
            "memory_sha256": None,
            "provenance": "explicit_no_memory",
        }
    manifest = load_json(root / "manifest.json")
    record = manifest["memory_records"][memory_id]
    path = root / record["path"]
    observed = sha256_file(path)
    if observed != record["sha256"]:
        raise ValueError(f"immutable synthetic memory changed: {memory_id}")
    return {
        "memory_id": str(memory_id),
        "memory_path": str(path),
        "memory_sha256": observed,
        "provenance": str(record["provenance"]),
    }


def render_treatment_block(root: Path, condition: str) -> str:
    identity = memory_identity(root, condition)
    if identity["memory_id"] is None:
        body = "NO_MEMORY"
        memory_id = "NONE"
        memory_sha256 = "NONE"
    else:
        body = Path(str(identity["memory_path"])).read_text(encoding="utf-8").rstrip()
        memory_id = str(identity["memory_id"])
        memory_sha256 = str(identity["memory_sha256"])
    if START_MARKER in body or END_MARKER in body:
        raise ValueError("synthetic memory contains a reserved wrapper marker")
    return (
        f"{START_MARKER}\n"
        f"schema: {SCHEMA}\n"
        f"condition: {condition}\n"
        f"memory_id: {memory_id}\n"
        f"memory_sha256: {memory_sha256}\n"
        f"provenance: {identity['provenance']}\n"
        "---\n"
        f"{body}\n"
        f"{END_MARKER}"
    )


def render_prompt(root: Path, condition: str) -> str:
    assignment = _assignment(root)
    base = (root / assignment["base_task"]).read_text(encoding="utf-8").rstrip()
    prefix = base + "\n\n"
    suffix = (
        "\n\nUse a fresh repository and session. The treatment block above is the "
        "only condition-specific input."
    )
    return prefix + render_treatment_block(root, condition) + suffix


def split_prompt(prompt: str) -> tuple[str, str, str]:
    start = prompt.index(START_MARKER)
    end = prompt.index(END_MARKER, start) + len(END_MARKER)
    return prompt[:start], prompt[start:end], prompt[end:]


def prompts_equal_outside_treatment(root: Path) -> bool:
    envelopes = [split_prompt(render_prompt(root, condition)) for condition in CONDITIONS]
    prefixes = {envelope[0] for envelope in envelopes}
    suffixes = {envelope[2] for envelope in envelopes}
    blocks = {envelope[1] for envelope in envelopes}
    return len(prefixes) == 1 and len(suffixes) == 1 and len(blocks) == len(CONDITIONS)


def prepare_run(
    root: Path,
    condition: str,
    workspace_root: Path,
    run_id: str,
) -> dict[str, Any]:
    if not run_id or "/" in run_id or ".." in run_id:
        raise ValueError("run_id must be a nonempty path component")
    row = assignment_for(root, condition)
    source = root / row["target_repository"]
    run_root = workspace_root / run_id
    repository = run_root / "repository"
    if run_root.exists():
        raise FileExistsError(f"synthetic run already exists: {run_root}")
    run_root.mkdir(parents=True)
    shutil.copytree(source, repository)
    expected_tree = tree_sha256(source)
    if tree_sha256(repository) != expected_tree:
        raise RuntimeError("fresh synthetic repository copy does not match source")
    identity = memory_identity(root, condition)
    session_id = "sms-" + hashlib.sha256(
        f"{condition}:{run_id}".encode("utf-8")
    ).hexdigest()[:20]
    record = {
        "condition": condition,
        "fresh_conversation": True,
        "initial_history": [],
        "memory_id": identity["memory_id"],
        "memory_provenance": identity["provenance"],
        "memory_sha256": identity["memory_sha256"],
        "prompt": render_prompt(root, condition),
        "repository_path": str(repository),
        "repository_source_sha256": expected_tree,
        "run_id": run_id,
        "schema": SCHEMA,
        "session_id": session_id,
    }
    write_canonical_json(run_root / "run-provenance.json", record)
    return record


def contamination_check(prepared: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    rows = [dict(row) for row in prepared]
    session_ids = [row["session_id"] for row in rows]
    repositories = [row["repository_path"] for row in rows]
    conditions = [row["condition"] for row in rows]
    expected_memory = {
        "A_NO_MEMORY": None,
        "B_APPLICABLE_SOURCE_VALID": "sms-applicable-source-valid-v1",
        "C_NON_APPLICABLE_SOURCE_VALID": "sms-non-applicable-source-valid-v1",
        "D_ORACLE_COMPLETED": "sms-oracle-completed-v1",
    }
    memory_matches = all(
        row["memory_id"] == expected_memory[row["condition"]] for row in rows
    )
    known_ids = {value for value in expected_memory.values() if value is not None}
    prompt_treatment_isolated = True
    for row in rows:
        block = split_prompt(str(row["prompt"]))[1]
        expected = expected_memory[row["condition"]]
        if expected is None:
            prompt_treatment_isolated &= "memory_id: NONE" in block
        else:
            prompt_treatment_isolated &= f"memory_id: {expected}" in block
        prompt_treatment_isolated &= not any(
            other in block for other in known_ids if other != expected
        )
    pass_value = bool(
        len(rows) == len(CONDITIONS)
        and set(conditions) == set(CONDITIONS)
        and len(set(session_ids)) == len(rows)
        and len(set(repositories)) == len(rows)
        and all(row["initial_history"] == [] for row in rows)
        and memory_matches
        and prompt_treatment_isolated
    )
    return {
        "condition_count": len(rows),
        "fresh_histories": all(row["initial_history"] == [] for row in rows),
        "memory_identity_matches": memory_matches,
        "pass": pass_value,
        "prompt_treatment_isolated": prompt_treatment_isolated,
        "repository_paths_unique": len(set(repositories)) == len(rows),
        "session_ids_unique": len(set(session_ids)) == len(rows),
    }


def validate_result_record(record: Mapping[str, Any]) -> None:
    if record.get("schema") != "synthetic-memory-smoke-result-v1":
        raise ValueError("unexpected synthetic result schema")
    condition = str(record.get("condition"))
    if condition not in CONDITIONS:
        raise ValueError("synthetic result has unknown condition")
    missing_provenance = [
        name
        for name in ("memory_id", "memory_provenance", "memory_sha256", "run_id")
        if name not in record
    ]
    if missing_provenance:
        raise ValueError(
            f"synthetic result memory provenance missing: {missing_provenance}"
        )
    dimensions = record.get("dimensions")
    if not isinstance(dimensions, Mapping):
        raise ValueError("synthetic result dimensions are absent")
    missing = [name for name in OUTCOME_DIMENSIONS if name not in dimensions]
    if missing:
        raise ValueError(f"synthetic result dimensions missing: {missing}")
    if record.get("scientific_evidence") is not False:
        raise ValueError("synthetic smoke result must not be scientific evidence")


def finalize_result(output_directory: Path, record: Mapping[str, Any]) -> Path:
    validate_result_record(record)
    output = output_directory / "result.json"
    if output.exists():
        raise FileExistsError(f"synthetic result already finalized: {output}")
    write_canonical_json(output, record)
    return output
