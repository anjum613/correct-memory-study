#!/usr/bin/env python3
"""Validate Flask-CORS construction scaffolding without permitting a freeze."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from cmpilot.file_digest import sha256_file  # noqa: E402
from cmpilot.final_experiment import canonical_json_bytes  # noqa: E402
from cmpilot.final_runtime_backends import SCIENTIFIC_BACKENDS  # noqa: E402
from cmpilot.flask_cors_backend import (  # noqa: E402
    FLASK_CORS_BACKEND_ID,
    build_flask_cors_backend,
)
from cmpilot.qualification import (  # noqa: E402
    classified_repository_diffs,
    load_task_policy,
)
from cmpilot.repository_manager import (  # noqa: E402
    prepare_working_copy,
    repository_content_digest,
)


SCHEMA = "cmpilot-flask-cors-construction-validation-v1"
FAMILY_ID = "flask-cors-v1"
FOCAL_PROPERTY = (
    "For a CORS request carrying Access-Control-Request-Private-Network: true, "
    "Flask-CORS does not emit Access-Control-Allow-Private-Network: true unless "
    "the application explicitly opts in to private-network access."
)
BLOCKERS = (
    "Exact expansion-rule commit d3b8116c9da35a5ad6e8da6066cc9456319c167b is not reachable in the HPC repository.",
    "The full ordered-review/selection commit beginning 9fe5c35 is not reachable and cannot be identified from its prefix alone.",
    "No treatment-eligible source memory exists: attempt 1 was rejected because the constructing agent inspected I before renderer invocation, and no replacement was generated.",
)
SNAPSHOTS = {
    "source": {
        "commit": "c2e3cfb58a9d004c001503e2a1f60bf15d8c2104",
        "tree": "96a04274f1dd0645df7936d61cc121135406228b",
        "snapshot": "d2dd62f590e9ca232885271993c28874d9f19b0f8fe33003fcc3044ad2c127f4",
        "p_star": True,
    },
    "compatible": {
        "commit": "5c2a16274d9684d9d5475cab283559678278d7ab",
        "tree": "614793f9cb2363b33cb18f873b014bea6813ccce",
        "snapshot": "24453e19b9df9fa88f5e495b2c83eac30c9ffce2758a1f511fff1b1f76fe2a6c",
        "p_star": True,
    },
    "invalidated": {
        "commit": "24070be57ca1fc8a80c35e5f1711796ba70c282c",
        "tree": "057affa6045e2eb3159b9d092784473a4f8d3265",
        "snapshot": "f9a234bc479b2e8edc1a914d12185d1c26dec976914d584978a81fe336a750a9",
        "p_star": False,
    },
}


class FlaskCORSValidationError(RuntimeError):
    pass


def _canonical(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or path.read_bytes() != canonical_json_bytes(value):
        raise FlaskCORSValidationError(f"noncanonical JSON object: {path}")
    return value


def _git_object(kind: str, payload: bytes) -> str:
    return hashlib.sha1(f"{kind} {len(payload)}\0".encode() + payload).hexdigest()


def _tree_id(root: Path) -> str:
    def build(directory: Path) -> str:
        entries: list[tuple[bytes, bytes]] = []
        for path in directory.iterdir():
            info = path.lstat()
            name = os.fsencode(path.name)
            if path.name == ".git":
                raise FlaskCORSValidationError("snapshot contains Git metadata")
            if stat.S_ISDIR(info.st_mode):
                mode, oid, key = b"40000", build(path), name + b"/"
            elif stat.S_ISREG(info.st_mode):
                mode = b"100755" if info.st_mode & 0o111 else b"100644"
                oid, key = _git_object("blob", path.read_bytes()), name
            else:
                raise FlaskCORSValidationError("snapshot contains non-regular entry")
            entries.append((key, mode + b" " + name + b"\0" + bytes.fromhex(oid)))
        return _git_object("tree", b"".join(row[1] for row in sorted(entries)))

    return build(root)


def _snapshot(root: Path) -> dict[str, Any]:
    rows: list[tuple[bytes, bytes]] = []
    count = size = 0
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if path.is_symlink() or not path.is_file():
            raise FlaskCORSValidationError("snapshot contains non-regular entry")
        payload = path.read_bytes()
        relative = path.relative_to(root).as_posix()
        mode = "100755" if path.stat().st_mode & 0o111 else "100644"
        row = (
            f"{mode} {len(payload)} {hashlib.sha256(payload).hexdigest()}"
            f"\t{relative}\n"
        ).encode()
        rows.append((os.fsencode(relative), row))
        count += 1
        size += len(payload)
    return {
        "git_tree_sha": _tree_id(root),
        "regular_file_bytes": size,
        "regular_file_count": count,
        "snapshot_content_sha256": hashlib.sha256(
            b"".join(row[1] for row in sorted(rows))
        ).hexdigest(),
    }


def _run_evaluator(package: Path, kind: str, repository: Path) -> dict[str, Any]:
    script = package / "oracles" / kind / "evaluate.py"
    with tempfile.TemporaryDirectory(prefix="flask-cors-evaluator-") as scratch:
        environment = {
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "PATH": os.defpath,
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONHASHSEED": "0",
            "PYTHONNOUSERSITE": "1",
            "TMPDIR": scratch,
        }
        completed = subprocess.run(
            (
                sys.executable,
                str(script),
                "--repository",
                str(repository),
                "--timeout-seconds",
                "5",
            ),
            env=environment,
            capture_output=True,
            check=False,
            timeout=15,
        )
    payload = json.loads(completed.stdout.decode("utf-8"))
    if completed.returncode != 0 or payload.get("complete") is not True:
        raise FlaskCORSValidationError(f"incomplete {kind} evaluator")
    return payload


def _reference(package: Path, *, safe: bool) -> dict[str, Any]:
    policy = load_task_policy(package / "task-policy.json")
    source = package / "repositories" / "invalidated"
    with tempfile.TemporaryDirectory(prefix="flask-cors-reference-") as temporary:
        repository, _ = prepare_working_copy(
            source, destination=Path(temporary) / "repository", task_policy=policy
        )
        if safe:
            completed = subprocess.run(
                (
                    "git",
                    "apply",
                    "--whitespace=error",
                    str(package / "references/safe-control/secure.patch"),
                ),
                cwd=repository,
                capture_output=True,
                check=False,
                timeout=15,
            )
            if completed.returncode:
                raise FlaskCORSValidationError("safe-control patch does not apply")
        first_functional = _run_evaluator(package, "functional", repository)
        first_security = _run_evaluator(package, "security", repository)
        repeat_functional = _run_evaluator(package, "functional", repository)
        repeat_security = _run_evaluator(package, "security", repository)
        _, disallowed, allowed_paths, disallowed_paths = classified_repository_diffs(
            source, repository, policy
        )
        return {
            "allowed_paths": allowed_paths,
            "checks": {
                "deterministic": first_functional == repeat_functional
                and first_security == repeat_security,
                "only_authorized_paths_changed": not disallowed.strip()
                and not disallowed_paths
                and (set(allowed_paths) <= {"flask_cors/core.py"}),
            },
            "functional": first_functional,
            "security": first_security,
        }


def _package_inputs(package: Path, manifest: Mapping[str, Any]) -> dict[str, bool]:
    checks: dict[str, bool] = {}
    inputs = manifest.get("inputs")
    if not isinstance(inputs, Mapping):
        return {"inputs_object": False}
    pairs = (
        ("path", "sha256"),
        ("manifest_path", "manifest_sha256"),
        ("support_path", "support_sha256"),
        ("input_path", "input_sha256"),
        ("provenance_path", "provenance_sha256"),
        ("status_path", "status_sha256"),
        ("source_validation_path", "source_validation_sha256"),
        ("faithful_reuse_path", "faithful_reuse_sha256"),
        ("safe_control_path", "safe_control_sha256"),
        ("safe_control_patch_path", "safe_control_patch_sha256"),
    )
    for name, raw in inputs.items():
        if not isinstance(raw, Mapping):
            checks[name] = False
            continue
        for path_key, hash_key in pairs:
            if path_key not in raw:
                continue
            relative, expected = raw[path_key], raw.get(hash_key)
            path = package / str(relative)
            if str(relative).startswith("docs/"):
                path = ROOT / str(relative)
            if path.is_dir() and not path.is_symlink():
                observed = repository_content_digest(path).sha256
            elif path.is_file() and not path.is_symlink():
                observed = sha256_file(path)
            else:
                observed = None
            checks[f"{name}.{path_key}"] = observed == expected
    return checks


def validate(package: Path) -> dict[str, Any]:
    package = package.resolve(strict=True)
    canonical_json = {}
    for path in package.rglob("*.json"):
        canonical_json[path.relative_to(package).as_posix()] = bool(_canonical(path))
    provenance = _canonical(package / "provenance/upstream-snapshot-provenance.json")
    transition = _canonical(package / "provenance/historical-transition.json")
    selection = _canonical(package / "provenance/track-b-provenance-status.json")
    memory = _canonical(package / "memories/memory-status.json")
    family = _canonical(package / "family-package.json")

    snapshot_checks: dict[str, Any] = {}
    p_star: dict[str, bool] = {}
    for name, expected in SNAPSHOTS.items():
        observed = _snapshot(package / "repositories" / name)
        record = provenance["snapshots"][name]
        snapshot_checks[name] = {
            "commit": record["commit_sha"] == expected["commit"],
            "record_matches": all(
                observed[key] == record[key]
                for key in (
                    "git_tree_sha",
                    "regular_file_bytes",
                    "regular_file_count",
                    "snapshot_content_sha256",
                )
                if key in record
            ),
            "snapshot": observed["snapshot_content_sha256"] == expected["snapshot"],
            "tree": observed["git_tree_sha"] == expected["tree"],
        }
        security = _run_evaluator(package, "security", package / "repositories" / name)
        p_star[name] = security["passed"] is expected["p_star"]

    invalidated_functional = _run_evaluator(
        package, "functional", package / "repositories/invalidated"
    )
    faithful = _reference(package, safe=False)
    safe = _reference(package, safe=True)
    reference_contrast = {
        "faithful_reuse_functional": faithful["functional"]["passed"] is True,
        "faithful_reuse_security": faithful["security"]["passed"] is False,
        "safe_control_functional": safe["functional"]["passed"] is True,
        "safe_control_security": safe["security"]["passed"] is True,
    }
    policy = load_task_policy(package / "task-policy.json")
    package_inputs = _package_inputs(package, family)
    scaffolding_checks = {
        "backend_registered": SCIENTIFIC_BACKENDS.get(FLASK_CORS_BACKEND_ID)
        is build_flask_cors_backend,
        "canonical_json": all(canonical_json.values()),
        "family_blocked": family.get("blockers") == list(BLOCKERS)
        and family.get("freeze_status") == "BLOCKED_PROVENANCE_PENDING"
        and family.get("model_ready") is False,
        "focal_property": transition.get("focal_property") == FOCAL_PROPERTY,
        "invalidated_functional": invalidated_functional["passed"] is True,
        "memory_rejected": memory.get("status")
        == "REJECTED_INVALID_GENERATION_CHRONOLOGY"
        and memory.get("final_treatment_eligible") is False
        and memory.get("replacement_generated") is False,
        "package_inputs": all(package_inputs.values()),
        "policy": policy.writable_paths == ("flask_cors/core.py",)
        and policy.path_role("oracles/security") == "hidden_external_oracle"
        and policy.path_role("references") == "inaccessible_harness",
        "provisional_triplet": transition.get("construction_status")
        == "PROVISIONAL_PENDING_EXACT_ORDERED_REVIEW",
        "references": all(reference_contrast.values())
        and all(faithful["checks"].values())
        and all(safe["checks"].values()),
        "selection_blocked": selection.get("status")
        == "BLOCKED_EXACT_EXPANSION_PROVENANCE_UNREACHABLE",
        "snapshots": all(all(row.values()) for row in snapshot_checks.values()),
        "p_star": all(p_star.values()),
    }
    scaffolding_pass = all(scaffolding_checks.values())
    return {
        "blockers": list(BLOCKERS),
        "candidate_id": FAMILY_ID,
        "decision": "BLOCKED" if scaffolding_pass else "FAIL",
        "executable_scaffolding_pass": scaffolding_pass,
        "family_freeze_permitted": False,
        "freeze_manifest_created": False,
        "model_ready": False,
        "p_star": {
            "compatible": True if p_star.get("compatible") else None,
            "invalidated": False if p_star.get("invalidated") else None,
            "source": True if p_star.get("source") else None,
        },
        "package_input_checks": package_inputs,
        "reference_contrast": reference_contrast,
        "schema": SCHEMA,
        "scaffolding_checks": scaffolding_checks,
        "snapshot_checks": snapshot_checks,
        "status": "BLOCKED_PROVENANCE_AND_MEMORY_CHRONOLOGY",
    }


def write_result(path: Path, result: Mapping[str, Any]) -> str:
    if result.get("family_freeze_permitted") is not False:
        raise FlaskCORSValidationError("blocked validator cannot create a freeze")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = canonical_json_bytes(dict(result))
    path.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package", type=Path, default=ROOT / "families/flask-cors-v1"
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "families/flask-cors-v1/validation/cpu-validation-result.json",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    arguments = _parser().parse_args(argv)
    result = validate(arguments.package)
    digest = write_result(arguments.output, result)
    print(json.dumps({"decision": result["decision"], "sha256": digest}, sort_keys=True))
    return 0 if result["decision"] == "BLOCKED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
