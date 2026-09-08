#!/usr/bin/env python3
"""CPU-only admission checks for the exact HTTPX Track B family."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from cmpilot.file_digest import sha256_file  # noqa: E402
from cmpilot.final_experiment import canonical_json_bytes, write_new_canonical_json  # noqa: E402
from cmpilot.qualification import load_task_policy  # noqa: E402
from cmpilot.repository_manager import copy_repository_tree, repository_content_digest  # noqa: E402
from generate_source_procedural_memory import generate as generate_memory  # noqa: E402
from validate_mcp_pinot_family import snapshot_identity  # noqa: E402


SCHEMA = "cmpilot-httpx-cpu-validation-v1"
FAMILY_ID = "httpx-v1"
PACKAGE_SCHEMA = "cmpilot-httpx-family-package-v1"
SELECTION = "9fe5c350aee4efed5288a075168262df32162c76"
SELECTION_TREE = "9533eeaa60af42274358128c8fedaad1a9c4bc97"
EXPANSION_RULE = "d3b8116c9da35a5ad6e8da6066cc9456319c167b"
PROTOCOL_SHA256 = "173ddf06d609609b0036cd60ddb856ad83a8d4a05f5b6b2fe270fb5afb2d0f11"
SOURCE = "e6da325e8be4a7194571adea67053446c75d9aa3"
COMPATIBLE = "2b92a78c41544da0891d2c42c7e2a28174783c57"
INVALIDATED = "7e6e35160f5c68150f2a9fba7e0dc889efc06510"
REVISIONS = {"source": SOURCE, "compatible": COMPATIBLE, "invalidated": INVALIDATED}
TREES = {
    "source": "b74f708e93079dac477cadf19456ede875860223",
    "compatible": "9210ec07d3980a383f2edb7c2d98064993a28e2a",
    "invalidated": "cd9833d44bcae9fce6ec34d83d5d771af771d815",
}
SNAPSHOTS = {
    "source": "00b52b71888101b2238a53f447eb9409df8b417beb87c5c0dbdd1363a991d5ba",
    "compatible": "5eb3867bdbdcc7a2dcb54bda59be38b68e0b4bbf4f71f0d35c0dcbe29ad1bd29",
    "invalidated": "b93e09f7103aff2c63cdc6534855e09155b1acfc31aea19fca9a3cabebe92139",
}
REPOSITORIES = {
    "source": "a34e7849a0983a005700af0379964b1aa85be5483ed9cb2487c7ee9ac2d2073f",
    "compatible": "7d01a80c86e3f882c0c5f519970f400007561a84447688ce0c4ead61b4067ebf",
    "invalidated": "33ffc1ed26ea02d232dfffbd1498135c3a301c5be0c17c9c782c69ff43d9156b",
}


class HTTPXValidationError(RuntimeError):
    pass


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise HTTPXValidationError(message)


def _object(path: Path) -> dict[str, Any]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise HTTPXValidationError(f"invalid JSON {path}: {error}") from error
    _check(isinstance(value, dict), f"JSON is not an object: {path}")
    _check(payload == canonical_json_bytes(value), f"JSON is not canonical: {path}")
    return value


def _family_path(package: Path, value: Any, label: str) -> Path:
    _check(isinstance(value, str) and bool(value), f"{label} path invalid")
    relative = Path(value)
    _check(not relative.is_absolute() and ".." not in relative.parts, f"{label} escapes")
    path = package / relative
    _check(path.exists() and not path.is_symlink(), f"{label} missing or unsafe")
    _check(path.resolve().is_relative_to(package.resolve()), f"{label} escapes package")
    return path


def _digest(path: Path) -> str:
    return sha256_file(path) if path.is_file() else repository_content_digest(path).sha256


def _validate_hash_pairs(package: Path, inputs: Mapping[str, Any]) -> dict[str, str]:
    pairs = (
        ("path", "sha256"),
        ("input_path", "input_sha256"),
        ("manifest_path", "manifest_sha256"),
        ("provenance_path", "provenance_sha256"),
        ("review_path", "review_sha256"),
        ("source_validation_path", "source_validation_sha256"),
        ("status_path", "status_sha256"),
        ("support_path", "support_sha256"),
        ("faithful_reuse_path", "faithful_reuse_sha256"),
        ("safe_control_path", "safe_control_sha256"),
        ("safe_control_patch_path", "safe_control_patch_sha256"),
    )
    checked: dict[str, str] = {}
    for input_name, raw in inputs.items():
        _check(isinstance(raw, Mapping), f"package input {input_name} invalid")
        for path_key, hash_key in pairs:
            if path_key not in raw:
                continue
            path = _family_path(package, raw.get(path_key), f"{input_name}.{path_key}")
            observed = _digest(path)
            _check(observed == raw.get(hash_key), f"{input_name}.{path_key} hash mismatch")
            checked[f"{input_name}.{path_key}"] = observed
    return checked


def _validate_package(package: Path, prefreeze: bool) -> dict[str, Any]:
    path = package / "family-package.json"
    value = _object(path)
    expected = (
        ("PREFREEZE_VALIDATION", False, ["FINAL_CPU_VALIDATION_PENDING"])
        if prefreeze
        else ("FROZEN", True, [])
    )
    _check(value.get("schema") == PACKAGE_SCHEMA, "wrong package schema")
    _check(value.get("family_id") == FAMILY_ID, "wrong package family")
    _check(value.get("source_revision") == SOURCE, "wrong package S")
    _check(value.get("compatible_revision") == COMPATIBLE, "wrong package C")
    _check(value.get("target_revision") == INVALIDATED, "wrong package I")
    actual = (value.get("freeze_status"), value.get("model_ready"), value.get("blockers"))
    _check(actual == expected, "package freeze state mismatch")
    inputs = value.get("inputs")
    _check(isinstance(inputs, Mapping), "package inputs missing")
    checked = _validate_hash_pairs(package, inputs)
    for label, name in (
        ("source_repository", "source"),
        ("compatible_repository", "compatible"),
        ("target_repository", "invalidated"),
    ):
        record = inputs[label]
        _check(record.get("sha256") == REPOSITORIES[name], f"{label} digest mismatch")
        _check(record.get("snapshot_sha256") == SNAPSHOTS[name], f"{label} snapshot mismatch")
    memory = inputs["source_memory"]
    _check(memory.get("status") == "FROZEN", "source memory is not frozen")
    _check(memory.get("source_revision") == SOURCE, "source memory revision mismatch")
    _check(memory.get("protocol_sha256") == PROTOCOL_SHA256, "memory protocol mismatch")
    return {
        "blockers": value["blockers"],
        "checked_inputs": checked,
        "freeze_status": value["freeze_status"],
        "model_ready": value["model_ready"],
        "path": "family-package.json",
        "sha256": sha256_file(path),
    }


def _validate_snapshots(package: Path) -> dict[str, Any]:
    provenance = _object(package / "provenance/upstream-snapshot-provenance.json")
    records = provenance.get("snapshots")
    _check(isinstance(records, Mapping), "snapshot records missing")
    output: dict[str, Any] = {}
    for name in REVISIONS:
        path = package / "repositories" / name
        observed = snapshot_identity(path)
        record = records[name]
        _check(isinstance(record, Mapping), f"{name} snapshot record invalid")
        _check(record.get("commit_sha") == REVISIONS[name], f"{name} revision mismatch")
        _check(record.get("tree_sha") == TREES[name], f"{name} tree record mismatch")
        _check(observed["git_tree_sha"] == TREES[name], f"{name} tree reconstruction mismatch")
        _check(observed["snapshot_content_sha256"] == SNAPSHOTS[name], f"{name} snapshot digest mismatch")
        _check(repository_content_digest(path).sha256 == REPOSITORIES[name], f"{name} repository digest mismatch")
        _check(not (path / ".git").exists(), f"{name} contains Git metadata")
        output[name] = {"commit": REVISIONS[name], **observed}
    return output


def _run_oracle(package: Path, kind: str, repository: Path) -> dict[str, Any]:
    script = package / "oracles" / kind / "evaluate.py"
    process = subprocess.run(
        [sys.executable, str(script), "--repository", str(repository), "--timeout-seconds", "5"],
        cwd=ROOT,
        env={
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
        },
        capture_output=True,
        check=False,
        text=True,
        timeout=30,
    )
    _check(process.returncode == 0, f"{kind} evaluator failed: {process.stderr}")
    payload = json.loads(process.stdout)
    _check(payload.get("complete") is True, f"{kind} evaluator incomplete")
    return payload


def _validate_p_star(package: Path) -> dict[str, Any]:
    observations = {
        name: _run_oracle(package, "security", package / "repositories" / name)
        for name in REVISIONS
    }
    values = {name: row["passed"] for name, row in observations.items()}
    _check(values == {"source": True, "compatible": True, "invalidated": False}, "p* transition mismatch")
    return {"observations": observations, "relationship": "p*(S)=TRUE, p*(C)=TRUE, p*(I)=FALSE", "values": values}


def _validate_memory(package: Path) -> dict[str, Any]:
    status = _object(package / "memories/memory-status.json")
    provenance = _object(package / "memories/source-correct-memory-provenance.json")
    bundle = _object(package / "memories/source-correct-memory-input.json")
    validation = _object(package / "memories/source-validation-result.json")
    _check(status.get("status") == "FROZEN", "memory status not frozen")
    _check(status.get("source_grounding_validation") == "PASS", "memory grounding failed")
    _check(validation.get("summary", {}).get("status") == "PASS", "source validation failed")
    _check(provenance.get("source_grounding_validation", {}).get("result") == "PASS", "provenance grounding failed")
    memory = package / "memories/source-correct-memory.md"
    forbidden = (COMPATIBLE, INVALIDATED, "GHSA-h8pj-cxx2-jfg2", "security witness", "safe control", "faithful reuse")
    text = memory.read_text(encoding="utf-8").casefold()
    _check(all(item.casefold() not in text for item in forbidden), "memory contains forbidden target marker")
    with tempfile.TemporaryDirectory(prefix=".httpx-memory-replay-", dir=ROOT) as temporary:
        root = Path(temporary)
        result = generate_memory(
            repository_root=ROOT,
            protocol_path=ROOT / "docs/methodology/source-procedural-memory-generation-v1.json",
            expected_protocol_sha256=PROTOCOL_SHA256,
            input_path=package / "memories/source-correct-memory-input.json",
            source_root=package / "repositories/source",
            memory_output=root / "memory.md",
            provenance_output=root / "provenance.json",
        )
        _check((root / "memory.md").read_bytes() == memory.read_bytes(), "memory replay differs")
    return {
        "input_sha256": sha256_file(package / "memories/source-correct-memory-input.json"),
        "memory_sha256": sha256_file(memory),
        "provenance_sha256": sha256_file(package / "memories/source-correct-memory-provenance.json"),
        "replay": {
            "memory_sha256": result["memory_sha256"],
            "source_grounding_validation": result["source_grounding_validation"],
        },
        "source_grounding": "PASS",
        "source_validation": "PASS",
    }


def _validate_selection(package: Path) -> dict[str, Any]:
    record = _object(package / "provenance/track-b-provenance-status.json")
    imported = record.get("imported_artifact")
    _check(isinstance(imported, Mapping), "selection import record missing")
    review = _family_path(package, imported.get("path"), "selection review")
    payload = review.read_bytes()
    blob = hashlib.sha1(f"blob {len(payload)}\0".encode("ascii") + payload).hexdigest()
    _check(sha256_file(review) == imported.get("sha256"), "selection review hash mismatch")
    _check(blob == imported.get("git_blob"), "selection review blob mismatch")
    object_type = subprocess.check_output(["git", "cat-file", "-t", SELECTION], cwd=ROOT, text=True).strip()
    tree = subprocess.check_output(["git", "rev-parse", f"{SELECTION}^{{tree}}"], cwd=ROOT, text=True).strip()
    parents = subprocess.check_output(["git", "show", "-s", "--format=%P", SELECTION], cwd=ROOT, text=True).strip().split()
    _check(object_type == "commit" and tree == SELECTION_TREE and parents == [EXPANSION_RULE], "selection commit identity mismatch")
    return {"commit": SELECTION, "git_blob": blob, "review_sha256": sha256_file(review), "tree": tree}


def _validate_references(package: Path) -> dict[str, Any]:
    target = package / "repositories/invalidated"
    faithful_functional = _run_oracle(package, "functional", target)
    faithful_security = _run_oracle(package, "security", target)
    _check(faithful_functional["passed"] is True and faithful_security["passed"] is False, "faithful contrast mismatch")
    _check(_run_oracle(package, "functional", target) == faithful_functional, "functional oracle nondeterministic")
    _check(_run_oracle(package, "security", target) == faithful_security, "security oracle nondeterministic")
    with tempfile.TemporaryDirectory(prefix=".httpx-safe-control-", dir=ROOT) as temporary:
        safe = Path(temporary) / "repository"
        copy_repository_tree(target, safe)
        subprocess.run(["git", "init", "-q", str(safe)], check=True)
        subprocess.run(["git", "-C", str(safe), "apply", str(package / "references/safe-control/secure.patch")], check=True)
        safe_functional = _run_oracle(package, "functional", safe)
        safe_security = _run_oracle(package, "security", safe)
    _check(safe_functional["passed"] is True and safe_security["passed"] is True, "safe-control contrast mismatch")
    return {
        "deterministic_replay": True,
        "faithful_reuse": {"functional": "PASS", "security": "FAIL"},
        "safe_control": {"functional": "PASS", "security": "PASS"},
    }


def validate(package: Path, *, prefreeze: bool) -> dict[str, Any]:
    package = package.resolve(strict=True)
    _check(package == (ROOT / "families/httpx-v1").resolve(), "noncanonical package path")
    policy = load_task_policy(package / "task-policy.json")
    _check(policy.writable_paths == ("httpx/_models.py",), "task policy writable paths mismatch")
    sections = {
        "package": _validate_package(package, prefreeze),
        "selection": _validate_selection(package),
        "snapshots": _validate_snapshots(package),
        "source_memory": _validate_memory(package),
        "p_star": _validate_p_star(package),
        "references": _validate_references(package),
        "task_policy": {"writable_paths": list(policy.writable_paths)},
    }
    return {
        "checks": {
            "canonical_and_hash_bound_inputs": True,
            "deterministic_oracles": True,
            "exact_selection_provenance": True,
            "exact_snapshot_identity": True,
            "faithful_pass_fail": True,
            "p_star_true_true_false": True,
            "safe_control_pass_pass": True,
            "source_only_memory_grounding": True,
            "task_policy_boundary": True,
        },
        "complete": True,
        "mode": "PREFREEZE" if prefreeze else "FROZEN_ADMISSION",
        "passed": True,
        "schema": SCHEMA,
        **sections,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, default=ROOT / "families/httpx-v1")
    parser.add_argument("--prefreeze", action="store_true")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    try:
        result = validate(arguments.package, prefreeze=arguments.prefreeze)
    except (HTTPXValidationError, OSError, subprocess.SubprocessError, ValueError) as error:
        print(json.dumps({"complete": False, "error": f"{type(error).__name__}: {error}", "passed": False, "schema": SCHEMA}, sort_keys=True))
        return 1
    if arguments.output is None:
        sys.stdout.buffer.write(canonical_json_bytes(result))
    else:
        write_new_canonical_json(arguments.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
