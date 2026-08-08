#!/usr/bin/env python3
"""Controller-side completion and twice-idempotent manifest validation."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
from typing import Any


EXCLUDED = frozenset(
    {
        "artifact-preservation-idempotency.json",
        "manifest-validation.json",
        "sha256-manifest.txt",
    }
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _copy_file(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise FileNotFoundError(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)


def _rows(artifact: Path) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for path in sorted(artifact.rglob("*"), key=lambda item: item.as_posix()):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(artifact).as_posix()
        if path.name in EXCLUDED or path.name.startswith("preservation-pass-"):
            continue
        rows.append((_sha256(path), relative))
    return rows


def _preserve(artifact: Path, pass_number: int) -> dict[str, Any]:
    rows = _rows(artifact)
    text = "".join(f"{digest}  {relative}\n" for digest, relative in rows)
    (artifact / "sha256-manifest.txt").write_text(text, encoding="utf-8")
    inventory = hashlib.sha256(
        (
            json.dumps(rows, separators=(",", ":"), sort_keys=True) + "\n"
        ).encode("utf-8")
    ).hexdigest()
    record = {
        "pass_number": pass_number,
        "entry_count": len(rows),
        "inventory_sha256": inventory,
        "manifest_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
    }
    _write_json(artifact / f"preservation-pass-{pass_number}.json", record)
    return record


def _validate(artifact: Path) -> dict[str, Any]:
    errors: list[str] = []
    paths: set[str] = set()
    manifest = artifact / "sha256-manifest.txt"
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, separator, relative = line.partition("  ")
        paths.add(relative)
        path = artifact / relative
        if separator != "  " or not path.is_file() or _sha256(path) != digest:
            errors.append(relative or line)
    return {
        "pass": not errors and "sha256-manifest.txt" not in paths,
        "errors": errors,
        "entry_count": len(paths),
        "manifest_sha256": _sha256(manifest),
        "self_excluding": "sha256-manifest.txt" not in paths,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-directory", type=Path, required=True)
    parser.add_argument("--pre-submit-directory", type=Path, required=True)
    parser.add_argument("--controller-attestation", type=Path, required=True)
    parser.add_argument("--slurm-stdout", type=Path, required=True)
    parser.add_argument("--slurm-stderr", type=Path, required=True)
    parser.add_argument("--slurm-accounting", type=Path, required=True)
    arguments = parser.parse_args()
    artifact = arguments.artifact_directory.resolve(strict=True)
    pre_submit = arguments.pre_submit_directory.resolve(strict=True)
    attestation_source = arguments.controller_attestation.resolve(strict=True)
    attestation_destination = artifact / "controller-attestation"
    if attestation_destination.exists():
        shutil.copytree(
            attestation_source,
            attestation_destination,
            dirs_exist_ok=True,
            copy_function=shutil.copyfile,
        )
    else:
        shutil.copytree(
            attestation_source,
            attestation_destination,
            copy_function=shutil.copyfile,
        )
    _copy_file(arguments.slurm_stdout, artifact / "slurm.stdout")
    _copy_file(arguments.slurm_stderr, artifact / "slurm.stderr")
    _copy_file(arguments.slurm_accounting, artifact / "slurm-accounting.txt")
    for name in (
        "implementation.diff",
        "initial-git-state.json",
        "project-runtime-manifest.json",
        "runtime-manifest.json",
        "protected-oracle-cpu-gate.sbatch",
        "protected-oracle-cpu-gate.py",
        "calculator-final-harness-cpu-gate.sbatch",
        "calculator-final-harness-cpu-gate.py",
        "local-complete-tests.stdout",
        "local-complete-tests.stderr",
        "local-complete-tests.exit",
        "local-targeted-tests.stdout",
        "local-targeted-tests.stderr",
        "local-targeted-tests.exit",
        "job-25642-forensic-review.json",
    ):
        source = pre_submit / name
        if source.is_file():
            _copy_file(source, artifact / "pre-submit-evidence" / name)
    project_runtime = pre_submit / "project-runtime"
    if project_runtime.is_dir():
        shutil.copytree(
            project_runtime,
            artifact / "pre-submit-evidence" / "project-runtime",
            dirs_exist_ok=True,
            copy_function=shutil.copyfile,
        )
    attestation = json.loads(
        (attestation_destination / "attested-submission-result.json").read_text(
            encoding="utf-8"
        )
    )
    result = json.loads((artifact / "result.json").read_text(encoding="utf-8"))
    finalization = {
        "controller_attestation_pass": attestation.get("pass") is True,
        "cpu_gate_pass": result.get("pass") is True,
        "slurm_stdout_preserved": (artifact / "slurm.stdout").is_file(),
        "slurm_stderr_preserved": (artifact / "slurm.stderr").is_file(),
        "slurm_accounting_preserved": (artifact / "slurm-accounting.txt").is_file(),
    }
    finalization["pass"] = all(finalization.values())
    _write_json(artifact / "controller-finalization.json", finalization)
    first = _preserve(artifact, 1)
    second = _preserve(artifact, 2)
    idempotency = {
        "pass": first["inventory_sha256"] == second["inventory_sha256"],
        "first": first,
        "second": second,
    }
    _write_json(artifact / "artifact-preservation-idempotency.json", idempotency)
    _preserve(artifact, 2)
    validation = _validate(artifact)
    _write_json(artifact / "manifest-validation.json", validation)
    passed = finalization["pass"] and idempotency["pass"] and validation["pass"]
    print(
        json.dumps(
            {
                "artifact_directory": str(artifact),
                "idempotency": idempotency["pass"],
                "manifest": validation,
                "pass": passed,
            },
            sort_keys=True,
        )
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
