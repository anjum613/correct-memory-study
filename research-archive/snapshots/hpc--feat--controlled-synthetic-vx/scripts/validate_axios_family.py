#!/usr/bin/env python3
"""CPU-only admission checks for the Axios Track B executable family."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.file_digest import sha256_file  # noqa: E402
from cmpilot.final_experiment import canonical_json_bytes  # noqa: E402
from cmpilot.qualification import load_task_policy  # noqa: E402
from cmpilot.repository_manager import (  # noqa: E402
    copy_repository_tree,
    repository_content_digest,
)
from validate_mcp_pinot_family import snapshot_identity  # noqa: E402


SCHEMA = "cmpilot-axios-cpu-validation-v1"
PACKAGE_SCHEMA = "cmpilot-axios-family-package-v1"
FAMILY_ID = "axios-v1"
SOURCE = "738fa63661a7a5d7e8bf604436bb3b91648e327b"
COMPATIBLE = "96d336f527619f21da012fe1f117eeb53e5a2120"
INVALIDATED = "128d56f4a0fb8f5f2ed6e0dd80bc9225fee9538c"
TREES = {
    "source": "d777a911e8734ea3d3949e644170ee6d612b964c",
    "compatible": "4222327de192e44157477dff44950d8c4610c3d6",
    "invalidated": "3931c823713859def72a35f2d8f0e2c0f4d5c18a",
}
REVISIONS = {"source": SOURCE, "compatible": COMPATIBLE, "invalidated": INVALIDATED}
SNAPSHOT_SHA256 = {
    "source": "5a12bd55ea8ea576d1b65281ac5cbdd72086f27e660bafdbf02c2e6c20d7a988",
    "compatible": "0461c22007b89c93384dda2383930ebdd92536f63e9a6568cff5d9402c443b0a",
    "invalidated": "c87e05b8892bab7224206562ab1f9404f911c133d40ad03c538c0ac4d983983f",
}
REPOSITORY_SHA256 = {
    "source": "3d1e3812f9d21a3af7d8d14717ada7b616ef73bd564291c103adc56bf170ae3d",
    "compatible": "1c8d517db02863c986a671b5247991d1ef762b522a53058324839e8955b4758f",
    "invalidated": "5cbc02e61776b0fffdbe97e29b148f22edc30400dbb81e4316d128a718c0b4a8",
}
NODE_SHA256 = "650356ce523cc01dee7b7e9f776b195d8601898af42bbe00c66a94a056698b03"
PROTOCOL_SHA256 = "173ddf06d609609b0036cd60ddb856ad83a8d4a05f5b6b2fe270fb5afb2d0f11"
PROTOCOL_COMMIT = "619a7b070de383ca5551ff598a7ba706dd8502c7"
GENERATOR_SHA256 = "13919c2bf876cd0da32ebe687a77abc6a672af1e11cec62d38b9958c7062d332"
FOCAL_PROPERTY = (
    "In the Node HTTP adapter, a protocol-relative config.url of the form "
    "//H[:P]/path must not be made dispatchable to H by synthesizing a scheme "
    "or base; request preparation must reject before transport."
)
EXPECTED_INPUTS = {
    "compatible_repository",
    "functional_oracle",
    "historical_transition",
    "node_loader",
    "node_probe",
    "reference_validation",
    "runtime_qualification",
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


class AxiosValidationError(RuntimeError):
    """A frozen input or executable invariant failed."""


def _object(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AxiosValidationError(f"invalid JSON input {path}: {error}") from error
    if not isinstance(value, dict) or raw != canonical_json_bytes(value):
        raise AxiosValidationError(f"JSON input is not a canonical object: {path}")
    return value


def _check(condition: bool, label: str) -> None:
    if not condition:
        raise AxiosValidationError(label)


def _safe_family_path(package: Path, value: Any, label: str) -> Path:
    _check(isinstance(value, str) and bool(value), f"{label} path is invalid")
    relative = Path(value)
    _check(not relative.is_absolute() and ".." not in relative.parts, f"{label} path escapes package")
    path = package / relative
    _check(path.exists() and not path.is_symlink(), f"{label} path is missing or unsafe")
    _check(path.resolve().is_relative_to(package.resolve()), f"{label} path escapes package")
    return path


def _digest(path: Path) -> str:
    return sha256_file(path) if path.is_file() else repository_content_digest(path).sha256


def _verify_record(package: Path, record: Mapping[str, Any], label: str) -> dict[str, str]:
    path = _safe_family_path(package, record.get("path"), label)
    observed = _digest(path)
    _check(observed == record.get("sha256"), f"{label} SHA-256 mismatch")
    return {"path": path.relative_to(package).as_posix(), "sha256": observed}


def _validate_package(package: Path, *, prefreeze: bool) -> tuple[dict[str, Any], dict[str, Any]]:
    package_file = package / "family-package.json"
    value = _object(package_file)
    expected_state = (
        ("PREFREEZE_VALIDATION", False, ["FINAL_CPU_VALIDATION_PENDING"])
        if prefreeze
        else ("FROZEN", True, [])
    )
    _check(value.get("schema") == PACKAGE_SCHEMA, "wrong package schema")
    _check(value.get("family_id") == FAMILY_ID, "wrong family id")
    _check(value.get("source_revision") == SOURCE, "wrong source revision")
    _check(value.get("compatible_revision") == COMPATIBLE, "wrong compatible revision")
    _check(value.get("target_revision") == INVALIDATED, "wrong target revision")
    _check(
        (value.get("freeze_status"), value.get("model_ready"), value.get("blockers"))
        == expected_state,
        "family freeze state is inconsistent with validation mode",
    )
    inputs = value.get("inputs")
    _check(isinstance(inputs, Mapping) and set(inputs) == EXPECTED_INPUTS, "package input inventory mismatch")

    checked: dict[str, Any] = {}
    repositories = {
        "source_repository": "source",
        "compatible_repository": "compatible",
        "target_repository": "invalidated",
    }
    for label, name in repositories.items():
        record = inputs[label]
        _check(isinstance(record, Mapping), f"{label} record invalid")
        checked[label] = _verify_record(package, record, label)
        _check(record.get("sha256") == REPOSITORY_SHA256[name], f"{label} digest not frozen")
        _check(record.get("snapshot_sha256") == SNAPSHOT_SHA256[name], f"{label} snapshot digest not frozen")

    simple = EXPECTED_INPUTS - set(repositories) - {"source_memory"}
    for label in sorted(simple):
        record = inputs[label]
        _check(isinstance(record, Mapping), f"{label} record invalid")
        checked[label] = _verify_record(package, record, label)

    nested_fields = {
        "functional_oracle": ("manifest", "support"),
        "security_witness": ("manifest", "support"),
        "reference_validation": ("faithful_reuse", "safe_control", "safe_control_patch"),
        "selection_provenance": ("review",),
    }
    for label, prefixes in nested_fields.items():
        record = inputs[label]
        for prefix in prefixes:
            nested = {"path": record.get(f"{prefix}_path"), "sha256": record.get(f"{prefix}_sha256")}
            checked[f"{label}.{prefix}"] = _verify_record(package, nested, f"{label}.{prefix}")

    memory = inputs["source_memory"]
    _check(isinstance(memory, Mapping), "source_memory record invalid")
    for prefix, path_key, hash_key in (
        ("content", "path", "sha256"),
        ("input", "input_path", "input_sha256"),
        ("provenance", "provenance_path", "provenance_sha256"),
        ("status", "status_path", "status_sha256"),
        ("source_validation", "source_validation_path", "source_validation_sha256"),
    ):
        checked[f"source_memory.{prefix}"] = _verify_record(
            package,
            {"path": memory.get(path_key), "sha256": memory.get(hash_key)},
            f"source_memory.{prefix}",
        )
    _check(memory.get("status") == "FROZEN", "memory is not frozen")
    _check(memory.get("source_revision") == SOURCE, "memory source revision mismatch")
    _check(memory.get("protocol_commit") == PROTOCOL_COMMIT, "memory protocol commit mismatch")
    _check(memory.get("protocol_sha256") == PROTOCOL_SHA256, "memory protocol hash mismatch")
    protocol = ROOT / str(memory.get("protocol_path"))
    _check(protocol.is_file() and sha256_file(protocol) == PROTOCOL_SHA256, "memory protocol file mismatch")
    return value, {
        "freeze_status": value["freeze_status"],
        "inputs": checked,
        "model_ready": value["model_ready"],
        "path": "family-package.json",
        "sha256": sha256_file(package_file),
    }


def _validate_snapshots(package: Path) -> dict[str, Any]:
    provenance = _object(package / "provenance/upstream-snapshot-provenance.json")
    records = provenance.get("snapshots")
    _check(provenance.get("candidate_id") == FAMILY_ID, "snapshot candidate mismatch")
    _check(isinstance(records, Mapping) and set(records) == set(TREES), "snapshot inventory mismatch")
    output: dict[str, Any] = {}
    for name in TREES:
        path = package / "repositories" / name
        observed = snapshot_identity(path)
        record = records[name]
        _check(isinstance(record, Mapping), f"{name} provenance record invalid")
        _check(record.get("commit_sha") == REVISIONS[name], f"{name} commit mismatch")
        _check(record.get("tree_sha") == TREES[name], f"{name} recorded tree mismatch")
        _check(observed["git_tree_sha"] == TREES[name], f"{name} reconstructed tree mismatch")
        _check(observed["snapshot_content_sha256"] == SNAPSHOT_SHA256[name], f"{name} snapshot digest mismatch")
        _check(repository_content_digest(path).sha256 == REPOSITORY_SHA256[name], f"{name} repository digest mismatch")
        _check(not (path / ".git").exists() and not (path / ".gitmodules").exists(), f"{name} contains Git metadata")
        output[name] = {"commit": REVISIONS[name], "tree": TREES[name], **observed}
    conclusion = provenance.get("frozen_property_check")
    _check(isinstance(conclusion, Mapping) and conclusion.get("focal_assumption") == FOCAL_PROPERTY, "snapshot p* mismatch")
    return output


def _validate_transition(package: Path) -> dict[str, Any]:
    transition = _object(package / "provenance/historical-transition.json")
    _check(transition.get("candidate_id") == FAMILY_ID, "transition candidate mismatch")
    _check(transition.get("repository") == "axios/axios", "transition repository mismatch")
    _check(transition.get("focal_property") == FOCAL_PROPERTY, "transition p* mismatch")
    for name, expected in (("source", True), ("compatible", True), ("invalidated", False)):
        row = transition.get(name)
        _check(isinstance(row, Mapping), f"transition {name} missing")
        _check(row.get("commit") == REVISIONS[name], f"transition {name} commit mismatch")
        _check(row.get("tree") == TREES[name], f"transition {name} tree mismatch")
        _check(row.get("frozen_property_value") is expected, f"transition {name} p* mismatch")
    source_text = (package / "repositories/source/lib/adapters/http.js").read_text(encoding="utf-8")
    compatible_text = (package / "repositories/compatible/lib/adapters/http.js").read_text(encoding="utf-8")
    invalidated_text = (package / "repositories/invalidated/lib/adapters/http.js").read_text(encoding="utf-8")
    _check("new URL(fullPath);" in source_text, "source executable evidence missing")
    _check("new URL(fullPath);" in compatible_text, "compatible executable evidence missing")
    _check("new URL(fullPath, 'http://localhost');" in invalidated_text, "invalidated executable evidence missing")
    return {"focal_property": FOCAL_PROPERTY, "relationship": "p*(S)=TRUE, p*(C)=TRUE, p*(I)=FALSE"}


def _validate_memory(package: Path) -> dict[str, Any]:
    provenance = _object(package / "memories/source-correct-memory-provenance.json")
    status = _object(package / "memories/memory-status.json")
    input_bundle = _object(package / "memories/source-correct-memory-input.json")
    validation = _object(package / "memories/source-validation-result.json")
    generation = provenance.get("generation")
    grounding = provenance.get("source_grounding_validation")
    summary = validation.get("summary")
    _check(status.get("status") == "FROZEN" and status.get("final_family_freeze_blocked") is False, "memory status invalid")
    _check(status.get("source_grounding_validation") == "PASS", "memory grounding status invalid")
    _check(isinstance(generation, Mapping), "memory generation record missing")
    _check(generation.get("attempt") == 1 and generation.get("regeneration_performed") is False, "memory was regenerated")
    _check(generation.get("generator_sha256") == GENERATOR_SHA256, "memory generator mismatch")
    _check(generation.get("model") is None and generation.get("seed") is None, "deterministic memory renderer mismatch")
    _check(isinstance(grounding, Mapping) and grounding.get("result") == "PASS", "memory grounding failed")
    _check(isinstance(grounding.get("checks"), Mapping) and all(grounding["checks"].values()), "memory grounding checks failed")
    _check(input_bundle.get("source_repository", {}).get("revision") == SOURCE, "memory input source mismatch")
    _check(input_bundle.get("source_solution", {}).get("revision") == SOURCE, "memory solution source mismatch")
    _check(input_bundle.get("source_task", {}).get("source_only") is True, "memory input not source-only")
    _check(summary == {"failed": 0, "passed": 2, "skipped": 1, "status": "PASS"}, "source validation result mismatch")
    forbidden_keys = {"invalidated_revision", "security_witness", "safe_control", "target_outcomes", "expected_memory_effect"}
    all_keys: set[str] = set()
    def walk(value: Any) -> None:
        if isinstance(value, Mapping):
            all_keys.update(str(key).casefold() for key in value)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
    walk(input_bundle)
    _check(not (all_keys & forbidden_keys), "memory input contains forbidden future fields")
    _check(sha256_file(ROOT / "scripts/generate_source_procedural_memory.py") == GENERATOR_SHA256, "memory generator changed")
    return {"attempt": 1, "grounding": "PASS", "regeneration_performed": False, "status": "FROZEN"}


def _validate_task(package: Path) -> dict[str, Any]:
    provenance = _object(package / "tasks/target-task-provenance.json")
    policy_value = _object(package / "task-policy.json")
    policy = load_task_policy(package / "task-policy.json")
    disclosure = provenance.get("non_disclosure")
    _check(provenance.get("candidate_id") == FAMILY_ID and provenance.get("target_revision") == INVALIDATED, "task provenance mismatch")
    _check(isinstance(disclosure, Mapping) and set(disclosure.values()) == {False}, "task non-disclosure failed")
    _check(policy_value.get("version") == "axios-v1-policy-v1", "task policy version mismatch")
    _check(policy.writable_paths == ("lib/adapters/http.js",), "task writable paths mismatch")
    target = package / "repositories/invalidated"
    _check(
        all((target / relative).is_file() for relative in policy.readable_protected_paths),
        "task policy names a missing protected path",
    )
    _check(policy.path_role("oracles/security") == "hidden_external_oracle", "witness is not hidden")
    _check(policy.path_role("references") == "inaccessible_harness", "references are not inaccessible")
    return {"non_disclosure": "PASS", "writable_paths": list(policy.writable_paths)}


def _validate_runtime(package: Path, node: Path) -> dict[str, Any]:
    qualification = _object(package / "validation/node-runtime-qualification.json")
    node = node.resolve(strict=True)
    _check(node.is_file() and os.access(node, os.X_OK), "qualified Node executable unavailable")
    _check(sha256_file(node) == NODE_SHA256, "qualified Node executable hash mismatch")
    process = subprocess.run((str(node), "--version"), capture_output=True, text=True, check=False, timeout=10)
    _check(process.returncode == 0 and process.stdout.strip() == "v20.19.5", "qualified Node version mismatch")
    _check(qualification.get("qualification", {}).get("status") == "PASS", "runtime qualification failed")
    _check(qualification.get("executable", {}).get("sha256") == NODE_SHA256, "runtime qualification hash mismatch")
    return {"node_sha256": NODE_SHA256, "node_version": "v20.19.5", "status": "PASS"}


def _run_evaluator(package: Path, repository: Path, kind: str, node: Path) -> dict[str, Any]:
    script = package / f"oracles/{kind}/evaluate.py"
    command = (sys.executable, str(script), "--repository", str(repository), "--timeout-seconds", "5")
    environment = {
        "CMPILOT_AXIOS_NODE": str(node),
        "HOME": str(repository.parent),
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": os.defpath,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "TMPDIR": str(repository.parent),
    }
    before = sha256_file(script)
    completed = subprocess.run(command, capture_output=True, check=False, env=environment, timeout=20)
    _check(
        completed.returncode == 0,
        f"{kind} evaluator failed: stdout={completed.stdout[:800]!r}; "
        f"stderr={completed.stderr[:400]!r}",
    )
    _check(sha256_file(script) == before, f"{kind} evaluator changed during execution")
    try:
        value = json.loads(completed.stdout.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AxiosValidationError(f"{kind} evaluator emitted invalid JSON") from error
    _check(isinstance(value, dict) and value.get("complete") is True, f"{kind} evaluator incomplete")
    _check(isinstance(value.get("passed"), bool), f"{kind} evaluator result invalid")
    value.pop("node_stderr", None)
    return value


def _case(
    package: Path,
    source: Path,
    node: Path,
    *,
    safe: bool,
    include_functional: bool = True,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="cmpilot-axios-validation-") as directory:
        repository = Path(directory) / "repository"
        copy_repository_tree(source, repository)
        if safe:
            patch = package / "references/safe-control/secure.patch"
            completed = subprocess.run(
                ("git", "apply", "--whitespace=error", str(patch)),
                cwd=repository,
                capture_output=True,
                check=False,
                timeout=10,
            )
            _check(completed.returncode == 0, f"safe-control patch failed: {completed.stderr[:400]!r}")
        repetitions = []
        for _ in range(2):
            result = {"security": _run_evaluator(package, repository, "security", node)}
            if include_functional:
                result["functional"] = _run_evaluator(
                    package, repository, "functional", node
                )
            repetitions.append(result)
        _check(repetitions[0] == repetitions[1], "evaluator repetitions are not deterministic")
        return repetitions[0]


def _validate_oracles(package: Path, node: Path) -> dict[str, Any]:
    manifest = _object(package / "oracles/manifest.json")
    files = manifest.get("files")
    _check(manifest.get("schema") == "cmpilot-axios-oracle-manifest-v1", "oracle manifest schema mismatch")
    _check(isinstance(files, Mapping), "oracle file inventory missing")
    for relative, expected in files.items():
        path = package / "oracles" / relative
        _check(path.is_file() and sha256_file(path) == expected, f"oracle file mismatch: {relative}")
    controlled = manifest.get("controlled_environment")
    _check(isinstance(controlled, Mapping) and controlled.get("network_required") is False, "oracle requires external network")

    source = _case(
        package,
        package / "repositories/source",
        node,
        safe=False,
        include_functional=False,
    )
    compatible = _case(
        package,
        package / "repositories/compatible",
        node,
        safe=False,
        include_functional=False,
    )
    faithful = _case(package, package / "repositories/invalidated", node, safe=False)
    safe = _case(package, package / "repositories/invalidated", node, safe=True)
    _check(source["security"]["passed"] is True, "p*(S) executable check failed")
    _check(compatible["security"]["passed"] is True, "p*(C) executable check failed")
    _check(faithful["functional"]["passed"] is True and faithful["security"]["passed"] is False, "faithful-reuse contrast failed")
    _check(safe["functional"]["passed"] is True and safe["security"]["passed"] is True, "safe-control contrast failed")
    frozen_reference = _object(package / "references/reference-validation.json")
    _check(frozen_reference["faithful_reuse"]["functional"]["passed"] is True, "recorded faithful functional result invalid")
    _check(frozen_reference["faithful_reuse"]["security"]["passed"] is False, "recorded faithful security result invalid")
    _check(frozen_reference["safe_control"]["functional"]["passed"] is True, "recorded safe functional result invalid")
    _check(frozen_reference["safe_control"]["security"]["passed"] is True, "recorded safe security result invalid")
    return {"compatible": compatible, "faithful_reuse": faithful, "safe_control": safe, "source": source}


def validate(package: Path, node: Path, *, prefreeze: bool) -> dict[str, Any]:
    package = package.resolve(strict=True)
    _check(package.is_dir() and not package.is_symlink(), "family package root is unsafe")
    package_value, package_result = _validate_package(package, prefreeze=prefreeze)
    result = {
        "family_id": FAMILY_ID,
        "family_package": package_result,
        "memory": _validate_memory(package),
        "oracles_and_references": _validate_oracles(package, node),
        "runtime": _validate_runtime(package, node),
        "schema": SCHEMA,
        "snapshots": _validate_snapshots(package),
        "status": "PASS",
        "task": _validate_task(package),
        "transition": _validate_transition(package),
        "validated_model_ready": package_value["model_ready"],
    }
    return result


def _write_new(path: Path, result: Mapping[str, Any]) -> str:
    payload = canonical_json_bytes(result)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as error:
        raise AxiosValidationError(f"refusing to overwrite validation result: {path}") from error
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    return hashlib.sha256(payload).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=ROOT / "families/axios-v1")
    parser.add_argument("--node", type=Path, default=ROOT / "tmp/axios-node-runtime-v1/bin/node")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--prefreeze", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = validate(arguments.package, arguments.node, prefreeze=arguments.prefreeze)
        if arguments.output is not None:
            digest = _write_new(arguments.output, result)
            print(json.dumps({"output": str(arguments.output), "sha256": digest, "status": "PASS"}, sort_keys=True))
        else:
            sys.stdout.buffer.write(canonical_json_bytes(result))
    except (AxiosValidationError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(f"Axios family validation failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
